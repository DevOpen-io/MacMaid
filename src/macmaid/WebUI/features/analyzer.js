/* =========================================================
   MacMaid Pro — Disk analyzer and storage treemap:
   incremental analysis, cached views, reconnect-on-nav
   ========================================================= */

// =========================================================
// Tab 6: Disk Space Analyzer (analyze)
// =========================================================

function renderAnalyzerSnapshot(data, requestId) {
  if (requestId !== state.analyzerRequestId) return;
  const folderBars = document.getElementById('folder-bars-container');
  const tbodyFiles = document.getElementById('tbody-analyzer-files');
  const cachedBadge = document.getElementById('analyzer-cached-badge');
  const entries = data.entries || [];

  state.analyzerViews.set(data.path, data);
  document.getElementById('analyzer-path-input').value = data.path;
  document.getElementById('analyzer-current-path').textContent = data.path;
  document.getElementById('analyzer-total-size').textContent = data.isComplete
    ? (data.humanTotal || formatBytes(data.totalBytes))
    : `${data.humanTotal || formatBytes(data.totalBytes)} ${t('analyzer.measured', 'measured')}`;
  cachedBadge?.classList.toggle('hidden', !data.cached);

  if (entries.length === 0) {
    folderBars.innerHTML = `<div class="empty-state">${t('analyzer.empty_dir', 'No visible items in this directory.')}</div>`;
  } else {
    folderBars.innerHTML = entries.map(entry => {
      const ready = entry.state === 'ready';
      const partial = entry.state === 'partial';
      const scanning = entry.state === 'scanning';
      const failed = entry.state === 'failed';
      const measured = ready || partial;
      const sizeLabel = measured ? `${partial ? '~' : ''}${entry.humanBytes || formatBytes(entry.bytes)}` : (failed ? t('analyzer.unreadable', 'Unreadable') : (scanning ? t('analyzer.measuring', 'Measuring…') : t('analyzer.queued', 'Queued')));
      const percentLabel = measured ? `${entry.percent || 0}%` : '';
      const rowClass = ready ? 'is-ready' : (partial ? 'is-partial' : (failed ? 'is-failed' : 'is-measuring'));
      const barClass = measured ? '' : 'indeterminate';
      const width = measured ? Math.max(2, entry.percent || 0) : 100;
      const title = partial ? t('analyzer.partial_tip', 'Partial measurement — some entries were inaccessible') : (entry.isDirectory ? t('analyzer.enter_dir', 'Enter this directory') : t('common.th_file', 'File'));
      return `
        <div class="folder-bar-item ${rowClass}" data-path="${escapeHtml(entry.path)}" data-directory="${entry.isDirectory}" tabindex="${entry.isDirectory ? '0' : '-1'}" ${entry.isDirectory ? 'role="button"' : ''} title="${escapeHtml(title)}">
          <div class="folder-bar-header">
            <span class="folder-name">
              <span class="folder-icon">${sfSymbol(entry.isDirectory ? 'folder' : 'doc')}</span>
              ${escapeHtml(entry.name)}
            </span>
            <div class="folder-size-wrap">
              <span class="text-muted">${percentLabel}</span>
              <strong>${escapeHtml(sizeLabel)}</strong>
            </div>
          </div>
          <div class="folder-bar-track">
            <div class="folder-bar-fill ${barClass}" style="width: ${width}%"></div>
          </div>
        </div>`;
    }).join('');

    folderBars.querySelectorAll('.folder-bar-item[data-directory="true"]').forEach(item => {
      const open = () => runDiskAnalyzer(item.dataset.path);
      item.addEventListener('click', open);
      item.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          open();
        }
      });
    });
  }

  if (!data.largestFiles || data.largestFiles.length === 0) {
    tbodyFiles.innerHTML = `<tr><td colspan="4" class="empty-state">${data.isComplete ? t('analyzer.no_large_files', 'No files above threshold in this directory.') : t('analyzer.files_pending', 'Files will appear here as they are processed…')}</td></tr>`;
  } else {
    tbodyFiles.innerHTML = data.largestFiles.map(file => `
      <tr>
        <td><span class="table-label">${escapeHtml(file.name)}</span></td>
        <td><span class="table-path">${escapeHtml(file.path)}</span></td>
        <td class="table-number">${escapeHtml(file.humanBytes)}</td>
        <td class="table-action"><button class="btn btn-secondary btn-sm btn-trash-file" data-path="${escapeHtml(file.path)}" title="${t('analyzer.move_trash_tip', 'Move to Trash')}">${t('analyzer.trash_btn', 'Trash')}</button></td>
      </tr>`).join('');

    tbodyFiles.querySelectorAll('.btn-trash-file').forEach(btn => {
      btn.addEventListener('click', async () => {
        const path = btn.dataset.path;
        const payload = { path };
        await reviewedMutation('/api/analyze/trash', payload, {
          confirmText: t('common.move_to_trash', 'Move to Trash'),
          progressLabel: t('analyzer.action_trashing', 'Moving file to Trash…'),
          onSuccess: data => {
            showOutcomeToast(data);
            runDiskAnalyzer(state.currentAnalyzePath, { force: true });
          },
          onError: error => {
            showToast(`${t('toast.error_prefix', 'Error: ')}${error.message}`, 'error');
            showOperationOutcome('error', error.message);
          },
        });
      });
    });
  }
}

