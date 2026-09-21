from __future__ import annotations

import json
import plistlib
import shutil
from pathlib import Path
from unittest.mock import Mock

import pytest

from macmaid import cleaner as cleaning, developer, features
from macmaid.cleaner import Cleaner
from macmaid.config import Config
from macmaid.developer import DeveloperInventory, DeveloperItem
from macmaid.features import ApplicationManager, InstalledApplication, ProjectArtifact, ProjectPurgeManager
from macmaid.models import ActionType, CleanupAction, CleanupCategory, CleanupItem, RiskLevel
from macmaid.safety import PathSafetyError
from macmaid.system import CommandResult


@pytest.fixture
def config(monkeypatch, tmp_path):
    home = tmp_path.resolve() / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(cleaning.os, "geteuid", lambda: 501)
    monkeypatch.setattr(cleaning, "size_of", lambda path: 10 if path.exists() else 0)
    monkeypatch.setattr(features, "size_of", lambda path: 10)
    monkeypatch.setattr(features, "sizes_of", lambda paths, **_kwargs: {})
    monkeypatch.setattr(developer, "sizes_of", lambda paths, **_kwargs: {})
    monkeypatch.setattr(features, "process_running", lambda value: False)
    monkeypatch.setattr(cleaning, "process_running", lambda value: False)
    monkeypatch.setattr(features, "which", lambda name: None)
    monkeypatch.setattr(developer, "which", lambda name: None)
    for module in (cleaning, features):
        monkeypatch.setattr(module, "run_command", Mock(side_effect=AssertionError("Unexpected real command")))
    monkeypatch.setattr(developer, "_run_command", Mock(side_effect=AssertionError("Unexpected real command")))
    result = Config(home=home)
    result.ensure_files()
    return result


def cache_item(config, kind=ActionType.REMOVE_PATH):
    path = config.home / "Library/Caches/test-cache"
    path.mkdir(parents=True)
    (path / "payload").write_text("data")
    return CleanupItem(CleanupCategory.USER_CACHES, "Test cache", path, 10,
                       RiskLevel.SAFE, "test", CleanupAction(kind))


@pytest.mark.parametrize("kind", [ActionType.REMOVE_PATH, ActionType.REMOVE_CHILDREN])
def test_cleaner_allowed_deletion_and_audit(config, kind):
    item = cache_item(config, kind)
    result = Cleaner(config).execute([item], apply=True, assume_yes=True)
    assert result.failed == result.skipped == 0
    assert not (item.path / "payload").exists()
    assert json.loads(config.operation_log.read_text().splitlines()[-1])["result"] == "success"


@pytest.mark.parametrize("kind", [ActionType.REMOVE_PATH, ActionType.REMOVE_CHILDREN, ActionType.MANUAL_CACHE_FALLBACK])
@pytest.mark.parametrize("pattern", ["exact", "glob"])
def test_recursive_cleanup_preserves_whitelisted_descendant(config, kind, pattern):
    item = cache_item(config, kind)
    if kind is ActionType.MANUAL_CACHE_FALLBACK:
        path = config.home / ".npm"
        item.path.rename(path)
        item.path = path
        item.risk = RiskLevel.MANUAL_ONLY
        item.action.fallback_manager = "npm"
    entry = str(item.path / "payload") if pattern == "exact" else str(item.path / "pay*")
    config.whitelist_file.write_text(entry)
    result = Cleaner(config).execute([item], apply=True, assume_yes=True, allow_manual_fallback=True)
    assert result.skipped == 1 and result.freed == 0
    assert (item.path / "payload").read_text() == "data"


@pytest.mark.parametrize("mode", ["missing", "directory", "symlink", "encoding", "relative"])
def test_unreadable_or_invalid_whitelist_blocks_mutation(config, mode):
    item = cache_item(config)
    if mode in {"missing", "directory"}:
        config.whitelist_file.unlink()
        if mode == "directory": config.whitelist_file.mkdir()
    elif mode == "symlink":
        outside = config.home / "empty-file"
        outside.write_text("")
        config.whitelist_file.unlink()
        config.whitelist_file.symlink_to(outside)
    elif mode == "encoding": config.whitelist_file.write_bytes(b"\xff")
    else: config.whitelist_file.write_text("relative/protected")
    result = Cleaner(config).execute([item], apply=True, assume_yes=True)
    assert result.skipped == 1 and result.freed == 0
    assert (item.path / "payload").exists()
    if mode == "missing": assert not config.whitelist_file.exists()


