from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

from macmaid.cleaner import Cleaner
from macmaid.config import Config
from macmaid.features import ApplicationManager, ProjectArtifact, ProjectPurgeManager, completion_activation_hint, completion_script, install_completion, remove_completion_hooks, system_status
from macmaid.models import ActionType, CleanupAction, CleanupCategory, CleanupItem, CleanupProfile, RiskLevel
from macmaid.safety import PathSafety, PathSafetyError, manual_cache_allowed
from macmaid.scanner import Scanner
from macmaid.system import human_bytes, run_command, sizes_of


def test_config_persists_only_supported_interface_languages(tmp_path: Path) -> None:
    config = Config(home=tmp_path)
    config.ensure_files()

    assert config.preferences() == {"language": "en"}
    config.set_language("en")
    assert config.preferences() == {"language": "en"}
    with pytest.raises(ValueError, match="Unsupported"):
        config.set_language("de")
    assert config.preferences() == {"language": "en"}


def test_config_replaces_whitelist_atomically_after_validating_all_entries(tmp_path: Path) -> None:
    config = Config(home=tmp_path)
    config.ensure_files()
    keep = tmp_path / "Library/Caches/keep"
    important = tmp_path / "Developer/important-*"
    config.replace_whitelist([str(keep), str(important)])

    assert config.patterns(strict=True) == [str(keep), str(important)]

    with pytest.raises(ValueError, match="absolute paths"):
        config.replace_whitelist(["relative/path"])
    assert config.patterns(strict=True) == [str(keep), str(important)]


def test_symlinked_whitelist_still_filters_scans_but_blocks_operations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = Config(home=tmp_path)
    config.ensure_files()
    managed = tmp_path / "dotfiles"
    managed.mkdir()
    real = managed / "whitelist"
    keep = tmp_path / "Library" / "Caches" / "keepme"
    drop = tmp_path / "Library" / "Caches" / "dropme"
    for target in (keep, drop):
        target.mkdir(parents=True)
        (target / "blob.bin").write_bytes(b"x" * 128)
    real.write_text(f"{keep}\n")
    config.whitelist_file.unlink()
    config.whitelist_file.symlink_to(real)

    # Scan-time reads follow the symlink so dotfiles-manager setups keep
    # hiding entries; operation-time reads stay fail-closed.
    assert config.patterns() == [str(keep)]
    assert config.is_whitelisted(keep)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    # The whitelist snapshot lives on the Scanner and is populated inside
    # scan(); the public entry point is what must honor it.
    scanned = {item.path for item in Scanner(config).scan(CleanupProfile.SAFE).items}
    assert keep not in scanned
    assert drop in scanned
    with pytest.raises(PermissionError):
        config.patterns(strict=True)
    with pytest.raises(PermissionError):
        config.require_unprotected(keep)


def test_cli_refuses_root(monkeypatch: pytest.MonkeyPatch) -> None:
    from macmaid import cli
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    with pytest.raises(SystemExit) as stopped:
        cli.main(["doctor"])
    assert stopped.value.code == 2


def test_cleaner_reports_per_item_progress_without_changing_safety(monkeypatch: pytest.MonkeyPatch) -> None:
    item = CleanupItem(
        CleanupCategory.USER_CACHES, "fixture", None, 10, RiskLevel.SAFE,
        "test fixture", CleanupAction(ActionType.REMOVE_PATH),
    )
    cleaner = Cleaner(Config())
    executed: list[str] = []
    events: list[tuple[int, str]] = []
    monkeypatch.setattr(cleaner, "_execute_item", lambda current, **_: executed.append(current.label))
    monkeypatch.setattr(cleaner, "_log", lambda *_, **__: None)
    monkeypatch.setattr(cleaner, "_log_summary", lambda *_: None)

    result = cleaner.execute(
        [item], apply=True, assume_yes=True,
        progress=lambda index, _total, _item, outcome: events.append((index, outcome)),
    )

    assert executed == ["fixture"]
    assert events == [(1, "running"), (1, "success")]
    assert result.failed == 0


def test_cleaner_progress_failure_does_not_repeat_or_corrupt_operation(monkeypatch: pytest.MonkeyPatch) -> None:
    item = CleanupItem(
        CleanupCategory.USER_CACHES, "fixture", None, 10, RiskLevel.SAFE,
        "test fixture", CleanupAction(ActionType.REMOVE_PATH),
    )
    cleaner = Cleaner(Config())
    executed: list[str] = []
    monkeypatch.setattr(cleaner, "_execute_item", lambda current, **_: executed.append(current.label))
    monkeypatch.setattr(cleaner, "_log", lambda *_, **__: None)
    monkeypatch.setattr(cleaner, "_log_summary", lambda *_: None)

    result = cleaner.execute(
        [item], apply=True, assume_yes=True,
        progress=lambda *_: (_ for _ in ()).throw(RuntimeError("closed UI")),
    )

    assert executed == ["fixture"]
    assert result.failed == 0
    assert result.details == ["progress reporting disabled: closed UI"]


