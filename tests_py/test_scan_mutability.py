from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from macmaid import cleaner as cleaning, web
from macmaid.cleaner import Cleaner
from macmaid.config import Config
from macmaid.models import ActionType, CleanupAction, CleanupCategory, CleanupItem, RiskLevel, ScanResult
from macmaid.scanner import PackageManagerCacheScanner, scan_installers, scan_leftovers
from macmaid.system import ensure_tool_search_path


def _denied_size(path, *, cancel=None, on_error=None):
    if on_error:
        on_error(path, "Operation not permitted")
    return 0


def _gate():
    handler = object.__new__(web.MacMaidHandler)
    handler.server = SimpleNamespace(state=SimpleNamespace())
    return handler._select_ids


def test_leftover_measurement_errors_keep_result_mutable(monkeypatch, tmp_path):
    home = tmp_path / "home"
    stale = home / "Library" / "Caches" / "com.example.orphan"
    stale.mkdir(parents=True)
    (stale / "blob.bin").write_bytes(b"cache")
    old = time.time() - 60 * 86400
    os.utime(stale, (old, old))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr("macmaid.scanner.size_of", _denied_size)

    result = scan_leftovers(Config(home=home), older_than_days=30)

    assert result.status == "complete" and result.is_complete
    assert result.items and result.issues
    assert any("Full Disk Access" in note for note in result.notes)
    _gate()(result, [result.items[0].id])


def test_leftover_app_enumeration_failure_blocks_mutation(monkeypatch, tmp_path):
    home = tmp_path / "home"
    (home / "Library" / "Caches").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    real_rglob = Path.rglob

    def fail_rglob(self, pattern):
        if str(self) == "/Applications":
            raise PermissionError("Operation not permitted")
        return real_rglob(self, pattern)

    monkeypatch.setattr(Path, "rglob", fail_rglob)
    result = scan_leftovers(Config(home=home), older_than_days=30)

    assert result.status == "partial" and not result.is_complete
    assert result.issues
    with pytest.raises(PermissionError, match="Incomplete"):
        _gate()(result, ["anything"])


def test_installer_measurement_errors_keep_result_mutable(monkeypatch, tmp_path):
    home = tmp_path / "home"
    installer = home / "Downloads" / "old.dmg"
    installer.parent.mkdir(parents=True)
    installer.write_bytes(b"dmg")
    old = time.time() - 60 * 86400
    os.utime(installer, (old, old))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr("macmaid.scanner.size_of", _denied_size)

    result = scan_installers(older_than_days=30)

    assert result.status == "complete" and result.is_complete
    assert [item.path for item in result.items] == [installer]
    assert result.issues
    _gate()(result, [result.items[0].id])


def test_package_cache_measurement_errors_keep_result_mutable(monkeypatch, tmp_path):
    home = tmp_path / "home"
    cacache = home / ".npm" / "_cacache"
    cacache.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr("macmaid.scanner.which", lambda name: "/fake/bin/npm" if name == "npm" else None)
    monkeypatch.setattr("macmaid.scanner.run_command",
                        lambda exe, args, **kw: SimpleNamespace(succeeded=True, status=0, stdout="", stderr=""))
    monkeypatch.setattr("macmaid.scanner.size_of", _denied_size)

    result = PackageManagerCacheScanner(Config(home=home)).scan()

    npm_items = [item for item in result.items if "npm" in item.label]
    assert result.status == "complete" and result.is_complete
    assert npm_items and npm_items[0].path == cacache
    assert result.issues
    _gate()(result, [npm_items[0].id])


def test_package_cache_scan_skips_verified_empty_targets(monkeypatch, tmp_path):
    home = tmp_path / "home"
    (home / ".npm").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr("macmaid.scanner.which", lambda name: "/fake/bin/npm" if name == "npm" else None)
    monkeypatch.setattr("macmaid.scanner.run_command",
                        lambda exe, args, **kw: SimpleNamespace(succeeded=True, status=0, stdout="", stderr=""))
    monkeypatch.setattr("macmaid.scanner.size_of", lambda path, **kw: 0)

    result = PackageManagerCacheScanner(Config(home=home)).scan()

    assert not [item for item in result.items if "npm" in item.label]
    assert result.is_complete


