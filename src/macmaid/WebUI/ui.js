/* =========================================================
   MacMaid Pro — UI chrome: sounds, confetti, toasts, modal,
   formatting and shared DOM helpers
   ========================================================= */

const SoundEffects = {
  audioCtx: null,

  init() {
    if (!this.audioCtx && (window.AudioContext || window.webkitAudioContext)) {
      this.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
  },

  playClick() {
    if (!state.soundEnabled) return;
    try {
      this.init();
      if (!this.audioCtx) return;
      const osc = this.audioCtx.createOscillator();
      const gain = this.audioCtx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(600, this.audioCtx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(300, this.audioCtx.currentTime + 0.04);
      gain.gain.setValueAtTime(0.08, this.audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, this.audioCtx.currentTime + 0.04);
      osc.connect(gain);
      gain.connect(this.audioCtx.destination);
      osc.start();
      osc.stop(this.audioCtx.currentTime + 0.04);
    } catch (e) {}
  },

  playSuccess() {
    if (!state.soundEnabled) return;
    try {
      this.init();
      if (!this.audioCtx) return;
      const chords = [523.25, 659.25, 783.99, 1046.50];
      chords.forEach((freq, idx) => {
        const osc = this.audioCtx.createOscillator();
        const gain = this.audioCtx.createGain();
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(freq, this.audioCtx.currentTime + idx * 0.08);
        gain.gain.setValueAtTime(0.12, this.audioCtx.currentTime + idx * 0.08);
        gain.gain.exponentialRampToValueAtTime(0.001, this.audioCtx.currentTime + idx * 0.08 + 0.35);
        osc.connect(gain);
        gain.connect(this.audioCtx.destination);
        osc.start(this.audioCtx.currentTime + idx * 0.08);
        osc.stop(this.audioCtx.currentTime + idx * 0.08 + 0.35);
      });
    } catch (e) {}
  }
};

// UI Toast Notification helper
function dismissToast(toast) {
  if (!toast || !toast.isConnected || toast.classList.contains('toast-dismissing')) return;
  if (toast.dismissTimer) clearTimeout(toast.dismissTimer);
  toast.classList.add('toast-dismissing');
  toast.addEventListener('transitionend', () => toast.remove(), { once: true });
  setTimeout(() => toast.remove(), 350);
}

function showToast(message, type = 'info') {
  if (type === 'error' && state.isOperationRunning) showOperationOutcome('error', message);
  const container = document.getElementById('toast-container');
  if (!container) return;
  const normalizedType = ['success', 'error', 'warning', 'info'].includes(type) ? type : 'info';
  const icons = { success: 'checkmark.circle', error: 'exclamationmark.circle', warning: 'exclamationmark.triangle', info: 'info.circle' };
  const titles = {
    success: t('toast.success_title', 'Completed'),
    error: t('toast.error_title', 'Action failed'),
    warning: t('toast.warning_title', 'Attention required'),
    info: t('toast.info_title', 'MacMaid'),
  };
  const toast = document.createElement('div');
  toast.className = `toast toast-${normalizedType}`;
  toast.setAttribute('role', normalizedType === 'error' ? 'alert' : 'status');
  toast.setAttribute('tabindex', '0');
  toast.setAttribute('aria-label', `${titles[normalizedType]}: ${message}. ${t('toast.close_tip', 'Dismiss notification')}`);
  toast.innerHTML = `
    <span class="toast-icon" aria-hidden="true">${sfSymbol(icons[normalizedType])}</span>
    <span class="toast-copy"><strong>${escapeHtml(titles[normalizedType])}</strong><span class="toast-msg">${escapeHtml(message)}</span></span>
    <button class="toast-close" type="button" aria-label="${escapeHtml(t('toast.close_tip', 'Dismiss notification'))}">${sfSymbol('xmark')}</button>
  `;
  toast.addEventListener('click', () => dismissToast(toast));
  toast.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ' || event.key === 'Escape') {
      event.preventDefault();
      dismissToast(toast);
    }
  });
  container.appendChild(toast);
  const lifetime = normalizedType === 'success' ? 3500 : normalizedType === 'error' ? 7000 : 4500;
  toast.dismissTimer = setTimeout(() => dismissToast(toast), lifetime);
}