def test_profiles_preserve_risk_contract() -> None:
    assert CleanupProfile.SAFE.maximum_risk is RiskLevel.SAFE
    assert CleanupProfile.DEVELOPER.includes_developer
    assert CleanupProfile.AGGRESSIVE.maximum_risk is RiskLevel.AGGRESSIVE


@pytest.mark.parametrize("path", ["/", "/System", "/usr", "/Library", "/Applications", "/Users"])
def test_protected_roots_are_rejected(path: str) -> None:
    with pytest.raises(PathSafetyError):
        PathSafety().validate_deletion_path(path)


def test_home_cache_is_allowed() -> None:
    path = Path.home() / "Library/Caches/com.example.fixture"
    assert PathSafety().validate_deletion_path(path) == path


def test_application_support_root_is_rejected() -> None:
    with pytest.raises(PathSafetyError):
        PathSafety().validate_deletion_path(Path.home() / "Library/Application Support")


def test_browser_cache_leaf_is_allowed_but_history_is_not() -> None:
    root = Path.home() / "Library/Application Support/Google/Chrome/Default"
    assert PathSafety().validate_deletion_path(root / "GPUCache") == root / "GPUCache"
    with pytest.raises(PathSafetyError):
        PathSafety().validate_deletion_path(root / "History")


def test_sandbox_is_bounded_to_cache_directory() -> None:
    root = Path.home() / "Library/Containers/com.example.app/Data/Library"
    assert PathSafety().validate_deletion_path(root / "Caches/item") == root / "Caches/item"
    with pytest.raises(PathSafetyError):
        PathSafety().validate_deletion_path(root / "Application Support/item")


def test_temp_root_rejected_but_child_allowed() -> None:
    with pytest.raises(PathSafetyError):
        PathSafety().validate_deletion_path("/private/tmp")
    assert PathSafety().validate_deletion_path("/private/tmp/macmaid-test") == Path("/private/tmp/macmaid-test")


def test_analyzer_protects_home_anchors() -> None:
    with pytest.raises(PathSafetyError):
        PathSafety.validate_analyzer_candidate(Path.home() / "Documents")


def test_analyzer_protects_everything_below_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    target = tmp_path / "Library" / "Caches" / "candidate"
    target.mkdir(parents=True)
    with pytest.raises(PathSafetyError):
        PathSafety.validate_analyzer_candidate(target)