def test_unsafe_audit_log_blocks_before_mutation(config):
    item = cache_item(config)
    outside = config.home / "outside-log"
    outside.write_text("do not append")
    config.operation_log.symlink_to(outside)
    with pytest.raises(PermissionError, match="state file"):
        Cleaner(config).execute([item], apply=True, assume_yes=True)
    assert (item.path / "payload").exists()
    assert outside.read_text() == "do not append"


def test_symlinked_state_directory_is_rejected(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (home / ".config").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    with pytest.raises(PermissionError, match="state directory"):
        Config(home=home).ensure_files()


@pytest.mark.parametrize("kind", [ActionType.REMOVE_CHILDREN, ActionType.MANUAL_CACHE_FALLBACK])
def test_recursive_cleanup_rejects_owner_mismatch(config, monkeypatch, kind):
    item = cache_item(config, kind)
    if kind is ActionType.MANUAL_CACHE_FALLBACK:
        root = config.home / ".npm"
        item.path.rename(root); item.path = root
        item.risk = RiskLevel.MANUAL_ONLY; item.action.fallback_manager = "npm"
    monkeypatch.setattr(cleaning.os, "getuid", lambda: item.path.lstat().st_uid + 1)
    with pytest.raises(PathSafetyError, match="user-owned"):
        if kind is ActionType.REMOVE_CHILDREN:
            Cleaner(config)._remove_children(item.path)
        else:
            Cleaner(config)._remove_manual_children(item.path)
    assert (item.path / "payload").exists()


def test_cleaner_read_only_and_manual_gates(config, monkeypatch):
    item = cache_item(config)
    cleaner = Cleaner(config)
    execute = Mock()
    monkeypatch.setattr(cleaner, "_execute_item", execute)
    assert cleaner.execute([item], apply=False).skipped == 1
    item.risk = RiskLevel.MANUAL_ONLY
    assert cleaner.execute([item], apply=True, assume_yes=True).skipped == 1
    execute.assert_not_called()


@pytest.mark.parametrize("running", [True, None])
def test_running_or_unknown_application_blocks_cleanup(config, monkeypatch, running):
    item = cache_item(config)
    item.requires_app_closed = "Example"
    def check(value):
        if running is None: raise PermissionError("process query failed")
        return running
    monkeypatch.setattr(cleaning, "process_running", check)
    result = Cleaner(config).execute([item], apply=True, assume_yes=True)
    assert result.skipped == 1
    assert item.path.exists()


@pytest.mark.parametrize("status", [1, 124, 127])
def test_command_failure_never_triggers_recursive_fallback(config, monkeypatch, status):
    item = cache_item(config, ActionType.COMMAND_WITH_CACHE_FALLBACK)
    item.action.executable = "fake-manager"
    command = Mock(return_value=CommandResult(status, stderr="command failed"))
    monkeypatch.setattr(cleaning, "run_command", command)
    result = Cleaner(config).execute([item], apply=True, assume_yes=True)
    assert result.failed == 1 and item.path.exists()
    assert command.call_args.kwargs["timeout"] == 600


def project(config):
    root = config.home / "Projects/example"
    root.mkdir(parents=True)
    (root / "package.json").write_text("{}")
    path = root / "node_modules"
    path.mkdir()
    (path / "payload").write_text("dependency")
    artifact = ProjectArtifact(root.name, root, path.name, path, 10, 0, True, True)
    return artifact


def test_purge_uses_shared_trash_and_keeps_source(config):
    artifact = project(config)
    result = ProjectPurgeManager(config).purge([artifact])
    assert result["success"] and result["freed"] == 0
    assert result["processedEstimatedBytes"] == artifact.bytes
    assert result["trashMovedEstimatedBytes"] == artifact.bytes
    assert result["estimatedReclaimedBytes"] == 0
    assert not artifact.path.exists()
    assert (artifact.project_path / "package.json").exists()
    assert (Path(result["moved"][0]) / "payload").read_text() == "dependency"
    assert json.loads(config.operation_log.read_text().splitlines()[-1])["result"] == "success"


@pytest.mark.parametrize("change", ["marker", "whitelist", "symlink", "protected"])
def test_purge_revalidates_at_execution(config, change):
    artifact = project(config)
    if change == "marker": (artifact.project_path / "package.json").unlink()
    elif change == "whitelist": config.whitelist_file.write_text(str(artifact.path / "payload"))
    elif change == "symlink":
        artifact.path.rename(artifact.project_path / "original")
        artifact.path.symlink_to(artifact.project_path / "original", target_is_directory=True)
    else:
        artifact.path = config.home / "Documents"
        artifact.path.mkdir()
    result = ProjectPurgeManager(config).purge([artifact])
    assert not result["success"] and result["failed"] == [str(artifact.path)]
    assert artifact.path.exists()


def test_purge_partial_failure_is_reported(config):
    artifact = project(config)
    bad = ProjectArtifact("bad", artifact.project_path, "source", artifact.project_path / "package.json", 10, 0, False, True)
    result = ProjectPurgeManager(config).purge([artifact, bad])
    assert len(result["moved"]) == 1 and result["failed"] == [str(bad.path)]
    assert not result["success"]


def application(config, monkeypatch, cask=None):
    path = config.home / "Applications/Example.app"
    (path / "Contents").mkdir(parents=True)
    (path / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "org.example.app"}))
    app = InstalledApplication("Example", path, "org.example.app", "1", 10, cask)
    manager = ApplicationManager(config)
    scan = lambda: [app] if path.exists() else []
    monkeypatch.setattr(manager, "scan", scan)
    monkeypatch.setattr(manager, "_refresh_identity",
                        lambda a: next((i for i in scan() if i.path == a.path), None))
    monkeypatch.setattr(manager, "_bundles_with_id",
                        lambda bundle_id: [str(i.path) for i in scan() if i.bundle_id == bundle_id])
    return manager, app


