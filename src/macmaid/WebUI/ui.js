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
// Compact information disclosures
// =========================================================

let informationSourceSequence = 0;

function informationButton(text, extraClass = '') {
  if (!text) return '';
  const safeText = escapeHtml(text);
  return `<button type="button" class="mm-info-button ${extraClass}" data-mm-tooltip="${safeText}" aria-label="${safeText}">${sfSymbol('info.circle')}</button>`;
}

function enhanceInformationCopy(root = document) {
  const selector = [
    '.pane-header .pane-subtitle',
    '.memory-section-header .memory-note[data-i18n]',
    '#clean-profile-context',
    '.card-desc[data-i18n]',
    '.setting-row .text-muted[data-i18n]',
    '.mm-info-copy',
  ].join(',');
  const sources = [];
  if (root instanceof Element && root.matches(selector)) sources.push(root);
  sources.push(...root.querySelectorAll(selector));
  sources.forEach(source => {
    if (source.dataset.infoEnhanced === 'true') return;
    source.dataset.infoEnhanced = 'true';
    source.id ||= `mm-info-source-${informationSourceSequence++}`;
    source.classList.add('mm-info-source');

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'mm-info-button';
    button.dataset.mmTooltipSource = source.id;
    button.setAttribute('aria-describedby', source.id);
    button.setAttribute('aria-label', source.textContent.trim());
    button.innerHTML = sfSymbol('info.circle');

    const directCard = source.matches('.card-desc') && source.parentElement?.matches('.glass-card');
    const cardHeader = directCard ? source.parentElement.querySelector(':scope > .card-header') : null;
    if (cardHeader) {
      cardHeader.appendChild(button);
      cardHeader.classList.add('mm-info-heading');
    } else {
      const parentHasOnlyLabelAndCopy = (source.parentElement?.children.length || 0) <= 2;
      const canAlignWithLabel = source.matches('.pane-subtitle, .memory-section-header .memory-note, .setting-row .text-muted')
        || (source.matches('.card-desc') && parentHasOnlyLabelAndCopy);
      const standaloneCardHeading = source.matches('.card-desc') && !parentHasOnlyLabelAndCopy
        ? source.parentElement?.querySelector(':scope > h1, :scope > h2, :scope > h3, :scope > h4, :scope > strong')
        : null;
      if (standaloneCardHeading) standaloneCardHeading.appendChild(button);
      else source.before(button);
      if (canAlignWithLabel) source.parentElement?.classList.add('mm-info-heading');
    }
    new MutationObserver(() => {
      button.setAttribute('aria-label', source.textContent.trim());
    }).observe(source, { childList: true, characterData: true, subtree: true });
  });
}

function tooltipText(control) {
  const sourceId = control.dataset.mmTooltipSource;
  if (sourceId) return document.getElementById(sourceId)?.textContent?.trim() || '';
  return control.dataset.mmTooltip || '';
}

function positionInformationTooltip(control, tooltip) {
  const text = tooltipText(control);
  if (!text) return;
  tooltip.textContent = text;
  tooltip.hidden = false;
  tooltip.style.left = '0px';
  tooltip.style.top = '0px';
  const controlRect = control.getBoundingClientRect();
  const tooltipRect = tooltip.getBoundingClientRect();
  const gutter = 8;
  const left = Math.min(
    window.innerWidth - tooltipRect.width - gutter,
    Math.max(gutter, controlRect.left + (controlRect.width - tooltipRect.width) / 2),
  );
  const below = controlRect.bottom + gutter;
  const top = below + tooltipRect.height <= window.innerHeight - gutter
    ? below
    : Math.max(gutter, controlRect.top - tooltipRect.height - gutter);
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function setupInformationTooltips() {
  enhanceInformationCopy();
  new MutationObserver(records => {
    records.forEach(record => record.addedNodes.forEach(node => {
      if (node instanceof Element) enhanceInformationCopy(node);
    }));
  }).observe(document.body, { childList: true, subtree: true });
  const tooltip = document.createElement('div');
  tooltip.className = 'mm-info-tooltip';
  tooltip.id = 'mm-info-tooltip';
  tooltip.setAttribute('role', 'tooltip');
  tooltip.hidden = true;
  document.body.appendChild(tooltip);

  const findControl = target => target instanceof Element
    ? target.closest('.mm-info-button')
    : null;
  const show = event => {
    const control = findControl(event.target);
    if (control) positionInformationTooltip(control, tooltip);
  };
  const hide = event => {
    const control = findControl(event.target);
    if (!control) return;
    if (event.type === 'pointerout' && event.relatedTarget instanceof Node && control.contains(event.relatedTarget)) return;
    tooltip.hidden = true;
  };
  document.addEventListener('pointerover', show);
  document.addEventListener('pointerout', hide);
  document.addEventListener('focusin', show);
  document.addEventListener('focusout', hide);
  window.addEventListener('scroll', () => { tooltip.hidden = true; }, true);
  window.addEventListener('resize', () => { tooltip.hidden = true; });
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
  setupInformationTooltips();
  document.getElementById('modal-close-btn')?.addEventListener('click', hideModal);
  document.getElementById('modal-container')?.addEventListener('click', event => {
    if (event.target.id === 'modal-container') hideModal();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') hideModal();
  });
});
