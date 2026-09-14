from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .cancellation import CancellationToken
from .models import ActionType, CleanupAction, CleanupCategory, CleanupItem, RiskLevel, ScanResult
from .safety import PathSafety
from .system import human_bytes

SIZE_FILTERS = {
    "500MB": 500 * 1000**2,
    "1GB": 1000**3,
    "5GB": 5 * 1000**3,
    "10GB": 10 * 1000**3,
}
AGE_FILTERS_DAYS = (30, 90, 180, 365)
_ARCHIVES = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".tbz2"}
_VIDEOS = {".mov", ".mp4", ".m4v", ".avi", ".mkv", ".webm"}
_DISK_IMAGES = {".dmg", ".iso", ".img", ".sparsebundle", ".sparseimage"}


@dataclass(frozen=True, slots=True)
class LargeOldFile:
    path: Path
    bytes: int
    modified: float
    categories: tuple[str, ...]

    @property
    def age_days(self) -> int:
        return max(0, int((time.time() - self.modified) // 86400))

    def web_dict(self) -> dict:
        return {"path": str(self.path), "name": self.path.name, "bytes": self.bytes,
                "humanBytes": human_bytes(self.bytes), "modified": self.modified,
                "ageDays": self.age_days, "categories": list(self.categories),
                "selectedByDefault": False}


class LargeOldFileScanner:
    """Read-only user-file scanner. It never selects files automatically."""

    def __init__(self, *, min_bytes: int = SIZE_FILTERS["500MB"], older_than_days: int | None = None,
                 max_files: int = 200_000) -> None:
        self.min_bytes = max(1, min_bytes)
        self.older_than_days = older_than_days
        self.max_files = max_files

    def scan(self, roots: Iterable[Path] | None = None, *, cancellation: CancellationToken | None = None) -> list[LargeOldFile]:
        token = cancellation or CancellationToken()
        found: list[LargeOldFile] = []
        default_roots = [Path.home()]
        for root in roots or default_roots:
            self._scan_root(Path(root).expanduser().absolute(), found, token)
        return sorted(found, key=lambda item: (-item.bytes, str(item.path)))

    def scan_result(self, roots: Iterable[Path] | None = None, *, cancellation: CancellationToken | None = None) -> ScanResult:
        items = [self._cleanup_item(item) for item in self.scan(roots, cancellation=cancellation)]
        return ScanResult(items=items)

    def _scan_root(self, root: Path, found: list[LargeOldFile], token: CancellationToken) -> None:
        root = PathSafety._lexical(root)
        home = Path.home()
        if root != home and home not in root.parents:
            return
        if root == home / "Library" or home / "Library" in root.parents:
            return
        stack = [root]
        seen = 0
        cutoff = time.time() - self.older_than_days * 86400 if self.older_than_days is not None else None
        while stack:
            token.check()
            current = stack.pop()
            if current == home / "Library" or home / "Library" in current.parents:
                continue
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        token.check()
                        if entry.is_symlink():
                            continue
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                stack.append(Path(entry.path))
                            elif entry.is_file(follow_symlinks=False):
                                info = entry.stat(follow_symlinks=False)
                                seen += 1
                                if seen > self.max_files:
                                    return
                                if info.st_size < self.min_bytes:
                                    continue
                                if cutoff is not None and info.st_mtime > cutoff:
                                    continue
                                path = Path(entry.path)
                                found.append(LargeOldFile(path, info.st_size, info.st_mtime, self._categories(path, root, info.st_mtime)))
                        except OSError:
                            continue
            except OSError:
                continue

    def _categories(self, path: Path, root: Path, modified: float) -> tuple[str, ...]:
        categories = ["Large files"]
        if self.older_than_days is not None and int((time.time() - modified) // 86400) >= self.older_than_days:
            categories.append("Old files")
        suffixes = {path.suffix.lower()}
        if path.name.lower().endswith(".tar.gz"):
            suffixes.add(".tar.gz")
        if suffixes & _ARCHIVES:
            categories.append("Archives")
        if suffixes & _VIDEOS:
            categories.append("Videos")
        if suffixes & _DISK_IMAGES:
            categories.append("Disk images")
        if Path.home() / "Downloads" == root or Path.home() / "Downloads" in path.parents:
            categories.append("Downloads")
        return tuple(dict.fromkeys(categories))

    @staticmethod
    def _cleanup_item(item: LargeOldFile) -> CleanupItem:
        return CleanupItem(
            CleanupCategory.TRASH,
            f"{', '.join(item.categories)} · {item.path.name}",
            item.path,
            item.bytes,
            RiskLevel.AGGRESSIVE,
            "User file candidate. It is never selected automatically; review explicitly before moving to Trash.",
            CleanupAction(ActionType.MOVE_TO_TRASH),
        )
