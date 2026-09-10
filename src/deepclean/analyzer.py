from __future__ import annotations

import os
import threading
import time
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
        return self.completed + self.failed >= len(self.entries)


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
        self._executor = ThreadPoolExecutor(max_workers=self._max_workers, thread_name_prefix="deepclean-analyzer")
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
        target = Path(entry["path"])
        try:
            size, largest = self._walk(target, job.min_file_bytes, job.top, cancelled)
        except Exception as exc:
            with self._lock:
                if self._jobs.get(job.path) is job and job.generation == generation and not cancelled.is_set():
                    entry["state"] = "failed"
                    job.failed += 1
                    job.issues.append(f"{target}: {exc}")
                    if job.is_complete:
                        job.current_scan_path = None
                    else:
                        self._submit_next_locked(job)
            return
        with self._lock:
            if cancelled.is_set() or job.generation != generation or self._jobs.get(job.path) is not job:
                return
            entry["bytes"] = size
            entry["state"] = "ready"
            job.completed += 1
            for item in largest:
                job.largest_files[item["path"]] = item
            if len(job.largest_files) > job.top * 4:
                keep = sorted(job.largest_files.values(), key=lambda item: -item["bytes"])[: job.top]
                job.largest_files = {item["path"]: item for item in keep}
            if job.is_complete:
                job.current_scan_path = None
            else:
                self._submit_next_locked(job)

    @staticmethod
    def _walk(target: Path, threshold: int, top: int, cancelled: threading.Event) -> tuple[int, list[dict[str, Any]]]:
        if cancelled.is_set():
            return 0, []
        try:
            if not target.is_dir():
                size = target.stat().st_size
                largest = [{"name": target.name, "path": str(target), "bytes": size, "directory": False, "viewOnly": _view_only(target)}] if size >= threshold else []
                return size, largest
        except OSError:
            raise
        total = 0
        largest: list[dict[str, Any]] = []
        inaccessible = 0
        stack = [target]
        while stack and not cancelled.is_set():
            directory = stack.pop()
            try:
                with os.scandir(directory) as iterator:
                    for child in iterator:
                        if cancelled.is_set():
                            break
                        try:
                            if child.is_symlink():
                                continue
                            if child.is_dir(follow_symlinks=False):
                                stack.append(Path(child.path))
                                continue
                            stat = child.stat(follow_symlinks=False)
                        except OSError:
                            inaccessible += 1
                            continue
                        total += stat.st_size
                        if stat.st_size >= threshold:
                            path = Path(child.path)
                            largest.append({"name": child.name, "path": child.path, "bytes": stat.st_size, "directory": False, "viewOnly": _view_only(path)})
                            if len(largest) > top * 3:
                                largest = sorted(largest, key=lambda item: -item["bytes"])[:top]
            except OSError:
                inaccessible += 1
                continue
        if inaccessible and not cancelled.is_set():
            raise PermissionError(f"{inaccessible} analyzer entries were inaccessible; result is incomplete")
        return total, sorted(largest, key=lambda item: -item["bytes"])[:top]

    def _serialize(self, job: AnalyzerJob, *, cached: bool) -> dict[str, Any]:
        total_bytes = sum(int(entry["bytes"]) for entry in job.entries if entry["state"] == "ready")
        entries = [dict(entry) for entry in job.entries]
        if job.is_complete:
            entries.sort(key=lambda entry: (-int(entry["bytes"]), entry["name"].casefold()))
        for entry in entries:
            entry["isDirectory"] = entry["directory"]
            entry["humanBytes"] = human_bytes(int(entry["bytes"]))
            entry["percent"] = int(entry["bytes"] / total_bytes * 100) if total_bytes and entry["state"] == "ready" else 0
        largest = sorted(job.largest_files.values(), key=lambda item: -item["bytes"])[: job.top]
        return {
            "path": str(job.path),
            "parent": str(job.path.parent),
            "totalBytes": total_bytes,
            "humanTotal": human_bytes(total_bytes),
            "entries": entries,
            "largestFiles": [dict(item, humanBytes=human_bytes(item["bytes"])) for item in largest],
            "cached": cached,
            "completed": job.completed,
            "total": len(job.entries),
            "failed": job.failed,
            "issues": list(job.issues),
            "notes": (["macOS privacy/TCC may require Full Disk Access for the inaccessible locations."]
                      if any("permitted" in issue.lower() or "denied" in issue.lower() or "inaccessible" in issue.lower() for issue in job.issues) else []),
            "currentScanPath": job.current_scan_path,
            "isComplete": job.is_complete,
            "isPaused": job.paused,
            "isCancelled": job.was_cancelled,
            "status": "cancelled" if job.was_cancelled else "partial" if job.failed else "complete" if job.is_complete else "scanning",
        }

    def progress(self) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(self._active_path) if self._active_path else None
            if job is None:
                return {"active": False}
            done = job.completed + job.failed
            total = len(job.entries)
            return {
                "active": not job.is_complete and not job.was_cancelled,
                "service": "analyzer",
                "action": "Dizin arka planda analiz ediliyor",
                "phase": "İPTAL EDİLDİ" if job.was_cancelled else "TARANIYOR" if not job.is_complete else "KISMİ" if job.failed else "TAMAMLANDI",
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
