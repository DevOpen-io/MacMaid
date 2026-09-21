/* =========================================================
   MacMaid Pro — File-based cleanup: installers, leftovers,
   browser storage, smart downloads, large files, duplicates
   ========================================================= */

// =========================================================
// Tab 4: Installers Cleaner (installers)
// =========================================================

async function scanInstallers() {
  SoundEffects.playClick();
  const tbody = document.getElementById('tbody-installers');
  tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('more.action_scanning_installers_sub', 'Scanning installer files...')}</td></tr>`;
  startLiveProgressPolling();

  try {
    // Discover once at the lowest threshold; the age pills then filter the
    // cached result client-side instead of rescanning the disk.
    const res = await fetch(`/api/installers?olderThan=0`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.installersAll = data.installers || [];
    state.selectedInstallers = new Set();
    renderInstallers();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('toast.error_prefix', 'Error: ')}${escapeHtml(err.message)}</td></tr>`;
  } finally {
    stopLiveProgressPolling();
  }
}

function renderInstallers() {
  const tbody = document.getElementById('tbody-installers');
  if (!tbody) return;
  const daysPill = document.querySelector('.installer-age-pill.active');
  const days = Number(daysPill?.dataset.days ?? 30);
  const visible = (state.installersAll || []).filter(item => days === 0 || (item.ageDays ?? days) >= days);
  state.installers = visible;
  state.selectedInstallers = new Set(visible.map(i => i.path));

  document.getElementById('installers-total-size').textContent = formatBytes(visible.reduce((sum, i) => sum + (i.bytes || 0), 0));
  document.getElementById('installers-count').textContent = t('common.file_count', '{count} files').replace('{count}', String(visible.length));
  syncMasterCheckbox('master-installers-chk', visible.length, state.selectedInstallers.size);

  if (visible.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('more.empty_installers_found', 'No old installer files found.')}</td></tr>`;
    return;
  }

  tbody.innerHTML = visible.map(item => `
    <tr>
      <td><input type="checkbox" class="installer-chk" data-path="${escapeHtml(item.path)}" checked></td>
      <td><strong>${escapeHtml(item.label)}</strong></td>
      <td><span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(item.path)}</span></td>
      <td><span style="font-size: 11.5px; color: var(--text-dim);">${escapeHtml(item.reason)}</span></td>
      <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${escapeHtml(item.humanBytes)}</td>
    </tr>
  `).join('');

  tbody.querySelectorAll('.installer-chk').forEach(chk => {
    chk.addEventListener('change', (e) => {
      const p = e.target.dataset.path;
      if (e.target.checked) state.selectedInstallers.add(p);
      else state.selectedInstallers.delete(p);
      syncMasterCheckbox('master-installers-chk', state.installers.length, state.selectedInstallers.size);
    });
  });
}

async function executeInstallersClean() {
  if (state.selectedInstallers.size === 0) {
    showToast(t('toast.select_installer_warn', 'Select at least one installer to delete.'), 'warning');
    return;
  }

  const paths = Array.from(state.selectedInstallers);
  const payload = { paths };
  await reviewedMutation('/api/installers/clean', payload, {
    confirmText: t('common.move_to_trash', 'Move to Trash'),
    buttonId: 'btn-execute-installers-clean',
    onSuccess: data => {
      SoundEffects.playSuccess();
      showOutcomeToast(data);
      scanInstallers();
    },
  });
}

// =========================================================
// Tab 5: Leftovers Cleaner (leftovers)
// =========================================================

async function scanLeftovers() {
  SoundEffects.playClick();
  const includeData = document.getElementById('chk-leftovers-data').checked;

  const tbody = document.getElementById('tbody-leftovers');
  tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('more.action_scanning_leftovers_sub', 'Scanning orphaned application leftovers...')}</td></tr>`;
  startLiveProgressPolling();

  try {
    // Discover once at the lowest threshold; the age pills then filter the
    // cached result client-side instead of rescanning the filesystem.
    const res = await fetch(`/api/leftovers?olderThan=0&includeData=${includeData}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.leftoversAll = data.leftovers || [];
    state.leftoversIssues = data.issues || [];
    state.selectedLeftovers = new Set();
    renderLeftovers();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('toast.error_prefix', 'Error: ')}${escapeHtml(err.message)}</td></tr>`;
  } finally {
    stopLiveProgressPolling();
  }
}

