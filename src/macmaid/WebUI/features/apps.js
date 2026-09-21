/* =========================================================
   MacMaid Pro — Application uninstaller: inventory,
   component review, authorized uninstall
   ========================================================= */

// =========================================================
// Tab 3: App Uninstaller (apps)
// =========================================================

async function fetchApplications() {
  const container = document.getElementById('apps-list-container');
  const previousApps = state.apps || [];
  container.classList.add('is-refreshing');
  container.setAttribute('aria-busy', 'true');
  if (!previousApps.length) container.innerHTML = `<div class="loading-state">${t('apps.action_scanning', 'Scanning Applications...')}</div>`;
  startLiveProgressPolling(t('apps.action_scanning', 'Scanning Applications…'));

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
        removed.textContent = `${t('toast.uninstalled', 'Removed')}: ${app.name}`;
        container.prepend(removed);
      });
      setTimeout(() => {
        container.querySelectorAll('.row-removed').forEach(row => row.remove());
        container.querySelectorAll('.row-added').forEach(row => row.classList.remove('row-added'));
      }, 4500);
    }
  } catch (err) {
    if (!previousApps.length) container.innerHTML = `<div class="empty-state">${t('apps.load_failed', 'Failed to load applications: ')}${escapeHtml(err.message)}</div>`;
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
    container.innerHTML = `<div class="empty-state">${t('apps.empty_search', 'No matching applications found.')}</div>`;
    return;
  }

  container.innerHTML = filtered.map(app => {
    const isSel = state.selectedApp && state.selectedApp.path === app.path ? 'selected' : '';
    const initial = app.name ? app.name.charAt(0).toUpperCase() : '';
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
    img.addEventListener('error', () => { img.parentElement.innerHTML = img.dataset.fallback ? escapeHtml(img.dataset.fallback) : sfSymbol('app'); }, { once: true });
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
  const initial = app.name ? app.name.charAt(0).toUpperCase() : '';
  detailIcon.innerHTML = `<img src="/api/apps/icon?path=${encodeURIComponent(app.path)}" alt="" data-fallback="${escapeHtml(initial)}">`;
  detailIcon.querySelector('img')?.addEventListener('error', event => {
    event.currentTarget.parentElement.innerHTML = event.currentTarget.dataset.fallback ? escapeHtml(event.currentTarget.dataset.fallback) : sfSymbol('app');
  }, { once: true });
  document.getElementById('detail-app-name').textContent = app.name;
  document.getElementById('detail-app-bundle').textContent = app.bundleId || app.path;
  document.getElementById('detail-app-version').textContent = app.version ? `${t('settings.version_label', 'Version')} ${app.version}` : t('apps.no_version', 'No version info');
  document.getElementById('detail-app-size').textContent = formatBytes(app.bytes);

  const leftoversList = document.getElementById('detail-leftovers-list');
  leftoversList.innerHTML = `<div style="padding: 10px; color: var(--text-dim);">${t('apps.searching_leftovers', 'Searching for leftovers...')}</div>`;

  try {
    const res = await fetch(`/api/apps/leftovers?path=${encodeURIComponent(app.path)}&bundleId=${encodeURIComponent(app.bundleId || '')}`);
    const data = await res.json();
    state.appLeftovers = data.leftovers || [];
    document.getElementById('detail-leftovers-count').textContent = `${state.appLeftovers.length} konum`;

    if (state.appLeftovers.length === 0) {
      leftoversList.innerHTML = `<div class="empty-state" style="padding: 15px;">${t('apps.no_extra_leftovers', 'No extra leftovers found. Only application bundle will be removed.')}</div>`;
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
    leftoversList.innerHTML = `<div class="empty-state">${t('apps.leftovers_scan_failed', 'Failed to scan leftovers: ')}${escapeHtml(err.message)}</div>`;
  }
}

async function uninstallSelectedApp() {
  if (!state.selectedApp) return;
  const app = state.selectedApp;
  const payload = { path: app.path, bundleId: app.bundleId, leftoverPaths: state.appLeftovers.map(l => l.path) };
  await reviewedMutation('/api/apps/uninstall', payload, {
    confirmText: t('apps.btn_uninstall', 'Uninstall'),
    onSuccess: async data => {
      Confetti.launch();
      SoundEffects.playSuccess();
      showOutcomeToast(data, `${app.name} ${t('toast.uninstalled', 'uninstalled')} · `);
      state.selectedApp = null;
      document.getElementById('app-detail-view').classList.add('hidden');
      document.getElementById('app-detail-empty').classList.remove('hidden');
      await fetchApplications();
    },
    onError: e => {
      showOperationOutcome('error', e.message);
      showToast(`${t('toast.uninstall_error', 'Uninstall error: ')}${e.message}`, 'error');
    },
  });
}

document.addEventListener('DOMContentLoaded', () => {
  // App tab events
  document.getElementById('btn-refresh-apps')?.addEventListener('click', fetchApplications);
  document.getElementById('search-apps-input')?.addEventListener('input', renderAppsList);
  document.getElementById('sort-apps-select')?.addEventListener('change', renderAppsList);
  document.getElementById('btn-uninstall-selected-app')?.addEventListener('click', uninstallSelectedApp);
});
