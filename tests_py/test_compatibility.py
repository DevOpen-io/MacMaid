from __future__ import annotations

import tomllib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from macmaid import __version__, developer, features, system, web
from macmaid.config import Config
from macmaid.developer import DeveloperInventory


def test_compatibility_reports_both_supported_mac_architectures(monkeypatch) -> None:
    monkeypatch.setattr(features.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(features.platform, "mac_ver", lambda: ("13.0", ("", "", ""), ""))
    monkeypatch.setattr(features.platform, "python_version", lambda: "3.11.0")
    monkeypatch.setattr(features.sys, "version_info", (3, 11, 0))
    for architecture, family in (("arm64", "Apple Silicon"), ("x86_64", "Intel")):
        monkeypatch.setattr(features.platform, "machine", lambda current=architecture: current)
        checks = {item["name"]: item for item in features.compatibility_checks()}
        assert checks["macOS"]["ok"] is True
        assert checks["Architecture"] == {"name": "Architecture", "value": f"{architecture} ({family})", "ok": True}
        assert checks["Python"]["ok"] is True


def test_unknown_or_unsupported_host_is_not_reported_compatible(monkeypatch) -> None:
    monkeypatch.setattr(features.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(features.platform, "mac_ver", lambda: ("12.7", ("", "", ""), ""))
    monkeypatch.setattr(features.platform, "machine", lambda: "mystery-cpu")
    monkeypatch.setattr(features.sys, "version_info", (3, 10, 0))
    checks = features.compatibility_checks()
    assert all(item["ok"] is False for item in checks)


def test_missing_path_and_managers_produce_empty_inventory(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PATH", "")
    for name in (
        "MISE_DATA_DIR", "ASDF_DATA_DIR", "PYENV_ROOT", "RBENV_ROOT", "NODENV_ROOT",
        "NVM_DIR", "FNM_DIR", "SDKMAN_DIR", "VOLTA_HOME", "CONDA_PREFIX",
        "ANDROID_SDK_ROOT", "ANDROID_HOME", "ANDROID_AVD_HOME", "CARGO_HOME",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(developer, "which", lambda _name: None)
    inventory = DeveloperInventory(Config(home=tmp_path))
    assert inventory.scan("runtime") == []
    assert inventory.scan("environment") == []
    assert inventory.scan("tool") == []
    assert inventory.scan("sdk") == []


def test_permission_denied_inventory_directory_is_skipped() -> None:
    denied = Mock()
    denied.iterdir.side_effect = PermissionError("denied")
    assert developer._children(denied) == []


def test_web_doctor_does_not_present_unknown_or_failed_checks_as_ok(monkeypatch) -> None:
    monkeypatch.setattr(web, "doctor", lambda: [
        {"name": "macOS", "value": "26.2", "ok": True},
        {"name": "Architecture", "value": "unknown", "ok": False},
        {"name": "System Integrity Protection", "value": "Unknown", "ok": None},
    ])
    handler = object.__new__(web.MacMaidHandler)
    handler.server = SimpleNamespace(state=object())
    report = handler._route_get("/api/doctor", {})
    assert [probe["ok"] for probe in report["probes"]] == [True, False, False]


def test_unicode_and_spaces_remain_one_subprocess_argument(monkeypatch) -> None:
    process = Mock(returncode=0)
    process.communicate.return_value = ("ok", "")
    popen = Mock(return_value=process)
    monkeypatch.setattr(system.subprocess, "Popen", popen)
    value = "/tmp/Proje klasörü/ölçüm.txt"
    result = system.run_command("/usr/bin/example", ["--path", value])
    assert result.succeeded
    assert popen.call_args.args[0] == ["/usr/bin/example", "--path", value]
    assert popen.call_args.kwargs["shell"] is False


def test_release_version_is_consistent_across_metadata_and_web_ui() -> None:
    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text())
    lock = tomllib.loads((root / "uv.lock").read_text())
    web_ui = (root / "src/macmaid/WebUI/index.html").read_text()
    locked_project = next(package for package in lock["package"] if package["name"] == "macmaid")

    assert metadata["project"]["version"] == __version__
    assert locked_project["version"] == __version__
    assert f"v{__version__} Python" in web_ui
    assert f">{__version__} (Python 3.11+)<" in web_ui