def test_package_cache_scan_resolves_npm_cache_path_from_probe(monkeypatch, tmp_path):
    home = tmp_path / "home"
    cacache = home / "custom-npm-cache" / "_cacache"
    cacache.mkdir(parents=True)
    (cacache / "blob.bin").write_bytes(b"x" * 2 * 1024 * 1024)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr("macmaid.scanner.which", lambda name: "/fake/bin/npm" if name == "npm" else None)

    def fake_run(exe, args, **kw):
        if args[:2] == ["config", "get"]:
            return SimpleNamespace(succeeded=True, status=0, stdout=str(cacache.parent), stderr="")
        return SimpleNamespace(succeeded=True, status=0, stdout="", stderr="")

    monkeypatch.setattr("macmaid.scanner.run_command", fake_run)
    result = PackageManagerCacheScanner(Config(home=home)).scan()

    npm_items = [item for item in result.items if item.label == "npm cache clean"]
    assert npm_items and npm_items[0].path == cacache
    assert npm_items[0].estimated_bytes > 0


def test_package_cache_npm_rows_target_cleaned_subdirs(monkeypatch, tmp_path):
    home = tmp_path / "home"
    for sub in ("_cacache", "_npx", "_libvips", "_logs"):
        target = home / ".npm" / sub
        target.mkdir(parents=True)
        (target / "blob.bin").write_bytes(b"x" * 2 * 1024 * 1024)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr("macmaid.scanner.which", lambda name: "/fake/bin/npm" if name == "npm" else None)
    monkeypatch.setattr("macmaid.scanner.run_command",
                        lambda exe, args, **kw: SimpleNamespace(succeeded=True, status=0, stdout="", stderr=""))

    result = PackageManagerCacheScanner(Config(home=home)).scan()

    rows = {item.label: item for item in result.items}
    assert rows["npm cache clean"].path == home / ".npm/_cacache"
    npx = rows["npx package cache · manual fallback"]
    assert npx.path == home / ".npm/_npx" and npx.risk is RiskLevel.MANUAL_ONLY
    assert rows["npm binary caches · manual fallback"].path == home / ".npm/_libvips"
    assert rows["npm request logs · manual fallback"].path == home / ".npm/_logs"


def test_package_cache_manual_rows_require_allowlist(monkeypatch, tmp_path):
    home = tmp_path / "home"
    custom = home / "custom-npm-cache"
    for sub in ("_cacache", "_npx"):
        target = custom / sub
        target.mkdir(parents=True)
        (target / "blob.bin").write_bytes(b"x" * 2 * 1024 * 1024)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr("macmaid.scanner.which", lambda name: "/fake/bin/npm" if name == "npm" else None)
    monkeypatch.setattr("macmaid.scanner.run_command",
                        lambda exe, args, **kw: SimpleNamespace(succeeded=True, status=0, stdout=str(custom), stderr=""))

    result = PackageManagerCacheScanner(Config(home=home)).scan()

    assert {item.label for item in result.items} == {"npm cache clean"}


def test_package_cache_brew_rows_target_downloads_dir(monkeypatch, tmp_path):
    home = tmp_path / "home"
    brew_root = home / "Library/Caches/Homebrew"
    for sub in ("downloads", "api"):
        target = brew_root / sub
        target.mkdir(parents=True)
        (target / "blob.bin").write_bytes(b"x" * 2 * 1024 * 1024)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr("macmaid.scanner.which", lambda name: "/fake/bin/brew" if name == "brew" else None)
    monkeypatch.setattr("macmaid.scanner.run_command",
                        lambda exe, args, **kw: SimpleNamespace(succeeded=True, status=0, stdout=str(brew_root), stderr=""))

    result = PackageManagerCacheScanner(Config(home=home)).scan()

    rows = {item.label: item for item in result.items}
    assert rows["Homebrew cleanup"].path == brew_root / "downloads"
    manual_row = rows["Homebrew API/bootsnap caches · manual fallback"]
    assert manual_row.path == brew_root and manual_row.risk is RiskLevel.MANUAL_ONLY


