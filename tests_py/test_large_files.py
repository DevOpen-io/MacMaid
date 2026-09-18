from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from macmaid import cleaner as cleaning, web
from macmaid.config import Config
from macmaid.large_files import LargeOldFileScanner, SIZE_FILTERS


def _home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "Downloads").mkdir(parents=True)
    (home / "Movies").mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


def test_large_old_file_filters_and_categories(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    archive = home / "Downloads" / "old.zip"
    archive.write_bytes(b"x" * 20)
    old = time.time() - 91 * 86400
    os.utime(archive, (old, old))
    video = home / "Movies" / "new.mov"
    video.write_bytes(b"x" * 20)

    files = LargeOldFileScanner(min_bytes=10, older_than_days=90).scan([home / "Downloads", home / "Movies"])

    assert [item.path for item in files] == [archive]
    assert set(files[0].categories) >= {"Large files", "Old files", "Archives", "Downloads"}


def test_large_old_scanner_skips_library_and_symlinks(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    library = home / "Library" / "Caches"
    library.mkdir(parents=True)
    (library / "large.bin").write_bytes(b"x" * 20)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "large.bin").write_bytes(b"x" * 20)
    (home / "Downloads" / "link.bin").symlink_to(outside / "large.bin")

    assert LargeOldFileScanner(min_bytes=10).scan([home]) == []


def test_large_old_scan_result_selects_nothing_automatically(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    (home / "Downloads" / "disk.dmg").write_bytes(b"x" * 20)

    result = LargeOldFileScanner(min_bytes=10).scan_result([home / "Downloads"])

    assert len(result.items) == 1
    assert "never selected automatically" in result.items[0].reason
    assert "Disk images" in result.items[0].label


def test_web_large_file_cleanup_requires_scan_and_review(monkeypatch, tmp_path):
    home = _home(tmp_path, monkeypatch)
    monkeypatch.setattr(cleaning.os, "geteuid", lambda: 501)
    config = Config(home=home)
    config.ensure_files()
    target = home / "Downloads" / "large.iso"
    target.write_bytes(b"x" * 20)
    other = home / "Downloads" / "other.iso"
    other.write_bytes(b"x" * 20)
    state = SimpleNamespace(config=config, large_files={target}, token="secret", generations={"large-files": 1},
                            review_tokens={}, lock=__import__("threading").RLock())
    handler = object.__new__(web.MacMaidHandler)
    handler.server = SimpleNamespace(state=state)

    with pytest.raises(PermissionError):
        handler._route_post("/api/large-files/trash", {"paths": [str(other)]})
    prepared = handler._route_post("/api/large-files/trash", {"paths": [str(target)], "reviewOnly": True})
    with pytest.raises(PermissionError):
        handler._route_post("/api/large-files/trash", {"paths": [str(target)], "reviewToken": prepared["reviewToken"]})
    prepared = handler._route_post("/api/large-files/trash", {"paths": [str(target)], "reviewOnly": True})
    result = handler._route_post("/api/large-files/trash", {"paths": [str(target)], "reviewToken": prepared["reviewToken"], "extraOptIn": True})

    assert result["success"] is True
    assert not target.exists()


def test_size_filters_match_roadmap():
    assert set(SIZE_FILTERS) == {"500MB", "1GB", "5GB", "10GB"}


def test_large_old_scan_reports_progress(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    for index in range(3):
        (home / "Downloads" / f"file{index}.bin").write_bytes(b"x" * 20)
    calls = []

    LargeOldFileScanner(min_bytes=10).scan(
        [home / "Downloads"], progress=lambda seen, current: calls.append((seen, current)),
    )

    assert calls and calls[-1][0] >= 1
    assert all(isinstance(current, Path) for _, current in calls)


def test_progress_update_items_zero_total_is_indeterminate():
    progress = web.ProgressState()
    progress.start("largefiles", "scanning")

    progress.update_items(42, 0, "Taranıyor", "/some/path")

    assert progress.value["percent"] == -1
    assert progress.value["completed"] == 42
    assert progress.value["total"] == 0
