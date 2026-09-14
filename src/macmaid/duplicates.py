from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .cancellation import CancellationToken
from .models import ActionType, CleanupAction, CleanupCategory, CleanupItem, RiskLevel, ScanResult
from .safety import PathSafety
from .system import human_bytes

_PARTIAL_BYTES = 1024 * 1024
_READ_CHUNK = 1024 * 1024


@dataclass(frozen=True, slots=True)
class DuplicateFile:
    path: Path
    bytes: int
    device: int
    inode: int
    partial_hash: str
    full_hash: str

    def web_dict(self) -> dict:
        return {"path": str(self.path), "bytes": self.bytes, "humanBytes": human_bytes(self.bytes),
                "inode": self.inode, "device": self.device, "partialHash": self.partial_hash,
                "fullHash": self.full_hash}


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    bytes: int
    full_hash: str
    files: tuple[DuplicateFile, ...] = field(default_factory=tuple)

    @property
    def wasted_bytes(self) -> int:
        return max(0, len(self.files) - 1) * self.bytes

    def web_dict(self) -> dict:
        return {"bytes": self.bytes, "humanBytes": human_bytes(self.bytes), "fullHash": self.full_hash,
                "wastedBytes": self.wasted_bytes, "humanWasted": human_bytes(self.wasted_bytes),
                "files": [file.web_dict() for file in self.files]}


class DuplicateFinder:
    """Read-only byte-for-byte duplicate finder: size → partial hash → full hash."""

    def __init__(self, *, min_bytes: int = 1, max_files: int = 200_000) -> None:
        self.min_bytes = max(1, min_bytes)
        self.max_files = max_files

    def scan(self, roots: Iterable[Path] | None = None, *, cancellation: CancellationToken | None = None) -> list[DuplicateGroup]:
        token = cancellation or CancellationToken()
        candidates: dict[int, list[tuple[Path, os.stat_result]]] = {}
        for root in roots or [Path.home() / "Downloads", Path.home() / "Desktop"]:
            self._collect(Path(root).expanduser().absolute(), candidates, token)
        partials: dict[tuple[int, str], list[tuple[Path, os.stat_result]]] = {}
        for size, files in candidates.items():
            if len(files) < 2:
                continue
            for path, info in files:
                token.check()
                digest = self._hash_file(path, limit=_PARTIAL_BYTES)
                if digest:
                    partials.setdefault((size, digest), []).append((path, info))
        fulls: dict[tuple[int, str], list[DuplicateFile]] = {}
        for (size, partial), files in partials.items():
            unique_inodes: set[tuple[int, int]] = set()
            if len(files) < 2:
                continue
            for path, info in files:
                token.check()
                identity = (info.st_dev, info.st_ino)
                if identity in unique_inodes:
                    continue
                unique_inodes.add(identity)
                digest = self._hash_file(path)
                if digest:
                    fulls.setdefault((size, digest), []).append(DuplicateFile(path, size, info.st_dev, info.st_ino, partial, digest))
        groups = [DuplicateGroup(size, digest, tuple(sorted(files, key=lambda item: str(item.path))))
                  for (size, digest), files in fulls.items() if len(files) > 1]
        return sorted(groups, key=lambda group: (-group.wasted_bytes, str(group.files[0].path)))

    def scan_result(self, roots: Iterable[Path] | None = None, *, cancellation: CancellationToken | None = None) -> ScanResult:
        items: list[CleanupItem] = []
        for group_index, group in enumerate(self.scan(roots, cancellation=cancellation), 1):
            for file_index, duplicate in enumerate(group.files, 1):
                items.append(CleanupItem(
                    CleanupCategory.TRASH,
                    f"Duplicate group {group_index} file {file_index} · {duplicate.path.name}",
                    duplicate.path,
                    duplicate.bytes,
                    RiskLevel.AGGRESSIVE,
                    "Byte-for-byte duplicate confirmed by size, partial hash and full hash. Nothing is selected automatically; review before moving to Trash.",
                    CleanupAction(ActionType.MOVE_TO_TRASH),
                ))
        return ScanResult(items=items)

    def _collect(self, root: Path, candidates: dict[int, list[tuple[Path, os.stat_result]]], token: CancellationToken) -> None:
        root = PathSafety._lexical(root)
        home = Path.home()
        if root != home and home not in root.parents:
            return
        stack = [root]
        seen = 0
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
                            elif entry.is_file(follow_symlinks=False):
                                info = entry.stat(follow_symlinks=False)
                                if info.st_size >= self.min_bytes:
                                    candidates.setdefault(info.st_size, []).append((Path(entry.path), info))
                                    seen += 1
                                    if seen >= self.max_files:
                                        return
                        except OSError:
                            continue
            except OSError:
                continue

    @staticmethod
    def _hash_file(path: Path, *, limit: int | None = None) -> str | None:
        digest = hashlib.sha256()
        remaining = limit
        try:
            with path.open("rb") as handle:
                while True:
                    if remaining is not None and remaining <= 0:
                        break
                    chunk_size = _READ_CHUNK if remaining is None else min(_READ_CHUNK, remaining)
                    chunk = handle.read(chunk_size)
                    if not chunk:
                        break
                    digest.update(chunk)
                    if remaining is not None:
                        remaining -= len(chunk)
        except OSError:
            return None
        return digest.hexdigest()
