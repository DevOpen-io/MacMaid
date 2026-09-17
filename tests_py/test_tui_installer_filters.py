from __future__ import annotations

import asyncio
import time
from pathlib import Path

from macmaid import tui
from macmaid.config import Config
from macmaid.models import ActionType, CleanupAction, CleanupCategory, CleanupItem, RiskLevel, ScanResult


def test_installer_age_keys_filter_cached_results_without_rescanning(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(tui, "Config", lambda: Config(home=tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    old = tmp_path / "Downloads" / "old.dmg"; recent = tmp_path / "Downloads" / "recent.dmg"
    old.parent.mkdir(parents=True); old.write_bytes(b"old"); recent.write_bytes(b"recent")
    old_item = CleanupItem(CleanupCategory.INSTALLERS, old.name, old, 1, RiskLevel.SAFE, "test", CleanupAction(ActionType.MOVE_TO_TRASH))
    recent_item = CleanupItem(CleanupCategory.INSTALLERS, recent.name, recent, 1, RiskLevel.SAFE, "test", CleanupAction(ActionType.MOVE_TO_TRASH))

    async def exercise() -> None:
        app = tui.MacMaidTUI()
        async with app.run_test() as pilot:
            app._show_results("more")
            app.more_kind = "installers"
            app.installer_cache = ScanResult([old_item, recent_item])
            app.installer_mtimes = {old_item.id: time.time() - 31 * 86400, recent_item.id: time.time() - 2 * 86400}
            rescans: list[str] = []
            monkeypatch.setattr(app, "_load_more", lambda kind: rescans.append(kind))

            await pilot.press("1")

            assert not rescans
            assert app.more_result is not None
            assert [item.id for item in app.more_result.items] == [old_item.id]

    asyncio.run(exercise())
