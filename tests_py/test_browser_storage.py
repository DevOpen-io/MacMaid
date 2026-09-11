from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from deepclean import browser_storage, cleaner as cleaning, web
from deepclean.browser_storage import BrowserStorageInspector
from deepclean.config import Config


def test_browser_storage_separates_safe_cache_from_user_data(tmp_path, monkeypatch):
    home = tmp_path / "home"
    profile = home / "Library/Application Support/Google/Chrome/Default"
    (profile / "Cache").mkdir(parents=True)
    (profile / "Cookies").write_text("cookie")
    (profile / "Local Storage").mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(browser_storage, "process_running", lambda _: False)

    areas = BrowserStorageInspector().scan()
    by_kind = {area.kind: area for area in areas}

    assert by_kind["Cache"].cleanable is True
    assert by_kind["Cookies"].cleanable is False
    assert by_kind["Local Storage"].cleanable is False


def test_browser_storage_supports_safari_firefox_and_arc(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "Library/Caches/com.apple.Safari").mkdir(parents=True)
    (home / "Library/Application Support/Firefox/Profiles/abc.default-release/cookies.sqlite").parent.mkdir(parents=True)
    (home / "Library/Application Support/Firefox/Profiles/abc.default-release/cookies.sqlite").write_text("cookie")
    (home / "Library/Application Support/Arc/User Data/Default/GPUCache").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(browser_storage, "process_running", lambda _: False)

    browsers = {area.browser for area in BrowserStorageInspector().scan()}

    assert {"Safari", "Firefox", "Arc"}.issubset(browsers)


def test_browser_smart_clean_result_only_contains_safe_cache(tmp_path, monkeypatch):
    home = tmp_path / "home"
    profile = home / "Library/Application Support/Google/Chrome/Default"
    (profile / "Cache").mkdir(parents=True)
    (profile / "IndexedDB").mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(browser_storage, "process_running", lambda _: False)

    result = BrowserStorageInspector().scan_result()

    assert len(result.items) == 1
    assert result.items[0].label.endswith("Cache")


def test_web_browser_smart_clean_requires_scan_review_and_safe_ids(monkeypatch, tmp_path):
    home = tmp_path / "home"
    profile = home / "Library/Application Support/Google/Chrome/Default"
    cache = profile / "Cache"
    cache.mkdir(parents=True)
    (cache / "payload").write_text("x")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(cleaning.os, "geteuid", lambda: 501)
    monkeypatch.setattr(browser_storage, "process_running", lambda _: False)
    config = Config(home=home); config.ensure_files()
    state = SimpleNamespace(config=config, token="secret", generations={}, review_tokens={}, lock=__import__("threading").RLock())
    handler = object.__new__(web.DeepCleanHandler); handler.server = SimpleNamespace(state=state)

    scan = handler._route_get("/api/browser-storage", {})
    item_id = scan["items"][0]["id"]
    prepared = handler._route_post("/api/browser-storage/clean", {"itemIds": [item_id], "reviewOnly": True})
    result = handler._route_post("/api/browser-storage/clean", {"itemIds": [item_id], "reviewToken": prepared["reviewToken"]})

    assert result["success"] is True
    assert not cache.exists()


def test_web_browser_smart_clean_blocks_without_scan(tmp_path):
    handler = object.__new__(web.DeepCleanHandler)
    handler.server = SimpleNamespace(state=SimpleNamespace(browser_storage=None))
    with pytest.raises(ValueError):
        handler._route_post("/api/browser-storage/clean", {"itemIds": []})
