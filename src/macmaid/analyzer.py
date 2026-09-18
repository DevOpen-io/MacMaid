from __future__ import annotations

import os
import stat
import threading
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .system import human_bytes


def _view_only(path: Path) -> bool:
    home = Path.home()
    return (
        path == home / "Library"
        or home / "Library" in path.parents
        or path.suffix.lower() == ".app"
        or ".photoslibrary" in path.name.lower()
    )


@dataclass(slots=True)
class AnalyzerJob:
    path: Path
    top: int
    min_file_bytes: int
    entries: list[dict[str, Any]]
    generation: int
    created_at: float = field(default_factory=time.monotonic)
    last_accessed: float = field(default_factory=time.monotonic)
    completed: int = 0
    failed: int = 0
    partial: int = 0
    current_scan_path: str | None = None
    largest_files: dict[str, dict[str, Any]] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    futures: list[Future[Any]] = field(default_factory=list)
    cancelled: threading.Event = field(default_factory=threading.Event)
    next_index: int = 0
    paused: bool = False
    was_cancelled: bool = False

    @property
    def is_complete(self) -> bool:
        return self.completed + self.failed + self.partial >= len(self.entries)


@dataclass(slots=True)
class _DirScan:
    """Per-directory scan output; merged into a ``_WalkContext`` under its lock."""

    subdirs: list[Path] = field(default_factory=list)
    links: list[tuple[int, int, int, int]] = field(default_factory=list)
    largest: list[dict[str, Any]] = field(default_factory=list)
    apparent: int = 0
    disk: int = 0
    files: int = 0
    inaccessible: int = 0
    boundary: int = 0
    open_failed: bool = False


@dataclass(slots=True)
class _WalkResult:
    apparent: int = 0
    disk: int = 0
    files: int = 0
    inaccessible: int = 0
    boundary: int = 0
    largest: list[dict[str, Any]] = field(default_factory=list)
    root_error: str | None = None


class _WalkContext:
    """Shared measurement state for one top-level entry.

    Directory workers drain a common frontier instead of each owning one
    child, so a single large subtree can use the whole worker pool without a
    nested ``ThreadPoolExecutor``. Helpers are ordinary futures on the shared
    executor and never block on each other, which keeps the pool deadlock-free.
    """

    __slots__ = ("target", "threshold", "top", "dirs", "pending", "helpers",
                 "capacity", "lock", "result", "inodes", "root_dev")

    def __init__(self, target: Path, threshold: int, top: int, capacity: int) -> None:
        self.target = target
        self.threshold = threshold
        self.top = top
        self.dirs: deque[Path] = deque()
        self.pending = 0
        self.helpers = 0
        self.capacity = capacity
        self.lock = threading.Lock()
        self.result = _WalkResult()
        self.inodes: set[tuple[int, int]] = set()
        self.root_dev: int | None = None