// Format bytes
function formatBytes(bytes) {
  if (bytes === undefined || bytes === null || isNaN(bytes)) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  let val = Number(bytes);
  while (val >= 1024 && i < units.length - 1) {
    val /= 1024;
    i++;
  }
  return `${val.toFixed(val >= 10 || i === 0 ? 1 : 2)} ${units[i]}`;
}

function syncMasterCheckbox(id, total, selected) {
  const checkbox = document.getElementById(id);
  if (!checkbox) return;
  checkbox.checked = total > 0 && selected === total;
  checkbox.indeterminate = selected > 0 && selected < total;
  checkbox.disabled = total === 0;
}

function collectionFingerprint(items = []) {
  return JSON.stringify(items.map(item => [item.id || item.path, item.bytes, item.version, item.isActive, item.removable]));
}

function beginCollectionRefresh(tbody, previousItems, colspan, message) {
  const container = tbody.closest('.table-container');
  container?.classList.add('is-refreshing');
  container?.setAttribute('aria-busy', 'true');
  if (!previousItems?.length) {
    tbody.innerHTML = `<tr><td colspan="${colspan}" class="empty-state">${escapeHtml(message)}</td></tr>`;
  }
}

function endCollectionRefresh(tbody) {
  const container = tbody.closest('.table-container');
  container?.classList.remove('is-refreshing');
  container?.removeAttribute('aria-busy');
}

function highlightCollectionDiff(tbody, previousItems, nextItems, colspan) {
  const previousIds = new Set((previousItems || []).map(item => item.id || item.path));
  const nextIds = new Set((nextItems || []).map(item => item.id || item.path));
  tbody.querySelectorAll('tr[data-item-id]').forEach(row => {
    if (!previousIds.has(row.dataset.itemId)) row.classList.add('row-added');
  });
  (previousItems || []).filter(item => !nextIds.has(item.id || item.path)).forEach(item => {
    const row = document.createElement('tr');
    row.className = 'row-removed';
    row.innerHTML = `<td colspan="${colspan}"></td>`;
    row.firstElementChild.textContent = `${t('toast.uninstalled', 'Removed')}: ${item.title || item.name || item.label || item.path}`;
    tbody.prepend(row);
  });
  setTimeout(() => {
    tbody.querySelectorAll('.row-removed').forEach(row => row.remove());
    tbody.querySelectorAll('.row-added').forEach(row => row.classList.remove('row-added'));
  }, 4500);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function setGauge(circleId, percent) {
  const circle = document.getElementById(circleId);
  if (!circle) return;
  const clamped = Math.max(0, Math.min(100, percent));
  const offset = 264 - (264 * clamped) / 100;
  circle.style.strokeDashoffset = offset;
}

// =========================================================
// Modal dialog
// =========================================================

function showModal(title, bodyHtml, buttons = []) {
  state.modalReturnFocus = document.activeElement;
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').innerHTML = bodyHtml;

  const footer = document.getElementById('modal-footer');
  footer.innerHTML = '';
  buttons.forEach(btnInfo => {
    const btn = document.createElement('button');
    btn.className = `btn ${btnInfo.class || 'btn-secondary'}`;
    btn.textContent = btnInfo.text;
    btn.onclick = btnInfo.onClick;
    footer.appendChild(btn);
  });

  document.getElementById('modal-container').classList.remove('hidden');
  requestAnimationFrame(() => {
    const firstControl = document.querySelector('#modal-container button, #modal-container input, #modal-container select, #modal-container textarea');
    firstControl?.focus();
  });
}

function hideModal() {
  const modal = document.getElementById('modal-container');
  if (modal.classList.contains('hidden')) return;
  modal.classList.add('hidden');
  state.modalReturnFocus?.focus?.();
  state.modalReturnFocus = null;
}

// Modal dismiss wiring — registered once at DOM ready.
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('modal-close-btn')?.addEventListener('click', hideModal);
  document.getElementById('modal-container')?.addEventListener('click', event => {
    if (event.target.id === 'modal-container') hideModal();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') hideModal();
  });
});
