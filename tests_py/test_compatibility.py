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


def test_permission_report_reflects_current_process_access(monkeypatch, tmp_path) -> None:
    home = tmp_path
    user_caches = home / "Library/Caches"
    brave = home / "Library/Application Support/BraveSoftware/Brave-Browser"
    sandbox = home / "Library/Containers/com.example.Editor/Data/Library/Caches"
    mail = home / "Library/Mail"
    safari = home / "Library/Safari"
    for path in (user_caches, brave, sandbox, mail, safari):
        path.mkdir(parents=True)

    denied = {brave, sandbox}
    monkeypatch.setattr(system, "_directory_access", lambda path: "denied" if path in denied else "granted")
    monkeypatch.setattr(system.sys, "executable", str(tmp_path / "MacMaid.app/Contents/MacOS/macmaid-bin"))

    report = system.macos_permission_report(home)
    checks = {check["id"]: check for check in report["checks"]}
    assert report["launchContext"] == "app"
    assert report["fullDiskAccess"] == "granted"
    assert checks["userCaches"]["status"] == "granted"
    assert checks["browserProfiles"]["status"] == "denied"
    assert checks["browserProfiles"]["entries"] == [{"name": "Brave", "status": "denied"}]
    assert checks["appSandboxes"]["status"] == "denied"
    assert checks["appSandboxes"]["entries"] == [{"name": "com.example.Editor", "status": "denied"}]


def test_web_permissions_endpoint_uses_configured_home(monkeypatch, tmp_path) -> None:
    expected = {"launchContext": "app", "fullDiskAccess": "unknown", "checks": []}
    report = Mock(return_value=expected)
    monkeypatch.setattr(web, "macos_permission_report", report)
    handler = object.__new__(web.MacMaidHandler)
    handler.server = SimpleNamespace(state=SimpleNamespace(config=Config(home=tmp_path)))

    assert handler._route_get("/api/permissions", {}) == expected
    report.assert_called_once_with(tmp_path)


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


def test_settings_ui_exposes_read_only_permission_status() -> None:
    root = Path(__file__).resolve().parents[1]
    web_ui = (root / "src/macmaid/WebUI/index.html").read_text()
    javascript = (root / "src/macmaid/WebUI/app.js").read_text()
    styles = (root / "src/macmaid/WebUI/styles.css").read_text()

    assert 'id="btn-manage-permissions"' in web_ui
    assert 'id="permission-summary"' in web_ui
    assert 'id="permission-modal-list"' in javascript
    assert "The counts below are readable locations, not separate macOS permissions" in javascript
    assert "settings.permissions_show_details" in javascript
    assert "fetch('/api/permissions')" in javascript
    assert "fetch('/api/permissions/open-full-disk-access'" in javascript
    assert "max-height: calc(100vh - 32px)" in styles
    assert ".modal-body" in styles and "overflow-y: auto" in styles


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
