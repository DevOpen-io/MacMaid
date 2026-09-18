from __future__ import annotations

import os
import stat
import threading
import time
from pathlib import Path

import pytest

from macmaid.analyzer import IncrementalAnalyzer, _WalkContext


def _wait_complete(analyzer: IncrementalAnalyzer, path: Path, timeout: float = 3, min_file_bytes: int = 1) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = analyzer.snapshot(path, min_file_bytes=min_file_bytes)
        if result["isComplete"]:
            return result
        time.sleep(0.01)
    raise AssertionError(f"analysis did not complete for {path}")


def test_navigation_pauses_previous_scan_and_keeps_partial_cache(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    child = parent / "child"
    sibling = parent / "sibling"
    child.mkdir(parents=True)
    sibling.mkdir()
    (child / "large.bin").write_bytes(b"x" * 4096)

    analyzer = IncrementalAnalyzer(max_workers=1)
    entered = threading.Event()
    release = threading.Event()
    original_walk = analyzer._walk

    def slow_walk(job, index, ctx, generation, cancelled, helper=False):
        entered.set()
        while not release.wait(0.01):
            if cancelled.is_set():
                return
        return original_walk(job, index, ctx, generation, cancelled, helper)

    analyzer._walk = slow_walk  # type: ignore[method-assign]
    try:
        first = analyzer.snapshot(parent, start=True, min_file_bytes=1)
        assert {entry["name"] for entry in first["entries"]} == {"child", "sibling"}
        assert not first["isComplete"]
        assert entered.wait(1)

        nested = analyzer.snapshot(child, start=True, min_file_bytes=1)
        assert [entry["name"] for entry in nested["entries"]] == ["large.bin"]
        assert not nested["isComplete"]
        assert analyzer._jobs[parent].paused is True
        assert analyzer._jobs[parent].current_scan_path is None

        returned = analyzer.snapshot(parent, min_file_bytes=1)
        assert returned["cached"] is True
        assert returned["isPaused"] is False
        assert {entry["name"] for entry in returned["entries"]} == {"child", "sibling"}

        release.set()
        complete = _wait_complete(analyzer, parent)
        assert complete["totalBytes"] == 4096
        assert complete["isComplete"] is True
    finally:
        release.set()
        analyzer.shutdown()


def test_completed_result_is_reused_until_forced(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "file.bin").write_bytes(b"x" * 128)
    analyzer = IncrementalAnalyzer(max_workers=1)
    try:
        analyzer.snapshot(root, start=True, min_file_bytes=1)
        complete = _wait_complete(analyzer, root)
        assert complete["cached"] is True
        assert complete["totalBytes"] == 128

        cached = analyzer.snapshot(root, min_file_bytes=1)
        assert cached["cached"] is True
        assert cached["isComplete"] is True

        refreshed = analyzer.snapshot(root, force=True, min_file_bytes=1)
        assert refreshed["cached"] is False
    finally:
        analyzer.shutdown()


def test_stale_browser_poll_cannot_reactivate_previous_path(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir(); second.mkdir()
    analyzer = IncrementalAnalyzer(max_workers=1)
    try:
        analyzer.snapshot(first, start=True, focus_id=100)
        analyzer.snapshot(second, start=True, focus_id=101)
        stale = analyzer.snapshot(first, focus_id=100)
        assert stale["cached"] is True
        assert analyzer._active_path == second
    finally:
        analyzer.shutdown()


def test_disk_usage_and_apparent_size_differ_on_sparse_files(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    sparse = root / "sparse.bin"
    with open(sparse, "wb") as handle:
        handle.truncate(64 * 1024 * 1024)
    analyzer = IncrementalAnalyzer(max_workers=1)
    try:
        result = _wait_complete(analyzer, root)
        entry = next(item for item in result["entries"] if item["name"] == "sparse.bin")
        assert entry["state"] == "ready"
        assert entry["bytes"] == 64 * 1024 * 1024
        assert entry["diskBytes"] < entry["bytes"]
        assert result["totalDiskBytes"] < result["totalBytes"]
    finally:
        analyzer.shutdown()


def test_hardlinks_are_counted_once_per_entry(tmp_path: Path) -> None:
    root = tmp_path / "root"
    nested = root / "nested"
    nested.mkdir(parents=True)
    source = nested / "source.bin"
    source.write_bytes(b"x" * 1024 * 1024)
    os.link(source, nested / "copy.bin")
    sub = nested / "sub"
    sub.mkdir()
    os.link(source, sub / "deep.bin")
    analyzer = IncrementalAnalyzer(max_workers=2)
    try:
        result = _wait_complete(analyzer, root)
        entry = next(item for item in result["entries"] if item["name"] == "nested")
        assert entry["state"] == "ready"
        assert entry["fileCount"] == 3
        assert entry["bytes"] == 1024 * 1024
    finally:
        analyzer.shutdown()


def test_scan_directory_skips_filesystem_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "root"
    root.mkdir()
    root_dev = os.stat(root).st_dev

    class _FakeEntry:
        def __init__(self, name: str, dev: int) -> None:
            self.name = name
            self.path = str(root / name)
            self._dev = dev

        def is_symlink(self) -> bool:
            return False

        def stat(self, follow_symlinks: bool = False) -> os.stat_result:
            return os.stat_result(
                (stat.S_IFDIR | 0o755, 1, self._dev, 1, 0, 0, 0, 0, 0, 0),
                {"st_blocks": 0},
            )

    class _FakeIterator:
        def __init__(self, entries: list[_FakeEntry]) -> None:
            self._entries = entries

        def __enter__(self):
            return iter(self._entries)

        def __exit__(self, *exc) -> None:
            return None

    real_scandir = os.scandir

    def fake_scandir(path):
        if Path(path) == root:
            return _FakeIterator([_FakeEntry("same-fs", root_dev), _FakeEntry("other-fs", root_dev + 9999)])
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", fake_scandir)
    ctx = _WalkContext(root, 0, 10, 0)
    ctx.root_dev = root_dev
    batch = IncrementalAnalyzer._scan_directory(root, ctx, threading.Event())
    assert batch.boundary == 1
    assert [item.name for item in batch.subdirs] == ["same-fs"]


@pytest.mark.skipif(os.geteuid() == 0, reason="chmod restrictions do not apply to root")
def test_inaccessible_child_marks_entry_partial_instead_of_failed(tmp_path: Path) -> None:
    root = tmp_path / "root"
    parent = root / "parent"
    denied = parent / "denied"
    denied.mkdir(parents=True)
    (denied / "secret.bin").write_bytes(b"x" * 2048)
    (parent / "visible.bin").write_bytes(b"y" * 1024)
    denied.chmod(0)
    analyzer = IncrementalAnalyzer(max_workers=1)
    try:
        result = _wait_complete(analyzer, root)
        entry = next(item for item in result["entries"] if item["name"] == "parent")
        assert result["isComplete"] is True
        assert result["status"] == "partial"
        assert entry["state"] == "partial"
        assert entry["bytes"] == 1024
        assert entry["fileCount"] == 1
        assert entry["inaccessible"] == 1
        assert result["partial"] == 1
        assert result["failed"] == 0
    finally:
        denied.chmod(0o700)
        analyzer.shutdown()


@pytest.mark.skipif(os.geteuid() == 0, reason="chmod restrictions do not apply to root")
def test_unreadable_root_entry_still_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "root"
    denied = root / "denied"
    denied.mkdir(parents=True)
    denied.chmod(0)
    analyzer = IncrementalAnalyzer(max_workers=1)
    try:
        result = _wait_complete(analyzer, root)
        entry = next(item for item in result["entries"] if item["name"] == "denied")
        assert entry["state"] == "failed"
        assert result["failed"] == 1
        assert result["status"] == "partial"
    finally:
        denied.chmod(0o700)
        analyzer.shutdown()


def test_tree_level_parallelism_uses_multiple_workers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "root"
    tree = root / "wide"
    for index in range(12):
        subdir = tree / f"branch{index}"
        subdir.mkdir(parents=True)
        (subdir / "file.bin").write_bytes(b"x" * 256)
    analyzer = IncrementalAnalyzer(max_workers=4)
    threads: set[int] = set()
    original = IncrementalAnalyzer._scan_directory

    def spy(directory, ctx, cancelled):
        threads.add(threading.get_ident())
        time.sleep(0.02)
        return original(directory, ctx, cancelled)

    monkeypatch.setattr(IncrementalAnalyzer, "_scan_directory", staticmethod(spy))
    try:
        result = _wait_complete(analyzer, root, timeout=15)
        entry = next(item for item in result["entries"] if item["name"] == "wide")
        assert entry["state"] == "ready"
        assert entry["fileCount"] == 12
        assert len(threads) > 1
    finally:
        analyzer.shutdown()


def test_small_directories_do_not_spawn_helper_futures(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "tiny").mkdir(parents=True)
    (root / "tiny" / "a.bin").write_bytes(b"x" * 64)
    analyzer = IncrementalAnalyzer(max_workers=4)
    submitted: list[tuple] = []
    original = analyzer._executor.submit

    def spy(fn, *args, **kwargs):
        submitted.append(args)
        return original(fn, *args, **kwargs)

    analyzer._executor.submit = spy  # type: ignore[method-assign]
    try:
        result = _wait_complete(analyzer, root)
        assert result["isComplete"] is True
        helpers = [args for args in submitted if args and args[-1] is True]
        assert helpers == []
    finally:
        analyzer.shutdown()


def test_symlinked_children_are_skipped(tmp_path: Path) -> None:
    root = tmp_path / "root"
    tree = root / "tree"
    tree.mkdir(parents=True)
    (tree / "real.bin").write_bytes(b"x" * 512)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"z" * 4096)
    os.symlink(outside, tree / "link.bin")
    analyzer = IncrementalAnalyzer(max_workers=1)
    try:
        result = _wait_complete(analyzer, root)
        entry = next(item for item in result["entries"] if item["name"] == "tree")
        assert entry["state"] == "ready"
        assert entry["bytes"] == 512
        assert entry["fileCount"] == 1
    finally:
        analyzer.shutdown()


def test_cancel_active_marks_inflight_entries_cancelled(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "dir").mkdir(parents=True)
    (root / "dir" / "file.bin").write_bytes(b"x" * 128)
    analyzer = IncrementalAnalyzer(max_workers=1)
    entered = threading.Event()
    release = threading.Event()
    original_walk = analyzer._walk

    def slow_walk(job, index, ctx, generation, cancelled, helper=False):
        entered.set()
        while not release.wait(0.01):
            if cancelled.is_set():
                return
        return original_walk(job, index, ctx, generation, cancelled, helper)

    analyzer._walk = slow_walk  # type: ignore[method-assign]
    try:
        analyzer.snapshot(root, start=True, min_file_bytes=1)
        assert entered.wait(1)
        assert analyzer.cancel_active() is True
        result = analyzer.snapshot(root, min_file_bytes=1)
        assert result["isCancelled"] is True
        entry = next(item for item in result["entries"] if item["name"] == "dir")
        assert entry["state"] == "cancelled"
    finally:
        release.set()
        analyzer.shutdown()


def test_concurrent_scan_counts_match_sequential(tmp_path: Path) -> None:
    import random
    random.seed(7)
    root = tmp_path / "root"
    tree = root / "tree"
    expected = 0
    files = 0
    for index in range(20):
        subdir = tree / f"d{index}"
        subdir.mkdir(parents=True)
        for file_index in range(25):
            size = random.randint(64, 4096)
            (subdir / f"f{file_index}.bin").write_bytes(b"x" * size)
            expected += size
            files += 1
    sequential = IncrementalAnalyzer(max_workers=1)
    parallel = IncrementalAnalyzer(max_workers=8)
    try:
        seq = _wait_complete(sequential, root)
        par = _wait_complete(parallel, root)
        seq_entry = next(item for item in seq["entries"] if item["name"] == "tree")
        par_entry = next(item for item in par["entries"] if item["name"] == "tree")
        assert seq_entry["bytes"] == par_entry["bytes"] == expected
        assert seq_entry["diskBytes"] == par_entry["diskBytes"]
        assert seq_entry["fileCount"] == par_entry["fileCount"] == files
    finally:
        sequential.shutdown()
        parallel.shutdown()


def test_internal_walk_error_fails_closed_instead_of_stuck(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "root"
    (root / "a").mkdir(parents=True)
    (root / "a" / "f.bin").write_bytes(b"x" * 64)

    def boom(directory, ctx, cancelled):
        raise RuntimeError("internal failure")

    monkeypatch.setattr(IncrementalAnalyzer, "_scan_directory", staticmethod(boom))
    analyzer = IncrementalAnalyzer(max_workers=1)
    try:
        result = _wait_complete(analyzer, root)
        entry = next(item for item in result["entries"] if item["name"] == "a")
        assert entry["state"] == "failed"
        assert result["failed"] == 1
        assert result["isComplete"] is True
    finally:
        analyzer.shutdown()


def test_queued_dir_swapped_to_symlink_is_not_traversed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "loot.bin").write_bytes(b"z" * 9999)
    root = tmp_path / "root"
    (root / "victim").mkdir(parents=True)
    (root / "victim" / "keep.bin").write_bytes(b"k" * 10)
    real_islink = os.path.islink
    monkeypatch.setattr(os.path, "islink", lambda p: True if Path(p).name == "victim" else real_islink(p))
    analyzer = IncrementalAnalyzer(max_workers=1)
    try:
        result = _wait_complete(analyzer, root)
        entry = next(item for item in result["entries"] if item["name"] == "victim")
        assert entry["state"] == "partial"
        assert entry["bytes"] == 0
        assert entry["fileCount"] == 0
    finally:
        analyzer.shutdown()
