/* =========================================================
   MacMaid Pro — Developer storage: caches, runtimes,
   environments, tools, SDK inventories
   ========================================================= */

// =========================================================
// Tab 8: Developer Storage Center
// =========================================================

async function scanDeveloperStorage() {
  SoundEffects.playClick();
  const tbody = document.getElementById('tbody-devstorage');
  if (!tbody) return;
  const previousItems = state.developerStorage || [];
  beginCollectionRefresh(tbody, previousItems, 5, t('dev.action_scanning_storage_sub', 'Scanning developer storage…'));
  startLiveProgressPolling(t('dev.action_scanning_storage_sub', 'Scanning developer storage…'));
  try {
    const data = await readAPIResponse(await fetch('/api/developer/storage'));
    const rows = (data.sections || []).flatMap(section => {
      const items = section.items || [];
      if (!items.length) {
        return section.note ? [{ ecosystem: section.title, label: t('dev.inventory_only', 'Inventory status'), path: '—', note: section.note, bytes: 0, humanBytes: '0 B' }] : [];
      }
      return items.map(item => ({ ...item, ecosystem: section.title, note: item.note || section.note || '' }));
    });
    state.developerStorage = rows;
    document.getElementById('devstorage-total-size').textContent = data.humanTotal || formatBytes(data.totalBytes);
    document.getElementById('devstorage-count').textContent = `(${rows.length} ${t('dev.storage_items', 'items')})`;
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('dev.empty_storage_found', 'No developer storage items found.')}</td></tr>`;
      return;
    }
    tbody.innerHTML = rows.map(item => `
      <tr data-item-id="${escapeHtml(item.path || `${item.ecosystem}:${item.label}`)}">
        <td><span class="table-secondary">${escapeHtml(item.ecosystem)}</span></td>
        <td><span class="table-label">${escapeHtml(item.label)}</span></td>
        <td><span class="table-path">${escapeHtml(item.path || '—')}</span></td>
        <td class="table-info-cell">${item.note ? informationButton(item.note, 'mm-table-info') : '—'}</td>
        <td class="table-number">${escapeHtml(item.humanBytes || formatBytes(item.bytes || 0))}</td>
      </tr>
    `).join('');
    highlightCollectionDiff(tbody, previousItems, rows, 5);
  } catch (err) {
    if (!previousItems.length) tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('dev.scan_failed', 'Storage scan failed: ')}${escapeHtml(err.message)}</td></tr>`;
    showOperationOutcome('error', err.message);
  } finally {
    endCollectionRefresh(tbody);
    stopLiveProgressPolling();
  }
}

// Tab 8: Developer Caches (developer-caches)
// =========================================================

async function scanDeveloperCaches() {
  SoundEffects.playClick();
  const tbody = document.getElementById('tbody-devcaches');
  tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${t('dev.action_scanning_caches_sub', 'Scanning developer caches...')}</td></tr>`;
  startLiveProgressPolling();

  try {
    const res = await fetch('/api/developer/caches');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.devCaches = data.items || [];
    state.selectedDevCaches = new Set(state.devCaches.filter(i => i.risk !== 'MANUAL').map(i => i.id));

    document.getElementById('devcaches-total-size').textContent = data.humanTotal || formatBytes(data.totalBytes);
    document.getElementById('devcaches-count').textContent = `(${state.devCaches.length} ${t('dev.caches_title', 'caches')})`;
    const actionableCount = state.devCaches.filter(item => item.risk !== 'MANUAL').length;
    syncMasterCheckbox('master-devcaches-chk', actionableCount, state.selectedDevCaches.size);

    if (state.devCaches.length === 0) {
      tbody.innerHTML = accessNoticeRow(data.issues, 6) + `<tr><td colspan="6" class="empty-state">${t('dev.empty_caches_found', 'No developer caches found.')}</td></tr>`;
      return;
    }

    tbody.innerHTML = accessNoticeRow(data.issues, 6) + state.devCaches.map(item => `
      <tr>
        <td><input type="checkbox" class="devcache-chk" data-id="${item.id}" ${item.risk === 'MANUAL' ? 'disabled' : 'checked'}></td>
        <td><span class="table-label">${escapeHtml(item.label)}</span></td>
        <td><span class="table-path">${escapeHtml(item.path || '—')}</span></td>
        <td><span class="badge-status table-status">${escapeHtml(item.risk)}</span></td>
        <td class="table-info-cell">${informationButton(item.reason, 'mm-table-info')}</td>
        <td class="table-number">${escapeHtml(item.humanBytes)}</td>
      </tr>
    `).join('');

    tbody.querySelectorAll('.devcache-chk').forEach(chk => {
      chk.addEventListener('change', (e) => {
        const id = e.target.dataset.id;
        if (e.target.checked) state.selectedDevCaches.add(id);
        else state.selectedDevCaches.delete(id);
        syncMasterCheckbox('master-devcaches-chk', state.devCaches.filter(item => item.risk !== 'MANUAL').length, state.selectedDevCaches.size);
      });
    });

  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${t('toast.error_prefix', 'Error: ')}${escapeHtml(err.message)}</td></tr>`;
  } finally {
    stopLiveProgressPolling();
  }
}

