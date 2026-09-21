/* =========================================================
   MacMaid Pro — Settings: whitelist, filesystem permissions,
   privacy report, Homebrew update check
   ========================================================= */

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
    showToast(t('toast.whitelist_saved', 'Whitelist settings saved.'), 'success');
  } catch (e) {
    showToast(`${t('toast.save_error', 'Save error: ')}${e.message}`, 'error');
  }
}

// =========================================================
// Filesystem access & macOS privacy
// =========================================================

function renderPermissionSummary(report) {
  const summary = document.getElementById('permission-summary');
  if (!summary) return;
  const context = t(`settings.permissions_context_${report.launchContext}`, report.launchContext);
  const fda = t(`settings.permissions_fda_${report.fullDiskAccess}`, report.fullDiskAccess);
  const counts = (report.checks || []).reduce((result, check) => {
    if (check.status === 'granted') result.allowed += 1;
    else if (check.status === 'limited') result.limited += 1;
    else if (check.status !== 'not_applicable') result.denied += 1;
    return result;
  }, { allowed: 0, limited: 0, denied: 0 });
  const countText = t('settings.permissions_summary', '{allowed} allowed · {limited} limited · {denied} unavailable')
    .replace('{allowed}', String(counts.allowed))
    .replace('{limited}', String(counts.limited))
    .replace('{denied}', String(counts.denied));
  summary.textContent = `${context} · ${fda} · ${countText}`;
}

async function fetchPermissionReport() {
  const button = document.getElementById('btn-refresh-permissions');
  const summary = document.getElementById('permission-summary');
  if (!summary) return null;
  if (button) button.disabled = true;
  summary.textContent = t('settings.permissions_loading', 'Checking access…');
  try {
    state.permissionReport = await readAPIResponse(await fetch('/api/permissions'));
    renderPermissionSummary(state.permissionReport);
    return state.permissionReport;
  } catch (error) {
    summary.textContent = t('settings.permissions_failed', 'Permission status could not be checked: {error}')
      .replace('{error}', error.message);
    return null;
  } finally {
    if (button) button.disabled = false;
  }
}

function populatePermissionModal(report) {
  const list = document.getElementById('permission-modal-list');
  if (!list) return;
  list.replaceChildren();
  (report.checks || []).forEach(check => {
    const group = document.createElement('div');
    group.className = 'permission-group';
    const row = document.createElement('div');
    row.className = 'permission-row';
    const label = document.createElement('strong');
    label.textContent = t(`settings.permission_${check.id}`, check.id);
    const badge = document.createElement('span');
    badge.className = `permission-badge permission-${check.status}`;
    badge.textContent = t(`settings.permission_${check.status}`, check.status)
      .replace('{accessible}', String(check.accessible ?? 0))
      .replace('{total}', String(check.total ?? 0));
    const actions = document.createElement('div');
    actions.className = 'permission-row-actions';
    const entries = Array.isArray(check.entries) ? [...check.entries] : [];
    if (entries.length) {
      const detailsButton = document.createElement('button');
      detailsButton.className = 'btn btn-secondary btn-sm permission-details-toggle';
      detailsButton.textContent = t('settings.permissions_show_details', 'Show locations');
      actions.appendChild(detailsButton);
      const details = document.createElement('div');
      details.className = 'permission-detail-list hidden';
      entries.sort((left, right) => {
        if (left.status === 'granted' && right.status !== 'granted') return 1;
        if (left.status !== 'granted' && right.status === 'granted') return -1;
        return left.name.localeCompare(right.name);
      }).forEach(entry => {
        const detail = document.createElement('div');
        detail.className = 'permission-detail-row';
        const name = document.createElement('span');
        name.textContent = entry.name;
        const status = document.createElement('span');
        status.className = `permission-badge permission-${entry.status}`;
        status.textContent = t(`settings.permission_${entry.status}`, entry.status);
        detail.append(name, status);
        details.appendChild(detail);
      });
      detailsButton.addEventListener('click', () => {
        const opening = details.classList.contains('hidden');
        if (opening) {
          list.querySelectorAll('.permission-detail-list').forEach(other => other.classList.add('hidden'));
          list.querySelectorAll('.permission-details-toggle').forEach(otherButton => {
            otherButton.textContent = t('settings.permissions_show_details', 'Show locations');
          });
        }
        details.classList.toggle('hidden', !opening);
        detailsButton.textContent = t(
          opening ? 'settings.permissions_hide_details' : 'settings.permissions_show_details',
          opening ? 'Hide locations' : 'Show locations'
        );
      });
      group.append(row, details);
    } else {
      group.appendChild(row);
    }
    if (!['granted', 'not_applicable'].includes(check.status)) {
      const manage = document.createElement('button');
      manage.className = 'btn btn-secondary btn-sm permission-manage-btn';
      manage.textContent = t('settings.permissions_manage_macos', 'Manage in macOS');
      manage.addEventListener('click', openFullDiskAccessSettings);
      actions.appendChild(manage);
    }
    row.append(label, badge, actions);
    list.appendChild(group);
  });
}