async function fetchAnalyzerSnapshot(path, requestId, { start = false, force = false } = {}) {
  const params = new URLSearchParams({ path, start: String(start), nav: String(requestId) });
  if (force) params.set('force', 'true');
  const response = await fetch(`/api/analyze?${params}`);
  const data = await readAPIResponse(response);
  if (requestId !== state.analyzerRequestId) return;

  state.currentAnalyzePath = data.path;
  state.analyzerViews.set(path, data);
  renderAnalyzerSnapshot(data, requestId);
  if (data.isComplete) {
    stopLiveProgressPolling();
    return;
  }
  state.analyzerPollTimer = setTimeout(() => {
    fetchAnalyzerSnapshot(data.path, requestId).catch(error => {
      if (requestId !== state.analyzerRequestId) return;
      showToast(`${t('clean.title', 'Analyze')} error: ${error.message}`, 'error');
      showOperationOutcome('error', error.message);
      stopLiveProgressPolling();
    });
  }, 300);
}

async function runDiskAnalyzer(targetPath = null, options = {}) {
  SoundEffects.playClick();
  const path = targetPath || document.getElementById('analyzer-path-input').value || '~';
  const requestId = ++state.analyzerRequestId;
  if (state.analyzerPollTimer) clearTimeout(state.analyzerPollTimer);
  state.currentAnalyzePath = path;
  document.getElementById('analyzer-path-input').value = path;

  const resultsBox = document.getElementById('analyzer-results-box');
  document.getElementById('analyzer-idle-state')?.classList.add('hidden');
  resultsBox.classList.remove('hidden');
  document.getElementById('analyzer-current-path').textContent = path;

  const folderBars = document.getElementById('folder-bars-container');
  const tbodyFiles = document.getElementById('tbody-analyzer-files');
  const localSnapshot = state.analyzerViews.get(path);
  if (localSnapshot) {
    renderAnalyzerSnapshot(localSnapshot, requestId);
  } else {
    document.getElementById('analyzer-total-size').textContent = '--';
    document.getElementById('analyzer-cached-badge')?.classList.add('hidden');
    folderBars.innerHTML = `<div class="loading-state">${t('analyzer.reading_folders', 'Reading folder names…')}</div>`;
    tbodyFiles.innerHTML = `<tr><td colspan="4" class="empty-state">${t('analyzer.searching_large', 'Searching large files...')}</td></tr>`;
  }

  startLiveProgressPolling(t('analyzer.listing_folders', 'Listing folders…'));

  try {
    await fetchAnalyzerSnapshot(path, requestId, { start: true, force: options.force === true });
  } catch (err) {
    if (requestId !== state.analyzerRequestId) return;
    folderBars.innerHTML = `<div class="empty-state">${t('toast.error_prefix', 'Error: ')}${escapeHtml(err.message)}</div>`;
    showOperationOutcome('error', err.message);
    stopLiveProgressPolling();
  }
}

function navigateAnalyzerToParent() {
  const current = state.currentAnalyzePath || document.getElementById('analyzer-path-input')?.value || '~';
  const trimmed = current.trim();
  if (trimmed === '/' || trimmed === '') {
    showToast(t('toast.already_root', 'Already at root directory (/)...'), 'info');
    return;
  }
  if (trimmed === '~') {
    runDiskAnalyzer('/Users');
    return;
  }
  if (trimmed.startsWith('~/')) {
    const parts = trimmed.split('/').filter(Boolean);
    if (parts.length <= 1) {
      runDiskAnalyzer('~');
    } else {
      parts.pop();
      runDiskAnalyzer(parts.join('/'));
    }
    return;
  }
  const clean = trimmed.replace(/\/+$/, '');
  const lastSlash = clean.lastIndexOf('/');
  if (lastSlash <= 0) {
    runDiskAnalyzer('/');
  } else {
    runDiskAnalyzer(clean.substring(0, lastSlash));
  }
}