def test_package_cache_skips_tiny_caches(monkeypatch, tmp_path):
    home = tmp_path / "home"
    cacache = home / ".npm" / "_cacache"
    cacache.mkdir(parents=True)
    (cacache / "tiny.bin").write_bytes(b"x" * 4096)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr("macmaid.scanner.which", lambda name: "/fake/bin/npm" if name == "npm" else None)
    monkeypatch.setattr("macmaid.scanner.run_command",
                        lambda exe, args, **kw: SimpleNamespace(succeeded=True, status=0, stdout="", stderr=""))

    result = PackageManagerCacheScanner(Config(home=home)).scan()

    assert not [item for item in result.items if "npm" in item.label]


def _command_item(path: Path) -> CleanupItem:
    return CleanupItem(CleanupCategory.PACKAGE_MANAGERS, "pkg cache", path, 1,
                       RiskLevel.SAFE, "test", CleanupAction(ActionType.COMMAND, "pkg", ["cache", "clean"]))


def test_command_cleanup_fails_when_target_size_unchanged(monkeypatch, tmp_path):
    home = tmp_path / "home"
    target = home / "Library/Caches/pkg"
    target.mkdir(parents=True)
    (target / "blob.bin").write_bytes(b"x" * 2048)
    config = Config(home=home)
    config.ensure_files()
    monkeypatch.setattr(cleaning.os, "geteuid", lambda: 501)
    monkeypatch.setattr("macmaid.cleaner.run_command",
                        lambda exe, args, **kw: SimpleNamespace(succeeded=True, status=0, stdout="", stderr=""))

    result = Cleaner(config).execute([_command_item(target)], apply=True, assume_yes=True)

    assert result.failed == 1
    assert any("remains" in detail for detail in result.details)
    assert target.exists()


def test_command_cleanup_verified_reduction_counts_reclaim(monkeypatch, tmp_path):
    home = tmp_path / "home"
    target = home / "Library/Caches/pkg"
    target.mkdir(parents=True)
    (target / "blob.bin").write_bytes(b"x" * 65536)
    config = Config(home=home)
    config.ensure_files()
    monkeypatch.setattr(cleaning.os, "geteuid", lambda: 501)

    def fake_run(exe, args, **kw):
        (target / "blob.bin").unlink()
        return SimpleNamespace(succeeded=True, status=0, stdout="", stderr="")

    monkeypatch.setattr("macmaid.cleaner.run_command", fake_run)
    result = Cleaner(config).execute([_command_item(target)], apply=True, assume_yes=True)

    assert result.failed == 0
    assert result.freed > 0 and result.unknown_reclaim_count == 0


def test_dev_cache_scan_state_invalidated_after_clean(monkeypatch, tmp_path):
    home = tmp_path / "home"
    target = home / "Library/Caches/pkg"
    target.mkdir(parents=True)
    (target / "blob.bin").write_bytes(b"x" * 2048)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    config = Config(home=home)
    config.ensure_files()
    monkeypatch.setattr(cleaning.os, "geteuid", lambda: 501)
    item = CleanupItem(CleanupCategory.PACKAGE_MANAGERS, "pkg cache", target, 2048,
                       RiskLevel.SAFE, "test", CleanupAction(ActionType.REMOVE_PATH))
    state = SimpleNamespace(config=config, dev_caches=ScanResult([item], status="complete"),
                            installers=None, leftovers=None, token="secret",
                            generations={"developer-caches": 1}, review_tokens={},
                            lock=threading.RLock())
    handler = object.__new__(web.MacMaidHandler)
    handler.server = SimpleNamespace(state=state)

    prepared = handler._route_post("/api/developer/caches/clean", {"itemIds": [item.id], "reviewOnly": True})
    result = handler._route_post("/api/developer/caches/clean",
                                 {"itemIds": [item.id], "reviewToken": prepared["reviewToken"]})

    assert result["success"] is True and not target.exists()
    assert state.dev_caches is None
    with pytest.raises(ValueError, match="latest scan"):
        handler._route_post("/api/developer/caches/clean", {"itemIds": [item.id], "reviewToken": prepared["reviewToken"]})


