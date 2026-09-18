from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from macmaid import web
from macmaid.config import Config
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
    npm_cache = home / ".npm"
    npm_cache.mkdir(parents=True)
    (npm_cache / "_cacache").mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr("macmaid.scanner.which", lambda name: "/fake/bin/npm" if name == "npm" else None)
    monkeypatch.setattr("macmaid.scanner.run_command",
                        lambda exe, args, **kw: SimpleNamespace(succeeded=True, status=0, stdout="", stderr=""))
    monkeypatch.setattr("macmaid.scanner.size_of", _denied_size)

    result = PackageManagerCacheScanner(Config(home=home)).scan()

    npm_items = [item for item in result.items if "npm" in item.label]
    assert result.status == "complete" and result.is_complete
    assert npm_items and npm_items[0].path == npm_cache
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
    resolved = home / "custom-npm-cache"
    resolved.mkdir(parents=True)
    (resolved / "blob.bin").write_bytes(b"x" * 2048)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr("macmaid.scanner.which", lambda name: "/fake/bin/npm" if name == "npm" else None)

    def fake_run(exe, args, **kw):
        if args[:2] == ["config", "get"]:
            return SimpleNamespace(succeeded=True, status=0, stdout=str(resolved), stderr="")
        return SimpleNamespace(succeeded=True, status=0, stdout="", stderr="")

    monkeypatch.setattr("macmaid.scanner.run_command", fake_run)
    result = PackageManagerCacheScanner(Config(home=home)).scan()

    npm_items = [item for item in result.items if "npm" in item.label]
    assert npm_items and npm_items[0].path == resolved
    assert npm_items[0].estimated_bytes > 0


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