// =========================================================
// Storage Treemap
// =========================================================
let treemapPath = '~';
let treemapParent = '~';

function syncTreemapParentButton() {
  const button = document.getElementById('btn-treemap-back');
  if (button) button.disabled = treemapPath === '~' || treemapParent === treemapPath;
}
let treemapRequestId = 0;
let lastTreemapData = null;
let lastTreemapRenderSignature = '';
const treemapViews = new Map();

function getTreemapRenderSignature(data) {
  const nodePaths = (data.nodes || []).map(node => node.path || node.name || '').join('|');
  return `${data.path || ''}:${data.isComplete ? 'done' : 'scan'}:${nodePaths}`;
}

function splitTreemapItems(items, x, y, width, height, depth = 0, out = []) {
  if (!items.length || width <= 0 || height <= 0) return out;
  if (items.length === 1) {
    out.push({ ...items[0], x, y, width, height, depth });
    return out;
  }

  const total = items.reduce((sum, item) => sum + item.value, 0);
  let running = 0;
  let splitIndex = 1;
  for (let i = 0; i < items.length - 1; i++) {
    const next = running + items[i].value;
    if (Math.abs(total / 2 - next) <= Math.abs(total / 2 - running)) {
      running = next;
      splitIndex = i + 1;
    } else {
      break;
    }
  }

  const first = items.slice(0, splitIndex);
  const second = items.slice(splitIndex);
  const firstTotal = first.reduce((sum, item) => sum + item.value, 0);
  const ratio = total ? firstTotal / total : 0.5;

  if (width >= height) {
    const firstWidth = Math.max(1, Math.round(width * ratio));
    splitTreemapItems(first, x, y, firstWidth, height, depth + 1, out);
    splitTreemapItems(second, x + firstWidth, y, width - firstWidth, height, depth + 1, out);
  } else {
    const firstHeight = Math.max(1, Math.round(height * ratio));
    splitTreemapItems(first, x, y, width, firstHeight, depth + 1, out);
    splitTreemapItems(second, x, y + firstHeight, width, height - firstHeight, depth + 1, out);
  }
  return out;
}