def test_manual_cache_fallback_is_manager_and_path_specific(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert manual_cache_allowed("npm", tmp_path / ".npm")
    assert not manual_cache_allowed("npm", tmp_path / ".config")


def test_analyzer_protects_library_descendants() -> None:
    with pytest.raises(PathSafetyError):
        PathSafety.validate_analyzer_candidate(Path.home() / "Library/Caches/example")


def test_bundle_identifier_validation() -> None:
    assert ApplicationManager.valid_bundle_id("com.example.App")
    assert not ApplicationManager.valid_bundle_id("../../Library/Caches")
    assert not ApplicationManager.valid_bundle_id("invalid")


def test_project_purge_requires_marker_and_known_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    project = tmp_path / "project"; project.mkdir(); (project / "package.json").write_text("{}")
    target = project / "node_modules"; target.mkdir(); (target / "x").write_bytes(b"x")
    artifact = ProjectArtifact("project", project, "node_modules", target, 1, target.stat().st_mtime, True, True)
    assert ProjectPurgeManager().validate(artifact)
    (project / "package.json").unlink()
    assert not ProjectPurgeManager().validate(artifact)


def test_project_scan_refuses_roots_outside_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"; home.mkdir()
    outside = tmp_path / "outside"; outside.mkdir(); (outside / "package.json").write_text("{}")
    (outside / "node_modules").mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    assert ProjectPurgeManager().scan([outside]) == []


def test_command_runner_does_not_invoke_shell() -> None:
    result = run_command("/bin/echo", ["hello; /usr/bin/false"])
    assert result.succeeded
    assert result.stdout == "hello; /usr/bin/false"


def test_bounded_parallel_sizes(tmp_path: Path) -> None:
    paths = []
    completed = []
    for index in range(5):
        path = tmp_path / str(index); path.write_bytes(b"x" * (index + 1)); paths.append(path)
    values = sizes_of(paths, max_workers=2, on_result=lambda path, size: completed.append((path, size)))
    assert set(values) == set(paths)
    assert {path for path, _size in completed} == set(paths)
    assert all(value > 0 for value in values.values())


def test_completion_contains_all_primary_commands() -> None:
    script = completion_script("zsh")
    for command in ("scan", "apps", "analyze", "purge", "status", "memory", "developer", "ui"):
        assert f"'{command}:" in script
    for option in ("--profile", "--scan-only", "--apply", "--path", "--task", "--port"):
        assert option in script
    for option in ("--growing", "--sort", "--filter"):
        assert option in script
    assert "'help:" not in script and "'version:" not in script
    assert "memory" in completion_script("bash")
    assert "memory" in completion_script("fish")


def test_zsh_completion_script_has_valid_syntax() -> None:
    checked = subprocess.run(
        ["/bin/zsh", "-n"], input=completion_script("zsh"), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    assert checked.returncode == 0, checked.stderr


def test_installed_zsh_completion_is_registered(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(os, "getuid", lambda: tmp_path.lstat().st_uid)
    destination = install_completion("zsh", Config(home=tmp_path))
    assert destination == tmp_path / ".config/macmaid/completions/zsh/_macmaid"
    assert "MacMaid completion" in (tmp_path / ".zshrc").read_text()
    checked = subprocess.run(
        ["/bin/zsh", "-fc", 'fpath=("$HOME/.config/macmaid/completions/zsh" $fpath); autoload -Uz compinit; compinit -D; print -r -- ${_comps[macmaid]-missing}'],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        env=dict(os.environ, HOME=str(tmp_path)),
    )
    assert checked.returncode == 0, checked.stderr
    assert checked.stdout.strip() == "_macmaid"


def test_completion_writes_preserve_symlinked_rc_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(os, "getuid", lambda: tmp_path.lstat().st_uid)
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    target = dotfiles / "zshrc"
    target.write_text("# managed by dotfiles\n")
    os.chmod(target, 0o640)
    rc = tmp_path / ".zshrc"
    rc.symlink_to(target)

    install_completion("zsh", Config(home=tmp_path))

    # The link survives and the write lands in the managed target file.
    assert rc.is_symlink() and rc.resolve() == target
    text = target.read_text()
    assert "# managed by dotfiles" in text and "MacMaid completion" in text
    assert stat.S_IMODE(target.stat().st_mode) == 0o640

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    remove_completion_hooks()
    assert rc.is_symlink() and rc.resolve() == target
    assert "MacMaid completion" not in target.read_text()


def test_completion_activation_hint_initializes_current_zsh() -> None:
    hint = completion_activation_hint("zsh")
    assert 'fpath=("$HOME/.config/macmaid/completions/zsh" $fpath)' in hint
    assert "autoload -Uz compinit" in hint


def test_installer_configures_completion_for_active_shell(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    fake_bin = tmp_path / "bin"
    tool_bin = tmp_path / "tool-bin"
    fake_home = tmp_path / "home"
    log = tmp_path / "macmaid-arguments"
    for directory in (fake_bin, tool_bin, fake_home):
        directory.mkdir()

    scripts = {
        fake_bin / "uname": "#!/bin/sh\nprintf '%s\\n' Darwin\n",
        fake_bin / "id": "#!/bin/sh\nprintf '%s\\n' 501\n",
        fake_bin / "uv": "#!/bin/sh\nif [ \"$*\" = \"tool dir --bin\" ]; then printf '%s\\n' \"$FAKE_TOOL_BIN\"; fi\n",
        tool_bin / "macmaid": "#!/bin/sh\nprintf '%s\\n' \"$*\" > \"$FAKE_LOG\"\n",
    }
    for path, content in scripts.items():
        path.write_text(content)
        path.chmod(0o700)

    environment = dict(
        os.environ,
        PATH=f"{fake_bin}:/usr/bin:/bin",
        HOME=str(fake_home),
        SHELL="/bin/zsh",
        FAKE_TOOL_BIN=str(tool_bin),
        FAKE_LOG=str(log),
    )
    installed = subprocess.run(
        ["/bin/sh", str(root / "install.sh")], cwd=root, env=environment,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    assert installed.returncode == 0, installed.stderr
    assert log.read_text().strip() == "completion zsh --install"
    assert "Shell completion installed automatically for zsh" in installed.stdout


def test_human_bytes() -> None:
    assert human_bytes(1024) == "1.0 KB"


def test_system_status_is_sane() -> None:
    status = system_status()
    assert 0 <= status["cpuPercent"] <= 100
    assert 0 < status["memoryUsed"] <= status["memoryTotal"]
    assert 0 < status["diskUsed"] <= status["diskTotal"]
    assert 0 <= status["diskFree"] <= status["diskTotal"]
    expected_mount = "/System/Volumes/Data" if Path("/System/Volumes/Data").is_dir() else "/"
    assert status["diskMount"] == expected_mount
    assert 0 <= status["diskPercent"] <= 100