def test_dev_cache_clean_then_rescan_drops_verified_row(monkeypatch, tmp_path):
    home = tmp_path / "home"
    cacache = home / ".npm" / "_cacache"
    cacache.mkdir(parents=True)
    (cacache / "blob.bin").write_bytes(b"x" * 2 * 1024 * 1024)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(cleaning.os, "geteuid", lambda: 501)
    monkeypatch.setattr("macmaid.scanner.which", lambda name: "/fake/bin/npm" if name == "npm" else None)

    def npm_behavior(exe, args, **kw):
        if args[:2] == ["config", "get"]:
            return SimpleNamespace(succeeded=True, status=0, stdout=str(cacache.parent), stderr="")
        if args[:2] == ["cache", "clean"]:
            (cacache / "blob.bin").unlink()
            return SimpleNamespace(succeeded=True, status=0, stdout="", stderr="")
        return SimpleNamespace(succeeded=True, status=0, stdout="", stderr="")

    monkeypatch.setattr("macmaid.scanner.run_command", npm_behavior)
    monkeypatch.setattr("macmaid.cleaner.run_command", npm_behavior)
    config = Config(home=home)
    config.ensure_files()
    state = SimpleNamespace(config=config, dev_caches=None, installers=None, leftovers=None,
                            token="secret", generations={}, review_tokens={},
                            lock=threading.RLock(), progress=web.ProgressState())
    handler = object.__new__(web.MacMaidHandler)
    handler.server = SimpleNamespace(state=state)

    scan = handler._route_get("/api/developer/caches", {})
    npm_rows = [item for item in scan["items"] if item["label"] == "npm cache clean"]
    assert npm_rows and npm_rows[0]["bytes"] > 0

    prepared = handler._route_post("/api/developer/caches/clean",
                                   {"itemIds": [npm_rows[0]["id"]], "reviewOnly": True})
    result = handler._route_post("/api/developer/caches/clean",
                                 {"itemIds": [npm_rows[0]["id"]], "reviewToken": prepared["reviewToken"]})
    assert result["success"] is True and result["failed"] == 0

    rescan = handler._route_get("/api/developer/caches", {})
    assert not [item for item in rescan["items"] if item["label"] == "npm cache clean"]


def test_ensure_tool_search_path_merges_missing_tool_dirs(monkeypatch, tmp_path):
    home = tmp_path / "home"
    nvm_bin = home / ".nvm/versions/node/v22.1.0/bin"
    brew = Path("/opt/homebrew/bin") if Path("/opt/homebrew/bin").is_dir() else home / ".local/bin"
    nvm_bin.mkdir(parents=True)
    brew.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    ensure_tool_search_path()

    parts = os.environ["PATH"].split(os.pathsep)
    assert str(nvm_bin) in parts
    assert str(brew) in parts
    assert parts[:2] == ["/usr/bin", "/bin"]


def test_ensure_tool_search_path_is_noop_when_dirs_present(monkeypatch, tmp_path):
    home = tmp_path / "home"
    existing = home / ".local/bin"
    existing.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("PATH", f"/usr/bin:{existing}")

    ensure_tool_search_path()

    assert os.environ["PATH"].split(os.pathsep).count(str(existing)) == 1