def test_application_bundle_and_leftovers_use_shared_trash(config, monkeypatch):
    manager, app = application(config, monkeypatch)
    cache = config.home / "Library/Caches/org.example.app"
    cache.mkdir(parents=True)
    cache.joinpath("payload").write_text("cache")
    data = config.home / "Library/Application Support/org.example.app"
    data.mkdir(parents=True)
    components = manager.components(app)
    assert not next(c for c in components if c.path == data).selected
    result = manager.remove(app, [app.path, cache])
    assert result["success"] and not cache.exists() and not app.path.exists()
    assert data.exists()
    records = [json.loads(line) for line in config.operation_log.read_text().splitlines()]
    assert len(records) == 3
    assert records[-1]["recordType"] == "operation_summary"
    assert records[-1]["trashMovedEstimatedBytes"] > 0
    assert records[-1]["estimatedReclaimedBytes"] == 0


@pytest.mark.parametrize("change", ["running", "identity", "whitelist", "symlink"])
def test_application_removal_revalidates_review(config, monkeypatch, change):
    manager, app = application(config, monkeypatch)
    if change == "running": monkeypatch.setattr(features, "process_running", lambda value: True)
    elif change == "identity":
        (app.path / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "org.other.app"}))
    elif change == "whitelist": config.whitelist_file.write_text(str(app.path / "Contents/Info.plist"))
    else:
        original = app.path.with_name("Original.app")
        app.path.rename(original)
        app.path.symlink_to(original, target_is_directory=True)
    with pytest.raises((PermissionError, PathSafetyError)):
        manager.remove(app, [app.path])
    assert app.path.exists()


@pytest.mark.parametrize("status", [1, 124, 127])
def test_cask_failure_never_falls_back_to_filesystem_removal(config, monkeypatch, status):
    manager, app = application(config, monkeypatch, "example")
    monkeypatch.setattr(features, "which", lambda name: "fake-brew")
    monkeypatch.setattr(manager, "_homebrew_ownership", lambda: {"example.app": "example"})
    command = Mock(return_value=CommandResult(status, stderr="brew failed"))
    monkeypatch.setattr(features, "run_command", command)
    with pytest.raises(RuntimeError): manager.remove(app, [app.path])
    assert app.path.exists()
    assert not (config.home / ".Trash").exists()


def _brew_payload(*casks):
    return json.dumps({"casks": [{"token": token, "artifacts": artifacts} for token, artifacts in casks]})


def system_application(config, monkeypatch, cask="example"):
    """App bundle whose parent reports /Applications so the Homebrew gate runs."""
    real = config.home / "Applications" / "Example.app"
    (real / "Contents").mkdir(parents=True)
    (real / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "org.example.app"}))

    class AppPath(type(Path())):
        @property
        def parent(self):
            return Path("/Applications") if str(self) == str(real) else super().parent

    app = InstalledApplication("Example", AppPath(real), "org.example.app", "1", 10, cask)
    monkeypatch.setattr(features, "which", lambda name: "fake-brew" if name == "brew" else None)
    monkeypatch.setattr(features, "iter_app_bundles", lambda *args, **kwargs: iter(()))
    return ApplicationManager(config), app, real


