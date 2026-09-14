from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from macmaid import cleaner as cleaning, web
from macmaid.config import Config
from macmaid.smart_downloads import SmartDownloadsScanner


def _home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "Downloads").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


def test_smart_downloads_classifies_target_extensions_and_duplicates(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    downloads = home / "Downloads"
    old = time.time() - 31 * 86400
    installer = downloads / "tool.dmg"
    archive = downloads / "archive.zip"
    incomplete = downloads / "video.crdownload"
    dup1 = downloads / "copy-a.bin"
    dup2 = downloads / "copy-b.bin"
    for path in (installer, archive, incomplete, dup1, dup2):
        path.write_bytes(b"same duplicate payload" if path.name.startswith("copy") else b"x")
    os.utime(installer, (old, old))

    items = SmartDownloadsScanner(older_than_days=30).scan()
    by_name = {item.path.name: set(item.categories) for item in items}

    assert {"Installers", "Old Downloads"} <= by_name["tool.dmg"]
    assert "Archives" in by_name["archive.zip"]
    assert "Incomplete Downloads" in by_name["video.crdownload"]
    assert by_name["copy-a.bin"] == {"Duplicates"}
    assert by_name["copy-b.bin"] == {"Duplicates"}


def test_smart_downloads_does_not_classify_documents_photos_or_source(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    downloads = home / "Downloads"
    for name in ("paper.pdf", "photo.jpg", "main.py", "README.md"):
        path = downloads / name
        path.write_text("content")
        old = time.time() - 365 * 86400
        os.utime(path, (old, old))

    assert SmartDownloadsScanner(older_than_days=30).scan() == []


def test_smart_downloads_skips_symlinks(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "tool.dmg").write_bytes(b"x")
    (home / "Downloads" / "tool.dmg").symlink_to(outside / "tool.dmg")

    assert SmartDownloadsScanner().scan() == []


def test_smart_downloads_scan_result_selects_nothing_automatically(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    (home / "Downloads" / "tool.iso").write_bytes(b"x")

    result = SmartDownloadsScanner().scan_result()

    assert len(result.items) == 1
    assert "Documents, photos and source code are not classified as junk" in result.items[0].reason


def test_web_smart_download_cleanup_requires_scan_and_review(monkeypatch, tmp_path):
    home = _home(tmp_path, monkeypatch)
    monkeypatch.setattr(cleaning.os, "geteuid", lambda: 501)
    config = Config(home=home)
    config.ensure_files()
    target = home / "Downloads" / "old.dmg"
    target.write_bytes(b"x")
    other = home / "Downloads" / "other.dmg"
    other.write_bytes(b"x")
    state = SimpleNamespace(config=config, smart_downloads={target}, token="secret", generations={"smart-downloads": 1},
                            review_tokens={}, lock=__import__("threading").RLock())
    handler = object.__new__(web.MacMaidHandler)
    handler.server = SimpleNamespace(state=state)

    with pytest.raises(PermissionError):
        handler._route_post("/api/smart-downloads/trash", {"paths": [str(other)]})
    prepared = handler._route_post("/api/smart-downloads/trash", {"paths": [str(target)], "reviewOnly": True})
    with pytest.raises(PermissionError):
        handler._route_post("/api/smart-downloads/trash", {"paths": [str(target)], "reviewToken": prepared["reviewToken"]})
    prepared = handler._route_post("/api/smart-downloads/trash", {"paths": [str(target)], "reviewOnly": True})
    result = handler._route_post("/api/smart-downloads/trash", {"paths": [str(target)], "reviewToken": prepared["reviewToken"], "extraOptIn": True})

    assert result["success"] is True
    assert not target.exists()
