from __future__ import annotations

import json
from pathlib import Path

import pytest

from macmaid import cleaner as cleaning
from macmaid.config import Config
from macmaid.features import RecoveryCenter
from macmaid.models import ActionType, CleanupAction, CleanupCategory, CleanupItem, RiskLevel
from macmaid.safety import PathSafetyError


@pytest.fixture
def config(monkeypatch, tmp_path):
    home = tmp_path.resolve() / "home"
    (home / "Downloads").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(cleaning.os, "geteuid", lambda: 501)
    result = Config(home=home)
    result.ensure_files()
    return result


def _trash_record(config: Config) -> tuple[dict, Path]:
    source = config.home / "Downloads" / "recover.txt"
    source.write_text("important")
    item = CleanupItem(CleanupCategory.TRASH, "recover", source, source.stat().st_size,
                       RiskLevel.AGGRESSIVE, "reviewed", CleanupAction(ActionType.MOVE_TO_TRASH))
    Cleaner = cleaning.Cleaner
    Cleaner(config).execute([item], apply=True, assume_yes=True)
    record = json.loads(config.operation_log.read_text().splitlines()[-2])
    return record, source


def test_restore_moves_trash_item_back_to_original_path(config):
    record, original = _trash_record(config)

    result = RecoveryCenter(config).restore(record["operation_id"], record["trash_path"])

    assert result["success"] is True
    assert original.read_text() == "important"
    assert not Path(record["trash_path"]).exists()
    recovery = json.loads(config.operation_log.read_text().splitlines()[-1])
    assert recovery["recordType"] == "recovery"
    assert recovery["action"] == "restore"


def test_restore_detects_conflict_and_restore_as_copy_preserves_trash(config):
    record, original = _trash_record(config)
    original.write_text("new file")

    with pytest.raises(FileExistsError):
        RecoveryCenter(config).restore(record["operation_id"], record["trash_path"])

    result = RecoveryCenter(config).restore(record["operation_id"], record["trash_path"], copy=True)
    restored_copy = Path(result["restored_path"])
    assert original.read_text() == "new file"
    assert restored_copy.read_text() == "important"
    assert Path(record["trash_path"]).exists()


def test_package_manager_history_is_marked_not_restorable(config):
    item = CleanupItem(CleanupCategory.PACKAGE_MANAGERS, "manager", None, 0, RiskLevel.MODERATE,
                       "official cleanup", CleanupAction(ActionType.COMMAND, "/bin/true", []))
    cleaning.Cleaner(config)._log(item, "success", None)

    [entry] = RecoveryCenter(config).entries()

    assert entry["restorable"] is False
    assert entry["restoreStatus"] == "Not Restorable"


def test_restore_rejects_trash_symlink(config):
    record, _original = _trash_record(config)
    trash = Path(record["trash_path"])
    payload = trash.with_name("payload")
    trash.rename(payload)
    trash.symlink_to(payload)

    with pytest.raises(PathSafetyError):
        RecoveryCenter(config).restore(record["operation_id"], record["trash_path"])