def test_homebrew_ownership_maps_cask_tokens_with_single_query(config, monkeypatch):
    manager = ApplicationManager(config)
    calls = []

    def brew(executable, arguments, **kwargs):
        calls.append((executable, list(arguments)))
        return CommandResult(0, _brew_payload(("firefox", [{"app": ["Firefox.app"]}])))

    monkeypatch.setattr(features, "which", lambda name: "fake-brew" if name == "brew" else None)
    monkeypatch.setattr(features, "run_command", brew)
    assert manager._homebrew_ownership() == {"firefox.app": "firefox"}
    assert calls == [("fake-brew", ["info", "--json=v2", "--installed"])]


def test_homebrew_ownership_failures_are_fail_closed(config, monkeypatch):
    manager = ApplicationManager(config)
    monkeypatch.setattr(features, "which", lambda name: "fake-brew")
    monkeypatch.setattr(features, "run_command", lambda exe, args, **kw: CommandResult(1, stderr="boom"))
    with pytest.raises(PermissionError, match="could not be determined"):
        manager._homebrew_ownership()
    monkeypatch.setattr(features, "run_command", lambda exe, args, **kw: CommandResult(0, "not-json"))
    with pytest.raises(PermissionError, match="Invalid Homebrew"):
        manager._homebrew_ownership()
    ambiguous = _brew_payload(("one", [{"app": ["Shared.app"]}]), ("two", [{"app": ["Shared.app"]}]))
    monkeypatch.setattr(features, "run_command", lambda exe, args, **kw: CommandResult(0, ambiguous))
    with pytest.raises(PermissionError, match="Ambiguous"):
        manager._homebrew_ownership()
    monkeypatch.setattr(features, "which", lambda name: None)
    assert manager._homebrew_ownership() == {}


def test_brew_cask_removal_requeries_real_ownership(config, monkeypatch):
    manager, app, real = system_application(config, monkeypatch)
    commands = []

    def brew(executable, arguments, **kwargs):
        commands.append(list(arguments))
        if arguments[:2] == ["info", "--json=v2"]:
            return CommandResult(0, _brew_payload(("example", [{"app": ["Example.app"]}])))
        if arguments[:2] == ["uninstall", "--cask"]:
            shutil.rmtree(real)
            return CommandResult(0)
        raise AssertionError(f"unexpected brew call: {arguments}")

    monkeypatch.setattr(features, "run_command", brew)
    result = manager.remove(app, [app.path])
    assert result["success"] and not real.exists()
    assert ["uninstall", "--cask", "example"] in commands


def test_brew_ownership_change_blocks_cask_removal(config, monkeypatch):
    manager, app, real = system_application(config, monkeypatch)
    monkeypatch.setattr(features, "run_command", lambda exe, args, **kw:
                        CommandResult(0, _brew_payload(("impostor", [{"app": ["Example.app"]}]))))
    with pytest.raises(PermissionError, match="identity changed"):
        manager.remove(app, [app.path])
    assert real.exists()


def test_brew_ownership_drop_blocks_cask_removal(config, monkeypatch):
    # Cask uninstalled between review and apply: ownership lookup is empty.
    manager, app, real = system_application(config, monkeypatch)
    monkeypatch.setattr(features, "run_command", lambda exe, args, **kw: CommandResult(0, _brew_payload()))
    with pytest.raises(PermissionError, match="identity changed"):
        manager.remove(app, [app.path])
    assert real.exists()


def dev_item(config, **kwargs):
    path = config.home / "runtime/v1"
    path.mkdir(parents=True)
    return DeveloperItem("runtime:v1", "runtime", "Runtime", "1", "test", path,
                         executable="fake-manager", arguments=("uninstall", "v1"), **kwargs)


@pytest.mark.parametrize("protection", ["active", "base", "missing", "root"])
def test_developer_rejects_protected_resources(config, monkeypatch, protection):
    item = dev_item(config)
    inventory = DeveloperInventory(config)
    monkeypatch.setattr(inventory, "scan", lambda kind: [item])
    command = Mock()
    monkeypatch.setattr(developer, "run_command", command)
    if protection == "active": item.is_active = True
    elif protection == "base": item.protected_reason = "base environment"
    elif protection == "missing": item.executable = None
    else: monkeypatch.setattr(developer.os, "geteuid", lambda: 0)
    with pytest.raises(PermissionError): inventory.remove(item.id, "runtime")
    command.assert_not_called()


