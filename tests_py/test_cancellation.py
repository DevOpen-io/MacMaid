from __future__ import annotations

import asyncio
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from textual.widgets import Static

from deepclean import tui, web
from deepclean.analyzer import IncrementalAnalyzer
from deepclean.cancellation import CancellationToken, ScanCancelled
from deepclean.config import Config
from deepclean.models import ActionType, CleanupAction, CleanupCategory, CleanupItem, CleanupProfile, RiskLevel, ScanResult
from deepclean.scanner import Scanner
from deepclean.system import run_command, sizes_of


def candidate(path: Path) -> CleanupItem:
    return CleanupItem(CleanupCategory.USER_CACHES, "candidate", path, 10, RiskLevel.SAFE, "test",
                       CleanupAction(ActionType.REMOVE_PATH))


def test_scanner_cancellation_stops_later_phases_and_marks_result_incomplete(monkeypatch, tmp_path):
    config = Config(home=tmp_path)
    token = CancellationToken()
    scanner = Scanner(config)
    reached = []

    def first(profile):
        reached.append("first")
        token.cancel()
        return [candidate(tmp_path / "cache")]

    monkeypatch.setattr(scanner, "_user_caches", first)
    monkeypatch.setattr(scanner, "_browser_caches", lambda profile: reached.append("second") or [])
    result = scanner.scan(CleanupProfile.SAFE, cancellation=token)
    assert reached == ["first"]
    assert result.status == "cancelled" and result.is_partial
    assert len(result.items) == 1
    assert "incomplete" in result.notes[0]


def test_measurement_error_marks_scan_partial(monkeypatch, tmp_path):
    root = tmp_path / "cache"; root.mkdir()
    scanner = Scanner(Config(home=tmp_path))

    def failed_measure(paths, **kwargs):
        listed = list(paths)
        kwargs["on_error"](listed[0], "Operation not permitted")
        return {}

    monkeypatch.setattr("deepclean.scanner.sizes_of", failed_measure)
    monkeypatch.setattr(scanner, "_user_caches", lambda profile: scanner._candidates(
        [("cache", root, RiskLevel.SAFE, "test", ActionType.REMOVE_PATH, None)],
        CleanupCategory.USER_CACHES, RiskLevel.SAFE,
    ))
    monkeypatch.setattr(scanner, "_browser_caches", lambda profile: [])
    monkeypatch.setattr(scanner, "_application_caches", lambda profile: [])
    monkeypatch.setattr(scanner, "_sandbox_caches", lambda profile: [])
    monkeypatch.setattr(scanner, "_logs", lambda profile: [])
    result = scanner.scan(CleanupProfile.SAFE)
    assert result.status == "partial" and result.issues


def test_permission_limited_scan_is_partial_not_clean(monkeypatch, tmp_path):
    scanner = Scanner(Config(home=tmp_path))

    def limited(profile):
        scanner._issue(tmp_path / "Library", PermissionError("Operation not permitted"))
        return []

    monkeypatch.setattr(scanner, "_user_caches", limited)
    monkeypatch.setattr(scanner, "_browser_caches", lambda profile: [])
    monkeypatch.setattr(scanner, "_application_caches", lambda profile: [])
    monkeypatch.setattr(scanner, "_sandbox_caches", lambda profile: [])
    monkeypatch.setattr(scanner, "_logs", lambda profile: [])
    result = scanner.scan(CleanupProfile.SAFE)
    assert result.status == "partial" and not result.is_complete
    assert result.issues and any("Full Disk Access" in note for note in result.notes)


def test_cancellation_terminates_waiting_subprocess_promptly():
    token = CancellationToken()
    timer = threading.Timer(0.1, token.cancel); timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(ScanCancelled):
            run_command(sys.executable, ["-c", "import time; time.sleep(30)"], timeout=30, on_wait=token.check)
    finally:
        timer.cancel()
    assert time.monotonic() - started < 3


