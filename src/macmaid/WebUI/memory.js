/* Memory workspace. Process selection is always keyed by PID + creation time.
   The primary table lists process families (application groups); expanding a
   group reveals the real child processes and their per-process RSS. Group
   memory uses the macOS physical footprint measured by footprint(1) — shared
   pages de-duplicated across the family — never a synthetic "PSS" estimate. */
const MAX_MEMORY_SELECTION = 100;

const memoryState = {
  snapshot: null,
  selected: new Set(),
  busy: false,
  loading: false,
  detailKey: null,
  detailGroup: null,
  detailData: null,
  detailRequest: 0,
  sortField: 'memoryBytes',
  sortAsc: false,
  expanded: new Set(),
  searchMatched: new Set()
};

function mt(key, values = {}) {
  let value = t(`memory.${key}`);
  if (value === undefined) value = key;
  for (const [name, replacement] of Object.entries(values)) value = value.replaceAll(`{${name}}`, String(replacement));
  return value;
}

function categoryIcon(row) {
  if (row.category === 'flutter' || (row.role && row.role.startsWith('dart'))) return 'square.stack.3d.up';
  if (row.category === 'developer' || row.role === 'typescript-server') return 'terminal';
  if (row.protected === 'system-process') return 'cpu';
  return 'app';
}

function groupIcon(group) {
  if (group.kind === 'application') return 'app';
  if (group.developer) return 'terminal';
  return 'memorychip';
}

function memoryGroupIcon(group, fallback = groupIcon(group)) {
  const symbol = sfSymbol(fallback);
  if (group.kind !== 'application' || !group.bundlePath) return symbol;
  const url = `/api/memory/icon?path=${encodeURIComponent(group.bundlePath)}`;
  return `${symbol}<img class="memory-app-icon" src="${escapeHtml(url)}" alt="" loading="lazy" decoding="async">`;
}