@pytest.mark.parametrize("outcome", ["success", "still-present", "timeout", "missing"])
def test_developer_manager_result_and_postcondition(config, monkeypatch, outcome):
    item = dev_item(config)
    inventory = DeveloperInventory(config)
    scans = Mock(side_effect=[[item], [] if outcome == "success" else [item]])
    monkeypatch.setattr(inventory, "scan", scans)
    status = {"timeout": 124, "missing": 127}.get(outcome, 0)
    command = Mock(return_value=CommandResult(status, stderr="manager failure" if status else ""))
    monkeypatch.setattr(developer, "_run_command", command)
    if outcome == "success":
        result = inventory.remove(item.id, "runtime")
        assert result["success"] and result["estimatedReclaimedBytes"] == 0
        assert result["processedEstimatedBytes"] == item.bytes
        assert result["unknownReclaimCount"] == 1
    else:
        with pytest.raises(RuntimeError): inventory.remove(item.id, "runtime")
    assert command.call_args.kwargs["timeout"] == 900
    assert item.path.exists()  # the fake manager never deletes real data


def test_developer_command_change_after_review_is_rejected(config, monkeypatch):
    reviewed = dev_item(config)
    changed = DeveloperItem(reviewed.id, reviewed.category, reviewed.title, reviewed.version, reviewed.manager,
                            reviewed.path, executable=reviewed.executable, arguments=("uninstall", "different"))
    inventory = DeveloperInventory(config)
    monkeypatch.setattr(inventory, "scan", lambda category: [changed])
    command = Mock()
    monkeypatch.setattr(developer, "_run_command", command)
    with pytest.raises(PermissionError, match="changed after review"):
        inventory.remove(reviewed.id, "runtime", reviewed=reviewed)
    command.assert_not_called()


def test_conda_base_identity_comes_from_manager_info(config, monkeypatch):
    base = config.home / "miniforge3"
    other = base / "envs/work"
    monkeypatch.setattr(developer, "which", lambda name: "fake-conda" if name == "conda" else None)
    def command(executable, args, **kwargs):
        data = {"envs": [str(base), str(other)]} if args[:2] == ["env", "list"] else {"root_prefix": str(base), "active_prefix": str(other)}
        return CommandResult(0, json.dumps(data))
    monkeypatch.setattr(developer, "_run_command", command)
    items = DeveloperInventory(config).environments()
    assert len(items) == 2 and all(not item.removable for item in items)


def test_poetry_environment_inventory_does_not_require_project_cwd(config, monkeypatch):
    monkeypatch.delenv("POETRY_VIRTUALENVS_PATH", raising=False)
    monkeypatch.delenv("POETRY_CACHE_DIR", raising=False)
    environment = config.home / "Library/Caches/pypoetry/virtualenvs/example-py3.11"
    environment.mkdir(parents=True)

    items = DeveloperInventory(config).environments()

    assert len(items) == 1
    assert items[0].manager == "Poetry"
    assert items[0].path == environment
    assert not items[0].removable


def test_pipx_list_accepts_current_list_shaped_venv_args(config, monkeypatch):
    monkeypatch.delenv("PIPX_HOME", raising=False)
    payload = {
        "venvs": {
            "poetry": {
                "metadata": {
                    "main_package": {"package_version": "2.3.2"},
                    "venv_args": [],
                }
            }
        }
    }
    monkeypatch.setattr(developer, "which", lambda name: "fake-pipx" if name == "pipx" else None)
    monkeypatch.setattr(developer, "_run_command", lambda *args, **kwargs: CommandResult(0, json.dumps(payload)))

    items = DeveloperInventory(config).tools()

    assert len(items) == 1
    assert items[0].title == "poetry"
    assert items[0].version == "2.3.2"
    assert items[0].path == config.home / ".local/share/pipx/venvs/poetry"


def test_failed_active_query_is_not_treated_as_inactive(config, monkeypatch):
    monkeypatch.setattr(developer, "which", lambda name: "fake-manager" if name == "mise" else None)
    monkeypatch.setattr(developer, "_run_command", lambda *a, **kw: CommandResult(124, stderr="timeout"))
    with pytest.raises(RuntimeError): DeveloperInventory(config).runtimes()


