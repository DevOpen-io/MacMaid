/* =========================================================
   DeepClean Pro — Modern Web Dashboard Controller
   With Real-time Continuous Live Feedback Engine & Full Tool Suite
   ========================================================= */

// State Management
const state = {
  activeTab: 'cleaner',
  refreshInterval: 3000,
  refreshTimer: null,
  progressTimer: null,
  isOperationRunning: false,
  operationObservedActive: false,
  soundEnabled: localStorage.getItem('deepclean_sound') !== 'off',
  currentScan: null,
  selectedCleanItems: new Set(),
  apps: [],
  selectedApp: null,
  appLeftovers: [],
  purgeArtifacts: [],
  selectedPurgeArtifacts: new Set(),
  installers: [],
  selectedInstallers: new Set(),
  leftovers: [],
  selectedLeftovers: new Set(),
  devCaches: [],
  selectedDevCaches: new Set(),
  currentAnalyzePath: '~',
  analyzerViews: new Map(),
  analyzerRequestId: Date.now(),
  analyzerPollTimer: null,
  theme: ['dark', 'midnight', 'cyber', 'light'].includes(localStorage.getItem('deepclean_theme'))
    ? localStorage.getItem('deepclean_theme')
    : 'dark',
  modalReturnFocus: null,
};

async function readAPIResponse(response) {
  let payload = {};
  try { payload = await response.json(); } catch (_) {}
  if (!response.ok || payload.success === false) {
    const details = Array.isArray(payload.details) ? payload.details.join(' ') : '';
    throw new Error(payload.error || payload.message || details || `HTTP ${response.status}`);
  }
  return payload;
}

// Web Audio API Sound Synthesizer
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

// Confetti Particle System
const Confetti = {
  canvas: null,
  ctx: null,
  particles: [],
  animId: null,

  init() {
    this.canvas = document.getElementById('confetti-canvas');
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');
    this.resize();
    window.addEventListener('resize', () => this.resize());
  },

  resize() {
    if (!this.canvas) return;
    this.canvas.width = window.innerWidth;
    this.canvas.height = window.innerHeight;
  },

  launch() {
    if (!this.canvas) this.init();
    this.particles = [];
    const colors = ['#3b82f6', '#06b6d4', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6'];
    for (let i = 0; i < 90; i++) {
      this.particles.push({
        x: window.innerWidth / 2,
        y: window.innerHeight / 2,
        vx: (Math.random() - 0.5) * 16,
        vy: (Math.random() - 0.8) * 16,
        size: Math.random() * 8 + 4,
        color: colors[Math.floor(Math.random() * colors.length)],
        rotation: Math.random() * 360,
        rSpeed: (Math.random() - 0.5) * 10,
        alpha: 1
      });
    }
    if (this.animId) cancelAnimationFrame(this.animId);
    this.loop();
  },

  loop() {
    if (!this.ctx) return;
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    let active = false;

    for (let p of this.particles) {
      p.x += p.vx;
      p.y += p.vy;
      p.vy += 0.35;
      p.rotation += p.rSpeed;
      p.alpha -= 0.012;

      if (p.alpha > 0) {
        active = true;
        this.ctx.save();
        this.ctx.globalAlpha = p.alpha;
        this.ctx.translate(p.x, p.y);
        this.ctx.rotate((p.rotation * Math.PI) / 180);
        this.ctx.fillStyle = p.color;
        this.ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size);
        this.ctx.restore();
      }
    }

    if (active) {
      this.animId = requestAnimationFrame(() => this.loop());
    } else {
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    }
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
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.setAttribute('role', 'button');
  toast.setAttribute('tabindex', '0');
  toast.setAttribute('aria-label', `${message}. Bildirimi kapat`);
  toast.title = 'Kapatmak için tıklayın';
  toast.innerHTML = `
    <span class="toast-icon">⚡</span>
    <span class="toast-msg">${escapeHtml(message)}</span>
  `;
  toast.addEventListener('click', () => dismissToast(toast));
  toast.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ' || event.key === 'Escape') {
      event.preventDefault();
      dismissToast(toast);
    }
  });
  container.appendChild(toast);
  toast.dismissTimer = setTimeout(() => dismissToast(toast), 3500);
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
    row.firstElementChild.textContent = `Kaldırıldı: ${item.title || item.name || item.label || item.path}`;
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
// CONTINUOUS IN-PAGE LIVE PROGRESS FEEDBACK ENGINE
// =========================================================

function startLiveProgressPolling(label = 'İşlem başlatılıyor…') {
  state.isOperationRunning = true;
  state.operationObservedActive = false;
  const hud = document.getElementById('global-operation-hud');
  hud?.classList.remove('hidden', 'is-success', 'is-error');
  document.getElementById('global-operation-spinner')?.classList.remove('hidden');
  const title = document.getElementById('global-operation-title');
  const detail = document.getElementById('global-operation-detail');
  const percent = document.getElementById('global-operation-percent');
  if (title) title.textContent = label;
  if (detail) detail.textContent = 'Sunucu yanıtı bekleniyor';
  if (percent) percent.textContent = '…';
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
          showOperationOutcome('success', 'Tamamlandı');
        }
      });
    }
  }, 1000);
}