function renderLeftovers() {
  const tbody = document.getElementById('tbody-leftovers');
  if (!tbody) return;
  const daysPill = document.querySelector('.leftover-age-pill.active');
  const days = Number(daysPill?.dataset.days ?? 30);
  const visible = (state.leftoversAll || []).filter(item => days === 0 || (item.ageDays ?? days) >= days);
  state.leftovers = visible;
  state.selectedLeftovers = new Set(visible.filter(l => l.risk !== 'MANUAL').map(l => l.id));
  const issues = state.leftoversIssues || [];

  document.getElementById('leftovers-total-size').textContent = formatBytes(visible.reduce((sum, i) => sum + (i.bytes || 0), 0));
  document.getElementById('leftovers-count').textContent = `(${visible.length} ${t('more.leftovers_title', 'leftovers')})`;
  const actionableCount = visible.filter(item => item.risk !== 'MANUAL').length;
  syncMasterCheckbox('master-leftovers-chk', actionableCount, state.selectedLeftovers.size);

  if (visible.length === 0) {
    tbody.innerHTML = accessNoticeRow(issues, 5) + `<tr><td colspan="5" class="empty-state">${t('more.empty_leftovers_found', 'No orphaned leftover files found.')}</td></tr>`;
    return;
  }

  tbody.innerHTML = accessNoticeRow(issues, 5) + visible.map(item => `
    <tr>
      <td><input type="checkbox" class="leftover-chk" data-id="${item.id}" ${item.risk === 'MANUAL' ? 'disabled' : 'checked'}></td>
      <td><strong>${escapeHtml(item.label)}</strong></td>
      <td><span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(item.path)}</span></td>
      <td><span class="badge-status">${escapeHtml(item.risk)}</span></td>
      <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${escapeHtml(item.humanBytes)}</td>
    </tr>
  `).join('');

  tbody.querySelectorAll('.leftover-chk').forEach(chk => {
    chk.addEventListener('change', (e) => {
      const id = e.target.dataset.id;
      if (e.target.checked) state.selectedLeftovers.add(id);
      else state.selectedLeftovers.delete(id);
      syncMasterCheckbox('master-leftovers-chk', state.leftovers.filter(item => item.risk !== 'MANUAL').length, state.selectedLeftovers.size);
    });
  });
}

async function executeLeftoversClean() {
  if (state.selectedLeftovers.size === 0) {
    showToast(t('toast.select_leftover_warn', 'Select at least one leftover to delete.'), 'warning');
    return;
  }

  const itemIds = Array.from(state.selectedLeftovers);
  const payload = { itemIds };
  await reviewedMutation('/api/leftovers/clean', payload, {
    confirmText: t('common.delete', 'Delete'),
    buttonId: 'btn-execute-leftovers-clean',
    onSuccess: data => {
      SoundEffects.playSuccess();
      showOutcomeToast(data);
      scanLeftovers();
    },
  });
}

// =========================================================
// Browser Storage Inspector
// =========================================================

function accessNoticeRow(issues, colspan) {
  const denied = (issues || []).filter(issue => /denied|permitted/i.test(issue));
  if (!denied.length) return '';
  return `<tr><td colspan="${colspan}"><div class="scan-notice">${escapeHtml(t('more.access_denied', 'macOS denied access to some locations. Grant Full Disk Access in System Settings → Privacy & Security for complete results.'))}<br><small>${denied.slice(0, 3).map(escapeHtml).join(' · ')}${denied.length > 3 ? ` · +${denied.length - 3}` : ''}</small></div></td></tr>`;
}

async function fetchBrowserStorage() {
  const tbody = document.getElementById('tbody-browser-storage');
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${t('more.action_scanning_browsers_sub', 'Scanning browser storage…')}</td></tr>`;
  try {
    const data = await readAPIResponse(await fetch('/api/browser-storage'));
    state.browserStorage = data;
    document.getElementById('browser-safe-cache').textContent = data.humanSafeCache || '0 B';
    tbody.innerHTML = accessNoticeRow(data.issues, 6) + ((data.areas || []).map(area => {
      const checked = area.cleanable ? 'checked' : '';
      const disabled = area.cleanable ? '' : 'disabled';
      const riskClass = area.cleanable ? 'highlight-green' : 'text-muted';
      return `<tr>
        <td><input type="checkbox" class="browser-storage-chk" data-id="${escapeHtml(area.itemId || '')}" ${checked} ${disabled}></td>
        <td>${escapeHtml(area.browser || '')}</td><td>${escapeHtml(area.profile || '')}</td><td>${escapeHtml(area.kind || '')}<br><small>${escapeHtml(area.reason || '')}</small></td>
        <td><span class="${riskClass}">${escapeHtml(area.risk || '')}${area.cleanable ? ' · Smart Clean' : ' · Not auto-selected'}</span></td>
        <td>${escapeHtml(area.humanBytes || formatBytes(area.bytes || 0))}</td>
      </tr>`;
    }).join('') || `<tr><td colspan="6" class="empty-state">${t('more.empty_browsers_found', 'No browser storage found.')}</td></tr>`);
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${t('more.browser_scan_failed', 'Browser storage scan failed: ')}${escapeHtml(err.message)}</td></tr>`;
  }
}