async function executeDeveloperCachesClean() {
  if (state.selectedDevCaches.size === 0) {
    showToast(t('toast.select_cache_warn', 'Select at least one cache to clean.'), 'warning');
    return;
  }

  const itemIds = Array.from(state.selectedDevCaches);
  const payload = { itemIds };
  await reviewedMutation('/api/developer/caches/clean', payload, {
    confirmText: t('common.clean', 'Clean'),
    buttonId: 'btn-execute-devcaches-clean',
    onSuccess: data => {
      SoundEffects.playSuccess();
      showOutcomeToast(data);
      scanDeveloperCaches();
    },
  });
}

// Developer Item Details & Removal Modal
function showDeveloperItemModal(item, onRefresh) {
  SoundEffects.playClick();
  const title = item.title || `${item.language || ''} ${item.version || ''}`.trim() || t('dev.generic_component', 'Developer Component');

  let statusHtml = '';
  if (item.isActive) {
    statusHtml = `<span class="badge-status badge-green">${t('dev.badge_active', 'ACTIVE')}</span>${informationButton(t('dev.desc_active', 'Currently used as default by shell or system.'))}`;
  } else if (item.removable) {
    statusHtml = `<span class="badge-status badge-yellow">${t('dev.badge_removable', 'Removable')}</span>${informationButton(`${t('dev.desc_removable', 'Can be safely removed via package manager.')} (${item.manager})`)}`;
  } else {
    statusHtml = `<span class="badge-status">${t('dev.badge_protected', 'Protected')}</span>${informationButton(item.protectedReason || t('dev.desc_protected', 'Protected by system.'))}`;
  }

  const html = `
    <div class="component-detail">
      <div class="component-detail-header">
        <strong class="component-detail-title">${escapeHtml(title)}</strong>
        <span class="badge-status badge-cyan">${escapeHtml(item.manager)}</span>
      </div>

      <div class="component-detail-grid">
        <span class="text-muted">${t('common.category', 'Category')}:</span>
        <span class="component-detail-value"><strong>${escapeHtml((item.category || t('dev.title', 'DEVELOPER')).toUpperCase())}</strong></span>

        ${item.version ? `
          <span class="text-muted">${t('settings.version_label', 'Version')}:</span>
          <span class="component-detail-value table-code">${escapeHtml(item.version)}</span>
        ` : ''}

        <span class="text-muted">${t('dev.th_manager', 'Manager')}:</span>
        <span class="component-detail-value">${escapeHtml(item.manager)}</span>

        <span class="text-muted">${t('dev.occupied_space', 'Occupied Space')}:</span>
        <strong class="component-detail-value table-code">${escapeHtml(item.humanBytes || formatBytes(item.bytes || 0))}</strong>

        <span class="text-muted">${t('dev.install_path', 'Install path')}:</span>
        <span class="component-detail-value component-detail-code">${escapeHtml(item.path)}</span>

        <span class="text-muted">${t('dev.th_status', 'Status')}:</span>
        <div class="component-detail-value">${statusHtml}</div>

        ${item.note ? `
          <span class="text-muted">${t('dev.description', 'Description')}:</span>
          <span class="component-detail-value">${informationButton(item.note)}</span>
        ` : ''}
      </div>
    </div>
  `;

  const buttons = [
    { text: t('common.close', 'Close'), class: 'btn-secondary', onClick: hideModal }
  ];

  if (item.removable && !item.isActive) {
    buttons.push({
      text: t('dev.btn_uninstall_item', 'Uninstall This Item'),
      class: 'btn-danger',
      onClick: async () => {
        const payload = { category: item.category, id: item.id };
        await reviewedMutation('/api/developer/remove', payload, {
          confirmText: t('dev.btn_uninstall_manager', 'Uninstall with Manager'),
          progressLabel: `${title} ${t('hud.in_progress', 'removing…')}`,
          onSuccess: async resData => {
            SoundEffects.playSuccess();
            showOutcomeToast(resData, `${title} ${t('toast.uninstalled', 'uninstalled')} · `);
            if (typeof onRefresh === 'function') await onRefresh();
          },
          onError: e => {
            showToast(`${t('toast.uninstall_failed', 'Uninstall failed: ')}${e.message}`, 'error'); showOperationOutcome('error', e.message);
          },
        });
      }
    });
  }

  showModal(`${t('dev.modal_comp_detail', 'Component Details: ')}${title}`, html, buttons);
}