function memoryDuration(seconds) {
  const total = Math.max(0, Math.round(seconds));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

function memoryGrowthTime(row) {
  if (typeof row.growthWindowElapsedSeconds !== 'number') return null;
  const remaining = typeof row.growthWindowRemainingSeconds === 'number' ? row.growthWindowRemainingSeconds : 0;
  return {
    elapsed: row.growthWindowElapsedSeconds,
    remaining,
    total: row.growthWindowElapsedSeconds + remaining,
    percent: Math.round(Math.min(1, Math.max(0, row.growthWindowProgress ?? 0)) * 100)
  };
}

function memoryGrowthLabel(row) {
  if (row.growthBytes != null) return memorySigned(row.growthBytes);
  const time = memoryGrowthTime(row);
  if (time) {
    return `${mt('collecting')} · ${mt('collectingTime', {
      elapsed: memoryDuration(time.elapsed), total: memoryDuration(time.total), remaining: memoryDuration(time.remaining)
    })}`;
  }
  return mt(row.rssBytes == null ? 'unknown' : 'collecting');
}

function memoryGrowthCell(row, statusClass) {
  if (row.growthBytes != null) {
    return `<span class="memory-growth-pill ${statusClass}">${row.growing ? sfSymbol('chart.line.uptrend.xyaxis', 'mini-icon') : ''} ${escapeHtml(memorySigned(row.growthBytes))}</span>`;
  }
  const time = memoryGrowthTime(row);
  if (!time) return `<span class="memory-growth-pill ${statusClass}">${escapeHtml(mt(row.rssBytes == null ? 'unknown' : 'collecting'))}</span>`;
  return `<span class="memory-growth-pill ${statusClass}">${escapeHtml(mt('collecting'))}</span>
    <div class="memory-bar-track" aria-hidden="true"><div class="memory-bar-fill growth-progress-fill" style="width: ${time.percent}%"></div></div>
    <span class="memory-progress-caption">${escapeHtml(mt('collectingTime', {
      elapsed: memoryDuration(time.elapsed), total: memoryDuration(time.total), remaining: memoryDuration(time.remaining)
    }))}</span>`;
}

function memoryGroupGrowthCell(group) {
  if (group.growthBytes != null) {
    const growing = group.growing || group.growingCount > 0;
    const label = `${memorySigned(group.growthBytes)}${growing && group.growingCount > 1 ? ` · ${mt('growingCountShort', { count: group.growingCount })}` : ''}`;
    return `<span class="memory-growth-pill ${growing ? 'is-growing' : 'is-stable'}">${growing ? sfSymbol('chart.line.uptrend.xyaxis', 'mini-icon') : ''} ${escapeHtml(label)}</span>`;
  }
  if (group.allHistoryReady) {
    return `<span class="memory-growth-pill is-stable">${escapeHtml(mt('stable'))}</span>`;
  }
  const time = memoryGrowthTime(group);
  if (!time) return `<span class="memory-growth-pill is-collecting">${escapeHtml(mt('collecting'))}</span>`;
  return `<span class="memory-growth-pill is-collecting">${escapeHtml(mt('collecting'))}</span>
    <div class="memory-bar-track" aria-hidden="true"><div class="memory-bar-fill growth-progress-fill" style="width: ${time.percent}%"></div></div>
    <span class="memory-progress-caption">${escapeHtml(mt('collectingTimeAvg', {
      elapsed: memoryDuration(time.elapsed), total: memoryDuration(time.total), remaining: memoryDuration(time.remaining)
    }))}</span>`;
}

function memoryGroupMatches(group, search) {
  const haystack = `${group.name} ${group.bundleId} ${group.bundlePath}`.toLocaleLowerCase();
  if (haystack.includes(search)) return true;
  return (group.children || []).some(row =>
    `${row.name} ${row.pid} ${row.exe} ${mt(row.role)}`.toLocaleLowerCase().includes(search));
}

function memoryGroupVisibleChildren(group, search) {
  const children = group.children || [];
  if (!search) return children;
  const own = `${group.name} ${group.bundleId} ${group.bundlePath}`.toLocaleLowerCase().includes(search);
  if (own) return children;
  const matched = children.filter(row =>
    `${row.name} ${row.pid} ${row.exe} ${mt(row.role)}`.toLocaleLowerCase().includes(search));
  return matched.length ? matched : children;
}

function memoryVisibleGroups() {
  const search = document.getElementById('memory-search')?.value?.toLocaleLowerCase() || '';
  const filter = document.getElementById('memory-filter')?.value || 'all';
  const sort = document.getElementById('memory-sort')?.value || memoryState.sortField || 'memoryBytes';
  const asc = (memoryState.sortField === sort) ? Boolean(memoryState.sortAsc) : false;

  memoryState.searchMatched = new Set();
  const groups = (memoryState.snapshot?.groups || []).filter(group => {
    if (search) {
      const own = `${group.name} ${group.bundleId} ${group.bundlePath}`.toLocaleLowerCase().includes(search);
      if (!own) memoryState.searchMatched.add(group.id);
      if (!memoryGroupMatches(group, search)) return false;
    }
    if (filter === 'all') return true;
    if (filter === 'applications') return group.kind === 'application';
    if (filter === 'developer') return Boolean(group.developer);
    if (filter === 'growing') return Boolean(group.growing || group.growingCount);
    if (filter === 'high') return Boolean(group.highMemory);
    if (filter === 'protected') return (group.protectedCount || 0) > 0;
    return true;
  }).sort((a, b) => {
    let diff = 0;
    if (sort === 'name') diff = a.name.localeCompare(b.name);
    else if (sort === 'processCount') diff = (b.processCount || 0) - (a.processCount || 0);
    else diff = (b[sort] ?? -Infinity) - (a[sort] ?? -Infinity);
    return asc ? -diff : diff;
  });
  return groups;
}

function memoryGroupEligible(group) {
  return (group.children || []).filter(row => !row.protected);
}

function memorySelection() {
  const rows = memoryState.snapshot?.processes || [];
  // Keep the client selection within the server's exact-review limit.
  memoryState.selected = new Set([...memoryState.selected]
    .filter(key => rows.some(row => row.key === key && !row.protected))
    .slice(0, MAX_MEMORY_SELECTION));

  const selEl = document.getElementById('memory-selection');
  if (selEl) selEl.textContent = mt('selected', { count: memoryState.selected.size });

  const stopBtn = document.getElementById('memory-stop');
  if (stopBtn) stopBtn.disabled = memoryState.busy || !memoryState.selected.size;

  const forceBtn = document.getElementById('memory-force');
  if (forceBtn) forceBtn.disabled = memoryState.busy || !memoryState.selected.size || [...memoryState.selected].some(key => !rows.find(row => row.key === key)?.forceEligible);

  const selectAll = document.getElementById('memory-select-all');
  if (selectAll) {
    const visible = memoryVisibleGroups().flatMap(g => memoryGroupEligible(g));
    const selectedCount = visible.filter(r => memoryState.selected.has(r.key)).length;
    if (visible.length === 0) {
      selectAll.checked = false;
      selectAll.indeterminate = false;
      selectAll.disabled = true;
    } else {
      selectAll.disabled = false;
      selectAll.checked = selectedCount === visible.length;
      selectAll.indeterminate = selectedCount > 0 && selectedCount < visible.length;
    }
  }
}

function memorySigned(bytes) {
  return `${bytes < 0 ? '−' : '+'}${formatBytes(Math.abs(bytes))}`;
}

function addMemorySelection(rows) {
  const capacity = Math.max(0, MAX_MEMORY_SELECTION - memoryState.selected.size);
  rows.filter(row => !row.protected && !memoryState.selected.has(row.key)).slice(0, capacity)
    .forEach(row => memoryState.selected.add(row.key));
}

function memoryGroupSelect(group, checked) {
  const eligible = memoryGroupEligible(group);
  if (checked) addMemorySelection(eligible);
  else eligible.forEach(row => memoryState.selected.delete(row.key));
  memorySelection();
  renderMemory();
}

function memoryMetricTag(group) {
  if (group.memoryMetric === 'physical_footprint') return '';
  if (group.memoryMetric === 'rss') return `<span class="memory-metric-tag" title="${escapeHtml(mt('metricRss'))}">RSS</span>`;
  return '';
}

function renderMemory() {
  const data = memoryState.snapshot;
  if (!data) return;
  const e = escapeHtml;
  const metrics = data.metrics || {};
  const allRows = data.processes || [];
  const allGroups = data.groups || [];
  const growing = allRows.filter(row => row.growing).length;
  const protectedCount = allRows.filter(row => row.protected).length;

  const headroom = metrics.pressureHeadroom;
  let pressureState = 'normal';
  let pressureAlert = '';
  if (headroom != null) {
    if (headroom < 10) { pressureState = 'critical'; pressureAlert = mt('pressureCritical'); }
    else if (headroom < 20) { pressureState = 'elevated'; pressureAlert = mt('pressureElevated'); }
  }
  const ramPercent = metrics.total ? Math.min(100, Math.round(((metrics.used || 0) / metrics.total) * 100)) : 0;
  const swapVal = metrics.swap || 0;
  const swapPercent = metrics.total ? Math.min(100, Math.round((swapVal / metrics.total) * 100)) : 0;

  const metricsTarget = document.getElementById('memory-metrics');
  if (metricsTarget) {
    metricsTarget.innerHTML = `
      <div class="memory-metric metric-ram">
        <div class="memory-metric-line"><dt>${e(mt('ram'))}</dt><dd>${e(metrics.total ? `${formatBytes(metrics.used)} / ${formatBytes(metrics.total)}` : mt('unknown'))}</dd></div>
        <div class="memory-meter" aria-hidden="true"><div class="memory-meter-fill meter-primary" style="width: ${ramPercent}%"></div></div>
      </div>
      <div class="memory-metric metric-swap">
        <div class="memory-metric-line"><dt>${e(mt('swap'))}</dt><dd>${e(metrics.swap == null ? mt('unknown') : formatBytes(metrics.swap))}</dd></div>
        <div class="memory-meter" aria-hidden="true"><div class="memory-meter-fill meter-swap" style="width: ${swapPercent}%"></div></div>
      </div>
      <div class="memory-metric metric-pressure is-${pressureState}">
        <div class="memory-metric-line">
          <dt>${e(mt('pressure'))}${pressureAlert ? `<span class="memory-pressure-alert">${e(pressureAlert)}</span>` : ''}</dt>
          <dd>${e(headroom == null ? mt('unknown') : `${headroom}%`)}</dd>
        </div>
        <div class="memory-meter" aria-hidden="true"><div class="memory-meter-fill meter-${pressureState}" style="width: ${headroom == null ? 0 : Math.min(100, headroom)}%"></div></div>
      </div>
    `;
  }

  // Sync sort indicators on sortable table headers
  const currentSort = document.getElementById('memory-sort')?.value || memoryState.sortField;
  document.querySelectorAll('.memory-table th.sortable').forEach(th => {
    const field = th.dataset.sort;
    const isSorted = field === currentSort;
    th.classList.toggle('is-sorted', isSorted);
    th.classList.toggle('is-asc', isSorted && memoryState.sortAsc);
    th.classList.toggle('is-desc', isSorted && !memoryState.sortAsc);
    const indicator = th.querySelector('.sort-indicator');
    if (indicator) {
      indicator.innerHTML = isSorted ? sfSymbol(memoryState.sortAsc ? 'arrow.up' : 'arrow.down') : sfSymbol('arrow.up.arrow.down');
    }
  });

  const error = document.getElementById('memory-error');
  if (error) {
    error.hidden = !data.error;
    error.textContent = data.error || '';
  }

  memorySelection();

  const focused = document.activeElement;
  const focusKey = focused?.dataset?.key;
  const focusGroup = focused?.dataset?.group;
  const focusAction = focused?.dataset?.memoryAction;
  const focusRule = focused?.dataset?.ruleId;
  const focusExclusion = focused?.dataset?.exclusion;

  const search = document.getElementById('memory-search')?.value?.toLocaleLowerCase() || '';
  const groups = memoryVisibleGroups();
  const maxMem = groups.length ? Math.max(...groups.map(g => g.memoryBytes || 0), 1) : 1;

  const summary = document.getElementById('memory-summary');
  if (summary) {
    summary.textContent = mt('groupSummary', { visible: groups.length, total: allGroups.length, processes: allRows.length, protected: protectedCount });
  }

  const tableBody = document.getElementById('memory-processes');
  if (tableBody) {
    const parts = [];
    for (const group of groups) {
      const single = group.processCount === 1;
      const expanded = !single && (memoryState.expanded.has(group.id) || (search && memoryState.searchMatched.has(group.id)));
      const children = expanded ? memoryGroupVisibleChildren(group, search && memoryState.searchMatched.has(group.id) ? search : '') : [];
      const eligible = memoryGroupEligible(group);
      const eligibleSelected = eligible.filter(r => memoryState.selected.has(r.key)).length;
      const memPercent = group.memoryBytes ? Math.min(100, Math.max(4, Math.round((group.memoryBytes / maxMem) * 100))) : 0;
      const cpuVal = group.cpuPercent != null ? group.cpuPercent.toFixed(1) : null;
      const groupProtected = group.protectedCount === group.processCount;
      const groupGrowing = Boolean(group.growing || group.growingCount);
      const statusClass = groupProtected ? 'is-protected' : groupGrowing ? 'is-growing' : group.allHistoryReady ? 'is-stable' : 'is-collecting';
      const statusText = groupProtected ? mt('protectedAll') : groupGrowing ? mt(group.growingCount > 1 ? 'growingMulti' : 'growing', { count: group.growingCount }) : '';
      const subtitleBits = [mt('procCount', { count: group.processCount })];
      if (group.protectedCount && !groupProtected) subtitleBits.push(mt('protectedInline', { count: group.protectedCount }));
      const metricTitle = group.memoryMetric === 'physical_footprint' ? mt('metricFootprint') : mt('metricRss');

      if (single) {
        const row = group.children[0];
        const isChecked = memoryState.selected.has(row.key);
        // A footprint-measured group growth verdict is more accurate than the
        // child's RSS history (compressed pages stay invisible to RSS).
        const growthRow = group.growthMetric === 'physical_footprint' ? group : row;
        const childStatusClass = row.protected ? 'is-protected' : growthRow.growing ? 'is-growing' : growthRow.historyReady ? 'is-stable' : 'is-collecting';
        const childStatus = row.protected ? mt(row.protected) : growthRow.growing ? mt('growing') : '';
        const rssPercent = row.rssBytes ? Math.min(100, Math.max(4, Math.round((row.rssBytes / maxMem) * 100))) : 0;
        const cpuChild = row.cpuPercent != null ? row.cpuPercent.toFixed(1) : null;
        parts.push(`<tr class="${isChecked ? 'is-selected' : ''}" data-group-id="${e(group.id)}">
          <td class="memory-td-select">
            <input type="checkbox" data-memory-action="select" data-key="${e(row.key)}" aria-label="${e(`${mt('selection')} ${row.name} (${row.pid})`)}" ${row.protected ? 'disabled' : ''} ${isChecked ? 'checked' : ''}>
          </td>
          <td class="memory-td-name">
            <div class="memory-proc-info" title="${e(row.exe || row.name)}">
              <span class="memory-proc-icon">${memoryGroupIcon(group, categoryIcon(row))}</span>
              <div class="memory-proc-text">
                <strong class="memory-proc-title">${e(group.name !== row.name && group.kind === 'application' ? group.name : row.name)}</strong>
                <small class="memory-proc-role">${e(mt(row.role))}</small>
              </div>
            </div>
          </td>
          <td class="memory-pid"><span class="memory-pid-pill">${row.pid}</span></td>
          <td class="memory-number memory-rss-cell" title="${e(metricTitle)}">
            <div class="memory-cell-metric">
              <span class="memory-val">${e(group.memoryBytes == null ? mt('unknown') : formatBytes(group.memoryBytes))}</span>${memoryMetricTag(group)}
              <div class="memory-bar-track" aria-hidden="true"><div class="memory-bar-fill rss-fill" style="width: ${rssPercent}%"></div></div>
            </div>
          </td>
          <td class="memory-number ${growthRow.growing ? 'memory-growth-positive' : ''}">
            <div class="memory-cell-metric">${memoryGrowthCell(growthRow, childStatusClass)}</div>
          </td>
          <td class="memory-number memory-cpu-cell">
            <div class="memory-cell-metric">
              <span class="memory-val">${cpuChild == null ? e(mt('unknown')) : `${cpuChild}%`}</span>
              ${cpuChild != null ? `<div class="memory-bar-track" aria-hidden="true"><div class="memory-bar-fill cpu-fill" style="width: ${Math.min(100, Math.round(Number(cpuChild)))}%"></div></div>` : ''}
            </div>
          </td>
          <td>${childStatus ? `<span class="memory-status ${childStatusClass}"><span class="memory-status-dot" aria-hidden="true"></span><span class="memory-status-text">${e(childStatus)}</span></span>` : ''}</td>
          <td class="memory-td-actions">
            <div class="memory-row-actions">
              <button class="btn btn-secondary btn-icon-action" data-memory-action="details" data-key="${e(row.key)}" title="${e(mt('details'))}" aria-label="${e(mt('details'))}">
                ${sfSymbol('waveform.path.ecg')}<span>${e(mt('details'))}</span>
              </button>
              ${row.protected ? '' : `<button class="btn btn-secondary btn-icon-action" data-memory-action="exclude" data-key="${e(row.key)}" title="${e(mt('exclude'))}" aria-label="${e(mt('exclude'))}">
                ${sfSymbol('shield')}<span>${e(mt('exclude'))}</span>
              </button>`}
              ${row.helper ? `<button class="btn btn-secondary btn-icon-action" data-memory-action="rule" data-key="${e(row.key)}" title="${e(mt('addRule'))}" aria-label="${e(mt('addRule'))}">
                ${sfSymbol('slider.horizontal.3')}<span>${e(mt('addRule'))}</span>
              </button>` : ''}
            </div>
          </td>
        </tr>`);
        continue;
      }

      parts.push(`<tr class="memory-group-row" data-group-id="${e(group.id)}">
        <td class="memory-td-select">
          <input type="checkbox" data-memory-action="select-group" data-group="${e(group.id)}" aria-label="${e(mt('selectGroup'))}" ${eligible.length === 0 ? 'disabled' : ''} ${eligible.length && eligibleSelected === eligible.length ? 'checked' : ''} ${eligibleSelected > 0 && eligibleSelected < eligible.length ? 'data-indeterminate="1"' : ''}>
        </td>
        <td class="memory-td-name">
          <div class="memory-proc-info" title="${e(group.bundlePath || group.name)}">
            <button type="button" class="memory-disclosure" data-memory-action="toggle" data-group="${e(group.id)}" aria-expanded="${expanded}" aria-label="${e(mt(expanded ? 'collapseGroup' : 'expandGroup', { count: group.processCount }))}">
              ${sfSymbol('chevron.right')}
            </button>
            <span class="memory-proc-icon">${memoryGroupIcon(group)}</span>
            <div class="memory-proc-text">
              <strong class="memory-proc-title">${e(group.name)}</strong>
              <small class="memory-proc-role">${e(subtitleBits.join(' · '))}</small>
            </div>
          </div>
        </td>
        <td class="memory-pid"><span class="memory-pid-pill memory-count-pill">×${group.processCount}</span></td>
        <td class="memory-number memory-rss-cell" title="${e(metricTitle)}">
          <div class="memory-cell-metric">
            <span class="memory-val">${e(group.memoryBytes == null ? mt('unknown') : formatBytes(group.memoryBytes))}</span>${memoryMetricTag(group)}
            <div class="memory-bar-track" aria-hidden="true"><div class="memory-bar-fill rss-fill" style="width: ${memPercent}%"></div></div>
          </div>
        </td>
        <td class="memory-number ${groupGrowing ? 'memory-growth-positive' : ''}">
          <div class="memory-cell-metric">${memoryGroupGrowthCell(group)}</div>
        </td>
        <td class="memory-number memory-cpu-cell">
          <div class="memory-cell-metric">
            <span class="memory-val">${cpuVal == null ? e(mt('unknown')) : `${cpuVal}%`}</span>
            ${cpuVal != null ? `<div class="memory-bar-track" aria-hidden="true"><div class="memory-bar-fill cpu-fill" style="width: ${Math.min(100, Math.round(Number(cpuVal)))}%"></div></div>` : ''}
          </div>
        </td>
        <td>${statusText ? `<span class="memory-status ${statusClass}"><span class="memory-status-dot" aria-hidden="true"></span><span class="memory-status-text">${e(statusText)}</span></span>` : ''}</td>
        <td class="memory-td-actions">
          <div class="memory-row-actions">
            <button class="btn btn-secondary btn-icon-action" data-memory-action="group-details" data-group="${e(group.id)}" title="${e(mt('details'))}" aria-label="${e(mt('details'))}">
              ${sfSymbol('waveform.path.ecg')}<span>${e(mt('details'))}</span>
            </button>
          </div>
        </td>
      </tr>`);

      for (const row of children) {
        const isChecked = memoryState.selected.has(row.key);
        const rssPercent = row.rssBytes ? Math.min(100, Math.max(4, Math.round((row.rssBytes / maxMem) * 100))) : 0;
        const cpuChild = row.cpuPercent != null ? row.cpuPercent.toFixed(1) : null;
        const childStatusClass = row.protected ? 'is-protected' : row.growing ? 'is-growing' : row.historyReady ? 'is-stable' : 'is-collecting';
        const childStatus = row.protected ? mt(row.protected) : row.growing ? mt('growing') : '';
        parts.push(`<tr class="memory-child-row ${isChecked ? 'is-selected' : ''}" data-group-id="${e(group.id)}">
          <td class="memory-td-select">
            <input type="checkbox" data-memory-action="select" data-key="${e(row.key)}" aria-label="${e(`${mt('selection')} ${row.name} (${row.pid})`)}" ${row.protected ? 'disabled' : ''} ${isChecked ? 'checked' : ''}>
          </td>
          <td class="memory-td-name">
            <div class="memory-proc-info memory-child-info" title="${e(row.exe || row.name)}">
              <span class="memory-proc-icon">${memoryGroupIcon(group, categoryIcon(row))}</span>
              <div class="memory-proc-text">
                <span class="memory-proc-title memory-child-title">${e(row.name)}</span>
                <small class="memory-proc-role">${e(mt(row.role))}</small>
              </div>
            </div>
          </td>
          <td class="memory-pid"><span class="memory-pid-pill">${row.pid}</span></td>
          <td class="memory-number memory-rss-cell" title="${e(mt('rss'))}">
            <div class="memory-cell-metric">
              <span class="memory-val">${e(row.rssBytes == null ? mt('unknown') : formatBytes(row.rssBytes))}</span><span class="memory-metric-tag">RSS</span>
              <div class="memory-bar-track" aria-hidden="true"><div class="memory-bar-fill rss-fill" style="width: ${rssPercent}%"></div></div>
            </div>
          </td>
          <td class="memory-number ${row.growing ? 'memory-growth-positive' : ''}">
            <div class="memory-cell-metric">${memoryGrowthCell(row, childStatusClass)}</div>
          </td>
          <td class="memory-number memory-cpu-cell">
            <div class="memory-cell-metric">
              <span class="memory-val">${cpuChild == null ? e(mt('unknown')) : `${cpuChild}%`}</span>
              ${cpuChild != null ? `<div class="memory-bar-track" aria-hidden="true"><div class="memory-bar-fill cpu-fill" style="width: ${Math.min(100, Math.round(Number(cpuChild)))}%"></div></div>` : ''}
            </div>
          </td>
          <td>${childStatus ? `<span class="memory-status ${childStatusClass}"><span class="memory-status-dot" aria-hidden="true"></span><span class="memory-status-text">${e(childStatus)}</span></span>` : ''}</td>
          <td class="memory-td-actions">
            <div class="memory-row-actions">
              <button class="btn btn-secondary btn-icon-action" data-memory-action="details" data-key="${e(row.key)}" title="${e(mt('details'))}" aria-label="${e(mt('details'))}">
                ${sfSymbol('waveform.path.ecg')}<span>${e(mt('details'))}</span>
              </button>
              ${row.protected ? '' : `<button class="btn btn-secondary btn-icon-action" data-memory-action="exclude" data-key="${e(row.key)}" title="${e(mt('exclude'))}" aria-label="${e(mt('exclude'))}">
                ${sfSymbol('shield')}<span>${e(mt('exclude'))}</span>
              </button>`}
              ${row.helper ? `<button class="btn btn-secondary btn-icon-action" data-memory-action="rule" data-key="${e(row.key)}" title="${e(mt('addRule'))}" aria-label="${e(mt('addRule'))}">
                ${sfSymbol('slider.horizontal.3')}<span>${e(mt('addRule'))}</span>
              </button>` : ''}
            </div>
          </td>
        </tr>`);
      }
    }
    tableBody.innerHTML = parts.join('') || `<tr><td class="memory-empty" colspan="8">${sfSymbol(metrics.measuredAt ? 'magnifyingglass' : 'waveform.path.ecg')}<strong>${e(metrics.measuredAt ? mt('empty') : mt('loading'))}</strong></td></tr>`;
    tableBody.querySelectorAll('input[data-indeterminate]').forEach(box => { box.indeterminate = true; });
  }

  if (focusKey && focusAction) document.querySelector(`#memory-processes [data-key="${CSS.escape(focusKey)}"][data-memory-action="${focusAction}"]`)?.focus({ preventScroll: true });
  else if (focusGroup && focusAction) document.querySelector(`#memory-processes [data-group="${CSS.escape(focusGroup)}"][data-memory-action="${focusAction}"]`)?.focus({ preventScroll: true });

  const pause = document.getElementById('memory-pause');
  if (pause) {
    pause.textContent = mt(data.settings.paused ? 'resume' : 'pause');
    pause.disabled = memoryState.busy || Boolean(data.error);
  }

  // Modern Rules cards
  const rulesTarget = document.getElementById('memory-rules');
  if (rulesTarget) {
    rulesTarget.innerHTML = data.settings.rules.map(rule => `
      <div class="memory-rule memory-card-item">
        <div class="memory-card-main">
          <div class="memory-card-title-row">
            <span class="memory-helper-icon">${sfSymbol('slider.horizontal.3')}</span>
            <strong>${e(mt(rule.role))}</strong>
            <span class="memory-rule-status ${rule.enabled ? 'is-enabled' : 'is-disabled'}">${e(mt(rule.enabled ? 'enabled' : 'disabled'))}</span>
          </div>
          <code class="memory-card-path" title="${e(rule.exe)}">${e(rule.exe)}</code>
          <div class="memory-rule-chips">
            <span class="memory-chip">${sfSymbol('memorychip')} > ${e(formatBytes(rule.rssBytes))}</span>
            <span class="memory-chip">${sfSymbol('clock')} > ${e(String(rule.durationSeconds / 60))}m</span>
            <span class="memory-chip">${sfSymbol('waveform.path.ecg')} ${e(mt('ruleHeadroom', { pressure: rule.pressureBelow }))}</span>
          </div>
        </div>
        <div class="memory-card-action">
          <button class="btn btn-secondary btn-sm" data-rule-id="${e(rule.id)}" aria-label="${e(mt('remove'))}">${sfSymbol('trash')}<span>${e(mt('remove'))}</span></button>
        </div>
      </div>
    `).join('') || `<p class="memory-note">${e(mt('noRules'))}</p>`;
  }

  // Modern Exclusions tags
  const exclusionsTarget = document.getElementById('memory-exclusions');
  if (exclusionsTarget) {
    exclusionsTarget.innerHTML = data.settings.exclusions.map(exe => `
      <div class="memory-exclusion memory-card-item">
        <div class="memory-card-main">
          <div class="memory-exclusion-row">
            <span class="memory-exclusion-icon">${sfSymbol('shield')}</span>
            <code class="memory-card-path" title="${e(exe)}">${e(exe)}</code>
          </div>
        </div>
        <div class="memory-card-action">
          <button class="btn btn-secondary btn-sm" data-exclusion="${e(exe)}" aria-label="${e(mt('remove'))}">${sfSymbol('trash')}<span>${e(mt('remove'))}</span></button>
        </div>
      </div>
    `).join('') || `<p class="memory-note">${e(mt('noExclusions'))}</p>`;
  }

  if (focusRule) (document.querySelector(`#memory-rules [data-rule-id="${CSS.escape(focusRule)}"]`) || pause)?.focus({ preventScroll: true });
  if (focusExclusion) (document.querySelector(`#memory-exclusions [data-exclusion="${CSS.escape(focusExclusion)}"]`) || pause)?.focus({ preventScroll: true });

  // Modern Events timeline
  const eventsTarget = document.getElementById('memory-events');
  if (eventsTarget) {
    eventsTarget.innerHTML = data.events.slice(0, 30).map(event => {
      const outcomeClass = event.outcome === 'exited' ? 'outcome-success' : event.outcome === 'still-running' ? 'outcome-warning' : 'outcome-neutral';
      return `
      <div class="memory-event memory-timeline-row">
        <time class="memory-event-time">${e(new Date(event.time * 1000).toLocaleTimeString())}</time>
        <div class="memory-event-info">
          <span class="memory-event-name">${e(event.name || event.key)}</span>
          <span class="memory-event-mode">${sfSymbol(event.automatic ? 'bolt' : 'checkmark', 'mini-icon')} ${e(mt(event.automatic ? 'automatic' : 'manual'))}</span>
        </div>
        <span class="memory-event-outcome ${outcomeClass}">${e(mt(event.outcome))}</span>
        ${event.detail ? `<span class="memory-event-detail">${e(event.detail)}</span>` : ''}
      </div>`;
    }).join('') || `<p class="memory-note">${e(mt('noActivity'))}</p>`;
  }
}

async function memoryAPI(path, body) {
  const response = await fetch(path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  return readAPIResponse(response);
}

function memoryError(error) {
  const target = document.getElementById('memory-error');
  if (target) {
    target.hidden = false;
    target.textContent = error.message;
  }
}

async function refreshMemory() {
  if (memoryState.loading || memoryState.busy || state.activeTab !== 'memory') return;
  memoryState.loading = true;
  try {
    memoryState.snapshot = await memoryAPI('/api/memory');
    renderMemory();
    if (memoryState.detailKey) await showMemoryDetails(memoryState.detailKey, false);
    else if (memoryState.detailGroup) showMemoryGroupDetails(memoryState.detailGroup, false);
  } catch (error) {
    memoryError(error);
  } finally {
    memoryState.loading = false;
  }
}

async function memoryConfigure(body) {
  if (memoryState.busy) return;
  memoryState.busy = true;
  memorySelection();
  try {
    await memoryAPI('/api/memory/settings', body);
  } catch (error) {
    memoryError(error);
    showToast(error.message, 'error');
  } finally {
    memoryState.busy = false;
    await refreshMemory();
  }
}

async function reviewMemoryStop(force) {
  if (memoryState.busy) return;
  const keys = [...memoryState.selected];
  const endpoint = force ? '/api/memory/force-stop' : '/api/memory/stop';
  memoryState.busy = true;
  memorySelection();
  try {
    const review = await requestOperationReview(endpoint, { keys });
    showModal(mt(force ? 'force' : 'stop'), `<p>${escapeHtml(mt(force ? 'forceImpact' : 'impact'))}</p><ul>${review.review.items.map(item => `<li><strong>${escapeHtml(item.label)}</strong><p>${escapeHtml(item.target)}</p></li>`).join('')}</ul><label class="memory-consent"><input id="memory-stop-consent" type="checkbox"> ${escapeHtml(mt('consent'))}</label>`, [
      { text: mt('cancel'), onClick: () => { hideModal(); } },
      { text: mt(force ? 'confirmForce' : 'confirm'), class: 'btn-danger', onClick: async () => {
        if (!document.getElementById('memory-stop-consent').checked) { showToast(mt('needConsent'), 'warning'); return; }
        if (memoryState.busy) return;
        memoryState.busy = true;
        memorySelection();
        hideModal();
        const outcomeEl = document.getElementById('memory-outcome');
        if (outcomeEl) outcomeEl.textContent = mt('stopping');
        try {
          const result = await memoryAPI(endpoint, { keys, reviewToken: review.reviewToken, extraOptIn: true });
          if (outcomeEl) {
            outcomeEl.textContent = result.outcomes.map(item => `${item.name || item.key}: ${mt(item.outcome)}${item.detail ? ` (${item.detail})` : ''}`).join(' · ') + '\n' + mt('observed', { delta: memorySigned(result.observedAvailableDelta) });
          }
          for (const item of result.outcomes) {
            if (item.outcome === 'exited') memoryState.selected.delete(item.key);
          }
        } catch (error) {
          memoryError(error);
          if (outcomeEl) outcomeEl.textContent = error.message;
        } finally {
          memoryState.busy = false;
          await refreshMemory();
        }
      }}
    ]);
  } catch (error) {
    memoryError(error);
  } finally {
    memoryState.busy = false;
    memorySelection();
  }
}

function showMemoryRule(key) {
  const row = memoryState.snapshot?.processes?.find(item => item.key === key);
  if (!row?.helper) return;
  const rule = memoryState.snapshot.settings.rules.find(item => item.exe === row.exe && item.role === row.role && item.entrypoint === row.entrypoint);
  showModal(mt('addRule'), `<p>${escapeHtml(row.name)} · ${escapeHtml(row.exe)}</p><p>${escapeHtml(mt('ruleImpact'))}</p><form class="memory-rule-form" id="memory-rule-form"><label>${escapeHtml(mt('threshold'))}<input name="rss" type="number" min="0.0625" max="1024" step="any" value="${(rule?.rssBytes || 2 * 1024**3) / 1024**3}" required></label><label>${escapeHtml(mt('duration'))}<input name="duration" type="number" min="0.5" max="60" step="any" value="${(rule?.durationSeconds || 300) / 60}" required></label><label>${escapeHtml(mt('headroom'))}<input name="pressure" type="number" min="1" max="50" step="any" value="${rule?.pressureBelow || 15}" required></label><label class="memory-consent"><input name="consent" type="checkbox" required>${escapeHtml(mt('consent'))}</label></form>`, [
    { text: mt('cancel'), onClick: hideModal },
    { text: mt('save'), class: 'btn-primary', onClick: async () => {
      const form = document.getElementById('memory-rule-form');
      if (!form.reportValidity()) return;
      const values = new FormData(form);
      hideModal();
      await memoryConfigure({
        operation: 'rule',
        key,
        consent: true,
        rssBytes: Number(values.get('rss')) * 1024**3,
        durationSeconds: Number(values.get('duration')) * 60,
        pressureBelow: Number(values.get('pressure'))
      });
    }}
  ]);
}

function showMemoryGroupDetails(groupId, scroll = true) {
  const group = memoryState.snapshot?.groups?.find(item => item.id === groupId);
  memoryState.detailKey = null;
  memoryState.detailGroup = group ? groupId : null;
  const target = document.getElementById('memory-details');
  if (!group) {
    if (target) target.hidden = true;
    return;
  }
  memoryState.detailData = { group };
  renderMemoryGroupDetails(group, scroll);
}

function renderMemoryGroupDetails(group, scroll = false) {
  const e = escapeHtml;
  const target = document.getElementById('memory-details');
  if (!target) return;
  target.hidden = false;
  const metricLabel = group.memoryMetric === 'physical_footprint' ? mt('metricFootprint') : mt('metricRss');
  const children = group.children || [];
  target.innerHTML = `
    <div class="memory-details-header">
      <div class="memory-details-title-wrap">
        <span class="memory-details-icon">${memoryGroupIcon(group)}</span>
        <div>
          <h2>${e(group.name)} <span class="memory-pid-pill memory-count-pill">${e(mt('procCount', { count: group.processCount }))}</span></h2>
          <div class="memory-details-path-row">
            <code class="memory-details-path" title="${e(group.bundlePath || group.id)}">${e(group.bundleId || group.bundlePath || group.id)}</code>
            ${group.bundlePath ? `<button type="button" class="btn-icon-xs memory-copy-path-btn" data-copy-path="${e(group.bundlePath)}" title="${e(mt('copyPath'))}">${sfSymbol('doc.on.doc')}</button>` : ''}
          </div>
        </div>
      </div>
      <div class="memory-details-header-actions">
        <button type="button" class="btn-icon memory-details-close" id="memory-details-close" title="${e(mt('close'))}" aria-label="${e(mt('close'))}">
          ${sfSymbol('xmark')}
        </button>
      </div>
    </div>

    <div class="memory-details-stats">
      <div class="memory-details-stat">
        <dt>${e(mt('groupMemory'))}</dt>
        <dd>${e(group.memoryBytes == null ? mt('unknown') : formatBytes(group.memoryBytes))}${group.memoryPartial ? ` <span class="memory-metric-tag">${e(mt('partialCoverage'))}</span>` : ''}</dd>
        <dd class="memory-stat-note">${e(metricLabel)}</dd>
      </div>
      <div class="memory-details-stat">
        <dt>${e(mt('rssTotal'))}</dt>
        <dd>${e(group.rssBytes == null ? mt('unknown') : formatBytes(group.rssBytes))}</dd>
        <dd class="memory-stat-note">${e(mt('rssTotalNote'))}</dd>
      </div>
      <div class="memory-details-stat">
        <dt>${e(mt('growth'))}</dt>
        <dd class="${group.growing || group.growingCount ? 'memory-growth-positive' : ''}">${e(group.growthBytes != null ? memorySigned(group.growthBytes) : mt(group.allHistoryReady ? 'stable' : 'collecting'))}</dd>
      </div>
      <div class="memory-details-stat">
        <dt>${e(mt('cpu'))}</dt>
        <dd>${group.cpuPercent == null ? e(mt('unknown')) : `${group.cpuPercent.toFixed(1)}%`}</dd>
      </div>
      <div class="memory-details-stat">
        <dt>${e(mt('eligibility'))}</dt>
        <dd>${e(mt('groupEligible', { eligible: group.eligibleCount, total: group.processCount }))}</dd>
      </div>
    </div>

    <div class="memory-details-members">
      <h3>${e(mt('processes'))}</h3>
      <ul class="memory-member-list">
        ${children.map(row => `<li>
          <span class="memory-member-name">${e(row.name)}</span>
          <span class="memory-pid-pill">${row.pid}</span>
          <span class="memory-member-rss">${e(row.rssBytes == null ? mt('unknown') : formatBytes(row.rssBytes))} RSS</span>
          ${row.protected ? `<span class="memory-status is-protected"><span class="memory-status-dot" aria-hidden="true"></span><span class="memory-status-text">${e(mt(row.protected))}</span></span>` : ''}
        </li>`).join('')}
      </ul>
    </div>
  `;
  if (scroll) target.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

async function showMemoryDetails(key, scroll = true) {
  memoryState.detailKey = key;
  memoryState.detailGroup = null;
  const request = ++memoryState.detailRequest;
  try {
    const row = memoryState.snapshot?.processes?.find(item => item.key === key);
    if (!row) {
      const target = document.getElementById('memory-details');
      if (target) target.hidden = true;
      memoryState.detailKey = null;
      memoryState.detailData = null;
      return;
    }
    const result = await memoryAPI(`/api/memory/history?key=${encodeURIComponent(key)}`);
    if (request !== memoryState.detailRequest || state.activeTab !== 'memory') return;
    memoryState.detailData = { row, result };
    renderMemoryDetails(row, result, scroll);
  } catch (error) {
    memoryError(error);
  }
}

function renderMemoryDetails(row, result, scroll = false) {
  const e = escapeHtml;
  const samples = result.samples || [];
  const low = samples.length ? Math.min(...samples.map(s => s.rssBytes)) : 0;
  const high = samples.length ? Math.max(...samples.map(s => s.rssBytes)) : 0;
  const age = samples[0]?.secondsAgo || 1;

  const W = 1000, H = 160;
  const padTop = 15, padBottom = 20, padLeft = 20, padRight = 20;
  const chartW = W - padLeft - padRight;
  const chartH = H - padTop - padBottom;
  const points = samples.map(s => {
    const x = padLeft + (age - s.secondsAgo) / age * chartW;
    const y = padTop + chartH - (s.rssBytes - low) / (high - low || 1) * chartH;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');

  const firstX = padLeft.toFixed(1);
  const lastX = (padLeft + chartW).toFixed(1);
  const bottomY = (padTop + chartH).toFixed(1);
  const areaPoints = points ? `${firstX},${bottomY} ${points} ${lastX},${bottomY}` : '';

  const target = document.getElementById('memory-details');
  if (!target) return;
  target.hidden = false;

  const iconName = categoryIcon(row);
  const statusClass = row.protected ? 'is-protected' : row.growing ? 'is-growing' : row.historyReady ? 'is-stable' : 'is-collecting';
  const statusIcon = row.protected ? 'shield' : row.growing ? 'chart.line.uptrend.xyaxis' : row.historyReady ? 'checkmark' : 'clock';
  const statusText = row.protected ? mt(row.protected) : row.growing ? mt('growing') : row.historyReady ? mt('stable') : mt('collecting');

  target.innerHTML = `
    <div class="memory-details-header">
      <div class="memory-details-title-wrap">
        <span class="memory-details-icon">${sfSymbol(iconName)}</span>
        <div>
          <h2>${e(row.name)} <span class="memory-pid-pill">PID ${row.pid}</span></h2>
          <div class="memory-details-path-row">
            <code class="memory-details-path" title="${e(row.exe)}">${e(row.exe || '—')}</code>
            ${row.exe ? `<button type="button" class="btn-icon-xs memory-copy-path-btn" data-copy-path="${e(row.exe)}" title="${e(mt('copyPath'))}">${sfSymbol('doc.on.doc')}</button>` : ''}
          </div>
        </div>
      </div>
      <div class="memory-details-header-actions">
        <span class="memory-status ${statusClass}">
          <span class="memory-status-dot" aria-hidden="true"></span>
          <span>${e(statusText)}</span>
        </span>
        <button type="button" class="btn-icon memory-details-close" id="memory-details-close" title="${e(mt('close'))}" aria-label="${e(mt('close'))}">
          ${sfSymbol('xmark')}
        </button>
      </div>
    </div>

    <div class="memory-details-stats">
      <div class="memory-details-stat">
        <dt>${e(mt('currentRss'))}</dt>
        <dd>${e(row.rssBytes == null ? mt('unknown') : formatBytes(row.rssBytes))}</dd>
      </div>
      ${row.footprintBytes != null ? `<div class="memory-details-stat">
        <dt>${e(mt('groupMemory'))}</dt>
        <dd>${e(formatBytes(row.footprintBytes))}</dd>
        <dd class="memory-stat-note">${e(mt('metricFootprint'))}</dd>
      </div>` : ''}
      <div class="memory-details-stat">
        <dt>${e(mt('peak'))}</dt>
        <dd>${e(formatBytes(high))}</dd>
      </div>
      <div class="memory-details-stat">
        <dt>${e(mt('growth'))}</dt>
        <dd class="${row.growing ? 'memory-growth-positive' : ''}">${e(memoryGrowthLabel(row))}</dd>
      </div>
      <div class="memory-details-stat">
        <dt>${e(mt('cpu'))}</dt>
        <dd>${row.cpuPercent == null ? e(mt('unknown')) : `${row.cpuPercent.toFixed(1)}%`}</dd>
      </div>
      <div class="memory-details-stat">
        <dt>${e(mt('roleLabel'))}</dt>
        <dd><span class="memory-role-tag">${e(mt(row.role))}</span></dd>
      </div>
    </div>

    <figure class="memory-trend-figure">
      <figcaption>${e(mt('trend'))}</figcaption>
      <svg class="memory-trend" viewBox="0 0 1000 160" preserveAspectRatio="none" role="img" aria-label="${e(mt('trendRange', { old: Math.round(age), low: formatBytes(low), high: formatBytes(high) }))}">
        <defs>
          <linearGradient id="memory-chart-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="var(--primary)" stop-opacity="0.32" />
            <stop offset="100%" stop-color="var(--primary)" stop-opacity="0.02" />
          </linearGradient>
        </defs>
        <line x1="${padLeft}" y1="${padTop}" x2="${padLeft + chartW}" y2="${padTop + chartW}" stroke="currentColor" stroke-opacity="0.08" stroke-dasharray="4 4" vector-effect="non-scaling-stroke" />
        <line x1="${padLeft}" y1="${(padTop + chartH / 2).toFixed(1)}" x2="${padLeft + chartW}" y2="${(padTop + chartH / 2).toFixed(1)}" stroke="currentColor" stroke-opacity="0.08" stroke-dasharray="4 4" vector-effect="non-scaling-stroke" />
        <line x1="${padLeft}" y1="${bottomY}" x2="${padLeft + chartW}" y2="${bottomY}" stroke="currentColor" stroke-opacity="0.12" vector-effect="non-scaling-stroke" />
        ${areaPoints ? `<polygon points="${areaPoints}" fill="url(#memory-chart-grad)" />` : ''}
        <polyline points="${points}" fill="none" stroke="currentColor" stroke-width="2.5" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <p class="memory-note">${e(mt('trendRange', { old: Math.round(age), low: formatBytes(low), high: formatBytes(high) }))}</p>
    </figure>

    <div class="memory-details-actions">
      ${row.protected ? '' : `<button type="button" class="btn btn-secondary btn-sm" data-memory-action="detail-exclude" data-key="${e(row.key)}">${sfSymbol('shield')}<span>${e(mt('exclude'))}</span></button>`}
      ${row.helper ? `<button type="button" class="btn btn-secondary btn-sm" data-memory-action="detail-rule" data-key="${e(row.key)}">${sfSymbol('slider.horizontal.3')}<span>${e(mt('addRule'))}</span></button>` : ''}
    </div>
  `;

  if (scroll) target.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

document.addEventListener('macmaid-language-change', () => {
  if (!memoryState.snapshot) return;
  renderMemory();
  if (memoryState.detailData) {
    if (memoryState.detailGroup) {
      const group = memoryState.snapshot.groups?.find(item => item.id === memoryState.detailGroup);
      if (group) renderMemoryGroupDetails(group);
    } else if (memoryState.detailData.row) {
      renderMemoryDetails(memoryState.detailData.row, memoryState.detailData.result || { samples: [] });
    }
  }
});

document.addEventListener('DOMContentLoaded', () => {
  // Failed/missing bundle icons reveal the existing SF Symbol. Capture phase
  // handles image errors without inline handlers or listeners per process row.
  document.addEventListener('error', event => {
    if (event.target instanceof HTMLImageElement && event.target.classList.contains('memory-app-icon')) {
      event.target.remove();
    }
  }, true);
  document.querySelector('[data-tab="memory"]')?.addEventListener('click', refreshMemory);

  document.getElementById('memory-refresh-btn')?.addEventListener('click', async () => {
    const btn = document.getElementById('memory-refresh-btn');
    btn?.classList.add('is-refreshing');
    await refreshMemory();
    setTimeout(() => btn?.classList.remove('is-refreshing'), 600);
  });

  ['memory-search', 'memory-filter'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', renderMemory);
  });
  document.getElementById('memory-sort')?.addEventListener('input', event => {
    const field = event.target.value;
    if (memoryState.sortField !== field) {
      memoryState.sortField = field;
      memoryState.sortAsc = (field === 'name');
    }
    renderMemory();
  });

  // Sortable header click handling
  document.querySelectorAll('.memory-table th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const field = th.dataset.sort;
      if (!field) return;
      if (memoryState.sortField === field) {
        memoryState.sortAsc = !memoryState.sortAsc;
      } else {
        memoryState.sortField = field;
        memoryState.sortAsc = (field === 'name');
      }
      const sortSelect = document.getElementById('memory-sort');
      if (sortSelect) sortSelect.value = field;
      renderMemory();
    });
  });

  // Master selection checkbox
  document.getElementById('memory-select-all')?.addEventListener('change', event => {
    const checked = event.target.checked;
    const visibleEligible = memoryVisibleGroups().flatMap(g => memoryGroupEligible(g));
    if (checked) {
      addMemorySelection(visibleEligible);
    } else {
      visibleEligible.forEach(r => memoryState.selected.delete(r.key));
    }
    memorySelection();
    renderMemory();
  });

  document.getElementById('memory-select')?.addEventListener('click', () => {
    addMemorySelection(memoryVisibleGroups().flatMap(g => memoryGroupEligible(g)));
    renderMemory();
  });

  document.getElementById('memory-clear')?.addEventListener('click', () => {
    memoryState.selected.clear();
    renderMemory();
  });

  document.getElementById('memory-stop')?.addEventListener('click', () => reviewMemoryStop(false));
  document.getElementById('memory-force')?.addEventListener('click', () => reviewMemoryStop(true));
  document.getElementById('memory-pause')?.addEventListener('click', () => memoryConfigure({ operation: 'pause', paused: !memoryState.snapshot.settings.paused }));

  document.getElementById('memory-processes')?.addEventListener('click', event => {
    const control = event.target.closest('[data-memory-action]');
    if (!control) return;
    const key = control.dataset.key;
    const groupId = control.dataset.group;
    const action = control.dataset.memoryAction;
    if (action === 'select') {
      if (control.checked) memoryState.selected.add(key);
      else memoryState.selected.delete(key);
      memorySelection();
      const tr = control.closest('tr');
      if (tr) tr.classList.toggle('is-selected', control.checked);
      return;
    }
    if (action === 'select-group') {
      const group = memoryState.snapshot?.groups?.find(item => item.id === groupId);
      if (group) memoryGroupSelect(group, control.checked);
      return;
    }
    if (action === 'toggle') {
      if (memoryState.expanded.has(groupId)) memoryState.expanded.delete(groupId);
      else memoryState.expanded.add(groupId);
      renderMemory();
      return;
    }
    if (action === 'group-details') { showMemoryGroupDetails(groupId); return; }
    if (action === 'details') showMemoryDetails(key);
    if (action === 'exclude') memoryConfigure({ operation: 'exclude', key });
    if (action === 'rule') showMemoryRule(key);
  });

  // Details panel interactions (close, copy path, actions)
  document.getElementById('memory-details')?.addEventListener('click', event => {
    if (event.target.closest('#memory-details-close')) {
      const target = document.getElementById('memory-details');
      if (target) target.hidden = true;
      memoryState.detailKey = null;
      memoryState.detailGroup = null;
      memoryState.detailData = null;
      return;
    }
    const copyBtn = event.target.closest('[data-copy-path]');
    if (copyBtn) {
      const path = copyBtn.dataset.copyPath;
      if (path && navigator.clipboard) {
        navigator.clipboard.writeText(path).then(() => {
          showToast(mt('copied'), 'info');
        }).catch(() => {});
      }
      return;
    }
    const actionBtn = event.target.closest('[data-memory-action]');
    if (actionBtn) {
      const key = actionBtn.dataset.key;
      if (actionBtn.dataset.memoryAction === 'detail-exclude' || actionBtn.dataset.memoryAction === 'exclude') memoryConfigure({ operation: 'exclude', key });
      if (actionBtn.dataset.memoryAction === 'detail-rule' || actionBtn.dataset.memoryAction === 'rule') showMemoryRule(key);
    }
  });

  document.getElementById('memory-rules')?.addEventListener('click', event => {
    const button = event.target.closest('[data-rule-id]');
    if (button) memoryConfigure({ operation: 'delete-rule', id: button.dataset.ruleId });
  });

  document.getElementById('memory-exclusions')?.addEventListener('click', event => {
    const button = event.target.closest('[data-exclusion]');
    if (button) memoryConfigure({ operation: 'unexclude', exe: button.dataset.exclusion });
  });

  setInterval(refreshMemory, 5000);
});
