/* =========================================================
   MacMaid Pro — System status: dashboard metrics, snapshots,
   optimization tasks, doctor report, operation history
   ========================================================= */

// =========================================================
// Tab 1: Dashboard Status & Metrics
// =========================================================

async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) return;
    const data = await res.json();
    renderStatus(data);
  } catch (err) {}
}

function syncStatusPolling() {
  // /api/status samples system metrics; poll only while the dashboard is visible.
  if (state.activeTab === 'dashboard') {
    fetchStatus();
    if (!state.refreshTimer) state.refreshTimer = setInterval(fetchStatus, state.refreshInterval);
  } else if (state.refreshTimer) {
    clearInterval(state.refreshTimer);
    state.refreshTimer = null;
  }
}

function renderStatus(data) {
  const { metrics, health, uptime, loadAverage, thermal, battery, processes } = data;

  const healthGrid = document.getElementById('health-indicators');
  if (healthGrid && Array.isArray(health)) {
    const stateLabels = { normal: t('status.state_normal', 'NORMAL'), warning: t('status.state_warning', 'WARNING'), critical: t('status.state_critical', 'CRITICAL'), unknown: t('status.state_unknown', 'UNKNOWN'), not_applicable: t('status.state_na', 'N/A') };
    healthGrid.innerHTML = health.map(item => `
      <article class="health-indicator health-${escapeHtml(item.state)}">
        <div class="health-indicator-head">
          <strong>${escapeHtml(item.label)}</strong>
          <span class="health-state">${escapeHtml(stateLabels[item.state] || t('status.state_unknown', 'UNKNOWN'))}</span>
        </div>
        <div class="health-value">${escapeHtml(item.value)}</div>
        <p>${escapeHtml(item.detail)}</p>
        ${item.recommendation ? `<p class="health-recommendation">${t('status.recommendation', 'Recommendation: ')}${escapeHtml(item.recommendation)}</p>` : ''}
        <small>${t('status.measured_at', 'Measured: ')}${escapeHtml(item.measuredAt)}</small>
      </article>`).join('');
  }

  if (metrics) {
    const cpuPct = metrics.cpuPercent.toFixed(1);
    document.getElementById('header-cpu-val').textContent = `${cpuPct}%`;
    document.getElementById('dash-cpu-val').textContent = `${cpuPct}%`;
    setGauge('gauge-cpu-circle', metrics.cpuPercent);

    const ramUsedGB = (metrics.memoryUsed / (1024 ** 3)).toFixed(1);
    const ramTotalGB = (metrics.memoryTotal / (1024 ** 3)).toFixed(1);
    const ramPct = ((metrics.memoryUsed / metrics.memoryTotal) * 100) || 0;
    document.getElementById('header-ram-val').textContent = `${ramUsedGB} GB`;
    document.getElementById('dash-ram-val').textContent = `${ramPct.toFixed(0)}%`;
    document.getElementById('dash-ram-used-val').textContent = `${ramUsedGB} GB`;
    document.getElementById('dash-ram-total-val').textContent = `${ramTotalGB} GB`;
    const ramFreeGB = Math.max(0, (metrics.memoryTotal - metrics.memoryUsed) / (1024 ** 3)).toFixed(1);
    document.getElementById('dash-ram-free-val').textContent = `${ramFreeGB} GB`;
    setGauge('gauge-ram-circle', ramPct);

    const diskUsedGB = (metrics.diskUsed / (1024 ** 3)).toFixed(1);
    const diskTotalGB = (metrics.diskTotal / (1024 ** 3)).toFixed(1);
    const diskFreeGB = Math.max(0, Number(metrics.diskFree ?? (metrics.diskTotal - metrics.diskUsed)) / (1024 ** 3)).toFixed(1);
    const diskPct = Number(metrics.diskPercent ?? ((metrics.diskUsed / metrics.diskTotal) * 100)) || 0;
    document.getElementById('header-disk-val').textContent = `${diskFreeGB} GB ${t('sidebar.free', 'free')}`;
    document.getElementById('dash-disk-percent-val').textContent = `${diskPct.toFixed(0)}%`;
    document.getElementById('dash-disk-free-val').textContent = `${diskFreeGB} GB`;
    document.getElementById('dash-disk-used-val').textContent = `${diskUsedGB} GB`;
    document.getElementById('dash-disk-total-val').textContent = `${diskTotalGB} GB`;
    setGauge('gauge-disk-circle', diskPct);

    document.getElementById('dash-net-down').textContent = `${formatBytes(metrics.networkDownPerSecond)}/s`;
    document.getElementById('dash-net-up').textContent = `${formatBytes(metrics.networkUpPerSecond)}/s`;
  }

  if (thermal) document.getElementById('dash-thermal-val').textContent = thermal;
  if (loadAverage && loadAverage.length) {
    document.getElementById('dash-load-val').textContent = loadAverage.map(n => n.toFixed(2)).join(', ');
  }
  if (uptime) {
    const hours = Math.floor(uptime / 3600);
    const mins = Math.floor((uptime % 3600) / 60);
    document.getElementById('dash-uptime-val').textContent = `${hours} saat ${mins} dk`;
  }

  if (battery && battery.percent !== null && battery.percent !== undefined) {
    document.getElementById('dash-batt-pct').textContent = `${battery.percent}%`;
    document.getElementById('dash-batt-bar').style.width = `${battery.percent}%`;
    document.getElementById('dash-batt-state').textContent = battery.charging ? t('status.charging', 'Charging ⚡') : t('status.on_battery', 'On Battery');
    document.getElementById('dash-batt-cycles').textContent = battery.cycleCount ? `${battery.cycleCount} ${t('status.cycles', 'Cycles')}` : t('status.state_normal', 'Normal');
  } else {
    const batteryHealth = Array.isArray(health) ? health.find(item => item.id === 'battery') : null;
    const absent = batteryHealth?.state === 'not_applicable';
    document.getElementById('dash-batt-pct').textContent = absent ? 'Pil Yok' : 'Bilinmiyor';
    document.getElementById('dash-batt-bar').style.width = '0%';
    document.getElementById('dash-batt-state').textContent = absent ? t('status.desktop_ac', 'Desktop / AC') : t('status.batt_unavailable', 'Battery data unavailable');
    document.getElementById('dash-batt-cycles').textContent = absent ? 'Uygulanamaz' : 'Bilinmiyor';
  }

  if (processes && processes.length) {
    const tbody = document.getElementById('tbody-top-processes');
    tbody.innerHTML = processes.map(p => `
      <tr>
        <td><strong>${escapeHtml(p.command)}</strong></td>
        <td><span class="version-tag">${p.pid}</span></td>
        <td><span class="highlight-cyan">${p.cpu.toFixed(1)}%</span></td>
        <td>${p.memory.toFixed(1)}%</td>
      </tr>
    `).join('');
  }
}

