from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from macmaid import cleaner as cleaner_module, web
from macmaid.cleaner import Cleaner
from macmaid.config import Config
from macmaid.models import ActionType, CleanupAction, CleanupCategory, CleanupItem, RiskLevel
from macmaid.reporting import FreeSpaceProbe, MEASUREMENT_CAVEAT


def item(path: Path, size: int, action: ActionType = ActionType.REMOVE_PATH, label: str = "item") -> CleanupItem:
    return CleanupItem(CleanupCategory.USER_CACHES, label, path, size, RiskLevel.SAFE, "test",
                       CleanupAction(action))


def configured(tmp_path: Path, monkeypatch) -> tuple[Config, Path]:
    home = tmp_path / "home"
    target = home / "Library" / "Caches"
    target.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    config = Config(home=home)
    config.ensure_files()
    return config, target


def test_successful_estimates_exclude_failed_targets_and_trash(monkeypatch, tmp_path):
    config, root = configured(tmp_path, monkeypatch)
    permanent = item(root / "permanent", 100, label="permanent")
    trashed = item(root / "trashed", 200, ActionType.MOVE_TO_TRASH, "trashed")
    failed = item(root / "failed", 400, label="failed")
    skipped = item(root / "manual", 800, ActionType.MANUAL_CACHE_FALLBACK, "manual")
    skipped.risk = RiskLevel.MANUAL_ONLY
    for candidate in (permanent, trashed, failed, skipped):
        candidate.path.write_bytes(b"x")

    def execute(candidate, **kwargs):
        if candidate is failed:
            raise RuntimeError("synthetic failure")
        candidate.path.unlink()

    monkeypatch.setattr(Cleaner, "_execute_item", lambda self, candidate, **kwargs: execute(candidate, **kwargs))
    monkeypatch.setattr(cleaner_module, "size_of", lambda path: 10 if path and path.exists() else 0)
    monkeypatch.setattr(FreeSpaceProbe, "capture", classmethod(lambda cls, paths: type("Probe", (), {"finish": lambda self: (7, [MEASUREMENT_CAVEAT])})()))

    result = Cleaner(config).execute([permanent, trashed, failed, skipped], apply=True, assume_yes=True)
    assert result.scanned_estimated_bytes == 1500
    assert result.processed_estimated_bytes == 300
    assert result.freed == 10
    assert result.trash_moved_estimated_bytes == 200
    assert result.failed == 1 and result.skipped == 1
    assert result.observed_free_bytes_delta == 7
    assert "not space proven" in result.measurement_notes[0]


def test_real_trash_move_is_never_reported_as_freed(monkeypatch, tmp_path):
    config, _ = configured(tmp_path, monkeypatch)
    source = config.home / "Downloads" / "recoverable.cache"
    source.parent.mkdir()
    source.write_bytes(b"payload")
    result = Cleaner(config).execute([item(source, 4096, ActionType.MOVE_TO_TRASH)], apply=True, assume_yes=True)
    assert result.processed_estimated_bytes == 4096
    assert result.trash_moved_estimated_bytes == 4096
    assert result.freed == 0
    assert not source.exists()
    assert (Path.home() / ".Trash" / source.name).exists()


def test_history_api_totals_only_explicit_estimated_reclaim(monkeypatch):
    records = [
        {"recordType": "operation_summary", "timestamp": "2", "processedEstimatedBytes": 900,
         "estimatedReclaimedBytes": 100, "trashMovedEstimatedBytes": 800, "result": "success"},
        {"recordType": "operation_summary", "timestamp": "1", "processedEstimatedBytes": 700,
         "estimatedReclaimedBytes": 0, "trashMovedEstimatedBytes": 0, "result": "partial"},
    ]
    monkeypatch.setattr(web, "history", lambda limit: records)
    handler = object.__new__(web.MacMaidHandler)
    handler.server = SimpleNamespace(state=SimpleNamespace())
    payload = handler._route_get("/api/history", {})
    assert payload["totalEstimatedReclaimed"] == 100
    assert payload["totalProcessedEstimated"] == 1600
    assert "Trash" in payload["measurementCaveat"]


def test_measurement_failure_is_explicit_and_audit_summary_is_structured(monkeypatch, tmp_path):
    config, root = configured(tmp_path, monkeypatch)
    target = root / "cache"
    target.write_bytes(b"x")
    monkeypatch.setattr(Cleaner, "_execute_item", lambda self, candidate, **kwargs: candidate.path.unlink())
    monkeypatch.setattr(FreeSpaceProbe, "capture", classmethod(lambda cls, paths: type("Probe", (), {"finish": lambda self: (None, ["measurement unavailable", MEASUREMENT_CAVEAT])})()))
    result = Cleaner(config).execute([item(target, 123)], apply=True, assume_yes=True)
    assert result.observed_free_bytes_delta is None
    assert "measurement unavailable" in result.measurement_notes
    summary = json.loads(config.operation_log.read_text().splitlines()[-1])
    assert summary["recordType"] == "operation_summary"
    assert summary["scannedEstimatedBytes"] == 123
    assert summary["processedEstimatedBytes"] == 123
    assert summary["observedFreeBytesDelta"] is None
