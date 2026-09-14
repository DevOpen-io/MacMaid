from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from macmaid import cleaner as module
from macmaid.cleaner import Cleaner
from macmaid.config import Config
from macmaid.safety import PathSafety, PathSafetyError
from macmaid.web import MacMaidHandler


@pytest.fixture
def cleaner(monkeypatch, tmp_path) -> Cleaner:
    home = tmp_path.resolve() / "home"
    (home / "Downloads").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(module.os, "geteuid", lambda: 501)
    config = Config(home=home)
    config.ensure_files()
    return Cleaner(config)


def target(cleaner: Cleaner) -> Path:
    path = cleaner.config.home / "Downloads" / "örnek file.txt"
    path.write_text("keep this data")
    return path


@pytest.mark.parametrize("analyzer", [False, True])
def test_trash_preserves_data_and_avoids_name_collision(cleaner, analyzer):
    path = target(cleaner)
    trash = cleaner.config.home / ".Trash"
    trash.mkdir()
    (trash / path.name).write_text("existing data")
    move = cleaner.move_analyzer_item_to_trash if analyzer else cleaner._move_to_trash
    destination = move(path)
    assert not path.exists()
    assert destination.read_text() == "keep this data"
    assert (trash / path.name).read_text() == "existing data"
    if analyzer:
        record = json.loads(cleaner.config.operation_log.read_text().splitlines()[-1])
        assert record["result"] == "success"
        assert record["path"] == str(path)
        assert record["processedEstimatedBytes"] > 0
        assert record["estimatedReclaimedBytes"] == 0
        assert record["reclaimStatus"] == "moved_to_trash_not_reclaimed"
        assert record["operation_id"]
        assert record["original_path"] == str(path)
        assert record["trash_path"] == str(destination)
        assert record["size"] > 0
        assert record["restorable"] is True


def test_execute_records_recovery_metadata_for_trash_moves(cleaner):
    path = target(cleaner)
    size = path.stat().st_size
    item = module.CleanupItem(
        module.CleanupCategory.TRASH, "fixture", path, size, module.RiskLevel.AGGRESSIVE,
        "reviewed fixture", module.CleanupAction(module.ActionType.MOVE_TO_TRASH),
    )

    result = cleaner.execute([item], apply=True, assume_yes=True)

    records = [json.loads(line) for line in cleaner.config.operation_log.read_text().splitlines()]
    item_record, summary = records[-2], records[-1]
    assert result.failed == result.skipped == 0
    assert item_record["operation_id"] == summary["operation_id"]
    assert item_record["original_path"] == str(path)
    assert item_record["trash_path"]
    assert item_record["size"] == size
    assert item_record["restorable"] is True
    assert summary["original_path"] is None
    assert summary["trash_path"] is None
    assert summary["restorable"] is False


@pytest.mark.parametrize("analyzer", [False, True])
def test_whitelist_added_after_discovery_blocks_trash(cleaner, analyzer):
    path = target(cleaner)
    cleaner.config.whitelist_file.write_text(str(path))
    move = cleaner.move_analyzer_item_to_trash if analyzer else cleaner._move_to_trash
    with pytest.raises(PermissionError, match="whitelisted"):
        move(path)
    assert path.read_text() == "keep this data"
    assert not (cleaner.config.home / ".Trash").exists()


def test_whitelist_rechecked_after_destination_preparation(cleaner, monkeypatch):
    path = target(cleaner)
    original = module.unique_trash_destination

    def prepare(source):
        cleaner.config.whitelist_file.write_text(str(source))
        return original(source)

    monkeypatch.setattr(module, "unique_trash_destination", prepare)
    with pytest.raises(PermissionError, match="whitelisted"):
        cleaner._move_to_trash(path)
    assert path.exists()


@pytest.mark.parametrize("link_kind", ["target", "ancestor", "trash"])
def test_symlinks_cannot_redirect_trash(cleaner, link_kind):
    path = target(cleaner)
    outside = cleaner.config.home.parent / "outside"
    outside.mkdir()
    if link_kind == "target":
        original = outside / "original"
        path.rename(original)
        path.symlink_to(original)
    elif link_kind == "ancestor":
        downloads = path.parent
        downloads.rename(outside / "downloads")
        downloads.symlink_to(outside / "downloads", target_is_directory=True)
    else:
        (cleaner.config.home / ".Trash").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PathSafetyError):
        cleaner._move_to_trash(path)
    assert path.read_text() == "keep this data"


