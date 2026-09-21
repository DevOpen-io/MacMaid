/* =========================================================
   MacMaid Pro — Smart Clean feature: scan, selection, review
   ========================================================= */

// =========================================================
// Tab 2: Smart Clean (scan & clean)
// =========================================================

async function runSmartScan() {
  SoundEffects.playClick();
  const profilePill = document.querySelector('.profile-pill.active');
  const profile = profilePill ? profilePill.dataset.profile : 'safe';
  const includeTrash = document.getElementById('chk-trash').checked;
  const includeTemp = document.getElementById('chk-temp').checked;

  const resultsBox = document.getElementById('scan-results-box');
  const btnScan = document.getElementById('btn-start-scan');

  resultsBox.classList.add('hidden');
  btnScan.disabled = true;
  btnScan.style.opacity = '0.6';

  startLiveProgressPolling();

  try {
    const url = `/api/scan?profile=${encodeURIComponent(profile)}&trash=${includeTrash}&systemTemp=${includeTemp}`;
    const res = await fetch(url);

    const data = await readAPIResponse(res);
    state.currentScan = data;
    state.selectedCleanItems = new Set(data.isComplete ? data.items.filter(i => i.risk !== 'MANUAL').map(i => i.id) : []);

    resultsBox.classList.remove('hidden');
    renderScanResults(data);
    if (data.isComplete) {
      SoundEffects.playSuccess();
      showToast(`${t('toast.scan_completed', 'Scan completed: ')}${data.items.length} ${t('toast.items_found', 'items found')} (${data.humanTotal})`, 'success');
    } else {
      const issues = (data.issues || []).slice(0, 2).join(' ');
      showToast(`${t('clean.title', 'Scan')} ${data.status}: ${t('toast.results_incomplete', 'results incomplete, cleanup prevented.')} ${issues || (data.notes || []).join(' ')}`, 'warning');
    }
  } catch (err) {
    showToast(`${t('toast.scan_error', 'Scan error: ')}${err.message}`, 'error');
  } finally {
    stopLiveProgressPolling();
    btnScan.disabled = false;
    btnScan.style.opacity = '1';
  }
}

