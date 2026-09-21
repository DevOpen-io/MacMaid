/* =========================================================
   MacMaid Pro — Live progress engine: polling, HUD,
   in-page progress rendering, cancellation, outcomes
   ========================================================= */

// =========================================================
// CONTINUOUS IN-PAGE LIVE PROGRESS FEEDBACK ENGINE
// =========================================================

function startLiveProgressPolling(label = t('hud.starting', 'Starting operation…')) {
  state.isOperationRunning = true;
  state.operationObservedActive = false;
  state.operationStartedAt = Date.now();
  const hud = document.getElementById('global-operation-hud');
  hud?.classList.remove('hidden', 'is-success', 'is-error');
  if (hud) {
    hud.removeAttribute('tabindex');
    hud.setAttribute('role', 'status');
    hud.onclick = null;
    hud.onkeydown = null;
  }
  document.getElementById('global-operation-spinner')?.classList.remove('hidden');
  const title = document.getElementById('global-operation-title');
  const detail = document.getElementById('global-operation-detail');
  const percent = document.getElementById('global-operation-percent');
  const phase = document.getElementById('global-operation-phase');
  const count = document.getElementById('global-operation-count');
  const elapsed = document.getElementById('global-operation-elapsed');
  const bar = document.getElementById('global-operation-bar');
  const health = hud?.querySelector('.operation-health span');
  if (health) health.textContent = t('hud.active_healthy', 'Active · responding normally');
  if (title) title.textContent = label;
  if (detail) detail.textContent = t('hud.waiting_server', 'Waiting for server response');
  if (phase) phase.textContent = t('clean.preparing', 'Preparing');
  if (count) count.textContent = t('hud.preparing_items', 'Preparing items…');
  if (elapsed) elapsed.textContent = t('hud.elapsed', 'Elapsed {seconds}s').replace('{seconds}', '0');
  if (percent) percent.textContent = '…';
  if (bar) {
    bar.style.width = '35%';
    bar.classList.add('indeterminate');
  }
  if (state.progressTimer) clearInterval(state.progressTimer);
  state.progressTimer = setInterval(pollLiveProgress, 200);
  pollLiveProgress();
}

function stopLiveProgressPolling() {
  state.isOperationRunning = false;
  setTimeout(() => {
    if (!state.isOperationRunning) {
      if (state.progressTimer) clearInterval(state.progressTimer);
      pollLiveProgress().finally(() => {
        const hud = document.getElementById('global-operation-hud');
        if (hud && !hud.classList.contains('hidden') && !hud.classList.contains('is-error') && !hud.classList.contains('is-success')) {
          showOperationOutcome('success', t('hud.completed', 'Completed'));
        }
      });
    }
  }, 1000);
}

function dismissOperationOutcome() {
  const hud = document.getElementById('global-operation-hud');
  if (!hud || state.isOperationRunning) return;
  hud.classList.add('hidden');
}

function showOperationOutcome(type, message) {
  const hud = document.getElementById('global-operation-hud');
  if (!hud) return;
  hud.classList.remove('hidden', 'is-success', 'is-error');
  hud.classList.add(type === 'error' ? 'is-error' : 'is-success');
  hud.setAttribute('role', 'button');
  hud.setAttribute('tabindex', '0');
  hud.onclick = dismissOperationOutcome;
  hud.onkeydown = event => {
    if (event.key === 'Enter' || event.key === ' ' || event.key === 'Escape') {
      event.preventDefault();
      dismissOperationOutcome();
    }
  };
  document.getElementById('global-operation-spinner')?.classList.add('hidden');
  document.getElementById('global-scan-cancel')?.classList.add('hidden');
  const title = document.getElementById('global-operation-title');
  const detail = document.getElementById('global-operation-detail');
  const percent = document.getElementById('global-operation-percent');
  if (title) title.textContent = type === 'error' ? t('hud.failed', 'Operation failed') : t('hud.success', 'Operation completed');
  if (detail) detail.textContent = message || (type === 'error' ? t('hud.unknown_error', 'Unknown error') : t('hud.ok', 'Successful'));
  if (percent) percent.innerHTML = sfSymbol(type === 'error' ? 'exclamationmark.circle' : 'checkmark.circle');
  const health = hud.querySelector('.operation-health span');
  if (health) health.textContent = type === 'error'
    ? t('hud.finished_error', 'Stopped with an error')
    : t('hud.finished_healthy', 'Finished normally');
  const bar = document.getElementById('global-operation-bar');
  if (bar) {
    bar.classList.remove('indeterminate');
    bar.style.width = '100%';
  }
  setTimeout(() => {
    if (!state.isOperationRunning) hud.classList.add('hidden');
  }, type === 'error' ? 7000 : 3500);
}