async function cleanBrowserCache() {
  const ids = Array.from(document.querySelectorAll('.browser-storage-chk:checked')).map(chk => chk.dataset.id).filter(Boolean);
  if (ids.length === 0) return showToast(t('toast.no_safe_cache_warn', 'No safe cache area selected for Smart Clean.'), 'warning');
  const payload = { itemIds: ids };
  await reviewedMutation('/api/browser-storage/clean', payload, {
    confirmText: t('common.clean', 'Clean'),
    trackProgress: false,
    onSuccess: result => {
      showOutcomeToast(result);
      fetchBrowserStorage();
    },
  });
}

// =========================================================
// Smart Downloads
// =========================================================

async function fetchSmartDownloads() {
  const tbody = document.getElementById('tbody-smart-downloads');
  if (!tbody) return;
  const age = document.getElementById('smart-downloads-age-filter')?.value || '30';
  tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('more.action_scanning_downloads_sub', 'Scanning smart downloads…')}</td></tr>`;
  try {
    const data = await readAPIResponse(await fetch(`/api/smart-downloads?olderThanDays=${encodeURIComponent(age)}`));
    tbody.innerHTML = (data.files || []).map(file => `<tr>
      <td>${escapeHtml((file.categories || []).join(', '))}</td>
      <td><strong>${escapeHtml(file.name || '')}</strong><br><span style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(file.path)}</span></td>
      <td>${Number(file.ageDays || 0)}d</td>
      <td>${escapeHtml(file.humanBytes || formatBytes(file.bytes || 0))}</td>
      <td><button class="mini-btn smart-download-trash" data-path="${escapeHtml(file.path)}">${t('common.move_to_trash', 'Move to Trash')}</button></td>
    </tr>`).join('') || `<tr><td colspan="5" class="empty-state">${t('more.empty_downloads_found', 'No smart download candidates found.')}</td></tr>`;
    tbody.querySelectorAll('.smart-download-trash').forEach(button => button.addEventListener('click', () => trashSmartDownloadPath(button.dataset.path)));
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('more.downloads_scan_failed', 'Smart Downloads scan failed: ')}${escapeHtml(err.message)}</td></tr>`;
  }
}

async function trashSmartDownloadPath(path) {
  if (!path) return;
  const payload = { paths: [path] };
  await reviewedMutation('/api/smart-downloads/trash', payload, {
    confirmText: t('common.move_to_trash', 'Move to Trash'),
    trackProgress: false,
    onSuccess: result => {
      showOutcomeToast(result);
      fetchSmartDownloads();
    },
  });
}

// =========================================================
// Large & Old Files
// =========================================================

async function fetchLargeFiles() {
  const tbody = document.getElementById('tbody-large-files');
  if (!tbody) return;
  const size = document.getElementById('large-size-filter')?.value || '500MB';
  const age = document.getElementById('large-age-filter')?.value || '';
  tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('more.action_scanning_large_sub', 'Scanning large and old files…')}</td></tr>`;
  startLiveProgressPolling();
  try {
    const params = new URLSearchParams({ minSize: size });
    if (age) params.set('olderThanDays', age);
    const data = await readAPIResponse(await fetch(`/api/large-files?${params}`));
    tbody.innerHTML = (data.files || []).map(file => `<tr>
      <td>${escapeHtml((file.categories || []).join(', '))}</td>
      <td><strong>${escapeHtml(file.name || '')}</strong><br><span style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(file.path)}</span></td>
      <td>${Number(file.ageDays || 0)}d</td>
      <td>${escapeHtml(file.humanBytes || formatBytes(file.bytes || 0))}</td>
      <td><button class="mini-btn large-file-trash" data-path="${escapeHtml(file.path)}">${t('common.move_to_trash', 'Move to Trash')}</button></td>
    </tr>`).join('') || `<tr><td colspan="5" class="empty-state">${t('more.empty_large_found', 'No large or old files matching filters found.')}</td></tr>`;
    tbody.querySelectorAll('.large-file-trash').forEach(button => button.addEventListener('click', () => trashLargeFilePath(button.dataset.path)));
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('more.large_scan_failed', 'Large/old scan failed: ')}${escapeHtml(err.message)}</td></tr>`;
  } finally {
    stopLiveProgressPolling();
  }
}

async function trashLargeFilePath(path) {
  if (!path) return;
  const payload = { paths: [path] };
  await reviewedMutation('/api/large-files/trash', payload, {
    confirmText: t('common.move_to_trash', 'Move to Trash'),
    trackProgress: false,
    onSuccess: result => {
      showOutcomeToast(result);
      fetchLargeFiles();
    },
  });
}