function renderTreemap(data) {
  const box = document.getElementById('treemap-box');
  if (!box) return;
  const nodes = (data.nodes || [])
    .map((node, index) => ({ ...node, index, value: Math.max(0, Number(node.bytes || 0)) }))
    .filter(node => node.value > 0)
    .sort((a, b) => b.value - a.value);

  if (!nodes.length) {
    box.innerHTML = `<div class="empty-state">${data.isComplete ? t('more.empty_treemap_folder', 'No items to show in this folder.') : t('more.treemap_initial_measuring', 'Measuring initial results…')}</div>`;
    return;
  }

  const boxStyle = window.getComputedStyle(box);
  const horizontalPadding = parseFloat(boxStyle.paddingLeft || '0') + parseFloat(boxStyle.paddingRight || '0');
  const verticalPadding = parseFloat(boxStyle.paddingTop || '0') + parseFloat(boxStyle.paddingBottom || '0');
  const width = Math.max(1, Math.floor((box.clientWidth || 720) - horizontalPadding));
  const availableHeight = Math.max(1, Math.floor((box.clientHeight || 520) - verticalPadding));
  const summaryReserve = width < 760 ? 68 : 44;
  const height = Math.max(1, availableHeight - summaryReserve);
  const rects = splitTreemapItems(nodes, 0, 0, width, height);
  const largest = nodes[0]?.value || 1;
  const totalBytes = nodes.reduce((sum, node) => sum + node.value, 0);
  const palette = ['#3b82f6', '#06b6d4', '#8b5cf6', '#10b981', '#f59e0b', '#ec4899', '#6366f1', '#14b8a6'];

  box.innerHTML = `
    <div class="treemap-shell">
      <div class="treemap-summary-row">
        <span><strong>${nodes.length}</strong> ${t('more.items_mapped', 'items mapped')}</span>
        <span>${t('more.total_visible_space', 'Total visible space: ')}<strong>${escapeHtml(data.humanTotal || formatBytes(totalBytes))}</strong></span>
        <span class="text-muted">${t('more.treemap_hint', 'Tile size scales with disk usage. Click a box to drill into the folder.')}</span>
      </div>
      <div class="treemap-canvas" style="height:${height}px;">
        ${rects.map(rect => {
          const pad = rect.width > 26 && rect.height > 26 ? 4 : 2;
          const color = palette[rect.index % palette.length];
          const intensity = 0.45 + Math.min(0.35, rect.value / largest * 0.35);
          const area = rect.width * rect.height;
          const compact = area < 15000;
          const tiny = area < 5200;
          const percent = totalBytes ? rect.value / totalBytes * 100 : Number(rect.percentage || 0);
          const action = rect.cleanupCandidate ? `<button class="mini-btn treemap-trash" data-path="${escapeHtml(rect.path)}">Review</button>` : '';
          return `<div class="treemap-tile ${rect.directory ? 'is-directory' : 'is-file'} ${tiny ? 'is-tiny' : ''}" data-path="${escapeHtml(rect.path)}" data-directory="${rect.directory ? 'true' : 'false'}" title="${escapeHtml(rect.name)} · ${escapeHtml(rect.humanBytes || formatBytes(rect.value))} · ${percent.toFixed(1)}%" style="left:${rect.x + pad}px;top:${rect.y + pad}px;width:${Math.max(0, rect.width - pad * 2)}px;height:${Math.max(0, rect.height - pad * 2)}px;--tile-color:${color};--tile-glow:${color}66;--tile-alpha:${intensity};">
            <div class="treemap-tile-bg"></div>
            ${tiny ? '' : `<div class="treemap-tile-content">
              <div class="treemap-tile-name">${escapeHtml(rect.name)}</div>
              <div class="treemap-tile-meta">${escapeHtml(rect.humanBytes || formatBytes(rect.value))} · ${percent.toFixed(1)}%</div>
              ${compact ? '' : `<div class="treemap-tile-actions"><button class="mini-btn treemap-open" data-path="${escapeHtml(rect.path)}">Finder</button>${rect.directory ? `<button class="mini-btn treemap-drill" data-path="${escapeHtml(rect.path)}">Drill down</button>` : ''}${action}</div>`}
            </div>`}
          </div>`;
        }).join('')}
      </div>
    </div>`;

  box.querySelectorAll('.treemap-tile').forEach(tile => {
    tile.addEventListener('click', event => {
      if (event.target.closest('button')) return;
      if (tile.dataset.directory === 'true') fetchTreemap(tile.dataset.path);
    });
  });
  box.querySelectorAll('.treemap-drill').forEach(btn => btn.addEventListener('click', () => fetchTreemap(btn.dataset.path)));
  box.querySelectorAll('.treemap-open').forEach(btn => btn.addEventListener('click', () => openTreemapPath(btn.dataset.path)));
  box.querySelectorAll('.treemap-trash').forEach(btn => btn.addEventListener('click', () => trashTreemapPath(btn.dataset.path)));
}