// Developer Runtimes & Languages
async function scanDeveloperRuntimes() {
  SoundEffects.playClick();
  const tbody = document.getElementById('tbody-devruntimes');
  const previousItems = state.developerRuntimes || [];
  beginCollectionRefresh(tbody, previousItems, 6, t('dev.action_scanning_runtimes', 'Scanning runtimes...'));
  startLiveProgressPolling(t('dev.action_scanning_runtimes', 'Scanning runtimes…'));

  try {
    const res = await fetch('/api/developer/runtimes');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const items = data.items || [];
    const changed = collectionFingerprint(previousItems) !== collectionFingerprint(items);
    state.developerRuntimes = items;
    document.getElementById('devruntimes-total-size').textContent = data.humanTotal || formatBytes(data.totalBytes);
    document.getElementById('devruntimes-count').textContent = `(${items.length} ${t('dev.zero_runtimes', 'runtimes detected')})`;

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${t('dev.empty_runtimes_found', 'No installed runtimes found.')}</td></tr>`;
      return;
    }

    if (!changed && previousItems.length) return;
    tbody.innerHTML = items.map((item, idx) => `
      <tr class="clickable-row" data-idx="${idx}" data-item-id="${escapeHtml(item.id || item.path)}" title="${t('dev.row_tip_detail', 'Click to view details and remove')}">
        <td><span class="table-label">${escapeHtml(item.title || item.language)}</span></td>
        <td><span class="table-code">${escapeHtml(item.version)}</span></td>
        <td><span class="table-secondary">${escapeHtml(item.manager)}</span></td>
        <td><span class="table-path">${escapeHtml(item.path)}</span></td>
        <td><span class="badge-status table-status ${item.isActive ? 'badge-green' : (item.removable ? 'badge-yellow' : '')}">${item.isActive ? t('dev.badge_active', 'ACTIVE') : (item.removable ? t('dev.badge_removable', 'Removable') : t('dev.badge_protected', 'Protected'))}</span></td>
        <td class="table-number">${escapeHtml(item.humanBytes)}</td>
      </tr>
    `).join('');

    tbody.querySelectorAll('tr.clickable-row').forEach(row => {
      row.addEventListener('click', () => {
        const idx = parseInt(row.dataset.idx, 10);
        const item = state.developerRuntimes[idx];
        if (item) showDeveloperItemModal(item, scanDeveloperRuntimes);
      });
    });
    highlightCollectionDiff(tbody, previousItems, items, 6);
  } catch (err) {
    if (!previousItems.length) tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${t('toast.error_prefix', 'Error: ')}${escapeHtml(err.message)}</td></tr>`;
    showOperationOutcome('error', err.message);
  } finally {
    endCollectionRefresh(tbody);
    stopLiveProgressPolling();
  }
}

