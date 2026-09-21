"""POST route handlers for the MacMaid web UI — reviewed mutations only.

Every destructive endpoint funnels through :func:`_review_gate`, which keeps
generation/fingerprint review-token semantics identical to the pre-split
handler. ``web.py`` imports this module lazily inside ``_route_post``.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .cleaner import Cleaner
from .developer import DeveloperInventory
from .features import (
    OPTIMIZATION_UNAVAILABLE_REASON, OPTIMIZATIONS, ApplicationManager, ProjectPurgeManager,
    RecoveryCenter, apply_macmaid_brew_update, macmaid_brew_update_status, run_optimization,
    thin_snapshots,
)
from .models import ActionType, RiskLevel, ScanResult
from .reporting import FreeSpaceProbe
from .review import (
    analyzer_trash_plan, application_plan, cleanup_plan, developer_plan, issue_review_token,
    macmaid_update_plan, optimization_plan, purge_plan, snapshot_plan, validate_review_token,
)
from .system import human_bytes, run_command, size_of
from .web import ProgressState

if TYPE_CHECKING:
    from .web import MacMaidHandler


def _operation_payload(result) -> dict:
    observed = result.observed_free_bytes_delta
    return dict(
        result.web_dict(), success=result.failed == 0,
        humanFreed=human_bytes(result.freed),
        humanScannedEstimate=human_bytes(result.scanned_estimated_bytes),
        humanProcessedEstimate=human_bytes(result.processed_estimated_bytes),
        humanEstimatedReclaimed=human_bytes(result.freed),
        humanTrashMovedEstimate=human_bytes(result.trash_moved_estimated_bytes),
        humanObservedFreeDelta=None if observed is None else human_bytes(abs(observed)),
        observedFreeDirection=None if observed is None else ("increase" if observed >= 0 else "decrease"),
        reclaimCaveat="Observed free-space change is filesystem-wide and cannot be attributed solely to MacMaid.",
    )

def _review_gate(handler: MacMaidHandler, scope: str, body: dict, plan) -> dict | None:
    state = handler.server.state
    generation = state.generations.get(scope, 0)
    if body.get("reviewOnly") is True:
        token = issue_review_token(state.token, scope, generation, plan)
        with state.lock:
            if len(state.review_tokens) >= 256:
                state.review_tokens.clear()
            state.review_tokens[token] = (scope, generation, plan.fingerprint)
        return {"success": True, "reviewRequired": True, "reviewToken": token, "review": plan.web_dict()}
    provided_token = body.get("reviewToken")
    with state.lock:
        record = state.review_tokens.pop(provided_token, None) if isinstance(provided_token, str) else None
    if record != (scope, generation, plan.fingerprint) or not validate_review_token(state.token, scope, generation, plan, provided_token or ""):
        raise PermissionError("A fresh review of this exact selection is required")
    if plan.requires_extra_opt_in and body.get("extraOptIn") is not True:
        raise PermissionError("Explicit user-data/MANUAL opt-in is required")
    return None

def _known_request_paths(handler: MacMaidHandler, raw: object, known: set[Path], error: str) -> list[Path]:
    """Resolve request path strings to Path objects from server-populated scan state."""
    wanted = list(dict.fromkeys(handler._request_path_key(item) for item in raw)) if isinstance(raw, list) else []
    lookup = {str(item): item for item in known}
    if not wanted or any(key not in lookup for key in wanted):
        raise PermissionError(error)
    return [lookup[key] for key in wanted]

def _select_paths(handler: MacMaidHandler, scan: ScanResult | None, requested: list[str]):
    if scan is not None and not scan.is_complete:
        raise PermissionError("Incomplete scan results cannot be mutated")
    if scan is None or not requested: raise ValueError("No matching latest scan is available")
    wanted = {handler._request_path_key(path) for path in requested}
    chosen = [item for item in scan.items if item.path and str(item.path.absolute()) in wanted and item.risk is not RiskLevel.MANUAL_ONLY and item.action.kind is not ActionType.MANUAL_CACHE_FALLBACK]
    if len(chosen) != len(wanted): raise PermissionError("One or more paths were not present in the latest scan")
    return chosen

def _select_ids(scan: ScanResult | None, requested: list[str]):
    if scan is not None and not scan.is_complete:
        raise PermissionError("Incomplete scan results cannot be mutated")
    if scan is None or not requested: raise ValueError("No matching latest scan is available")
    wanted = set(requested)
    chosen = [item for item in scan.items if item.id in wanted and item.risk is not RiskLevel.MANUAL_ONLY and item.action.kind is not ActionType.MANUAL_CACHE_FALLBACK]
    if len(chosen) != len(wanted): raise PermissionError("One or more items were not present in the latest scan")
    return chosen

def _execute_cleanup(handler: MacMaidHandler, service: str, action: str, items: list, *, apply: bool = True):
    state = handler.server.state
    progress_state = getattr(state, "progress", None) or ProgressState()
    progress_state.start(service, action)

    def report(index: int, total: int, item, outcome: str) -> None:
        phase = {
            "running": "Cleaning",
            "success": "Completed",
            "skipped": "Skipped",
            "failed": "Failed",
        }.get(outcome, "Working")
        completed = index - 1 if outcome == "running" else index
        current = str(item.path) if item.path else item.label
        progress_state.update_items(completed, total, phase, current, item.label)

    try:
        result = Cleaner(state.config).execute(
            items,
            apply=apply,
            assume_yes=True,
            progress=report,
        )
    except Exception:
        progress_state.finish("Cleanup failed", percent=0)
        raise
    succeeded = max(0, len(items) - result.skipped - result.failed)
    progress_state.finish(
        f"Cleanup completed · {succeeded} succeeded · {result.skipped} skipped · {result.failed} failed"
    )
    return result

def _move_items_to_trash_with_progress(
    handler: MacMaidHandler,
    service: str,
    action: str,
    requested: list[Path],
    estimates: dict[Path, int],
    *,
    on_moved=None,
) -> list[str]:
    state = handler.server.state
    progress_state = getattr(state, "progress", None) or ProgressState()
    progress_state.start(service, action)
    cleaner = Cleaner(state.config)
    moved: list[str] = []
    try:
        for index, item in enumerate(requested, 1):
            progress_state.update_items(index - 1, len(requested), "Moving to Trash", str(item))
            destination = cleaner.move_analyzer_item_to_trash(item, estimates[item])
            moved.append(str(destination))
            if on_moved:
                on_moved(item)
            progress_state.update_items(index, len(requested), "Moved to Trash", str(item))
    except Exception:
        progress_state.finish("Trash operation failed", percent=0)
        raise
    progress_state.finish(f"Moved {len(moved)} item(s) to Trash")
    return moved

def _trash_reviewed_paths(
    handler: MacMaidHandler,
    body: dict,
    raw_paths: object,
    *,
    scope: str,
    state_attr: str,
    missing_error: str,
    progress_label: str,
    summary_action: str,
    on_moved=None,
) -> dict:
    """Shared flow for the reviewed "move selected paths to Trash" endpoints."""
    state = handler.server.state
    requested = _known_request_paths(handler, raw_paths, getattr(state, state_attr), missing_error)
    plan = analyzer_trash_plan(requested)
    if review := _review_gate(handler, scope, body, plan): return review
    estimates = {item: size_of(item) for item in requested}
    free_space = FreeSpaceProbe.capture(requested)
    moved = _move_items_to_trash_with_progress(handler, 
        scope, progress_label, requested, estimates, on_moved=on_moved
    )
    with state.lock: getattr(state, state_attr).difference_update(requested)
    observed, notes = free_space.finish()
    processed = sum(estimates.values())
    Cleaner(state.config).log_space_summary(
        summary_action, scanned=processed, processed=processed, reclaimed=0,
        trash_moved=processed, observed=observed, unknown=0, notes=notes,
    )
    return {"success": True, "removed": len(moved), "moved": moved,
            "processedEstimatedBytes": processed, "estimatedReclaimedBytes": 0,
            "trashMovedEstimatedBytes": processed, "observedFreeBytesDelta": observed,
            "measurementNotes": notes}

def route_post(handler: MacMaidHandler, path: str, body: dict) -> dict:
    state = handler.server.state
    if path in {"/api/memory/stop", "/api/memory/force-stop"}:
        keys = body.get("keys")
        if not isinstance(keys, list):
            raise ValueError("keys must be a JSON list")
        force = path.endswith("/force-stop")
        plan = state.memory.review(keys, force)
        review = _review_gate(handler, "memory-force" if force else "memory-stop", body, plan)
        if review is not None:
            return review
        return state.memory.stop(keys, force=force)
    if path == "/api/memory/settings":
        return state.memory.configure(body)
    if path == "/api/permissions/open-full-disk-access":
        result = run_command(
            "/usr/bin/open",
            ["x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"],
            timeout=10,
        )
        if not result.succeeded:
            raise OSError(result.stderr or "Could not open macOS Privacy & Security settings")
        return {"opened": True}
    if path == "/api/scan/cancel":
        service = str(body.get("service", "clean"))
        if service == "analyzer":
            cancelled = state.analyzer.cancel_active()
        elif service == "clean":
            with state.lock:
                token = state.scan_cancellations.get("clean")
                cancelled = bool(token and not token.cancelled)
                if token: token.cancel()
        else:
            raise ValueError("Unknown scan service")
        if cancelled:
            state.progress.finish("Tarama iptal ediliyor", percent=0)
        return {"success": True, "cancelled": cancelled, "service": service}
    if path == "/api/macmaid/update/check":
        status = macmaid_brew_update_status(refresh=True)
        state.macmaid_update = status
        return status
    if path == "/api/macmaid/update":
        status = macmaid_brew_update_status()
        plan = macmaid_update_plan(status)
        if review := _review_gate(handler, "macmaid-update", body, plan): return review
        return dict(apply_macmaid_brew_update(), success=True)
    if path == "/api/clean":
        if state.scan is None: raise ValueError("Run a scan first")
        items = _select_ids(state.scan, body.get("itemIds", []))
        plan = cleanup_plan("Apply cleanup", items)
        if review := _review_gate(handler, "clean", body, plan): return review
        result = _execute_cleanup(handler, 
            "cleaner",
            "Simulating selected cleanup" if body.get("dryRun", False) else "Cleaning selected items",
            items,
            apply=not body.get("dryRun", False),
        )
        return dict(_operation_payload(result), dryRun=bool(body.get("dryRun", False)))
    if path in ("/api/installers/clean", "/api/leftovers/clean", "/api/developer/caches/clean"):
        scan = {"/api/installers/clean": state.installers, "/api/leftovers/clean": state.leftovers, "/api/developer/caches/clean": state.dev_caches}[path]
        items = _select_paths(handler, scan, body.get("paths", [])) if "paths" in body else _select_ids(scan, body.get("itemIds", []))
        scope = {"/api/installers/clean": "installers", "/api/leftovers/clean": "leftovers", "/api/developer/caches/clean": "developer-caches"}[path]
        plan = cleanup_plan("Apply selected tool results", items)
        if review := _review_gate(handler, scope, body, plan): return review
        result = _execute_cleanup(handler, scope, "Cleaning selected items", items)
        with state.lock:
            setattr(state, {"installers": "installers", "leftovers": "leftovers", "developer-caches": "dev_caches"}[scope], None)
        return _operation_payload(result)
    if path == "/api/apps/uninstall":
        app_key = handler._request_path_key(body.get("path", ""))
        app = next((app for app in state.apps if str(app.path) == app_key), None)
        if not app: raise PermissionError("Application was not present in latest scan")
        leftover_keys = sorted({handler._request_path_key(item) for item in body.get("leftoverPaths", [])})
        manager = ApplicationManager(state.config)
        available = {str(component.path): component for component in manager.components(app)}
        selected_keys = [str(app.path), *leftover_keys]
        if any(key not in available for key in selected_keys):
            raise PermissionError("Application components changed after review")
        selected_paths = [available[key].path for key in selected_keys]
        plan = application_plan(app, [available[key] for key in selected_keys])
        if review := _review_gate(handler, "apps", body, plan): return review
        state.progress.start("apps", f"Uninstalling {app.name}")
        try:
            removal = manager.remove(
                app,
                selected_paths,
                progress=lambda index, total, current: state.progress.update_items(
                    index - 1, total, "Removing", str(current)
                ),
            )
        except Exception:
            state.progress.finish("Uninstall failed", percent=0)
            raise
        state.progress.finish(f"{app.name} uninstall completed")
        return removal
    if path == "/api/purge":
        wanted = {handler._request_path_key(item) for item in body.get("paths", [])}
        selected = [item for item in state.projects if str(item.path.absolute()) in wanted]
        if not wanted or len(selected) != len(wanted): raise PermissionError("Paths were not present in latest purge scan")
        plan = purge_plan(selected)
        if review := _review_gate(handler, "purge", body, plan): return review
        state.progress.start("purge", "Moving project artifacts to Trash")
        try:
            purged = ProjectPurgeManager(state.config).purge(
                selected,
                progress=lambda index, total, current: state.progress.update_items(
                    index - 1, total, "Moving to Trash", str(current)
                ),
            )
        except Exception:
            state.progress.finish("Project purge failed", percent=0)
            raise
        state.progress.finish("Project purge completed")
        return purged
    if path == "/api/treemap/open":
        requested_key = handler._request_path_key(body.get("path", ""))
        requested = next((item for item in state.treemap_paths if str(item) == requested_key), None)
        if requested is None:
            raise PermissionError("Treemap path was not present in latest view")
        result = run_command("/usr/bin/open", ["-R", str(requested)], timeout=15)
        if not result.succeeded:
            raise RuntimeError(result.stderr or result.stdout or "Open in Finder failed")
        return {"success": True, "path": str(requested)}
    if path == "/api/treemap/trash":
        return _trash_reviewed_paths(handler, 
            body, body.get("paths", []), scope="treemap", state_attr="treemap_paths",
            missing_error="Treemap path was not present in latest view",
            progress_label="Moving analyzed items to Trash",
            summary_action="treemap_trash_summary")
    if path == "/api/browser-storage/clean":
        if state.browser_storage is None: raise ValueError("Run browser storage scan first")
        items = _select_ids(state.browser_storage, body.get("itemIds", []))
        if any(item.risk not in (RiskLevel.SAFE, RiskLevel.MODERATE) for item in items):
            raise PermissionError("Browser Smart Clean only accepts cache areas")
        plan = cleanup_plan("Clean browser safe cache areas", items)
        if review := _review_gate(handler, "browser-storage", body, plan): return review
        result = _execute_cleanup(handler, "browser-storage", "Cleaning browser caches", items)
        with state.lock:
            state.browser_storage = None
        return _operation_payload(result)
    if path == "/api/smart-downloads/trash":
        return _trash_reviewed_paths(handler, 
            body, body.get("paths", []), scope="smart-downloads", state_attr="smart_downloads",
            missing_error="Smart Downloads item was not present in latest scan",
            progress_label="Moving downloads to Trash",
            summary_action="smart_downloads_trash_summary")
    if path == "/api/large-files/trash":
        return _trash_reviewed_paths(handler, 
            body, body.get("paths", []), scope="large-files", state_attr="large_files",
            missing_error="Large/old file was not present in latest scan",
            progress_label="Moving large files to Trash",
            summary_action="large_files_trash_summary")
    if path == "/api/duplicates/trash":
        return _trash_reviewed_paths(handler, 
            body, body.get("paths", []), scope="duplicates", state_attr="duplicates",
            missing_error="Duplicate path was not present in latest duplicate scan",
            progress_label="Moving duplicates to Trash",
            summary_action="duplicate_trash_summary")
    if path == "/api/analyze/trash":
        raw = body.get("paths", [])
        if "path" in body: raw = [body["path"]]
        return _trash_reviewed_paths(handler, 
            body, raw, scope="analyzer", state_attr="analyzed_paths",
            missing_error="Path was not present in latest analysis",
            progress_label="Moving analyzed items to Trash",
            summary_action="analyzer_trash_summary",
            on_moved=state.analyzer.invalidate_after_removal)
    if path == "/api/recovery/restore":
        return RecoveryCenter(state.config).restore(str(body.get("operationId", "")), str(body.get("trashPath", "")), copy=bool(body.get("copy", False)))
    if path == "/api/snapshots/thin":
        target = int(body.get("targetGB", 0))
        if target <= 0: raise ValueError("A positive snapshot target is required")
        if review := _review_gate(handler, "snapshots", body, snapshot_plan(target)): return review
        return thin_snapshots(target * 1024**3, state.config)
    if path == "/api/optimize/run":
        if not OPTIMIZATIONS: raise RuntimeError(OPTIMIZATION_UNAVAILABLE_REASON)
        tasks = [task for task in OPTIMIZATIONS if task["id"] == str(body.get("taskId", ""))]
        if not tasks: raise ValueError("Unknown optimization task")
        if review := _review_gate(handler, "optimize", body, optimization_plan(tasks)): return review
        return run_optimization(tasks[0]["id"])
    if path == "/api/optimize/run-all":
        if not OPTIMIZATIONS: raise RuntimeError(OPTIMIZATION_UNAVAILABLE_REASON)
        tasks = [task for task in OPTIMIZATIONS if task["recommended"]]
        if review := _review_gate(handler, "optimize", body, optimization_plan(tasks)): return review
        results = [run_optimization(task["id"]) for task in tasks]
        return {"success": all(r["success"] for r in results), "executed": sum(r["success"] for r in results), "failed": sum(not r["success"] for r in results), "skipped": 0, "total": len(results)}
    if path == "/api/whitelist":
        lines = body.get("lines")
        if not isinstance(lines, list) or not all(isinstance(line, str) for line in lines): raise ValueError("Invalid lines array")
        state.config.replace_whitelist(lines)
        with state.lock:
            state.review_tokens.clear()
            for scope in list(state.generations): state.generations[scope] += 1
        return {"success": True}
    if path == "/api/developer/remove":
        category = str(body.get("category", "")); item_id = str(body.get("id", ""))
        if category not in {"runtime", "environment", "tool", "sdk"} or not item_id:
            raise ValueError("Missing category or id")
        current = next((item for item in state.developer_items.get(category, []) if item.id == item_id), None)
        if current is None or not current.removable:
            raise PermissionError("Developer item was not removable in the latest inventory")
        if review := _review_gate(handler, f"developer-{category}", body, developer_plan(current)): return review
        removal = DeveloperInventory(state.config).remove(item_id, category, reviewed=current)
        return dict(removal, humanFreed=human_bytes(removal["freed"]),
                    humanProcessedEstimate=human_bytes(removal.get("processedEstimatedBytes", 0)))
    raise FileNotFoundError(path)

