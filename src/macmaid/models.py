from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4


class RiskLevel(IntEnum):
    SAFE = 0
    MODERATE = 1
    AGGRESSIVE = 2
    MANUAL_ONLY = 3


class CleanupProfile(StrEnum):
    SAFE = "safe"
    DEEP = "deep"
    DEVELOPER = "developer"
    AGGRESSIVE = "aggressive"

    @property
    def maximum_risk(self) -> RiskLevel:
        return {
            self.SAFE: RiskLevel.SAFE,
            self.DEEP: RiskLevel.MODERATE,
            self.DEVELOPER: RiskLevel.MODERATE,
            self.AGGRESSIVE: RiskLevel.AGGRESSIVE,
        }[self]

    @property
    def includes_developer(self) -> bool:
        return self in (self.DEVELOPER, self.AGGRESSIVE)


class CleanupCategory(StrEnum):
    USER_CACHES = "User caches"
    BROWSER_CACHES = "Browser caches"
    APP_CACHES = "Application caches"
    LOGS = "Logs & diagnostics"
    DEVELOPER = "Developer tools"
    PACKAGE_MANAGERS = "Package-manager caches"
    TEMPORARY = "Temporary files"
    TRASH = "Trash"
    LEFTOVERS = "Uninstalled-app leftovers"
    INSTALLERS = "Installer files"
    MAINTENANCE = "Maintenance commands"


class ActionType(StrEnum):
    REMOVE_PATH = "remove_path"
    REMOVE_CHILDREN = "remove_children"
    COMMAND = "command"
    COMMAND_WITH_CACHE_FALLBACK = "command_with_cache_fallback"
    MANUAL_CACHE_FALLBACK = "manual_cache_fallback"
    MOVE_TO_TRASH = "move_to_trash"


@dataclass(slots=True)
class CleanupAction:
    kind: ActionType
    executable: str | None = None
    arguments: list[str] = field(default_factory=list)
    dry_run_arguments: list[str] | None = None
    fallback_manager: str | None = None


@dataclass(slots=True)
class CleanupItem:
    category: CleanupCategory
    label: str
    path: Path | None
    estimated_bytes: int
    risk: RiskLevel
    reason: str
    action: CleanupAction
    requires_app_closed: str | None = None
    id: str = field(default_factory=lambda: str(uuid4()))

    def web_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category.value,
            "label": self.label,
            "path": str(self.path) if self.path else "",
            "bytes": self.estimated_bytes,
            "risk": "MANUAL" if self.risk is RiskLevel.MANUAL_ONLY else self.risk.name,
            "reason": self.reason,
            "requiresAppClosed": self.requires_app_closed or "",
        }


@dataclass(slots=True)
class ScanResult:
    items: list[CleanupItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    status: str = "complete"
    issues: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return self.status == "complete"

    @property
    def is_partial(self) -> bool:
        return self.status in {"partial", "cancelled", "failed"}

    @property
    def total_bytes(self) -> int:
        return sum(item.estimated_bytes for item in self.items)


@dataclass(slots=True)
class OperationResult:
    # `freed` remains for API compatibility. It is an estimate and never includes Trash moves or unknown manager effects.
    freed: int = 0
    failed: int = 0
    skipped: int = 0
    details: list[str] = field(default_factory=list)
    scanned_estimated_bytes: int = 0
    processed_estimated_bytes: int = 0
    trash_moved_estimated_bytes: int = 0
    observed_free_bytes_delta: int | None = None
    unknown_reclaim_count: int = 0
    measurement_notes: list[str] = field(default_factory=list)

    def web_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update({
            "scannedEstimatedBytes": self.scanned_estimated_bytes,
            "processedEstimatedBytes": self.processed_estimated_bytes,
            "estimatedReclaimedBytes": self.freed,
            "trashMovedEstimatedBytes": self.trash_moved_estimated_bytes,
            "observedFreeBytesDelta": self.observed_free_bytes_delta,
            "unknownReclaimCount": self.unknown_reclaim_count,
            "measurementNotes": self.measurement_notes,
        })
        return data
