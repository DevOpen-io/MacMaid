from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from .cancellation import CancellationToken
from .duplicates import DuplicateFinder
from .models import ActionType, CleanupAction, CleanupCategory, CleanupItem, RiskLevel, ScanResult
from .system import human_bytes

INSTALLER_EXTENSIONS = {".dmg", ".pkg", ".xip", ".iso", ".ipsw"}
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z"}
INCOMPLETE_EXTENSIONS = {".crdownload", ".download", ".part"}
SMART_DOWNLOAD_EXTENSIONS = INSTALLER_EXTENSIONS | ARCHIVE_EXTENSIONS | INCOMPLETE_EXTENSIONS
PROTECTED_USER_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".rtf", ".md", ".jpg", ".jpeg", ".png", ".heic", ".gif", ".py", ".js", ".ts", ".java", ".swift", ".c", ".cpp", ".h", ".rs", ".go"}


@dataclass(frozen=True, slots=True)
class SmartDownloadItem:
    path: Path
    bytes: int
    modified: float
    categories: tuple[str, ...]

    @property
    def age_days(self) -> int:
        return max(0, int((time.time() - self.modified) // 86400))

    def web_dict(self) -> dict:
        return {"path": str(self.path), "name": self.path.name, "bytes": self.bytes,
                "humanBytes": human_bytes(self.bytes), "ageDays": self.age_days,
                "categories": list(self.categories), "selectedByDefault": False}


class SmartDownloadsScanner:
    """Read-only Downloads classifier; it never treats documents/photos/source as junk."""

    def __init__(self, *, older_than_days: int = 30) -> None:
        self.older_than_days = max(0, older_than_days)

    def scan(self, *, cancellation: CancellationToken | None = None) -> list[SmartDownloadItem]:
        token = cancellation or CancellationToken()
        root = Path.home() / "Downloads"
        duplicate_paths = {file.path for group in DuplicateFinder().scan([root], cancellation=token) for file in group.files}
        found: list[SmartDownloadItem] = []
        cutoff = time.time() - self.older_than_days * 86400
        stack = [root]
        while stack:
            token.check()
            current = stack.pop()
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        token.check()
                        if entry.is_symlink():
                            continue
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                stack.append(Path(entry.path))
                                continue
                            if not entry.is_file(follow_symlinks=False):
                                continue
                            path = Path(entry.path)
                            info = entry.stat(follow_symlinks=False)
                        except OSError:
                            continue
                        categories = self._categories(path, info.st_mtime, cutoff, path in duplicate_paths)
                        if categories:
                            found.append(SmartDownloadItem(path, info.st_size, info.st_mtime, categories))
            except FileNotFoundError:
                return []
            except OSError:
                continue
        return sorted(found, key=lambda item: (-item.bytes, str(item.path)))

    def scan_result(self, *, cancellation: CancellationToken | None = None) -> ScanResult:
        return ScanResult(items=[self._cleanup_item(item) for item in self.scan(cancellation=cancellation)])

    def _categories(self, path: Path, modified: float, cutoff: float, duplicate: bool) -> tuple[str, ...]:
        suffix = path.suffix.lower()
        categories: list[str] = []
        if suffix in INSTALLER_EXTENSIONS:
            categories.append("Installers")
        if suffix in ARCHIVE_EXTENSIONS:
            categories.append("Archives")
        if suffix in INCOMPLETE_EXTENSIONS:
            categories.append("Incomplete Downloads")
        if suffix in SMART_DOWNLOAD_EXTENSIONS and modified < cutoff:
            categories.append("Old Downloads")
        if duplicate and suffix not in PROTECTED_USER_EXTENSIONS:
            categories.append("Duplicates")
        return tuple(dict.fromkeys(categories))

    @staticmethod
    def _cleanup_item(item: SmartDownloadItem) -> CleanupItem:
        return CleanupItem(
            CleanupCategory.TRASH,
            f"Smart Downloads · {', '.join(item.categories)} · {item.path.name}",
            item.path,
            item.bytes,
            RiskLevel.AGGRESSIVE,
            "Downloads candidate classified by exact extension or duplicate match. Documents, photos and source code are not classified as junk; review explicitly before moving to Trash.",
            CleanupAction(ActionType.MOVE_TO_TRASH),
        )