async function fetchTreemap(path = treemapPath, force = false, polling = false, requestId = 0) {
  const box = document.getElementById('treemap-box');
  const card = document.getElementById('treemap-progress-card');
  if (!box) return;
  if (!polling) {
    requestId = ++treemapRequestId;
    lastTreemapRenderSignature = '';
    const localSnapshot = !force ? treemapViews.get(path) : null;
    if (localSnapshot) {
      treemapPath = localSnapshot.path || path;
      treemapParent = localSnapshot.parent || '~';
      syncTreemapParentButton();
      document.getElementById('treemap-path').textContent = `${treemapPath} · ${localSnapshot.humanTotal || '0 B'}`;
      lastTreemapData = localSnapshot;
      lastTreemapRenderSignature = getTreemapRenderSignature(localSnapshot);
      renderTreemap(localSnapshot);
      card?.classList.add('hidden');
    } else {
      box.innerHTML = `<div class="empty-state">${t('more.treemap_measuring', 'Measuring treemap…')}</div>`;
      card?.classList.remove('hidden');
    }
  }
  try {
    const params = new URLSearchParams({ path, start: polling ? 'false' : 'true' });
    if (force) params.set('force', 'true');
    const data = await readAPIResponse(await fetch(`/api/treemap?${params}`));
    if (requestId !== treemapRequestId) return;
    treemapPath = data.path || path;
    treemapParent = data.parent || '~';
    syncTreemapParentButton();
    treemapViews.set(path, data);
    if (data.path) treemapViews.set(data.path, data);
    const total = Math.max(0, Number(data.total || 0));
    const done = Math.max(0, Number(data.completed || 0) + Number(data.failed || 0));
    const percent = total ? Math.min(100, Math.round(done / total * 100)) : 100;
    document.getElementById('treemap-path').textContent = `${treemapPath} · ${data.humanTotal || '0 B'}`;
    document.getElementById('treemap-progress-percent').textContent = `${percent}% · ${done}/${total}`;
    document.getElementById('treemap-progress-bar').style.width = `${percent}%`;
    document.getElementById('treemap-progress-path').textContent = data.currentScanPath || treemapPath;
    document.getElementById('treemap-action-label').textContent = data.isComplete ? t('more.treemap_done', 'Treemap scan completed') : t('more.action_scanning_treemap', 'Scanning treemap…');
    lastTreemapData = data;
    const renderSignature = getTreemapRenderSignature(data);
    if (renderSignature !== lastTreemapRenderSignature) {
      lastTreemapRenderSignature = renderSignature;
      renderTreemap(data);
    }
    if (!data.isComplete && document.getElementById('subpane-more-treemap')?.classList.contains('active')) {
      card?.classList.remove('hidden');
      setTimeout(() => fetchTreemap(treemapPath, false, true, requestId), 500);
    } else if (data.isComplete) {
      setTimeout(() => {
        card?.classList.add('hidden');
        lastTreemapRenderSignature = '';
        requestAnimationFrame(() => renderTreemap(data));
      }, 1200);
    }
  } catch (err) {
    if (requestId !== treemapRequestId) return;
    card?.classList.add('hidden');
    box.innerHTML = `<div class="empty-state">${t('more.treemap_failed', 'Treemap failed: ')}${escapeHtml(err.message)}</div>`;
  }
}

async function openTreemapPath(path) {
  try {
    await readAPIResponse(await fetch('/api/treemap/open', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }) }));
  } catch (err) { showToast(`Open in Finder failed: ${err.message}`, 'error'); }
}

async function trashTreemapPath(path) {
  const payload = { paths: [path] };
  await reviewedMutation('/api/treemap/trash', payload, {
    confirmText: t('common.move_to_trash', 'Move to Trash'),
    trackProgress: false,
    onSuccess: result => {
      showOutcomeToast(result);
      fetchTreemap(treemapPath, true);
    },
  });
}

function reconnectTreemap() {
  const cachedView = treemapViews.get(treemapPath) || lastTreemapData;
  if (!cachedView) return;
  treemapPath = cachedView.path || treemapPath;
  treemapParent = cachedView.parent || '~';
  syncTreemapParentButton();
  document.getElementById('treemap-path').textContent = `${treemapPath} · ${cachedView.humanTotal || '0 B'}`;
  lastTreemapData = cachedView;
  lastTreemapRenderSignature = getTreemapRenderSignature(cachedView);
  renderTreemap(cachedView);
  // Re-attach to an in-flight analysis without starting a new one (start=false).
  if (!cachedView.isComplete && !cachedView.isCancelled) {
    fetchTreemap(treemapPath, false, true, ++treemapRequestId);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  // Disk Analyzer events
  document.getElementById('btn-run-analyzer')?.addEventListener('click', () => runDiskAnalyzer());
  document.getElementById('btn-analyzer-parent')?.addEventListener('click', () => navigateAnalyzerToParent());
  document.querySelectorAll('.btn-quick-path').forEach(btn => {
    btn.addEventListener('click', () => runDiskAnalyzer(btn.dataset.path));
  });
  document.getElementById('btn-scan-treemap')?.addEventListener('click', () => fetchTreemap(treemapPath, true));
  document.getElementById('btn-treemap-back')?.addEventListener('click', () => fetchTreemap(treemapParent));
  let treemapResizeTimer = null;
  window.addEventListener('resize', () => {
    if (!lastTreemapData || !document.getElementById('subpane-more-treemap')?.classList.contains('active')) return;
    clearTimeout(treemapResizeTimer);
    treemapResizeTimer = setTimeout(() => renderTreemap(lastTreemapData), 120);
  });
});
