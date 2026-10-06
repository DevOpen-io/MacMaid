from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from textual.containers import VerticalScroll
from textual.widgets import ContentSwitcher, DataTable, Static

from macmaid import tui
from macmaid.config import Config


@pytest.fixture(autouse=True)
def isolated_tui(monkeypatch, tmp_path):
    monkeypatch.setattr(tui, "Config", lambda: Config(home=tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(tui, "system_status", _metrics)


def _metrics() -> dict:
    return {
        "cpuPercent": 12.0, "memoryPercent": 34.0, "diskPercent": 56.0,
        "memoryUsed": 1_000, "memoryTotal": 2_000, "diskUsed": 3_000,
        "diskTotal": 4_000, "networkDownPerSecond": 10,
        "networkUpPerSecond": 20, "diskIOPerSecond": 30,
        "thermal": "Normal", "battery": None, "processes": [],
    }


def test_pages_scroll_instead_of_clipping_content() -> None:
    async def exercise() -> None:
        app = tui.MacMaidTUI()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            for page in app.query(".page"):
                assert isinstance(page, VerticalScroll)
                assert page.is_scrollable

    asyncio.run(exercise())


def test_text_outputs_scroll_at_small_terminal() -> None:
    async def exercise() -> None:
        app = tui.MacMaidTUI()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            switcher = app.query_one("#pages", ContentSwitcher)
            long_text = "\n".join(f"line {i} " + "x" * 60 for i in range(60))

            for page_id, static_id, scroll_id in (
                ("page-status-results", "#status-output", "#status-scroll"),
                ("page-review", "#review-body", "#review-scroll"),
                ("page-operation", "#operation-log", "#operation-scroll"),
                ("page-more-results", "#more-output", "#more-scroll"),
            ):
                switcher.current = page_id
                app.query_one(static_id, Static).update(long_text)
                await pilot.pause()
                wrap = app.query_one(scroll_id, VerticalScroll)
                assert wrap.virtual_size.height > wrap.scrollable_content_region.height, page_id
                wrap.scroll_to(y=10_000, animate=False)
                await pilot.pause()
                assert wrap.scroll_y > 0, page_id

    asyncio.run(exercise())


def test_more_results_hides_empty_table_for_text_tools() -> None:
    async def exercise() -> None:
        app = tui.MacMaidTUI()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            table = app.query_one("#more-table", DataTable)
            detail = app.query_one("#more-detail", Static)

            for text_kind in ("snapshots", "doctor", "permissions", "history", "whitelist"):
                app._load_more(text_kind)
                await pilot.pause()
                assert table.display is False, text_kind
                assert detail.display is False, text_kind

            app._load_more("duplicates")
            await pilot.pause()
            assert table.display is True
            assert detail.display is True

    asyncio.run(exercise())


def test_compact_mode_drops_chrome_below_30_rows() -> None:
    async def exercise() -> None:
        app = tui.MacMaidTUI()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert app.screen.has_class("compact")
            assert app.query_one("#wordmark", Static).display is False

        tall = tui.MacMaidTUI()
        async with tall.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            assert not tall.screen.has_class("compact")
            assert tall.query_one("#wordmark", Static).display is True

    asyncio.run(exercise())


def test_tables_have_a_visible_scrollbar() -> None:
    async def exercise() -> None:
        app = tui.MacMaidTUI()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            for table in app.query(DataTable):
                assert table.styles.scrollbar_size_vertical == 1, table.id

    asyncio.run(exercise())


def test_text_tool_focuses_scroll_output_not_hidden_table() -> None:
    async def exercise() -> None:
        app = tui.MacMaidTUI()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            app.query_one("#pages", ContentSwitcher).current = "page-more-results"
            app.current_page = "more-results"
            app._load_more("doctor")
            await pilot.pause()
            assert app.focused is app.query_one("#more-scroll")

            app._load_more("duplicates")
            await pilot.pause()
            assert app.focused is app.query_one("#more-table")

    asyncio.run(exercise())


def test_jk_scrolls_a_focused_scroll_output() -> None:
    async def exercise() -> None:
        app = tui.MacMaidTUI()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            app.query_one("#pages", ContentSwitcher).current = "page-status-results"
            app.current_page = "status-results"
            wrap = app.query_one("#status-scroll", VerticalScroll)
            app.query_one("#status-output", Static).update("\n".join(f"line {i}" for i in range(80)))
            wrap.focus()
            await pilot.pause()
            await pilot.press("j")
            await pilot.pause()
            assert wrap.scroll_y > 0
            await pilot.press("k")
            await pilot.pause()
            assert wrap.scroll_y == 0

    asyncio.run(exercise())


def test_review_page_scrolls_the_plan_with_keys() -> None:
    async def exercise() -> None:
        app = tui.MacMaidTUI()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            app.query_one("#pages", ContentSwitcher).current = "page-review"
            app.current_page = "review"
            wrap = app.query_one("#review-scroll", VerticalScroll)
            app.query_one("#review-body", Static).update("\n".join(f"plan item {i}" for i in range(80)))
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            assert wrap.scroll_y > 0
            await pilot.press("home")
            await pilot.pause()
            assert wrap.scroll_y == 0
            # y still confirms — the scroll keys must not break the prompt flow
            await pilot.press("n")
            await pilot.pause()

    asyncio.run(exercise())


def test_cancel_review_restores_focus_to_visible_widget() -> None:
    async def exercise() -> None:
        app = tui.MacMaidTUI()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            app.query_one("#pages", ContentSwitcher).current = "page-more-results"
            app.current_page = "more-results"
            app.query_one("#more-table", DataTable).display = False
            await pilot.pause()
            app.review_origin = "more-results"
            app.current_page = "review"
            app.query_one("#pages", ContentSwitcher).current = "page-review"
            await pilot.pause()
            app._cancel_review()
            await pilot.pause()
            focused = app.focused
            assert focused is not None
            assert focused.focusable
            assert focused is not app.query_one("#page-review")
            # focus must not land inside the now-hidden review page
            node = focused
            while node is not None:
                assert node is not app.query_one("#page-review")
                node = node.parent

    asyncio.run(exercise())


def test_compact_mode_follows_resize_transitions() -> None:
    async def exercise() -> None:
        app = tui.MacMaidTUI()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            assert not app.screen.has_class("compact")
            await pilot.resize_terminal(80, 24)
            await pilot.pause()
            assert app.screen.has_class("compact")
            await pilot.resize_terminal(80, 40)
            await pilot.pause()
            assert not app.screen.has_class("compact")

    asyncio.run(exercise())