// =========================================================
// More Tools: Snapshots
// =========================================================

async function fetchSnapshotsList() {
  SoundEffects.playClick();
  const box = document.getElementById('snapshots-list-box');
  box.textContent = t('more.action_getting_snapshots', 'Retrieving snapshot list...');
  startLiveProgressPolling();

  try {
    const res = await fetch('/api/snapshots');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    box.textContent = data.raw || t('more.empty_snapshots_found', 'No snapshots found.');
  } catch (err) {
    box.textContent = `${t('toast.error_prefix', 'Error: ')}${err.message}`;
  } finally {
    stopLiveProgressPolling();
  }
}

async function executeSnapshotThin() {
  const pill = document.querySelector('.snapshot-thin-pill.active');
  const targetGB = parseInt(pill ? pill.dataset.gb : '10', 10);
  const payload = { targetGB };
  await reviewedMutation('/api/snapshots/thin', payload, {
    confirmText: t('more.btn_start_thinning', 'Start Thinning'),
    onSuccess: data => {
      SoundEffects.playSuccess();
      const observed = data.observedFreeBytesDelta === null || data.observedFreeBytesDelta === undefined
        ? t('outcome.diff_unmeasured', 'observed difference unmeasured')
        : `${t('more.observed_free_space', 'observed free space ')}${formatBytes(Math.abs(data.observedFreeBytesDelta))} ${data.observedFreeBytesDelta >= 0 ? t('common.increased', 'increased') : t('common.decreased', 'decreased')}`;
      showToast(`${t('toast.snapshot_thinned', 'Snapshot thinning request completed · actual manager impact unknown · ')}${observed}${t('outcome.not_strictly_macmaid', ' (not strictly attributable to MacMaid)')}`, 'success');
      fetchSnapshotsList();
    },
  });
}