// =========================================================
// Duplicate Finder
// =========================================================

async function fetchDuplicates() {
  const tbody = document.getElementById('tbody-duplicates');
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="4" class="empty-state">${t('more.action_scanning_duplicates_sub', 'Scanning duplicates…')}</td></tr>`;
  try {
    const res = await fetch('/api/duplicates');
    const data = await readAPIResponse(res);
    const rows = [];
    (data.groups || []).forEach((group, groupIndex) => {
      (group.files || []).forEach(file => {
        rows.push(`<tr>
          <td>${t('duplicates.group', 'Group')} ${groupIndex + 1}<br><small>${escapeHtml(group.humanWasted || '')}</small></td>
          <td><span style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(file.path)}</span></td>
          <td>${escapeHtml(file.humanBytes || formatBytes(file.bytes || 0))}</td>
          <td><button class="mini-btn duplicate-trash" data-path="${escapeHtml(file.path)}">${t('common.move_to_trash', 'Move to Trash')}</button></td>
        </tr>`);
      });
    });
    tbody.innerHTML = rows.join('') || `<tr><td colspan="4" class="empty-state">${t('more.empty_duplicates_found', 'No byte-for-byte duplicates found.')}</td></tr>`;
    tbody.querySelectorAll('.duplicate-trash').forEach(button => {
      button.addEventListener('click', () => trashDuplicatePath(button.dataset.path));
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="4" class="empty-state">${t('more.duplicate_scan_failed', 'Duplicate scan failed: ')}${escapeHtml(err.message)}</td></tr>`;
  }
}

async function trashDuplicatePath(path) {
  if (!path) return;
  const payload = { paths: [path] };
  await reviewedMutation('/api/duplicates/trash', payload, {
    confirmText: t('common.move_to_trash', 'Move to Trash'),
    trackProgress: false,
    onSuccess: result => {
      showOutcomeToast(result);
      fetchDuplicates();
    },
  });
}

document.addEventListener('DOMContentLoaded', () => {
  // Installer age pills — filter the cached discovery result; no rescan.
  document.querySelectorAll('.installer-age-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      SoundEffects.playClick();
      document.querySelectorAll('.installer-age-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      if (state.installersAll) renderInstallers();
    });
  });
  // Leftover age pills — filter the cached discovery result; no rescan.
  document.querySelectorAll('.leftover-age-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      SoundEffects.playClick();
      document.querySelectorAll('.leftover-age-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      if (state.leftoversAll) renderLeftovers();
    });
  });
  // Installers events
  document.getElementById('btn-scan-installers')?.addEventListener('click', scanInstallers);
  document.getElementById('btn-execute-installers-clean')?.addEventListener('click', executeInstallersClean);
  document.getElementById('btn-installers-select-all')?.addEventListener('click', () => {
    state.selectedInstallers = new Set(state.installers.map(i => i.path));
    document.querySelectorAll('#tbody-installers .installer-chk').forEach(c => c.checked = true);
  });
  document.getElementById('master-installers-chk')?.addEventListener('change', event => {
    state.selectedInstallers = event.target.checked ? new Set(state.installers.map(i => i.path)) : new Set();
    document.querySelectorAll('#tbody-installers .installer-chk').forEach(c => { c.checked = event.target.checked; });
  });
  // Leftovers events
  document.getElementById('btn-scan-leftovers')?.addEventListener('click', scanLeftovers);
  document.getElementById('btn-execute-leftovers-clean')?.addEventListener('click', executeLeftoversClean);
  document.getElementById('btn-leftovers-select-all')?.addEventListener('click', () => {
    state.selectedLeftovers = new Set(state.leftovers.filter(l => l.risk !== 'MANUAL').map(l => l.id));
    document.querySelectorAll('#tbody-leftovers .leftover-chk:not(:disabled)').forEach(c => c.checked = true);
  });
  document.getElementById('master-leftovers-chk')?.addEventListener('change', event => {
    const enabled = state.leftovers.filter(i => i.risk !== 'MANUAL');
    state.selectedLeftovers = event.target.checked ? new Set(enabled.map(i => i.id)) : new Set();
    document.querySelectorAll('#tbody-leftovers .leftover-chk:not(:disabled)').forEach(c => { c.checked = event.target.checked; });
  });
  document.getElementById('btn-scan-browser-storage')?.addEventListener('click', fetchBrowserStorage);
  document.getElementById('btn-clean-browser-cache')?.addEventListener('click', cleanBrowserCache);
  document.getElementById('btn-scan-smart-downloads')?.addEventListener('click', fetchSmartDownloads);
  document.getElementById('btn-scan-duplicates')?.addEventListener('click', fetchDuplicates);
  document.getElementById('btn-scan-large-files')?.addEventListener('click', fetchLargeFiles);
});
