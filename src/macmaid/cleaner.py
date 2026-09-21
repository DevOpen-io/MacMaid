from __future__ import annotations

import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .config import Config
from .models import ActionType, CleanupAction, CleanupCategory, CleanupItem, OperationResult, RiskLevel
from .reporting import FreeSpaceProbe
from .safety import PathSafety, PathSafetyError, manual_cache_allowed
from .system import human_bytes, move_to_trash_exclusive, process_running, remove_validated_path, run_command, size_of, unique_trash_destination


class Cleaner:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        self.safety = PathSafety()

    def execute(
        self,
        items: list[CleanupItem],
        *,
        apply: bool,
        assume_yes: bool = False,
        allow_manual_fallback: bool = False,
        progress: Callable[[int, int, CleanupItem, str], None] | None = None,
    ) -> OperationResult:
        result = OperationResult(scanned_estimated_bytes=sum(max(0, item.estimated_bytes) for item in items))

        def emit(index: int, item: CleanupItem, outcome: str) -> None:
            nonlocal progress
            if progress is None:
                return
            try:
                progress(index, len(items), item, outcome)
            except Exception as exc:
                result.details.append(f"progress reporting disabled: {exc}")
                progress = None
        if not apply:
            result.skipped = len(items)
            result.details.append("DRY RUN: no files were changed")
            return result
        if os.geteuid() == 0:
            raise PermissionError("MacMaid must run as your normal user, never with sudo/root")
        self._ensure_audit_safe()
        if not assume_yes:
            answer = input(f"Type CLEAN to execute {len(items)} cleanup action(s): ").strip()
            if answer != "CLEAN":
                result.skipped = len(items)
                return result
        operation_id = str(uuid4())
        free_space = FreeSpaceProbe.capture(item.path for item in items)
        for index, item in enumerate(items, 1):
            emit(index, item, "running")
            if item.risk is RiskLevel.MANUAL_ONLY and not (allow_manual_fallback and item.action.kind is ActionType.MANUAL_CACHE_FALLBACK):
                result.skipped += 1
                self._log(item, "skipped", "Manual action requires explicit authorization", operation_id=operation_id)
                emit(index, item, "skipped")
                continue
            try:
                if item.requires_app_closed and (process_running(item.requires_app_closed) or process_running(item.requires_app_closed + ".app")):
                    raise PermissionError(f"Close {item.requires_app_closed} first")
                # Trash moves never read before/after: `reclaimed` stays 0 for them
                # and the move's post-condition is verified inside _execute_item.
                measured_path = item.path if item.action.kind is not ActionType.MOVE_TO_TRASH else None
                before = size_of(measured_path) if measured_path is not None else 0
                trash_destination = self._execute_item(item, allow_manual_fallback=allow_manual_fallback)
                after = size_of(measured_path) if measured_path is not None else 0
                reclaimed = 0
                result.processed_estimated_bytes += max(0, item.estimated_bytes)
                if item.action.kind is ActionType.MOVE_TO_TRASH:
                    result.trash_moved_estimated_bytes += max(0, item.estimated_bytes)
                    reclaim_status = "moved_to_trash_not_reclaimed"
                elif item.action.kind in (ActionType.COMMAND, ActionType.COMMAND_WITH_CACHE_FALLBACK):
                    if item.path is not None and before > 0 and after >= before:
                        raise RuntimeError(f"{item.action.executable} reported success but {human_bytes(after)} remains in {item.path}")
                    reclaimed = max(0, before - after)
                    if reclaimed:
                        result.freed += reclaimed
                        reclaim_status = "verified_reduction"
                    else:
                        result.unknown_reclaim_count += 1
                        reclaim_status = "unknown_manager_effect"
                else:
                    reclaimed = max(0, before - after)
                    result.freed += reclaimed
                    reclaim_status = "estimated_from_target_size"
                self._log(item, "success", None, operation_id=operation_id,
                          trash_path=trash_destination if item.action.kind is ActionType.MOVE_TO_TRASH else None,
                          processed_estimated_bytes=max(0, item.estimated_bytes),
                          estimated_reclaimed_bytes=reclaimed, reclaim_status=reclaim_status)
                emit(index, item, "success")
            except PermissionError as exc:
                result.skipped += 1
                result.details.append(f"{item.label}: {exc}")
                self._log(item, "skipped", str(exc), operation_id=operation_id)
                emit(index, item, "skipped")
            except Exception as exc:
                result.failed += 1
                result.details.append(f"{item.label}: {exc}")
                self._log(item, "failed", str(exc), operation_id=operation_id)
                emit(index, item, "failed")
        result.observed_free_bytes_delta, result.measurement_notes = free_space.finish()
        self._log_summary(result, operation_id)
        return result

    def _execute_item(self, item: CleanupItem, *, allow_manual_fallback: bool = False) -> Path | None:
        kind = item.action.kind
        if kind is ActionType.REMOVE_PATH:
            self._remove_path(item.path)
            return None
        elif kind is ActionType.REMOVE_CHILDREN:
            self._remove_children(item.path)
            return None
        elif kind is ActionType.MOVE_TO_TRASH:
            return self._move_to_trash(item.path)
        elif kind in (ActionType.COMMAND, ActionType.COMMAND_WITH_CACHE_FALLBACK):
            if not item.action.executable:
                raise ValueError("missing executable")
            if item.path is not None:
                self.config.require_unprotected(item.path)
            if self.config.patterns(strict=True):
                raise PermissionError("Command-wide scope cannot be checked against whitelist")
            command = run_command(item.action.executable, item.action.arguments, timeout=600)
            if not command.succeeded:
                raise RuntimeError(command.stderr or command.stdout or "command failed")
            return None
        elif kind is ActionType.MANUAL_CACHE_FALLBACK and allow_manual_fallback:
            if item.path is None or not item.action.fallback_manager or not manual_cache_allowed(item.action.fallback_manager, item.path):
                raise PermissionError("manual cache fallback path rejected by strict allowlist")
            self._remove_manual_children(item.path)
            return None
        else:
            raise PermissionError("manual recursive fallback requires a second interactive confirmation")

    def _remove_manual_children(self, raw: Path) -> None:
        if os.geteuid() == 0:
            raise PermissionError("MacMaid must never run as root")
        safety = PathSafety(extra_allowed_roots=[raw]); root = safety.validate_deletion_path(raw)
        self._require_owned_directory(root, "cache root")
        self.config.require_unprotected(root)
        for child in root.iterdir() if root.exists() else []:
            self._delete_validated(child, safety)
        if root.exists() and any(root.iterdir()):
            raise RuntimeError("manual cleanup directory still contains children")

    def _remove_path(self, raw: Path | None) -> None:
        if raw is None:
            raise ValueError("missing path")
        self._delete_validated(raw, self.safety)

    def _delete_validated(self, raw: Path, safety: PathSafety) -> None:
        if os.geteuid() == 0:
            raise PermissionError("MacMaid must never run as root")
        def authorize() -> None:
            safety.validate_deletion_path(raw)
            self.config.require_unprotected(raw)
        authorize()
        remove_validated_path(raw, authorize)

    def _remove_children(self, raw: Path | None) -> None:
        if os.geteuid() == 0:
            raise PermissionError("MacMaid must never run as root")
        if raw is None:
            raise ValueError("missing path")
        root = self.safety.validate_deletion_path(raw)
        self._require_owned_directory(root, "cleanup root", allow_missing=True)
        self.config.require_unprotected(root)
        if not root.exists():
            return
        for child in root.iterdir():
            self._delete_validated(child, self.safety)
        if any(root.iterdir()):
            raise RuntimeError("cleanup directory still contains removable children")

    @staticmethod
    def _require_owned_directory(path: Path, label: str, *, allow_missing: bool = False) -> None:
        try:
            info = path.lstat()
        except FileNotFoundError:
            if allow_missing:
                return
            raise PathSafetyError(f"{label} is unavailable: {path}")
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise PathSafetyError(f"{label} must be a user-owned directory: {path}")

    def _move_to_trash(self, raw: Path | None) -> Path:
        if raw is None:
            raise ValueError("missing path")
        return self._move_validated_to_trash(raw, self.safety.validate_trash_candidate)

    def _move_validated_to_trash(self, raw: Path, validate: Callable[[Path], Path]) -> Path:
        if os.geteuid() == 0:
            raise PermissionError("MacMaid must run as your normal user, never with sudo/root")

        def validate_source() -> Path:
            path = validate(raw)
            if path.is_symlink():
                raise PathSafetyError(f"symlink Trash target rejected: {path}")
            if path.lstat().st_uid != os.getuid():
                raise PathSafetyError(f"Trash target is not owned by the current user: {path}")
            self.config.require_unprotected(path)
            return path

        path = validate_source()
        trash = Path.home() / ".Trash"

        def validate_trash() -> None:
            PathSafety._reject_symlink_ancestors(trash)
            if trash.is_symlink():
                raise PathSafetyError("symlink Trash directory rejected")
            if trash.exists() and (not trash.is_dir() or trash.lstat().st_uid != os.getuid()):
                raise PathSafetyError("Trash must be a directory owned by the current user")

        validate_trash()
        trash.mkdir(mode=0o700, exist_ok=True)
        destination = unique_trash_destination(path)
        # Selection and destination preparation are not execution-time authorization.
        validate_trash()
        path = validate_source()
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"Trash destination is no longer available: {destination}")
        def authorize() -> None:
            validate_trash()
            validate_source()
        move_to_trash_exclusive(path, destination, authorize)
        if path.exists() or path.is_symlink() or not destination.exists() or destination.is_symlink():
            raise RuntimeError("Trash move post-condition failed")
        return destination

    def move_analyzer_item_to_trash(self, raw: Path, estimated_bytes: int | None = None) -> Path:
        return self.move_reviewed_item_to_trash(raw, PathSafety.validate_analyzer_candidate, estimated_bytes)

    def move_reviewed_item_to_trash(self, raw: Path, validate: Callable[[Path], Path],
                                    estimated_bytes: int | None = None) -> Path:
        """Shared mutation/audit layer; callers supply narrow domain revalidation."""
        if os.geteuid() == 0:
            raise PermissionError("MacMaid must run as your normal user, never with sudo/root")
        self._ensure_audit_safe()
        estimate = max(0, size_of(raw) if estimated_bytes is None else estimated_bytes)
        item = CleanupItem(
            CleanupCategory.TRASH, raw.name, raw, estimate, RiskLevel.AGGRESSIVE,
            "Explicitly reviewed Trash target", CleanupAction(ActionType.MOVE_TO_TRASH),
        )
        try:
            destination = self._move_validated_to_trash(raw, validate)
        except Exception as exc:
            self._log(item, "failed", str(exc))
            raise
        self._log(item, "success", f"Moved to Trash: {destination}", trash_path=destination,
                  processed_estimated_bytes=estimate, reclaim_status="moved_to_trash_not_reclaimed")
        return destination

    def _ensure_audit_safe(self) -> None:
        self.config._ensure_owned_directory(self.config.log_dir)
        self.config._require_owned_regular_file(self.config.operation_log, allow_missing=True)

    def _log(self, item: CleanupItem, outcome: str, detail: str | None, *,
             operation_id: str | None = None, trash_path: Path | None = None,
             processed_estimated_bytes: int = 0, estimated_reclaimed_bytes: int = 0,
             reclaim_status: str = "not_processed") -> None:
        original_path = str(item.path) if item.path else None
        trash_path_text = str(trash_path) if trash_path else None
        restorable = outcome == "success" and item.action.kind is ActionType.MOVE_TO_TRASH and trash_path is not None
        record = {
            "timestamp": datetime.now(UTC).isoformat(), "recordType": "item", "action": item.action.kind.value,
            "operation_id": operation_id or str(uuid4()),
            "original_path": original_path, "trash_path": trash_path_text,
            "size": item.estimated_bytes, "restorable": restorable,
            "category": item.category.value, "label": item.label,
            "path": original_path, "bytes": item.estimated_bytes,
            "scannedEstimatedBytes": item.estimated_bytes,
            "processedEstimatedBytes": processed_estimated_bytes,
            "estimatedReclaimedBytes": estimated_reclaimed_bytes,
            "reclaimStatus": reclaim_status,
            "result": outcome, "detail": detail,
        }
        self._append_record(record)

    def _log_summary(self, result: OperationResult, operation_id: str | None = None) -> None:
        self.log_space_summary(
            "cleanup_summary", scanned=result.scanned_estimated_bytes,
            processed=result.processed_estimated_bytes, reclaimed=result.freed,
            trash_moved=result.trash_moved_estimated_bytes, observed=result.observed_free_bytes_delta,
            unknown=result.unknown_reclaim_count, notes=result.measurement_notes,
            failed=result.failed, skipped=result.skipped, operation_id=operation_id,
        )

    def log_space_summary(self, action: str, *, scanned: int, processed: int, reclaimed: int,
                          trash_moved: int, observed: int | None, unknown: int,
                          notes: list[str], failed: int = 0, skipped: int = 0,
                          operation_id: str | None = None) -> None:
        self._append_record({
            "timestamp": datetime.now(UTC).isoformat(), "recordType": "operation_summary",
            "operation_id": operation_id or str(uuid4()),
            "original_path": None, "trash_path": None,
            "size": processed, "restorable": False,
            "action": action, "result": "partial" if failed or skipped else "success",
            "scannedEstimatedBytes": scanned, "processedEstimatedBytes": processed,
            "estimatedReclaimedBytes": reclaimed, "trashMovedEstimatedBytes": trash_moved,
            "observedFreeBytesDelta": observed, "unknownReclaimCount": unknown,
            "failed": failed, "skipped": skipped, "measurementNotes": notes,
        })

    def _append_record(self, record: dict) -> None:
        self._ensure_audit_safe()
        fd = os.open(self.config.operation_log, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise PermissionError("Unsafe operation audit file")
            with os.fdopen(fd, "a", encoding="utf-8", closefd=False) as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        finally:
            os.close(fd)