function showOperationOutcome(type, message) {
  const hud = document.getElementById('global-operation-hud');
  if (!hud) return;
  hud.classList.remove('hidden', 'is-success', 'is-error');
  hud.classList.add(type === 'error' ? 'is-error' : 'is-success');
  document.getElementById('global-operation-spinner')?.classList.add('hidden');
  const title = document.getElementById('global-operation-title');
  const detail = document.getElementById('global-operation-detail');
  const percent = document.getElementById('global-operation-percent');
  if (title) title.textContent = type === 'error' ? 'İşlem başarısız' : 'İşlem tamamlandı';
  if (detail) detail.textContent = message || (type === 'error' ? 'Bilinmeyen hata' : 'Başarılı');
  if (percent) percent.textContent = type === 'error' ? '!' : '✓';
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
    showToast(result.cancelled ? 'Tarama güvenli durma noktasında iptal ediliyor.' : 'Aktif tarama bulunamadı.', result.cancelled ? 'warning' : 'info');
  } catch (error) {
    showToast(`Tarama durdurulamadı: ${error.message}`, 'error');
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
    const cancelButton = document.getElementById('global-scan-cancel');
    const cancellable = service === 'cleaner' || service === 'analyzer';
    cancelButton?.classList.toggle('hidden', !cancellable);
    if (cancelButton && cancellable) {
      cancelButton.dataset.service = service === 'analyzer' ? 'analyzer' : 'clean';
      cancelButton.onclick = cancelActiveScan;
    }
    if (hudTitle) hudTitle.textContent = p.action || 'İşlem sürüyor…';
    if (hudDetail) hudDetail.textContent = p.phase || p.path || 'Çalışıyor';
    if (hudPercent) hudPercent.textContent = p.percent >= 0 ? `${p.percent}%` : '…';
  } else if (state.isOperationRunning && state.operationObservedActive) {
    document.getElementById('global-scan-cancel')?.classList.add('hidden');
    showOperationOutcome('success', p.phase || 'Tamamlandı');
  }

  // Map sub-services to their top-level tab dot
  const serviceToTab = {
    'devcaches': 'developer',
    'developer': 'developer',
    'runtimes': 'developer',
    'environments': 'developer',
    'tools': 'developer',
    'devtools': 'developer',
    'sdks': 'developer',
    'leftovers': 'more',
    'installers': 'more',
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
  if (!card && (service === 'developer' || serviceToTab[service] === 'developer')) {
    const activeDevTab = document.querySelector('#pane-developer .subnav-pill.active')?.dataset.devtab || 'caches';
    const devProgressPrefixes = { caches: 'devcaches', runtimes: 'runtimes', environments: 'environments', tools: 'devtools', sdks: 'sdks' };
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
    if (actEl) actEl.textContent = p.action || 'İşlem Sürüyor...';

    const phaseEl = document.getElementById(`${activePrefix}-phase-badge`) || document.getElementById(`${service}-phase-badge`);
    if (phaseEl) phaseEl.textContent = p.phase || 'ÇALIŞIYOR';

    const countEl = document.getElementById(`${activePrefix}-progress-count`) || document.getElementById(`${service}-progress-count`);
    if (countEl) {
      if (p.total > 0 && p.completed !== undefined) {
        countEl.textContent = `${p.completed} / ${p.total}`;
      } else if (p.completed !== undefined && p.completed > 0) {
        countEl.textContent = `${p.completed.toLocaleString()} öğe incelendi`;
      } else {
        countEl.textContent = '';
      }
    }

    const pct = (p.percent !== undefined && p.percent >= 0)
      ? p.percent
      : (p.total > 0 && p.completed !== undefined ? Math.round((p.completed / p.total) * 100) : -1);

    const pctEl = document.getElementById(`${activePrefix}-progress-percent`) || document.getElementById(`${service}-progress-percent`);
    if (pctEl) {
      pctEl.textContent = pct >= 0 ? `${pct}%` : 'Taranıyor...';
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
    if (pathEl) pathEl.textContent = p.path || p.activity || p.detail || 'İşlem yürütülüyor...';

    const logsContainer = document.getElementById(`${activePrefix}-logs-container`) || document.getElementById(`${service}-logs-container`);
    if (logsContainer && p.logs && p.logs.length) {
      logsContainer.innerHTML = p.logs.map(log => {
        let cls = 'inpage-log-line';
        if (log.includes('✓') || log.includes('başarıyla') || log.includes('tamamlandı')) cls += ' success';
        else if (log.includes('Uyarı') || log.includes('hata')) cls += ' warn';
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
    btnText.textContent = isHidden ? '▸ Canlı Log Akışı' : '▾ Günlüğü Gizle';
  }
};

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

function renderStatus(data) {
  const { metrics, health, uptime, loadAverage, thermal, battery, processes } = data;

  const healthGrid = document.getElementById('health-indicators');
  if (healthGrid && Array.isArray(health)) {
    const stateLabels = { normal: 'NORMAL', warning: 'UYARI', critical: 'KRİTİK', unknown: 'BİLİNMİYOR', not_applicable: 'UYGULANAMAZ' };
    healthGrid.innerHTML = health.map(item => `
      <article class="health-indicator health-${escapeHtml(item.state)}">
        <div class="health-indicator-head">
          <strong>${escapeHtml(item.label)}</strong>
          <span class="health-state">${escapeHtml(stateLabels[item.state] || 'BİLİNMİYOR')}</span>
        </div>
        <div class="health-value">${escapeHtml(item.value)}</div>
        <p>${escapeHtml(item.detail)}</p>
        ${item.recommendation ? `<p class="health-recommendation">Öneri: ${escapeHtml(item.recommendation)}</p>` : ''}
        <small>Ölçüm: ${escapeHtml(item.measuredAt)}</small>
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
    document.getElementById('header-disk-val').textContent = `${diskFreeGB} GB boş`;
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
    document.getElementById('dash-batt-state').textContent = battery.charging ? 'Şarj Ediliyor ⚡' : 'Pilde Çalışıyor';
    document.getElementById('dash-batt-cycles').textContent = battery.cycleCount ? `${battery.cycleCount} Döngü` : 'Normal';
  } else {
    const batteryHealth = Array.isArray(health) ? health.find(item => item.id === 'battery') : null;
    const absent = batteryHealth?.state === 'not_applicable';
    document.getElementById('dash-batt-pct').textContent = absent ? 'Pil Yok' : 'Bilinmiyor';
    document.getElementById('dash-batt-bar').style.width = '0%';
    document.getElementById('dash-batt-state').textContent = absent ? 'Masaüstü / AC' : 'Pil verisi okunamadı';
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
      showToast(`Tarama tamamlandı: ${data.items.length} öğe bulundu (${data.humanTotal})`, 'success');
    } else {
      showToast(`Tarama ${data.status}: sonuçlar eksik, temizlik engellendi. ${(data.notes || []).join(' ')}`, 'warning');
    }
  } catch (err) {
    showToast(`Tarama hatası: ${err.message}`, 'error');
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
  const actionableCount = scanData.items.filter(item => item.risk !== 'MANUAL').length;
  syncMasterCheckbox('master-clean-chk', actionableCount, state.selectedCleanItems.size);

  const tbody = document.getElementById('tbody-clean-items');
  if (!scanData.items || scanData.items.length === 0) {
    const message = scanData.isComplete ? 'Temizlenecek öğe bulunamadı. Sisteminiz tertemiz! ✨' : `Tarama ${escapeHtml(scanData.status || 'eksik')} · sonuçlar temizleme için kullanılamaz.`;
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
          <div style="font-weight: 600;">${escapeHtml(item.label)}</div>
          <div style="font-size: 11px; color: var(--text-dim);">${escapeHtml(item.category)}</div>
        </td>
        <td><span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(item.path || 'Komut')}</span></td>
        <td><span class="badge-status"><span class="pill-dot ${riskBadgeClass}" style="display:inline-block; margin-right:4px;"></span>${escapeHtml(item.risk)}</span></td>
        <td><span style="font-size: 11.5px; color: var(--text-muted);">${escapeHtml(item.reason)}</span></td>
        <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${escapeHtml(item.humanBytes)}</td>
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

function updateSelectedCleanStats() {
  if (!state.currentScan) return;
  let selectedBytes = 0;
  state.currentScan.items.forEach(item => {
    if (state.selectedCleanItems.has(item.id)) selectedBytes += Number(item.estimatedBytes || 0);
  });
  document.getElementById('res-selected-bytes').textContent = formatBytes(selectedBytes);
  syncMasterCheckbox('master-clean-chk', state.currentScan.items.filter(item => item.risk !== 'MANUAL').length, state.selectedCleanItems.size);
}

async function executeClean() {
  if (state.currentScan && !state.currentScan.isComplete) {
    showToast('Kısmi veya iptal edilmiş tarama temizlenemez. Yeni ve tam bir tarama çalıştırın.', 'warning');
    return;
  }
  if (!state.currentScan || state.selectedCleanItems.size === 0) {
    showToast('Temizlemek için en az bir öğe seçin.', 'warning');
    return;
  }

  const isDryRun = document.getElementById('chk-dryrun').checked;
  const itemsToClean = state.currentScan.items.filter(i => state.selectedCleanItems.has(i.id));
  const payload = { itemIds: itemsToClean.map(i => i.id), dryRun: isDryRun };
  let reviewResponse;
  try {
    reviewResponse = await requestOperationReview('/api/clean', payload);
  } catch (err) {
    showToast(`İnceleme hazırlanamadı: ${err.message}`, 'error');
    return;
  }

  showModal(
    reviewResponse.review.title,
    operationReviewHtml(reviewResponse.review),
    [
      { text: 'Vazgeç', class: 'btn-secondary', onClick: hideModal },
      {
        text: isDryRun ? 'Simülasyonu Çalıştır' : 'Temizle ve Alan Kazan',
        class: 'btn-danger',
        onClick: async () => {
          const authorized = reviewedPayload(payload, reviewResponse);
          if (!authorized) return;
          hideModal();
          startLiveProgressPolling(isDryRun ? 'Temizlik simüle ediliyor…' : 'Seçilen öğeler temizleniyor…');
          const btn = document.getElementById('btn-execute-clean');
          btn.disabled = true;
          btn.innerHTML = `<span>Temizleniyor...</span>`;

          try {
            const res = await fetch('/api/clean', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(authorized)
            });
            const result = await readAPIResponse(res);
            Confetti.launch();
            SoundEffects.playSuccess();
            showToast(operationOutcomeText(result), 'success');
            document.getElementById('scan-results-box').classList.add('hidden');
            fetchStatus();
          } catch (err) {
            showOperationOutcome('error', err.message);
            showToast(`Hata: ${err.message}`, 'error');
          } finally {
            stopLiveProgressPolling();
            btn.disabled = false;
            btn.innerHTML = `<span>Temizliği Başlat</span>`;
          }
        }
      }
    ]
  );
}

// =========================================================
// Tab 3: App Uninstaller (apps)
// =========================================================

async function fetchApplications() {
  const container = document.getElementById('apps-list-container');
  const previousApps = state.apps || [];
  container.classList.add('is-refreshing');
  container.setAttribute('aria-busy', 'true');
  if (!previousApps.length) container.innerHTML = `<div class="loading-state">Yüklü uygulamalar taranıyor...</div>`;
  startLiveProgressPolling('Yüklü uygulamalar taranıyor…');

  try {
    const res = await fetch('/api/apps');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const nextApps = data.apps || [];
    const changed = collectionFingerprint(previousApps) !== collectionFingerprint(nextApps);
    state.apps = nextApps;
    if (changed || !previousApps.length) {
      renderAppsList();
      const previousPaths = new Set(previousApps.map(app => app.path));
      container.querySelectorAll('.app-item-card').forEach(card => {
        if (!previousPaths.has(card.dataset.path)) card.classList.add('row-added');
      });
      previousApps.filter(app => !nextApps.some(next => next.path === app.path)).forEach(app => {
        const removed = document.createElement('div');
        removed.className = 'app-item-card row-removed';
        removed.textContent = `Kaldırıldı: ${app.name}`;
        container.prepend(removed);
      });
      setTimeout(() => {
        container.querySelectorAll('.row-removed').forEach(row => row.remove());
        container.querySelectorAll('.row-added').forEach(row => row.classList.remove('row-added'));
      }, 4500);
    }
  } catch (err) {
    if (!previousApps.length) container.innerHTML = `<div class="empty-state">Uygulamalar alınamadı: ${escapeHtml(err.message)}</div>`;
    showOperationOutcome('error', err.message);
  } finally {
    container.classList.remove('is-refreshing');
    container.removeAttribute('aria-busy');
    stopLiveProgressPolling();
  }
}

function renderAppsList() {
  const container = document.getElementById('apps-list-container');
  const searchFilter = (document.getElementById('search-apps-input').value || '').toLowerCase();
  const sortMode = document.getElementById('sort-apps-select').value;

  let filtered = state.apps.filter(a => a.name.toLowerCase().includes(searchFilter) || (a.bundleId && a.bundleId.toLowerCase().includes(searchFilter)));

  if (sortMode === 'size') filtered.sort((a, b) => (b.bytes || 0) - (a.bytes || 0));
  else filtered.sort((a, b) => a.name.localeCompare(b.name));

  if (filtered.length === 0) {
    container.innerHTML = `<div class="empty-state">Eşleşen uygulama bulunamadı.</div>`;
    return;
  }

  container.innerHTML = filtered.map(app => {
    const isSel = state.selectedApp && state.selectedApp.path === app.path ? 'selected' : '';
    const initial = app.name ? app.name.charAt(0).toUpperCase() : '';
    const iconURL = `/api/apps/icon?path=${encodeURIComponent(app.path)}`;
    return `
      <div class="app-item-card ${isSel}" data-path="${escapeHtml(app.path)}" tabindex="0" role="button" aria-pressed="${isSel ? 'true' : 'false'}">
        <div class="app-avatar"><img src="${iconURL}" alt="" loading="lazy" data-fallback="${escapeHtml(initial)}"></div>
        <div class="app-meta">
          <h4>${escapeHtml(app.name)}</h4>
          <p>${escapeHtml(app.bundleId || app.path)}</p>
        </div>
        <div class="app-size-badge">${formatBytes(app.bytes)}</div>
      </div>
    `;
  }).join('');

  container.querySelectorAll('.app-item-card').forEach(card => {
    const activate = () => {
      const app = state.apps.find(a => a.path === card.dataset.path);
      if (app) selectApp(app);
    };
    card.addEventListener('click', activate);
    card.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        activate();
      }
    });
  });
  container.querySelectorAll('.app-avatar img').forEach(img => {
    img.addEventListener('error', () => { img.parentElement.textContent = img.dataset.fallback || ''; }, { once: true });
  });
}

async function selectApp(app) {
  SoundEffects.playClick();
  state.selectedApp = app;
  renderAppsList();

  document.getElementById('app-detail-empty').classList.add('hidden');
  const view = document.getElementById('app-detail-view');
  view.classList.remove('hidden');

  const detailIcon = document.getElementById('detail-app-icon');
  const initial = app.name ? app.name.charAt(0).toUpperCase() : '';
  detailIcon.innerHTML = `<img src="/api/apps/icon?path=${encodeURIComponent(app.path)}" alt="" data-fallback="${escapeHtml(initial)}">`;
  detailIcon.querySelector('img')?.addEventListener('error', event => {
    event.currentTarget.parentElement.textContent = event.currentTarget.dataset.fallback || '';
  }, { once: true });
  document.getElementById('detail-app-name').textContent = app.name;
  document.getElementById('detail-app-bundle').textContent = app.bundleId || app.path;
  document.getElementById('detail-app-version').textContent = app.version ? `Sürüm ${app.version}` : 'Sürüm bilgisi yok';
  document.getElementById('detail-app-size').textContent = formatBytes(app.bytes);

  const leftoversList = document.getElementById('detail-leftovers-list');
  leftoversList.innerHTML = `<div style="padding: 10px; color: var(--text-dim);">Artık dosyalar araştırılıyor...</div>`;

  try {
    const res = await fetch(`/api/apps/leftovers?path=${encodeURIComponent(app.path)}&bundleId=${encodeURIComponent(app.bundleId || '')}`);
    const data = await res.json();
    state.appLeftovers = data.leftovers || [];
    document.getElementById('detail-leftovers-count').textContent = `${state.appLeftovers.length} konum`;

    if (state.appLeftovers.length === 0) {
      leftoversList.innerHTML = `<div class="empty-state" style="padding: 15px;">Ekstra artık klasör bulunamadı. Sadece uygulama paketi kaldırılacak.</div>`;
    } else {
      leftoversList.innerHTML = state.appLeftovers.map(item => `
        <div class="leftover-row">
          <div>
            <div style="font-weight:600;">${escapeHtml(item.title)}</div>
            <div class="leftover-path">${escapeHtml(item.path)}</div>
          </div>
          <div style="font-family: var(--font-mono);">${formatBytes(item.bytes)}</div>
        </div>
      `).join('');
    }
  } catch (err) {
    leftoversList.innerHTML = `<div class="empty-state">Artıklar taranamadı: ${escapeHtml(err.message)}</div>`;
  }
}

async function uninstallSelectedApp() {
  if (!state.selectedApp) return;
  const app = state.selectedApp;
  const payload = { path: app.path, bundleId: app.bundleId, leftoverPaths: state.appLeftovers.map(l => l.path) };
  let reviewResponse;
  try {
    reviewResponse = await requestOperationReview('/api/apps/uninstall', payload);
  } catch (err) {
    showToast(`İnceleme hazırlanamadı: ${err.message}`, 'error');
    return;
  }

  showModal(
    reviewResponse.review.title,
    operationReviewHtml(reviewResponse.review),
    [
      { text: 'İptal', class: 'btn-secondary', onClick: hideModal },
      {
        text: 'Kaldır',
        class: 'btn-danger',
        onClick: async () => {
          const authorized = reviewedPayload(payload, reviewResponse);
          if (!authorized) return;
          hideModal();
          startLiveProgressPolling();
          try {
            const res = await fetch('/api/apps/uninstall', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(authorized)
            });
            const data = await readAPIResponse(res);
            Confetti.launch();
            SoundEffects.playSuccess();
            showToast(`${app.name} kaldırıldı · ${operationOutcomeText(data)}`, 'success');
            state.selectedApp = null;
            document.getElementById('app-detail-view').classList.add('hidden');
            document.getElementById('app-detail-empty').classList.remove('hidden');
            await fetchApplications();
          } catch (e) {
            showOperationOutcome('error', e.message);
            showToast(`Kaldırma hatası: ${e.message}`, 'error');
          } finally {
            stopLiveProgressPolling();
          }
        }
      }
    ]
  );
}

// =========================================================
// Tab 4: Installers Cleaner (installers)
// =========================================================

async function scanInstallers() {
  SoundEffects.playClick();
  const daysPill = document.querySelector('.installer-age-pill.active');
  const days = daysPill ? daysPill.dataset.days : '30';

  const tbody = document.getElementById('tbody-installers');
  tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Yükleyici dosyaları taranıyor...</td></tr>`;
  startLiveProgressPolling();

  try {
    const res = await fetch(`/api/installers?olderThan=${days}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.installers = data.installers || [];
    state.selectedInstallers = new Set(state.installers.map(i => i.path));

    document.getElementById('installers-total-size').textContent = data.humanTotal || formatBytes(data.totalBytes);
    document.getElementById('installers-count').textContent = `(${state.installers.length} dosya)`;
    syncMasterCheckbox('master-installers-chk', state.installers.length, state.selectedInstallers.size);

    if (state.installers.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Eski yükleyici dosyası bulunamadı.</td></tr>`;
      return;
    }

    tbody.innerHTML = state.installers.map(item => `
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

  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Hata: ${escapeHtml(err.message)}</td></tr>`;
  } finally {
    stopLiveProgressPolling();
  }
}

async function executeInstallersClean() {
  if (state.selectedInstallers.size === 0) {
    showToast('Silmek için en az bir yükleyici seçin.', 'warning');
    return;
  }

  const paths = Array.from(state.selectedInstallers);
  const payload = { paths };
  let reviewResponse;
  try { reviewResponse = await requestOperationReview('/api/installers/clean', payload); }
  catch (err) { showToast(`İnceleme hazırlanamadı: ${err.message}`, 'error'); return; }
  showModal(
    reviewResponse.review.title,
    operationReviewHtml(reviewResponse.review),
    [
      { text: 'İptal', class: 'btn-secondary', onClick: hideModal },
      {
        text: 'Çöpe Taşı',
        class: 'btn-danger',
        onClick: async () => {
          const authorized = reviewedPayload(payload, reviewResponse);
          if (!authorized) return;
          hideModal();
          startLiveProgressPolling();
          try {
            const res = await fetch('/api/installers/clean', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(authorized)
            });
            const data = await readAPIResponse(res);
            Confetti.launch();
            SoundEffects.playSuccess();
            showToast(operationOutcomeText(data), 'success');
            scanInstallers();
          } catch (e) {
            showToast(`Hata: ${e.message}`, 'error');
          } finally {
            stopLiveProgressPolling();
          }
        }
      }
    ]
  );
}

// =========================================================
// Tab 5: Leftovers Cleaner (leftovers)
// =========================================================

async function scanLeftovers() {
  SoundEffects.playClick();
  const daysPill = document.querySelector('.leftover-age-pill.active');
  const days = daysPill ? daysPill.dataset.days : '30';
  const includeData = document.getElementById('chk-leftovers-data').checked;

  const tbody = document.getElementById('tbody-leftovers');
  tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Kaldırılmış uygulama artıkları taranıyor...</td></tr>`;
  startLiveProgressPolling();

  try {
    const res = await fetch(`/api/leftovers?olderThan=${days}&includeData=${includeData}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.leftovers = data.leftovers || [];
    state.selectedLeftovers = new Set(state.leftovers.filter(l => l.risk !== 'MANUAL').map(l => l.id));

    document.getElementById('leftovers-total-size').textContent = data.humanTotal || formatBytes(data.totalBytes);
    document.getElementById('leftovers-count').textContent = `(${state.leftovers.length} artık)`;
    const actionableCount = state.leftovers.filter(item => item.risk !== 'MANUAL').length;
    syncMasterCheckbox('master-leftovers-chk', actionableCount, state.selectedLeftovers.size);

    if (state.leftovers.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Öksüz artık dosya bulunamadı.</td></tr>`;
      return;
    }

    tbody.innerHTML = state.leftovers.map(item => `
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

  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Hata: ${escapeHtml(err.message)}</td></tr>`;
  } finally {
    stopLiveProgressPolling();
  }
}

async function executeLeftoversClean() {
  if (state.selectedLeftovers.size === 0) {
    showToast('Silmek için en az bir artık seçin.', 'warning');
    return;
  }

  const itemIds = Array.from(state.selectedLeftovers);
  const payload = { itemIds };
  let reviewResponse;
  try { reviewResponse = await requestOperationReview('/api/leftovers/clean', payload); }
  catch (err) { showToast(`İnceleme hazırlanamadı: ${err.message}`, 'error'); return; }
  showModal(
    reviewResponse.review.title,
    operationReviewHtml(reviewResponse.review),
    [
      { text: 'İptal', class: 'btn-secondary', onClick: hideModal },
      {
        text: 'Sil',
        class: 'btn-danger',
        onClick: async () => {
          const authorized = reviewedPayload(payload, reviewResponse);
          if (!authorized) return;
          hideModal();
          startLiveProgressPolling();
          try {
            const res = await fetch('/api/leftovers/clean', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(authorized)
            });
            const data = await readAPIResponse(res);
            Confetti.launch();
            SoundEffects.playSuccess();
            showToast(operationOutcomeText(data), 'success');
            scanLeftovers();
          } catch (e) {
            showToast(`Hata: ${e.message}`, 'error');
          } finally {
            stopLiveProgressPolling();
          }
        }
      }
    ]
  );
}

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
    : `${data.humanTotal || formatBytes(data.totalBytes)} ölçüldü`;
  cachedBadge?.classList.toggle('hidden', !data.cached);

  if (entries.length === 0) {
    folderBars.innerHTML = `<div class="empty-state">Bu dizinde görünür öğe bulunamadı.</div>`;
  } else {
    folderBars.innerHTML = entries.map(entry => {
      const ready = entry.state === 'ready';
      const scanning = entry.state === 'scanning';
      const failed = entry.state === 'failed';
      const sizeLabel = ready ? (entry.humanBytes || formatBytes(entry.bytes)) : (failed ? 'Okunamadı' : (scanning ? 'Ölçülüyor…' : 'Sırada'));
      const percentLabel = ready ? `${entry.percent || 0}%` : '';
      const rowClass = ready ? 'is-ready' : (failed ? 'is-failed' : 'is-measuring');
      const barClass = ready ? '' : 'indeterminate';
      const width = ready ? Math.max(2, entry.percent || 0) : 100;
      return `
        <div class="folder-bar-item ${rowClass}" data-path="${escapeHtml(entry.path)}" data-directory="${entry.isDirectory}" tabindex="${entry.isDirectory ? '0' : '-1'}" ${entry.isDirectory ? 'role="button"' : ''} title="${entry.isDirectory ? 'Bu dizinin içine gir' : 'Dosya'}">
          <div class="folder-bar-header">
            <span class="folder-name">
              <span class="folder-icon">${entry.isDirectory ? '📁' : '📄'}</span>
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
    tbodyFiles.innerHTML = `<tr><td colspan="4" class="empty-state">${data.isComplete ? 'Bu dizinde eşik üstü dosya yok.' : 'Dosyalar hazır oldukça burada gösterilecek…'}</td></tr>`;
  } else {
    tbodyFiles.innerHTML = data.largestFiles.map(file => `
      <tr>
        <td><strong>${escapeHtml(file.name)}</strong></td>
        <td><span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(file.path)}</span></td>
        <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${escapeHtml(file.humanBytes)}</td>
        <td><button class="btn btn-secondary btn-sm btn-trash-file" data-path="${escapeHtml(file.path)}" title="Çöp Sepetine Taşı">Çöp</button></td>
      </tr>`).join('');

    tbodyFiles.querySelectorAll('.btn-trash-file').forEach(btn => {
      btn.addEventListener('click', async () => {
        const path = btn.dataset.path;
        const payload = { path };
        let reviewResponse;
        try { reviewResponse = await requestOperationReview('/api/analyze/trash', payload); }
        catch (error) { showToast(`İnceleme hazırlanamadı: ${error.message}`, 'error'); return; }
        showModal(reviewResponse.review.title, operationReviewHtml(reviewResponse.review), [
          { text: 'İptal', class: 'btn-secondary', onClick: hideModal },
          { text: 'Çöpe Taşı', class: 'btn-danger', onClick: async () => {
            const authorized = reviewedPayload(payload, reviewResponse);
            if (!authorized) return;
            hideModal();
            startLiveProgressPolling('Dosya Çöp Sepetine taşınıyor…');
            try {
              const response = await fetch('/api/analyze/trash', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(authorized)
              });
              const data = await readAPIResponse(response);
              showToast(operationOutcomeText(data), 'success');
              runDiskAnalyzer(state.currentAnalyzePath, { force: true });
            } catch (error) {
              showToast(`Hata: ${error.message}`, 'error');
              showOperationOutcome('error', error.message);
            } finally { stopLiveProgressPolling(); }
          }}
        ]);
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
      showToast(`Analiz hatası: ${error.message}`, 'error');
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
    folderBars.innerHTML = `<div class="loading-state">Klasör adları okunuyor…</div>`;
    tbodyFiles.innerHTML = `<tr><td colspan="4" class="empty-state">Büyük dosyalar aranıyor...</td></tr>`;
  }

  startLiveProgressPolling('Klasörler listeleniyor…');

  try {
    await fetchAnalyzerSnapshot(path, requestId, { start: true, force: options.force === true });
  } catch (err) {
    if (requestId !== state.analyzerRequestId) return;
    folderBars.innerHTML = `<div class="empty-state">Hata: ${escapeHtml(err.message)}</div>`;
    showOperationOutcome('error', err.message);
    stopLiveProgressPolling();
  }
}

function navigateAnalyzerToParent() {
  const current = state.currentAnalyzePath || document.getElementById('analyzer-path-input')?.value || '~';
  const trimmed = current.trim();
  if (trimmed === '/' || trimmed === '') {
    showToast('Zaten kök dizindesiniz (/)...', 'info');
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
// Tab 7: Project Purge (purge)
// =========================================================

async function scanProjectArtifacts() {
  SoundEffects.playClick();
  const tbody = document.getElementById('tbody-purge-items');
  tbody.innerHTML = `<tr><td colspan="6" class="empty-state">Geliştirici projeleri taranıyor...</td></tr>`;
  startLiveProgressPolling();

  try {
    const res = await fetch('/api/purge');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.purgeArtifacts = data.artifacts || [];
    state.selectedPurgeArtifacts = new Set(state.purgeArtifacts.filter(a => a.selectedByDefault).map(a => a.id));

    renderPurgeArtifacts();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">Hata: ${escapeHtml(err.message)}</td></tr>`;
  } finally {
    stopLiveProgressPolling();
  }
}

function renderPurgeArtifacts() {
  const tbody = document.getElementById('tbody-purge-items');
  let totalBytes = 0;
  state.purgeArtifacts.forEach(a => totalBytes += (a.bytes || 0));

  document.getElementById('purge-total-size').textContent = formatBytes(totalBytes);
  document.getElementById('purge-artifacts-count').textContent = `(${state.purgeArtifacts.length} dizin tespit edildi)`;
  syncMasterCheckbox('master-purge-chk', state.purgeArtifacts.length, state.selectedPurgeArtifacts.size);

  if (state.purgeArtifacts.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">Temizlenecek proje artığı bulunamadı.</td></tr>`;
    return;
  }

  tbody.innerHTML = state.purgeArtifacts.map(art => {
    const isChecked = state.selectedPurgeArtifacts.has(art.id) ? 'checked' : '';
    return `
      <tr>
        <td><input type="checkbox" class="purge-chk" data-id="${art.id}" ${isChecked}></td>
        <td><strong>${escapeHtml(art.projectName)}</strong></td>
        <td><span class="badge-status ${art.restoreClass === 'DEPENDENCY' ? 'badge-yellow' : 'badge-cyan'}">${escapeHtml(art.artifactName)}</span></td>
        <td><span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(art.path)}</span></td>
        <td>${escapeHtml(art.modified || 'Bilinmiyor')}</td>
        <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${formatBytes(art.bytes)}</td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('.purge-chk').forEach(chk => {
    chk.addEventListener('change', (e) => {
      const id = e.target.dataset.id;
      if (e.target.checked) state.selectedPurgeArtifacts.add(id);
      else state.selectedPurgeArtifacts.delete(id);
      syncMasterCheckbox('master-purge-chk', state.purgeArtifacts.length, state.selectedPurgeArtifacts.size);
    });
  });
}

async function executePurge() {
  if (state.selectedPurgeArtifacts.size === 0) {
    showToast('Silinecek en az bir proje dizini seçin.', 'warning');
    return;
  }

  const selected = state.purgeArtifacts.filter(a => state.selectedPurgeArtifacts.has(a.id));
  const payload = { paths: selected.map(s => s.path) };
  let reviewResponse;
  try { reviewResponse = await requestOperationReview('/api/purge', payload); }
  catch (err) { showToast(`İnceleme hazırlanamadı: ${err.message}`, 'error'); return; }

  showModal(
    reviewResponse.review.title,
    operationReviewHtml(reviewResponse.review),
    [
      { text: 'İptal', class: 'btn-secondary', onClick: hideModal },
      {
        text: 'Çöpe Taşı',
        class: 'btn-danger',
        onClick: async () => {
          const authorized = reviewedPayload(payload, reviewResponse);
          if (!authorized) return;
          hideModal();
          startLiveProgressPolling();
          try {
            const res = await fetch('/api/purge', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(authorized)
            });
            const data = await readAPIResponse(res);
            Confetti.launch();
            SoundEffects.playSuccess();
            showToast(operationOutcomeText(data), 'success');
            scanProjectArtifacts();
          } catch (e) {
            showToast(`Hata: ${e.message}`, 'error');
          } finally {
            stopLiveProgressPolling();
          }
        }
      }
    ]
  );
}

// =========================================================
// Tab 8: Developer Caches (developer-caches)
// =========================================================

async function scanDeveloperCaches() {
  SoundEffects.playClick();
  const tbody = document.getElementById('tbody-devcaches');
  tbody.innerHTML = `<tr><td colspan="6" class="empty-state">Geliştirici önbellekleri taranıyor...</td></tr>`;
  startLiveProgressPolling();

  try {
    const res = await fetch('/api/developer/caches');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.devCaches = data.items || [];
    state.selectedDevCaches = new Set(state.devCaches.filter(i => i.risk !== 'MANUAL').map(i => i.id));

    document.getElementById('devcaches-total-size').textContent = data.humanTotal || formatBytes(data.totalBytes);
    document.getElementById('devcaches-count').textContent = `(${state.devCaches.length} önbellek)`;
    const actionableCount = state.devCaches.filter(item => item.risk !== 'MANUAL').length;
    syncMasterCheckbox('master-devcaches-chk', actionableCount, state.selectedDevCaches.size);

    if (state.devCaches.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-state">Geliştirici önbelleği bulunamadı.</td></tr>`;
      return;
    }

    tbody.innerHTML = state.devCaches.map(item => `
      <tr>
        <td><input type="checkbox" class="devcache-chk" data-id="${item.id}" ${item.risk === 'MANUAL' ? 'disabled' : 'checked'}></td>
        <td><strong>${escapeHtml(item.label)}</strong></td>
        <td><span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(item.path || 'Komut')}</span></td>
        <td><span class="badge-status">${escapeHtml(item.risk)}</span></td>
        <td><span style="font-size: 11.5px; color: var(--text-dim);">${escapeHtml(item.reason)}</span></td>
        <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${escapeHtml(item.humanBytes)}</td>
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
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">Hata: ${escapeHtml(err.message)}</td></tr>`;
  } finally {
    stopLiveProgressPolling();
  }
}

async function executeDeveloperCachesClean() {
  if (state.selectedDevCaches.size === 0) {
    showToast('Temizlenecek en az bir önbellek seçin.', 'warning');
    return;
  }

  const itemIds = Array.from(state.selectedDevCaches);
  const payload = { itemIds };
  let reviewResponse;
  try { reviewResponse = await requestOperationReview('/api/developer/caches/clean', payload); }
  catch (err) { showToast(`İnceleme hazırlanamadı: ${err.message}`, 'error'); return; }
  showModal(
    reviewResponse.review.title,
    operationReviewHtml(reviewResponse.review),
    [
      { text: 'İptal', class: 'btn-secondary', onClick: hideModal },
      {
        text: 'Temizle',
        class: 'btn-danger',
        onClick: async () => {
          const authorized = reviewedPayload(payload, reviewResponse);
          if (!authorized) return;
          hideModal();
          startLiveProgressPolling();
          try {
            const res = await fetch('/api/developer/caches/clean', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(authorized)
            });
            const data = await readAPIResponse(res);
            Confetti.launch();
            SoundEffects.playSuccess();
            showToast(operationOutcomeText(data), 'success');
            scanDeveloperCaches();
          } catch (e) {
            showToast(`Hata: ${e.message}`, 'error');
          } finally {
            stopLiveProgressPolling();
          }
        }
      }
    ]
  );
}

// Developer Item Details & Removal Modal
function showDeveloperItemModal(item, onRefresh) {
  SoundEffects.playClick();
  const title = item.title || `${item.language || ''} ${item.version || ''}`.trim() || 'Geliştirici Bileşeni';

  let statusHtml = '';
  if (item.isActive) {
    statusHtml = `<span class="badge-status badge-green">AKTİF</span> <span style="font-size: 12px; color: var(--text-dim); margin-left: 6px;">Şu anda sistem veya kabuk tarafından varsayılan olarak kullanılıyor.</span>`;
  } else if (item.removable) {
    statusHtml = `<span class="badge-status badge-yellow">Kaldırılabilir</span> <span style="font-size: 12px; color: var(--text-dim); margin-left: 6px;">Paket yöneticisi (${escapeHtml(item.manager)}) üzerinden güvenle kaldırılabilir.</span>`;
  } else {
    statusHtml = `<span class="badge-status">Korumalı</span> <span style="font-size: 12px; color: var(--text-dim); margin-left: 6px;">${escapeHtml(item.protectedReason || 'Sistem tarafından korunuyor')}</span>`;
  }

  const html = `
    <div style="display: flex; flex-direction: column; gap: 14px; font-size: 13px;">
      <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border-glass); padding-bottom: 10px;">
        <strong style="font-size: 15px; color: var(--text-main);">${escapeHtml(title)}</strong>
        <span class="badge-status badge-cyan">${escapeHtml(item.manager)}</span>
      </div>

      <div style="display: grid; grid-template-columns: 120px 1fr; gap: 9px 14px; align-items: baseline;">
        <span class="text-muted">Kategori:</span>
        <span><strong>${escapeHtml((item.category || 'GELİŞTİRİCİ').toUpperCase())}</strong></span>

        ${item.version ? `
          <span class="text-muted">Sürüm:</span>
          <span style="font-family: var(--font-mono); font-weight: 600;">${escapeHtml(item.version)}</span>
        ` : ''}

        <span class="text-muted">Paket Yöneticisi:</span>
        <span>${escapeHtml(item.manager)}</span>

        <span class="text-muted">Kapladığı Alan:</span>
        <strong class="highlight-cyan" style="font-family: var(--font-mono);">${escapeHtml(item.humanBytes || formatBytes(item.bytes || 0))}</strong>

        <span class="text-muted">Kurulum Yolu:</span>
        <span style="font-family: var(--font-mono); font-size: 11.5px; word-break: break-all; background: rgba(255,255,255,0.03); padding: 5px 8px; border-radius: 4px; border: 1px solid var(--border-glass);">
          ${escapeHtml(item.path)}
        </span>

        <span class="text-muted">Durum:</span>
        <div>${statusHtml}</div>

        ${item.note ? `
          <span class="text-muted">Açıklama:</span>
          <span style="color: var(--text-dim);">${escapeHtml(item.note)}</span>
        ` : ''}
      </div>
    </div>
  `;

  const buttons = [
    { text: 'Kapat', class: 'btn-secondary', onClick: hideModal }
  ];

  if (item.removable && !item.isActive) {
    buttons.push({
      text: 'Bu Öğeyi Kaldır (Uninstall)',
      class: 'btn-danger',
      onClick: async () => {
        const payload = { category: item.category, id: item.id };
        let reviewResponse;
        try { reviewResponse = await requestOperationReview('/api/developer/remove', payload); }
        catch (e) { showToast(`İnceleme hazırlanamadı: ${e.message}`, 'error'); return; }
        showModal(reviewResponse.review.title, operationReviewHtml(reviewResponse.review), [
          { text: 'İptal', class: 'btn-secondary', onClick: hideModal },
          { text: 'Manager ile Kaldır', class: 'btn-danger', onClick: async () => {
            const authorized = reviewedPayload(payload, reviewResponse);
            if (!authorized) return;
            hideModal();
            startLiveProgressPolling(`${title} kaldırılıyor…`);
            try {
              const res = await fetch('/api/developer/remove', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(authorized)
              });
              const resData = await readAPIResponse(res);
              Confetti.launch(); SoundEffects.playSuccess();
              showToast(`${title} kaldırıldı · ${operationOutcomeText(resData)}`, 'success');
              if (typeof onRefresh === 'function') await onRefresh();
            } catch (e) {
              showToast(`Kaldırma başarısız: ${e.message}`, 'error'); showOperationOutcome('error', e.message);
            } finally { stopLiveProgressPolling(); }
          }}
        ]);
      }
    });
  }

  showModal(`Bileşen Detayı: ${title}`, html, buttons);
}

// Developer Runtimes & Languages
async function scanDeveloperRuntimes() {
  SoundEffects.playClick();
  const tbody = document.getElementById('tbody-devruntimes');
  const previousItems = state.developerRuntimes || [];
  beginCollectionRefresh(tbody, previousItems, 6, 'Çalışma zamanları taranıyor...');
  startLiveProgressPolling('Çalışma zamanları taranıyor…');

  try {
    const res = await fetch('/api/developer/runtimes');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const items = data.items || [];
    const changed = collectionFingerprint(previousItems) !== collectionFingerprint(items);
    state.developerRuntimes = items;
    document.getElementById('devruntimes-total-size').textContent = data.humanTotal || formatBytes(data.totalBytes);
    document.getElementById('devruntimes-count').textContent = `(${items.length} çalışma zamanı tespit edildi)`;

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-state">Yüklü çalışma zamanı bulunamadı.</td></tr>`;
      return;
    }

    if (!changed && previousItems.length) return;
    tbody.innerHTML = items.map((item, idx) => `
      <tr class="clickable-row" data-idx="${idx}" data-item-id="${escapeHtml(item.id || item.path)}" title="Detayları görüntülemek ve kaldırmak için tıklayın">
        <td><strong>${escapeHtml(item.language)}</strong></td>
        <td><span style="font-family: var(--font-mono); font-weight: 600;">${escapeHtml(item.version)}</span></td>
        <td><span class="badge-status">${escapeHtml(item.manager)}</span></td>
        <td><span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(item.path)}</span></td>
        <td><span class="badge-status ${item.isActive ? 'badge-green' : (item.removable ? 'badge-yellow' : '')}">${item.isActive ? 'AKTİF' : (item.removable ? 'Kaldırılabilir' : 'Korumalı')}</span></td>
        <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${escapeHtml(item.humanBytes)}</td>
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
    if (!previousItems.length) tbody.innerHTML = `<tr><td colspan="6" class="empty-state">Hata: ${escapeHtml(err.message)}</td></tr>`;
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
  beginCollectionRefresh(tbody, previousItems, 5, 'Sanal ortamlar taranıyor...');
  startLiveProgressPolling('Sanal ortamlar taranıyor…');

  try {
    const res = await fetch('/api/developer/environments');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const items = data.items || [];
    const changed = collectionFingerprint(previousItems) !== collectionFingerprint(items);
    state.developerEnvironments = items;
    document.getElementById('devenvironments-total-size').textContent = data.humanTotal || formatBytes(data.totalBytes);
    document.getElementById('devenvironments-count').textContent = `(${items.length} ortam tespit edildi)`;

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Sanal ortam bulunamadı.</td></tr>`;
      return;
    }

    if (!changed && previousItems.length) return;
    tbody.innerHTML = items.map((item, idx) => `
      <tr class="clickable-row" data-idx="${idx}" data-item-id="${escapeHtml(item.id || item.path)}" title="Detayları görüntülemek ve kaldırmak için tıklayın">
        <td><strong>${escapeHtml(item.title)}</strong></td>
        <td><span class="badge-status">${escapeHtml(item.manager)}</span></td>
        <td><span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(item.path)}</span></td>
        <td><span style="font-size: 11.5px; color: var(--text-dim);">${escapeHtml(item.note || '-')}</span></td>
        <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${escapeHtml(item.humanBytes)}</td>
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
    if (!previousItems.length) tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Hata: ${escapeHtml(err.message)}</td></tr>`;
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
  beginCollectionRefresh(tbody, previousItems, 5, 'Global CLI araçları taranıyor...');
  startLiveProgressPolling('Global CLI araçları taranıyor…');

  try {
    const res = await fetch('/api/developer/tools');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const items = data.items || [];
    const changed = collectionFingerprint(previousItems) !== collectionFingerprint(items);
    state.developerTools = items;
    document.getElementById('devtools-total-size').textContent = data.humanTotal || formatBytes(data.totalBytes);
    document.getElementById('devtools-count').textContent = `(${items.length} araç tespit edildi)`;

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Global CLI aracı bulunamadı.</td></tr>`;
      return;
    }

    if (!changed && previousItems.length) {
      showToast('Global CLI araçlarında değişiklik yok.', 'info');
      return;
    }

    tbody.innerHTML = items.map((item, idx) => `
      <tr class="clickable-row" data-idx="${idx}" data-item-id="${escapeHtml(item.id || item.path)}" title="Detayları görüntülemek ve kaldırmak için tıklayın">
        <td><strong>${escapeHtml(item.title)}</strong></td>
        <td><span class="badge-status">${escapeHtml(item.manager)}</span></td>
        <td><span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(item.path)}</span></td>
        <td><span style="font-size: 11.5px; color: var(--text-dim);">${escapeHtml(item.note || '-')}</span></td>
        <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${escapeHtml(item.humanBytes)}</td>
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
    if (!previousItems.length) tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Hata: ${escapeHtml(err.message)}</td></tr>`;
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
  beginCollectionRefresh(tbody, previousItems, 5, 'SDK ve simülatörler taranıyor...');
  startLiveProgressPolling('SDK ve simülatörler taranıyor…');

  try {
    const res = await fetch('/api/developer/sdks');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const items = data.items || [];
    const changed = collectionFingerprint(previousItems) !== collectionFingerprint(items);
    state.developerSDKs = items;
    document.getElementById('devsdks-total-size').textContent = data.humanTotal || formatBytes(data.totalBytes);
    document.getElementById('devsdks-count').textContent = `(${items.length} SDK/Simülatör tespit edildi)`;

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">SDK veya simülatör bulunamadı.</td></tr>`;
      return;
    }

    if (!changed && previousItems.length) return;
    tbody.innerHTML = items.map((item, idx) => `
      <tr class="clickable-row" data-idx="${idx}" data-item-id="${escapeHtml(item.id || item.path)}" title="Detayları görüntülemek ve kaldırmak için tıklayın">
        <td><strong>${escapeHtml(item.title)}</strong></td>
        <td><span class="badge-status">${escapeHtml(item.manager)}</span></td>
        <td><span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(item.path)}</span></td>
        <td><span style="font-size: 11.5px; color: var(--text-dim);">${escapeHtml(item.note || '-')}</span></td>
        <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${escapeHtml(item.humanBytes)}</td>
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
    if (!previousItems.length) tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Hata: ${escapeHtml(err.message)}</td></tr>`;
    showOperationOutcome('error', err.message);
  } finally {
    endCollectionRefresh(tbody);
    stopLiveProgressPolling();
  }
}

// =========================================================
// More Tools: Snapshots
// =========================================================

async function fetchSnapshotsList() {
  SoundEffects.playClick();
  const box = document.getElementById('snapshots-list-box');
  box.textContent = 'Snapshot listesi alınıyor...';
  startLiveProgressPolling();

  try {
    const res = await fetch('/api/snapshots');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    box.textContent = data.raw || 'Hiç anlık görüntü bulunamadı.';
  } catch (err) {
    box.textContent = `Hata: ${err.message}`;
  } finally {
    stopLiveProgressPolling();
  }
}

async function executeSnapshotThin() {
  const pill = document.querySelector('.snapshot-thin-pill.active');
  const targetGB = parseInt(pill ? pill.dataset.gb : '10', 10);
  const payload = { targetGB };
  let reviewResponse;
  try { reviewResponse = await requestOperationReview('/api/snapshots/thin', payload); }
  catch (err) { showToast(`İnceleme hazırlanamadı: ${err.message}`, 'error'); return; }

  showModal(
    reviewResponse.review.title,
    operationReviewHtml(reviewResponse.review),
    [
      { text: 'İptal', class: 'btn-secondary', onClick: hideModal },
      {
        text: 'Daraltmayı Başlat',
        class: 'btn-danger',
        onClick: async () => {
          const authorized = reviewedPayload(payload, reviewResponse);
          if (!authorized) return;
          hideModal();
          startLiveProgressPolling();
          try {
            const res = await fetch('/api/snapshots/thin', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(authorized)
            });
            const data = await readAPIResponse(res);
            SoundEffects.playSuccess();
            const observed = data.observedFreeBytesDelta === null || data.observedFreeBytesDelta === undefined
              ? 'gözlenen fark ölçülemedi'
              : `gözlenen boş alan ${formatBytes(Math.abs(data.observedFreeBytesDelta))} ${data.observedFreeBytesDelta >= 0 ? 'arttı' : 'azaldı'}`;
            showToast(`Snapshot daraltma isteği tamamlandı · gerçek manager etkisi bilinmiyor · ${observed} (DeepClean’e kesin atfedilemez)`, 'success');
            fetchSnapshotsList();
          } catch (e) {
            showToast(`Hata: ${e.message}`, 'error');
          } finally {
            stopLiveProgressPolling();
          }
        }
      }
    ]
  );
}

// =========================================================
// Tab 10: Mac Optimization (optimize)
// =========================================================

async function fetchOptimizationTasks() {
  const container = document.getElementById('optimize-tasks-grid');
  try {
    const res = await fetch('/api/optimize');
    const data = await readAPIResponse(res);
    renderOptimizationTasks(data.tasks || []);
  } catch (err) {
    container.innerHTML = `<div class="empty-state">Görevler alınamadı: ${escapeHtml(err.message)}</div>`;
  }
}

function renderOptimizationTasks(tasks) {
  const container = document.getElementById('optimize-tasks-grid');
  if (tasks.length === 0) {
    container.innerHTML = `<div class="empty-state">Kullanılabilir optimizasyon görevi bulunamadı.</div>`;
    return;
  }

  container.innerHTML = tasks.map(task => `
    <div class="task-card" data-task-id="${task.id}">
      <div class="task-head">
        <div class="task-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
          </svg>
        </div>
        <div class="task-info">
          <h4>${escapeHtml(task.title)}</h4>
          <p>${escapeHtml(task.subtitle)}</p>
        </div>
      </div>
      <div class="task-footer">
        <span class="badge-status ${task.risk === 'SAFE' ? 'live-status' : ''}">${escapeHtml(task.risk)}</span>
        <button class="btn btn-secondary btn-sm btn-run-task" data-id="${task.id}">Çalıştır</button>
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
  let reviewResponse;
  try { reviewResponse = await requestOperationReview('/api/optimize/run', payload); }
  catch (err) { showToast(`İnceleme hazırlanamadı: ${err.message}`, 'error'); return; }
  showModal(reviewResponse.review.title, operationReviewHtml(reviewResponse.review), [
    { text: 'İptal', class: 'btn-secondary', onClick: hideModal },
    { text: 'Görevi Çalıştır', class: 'btn-danger', onClick: async () => {
      const authorized = reviewedPayload(payload, reviewResponse);
      if (!authorized) return;
      hideModal(); startLiveProgressPolling();
      try {
        const res = await fetch('/api/optimize/run', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(authorized)
        });
        const data = await readAPIResponse(res);
        SoundEffects.playSuccess(); showToast(`Görev tamamlandı: ${data.message || 'Başarılı'}`, 'success');
      } catch (err) { showToast(`Hata: ${err.message}`, 'error'); }
      finally { stopLiveProgressPolling(); }
    }}
  ]);
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
    showToast(`Doktor raporu alınamadı: ${e.message}`, 'error');
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
    document.getElementById('hist-last-run').textContent = data.lastOperationDate || 'Hiç yapılmadı';

    const tbody = document.getElementById('tbody-history');
    if (!data.entries || data.entries.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Kayıtlı geçmiş işlem bulunamadı.</td></tr>`;
      return;
    }

    tbody.innerHTML = data.entries.slice(0, 60).map(e => `
      <tr>
        <td>${escapeHtml(e.date || '')}</td>
        <td><span class="badge-status">${escapeHtml(e.action || 'clean')}</span></td>
        <td><strong>${escapeHtml(e.label || e.category || 'İşlem özeti')}</strong></td>
        <td style="font-family: var(--font-mono);">${formatBytes(e.estimatedReclaimedBytes || 0)}</td>
        <td><span class="highlight-green">${escapeHtml(e.result || 'success')}</span></td>
      </tr>
    `).join('');
  } catch (e) {}
}

// =========================================================
// Tab 13: Settings & Whitelist (whitelist)
// =========================================================

async function fetchWhitelist() {
  try {
    const res = await fetch('/api/whitelist');
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById('whitelist-textarea').value = (data.lines || []).join('\n');
  } catch (e) {}
}

async function saveWhitelist() {
  SoundEffects.playClick();
  const text = document.getElementById('whitelist-textarea').value;
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);

  try {
    const res = await fetch('/api/whitelist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lines })
    });
    await readAPIResponse(res);
    showToast('Beyaz liste ayarları kaydedildi.', 'success');
  } catch (e) {
    showToast(`Kayıt hatası: ${e.message}`, 'error');
  }
}

// =========================================================
// Shared operation review
// =========================================================

async function requestOperationReview(endpoint, payload) {
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...payload, reviewOnly: true })
  });
  return readAPIResponse(response);
}

function operationReviewHtml(review) {
  const items = (review.items || []).map(item => `
    <li style="margin-bottom:10px;">
      <strong>[${escapeHtml(item.risk)}] ${escapeHtml(item.label)}</strong><br>
      <span style="font-family:var(--font-mono);font-size:11px;word-break:break-all;">${escapeHtml(item.target)}</span><br>
      <span class="text-muted">${escapeHtml(item.action)} · ${escapeHtml(item.reason)}</span>
      ${item.requires_app_closed ? `<br><span class="badge-status badge-yellow">Önce kapat: ${escapeHtml(item.requires_app_closed)}</span>` : ''}
      ${item.user_data ? '<br><span class="badge-status badge-yellow">USER DATA / AÇIK OPT-IN</span>' : ''}
    </li>`).join('');
  const extra = review.requiresExtraOptIn ? `
    <label style="display:flex;gap:8px;align-items:flex-start;margin-top:14px;">
      <input type="checkbox" id="review-extra-opt-in">
      <span>USER DATA / MANUAL etkisini anladım ve bu exact seçimi ayrıca onaylıyorum.</span>
    </label>` : '';
  return `
    <p>${escapeHtml(review.impact)}</p>
    <div style="margin:10px 0;"><strong>${review.items.length} işlem · tarama tahmini ${escapeHtml(review.humanEstimated)}</strong></div>
    <ul style="max-height:320px;overflow:auto;padding-left:20px;">${items}</ul>
    <p style="font-size:11.5px;color:var(--text-dim);">${escapeHtml(review.estimateNote)}</p>
    <p style="font-size:11.5px;color:var(--text-dim);">Whitelist, path, ownership, symlink ve çalışan uygulama kontrolleri yürütmeden hemen önce tekrar yapılır.</p>
    ${extra}`;
}

function operationOutcomeText(result) {
  if (result.dryRun) return `Tarama tahmini ${result.humanScannedEstimate || formatBytes(result.scannedEstimatedBytes || 0)} · değişiklik yapılmadı`;
  const parts = [
    `İşlenen hedef tahmini ${result.humanProcessedEstimate || formatBytes(result.processedEstimatedBytes || 0)}`,
    `tahmini geri kazanım ${result.humanEstimatedReclaimed || formatBytes(result.estimatedReclaimedBytes || 0)}`
  ];
  if (Number(result.trashMovedEstimatedBytes || 0) > 0) {
    parts.push(`Trash'e taşınan ${result.humanTrashMovedEstimate || formatBytes(result.trashMovedEstimatedBytes)} (alan boşalmadı)`);
  }
  if (Number(result.unknownReclaimCount || 0) > 0) parts.push(`${result.unknownReclaimCount} manager etkisi bilinmiyor`);
  if (result.observedFreeBytesDelta === null || result.observedFreeBytesDelta === undefined) {
    parts.push('gözlenen boş alan farkı ölçülemedi');
  } else {
    parts.push(`gözlenen boş alan ${result.humanObservedFreeDelta} ${result.observedFreeDirection === 'decrease' ? 'azaldı' : 'arttı'} (DeepClean’e kesin atfedilemez)`);
  }
  return parts.join(' · ');
}

function reviewedPayload(payload, reviewResponse) {
  const needsExtra = Boolean(reviewResponse.review.requiresExtraOptIn);
  const extraOptIn = Boolean(document.getElementById('review-extra-opt-in')?.checked);
  if (needsExtra && !extraOptIn) {
    showToast('USER DATA / MANUAL seçimi için ek onay kutusunu işaretleyin.', 'warning');
    return null;
  }
  return { ...payload, reviewToken: reviewResponse.reviewToken, extraOptIn };
}

// =========================================================
// Modal Helper
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

// =========================================================
// DOM Ready & Event Setup
// =========================================================

document.addEventListener('DOMContentLoaded', () => {
  document.documentElement.setAttribute('data-theme', state.theme);
  const themeSelect = document.getElementById('theme-selector-setting');
  if (themeSelect) themeSelect.value = state.theme;
  const soundSetting = document.getElementById('chk-sound-setting');
  if (soundSetting) soundSetting.checked = state.soundEnabled;

  document.querySelectorAll('[data-log-service]').forEach(button => {
    button.addEventListener('click', () => toggleInPageLogs(button.dataset.logService));
  });

  // Sidebar navigation
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
      SoundEffects.playClick();
      const tab = item.dataset.tab;
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      document.querySelectorAll('.nav-item').forEach(n => n.removeAttribute('aria-current'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

      item.classList.add('active');
      item.setAttribute('aria-current', 'page');
      const targetPane = document.getElementById(`pane-${tab}`);
      if (targetPane) targetPane.classList.add('active');
      state.activeTab = tab;

      // Only lazy load static settings / metadata; DO NOT auto-run scans without user action
      if (tab === 'optimize' && (!state.optimizeTasks || state.optimizeTasks.length === 0)) fetchOptimizationTasks();
      if (tab === 'more') {
        const activeMoreTab = document.querySelector('#pane-more .subnav-pill.active')?.dataset.moretab || 'leftovers';
        if (activeMoreTab === 'history' && (!state.history || state.history.length === 0)) fetchHistory();
        if (activeMoreTab === 'whitelist' && (!state.whitelist || state.whitelist.length === 0)) fetchWhitelist();
      }
    });
  });

  // Developer Tools sub-navigation pills
  document.querySelectorAll('#pane-developer .subnav-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      SoundEffects.playClick();
      const devtab = pill.dataset.devtab;
      document.querySelectorAll('#pane-developer .subnav-pill').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('#pane-developer .sub-pane').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      const targetSubPane = document.getElementById(`subpane-dev-${devtab}`);
      if (targetSubPane) targetSubPane.classList.add('active');
    });
  });

  // More Tools sub-navigation pills
  document.querySelectorAll('#pane-more .subnav-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      SoundEffects.playClick();
      const moretab = pill.dataset.moretab;
      document.querySelectorAll('#pane-more .subnav-pill').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('#pane-more .sub-pane').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      const targetSubPane = document.getElementById(`subpane-more-${moretab}`);
      if (targetSubPane) targetSubPane.classList.add('active');
      if (moretab === 'history' && (!state.history || state.history.length === 0)) fetchHistory();
      if (moretab === 'whitelist' && (!state.whitelist || state.whitelist.length === 0)) fetchWhitelist();
    });
  });

  // Sound toggle button in header
  const soundBtn = document.getElementById('sound-toggle');
  soundBtn?.addEventListener('click', () => {
    state.soundEnabled = !state.soundEnabled;
    localStorage.setItem('deepclean_sound', state.soundEnabled ? 'on' : 'off');
    soundBtn.querySelector('.icon-sound-on').classList.toggle('hidden', !state.soundEnabled);
    soundBtn.querySelector('.icon-sound-off').classList.toggle('hidden', state.soundEnabled);
    document.getElementById('chk-sound-setting').checked = state.soundEnabled;
    SoundEffects.playClick();
    showToast(`Ses efektleri ${state.soundEnabled ? 'açıldı' : 'kapatıldı'}.`, 'info');
  });

  soundSetting?.addEventListener('change', event => {
    state.soundEnabled = event.target.checked;
    localStorage.setItem('deepclean_sound', state.soundEnabled ? 'on' : 'off');
    soundBtn?.querySelector('.icon-sound-on')?.classList.toggle('hidden', !state.soundEnabled);
    soundBtn?.querySelector('.icon-sound-off')?.classList.toggle('hidden', state.soundEnabled);
  });

  // Theme toggle button in header
  document.getElementById('theme-btn')?.addEventListener('click', () => {
    const themes = ['dark', 'midnight', 'cyber', 'light'];
    let nextIdx = (themes.indexOf(state.theme) + 1) % themes.length;
    state.theme = themes[nextIdx];
    document.documentElement.setAttribute('data-theme', state.theme);
    localStorage.setItem('deepclean_theme', state.theme);
    if (themeSelect) themeSelect.value = state.theme;
    SoundEffects.playClick();
  });

  if (themeSelect) {
    themeSelect.addEventListener('change', (e) => {
      state.theme = e.target.value;
      document.documentElement.setAttribute('data-theme', state.theme);
      localStorage.setItem('deepclean_theme', state.theme);
    });
  }

  // Profile pills in Smart Clean
  document.querySelectorAll('.profile-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      SoundEffects.playClick();
      document.querySelectorAll('.profile-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
    });
  });

  // Installer age pills
  document.querySelectorAll('.installer-age-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      SoundEffects.playClick();
      document.querySelectorAll('.installer-age-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      if (state.installers && state.installers.length > 0) {
        scanInstallers();
      }
    });
  });

  // Leftover age pills
  document.querySelectorAll('.leftover-age-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      SoundEffects.playClick();
      document.querySelectorAll('.leftover-age-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      if (state.leftovers && state.leftovers.length > 0) {
        scanLeftovers();
      }
    });
  });

  // Snapshot thin pills
  document.querySelectorAll('.snapshot-thin-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      SoundEffects.playClick();
      document.querySelectorAll('.snapshot-thin-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
    });
  });

  // Dashboard quick jump to Clean
  document.getElementById('dash-quick-scan-btn')?.addEventListener('click', () => {
    document.querySelector('.nav-item[data-tab="cleaner"]')?.click();
  });

  // Cleaner tab events
  document.getElementById('btn-start-scan')?.addEventListener('click', runSmartScan);
  document.getElementById('btn-execute-clean')?.addEventListener('click', executeClean);
  document.getElementById('btn-select-all')?.addEventListener('click', () => {
    if (state.currentScan) {
      state.selectedCleanItems = new Set(state.currentScan.items.filter(i => i.risk !== 'MANUAL').map(i => i.id));
      document.querySelectorAll('#tbody-clean-items .item-chk:not(:disabled)').forEach(c => c.checked = true);
      updateSelectedCleanStats();
    }
  });
  document.getElementById('btn-deselect-all')?.addEventListener('click', () => {
    state.selectedCleanItems.clear();
    document.querySelectorAll('#tbody-clean-items .item-chk').forEach(c => c.checked = false);
    updateSelectedCleanStats();
  });
  document.getElementById('master-clean-chk')?.addEventListener('change', event => {
    const enabled = state.currentScan?.items.filter(i => i.risk !== 'MANUAL') || [];
    state.selectedCleanItems = event.target.checked ? new Set(enabled.map(i => i.id)) : new Set();
    document.querySelectorAll('#tbody-clean-items .item-chk:not(:disabled)').forEach(c => { c.checked = event.target.checked; });
    updateSelectedCleanStats();
  });

  // App tab events
  document.getElementById('btn-refresh-apps')?.addEventListener('click', fetchApplications);
  document.getElementById('search-apps-input')?.addEventListener('input', renderAppsList);
  document.getElementById('sort-apps-select')?.addEventListener('change', renderAppsList);
  document.getElementById('btn-uninstall-selected-app')?.addEventListener('click', uninstallSelectedApp);

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

  // Disk Analyzer events
  document.getElementById('btn-run-analyzer')?.addEventListener('click', () => runDiskAnalyzer());
  document.getElementById('btn-analyzer-parent')?.addEventListener('click', () => navigateAnalyzerToParent());
  document.querySelectorAll('.btn-quick-path').forEach(btn => {
    btn.addEventListener('click', () => runDiskAnalyzer(btn.dataset.path));
  });

  // Project purge events
  document.getElementById('btn-scan-projects')?.addEventListener('click', scanProjectArtifacts);
  document.getElementById('btn-execute-purge')?.addEventListener('click', executePurge);
  document.getElementById('btn-purge-select-all')?.addEventListener('click', () => {
    state.selectedPurgeArtifacts = new Set(state.purgeArtifacts.map(a => a.id));
    document.querySelectorAll('#tbody-purge-items .purge-chk').forEach(c => c.checked = true);
  });
  document.getElementById('master-purge-chk')?.addEventListener('change', event => {
    state.selectedPurgeArtifacts = event.target.checked ? new Set(state.purgeArtifacts.map(a => a.id)) : new Set();
    document.querySelectorAll('#tbody-purge-items .purge-chk').forEach(c => { c.checked = event.target.checked; });
  });

  // Developer tools events
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

  // Snapshot events
  document.getElementById('btn-refresh-snapshots')?.addEventListener('click', fetchSnapshotsList);
  document.getElementById('btn-execute-snapshot-thin')?.addEventListener('click', executeSnapshotThin);

  // Optimization events
  document.getElementById('btn-run-all-optimize')?.addEventListener('click', async () => {
    SoundEffects.playClick();
    const payload = {};
    let reviewResponse;
    try { reviewResponse = await requestOperationReview('/api/optimize/run-all', payload); }
    catch (e) { showToast(`İnceleme hazırlanamadı: ${e.message}`, 'error'); return; }
    showModal(reviewResponse.review.title, operationReviewHtml(reviewResponse.review), [
      { text: 'İptal', class: 'btn-secondary', onClick: hideModal },
      { text: 'Tümünü Çalıştır', class: 'btn-danger', onClick: async () => {
        const authorized = reviewedPayload(payload, reviewResponse);
        if (!authorized) return;
        hideModal(); startLiveProgressPolling();
        try {
          const res = await fetch('/api/optimize/run-all', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(authorized)
          });
          const result = await readAPIResponse(res);
          SoundEffects.playSuccess(); showToast(`${result.executed}/${result.total} bakım görevi tamamlandı.`, 'success');
        } catch (e) { showToast(`Hata: ${e.message}`, 'error'); }
        finally { stopLiveProgressPolling(); }
      }}
    ]);
  });

  // Doctor & Settings
  document.getElementById('btn-refresh-doctor')?.addEventListener('click', fetchDoctorReport);
  document.getElementById('btn-save-settings')?.addEventListener('click', saveWhitelist);
  document.getElementById('modal-close-btn')?.addEventListener('click', hideModal);
  document.getElementById('modal-container')?.addEventListener('click', event => {
    if (event.target.id === 'modal-container') hideModal();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') hideModal();
  });

  document.querySelector('.nav-item.active')?.setAttribute('aria-current', 'page');

  // Initial polling
  fetchStatus();
  state.refreshTimer = setInterval(fetchStatus, state.refreshInterval);
  pollLiveProgress();
});