// Developer Environments
async function scanDeveloperEnvironments() {
  SoundEffects.playClick();
  const tbody = document.getElementById('tbody-devenvironments');
  const previousItems = state.developerEnvironments || [];
  beginCollectionRefresh(tbody, previousItems, 5, t('dev.action_scanning_env', 'Scanning virtual environments...'));
  startLiveProgressPolling(t('dev.action_scanning_env', 'Scanning virtual environments…'));

  try {
    const res = await fetch('/api/developer/environments');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const items = data.items || [];
    const changed = collectionFingerprint(previousItems) !== collectionFingerprint(items);
    state.developerEnvironments = items;
    document.getElementById('devenvironments-total-size').textContent = data.humanTotal || formatBytes(data.totalBytes);
    document.getElementById('devenvironments-count').textContent = t('dev.environment_count', '{count} environments').replace('{count}', String(items.length));

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('dev.empty_venvs_found', 'No virtual environments found.')}</td></tr>`;
      return;
    }

    if (!changed && previousItems.length) return;
    tbody.innerHTML = items.map((item, idx) => `
      <tr class="clickable-row" data-idx="${idx}" data-item-id="${escapeHtml(item.id || item.path)}" title="${t('dev.row_tip_detail', 'Click to view details and remove')}">
        <td><span class="table-label">${escapeHtml(item.title)}</span></td>
        <td><span class="table-secondary">${escapeHtml(item.manager)}</span></td>
        <td><span class="table-path">${escapeHtml(item.path)}</span></td>
        <td class="table-info-cell">${item.note ? informationButton(item.note, 'mm-table-info') : '—'}</td>
        <td class="table-number">${escapeHtml(item.humanBytes)}</td>
      </tr>
    `).join('');

    tbody.querySelectorAll('tr.clickable-row').forEach(row => {
      row.addEventListener('click', () => {
        const idx = parseInt(row.dataset.idx, 10);
        const item = state.developerEnvironments[idx];
        if (item) showDeveloperItemModal(item, scanDeveloperEnvironments);
      });
    });
    highlightCollectionDiff(tbody, previousItems, items, 5);
  } catch (err) {
    if (!previousItems.length) tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('toast.error_prefix', 'Error: ')}${escapeHtml(err.message)}</td></tr>`;
    showOperationOutcome('error', err.message);
  } finally {
    endCollectionRefresh(tbody);
    stopLiveProgressPolling();
  }
}

// Developer Global CLI Tools
async function scanDeveloperTools() {
  SoundEffects.playClick();
  const tbody = document.getElementById('tbody-devtools');
  const previousItems = state.developerTools || [];
  beginCollectionRefresh(tbody, previousItems, 5, t('dev.action_scanning_tools', 'Scanning global tools...'));
  startLiveProgressPolling(t('dev.action_scanning_tools', 'Scanning global tools…'));

  try {
    const res = await fetch('/api/developer/tools');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const items = data.items || [];
    const changed = collectionFingerprint(previousItems) !== collectionFingerprint(items);
    state.developerTools = items;
    document.getElementById('devtools-total-size').textContent = data.humanTotal || formatBytes(data.totalBytes);
    document.getElementById('devtools-count').textContent = `(${items.length} ${t('dev.zero_tools', 'tools detected')})`;

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('dev.empty_tools_found', 'No global CLI tools found.')}</td></tr>`;
      return;
    }

    if (!changed && previousItems.length) {
      showToast(t('toast.no_cli_changes', 'No changes in global CLI tools.'), 'info');
      return;
    }

    tbody.innerHTML = items.map((item, idx) => `
      <tr class="clickable-row" data-idx="${idx}" data-item-id="${escapeHtml(item.id || item.path)}" title="${t('dev.row_tip_detail', 'Click to view details and remove')}">
        <td><span class="table-label">${escapeHtml(item.title)}</span></td>
        <td><span class="table-secondary">${escapeHtml(item.manager)}</span></td>
        <td><span class="table-path">${escapeHtml(item.path)}</span></td>
        <td class="table-info-cell">${item.note ? informationButton(item.note, 'mm-table-info') : '—'}</td>
        <td class="table-number">${escapeHtml(item.humanBytes)}</td>
      </tr>
    `).join('');

    tbody.querySelectorAll('tr.clickable-row').forEach(row => {
      row.addEventListener('click', () => {
        const idx = parseInt(row.dataset.idx, 10);
        const item = state.developerTools[idx];
        if (item) showDeveloperItemModal(item, scanDeveloperTools);
      });
    });
    highlightCollectionDiff(tbody, previousItems, items, 5);
  } catch (err) {
    if (!previousItems.length) tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('toast.error_prefix', 'Error: ')}${escapeHtml(err.message)}</td></tr>`;
    showOperationOutcome('error', err.message);
  } finally {
    endCollectionRefresh(tbody);
    stopLiveProgressPolling();
  }
}

