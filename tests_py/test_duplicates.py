from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from macmaid import cleaner as cleaning, web
from macmaid.config import Config
from macmaid.duplicates import DuplicateFinder
from macmaid.safety import PathSafetyError


def test_duplicate_finder_uses_size_partial_and_full_hash_without_hardlinks(tmp_path, monkeypatch):
    home = tmp_path / "home"
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    first = downloads / "a.bin"
    second = downloads / "b.bin"
    first.write_bytes(b"same" * 1024)
    second.write_bytes(b"same" * 1024)
    (downloads / "different.bin").write_bytes(b"same" * 1024 + b"x")
    hardlink = downloads / "hardlink.bin"
    hardlink.hardlink_to(first)

    groups = DuplicateFinder().scan([downloads])

    assert len(groups) == 1
    assert {file.path.name for file in groups[0].files} == {"a.bin", "b.bin"}
    assert groups[0].files[0].partial_hash == groups[0].files[1].partial_hash
    assert groups[0].files[0].full_hash == groups[0].files[1].full_hash


def test_duplicate_finder_does_not_follow_symlinks(tmp_path, monkeypatch):
    home = tmp_path / "home"
    downloads = home / "Downloads"
    outside = tmp_path / "outside"
    downloads.mkdir(parents=True)
    outside.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    (outside / "secret.bin").write_bytes(b"same")
    (downloads / "real.bin").write_bytes(b"same")
    (downloads / "link.bin").symlink_to(outside / "secret.bin")

    assert DuplicateFinder().scan([downloads]) == []


def test_duplicate_scan_result_selects_nothing_automatically(tmp_path, monkeypatch):
    home = tmp_path / "home"
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    (downloads / "a.txt").write_text("same")
    (downloads / "b.txt").write_text("same")

    result = DuplicateFinder().scan_result([downloads])

    assert len(result.items) == 2
    assert all("Nothing is selected automatically" in item.reason for item in result.items)


def test_web_duplicate_cleanup_requires_latest_scan_and_review(monkeypatch, tmp_path):
    home = tmp_path / "home"
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(cleaning.os, "geteuid", lambda: 501)
    config = Config(home=home)
    config.ensure_files()
    target = downloads / "a.txt"
    target.write_text("same")
    other = downloads / "b.txt"
    other.write_text("same")
    state = SimpleNamespace(config=config, duplicates={target}, token="secret", generations={"duplicates": 1},
                            review_tokens={}, lock=__import__("threading").RLock())
    handler = object.__new__(web.MacMaidHandler)
    handler.server = SimpleNamespace(state=state)

    with pytest.raises(PermissionError):
        handler._route_post("/api/duplicates/trash", {"paths": [str(other)]})
    prepared = handler._route_post("/api/duplicates/trash", {"paths": [str(target)], "reviewOnly": True})
    with pytest.raises(PermissionError):
        handler._route_post("/api/duplicates/trash", {"paths": [str(target)], "reviewToken": prepared["reviewToken"]})
    prepared = handler._route_post("/api/duplicates/trash", {"paths": [str(target)], "reviewOnly": True})
    result = handler._route_post("/api/duplicates/trash", {"paths": [str(target)], "reviewToken": prepared["reviewToken"], "extraOptIn": True})

    assert result["success"] is True
    assert not target.exists()
    assert any((home / ".Trash").iterdir())


def test_duplicate_restore_validation_rejects_protected_library(tmp_path, monkeypatch):
    home = tmp_path / "home"
    library = home / "Library"
    library.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    with pytest.raises(PathSafetyError):
        cleaning.Cleaner(Config(home=home)).move_analyzer_item_to_trash(library)