async function showPermissionManager() {
  const report = state.permissionReport || await fetchPermissionReport();
  if (!report) return;
  showModal(
    t('settings.permissions_modal_title', 'MacMaid Permissions'),
    `<div class="permission-modal-intro">${t('settings.permissions_modal_intro', 'macOS privacy permissions must be managed in System Settings.')}</div><div class="permission-list" id="permission-modal-list"></div>`,
    [
      { text: t('settings.permissions_close', 'Close'), class: 'btn-secondary', onClick: hideModal },
      { text: t('settings.permissions_refresh', 'Refresh'), class: 'btn-secondary', onClick: async () => {
        const refreshed = await fetchPermissionReport();
        if (refreshed) populatePermissionModal(refreshed);
      }},
      { text: t('settings.permissions_open_fda', 'Open Full Disk Access Settings'), class: 'btn-primary', onClick: openFullDiskAccessSettings },
    ]
  );
  populatePermissionModal(report);
}

async function openFullDiskAccessSettings() {
  try {
    await readAPIResponse(await fetch('/api/permissions/open-full-disk-access', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({})
    }));
    showToast(t('settings.permissions_opened', 'Privacy & Security settings opened.'), 'info');
  } catch (error) {
    showToast(t('settings.permissions_failed', 'Permission status could not be checked: {error}').replace('{error}', error.message), 'error');
  }
}

// =========================================================
// MacMaid Homebrew update
// =========================================================

async function checkMacMaidUpdate() {
  const button = document.getElementById('btn-check-macmaid-update');
  const status = document.getElementById('macmaid-update-status');
  button.disabled = true;
  status.textContent = t('settings.update_checking', 'Checking Homebrew for updates…');
  try {
    const result = await readAPIResponse(await fetch('/api/macmaid/update/check', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({})
    }));
    if (!result.installed) {
      status.textContent = result.reason || t('settings.update_not_brew', 'MacMaid was not installed with Homebrew.');
      return;
    }
    if (!result.available) {
      status.textContent = result.reason || t('settings.update_up_to_date', 'MacMaid is up to date.');
      return;
    }
    status.textContent = t('settings.update_available', 'Update available: {current} → {latest}')
      .replace('{current}', result.installedVersion || 'current')
      .replace('{latest}', result.latestVersion || 'latest');
    await reviewedMutation('/api/macmaid/update', {}, {
      confirmText: t('settings.update_with_brew', 'Update with Homebrew'),
      trackProgress: false,
      onAuthorized: () => { status.textContent = t('settings.update_installing', 'Installing update with Homebrew…'); },
      onSuccess: updated => {
        status.textContent = updated.updated ? t('settings.update_installed', 'Update installed. Restart MacMaid to use the new version.') : (updated.reason || t('settings.update_up_to_date', 'MacMaid is up to date.'));
        showToast(status.textContent, 'success');
      },
      onError: error => {
        status.textContent = t('settings.update_failed', 'Update failed: {error}').replace('{error}', error.message);
        showToast(status.textContent, 'error');
      },
    });
  } catch (error) {
    status.textContent = t('settings.update_check_failed', 'Update check failed: {error}').replace('{error}', error.message);
    showToast(status.textContent, 'error');
  } finally {
    button.disabled = false;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('btn-check-macmaid-update')?.addEventListener('click', checkMacMaidUpdate);
  document.getElementById('btn-save-settings')?.addEventListener('click', saveWhitelist);
  document.getElementById('btn-refresh-permissions')?.addEventListener('click', fetchPermissionReport);
  document.getElementById('btn-manage-permissions')?.addEventListener('click', showPermissionManager);
});
