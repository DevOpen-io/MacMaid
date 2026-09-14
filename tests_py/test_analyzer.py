from __future__ import annotations

import threading
import time
from pathlib import Path

from macmaid.analyzer import IncrementalAnalyzer


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

    def slow_walk(target: Path, threshold: int, top: int, cancelled: threading.Event):
        entered.set()
        while not release.wait(0.01):
            if cancelled.is_set():
                return 0, []
        return original_walk(target, threshold, top, cancelled)

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