def test_bounded_size_scheduler_does_not_enqueue_after_cancel(monkeypatch, tmp_path):
    import deepclean.system as system
    token = CancellationToken(); calls = []

    def fake_size(path, *, cancel=None, on_error=None):
        calls.append(path)
        token.cancel()
        if cancel: cancel()
        return 1

    monkeypatch.setattr(system, "size_of", fake_size)
    with pytest.raises(ScanCancelled):
        sizes_of([tmp_path / str(index) for index in range(20)], max_workers=2, cancel=token.check)
    assert len(calls) <= 2


def test_analyzer_cancel_stops_active_walk_and_exposes_terminal_state(monkeypatch, tmp_path):
    root = tmp_path / "root"; child = root / "child"; child.mkdir(parents=True)
    started = threading.Event(); stopped = threading.Event()

    def slow_walk(target, threshold, top, cancelled):
        started.set()
        while not cancelled.wait(0.01):
            pass
        stopped.set()
        return 0, []

    monkeypatch.setattr(IncrementalAnalyzer, "_walk", staticmethod(slow_walk))
    analyzer = IncrementalAnalyzer(max_workers=1)
    try:
        analyzer.snapshot(root, start=True)
        assert started.wait(2)
        assert analyzer.cancel_active()
        assert stopped.wait(2)
        snapshot = analyzer.snapshot(root)
        assert snapshot["isCancelled"] and snapshot["status"] == "cancelled"
        assert analyzer.progress()["active"] is False
    finally:
        analyzer.shutdown()


def test_analyzer_measurement_failure_is_partial_not_complete(monkeypatch, tmp_path):
    root = tmp_path / "root"; (root / "child").mkdir(parents=True)
    monkeypatch.setattr(IncrementalAnalyzer, "_walk", staticmethod(lambda *args: (_ for _ in ()).throw(PermissionError("denied"))))
    analyzer = IncrementalAnalyzer(max_workers=1)
    try:
        analyzer.snapshot(root, start=True)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            result = analyzer.snapshot(root)
            if result["isComplete"]: break
            time.sleep(0.01)
        assert result["status"] == "partial" and result["failed"] == 1
    finally:
        analyzer.shutdown()


def test_tui_cancel_key_requests_cooperative_stop_and_partial_result_cannot_clean(monkeypatch):
    async def exercise():
        app = tui.DeepCleanTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            app._show_results("clean")
            token = CancellationToken(); app.scan_cancellations["clean"] = token
            await pilot.press("c")
            assert token.cancelled
            assert "iptal ediliyor" in str(app.query_one("#activity", Static).content)
            partial = ScanResult([candidate(Path("/Users/test/Library/Caches/x"))], status="partial", issues=["denied"])
            app._finish_clean(partial)
            assert not app.clean_selected
            app._confirm_clean()
            assert app.current_page == "clean-results"
    asyncio.run(exercise())


def test_tui_scan_cancel_never_cancels_a_mutation(monkeypatch):
    async def exercise():
        app = tui.DeepCleanTUI()
        async with app.run_test(size=(100, 30)):
            app.current_page = "operation"
            app._mutation_requested = True
            app.action_cancel_scan()
            assert app._mutation_requested
            assert "aktif tarama yok" in str(app.query_one("#activity", Static).content)
    asyncio.run(exercise())


def test_web_cancel_endpoint_and_incomplete_scan_gate(tmp_path):
    token = CancellationToken()
    state = SimpleNamespace(scan_cancellations={"clean": token}, lock=threading.RLock(),
                            progress=SimpleNamespace(finish=lambda *args, **kwargs: None))
    handler = object.__new__(web.DeepCleanHandler); handler.server = SimpleNamespace(state=state)
    response = handler._route_post("/api/scan/cancel", {"service": "clean"})
    assert response["cancelled"] and token.cancelled
    partial = ScanResult([candidate(tmp_path / "cache")], status="cancelled")
    with pytest.raises(PermissionError, match="Incomplete"):
        handler._select_ids(partial, [partial.items[0].id])