// Developer SDKs & Simulators
async function scanDeveloperSDKs() {
  SoundEffects.playClick();
  const tbody = document.getElementById('tbody-devsdks');
  const previousItems = state.developerSDKs || [];
  beginCollectionRefresh(tbody, previousItems, 5, t('dev.action_scanning_sdks', 'Scanning SDKs & simulators...'));
  startLiveProgressPolling(t('dev.action_scanning_sdks', 'Scanning SDKs & simulators…'));

  try {
    const res = await fetch('/api/developer/sdks');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const items = data.items || [];
    const changed = collectionFingerprint(previousItems) !== collectionFingerprint(items);
    state.developerSDKs = items;
    document.getElementById('devsdks-total-size').textContent = data.humanTotal || formatBytes(data.totalBytes);
    document.getElementById('devsdks-count').textContent = `(${items.length} ${t('dev.zero_sdks', 'SDKs/Simulators detected')})`;

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('dev.empty_sdks_found', 'No SDKs or simulators found.')}</td></tr>`;
      return;
    }

    if (!changed && previousItems.length) return;
    tbody.innerHTML = items.map((item, idx) => `
      <tr class="clickable-row" data-idx="${idx}" data-item-id="${escapeHtml(item.id || item.path)}" title="${t('dev.row_tip_detail', 'Click to view details and remove')}">
        <td><span class="table-label">${escapeHtml(item.title)}</span></td>
        <td><span class="table-secondary">${escapeHtml(item.manager)}</span></td>
        <td><span class="table-path">${escapeHtml(item.path)}</span></td>
        <td class="table-info-cell">${item.note ? informationButton(item.note, 'mm-table-info') : '—'}</td>
        <td class="table-number">${escapeHtml(item.humanBytes)}</td>
      </tr>
    `).join('');

    tbody.querySelectorAll('tr.clickable-row').forEach(row => {
      row.addEventListener('click', () => {
        const idx = parseInt(row.dataset.idx, 10);
        const item = state.developerSDKs[idx];
        if (item) showDeveloperItemModal(item, scanDeveloperSDKs);
      });
    });
    highlightCollectionDiff(tbody, previousItems, items, 5);
  } catch (err) {
    if (!previousItems.length) tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('toast.error_prefix', 'Error: ')}${escapeHtml(err.message)}</td></tr>`;
    showOperationOutcome('error', err.message);
  } finally {
    endCollectionRefresh(tbody);
    stopLiveProgressPolling();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  // Developer tools events
  document.getElementById('btn-scan-devstorage')?.addEventListener('click', scanDeveloperStorage);
  document.getElementById('btn-scan-devcaches')?.addEventListener('click', scanDeveloperCaches);
  document.getElementById('btn-execute-devcaches-clean')?.addEventListener('click', executeDeveloperCachesClean);
  document.getElementById('btn-devcaches-select-all')?.addEventListener('click', () => {
    state.selectedDevCaches = new Set(state.devCaches.filter(i => i.risk !== 'MANUAL').map(i => i.id));
    document.querySelectorAll('#tbody-devcaches .devcache-chk:not(:disabled)').forEach(c => c.checked = true);
  });
  document.getElementById('master-devcaches-chk')?.addEventListener('change', event => {
    const enabled = state.devCaches.filter(i => i.risk !== 'MANUAL');
    state.selectedDevCaches = event.target.checked ? new Set(enabled.map(i => i.id)) : new Set();
    document.querySelectorAll('#tbody-devcaches .devcache-chk:not(:disabled)').forEach(c => { c.checked = event.target.checked; });
  });
  document.getElementById('btn-scan-runtimes')?.addEventListener('click', scanDeveloperRuntimes);
  document.getElementById('btn-scan-environments')?.addEventListener('click', scanDeveloperEnvironments);
  document.getElementById('btn-scan-devtools')?.addEventListener('click', scanDeveloperTools);
  document.getElementById('btn-scan-sdks')?.addEventListener('click', scanDeveloperSDKs);
});
