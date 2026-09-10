from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from deepclean.cleaner import Cleaner
from deepclean.config import Config
from deepclean.features import ApplicationManager, ProjectArtifact, ProjectPurgeManager, completion_script, system_status
from deepclean.models import ActionType, CleanupAction, CleanupCategory, CleanupItem, CleanupProfile, RiskLevel
from deepclean.safety import PathSafety, PathSafetyError, manual_cache_allowed
from deepclean.system import human_bytes, run_command, sizes_of


def test_cli_refuses_root(monkeypatch: pytest.MonkeyPatch) -> None:
    from deepclean import cli
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
    assert PathSafety().validate_deletion_path("/private/tmp/deepclean-test") == Path("/private/tmp/deepclean-test")


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
    for index in range(5):
        path = tmp_path / str(index); path.write_bytes(b"x" * (index + 1)); paths.append(path)
    values = sizes_of(paths, max_workers=2)
    assert set(values) == set(paths)
    assert all(value > 0 for value in values.values())


def test_completion_contains_all_primary_commands() -> None:
    script = completion_script("zsh")
    for command in ("scan", "apps", "analyze", "purge", "status", "ui"):
        assert command in script


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