function renderScanResults(scanData) {
  document.getElementById('res-total-bytes').textContent = scanData.humanTotal || formatBytes(scanData.totalBytes);
  document.getElementById('res-total-items').textContent = scanData.items.length;
  updateSelectedCleanStats();
  const actionableCount = cleanActionableItems().length;
  syncMasterCheckbox('master-clean-chk', actionableCount, state.selectedCleanItems.size);

  const tbody = document.getElementById('tbody-clean-items');
  if (!scanData.items || scanData.items.length === 0) {
    const message = scanData.isComplete ? t('clean.empty_clean', 'No cleanup items found.') : `${t('clean.title', 'Clean')} ${escapeHtml(scanData.status || '')} · ${t('toast.results_incomplete', 'results incomplete')}`;
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${message}</td></tr>`;
    return;
  }

  tbody.innerHTML = scanData.items.map(item => {
    const isChecked = state.selectedCleanItems.has(item.id) ? 'checked' : '';
    const isDisabled = item.risk === 'MANUAL' || !scanData.isComplete ? 'disabled' : '';
    const riskBadgeClass = item.risk === 'SAFE' ? 'safe-dot' : (item.risk === 'MODERATE' ? 'deep-dot' : 'agg-dot');
    return `
      <tr data-item-id="${item.id}">
        <td><input type="checkbox" class="item-chk" data-id="${item.id}" ${isChecked} ${isDisabled}></td>
        <td>
          <div class="table-label">${escapeHtml(item.label)}</div>
          <div class="table-tertiary">${escapeHtml(item.category)}</div>
        </td>
        <td><span class="table-path">${escapeHtml(item.path || '—')}</span></td>
        <td><span class="badge-status table-status"><span class="pill-dot ${riskBadgeClass}"></span>${escapeHtml(item.risk)}</span></td>
        <td><span class="table-secondary">${escapeHtml(item.reason)}</span></td>
        <td class="table-number">${escapeHtml(item.humanBytes)}</td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('.item-chk').forEach(chk => {
    chk.addEventListener('change', (e) => {
      const id = e.target.dataset.id;
      if (e.target.checked) state.selectedCleanItems.add(id);
      else state.selectedCleanItems.delete(id);
      updateSelectedCleanStats();
    });
  });
}

function cleanActionableItems() {
  if (!state.currentScan?.isComplete) return [];
  return state.currentScan.items.filter(item => item.risk !== 'MANUAL');
}

function setCleanSelection(selectAll) {
  const actionable = cleanActionableItems();
  state.selectedCleanItems = selectAll ? new Set(actionable.map(item => item.id)) : new Set();
  if (state.currentScan) renderScanResults(state.currentScan);
  return state.currentScan?.isComplete === true;
}

function updateSelectedCleanStats() {
  if (!state.currentScan) return;
  const actionable = cleanActionableItems();
  const actionableIds = new Set(actionable.map(item => item.id));
  state.selectedCleanItems = new Set([...state.selectedCleanItems].filter(id => actionableIds.has(id)));
  const selectedBytes = state.currentScan.items.reduce((total, item) => (
    state.selectedCleanItems.has(item.id) ? total + Number(item.estimatedBytes || 0) : total
  ), 0);
  document.getElementById('res-selected-bytes').textContent = formatBytes(selectedBytes);
  syncMasterCheckbox('master-clean-chk', actionable.length, state.selectedCleanItems.size);
  const controlsDisabled = actionable.length === 0;
  document.getElementById('btn-select-all').disabled = controlsDisabled;
  document.getElementById('btn-deselect-all').disabled = controlsDisabled;
  document.getElementById('btn-execute-clean').disabled = controlsDisabled;
}

async function executeClean() {
  if (state.currentScan && !state.currentScan.isComplete) {
    showToast(t('toast.partial_scan_warn', 'Partial or cancelled scans cannot be cleaned. Please run a fresh, full scan.'), 'warning');
    return;
  }
  if (!state.currentScan || state.selectedCleanItems.size === 0) {
    showToast(t('toast.select_at_least_one', 'Select at least one item to clean.'), 'warning');
    return;
  }

  const isDryRun = document.getElementById('chk-dryrun').checked;
  const itemsToClean = state.currentScan.items.filter(i => state.selectedCleanItems.has(i.id));
  const payload = { itemIds: itemsToClean.map(i => i.id), dryRun: isDryRun };
  await reviewedMutation('/api/clean', payload, {
    confirmText: isDryRun ? t('clean.btn_run_sim', 'Run Simulation') : t('clean.btn_clean_reclaim', 'Clean & Reclaim Space'),
    progressLabel: isDryRun ? t('clean.action_simulating', 'Simulating cleanup…') : t('clean.action_cleaning_items', 'Cleaning selected items…'),
    buttonId: 'btn-execute-clean',
    onAuthorized: btn => { if (btn) btn.innerHTML = `<span>${t('common.cleaning', 'Cleaning...')}</span>`; },
    onSuccess: result => {
      SoundEffects.playSuccess();
      showOutcomeToast(result);
      document.getElementById('scan-results-box').classList.add('hidden');
      fetchStatus();
    },
    onError: err => {
      showOperationOutcome('error', err.message);
      showToast(`${t('toast.error_prefix', 'Error: ')}${err.message}`, 'error');
    },
    onFinally: btn => { if (btn) btn.innerHTML = `<span>${t('clean.btn_execute', 'Start Cleaning')}</span>`; },
  });
}

document.addEventListener('DOMContentLoaded', () => {
  // Profile pills in Smart Clean
  document.querySelectorAll('.profile-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      SoundEffects.playClick();
      document.querySelectorAll('.profile-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      const context = document.getElementById('clean-profile-context');
      if (context) {
        const key = `clean.profile_${pill.dataset.profile === 'developer' ? 'developer' : pill.dataset.profile}_context`;
        context.dataset.i18n = key;
        context.textContent = t(key, '');
      }
    });
  });
  // Cleaner tab events
  document.getElementById('btn-start-scan')?.addEventListener('click', runSmartScan);
  document.getElementById('btn-execute-clean')?.addEventListener('click', executeClean);
  document.getElementById('btn-select-all')?.addEventListener('click', () => {
    if (!setCleanSelection(true)) {
      showToast(t('toast.partial_scan_warn', 'Partial or cancelled scans cannot be cleaned. Please run a fresh, full scan.'), 'warning');
    }
  });
  document.getElementById('btn-deselect-all')?.addEventListener('click', () => { setCleanSelection(false); });
  document.getElementById('master-clean-chk')?.addEventListener('change', event => {
    if (!setCleanSelection(event.target.checked)) {
      showToast(t('toast.partial_scan_warn', 'Partial or cancelled scans cannot be cleaned. Please run a fresh, full scan.'), 'warning');
    }
  });
});