def test_changed_ancestor_rejected_immediately_before_move(cleaner, monkeypatch):
    path = target(cleaner)
    original = module.unique_trash_destination

    def prepare(source):
        destination = original(source)
        source.parent.rename(cleaner.config.home / "old-downloads")
        source.parent.symlink_to(cleaner.config.home / "old-downloads", target_is_directory=True)
        return destination

    monkeypatch.setattr(module, "unique_trash_destination", prepare)
    with pytest.raises(PathSafetyError, match="ancestor"):
        cleaner._move_to_trash(path)
    assert path.read_text() == "keep this data"


@pytest.mark.parametrize("failure", ["no-op", "permission"])
def test_analyzer_never_reports_unverified_move_as_success(cleaner, monkeypatch, failure):
    path = target(cleaner)

    def move(*args):
        if failure == "permission":
            raise PermissionError("denied")

    monkeypatch.setattr(module, "move_to_trash_exclusive", move)
    with pytest.raises((PermissionError, RuntimeError)):
        cleaner.move_analyzer_item_to_trash(path)
    assert path.exists()
    record = json.loads(cleaner.config.operation_log.read_text().splitlines()[-1])
    assert record["result"] == "failed"


@pytest.mark.parametrize("analyzer", [False, True])
def test_direct_trash_operations_refuse_root(cleaner, monkeypatch, analyzer):
    path = target(cleaner)
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    move = cleaner.move_analyzer_item_to_trash if analyzer else cleaner._move_to_trash
    with pytest.raises(PermissionError, match="root"):
        move(path)
    assert path.exists()


@pytest.mark.parametrize("analyzer", [False, True])
def test_trash_rejects_owner_mismatch(cleaner, monkeypatch, analyzer):
    path = target(cleaner)
    monkeypatch.setattr(module.os, "getuid", lambda: path.lstat().st_uid + 1)
    move = (lambda current: cleaner._move_validated_to_trash(current, PathSafety.validate_analyzer_candidate)) if analyzer else cleaner._move_to_trash
    with pytest.raises(PathSafetyError, match="owned"):
        move(path)
    assert path.exists()


def test_destination_created_during_preparation_is_not_overwritten(cleaner, monkeypatch):
    path = target(cleaner)
    original = module.unique_trash_destination

    def prepare(source):
        destination = original(source)
        destination.write_text("another operation's data")
        return destination

    monkeypatch.setattr(module, "unique_trash_destination", prepare)
    with pytest.raises(FileExistsError):
        cleaner._move_to_trash(path)
    assert path.exists()
    assert (cleaner.config.home / ".Trash" / path.name).read_text() == "another operation's data"


@pytest.mark.parametrize("name", ["Library", "Documents", "Downloads"])
def test_analyzer_protected_anchors_are_not_moved(cleaner, name):
    path = cleaner.config.home / name
    path.mkdir(exist_ok=True)
    with pytest.raises(PathSafetyError, match="protected"):
        cleaner.move_analyzer_item_to_trash(path)
    assert path.is_dir()


def test_web_analyzer_uses_shared_whitelist_gate(cleaner):
    path = target(cleaner)
    cleaner.config.whitelist_file.write_text(str(path))
    state = SimpleNamespace(config=cleaner.config, analyzed_paths={path}, analyzer=Mock(), token="secret",
                            generations={"analyzer": 1}, review_tokens={}, lock=__import__("threading").RLock())
    handler = object.__new__(MacMaidHandler)
    handler.server = SimpleNamespace(state=state)
    prepared = handler._route_post("/api/analyze/trash", {"path": str(path), "reviewOnly": True})
    with pytest.raises(PermissionError, match="whitelisted"):
        handler._route_post("/api/analyze/trash", {"path": str(path), "reviewToken": prepared["reviewToken"], "extraOptIn": True})
    assert path.exists()
    state.analyzer.invalidate_after_removal.assert_not_called()