// =========================================================
// Tab 10: Mac Optimization (optimize)
// =========================================================

async function fetchOptimizationTasks() {
  const container = document.getElementById('optimize-tasks-grid');
  try {
    const res = await fetch('/api/optimize');
    const data = await readAPIResponse(res);
    renderOptimizationTasks(data.tasks || [], data.reason || t('optimize.empty_tasks', 'No available optimization tasks found.'));
  } catch (err) {
    container.innerHTML = `<div class="empty-state">${t('optimize.load_failed', 'Failed to load tasks: ')}${escapeHtml(err.message)}</div>`;
  }
}

function renderOptimizationTasks(tasks, unavailableReason = t('optimize.empty_tasks', 'No available optimization tasks found.')) {
  const container = document.getElementById('optimize-tasks-grid');
  if (tasks.length === 0) {
    container.innerHTML = `<div class="empty-state">${escapeHtml(unavailableReason)}</div>`;
    return;
  }

  container.innerHTML = tasks.map(task => `
    <div class="task-card" data-task-id="${task.id}">
      <div class="task-head">
        <div class="task-icon">
          ${sfSymbol('bolt')}
        </div>
        <div class="task-info">
          <h4>${escapeHtml(task.title)}</h4>
          <p>${escapeHtml(task.subtitle)}</p>
        </div>
      </div>
      <div class="task-footer">
        <span class="badge-status ${task.risk === 'SAFE' ? 'live-status' : ''}">${escapeHtml(task.risk)}</span>
        <button class="btn btn-secondary btn-sm btn-run-task" data-id="${task.id}">${t('optimize.btn_run', 'Run')}</button>
      </div>
    </div>
  `).join('');

  container.querySelectorAll('.btn-run-task').forEach(btn => {
    btn.addEventListener('click', () => runSingleOptimizeTask(btn.dataset.id));
  });
}

async function runSingleOptimizeTask(taskId) {
  SoundEffects.playClick();
  const payload = { taskId };
  await reviewedMutation('/api/optimize/run', payload, {
    confirmText: t('optimize.btn_run_task', 'Run Task'),
    onSuccess: data => {
      SoundEffects.playSuccess(); showToast(`${t('toast.task_completed', 'Task completed: ')}${data.message || t('hud.ok', 'Successful')}`, 'success');
    },
  });
}

// =========================================================
// Tab 11: Doctor (doctor)
// =========================================================

async function fetchDoctorReport() {
  SoundEffects.playClick();
  startLiveProgressPolling();
  try {
    const res = await fetch('/api/doctor');
    const data = await readAPIResponse(res);

    document.getElementById('doc-macos').textContent = `${data.macosVersion || 'macOS'} (${data.buildVersion || ''})`;
    document.getElementById('doc-arch').textContent = data.architecture || 'arm64 (Apple Silicon)';
    document.getElementById('doc-sip').textContent = data.sipStatus || 'Etkin (Tam Koruma)';
    document.getElementById('doc-disk').textContent = data.diskRoot || '/';

    if (data.probes && data.probes.length) {
      document.getElementById('doc-probes-list').innerHTML = data.probes.map(p => `
        <div class="probe-item ${p.ok ? 'ok' : 'limited'}" style="display:flex; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid rgba(255,255,255,0.03);">
          <span class="badge-status ${p.ok ? 'live-status' : ''}">${p.ok ? 'OK' : 'SINIRLI'}</span>
          <span style="font-family: var(--font-mono); font-size:12px;">${escapeHtml(p.path)}</span>
        </div>
      `).join('');
    }
  } catch (e) {
    showToast(`${t('toast.doctor_failed', 'Failed to obtain doctor report: ')}${e.message}`, 'error');
  } finally {
    stopLiveProgressPolling();
  }
}