async function cancelActiveScan(event) {
  const button = event?.currentTarget;
  const service = button?.dataset.service || 'clean';
  if (button) button.disabled = true;
  try {
    const response = await fetch('/api/scan/cancel', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ service })
    });
    const result = await readAPIResponse(response);
    showToast(result.cancelled ? t('toast.scan_cancelling', 'Scan is cancelling safely.') : t('toast.no_active_scan', 'No active scan found.'), result.cancelled ? 'warning' : 'info');
  } catch (error) {
    showToast(`${t('toast.scan_cancel_failed', 'Failed to stop scan: ')}${error.message}`, 'error');
  } finally {
    if (button) button.disabled = false;
  }
}

async function pollLiveProgress() {
  try {
    const res = await fetch('/api/progress');
    if (!res.ok) return;
    const data = await res.json();
    renderInPageProgress(data);
  } catch (err) {}
}

function renderInPageProgress(p) {
  const service = p.service || 'cleaner';
  const hud = document.getElementById('global-operation-hud');
  if (p.active) {
    state.operationObservedActive = true;
    hud?.classList.remove('hidden', 'is-success', 'is-error');
    document.getElementById('global-operation-spinner')?.classList.remove('hidden');
    const hudTitle = document.getElementById('global-operation-title');
    const hudDetail = document.getElementById('global-operation-detail');
    const hudPercent = document.getElementById('global-operation-percent');
    const hudPhase = document.getElementById('global-operation-phase');
    const hudBar = document.getElementById('global-operation-bar');
    const hudCount = document.getElementById('global-operation-count');
    const hudElapsed = document.getElementById('global-operation-elapsed');
    const cancelButton = document.getElementById('global-scan-cancel');
    const cancellable = service === 'cleaner' || service === 'analyzer';
    cancelButton?.classList.toggle('hidden', !cancellable);
    if (cancelButton && cancellable) {
      cancelButton.dataset.service = service === 'analyzer' ? 'analyzer' : 'clean';
      cancelButton.onclick = cancelActiveScan;
    }
    if (hudTitle) hudTitle.textContent = p.action || t('hud.in_progress', 'Operation in progress…');
    const currentPath = p.path || p.activity || p.detail || t('hud.waiting_server', 'Waiting for server response');
    if (hudDetail) {
      hudDetail.textContent = currentPath;
      hudDetail.title = currentPath;
    }
    if (hudPhase) hudPhase.textContent = p.phase || t('clean.phase_working', 'WORKING');
    const progressPercent = Number.isFinite(p.percent) && p.percent >= 0 ? Math.max(0, Math.min(100, p.percent)) : -1;
    if (hudPercent) hudPercent.textContent = progressPercent >= 0 ? `${progressPercent}%` : '…';
    if (hudBar) {
      hudBar.classList.toggle('indeterminate', progressPercent < 0);
      hudBar.style.width = progressPercent >= 0 ? `${progressPercent}%` : '35%';
    }
    if (hudCount) {
      hudCount.textContent = p.total > 0
        ? t('hud.items_progress', '{completed} of {total} items').replace('{completed}', String(p.completed || 0)).replace('{total}', String(p.total))
        : t('hud.preparing_items', 'Preparing items…');
    }
    if (hudElapsed) {
      const seconds = Math.max(0, Math.floor((Date.now() - state.operationStartedAt) / 1000));
      hudElapsed.textContent = t('hud.elapsed', 'Elapsed {seconds}s').replace('{seconds}', String(seconds));
    }
  } else if (state.isOperationRunning && state.operationObservedActive) {
    document.getElementById('global-scan-cancel')?.classList.add('hidden');
    showOperationOutcome('success', p.phase || t('hud.completed', 'Completed'));
  }

  // Map sub-services to their top-level tab dot
  const serviceToTab = {
    'devcaches': 'developer',
    'developer-caches': 'developer',
    'developer': 'developer',
    'runtimes': 'developer',
    'environments': 'developer',
    'tools': 'developer',
    'devtools': 'developer',
    'sdks': 'developer',
    'leftovers': 'more',
    'installers': 'more',
    'largefiles': 'more',
    'large-files': 'more',
    'browser-storage': 'more',
    'smart-downloads': 'more',
    'duplicates': 'more',
    'snapshots': 'more',
    'doctor': 'more',
    'history': 'more',
    'settings': 'more',
    'whitelist': 'more'
  };
  const targetTab = serviceToTab[service] || service;

  // Update sidebar active task indicator dots
  document.querySelectorAll('.nav-task-dot').forEach(dot => {
    if (p.active && dot.id === `dot-${targetTab}`) {
      dot.classList.remove('hidden');
    } else {
      dot.classList.add('hidden');
    }
  });

  let card = document.getElementById(`${service}-progress-card`);
  let activePrefix = service;
  if (!card) {
    const cardAliases = { 'developer-caches': 'devcaches', 'large-files': 'largefiles' };
    const aliasPrefix = cardAliases[service];
    if (aliasPrefix) {
      card = document.getElementById(`${aliasPrefix}-progress-card`);
      if (card) activePrefix = aliasPrefix;
    }
  }
  if (!card && (service === 'developer' || serviceToTab[service] === 'developer')) {
    const activeDevTab = document.querySelector('#pane-developer .sub-pane.active')?.id?.replace('subpane-dev-', '') || 'storage';
    const devProgressPrefixes = { storage: 'devstorage', caches: 'devcaches', runtimes: 'runtimes', environments: 'environments', tools: 'devtools', sdks: 'sdks' };
    const mappedPrefix = devProgressPrefixes[activeDevTab] || 'devcaches';
    const subCard = document.getElementById(`${mappedPrefix}-progress-card`);
    if (subCard) {
      card = subCard;
      activePrefix = mappedPrefix;
    } else {
      card = document.getElementById('devcaches-progress-card');
      activePrefix = 'devcaches';
    }
  }
  if (!card) return;

  if (p.active) {
    card.classList.remove('hidden');

    const actEl = document.getElementById(`${activePrefix}-action-label`) || document.getElementById(`${service}-action-label`);
    if (actEl) actEl.textContent = p.action || t('hud.in_progress', 'Operation in progress…');

    const phaseEl = document.getElementById(`${activePrefix}-phase-badge`) || document.getElementById(`${service}-phase-badge`);
    if (phaseEl) phaseEl.textContent = p.phase || t('clean.phase_working', 'WORKING');

    const countEl = document.getElementById(`${activePrefix}-progress-count`) || document.getElementById(`${service}-progress-count`);
    if (countEl) {
      if (p.total > 0 && p.completed !== undefined) {
        countEl.textContent = `${p.completed} / ${p.total}`;
      } else if (p.completed !== undefined && p.completed > 0) {
        countEl.textContent = `${p.completed.toLocaleString()} ${t('hud.items_examined', 'items examined')}`;
      } else {
        countEl.textContent = '';
      }
    }

    const pct = (p.percent !== undefined && p.percent >= 0)
      ? p.percent
      : (p.total > 0 && p.completed !== undefined ? Math.round((p.completed / p.total) * 100) : -1);

    const pctEl = document.getElementById(`${activePrefix}-progress-percent`) || document.getElementById(`${service}-progress-percent`);
    if (pctEl) {
      pctEl.textContent = pct >= 0 ? `${pct}%` : t('hud.scanning', 'Scanning...');
    }

    const barEl = document.getElementById(`${activePrefix}-progress-bar`) || document.getElementById(`${service}-progress-bar`);
    if (barEl) {
      if (pct >= 0) {
        barEl.style.width = `${pct}%`;
        barEl.classList.remove('indeterminate');
      } else {
        barEl.style.width = '100%';
        barEl.classList.add('indeterminate');
      }
    }

    const pathEl = document.getElementById(`${activePrefix}-path-text`) || document.getElementById(`${service}-path-text`);
    if (pathEl) pathEl.textContent = p.path || p.activity || p.detail || t('hud.executing', 'Executing operation...');

    const logsContainer = document.getElementById(`${activePrefix}-logs-container`) || document.getElementById(`${service}-logs-container`);
    if (logsContainer && p.logs && p.logs.length) {
      logsContainer.innerHTML = p.logs.map(log => {
        let cls = 'inpage-log-line';
        if (log.includes('✓') || log.includes('başarıyla') || log.includes('tamamlandı') || /success|completed|done/i.test(log)) cls += ' success';
        else if (log.includes('Uyarı') || log.includes('hata') || /warn|error|fail/i.test(log)) cls += ' warn';
        return `<div class="${cls}">${escapeHtml(log)}</div>`;
      }).join('');
      logsContainer.scrollTop = logsContainer.scrollHeight;
    }
  } else {
    // When finished, set 100% on active card and hide after timeout
    const phaseEl = document.getElementById(`${activePrefix}-phase-badge`) || document.getElementById(`${service}-phase-badge`);
    if (phaseEl) phaseEl.textContent = p.phase || 'TAMAMLANDI';
    const barEl = document.getElementById(`${activePrefix}-progress-bar`) || document.getElementById(`${service}-progress-bar`);
    if (barEl) {
      barEl.style.width = '100%';
      barEl.classList.remove('indeterminate');
    }
    const pctEl = document.getElementById(`${activePrefix}-progress-percent`) || document.getElementById(`${service}-progress-percent`);
    if (pctEl) pctEl.textContent = '100%';

    setTimeout(() => {
      if (!state.isOperationRunning) {
        card.classList.add('hidden');
      }
    }, 2500);
  }
}

window.toggleInPageLogs = function(service) {
  const container = document.getElementById(`${service}-logs-container`);
  const btnText = document.getElementById(`${service}-logs-btn-text`);
  if (!container) return;
  const isHidden = container.classList.toggle('hidden');
  if (btnText) {
    btnText.textContent = isHidden ? t('clean.logs_btn', '▸ Live Log Stream') : t('clean.logs_hide_btn', '▾ Hide Log Stream');
  }
};

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-log-service]').forEach(button => {
    button.addEventListener('click', () => toggleInPageLogs(button.dataset.logService));
  });
});
