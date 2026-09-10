from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest

from textual.widgets import ContentSwitcher, DataTable, ListView, Select, Static

from deepclean.models import RiskLevel

from deepclean import tui
from deepclean.config import Config
from deepclean.models import ActionType, CleanupAction, CleanupCategory, CleanupItem, ScanResult
from deepclean.review import cleanup_plan


@pytest.fixture(autouse=True)
def isolated_tui(monkeypatch, tmp_path):
    monkeypatch.setattr(tui, "Config", lambda: Config(home=tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(tui, "system_status", _metrics)


def _scan_result(label: str) -> ScanResult:
    return ScanResult(items=[CleanupItem(
        CleanupCategory.USER_CACHES, label, None, 1024, RiskLevel.SAFE,
        "Synthetic cache", CleanupAction(ActionType.REMOVE_PATH),
    )])


def _metrics() -> dict:
    return {
        "cpuPercent": 12.0, "memoryPercent": 34.0, "diskPercent": 56.0,
        "memoryUsed": 1_000, "memoryTotal": 2_000, "diskUsed": 3_000,
        "diskTotal": 4_000, "networkDownPerSecond": 10,
        "networkUpPerSecond": 20, "diskIOPerSecond": 30,
        "thermal": "Normal", "battery": None, "processes": [],
    }


def test_textual_tui_navigation_and_page_tables(monkeypatch) -> None:
    monkeypatch.setattr(tui, "system_status", _metrics)

    async def exercise() -> None:
        app = tui.DeepCleanTUI()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            switcher = app.query_one("#pages", ContentSwitcher)
            assert switcher.current == "page-dashboard"
            assert app.query_one("#wordmark", Static)
            nav = app.query_one("#nav", ListView)
            assert len(nav.children) == len(tui.NAVIGATION)
            assert nav.children[0].id == "nav-clean"

            for key, expected in (("1", "page-clean"), ("4", "page-analyzer-results"), ("6", "page-developer"), ("7", "page-status-results")):
                await pilot.press("m", key); await pilot.pause()
                assert switcher.current == expected

            await pilot.press("m", "1"); await pilot.pause()
            assert switcher.current == "page-clean"
            await pilot.press("7"); await pilot.pause()
            assert switcher.current == "page-clean"
            await pilot.press("2"); await pilot.pause()
            assert app.query_one("#clean-actions", ListView).index == 1
            assert switcher.current == "page-clean"
            await pilot.press("m", "7"); await pilot.pause()
            assert switcher.current == "page-status-results"

            await pilot.press("ctrl+n", "k", "enter"); await pilot.pause()
            assert app.query_one("#nav", ListView).index == 5
            assert switcher.current == "page-developer"

            await pilot.press("escape"); await pilot.pause()
            assert switcher.current == "page-dashboard"
            await pilot.press("4", "l"); await pilot.pause()
            assert app.focused is not app.query_one("#nav", ListView)
            assert len(app.query_one("#clean-table", DataTable).columns) == 5
            assert len(app.query_one("#analyzer-table", DataTable).columns) == 6
            assert len(app.query_one("#more-table", DataTable).columns) == 5

            app._update_clean_progress(37, "Sandbox caches", "/Users/test/Library/Containers/current-file")
            assert str(app.query_one("#clean-target", Static).content) == "/Users/test/Library/Containers/current-file"

            app._set_state("analyzer", "Dizin listeleniyor…")
            assert app.query_one("#analyzer-state", Static).has_class("busy")
            app._set_state("analyzer", "2 GB ölçüldü · 0 hata · 0 atlandı")
            assert app.query_one("#analyzer-state", Static).has_class("success")
            app._set_state("analyzer", "2 GB ölçüldü · 1 hata")
            assert app.query_one("#analyzer-state", Static).has_class("error")

    asyncio.run(exercise())


def test_tui_keyboard_submenus_replace_dropdowns(monkeypatch) -> None:
    monkeypatch.setattr(tui, "system_status", _metrics)

    async def exercise() -> None:
        app = tui.DeepCleanTUI()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("6")
            await pilot.pause()

            menu = app.query_one("#developer-actions", ListView)
            assert app.focused is menu
            assert menu.index == 0
            assert menu.children[0].has_class("-highlight")
            assert not app.query(Select)

            await pilot.press("down")
            assert menu.index == 1
            assert menu.children[1].has_class("-highlight")

            scans: list[str] = []
            app._scan_developer = lambda: scans.append(app.developer_kind)  # type: ignore[method-assign]
            app._run_menu_action("developer-kind-sdk")
            assert scans == ["sdk"]
            assert app.query_one("#pages", ContentSwitcher).current == "page-developer-results"
            assert app.query_one("#developer-progress")

            await pilot.press("escape")
            assert app.query_one("#pages", ContentSwitcher).current == "page-developer"
            await pilot.press("escape")
            assert app.query_one("#pages", ContentSwitcher).current == "page-dashboard"

    asyncio.run(exercise())


def test_every_tool_section_has_a_separate_results_screen(monkeypatch) -> None:
    monkeypatch.setattr(tui, "system_status", _metrics)

    async def exercise() -> None:
        app = tui.DeepCleanTUI()
        async with app.run_test(size=(120, 40)):
            for section in ("clean", "apps", "analyzer", "purge", "developer", "optimize", "status", "more"):
                app._show_results(section)
                assert app.query_one("#pages", ContentSwitcher).current == f"page-{section}-results"
                assert app.current_page == f"{section}-results"

    asyncio.run(exercise())


def test_review_requires_explicit_y_and_defaults_enter_to_cancel(monkeypatch) -> None:
    async def exercise() -> None:
        app = tui.DeepCleanTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            called: list[bool] = []
            app._show_results("clean")
            result = _scan_result("Reviewed action")
            app._finish_clean(result)
            app._confirm(cleanup_plan("Review", result.items), lambda: called.append(True))
            assert app.current_page == "review" and not called
            assert "Estimated" in str(app.query_one("#review-body", Static).content)
            await pilot.press("escape")
            assert app.current_page == "clean-results" and not called
            app._confirm(cleanup_plan("Review", result.items), lambda: called.append(True))
            await pilot.press("enter")
            assert app.current_page == "clean-results" and not called
            app._confirm(cleanup_plan("Review", result.items), lambda: called.append(True))
            await pilot.press("y")
            assert called == [True]

    asyncio.run(exercise())


def test_tui_selection_change_invalidates_visible_review(monkeypatch) -> None:
    async def exercise() -> None:
        app = tui.DeepCleanTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            app._show_results("clean")
            app._finish_clean(_scan_result("first"))
            called = []
            plan = app._current_clean_plan()
            app._confirm(plan, lambda: called.append(True), app._current_clean_plan)
            app.clean_selected.clear()
            await pilot.press("y")
            assert not called
            assert app.current_page == "clean-results"
            assert app.review_plan is None
            assert "eski onay iptal" in str(app.query_one("#activity", Static).content)
    asyncio.run(exercise())


def test_operation_summary_returns_home_only_after_completion(monkeypatch) -> None:
    monkeypatch.setattr(tui, "system_status", _metrics)

    async def exercise() -> None:
        app = tui.DeepCleanTUI()
        async with app.run_test(size=(120, 40)) as pilot:
            before = app._system_snapshot()
            app._begin_operation("Fixture temizliği", 1, before)
            app._operation_item(1, 1, "fixture cache", "running")
            app._operation_item(1, 1, "fixture cache", "success")
            app._complete_operation("Fixture tamamlandı", "1 KB kazanıldı", before, before)
            await pilot.pause()

            assert app.query_one("#pages", ContentSwitcher).current == "page-operation"
            assert app.operation_done
            operation_summary = str(app.query_one("#operation-summary", Static).content)
            assert "ÖNCE" in operation_summary and "SONRA" in operation_summary
            assert "GÖZLENEN BOŞ ALAN FARKI" in operation_summary
            assert "kesin atfedilemez" in operation_summary

            await pilot.press("enter")
            await pilot.pause()
            assert app.query_one("#pages", ContentSwitcher).current == "page-dashboard"

    asyncio.run(exercise())


def test_tui_blocks_duplicate_mutations_while_worker_starts(monkeypatch) -> None:
    async def exercise() -> None:
        app = tui.DeepCleanTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            app._show_results("clean")
            app._finish_clean(_scan_result("fixture"))
            calls = []
            monkeypatch.setattr(app, "_clean_apply_worker", lambda *args: calls.append(args))
            app._confirm_clean()
            assert app.current_page == "review" and not calls
            await pilot.press("y")
            assert len(calls) == 1
            app._confirm(cleanup_plan("duplicate", _scan_result("duplicate").items), lambda: calls.append("duplicate"))
            app.open_page("developer")
            assert len(calls) == 1
            assert app.current_page == "review"
    asyncio.run(exercise())


def test_manual_fallback_requires_selection_and_second_authorization(monkeypatch) -> None:
    async def exercise() -> None:
        app = tui.DeepCleanTUI()
        async with app.run_test(size=(100, 30)) as pilot:
            app._show_results("clean")
            result = _scan_result("manual")
            result.items[0].risk = RiskLevel.MANUAL_ONLY
            result.items[0].action.kind = ActionType.MANUAL_CACHE_FALLBACK
            app._finish_clean(result)
            calls = []
            monkeypatch.setattr(app, "_clean_apply_worker", lambda *args: calls.append(args))
            assert not app.clean_selected
            app._confirm_clean()
            assert not calls
            app.clean_selected.add(0)
            app._confirm_clean()
            assert app.current_page == "review" and not calls
            await pilot.press("escape")
            assert app.current_page == "clean-results" and not calls
            app._confirm_clean()
            await pilot.press("y")
            assert app.review_extra_armed and not calls
            await pilot.press("y")
            assert len(calls) == 1 and calls[0][1] is True
    asyncio.run(exercise())


def test_tui_risk_cells_are_clear_and_distinct() -> None:
    assert tui.DeepCleanTUI._risk_cell(RiskLevel.SAFE).plain == "SAFE"
    assert tui.DeepCleanTUI._risk_cell(RiskLevel.MODERATE).plain == "MODERATE"
    assert tui.DeepCleanTUI._risk_cell(RiskLevel.AGGRESSIVE).plain == "AGGRESSIVE"
    assert tui.DeepCleanTUI._risk_cell(RiskLevel.MANUAL_ONLY).plain == "MANUAL"


@pytest.mark.parametrize("late_failure", [False, True])
def test_clean_profile_switch_discards_results_and_late_callbacks(monkeypatch, late_failure) -> None:
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    class FakeScanner:
        def __init__(self, config):
            pass

        def scan(self, profile, progress, cancellation=None):
            if profile is tui.CleanupProfile.AGGRESSIVE:
                started.set()
                assert release.wait(10)
                progress(25, "obsolete scan", "obsolete path")
                finished.set()
                if late_failure:
                    raise OSError("obsolete scan failure")
                return _scan_result("obsolete")
            return _scan_result("developer")

    monkeypatch.setattr(tui, "Scanner", FakeScanner)

    async def exercise() -> None:
        app = tui.DeepCleanTUI()
        async with app.run_test(size=(120, 40)) as pilot:
            app._show_results("clean")
            app._finish_clean(_scan_result("previous cleanup"))
            app._run_menu_action("clean-profile-aggressive")
            assert app.clean_result is None
            assert not app.clean_selected
            assert app.query_one("#clean-table", DataTable).row_count == 0
            assert not str(app.query_one("#clean-detail", Static).content)
            try:
                assert await asyncio.to_thread(started.wait, 5)
                await pilot.press("escape", "escape", "6")
                assert app.current_page == "developer"
                app.open_page("clean")
                app._run_menu_action("clean-profile-developer")
                await app.workers.wait_for_complete()
                assert app.clean_result.items[0].label == "developer"
                release.set()
                assert await asyncio.to_thread(finished.wait, 5)
                await pilot.pause()
                assert app.clean_result.items[0].label == "developer"
                assert "obsolete" not in str(app.query_one("#clean-target", Static).content)
                assert "obsolete" not in str(app.query_one("#clean-state", Static).content)
                await pilot.press("escape")
                assert app.clean_result is None
                assert not app.clean_selected
            finally:
                release.set()

    asyncio.run(exercise())


def test_all_scan_tools_clear_review_state_before_rescan(monkeypatch) -> None:
    async def exercise() -> None:
        app = tui.DeepCleanTUI()
        async with app.run_test(size=(120, 40)):
            for worker in ("_clean_worker", "_apps_worker", "_projects_worker", "_developer_worker", "_more_worker"):
                monkeypatch.setattr(app, worker, lambda *args: None)
            cases = (
                ("clean", app._start_clean_scan, "clean_result", "clean_selected"),
                ("apps", app._scan_apps, "app_components", "component_selected"),
                ("purge", app._scan_projects, "artifacts", "purge_selected"),
                ("developer", app._scan_developer, "dev_cache_result", "dev_selected"),
                ("more", lambda: app._load_more("installers"), "more_result", "more_selected"),
            )
            for section, scan, result_attr, selected_attr in cases:
                app._show_results(section)
                setattr(app, result_attr, _scan_result("old"))
                getattr(app, selected_attr).add(0)
                table = app.query_one(f"#{section}-table", DataTable)
                table.add_row(*["old"] * len(table.columns))
                app.query_one(f"#{section}-detail", Static).update("old path")
                scan()
                assert not getattr(app, result_attr)
                assert not getattr(app, selected_attr)
                assert table.row_count == 0
                assert not str(app.query_one(f"#{section}-detail", Static).content)

    asyncio.run(exercise())


@pytest.mark.parametrize("size", [(80, 24), (120, 40)])
def test_all_tools_keyboard_smoke(monkeypatch, size) -> None:
    monkeypatch.setattr(tui.ApplicationManager, "scan", lambda self: [])
    monkeypatch.setattr(tui.ProjectPurgeManager, "scan", lambda self: [])
    monkeypatch.setattr(tui.DeveloperInventory, "scan", lambda self, kind: [])
    monkeypatch.setattr(tui.PackageManagerCacheScanner, "scan", lambda self: ScanResult())
    monkeypatch.setattr(tui, "scan_leftovers", lambda config: ScanResult())
    monkeypatch.setattr(tui, "scan_installers", lambda: ScanResult())
    monkeypatch.setattr(tui, "doctor", lambda: [])
    monkeypatch.setattr(tui, "list_snapshots", lambda: [])
    monkeypatch.setattr(tui, "history", lambda count: [])

    async def exercise() -> None:
        app = tui.DeepCleanTUI()
        async with app.run_test(size=size) as pilot:
            for index, (section, *_) in enumerate(tui.NAVIGATION, 1):
                app.open_page("dashboard")
                await pilot.press(str(index))
                await app.workers.wait_for_complete()
                assert app.current_page in {section, f"{section}-results"}
                if section in {"developer", "more"}:
                    actions = app.query_one(f"#{section}-actions", ListView)
                    action_ids = [item.id for item in actions.children if item.id != "action-back"]
                    for action_id in action_ids:
                        app._run_menu_action(action_id.removeprefix("action-"))
                        await app.workers.wait_for_complete()
                        assert app.current_page == f"{section}-results"
                        await pilot.press("escape")
                await pilot.press("escape")
                assert app.current_page == "dashboard"

    asyncio.run(exercise())


def test_cleanup_keyboard_flow_returns_to_fresh_scan(monkeypatch) -> None:
    from deepclean.models import OperationResult

    executed = []

    class FakeCleaner:
        def __init__(self, config):
            pass

        def execute(self, items, **kwargs):
            executed.extend(items)
            return OperationResult(freed=1024)

    monkeypatch.setattr(tui, "Cleaner", FakeCleaner)
    monkeypatch.setattr(tui.DeepCleanTUI, "_system_snapshot", staticmethod(lambda: {}))

    async def exercise() -> None:
        app = tui.DeepCleanTUI()
        async with app.run_test(size=(120, 40)) as pilot:
            app._show_results("clean")
            app._finish_clean(_scan_result("synthetic cleanup"))
            await pilot.press("enter")
            assert app.current_page == "review" and not executed
            await pilot.press("y")
            await app.workers.wait_for_complete()
            assert len(executed) == 1
            assert app.current_page == "operation"
            assert app.operation_done
            assert app.clean_result is None
            await pilot.press("enter", "6", "escape", "1")
            assert app.current_page == "clean"
            monkeypatch.setattr(app, "_clean_worker", lambda *args: None)
            app._run_menu_action("clean-profile-developer")
            assert app.query_one("#clean-table", DataTable).row_count == 0
            app._confirm_clean()
            assert len(executed) == 1

    asyncio.run(exercise())


def test_analyzer_navigation_clears_previous_directory(monkeypatch, tmp_path) -> None:
    async def exercise() -> None:
        app = tui.DeepCleanTUI()
        async with app.run_test(size=(120, 40)):
            monkeypatch.setattr(app, "_analysis_worker", lambda *args: None)
            app._show_results("analyzer")
            old = {"path": str(tmp_path), "entries": [], "isComplete": True}
            app._finish_analysis(old, app.analyzer_focus)
            table = app.query_one("#analyzer-table", DataTable)
            table.add_row("ready", "1 KB", "", "", "old", str(tmp_path / "old"))
            old_focus = app.analyzer_focus
            app._request_analysis(tmp_path / "new")
            assert table.row_count == 0
            assert app.analyzer_snapshot is None
            app._finish_analysis(old, old_focus)
            assert app.analyzer_snapshot is None
            app.open_page("clean")
            assert not app.analyzer_views

    asyncio.run(exercise())
