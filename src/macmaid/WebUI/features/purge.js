/* =========================================================
   MacMaid Pro — Project artifact purge: discovery,
   selection, reviewed deletion
   ========================================================= */

// =========================================================
// Tab 7: Project Purge (purge)
// =========================================================

async function scanProjectArtifacts() {
  SoundEffects.playClick();
  const tbody = document.getElementById('tbody-purge-items');
  tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${t('purge.action_scanning_sub', 'Scanning developer projects...')}</td></tr>`;
  startLiveProgressPolling();

  try {
    const res = await fetch('/api/purge');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.purgeArtifacts = data.artifacts || [];
    state.selectedPurgeArtifacts = new Set(state.purgeArtifacts.filter(a => a.selectedByDefault).map(a => a.id));

    renderPurgeArtifacts();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${t('toast.error_prefix', 'Error: ')}${escapeHtml(err.message)}</td></tr>`;
  } finally {
    stopLiveProgressPolling();
  }
}

function formatPurgeModified(value) {
  if (value === null || value === undefined || value === '') return t('common.unknown', 'Unknown');
  const numericValue = Number(value);
  const date = Number.isFinite(numericValue)
    ? new Date(numericValue < 1e12 ? numericValue * 1000 : numericValue)
    : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(state.lang === 'tr' ? 'tr-TR' : 'en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(date);
}

function renderPurgeArtifacts() {
  const tbody = document.getElementById('tbody-purge-items');
  let totalBytes = 0;
  state.purgeArtifacts.forEach(a => totalBytes += (a.bytes || 0));

  document.getElementById('purge-total-size').textContent = formatBytes(totalBytes);
  document.getElementById('purge-artifacts-count').textContent = t('purge.detected_count', '({count} directories detected)')
    .replace('{count}', String(state.purgeArtifacts.length));
  syncMasterCheckbox('master-purge-chk', state.purgeArtifacts.length, state.selectedPurgeArtifacts.size);

  if (state.purgeArtifacts.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${t('purge.empty_projects', 'No project build artifacts found to clean.')}</td></tr>`;
    return;
  }

  tbody.innerHTML = state.purgeArtifacts.map(art => {
    const isChecked = state.selectedPurgeArtifacts.has(art.id) ? 'checked' : '';
    return `
      <tr>
        <td><input type="checkbox" class="purge-chk" data-id="${art.id}" ${isChecked}></td>
        <td><span class="table-label">${escapeHtml(art.projectName)}</span></td>
        <td><span class="table-secondary">${escapeHtml(art.artifactName)}</span></td>
        <td><span class="table-path">${escapeHtml(art.path)}</span></td>
        <td class="table-value">${escapeHtml(formatPurgeModified(art.modified))}</td>
        <td class="table-number">${formatBytes(art.bytes)}</td>
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
    showToast(t('toast.select_project_warn', 'Select at least one project folder to delete.'), 'warning');
    return;
  }

  const selected = state.purgeArtifacts.filter(a => state.selectedPurgeArtifacts.has(a.id));
  const payload = { paths: selected.map(s => s.path) };
  await reviewedMutation('/api/purge', payload, {
    confirmText: t('common.move_to_trash', 'Move to Trash'),
    onSuccess: data => {
      SoundEffects.playSuccess();
      showOutcomeToast(data);
      scanProjectArtifacts();
    },
  });
}

document.addEventListener('DOMContentLoaded', () => {
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
});