// =========================================================
// Tab 12: History (history)
// =========================================================

async function fetchHistory() {
  try {
    const res = await fetch('/api/history');
    if (!res.ok) return;
    const data = await res.json();

    document.getElementById('hist-total-freed').textContent = data.humanTotalEstimatedReclaimed || '0 B';
    document.getElementById('hist-total-items').textContent = data.totalOperations || '0';
    document.getElementById('hist-last-run').textContent = data.lastOperationDate || t('more.hist_never', 'Never');

    const tbody = document.getElementById('tbody-history');
    if (!data.entries || data.entries.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('more.empty_history_found', 'No recorded history operations found.')}</td></tr>`;
      return;
    }

    tbody.innerHTML = data.entries.slice(0, 60).map((e, index) => {
      const restorable = Boolean(e.restorable && e.trash_path && e.operation_id);
      const restoreStatus = e.restoreStatus || (restorable ? 'Restorable' : 'Not Restorable');
      const actions = restorable
        ? `<div class="row-actions"><button class="mini-btn recovery-restore" data-index="${index}" data-copy="false">Restore</button><button class="mini-btn recovery-restore" data-index="${index}" data-copy="true">Restore as copy</button></div>`
        : `<span class="text-muted">${escapeHtml(restoreStatus)}</span>`;
      return `
      <tr>
        <td>${escapeHtml(e.date || '')}</td>
        <td><span class="badge-status">${escapeHtml(e.action || 'clean')}</span></td>
        <td><strong>${escapeHtml(e.label || e.category || t('more.op_summary', 'Operation Summary'))}</strong><br><small>${escapeHtml(restoreStatus)}</small></td>
        <td style="font-family: var(--font-mono);">${formatBytes(e.estimatedReclaimedBytes || 0)}</td>
        <td><span class="highlight-green">${escapeHtml(e.result || 'success')}</span>${actions}</td>
      </tr>`;
    }).join('');
    tbody.querySelectorAll('.recovery-restore').forEach(button => {
      button.addEventListener('click', () => restoreHistoryEntry(data.entries[Number(button.dataset.index)], button.dataset.copy === 'true'));
    });
   } catch (e) {}
}

async function restoreHistoryEntry(entry, copy) {
  if (!entry || !entry.operation_id || !entry.trash_path) return;
  const action = copy ? 'Restore as copy' : 'Restore';
  if (!confirm(`${action} this item?\n\n${entry.original_path || ''}`)) return;
  try {
    const res = await fetch('/api/recovery/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ operationId: entry.operation_id, trashPath: entry.trash_path, copy })
    });
    const result = await readAPIResponse(res);
    showToast(`Restored: ${result.restored_path}`, 'success');
    fetchHistory();
  } catch (err) {
    showToast(`Restore failed: ${err.message}`, 'error');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  // Dashboard quick jump to Clean
  document.getElementById('dash-quick-scan-btn')?.addEventListener('click', () => {
    document.querySelector('.nav-item[data-tab="cleaner"]')?.click();
  });
  // Snapshot events
  document.getElementById('btn-refresh-snapshots')?.addEventListener('click', fetchSnapshotsList);
  document.getElementById('btn-execute-snapshot-thin')?.addEventListener('click', executeSnapshotThin);
  // Snapshot thin pills
  document.querySelectorAll('.snapshot-thin-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      SoundEffects.playClick();
      document.querySelectorAll('.snapshot-thin-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
    });
  });
  // Optimization events
  document.getElementById('btn-run-all-optimize')?.addEventListener('click', async () => {
    SoundEffects.playClick();
    const payload = {};
    await reviewedMutation('/api/optimize/run-all', payload, {
      confirmText: t('optimize.btn_run_all', 'Run All'),
      onSuccess: result => {
        SoundEffects.playSuccess(); showToast(`${result.executed}/${result.total} ${t('toast.tasks_completed_count', 'maintenance tasks completed.')}`, 'success');
      },
    });
  });
  // Doctor & Settings
  document.getElementById('btn-refresh-doctor')?.addEventListener('click', fetchDoctorReport);
});