class IncrementalAnalyzer:
    """Process-local, non-blocking directory analyzer with navigation cache.

    Directory names are enumerated synchronously and returned immediately. Each
    child is then measured independently in a bounded worker pool. Navigation
    pauses the previous job but preserves its completed measurements, so only one
    directory consumes I/O and returning to a parent remains an instant cache hit.
    """

    def __init__(self, max_workers: int = 4) -> None:
        self._lock = threading.RLock()
        self._max_workers = max(1, min(max_workers, 8))
        self._executor = ThreadPoolExecutor(max_workers=self._max_workers, thread_name_prefix="macmaid-analyzer")
        self._jobs: dict[Path, AnalyzerJob] = {}
        self._generation = 0
        self._active_path: Path | None = None
        self._focus_id = -1

    @staticmethod
    def normalize(raw: str | Path) -> Path:
        path = Path(raw).expanduser().absolute()
        if not path.is_dir():
            raise ValueError(f"Analyzer path is not a readable directory: {path}")
        if path.is_symlink():
            raise ValueError(f"Analyzer does not follow a symlinked root: {path}")
        return path

    def snapshot(
        self,
        raw: str | Path,
        *,
        start: bool = False,
        force: bool = False,
        top: int = 30,
        min_file_bytes: int = 1_048_576,
        focus_id: int | None = None,
    ) -> dict[str, Any]:
        path = self.normalize(raw)
        top = max(1, min(int(top), 500))
        min_file_bytes = max(0, int(min_file_bytes))
        with self._lock:
            authoritative = focus_id is None or focus_id >= self._focus_id
            if focus_id is not None and authoritative:
                self._focus_id = focus_id
            if not authoritative:
                stale = self._jobs.get(path)
                if stale is None:
                    raise ValueError("stale analyzer navigation request")
                return self._serialize(stale, cached=True)
            if self._active_path is not None and self._active_path != path:
                previous = self._jobs.get(self._active_path)
                if previous is not None and not previous.is_complete:
                    self._pause_locked(previous)
            existing = self._jobs.get(path)
            incompatible = existing is not None and (existing.top != top or existing.min_file_bytes != min_file_bytes or (start and existing.was_cancelled))
            cached = existing is not None and not force and not incompatible
            if existing is None or force or incompatible:
                if existing is not None:
                    existing.cancelled.set()
                    for future in existing.futures:
                        future.cancel()
                job = self._create_job(path, top, min_file_bytes)
                self._jobs[path] = job
                self._schedule(job)
            else:
                job = existing
                if job.paused and not job.is_complete:
                    job.paused = False
                    self._schedule(job)
            job.last_accessed = time.monotonic()
            self._active_path = path
            return self._serialize(job, cached=cached)

    def _pause_locked(self, job: AnalyzerJob) -> None:
        job.cancelled.set()
        for future in job.futures:
            future.cancel()
        for entry in job.entries:
            if entry["state"] == "scanning":
                entry["state"] = "pending"
        self._generation += 1
        job.generation = self._generation
        job.cancelled = threading.Event()
        job.futures = []
        job.next_index = 0
        job.current_scan_path = None
        job.paused = True

    def _create_job(self, path: Path, top: int, min_file_bytes: int) -> AnalyzerJob:
        try:
            children = sorted(path.iterdir(), key=lambda item: item.name.casefold())
        except OSError as exc:
            raise ValueError(f"Analyzer could not list {path}: {exc}") from exc
        self._generation += 1
        entries: list[dict[str, Any]] = []
        for child in children:
            if child.name.startswith(".") or child.is_symlink():
                continue
            try:
                directory = child.is_dir()
            except OSError:
                directory = False
            entries.append({
                "name": child.name,
                "path": str(child),
                "bytes": 0,
                "directory": directory,
                "viewOnly": _view_only(child),
                "state": "pending",
                "fileCount": 0,
            })
        return AnalyzerJob(path, top, min_file_bytes, entries, self._generation)

    def _schedule(self, job: AnalyzerJob) -> None:
        # Do not fill the shared executor with an entire huge parent directory.
        # A newly navigated child can therefore enter the queue immediately.
        for _ in range(min(self._max_workers, len(job.entries))):
            self._submit_next_locked(job)

    def _submit_next_locked(self, job: AnalyzerJob) -> None:
        if job.cancelled.is_set() or job.paused:
            return
        while job.next_index < len(job.entries):
            index = job.next_index
            job.next_index += 1
            if job.entries[index]["state"] != "pending":
                continue
            generation = job.generation
            cancelled = job.cancelled
            future = self._executor.submit(self._measure_entry, job, index, generation, cancelled)
            job.futures.append(future)
            return

    def _measure_entry(self, job: AnalyzerJob, index: int, generation: int, cancelled: threading.Event) -> None:
        with self._lock:
            if cancelled.is_set() or job.generation != generation or self._jobs.get(job.path) is not job:
                return
            entry = job.entries[index]
            entry["state"] = "scanning"
            job.current_scan_path = entry["path"]
        ctx = _WalkContext(Path(entry["path"]), job.min_file_bytes, job.top, self._max_workers - 1)
        self._walk(job, index, ctx, generation, cancelled)

    def _walk(self, job: AnalyzerJob, index: int, ctx: _WalkContext, generation: int,
              cancelled: threading.Event, helper: bool = False) -> None:
        """Drain ``ctx.dirs``; whichever worker empties it finalizes the entry.

        The entry worker seeds the root; helper futures submitted to the same
        executor share the frontier. Workers never wait on futures, so the
        shared pool cannot deadlock and a cancelled job simply drains itself.
        """
        try:
            if not helper and ctx.root_dev is None:
                if self._walk_root(ctx):
                    self._finish_entry(job, index, ctx, generation, cancelled)
                    return
            while True:
                with ctx.lock:
                    if (cancelled.is_set() or job.generation != generation
                            or self._jobs.get(job.path) is not job or not ctx.dirs):
                        return
                    directory = ctx.dirs.popleft()
                batch = self._scan_directory(directory, ctx, cancelled)
                with ctx.lock:
                    if batch.open_failed and directory == ctx.target:
                        ctx.result.root_error = f"{ctx.target}: could not be read"
                    ctx.result.apparent += batch.apparent
                    ctx.result.disk += batch.disk
                    ctx.result.files += batch.files
                    ctx.result.inaccessible += batch.inaccessible
                    ctx.result.boundary += batch.boundary
                    for dev, ino, size, used in batch.links:
                        key = (dev, ino)
                        if key not in ctx.inodes:
                            ctx.inodes.add(key)
                            ctx.result.apparent += size
                            ctx.result.disk += used
                    ctx.result.largest.extend(batch.largest)
                    if len(ctx.result.largest) > ctx.top * 3:
                        ctx.result.largest = sorted(ctx.result.largest, key=lambda item: -item["bytes"])[: ctx.top]
                    ctx.dirs.extend(batch.subdirs)
                    ctx.pending += len(batch.subdirs) - 1
                    finished = ctx.pending == 0
                    while not finished and ctx.helpers < ctx.capacity and len(ctx.dirs) >= 3:
                        ctx.helpers += 1
                        self._executor.submit(self._walk, job, index, ctx, generation, cancelled, True)
                if finished:
                    self._finish_entry(job, index, ctx, generation, cancelled)
                    return
        finally:
            if helper:
                with ctx.lock:
                    ctx.helpers -= 1

    @staticmethod
    def _walk_root(ctx: _WalkContext) -> bool:
        """Stat the entry target. Returns True when the entry is already decided."""
        try:
            info = os.stat(ctx.target, follow_symlinks=False)
        except OSError as exc:
            ctx.result.root_error = f"{ctx.target}: {exc}"
            return True
        ctx.root_dev = info.st_dev
        ctx.result.disk += info.st_blocks * 512
        if not stat.S_ISDIR(info.st_mode):
            ctx.result.apparent += info.st_size
            ctx.result.files = 1
            if info.st_size >= ctx.threshold:
                ctx.result.largest.append({
                    "name": ctx.target.name, "path": str(ctx.target), "bytes": info.st_size,
                    "diskBytes": info.st_blocks * 512, "directory": False, "viewOnly": _view_only(ctx.target),
                })
            return True
        ctx.dirs.append(ctx.target)
        ctx.pending = 1
        return False

    @staticmethod
    def _scan_directory(directory: Path, ctx: _WalkContext, cancelled: threading.Event) -> _DirScan:
        batch = _DirScan()
        try:
            with os.scandir(directory) as iterator:
                for child in iterator:
                    if cancelled.is_set():
                        break
                    try:
                        if child.is_symlink():
                            continue
                        info = child.stat(follow_symlinks=False)
                    except OSError:
                        batch.inaccessible += 1
                        continue
                    if stat.S_ISDIR(info.st_mode):
                        if info.st_dev != ctx.root_dev:
                            batch.boundary += 1
                            continue
                        batch.disk += info.st_blocks * 512
                        batch.subdirs.append(Path(child.path))
                        continue
                    size = info.st_size
                    used = info.st_blocks * 512
                    batch.files += 1
                    if info.st_nlink > 1:
                        batch.links.append((info.st_dev, info.st_ino, size, used))
                    else:
                        batch.apparent += size
                        batch.disk += used
                    if size >= ctx.threshold:
                        batch.largest.append({
                            "name": child.name, "path": child.path, "bytes": size,
                            "diskBytes": used, "directory": False, "viewOnly": _view_only(Path(child.path)),
                        })
        except OSError:
            batch.inaccessible += 1
            batch.open_failed = True
        return batch

    def _finish_entry(self, job: AnalyzerJob, index: int, ctx: _WalkContext,
                      generation: int, cancelled: threading.Event) -> None:
        result = ctx.result
        with self._lock:
            if cancelled.is_set() or job.generation != generation or self._jobs.get(job.path) is not job:
                return
            entry = job.entries[index]
            if result.root_error is not None:
                entry["state"] = "failed"
                job.failed += 1
                job.issues.append(result.root_error)
            else:
                entry["bytes"] = result.apparent
                entry["diskBytes"] = result.disk
                entry["fileCount"] = result.files
                if result.inaccessible:
                    entry["state"] = "partial"
                    entry["inaccessible"] = result.inaccessible
                    job.issues.append(f"{entry['path']}: {result.inaccessible} analyzer entries were inaccessible; result is incomplete")
                    job.partial += 1
                else:
                    entry["state"] = "ready"
                    job.completed += 1
                if result.boundary:
                    entry["skippedFilesystems"] = result.boundary
                for item in result.largest:
                    job.largest_files[item["path"]] = item
                if len(job.largest_files) > job.top * 4:
                    keep = sorted(job.largest_files.values(), key=lambda item: -item["bytes"])[: job.top]
                    job.largest_files = {item["path"]: item for item in keep}
            if job.is_complete:
                job.current_scan_path = None
            else:
                self._submit_next_locked(job)

    def _serialize(self, job: AnalyzerJob, *, cached: bool) -> dict[str, Any]:
        measured = {"ready", "partial"}
        total_bytes = sum(int(entry["bytes"]) for entry in job.entries if entry["state"] in measured)
        total_disk = sum(int(entry.get("diskBytes", 0)) for entry in job.entries if entry["state"] in measured)
        entries = [dict(entry) for entry in job.entries]
        if job.is_complete:
            entries.sort(key=lambda entry: (-int(entry["bytes"]), entry["name"].casefold()))
        for entry in entries:
            entry["isDirectory"] = entry["directory"]
            entry["humanBytes"] = human_bytes(int(entry["bytes"]))
            entry["humanDiskBytes"] = human_bytes(int(entry.get("diskBytes", 0)))
            entry["fileCount"] = int(entry.get("fileCount", 0))
            entry["percent"] = int(entry["bytes"] / total_bytes * 100) if total_bytes and entry["state"] in measured else 0
        largest = sorted(job.largest_files.values(), key=lambda item: -item["bytes"])[: job.top]
        return {
            "path": str(job.path),
            "parent": str(job.path.parent),
            "totalBytes": total_bytes,
            "humanTotal": human_bytes(total_bytes),
            "totalDiskBytes": total_disk,
            "humanTotalDisk": human_bytes(total_disk),
            "entries": entries,
            "largestFiles": [dict(item, humanBytes=human_bytes(item["bytes"]), humanDiskBytes=human_bytes(int(item.get("diskBytes", 0)))) for item in largest],
            "cached": cached,
            "completed": job.completed,
            "partial": job.partial,
            "total": len(job.entries),
            "failed": job.failed,
            "issues": list(job.issues),
            "notes": (["macOS privacy/TCC may require Full Disk Access for the inaccessible locations."]
                      if any("permitted" in issue.lower() or "denied" in issue.lower() or "inaccessible" in issue.lower() for issue in job.issues) else []),
            "currentScanPath": job.current_scan_path,
            "isComplete": job.is_complete,
            "isPaused": job.paused,
            "isCancelled": job.was_cancelled,
            "status": "cancelled" if job.was_cancelled else "partial" if (job.failed or job.partial) else "complete" if job.is_complete else "scanning",
        }

    def progress(self) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(self._active_path) if self._active_path else None
            if job is None:
                return {"active": False}
            done = job.completed + job.failed + job.partial
            total = len(job.entries)
            return {
                "active": not job.is_complete and not job.was_cancelled,
                "service": "analyzer",
                "action": "Dizin arka planda analiz ediliyor",
                "phase": "İPTAL EDİLDİ" if job.was_cancelled else "TARANIYOR" if not job.is_complete else "KISMİ" if (job.failed or job.partial) else "TAMAMLANDI",
                "path": job.current_scan_path or str(job.path),
                "completed": done,
                "total": total,
                "percent": int(done / total * 100) if total else 100,
                "detail": str(job.path),
                "logs": [f"{done}/{total} öğe ölçüldü", job.current_scan_path or str(job.path)],
            }

    def cancel_active(self) -> bool:
        with self._lock:
            job = self._jobs.get(self._active_path) if self._active_path else None
            if job is None or job.is_complete or job.was_cancelled:
                return False
            job.cancelled.set()
            job.was_cancelled = True
            job.paused = False
            job.current_scan_path = None
            for future in job.futures:
                future.cancel()
            for entry in job.entries:
                if entry["state"] in {"pending", "scanning"}:
                    entry["state"] = "cancelled"
            return True

    def approved_paths(self, raw: str | Path) -> set[Path]:
        path = self.normalize(raw)
        with self._lock:
            job = self._jobs.get(path)
            if job is None:
                return set()
            return {Path(entry["path"]) for entry in job.entries} | {Path(item) for item in job.largest_files}

    def invalidate_after_removal(self, removed: Path) -> None:
        removed = removed.absolute()
        with self._lock:
            affected = [path for path in self._jobs if path == removed.parent or path in removed.parents]
            for path in affected:
                job = self._jobs.pop(path)
                job.cancelled.set()
                for future in job.futures:
                    future.cancel()

    def shutdown(self) -> None:
        with self._lock:
            for job in self._jobs.values():
                job.cancelled.set()
        self._executor.shutdown(wait=False, cancel_futures=True)
