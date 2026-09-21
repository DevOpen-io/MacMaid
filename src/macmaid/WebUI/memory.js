/* Memory workspace. Process selection is always keyed by PID + creation time. */
const MAX_MEMORY_SELECTION = 100;

const memoryState = {
  snapshot: null,
  selected: new Set(),
  busy: false,
  loading: false,
  detailKey: null,
  detailData: null,
  detailRequest: 0,
  sortField: 'rssBytes',
  sortAsc: false
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

function memoryVisibleRows() {
  const search = document.getElementById('memory-search')?.value?.toLocaleLowerCase() || '';
  const filter = document.getElementById('memory-filter')?.value || 'all';
  const sort = document.getElementById('memory-sort')?.value || memoryState.sortField || 'rssBytes';
  const asc = (memoryState.sortField === sort) ? Boolean(memoryState.sortAsc) : false;

  return (memoryState.snapshot?.processes || []).filter(row => {
    const text = `${row.name} ${row.pid} ${row.exe} ${mt(row.role)}`.toLocaleLowerCase();
    if (!text.includes(search)) return false;
    if (filter === 'all') return true;
    if (filter === 'growing') return Boolean(row.growing);
    if (filter === 'developer') return row.category === 'developer' || row.category === 'flutter';
    if (filter === 'flutter') return row.category === 'flutter';
    if (filter === 'protected') return Boolean(row.protected);
    return row.category === filter;
  }).sort((a, b) => {
    let diff = 0;
    if (sort === 'name') diff = a.name.localeCompare(b.name);
    else if (sort === 'pid') diff = (a.pid || 0) - (b.pid || 0);
    else diff = (b[sort] ?? -Infinity) - (a[sort] ?? -Infinity);
    return asc ? -diff : diff;
  });
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
    const visible = memoryVisibleRows().filter(r => !r.protected);
    const selectedCount = visible.filter(r => memoryState.selected.has(r.key)).length;
    if (visible.length === 0) {
      selectAll.checked = false;
      selectAll.indeterminate = false;
      selectAll.disabled = true;
    } else {
      selectAll.disabled = false;
      if (selectedCount === visible.length) {
        selectAll.checked = true;
        selectAll.indeterminate = false;
      } else if (selectedCount > 0) {
        selectAll.checked = false;
        selectAll.indeterminate = true;
      } else {
        selectAll.checked = false;
        selectAll.indeterminate = false;
      }
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

function renderMemory() {
  const data = memoryState.snapshot;
  if (!data) return;
  const e = escapeHtml;
  const metrics = data.metrics || {};
  const allRows = data.processes || [];
  const growing = allRows.filter(row => row.growing).length;
  const protectedCount = allRows.filter(row => row.protected).length;

  // Overview metrics with modern glass cards and visual meters
  const headroom = metrics.pressureHeadroom;
  let pressureState = 'normal';
  let pressureLabel = mt('pressureNormal');
  if (headroom != null) {
    if (headroom < 10) { pressureState = 'critical'; pressureLabel = mt('pressureCritical'); }
    else if (headroom < 20) { pressureState = 'elevated'; pressureLabel = mt('pressureElevated'); }
  }
  const ramPercent = metrics.total ? Math.min(100, Math.round(((metrics.used || 0) / metrics.total) * 100)) : 0;
  const swapVal = metrics.swap || 0;
  const swapPercent = metrics.total ? Math.min(100, Math.round((swapVal / metrics.total) * 100)) : 0;

  const metricsTarget = document.getElementById('memory-metrics');
  if (metricsTarget) {
    metricsTarget.innerHTML = `
      <div class="memory-metric metric-pressure is-${pressureState}">
        <div class="memory-metric-head">
          <span class="memory-metric-icon">${sfSymbol('waveform.path.ecg')}</span>
          <span class="memory-metric-badge is-${pressureState}">${e(pressureLabel)}</span>
        </div>
        <div class="memory-metric-body">
          <dt>${e(mt('pressure'))}</dt>
          <dd>${e(headroom == null ? mt('unknown') : `${headroom}%`)}</dd>
          <div class="memory-meter" aria-hidden="true">
            <div class="memory-meter-fill meter-${pressureState}" style="width: ${headroom == null ? 0 : Math.min(100, headroom)}%"></div>
          </div>
          <small>${e(growing ? mt('growingCount', {count: growing}) : mt('stable'))}</small>
        </div>
      </div>
      <div class="memory-metric metric-ram">
        <div class="memory-metric-head">
          <span class="memory-metric-icon">${sfSymbol('memorychip')}</span>
          <span class="memory-metric-badge">${ramPercent}%</span>
        </div>
        <div class="memory-metric-body">
          <dt>${e(mt('ram'))}</dt>
          <dd>${e(metrics.total ? `${formatBytes(metrics.used)} / ${formatBytes(metrics.total)}` : mt('unknown'))}</dd>
          <div class="memory-meter" aria-hidden="true">
            <div class="memory-meter-fill meter-primary" style="width: ${ramPercent}%"></div>
          </div>
          <small>${e(mt('rss'))}</small>
        </div>
      </div>
      <div class="memory-metric metric-swap">
        <div class="memory-metric-head">
          <span class="memory-metric-icon">${sfSymbol('cylinder')}</span>
        </div>
        <div class="memory-metric-body">
          <dt>${e(mt('swap'))}</dt>
          <dd>${e(metrics.swap == null ? mt('unknown') : formatBytes(metrics.swap))}</dd>
          <div class="memory-meter" aria-hidden="true">
            <div class="memory-meter-fill meter-swap" style="width: ${swapPercent}%"></div>
          </div>
          <small>${e(mt('systemWide'))}</small>
        </div>
      </div>
      <div class="memory-metric metric-processes">
        <div class="memory-metric-head">
          <span class="memory-metric-icon">${sfSymbol('cpu')}</span>
          ${growing ? `<span class="memory-metric-badge is-alert">${sfSymbol('chart.line.uptrend.xyaxis')} ${growing}</span>` : ''}
        </div>
        <div class="memory-metric-body">
          <dt>${e(mt('processCount'))}</dt>
          <dd>${e(String(allRows.length))}</dd>
          <div class="memory-meter" aria-hidden="true">
            <div class="memory-meter-fill meter-proc" style="width: ${allRows.length ? Math.min(100, Math.round((protectedCount / allRows.length) * 100)) : 0}%"></div>
          </div>
          <small>${e(mt('protectedCount', {count: protectedCount}))}</small>
        </div>
      </div>
    `;
  }

  // Update filter pill counts and active state
  const activeFilter = document.getElementById('memory-filter')?.value || 'all';
  document.querySelectorAll('.memory-filter-pills .memory-pill').forEach(pill => {
    const pillKey = pill.dataset.pill;
    const isAct = pillKey === activeFilter;
    pill.classList.toggle('active', isAct);
    pill.setAttribute('aria-selected', isAct ? 'true' : 'false');
  });
  const cAll = document.getElementById('pill-count-all');
  if (cAll) cAll.textContent = String(allRows.length);
  const cGrow = document.getElementById('pill-count-growing');
  if (cGrow) {
    cGrow.textContent = String(growing);
    cGrow.parentElement?.classList.toggle('has-alert', growing > 0);
  }
  const cDev = document.getElementById('pill-count-developer');
  if (cDev) cDev.textContent = String(allRows.filter(r => r.category === 'developer' || r.category === 'flutter').length);
  const cFlutter = document.getElementById('pill-count-flutter');
  if (cFlutter) cFlutter.textContent = String(allRows.filter(r => r.category === 'flutter').length);
  const cProt = document.getElementById('pill-count-protected');
  if (cProt) cProt.textContent = String(protectedCount);

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
  const focusAction = focused?.dataset?.memoryAction;
  const focusRule = focused?.dataset?.ruleId;
  const focusExclusion = focused?.dataset?.exclusion;

  const rows = memoryVisibleRows();
  const maxRss = rows.length ? Math.max(...rows.map(r => r.rssBytes || 0), 1) : 1;

  const summary = document.getElementById('memory-summary');
  if (summary) {
    summary.textContent = mt('processSummary', { visible: rows.length, total: allRows.length, protected: protectedCount });
  }

  const tableBody = document.getElementById('memory-processes');
  if (tableBody) {
    tableBody.innerHTML = rows.map(row => {
      const isChecked = memoryState.selected.has(row.key);
      const rssPercent = row.rssBytes ? Math.min(100, Math.max(4, Math.round((row.rssBytes / maxRss) * 100))) : 0;
      const cpuVal = row.cpuPercent != null ? row.cpuPercent.toFixed(1) : null;
      const iconName = categoryIcon(row);
      const growthClass = row.growing ? 'memory-growth-positive' : '';
      const statusClass = row.protected ? 'is-protected' : row.growing ? 'is-growing' : row.historyReady ? 'is-stable' : 'is-collecting';
      const statusText = row.protected ? mt(row.protected) : row.growing ? mt('growing') : row.historyReady ? mt('stable') : mt('collecting');

      return `<tr class="${isChecked ? 'is-selected' : ''}">
        <td class="memory-td-select">
          <input type="checkbox" data-memory-action="select" data-key="${e(row.key)}" aria-label="${e(`${mt('selection')} ${row.name} (${row.pid})`)}" ${row.protected ? 'disabled' : ''} ${isChecked ? 'checked' : ''}>
        </td>
        <td class="memory-td-name">
          <div class="memory-proc-info" title="${e(row.exe || row.name)}">
            <span class="memory-proc-icon">${sfSymbol(iconName)}</span>
            <div class="memory-proc-text">
              <strong class="memory-proc-title">${e(row.name)}</strong>
              <small class="memory-proc-role">${e(mt(row.role))}</small>
            </div>
          </div>
        </td>
        <td class="memory-pid"><span class="memory-pid-pill">${row.pid}</span></td>
        <td class="memory-number memory-rss-cell">
          <div class="memory-cell-metric">
            <span class="memory-val">${e(row.rssBytes == null ? mt('unknown') : formatBytes(row.rssBytes))}</span>
            <div class="memory-bar-track" aria-hidden="true"><div class="memory-bar-fill rss-fill" style="width: ${rssPercent}%"></div></div>
          </div>
        </td>
        <td class="memory-number ${growthClass}">
          <div class="memory-cell-metric">
            ${memoryGrowthCell(row, statusClass)}
          </div>
        </td>
        <td class="memory-number memory-cpu-cell">
          <div class="memory-cell-metric">
            <span class="memory-val">${cpuVal == null ? e(mt('unknown')) : `${cpuVal}%`}</span>
            ${cpuVal != null ? `<div class="memory-bar-track" aria-hidden="true"><div class="memory-bar-fill cpu-fill" style="width: ${Math.min(100, Math.round(Number(cpuVal)))}%"></div></div>` : ''}
          </div>
        </td>
        <td>
          <span class="memory-status ${statusClass}">
            <span class="memory-status-dot" aria-hidden="true"></span>
            <span class="memory-status-text">${e(statusText)}</span>
          </span>
        </td>
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
      </tr>`;
    }).join('') || `<tr><td class="memory-empty" colspan="8">${sfSymbol(metrics.measuredAt ? 'magnifyingglass' : 'waveform.path.ecg')}<strong>${e(metrics.measuredAt ? mt('empty') : mt('loading'))}</strong></td></tr>`;
  }

  if (focusKey && focusAction) document.querySelector(`#memory-processes [data-key="${CSS.escape(focusKey)}"][data-memory-action="${focusAction}"]`)?.focus({ preventScroll: true });

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

async function showMemoryDetails(key, scroll = true) {
  memoryState.detailKey = key;
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

    <p class="memory-note">${e(mt('evidence'))}</p>

    <figure class="memory-trend-figure">
      <figcaption>${e(mt('trend'))}</figcaption>
      <svg class="memory-trend" viewBox="0 0 1000 160" preserveAspectRatio="none" role="img" aria-label="${e(mt('trendRange', { old: Math.round(age), low: formatBytes(low), high: formatBytes(high) }))}">
        <defs>
          <linearGradient id="memory-chart-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="var(--primary)" stop-opacity="0.32" />
            <stop offset="100%" stop-color="var(--primary)" stop-opacity="0.02" />
          </linearGradient>
        </defs>
        <line x1="${padLeft}" y1="${padTop}" x2="${padLeft + chartW}" y2="${padTop}" stroke="currentColor" stroke-opacity="0.08" stroke-dasharray="4 4" vector-effect="non-scaling-stroke" />
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
    const { row, result } = memoryState.detailData;
    renderMemoryDetails(row, result);
  }
});

document.addEventListener('DOMContentLoaded', () => {
  document.querySelector('[data-tab="memory"]')?.addEventListener('click', refreshMemory);

  document.getElementById('memory-refresh-btn')?.addEventListener('click', async () => {
    const btn = document.getElementById('memory-refresh-btn');
    btn?.classList.add('is-refreshing');
    await refreshMemory();
    setTimeout(() => btn?.classList.remove('is-refreshing'), 600);
  });

  ['memory-search', 'memory-filter', 'memory-sort'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', renderMemory);
  });

  // Filter Pills click handling
  document.getElementById('memory-filter-pills')?.addEventListener('click', event => {
    const pill = event.target.closest('[data-pill]');
    if (!pill) return;
    const filter = pill.dataset.pill;
    const filterSelect = document.getElementById('memory-filter');
    if (filterSelect) filterSelect.value = filter;
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
    const visibleEligible = memoryVisibleRows().filter(r => !r.protected);
    if (checked) {
      addMemorySelection(visibleEligible);
    } else {
      visibleEligible.forEach(r => memoryState.selected.delete(r.key));
    }
    memorySelection();
    renderMemory();
  });

  document.getElementById('memory-select')?.addEventListener('click', () => {
    addMemorySelection(memoryVisibleRows().filter(row => !row.protected));
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
    if (control.dataset.memoryAction === 'select') {
      if (control.checked) memoryState.selected.add(key);
      else memoryState.selected.delete(key);
      memorySelection();
      const tr = control.closest('tr');
      if (tr) tr.classList.toggle('is-selected', control.checked);
    }
    if (control.dataset.memoryAction === 'details') showMemoryDetails(key);
    if (control.dataset.memoryAction === 'exclude') memoryConfigure({ operation: 'exclude', key });
    if (control.dataset.memoryAction === 'rule') showMemoryRule(key);
  });

  // Details panel interactions (close, copy path, actions)
  document.getElementById('memory-details')?.addEventListener('click', event => {
    if (event.target.closest('#memory-details-close')) {
      const target = document.getElementById('memory-details');
      if (target) target.hidden = true;
      memoryState.detailKey = null;
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
