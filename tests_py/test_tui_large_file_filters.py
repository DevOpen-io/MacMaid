from __future__ import annotations

import asyncio
import time
from pathlib import Path

from macmaid import tui
from macmaid.config import Config
from macmaid.models import ActionType, CleanupAction, CleanupCategory, CleanupItem, RiskLevel, ScanResult


def test_large_file_size_and_age_keys_filter_cached_results_without_rescanning(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(tui, "Config", lambda: Config(home=tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    huge_old = tmp_path / "huge_old.bin"
    medium_old = tmp_path / "medium_old.bin"
    huge_recent = tmp_path / "huge_recent.bin"
    huge_old.write_bytes(b"x")
    medium_old.write_bytes(b"x")
    huge_recent.write_bytes(b"x")

    item_huge_old = CleanupItem(CleanupCategory.TRASH, huge_old.name, huge_old, 2 * 1000**3, RiskLevel.AGGRESSIVE, "test", CleanupAction(ActionType.MOVE_TO_TRASH))
    item_medium_old = CleanupItem(CleanupCategory.TRASH, medium_old.name, medium_old, 600 * 1000**2, RiskLevel.AGGRESSIVE, "test", CleanupAction(ActionType.MOVE_TO_TRASH))
    item_huge_recent = CleanupItem(CleanupCategory.TRASH, huge_recent.name, huge_recent, 2 * 1000**3, RiskLevel.AGGRESSIVE, "test", CleanupAction(ActionType.MOVE_TO_TRASH))

    now = time.time()

    async def exercise() -> None:
        app = tui.MacMaidTUI()
        async with app.run_test() as pilot:
            app._show_results("more")
            app.more_kind = "large-files"
            app.large_cache = ScanResult([item_huge_old, item_medium_old, item_huge_recent])
            app.large_mtimes = {
                item_huge_old.id: now - 100 * 86400,
                item_medium_old.id: now - 100 * 86400,
                item_huge_recent.id: now - 2 * 86400,
            }
            rescans: list[str] = []
            monkeypatch.setattr(app, "_load_more", lambda kind: rescans.append(kind))

            # Filter size to >= 1 GB (key '2')
            await pilot.press("2")
            assert not rescans
            assert app.more_result is not None
            assert {item.id for item in app.more_result.items} == {item_huge_old.id, item_huge_recent.id}

            # Filter age to >= 90 days (key 'c')
            await pilot.press("c")
            assert not rescans
            assert app.more_result is not None
            assert [item.id for item in app.more_result.items] == [item_huge_old.id]

            # Reset age to All (key 'a')
            await pilot.press("a")
            assert not rescans
            assert app.more_result is not None
            assert {item.id for item in app.more_result.items} == {item_huge_old.id, item_huge_recent.id}

            # Reset size to All supported (key '0')
            await pilot.press("0")
            assert not rescans
            assert app.more_result is not None
            assert {item.id for item in app.more_result.items} == {item_huge_old.id, item_medium_old.id, item_huge_recent.id}

    asyncio.run(exercise())