@pytest.mark.parametrize("kind", ["cache-command", "developer"])
def test_manager_commands_do_not_bypass_whitelist(config, monkeypatch, kind):
    config.whitelist_file.write_text(str(config.home / "important"))
    command = Mock()
    if kind == "cache-command":
        item = cache_item(config, ActionType.COMMAND)
        item.action.executable = "fake-manager"
        monkeypatch.setattr(cleaning, "run_command", command)
        assert Cleaner(config).execute([item], apply=True, assume_yes=True).skipped == 1
    else:
        item = dev_item(config)
        inventory = DeveloperInventory(config)
        monkeypatch.setattr(inventory, "scan", lambda category: [item])
        monkeypatch.setattr(developer, "_run_command", command)
        with pytest.raises(PermissionError): inventory.remove(item.id, "runtime")
    command.assert_not_called()


def test_manual_cache_positive_path_is_bounded_and_verified(config):
    root = config.home / ".npm"
    root.mkdir(); (root / "payload").write_text("cache")
    item = CleanupItem(CleanupCategory.PACKAGE_MANAGERS, "Manual", root, 10,
                       RiskLevel.MANUAL_ONLY, "test", CleanupAction(ActionType.MANUAL_CACHE_FALLBACK, fallback_manager="npm"))
    result = Cleaner(config).execute([item], apply=True, assume_yes=True, allow_manual_fallback=True)
    assert result.failed == result.skipped == 0 and root.is_dir() and not list(root.iterdir())


def test_homebrew_cask_success_uses_manager_without_raw_fallback(config, monkeypatch):
    manager, app = application(config, monkeypatch, "example")
    monkeypatch.setattr(features, "which", lambda name: "fake-brew")
    monkeypatch.setattr(manager, "_homebrew_ownership", lambda: {"example.app": "example"})
    def uninstall(executable, args, **kwargs):
        assert args == ["uninstall", "--cask", "example"]
        assert kwargs["timeout"] == 600
        app.path.rename(config.home / "manager-removed.app")
        return CommandResult(0)
    monkeypatch.setattr(features, "run_command", uninstall)
    assert manager.remove(app, [app.path])["success"]


def test_homebrew_dependents_are_protected(config, monkeypatch):
    monkeypatch.setattr(developer, "which", lambda name: "fake-brew" if name == "brew" else None)
    def query(executable, args, **kwargs):
        if args[0] == "list": return CommandResult(0, "node 20.1")
        if args[0] == "--prefix": return CommandResult(0, str(config.home / "brew/node"))
        return CommandResult(0, "dependent-package")
    monkeypatch.setattr(developer, "_run_command", query)
    items = DeveloperInventory(config)._homebrew_runtimes()
    assert len(items) == 1 and not items[0].removable


def test_unknown_conda_root_is_not_guessed(config, monkeypatch):
    monkeypatch.setattr(developer, "which", lambda name: "fake-conda" if name == "conda" else None)
    monkeypatch.setattr(developer, "_run_command", lambda *a, **kw: CommandResult(0, '{"envs": []}'))
    with pytest.raises(PermissionError): DeveloperInventory(config).environments()


def test_booted_simulator_and_available_runtime_remain_protected(config, monkeypatch):
    monkeypatch.setattr(developer, "which", lambda name: "fake-xcrun" if name == "xcrun" else None)
    def query(executable, args, **kwargs):
        if args[2] == "runtimes":
            data = {"runtimes": [{"identifier": "runtime", "buildversion": "build", "isAvailable": True}]}
        else:
            data = {"devices": {"runtime": [{"udid": "booted", "state": "Booted", "isAvailable": False},
                                               {"udid": "old", "state": "Shutdown", "isAvailable": False}]}}
        return CommandResult(0, json.dumps(data))
    monkeypatch.setattr(developer, "_run_command", query)
    items = DeveloperInventory(config)._xcode_simulators()
    assert [item.removable for item in items] == [False, False, True]


def test_shell_managers_never_execute_directory_names(config, monkeypatch):
    nvm = config.home / ".nvm/versions/node/v1;touch injected"
    nvm.mkdir(parents=True)
    sdk = config.home / ".sdkman/candidates/java/1;touch injected"
    sdk.mkdir(parents=True)
    items = DeveloperInventory(config).runtimes()
    assert len(items) == 2 and all(not item.removable for item in items)
