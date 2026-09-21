/* =========================================================
   MacMaid Pro — API response handling and the single
   review-token mutation gate shared by every feature
   ========================================================= */

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
      ${item.requires_app_closed ? `<br><span class="badge-status badge-yellow">${t('modal.close_first', 'Close first: ')}${escapeHtml(item.requires_app_closed)}</span>` : ''}
      ${item.user_data ? `<br><span class="badge-status badge-yellow">${t('modal.user_data_badge', 'USER DATA / EXPLICIT OPT-IN')}</span>` : ''}
    </li>`).join('');
  const extra = review.requiresExtraOptIn ? `
    <label style="display:flex;gap:8px;align-items:flex-start;margin-top:14px;">
      <input type="checkbox" id="review-extra-opt-in">
      <span>${t('modal.user_data_confirm', 'I understand the impact of USER DATA / MANUAL and explicitly confirm this selection.')}</span>
    </label>` : '';
  return `
    <p>${escapeHtml(review.impact)}</p>
    <div style="margin:10px 0;"><strong>${review.items.length} ${t('modal.actions_scan_est', 'actions · scan estimate')} ${escapeHtml(review.humanEstimated)}</strong></div>
    <ul style="max-height:320px;overflow:auto;padding-left:20px;">${items}</ul>
    <p style="font-size:11.5px;color:var(--text-dim);">${escapeHtml(review.estimateNote)}</p>
    <p style="font-size:11.5px;color:var(--text-dim);">${t('modal.pre_exec_checks', 'Whitelist, path, ownership, symlink, and running app checks are re-evaluated immediately before execution.')}</p>
    ${extra}`;
}

function operationOutcomeText(result) {
  if (result.dryRun) return `${t('outcome.scan_est', 'Scan estimate ')}${result.humanScannedEstimate || formatBytes(result.scannedEstimatedBytes || 0)}${t('outcome.no_changes', ' · no changes made')}`;
  const parts = [
    `${t('outcome.processed_est', 'Processed target estimate ')}${result.humanProcessedEstimate || formatBytes(result.processedEstimatedBytes || 0)}`,
    `${t('outcome.est_reclaim', 'estimated reclaim ')}${result.humanEstimatedReclaimed || formatBytes(result.estimatedReclaimedBytes || 0)}`
  ];
  if (Number(result.trashMovedEstimatedBytes || 0) > 0) {
    parts.push(`${t('outcome.trash_moved', 'Moved to Trash ')}${result.humanTrashMovedEstimate || formatBytes(result.trashMovedEstimatedBytes)}${t('outcome.no_freed', ' (space not reclaimed)')}`);
  }
  if (Number(result.unknownReclaimCount || 0) > 0) parts.push(`${result.unknownReclaimCount}${t('outcome.manager_unknown', ' manager impact unknown')}`);
  if (Number(result.skipped || 0) > 0) parts.push(`${result.skipped} ${t('outcome.skipped_count', 'skipped')}`);
  if (Number(result.failed || 0) > 0) {
    parts.push(`${result.failed} ${t('outcome.failed_count', 'failed')}`);
    const detail = (result.details || []).find(entry => entry && !entry.startsWith('DRY RUN'));
    if (detail) parts.push(detail);
  }
  if (result.observedFreeBytesDelta === null || result.observedFreeBytesDelta === undefined) {
    parts.push(t('outcome.diff_unmeasured', 'observed free space difference unmeasured'));
  } else {
    const dir = result.observedFreeDirection === 'decrease' ? t('common.decreased', 'decreased') : t('common.increased', 'increased');
    parts.push(`${t('more.observed_free_space', 'observed free space ')}${result.humanObservedFreeDelta} ${dir}${t('outcome.not_strictly_macmaid', ' (not strictly attributable to MacMaid)')}`);
  }
  return parts.join(' · ');
}

function showOutcomeToast(result, prefix = '') {
  const failed = Number(result.failed || 0);
  showToast(`${prefix}${operationOutcomeText(result)}`, failed > 0 ? 'warning' : 'success');
}

function reviewedPayload(payload, reviewResponse) {
  const needsExtra = Boolean(reviewResponse.review.requiresExtraOptIn);
  const extraOptIn = Boolean(document.getElementById('review-extra-opt-in')?.checked);
  if (needsExtra && !extraOptIn) {
    showToast(t('toast.extra_opt_in_warn', 'Please check the extra confirmation box for USER DATA / MANUAL selections.'), 'warning');
    return null;
  }
  return { ...payload, reviewToken: reviewResponse.reviewToken, extraOptIn };
}

// Shared review → confirm → POST flow used by every destructive endpoint.
// Callers only supply the confirm label, progress label, and outcome handling.
async function reviewedMutation(endpoint, payload, {
  confirmText,
  progressLabel,
  trackProgress = true,
  buttonId = null,
  onAuthorized = null,
  onSuccess = null,
  onError = null,
  onFinally = null,
} = {}) {
  let reviewResponse;
  try {
    reviewResponse = await requestOperationReview(endpoint, payload);
  } catch (err) {
    showToast(`${t('toast.review_failed', 'Failed to prepare review: ')}${err.message}`, 'error');
    return;
  }
  showModal(reviewResponse.review.title, operationReviewHtml(reviewResponse.review), [
    { text: t('common.cancel', 'Cancel'), class: 'btn-secondary', onClick: hideModal },
    {
      text: confirmText, class: 'btn-danger', onClick: async () => {
        const authorized = reviewedPayload(payload, reviewResponse);
        if (!authorized) return;
        hideModal();
        if (trackProgress) startLiveProgressPolling(progressLabel);
        const actionBtn = buttonId ? document.getElementById(buttonId) : null;
        if (actionBtn) actionBtn.disabled = true;
        if (onAuthorized) onAuthorized(actionBtn);
        try {
          const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(authorized)
          });
          if (onSuccess) await onSuccess(await readAPIResponse(res));
        } catch (err) {
          if (onError) await onError(err);
          else showToast(`${t('toast.error_prefix', 'Error: ')}${err.message}`, 'error');
        } finally {
          if (onFinally) await onFinally(actionBtn);
          if (actionBtn) actionBtn.disabled = false;
          if (trackProgress) stopLiveProgressPolling();
        }
      }
    }
  ]);
}

// =========================================================
// Modal Helper
// =========================================================
