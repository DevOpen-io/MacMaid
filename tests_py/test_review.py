from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from macmaid import web
from macmaid.config import Config
from macmaid.features import AppComponent, InstalledApplication
from macmaid.models import ActionType, CleanupAction, CleanupCategory, CleanupItem, OperationResult, RiskLevel, ScanResult
from macmaid.review import application_plan, cleanup_plan, issue_review_token, validate_review_token


def cleanup_item(label="Cache", risk=RiskLevel.SAFE):
    return CleanupItem(CleanupCategory.USER_CACHES, label, Path("/Users/test/Library/Caches/example"), 1024,
                       risk, "Reconstructable cache", CleanupAction(ActionType.REMOVE_PATH),
                       requires_app_closed="Example")


def state(**values):
    defaults = dict(token="secret", generations={"clean": 1}, review_tokens={}, lock=threading.RLock(),
                    config=Config(home=Path("/tmp/macmaid-review-test")), progress=web.ProgressState())
    defaults.update(values)
    return SimpleNamespace(**defaults)


def handler(current):
    result = object.__new__(web.MacMaidHandler)
    result.server = SimpleNamespace(state=current)
    return result


def test_review_plan_exposes_exact_target_action_risk_impact_and_estimate():
    item = cleanup_item()
    plan = cleanup_plan("Review cleanup", [item])
    payload = plan.web_dict()
    assert payload["estimatedBytes"] == 1024
    assert "APFS" in payload["estimateNote"]
    assert payload["items"] == [{
        "key": item.id, "label": "Cache", "target": str(item.path), "action": "Permanent delete",
        "risk": "SAFE", "reason": "Reconstructable cache", "estimated_bytes": 1024,
        "requires_app_closed": "Example", "user_data": False,
        "estimatedBytes": 1024, "humanEstimated": "1.0 KB",
    }]
    text = plan.text()
    assert str(item.path) in text and "close Example" in text and "revalidated" not in text
    assert "checks run again" in text


def test_application_user_data_is_high_risk_and_requires_extra_opt_in():
    app = InstalledApplication("Example", Path("/Users/test/Applications/Example.app"), "org.example.app", "1")
    components = [
        AppComponent("Application", app.path, 10, "safe", True),
        AppComponent("Application Support", Path("/Users/test/Library/Application Support/org.example.app"), 20, "userData", False),
    ]
    plan = application_plan(app, components)
    assert plan.requires_extra_opt_in
    assert plan.items[0].risk == "AGGRESSIVE"
    assert plan.items[1].user_data and plan.items[1].risk == "AGGRESSIVE"


def test_review_fingerprint_changes_with_selection_or_effect():
    first = cleanup_plan("Review", [cleanup_item("A")])
    second = cleanup_plan("Review", [cleanup_item("B")])
    assert first.fingerprint != second.fingerprint


@pytest.mark.parametrize("change", ["none", "expired", "future", "generation", "selection", "scope", "malformed"])
def test_signed_review_token_is_short_lived_and_exact(change):
    plan = cleanup_plan("Review", [cleanup_item()])
    token = issue_review_token("secret", "clean", 2, plan, now=1000)
    args = dict(secret="secret", scope="clean", generation=2, plan=plan, token=token, now=1001)
    if change == "expired": args["now"] = 1400
    elif change == "future": args["now"] = 900
    elif change == "generation": args["generation"] = 3
    elif change == "selection": args["plan"] = cleanup_plan("Review", [cleanup_item("other")])
    elif change == "scope": args["scope"] = "purge"
    elif change == "malformed": args["token"] = "invalid"
    assert validate_review_token(**args) is (change not in {"expired", "future", "generation", "selection", "scope", "malformed"})


def test_web_never_executes_without_fresh_review_and_token_is_single_use(monkeypatch):
    item = cleanup_item()
    current = state(scan=ScanResult([item]))
    execute = Mock(return_value=OperationResult())
    monkeypatch.setattr(web, "Cleaner", lambda config: SimpleNamespace(execute=execute))
    route = handler(current)
    payload = {"itemIds": [item.id]}
    with pytest.raises(PermissionError, match="fresh review"):
        route._route_post("/api/clean", payload)
    execute.assert_not_called()
    prepared = route._route_post("/api/clean", dict(payload, reviewOnly=True))
    result = route._route_post("/api/clean", dict(payload, reviewToken=prepared["reviewToken"]))
    assert result["success"] and execute.call_count == 1
    with pytest.raises(PermissionError, match="fresh review"):
        route._route_post("/api/clean", dict(payload, reviewToken=prepared["reviewToken"]))
    assert execute.call_count == 1


def test_new_scan_invalidates_existing_web_review(monkeypatch):
    item = cleanup_item()
    current = state(scan=ScanResult([item]))
    execute = Mock()
    monkeypatch.setattr(web, "Cleaner", lambda config: SimpleNamespace(execute=execute))
    route = handler(current)
    payload = {"itemIds": [item.id]}
    prepared = route._route_post("/api/clean", dict(payload, reviewOnly=True))
    route._bump_generation("clean")
    with pytest.raises(PermissionError, match="fresh review"):
        route._route_post("/api/clean", dict(payload, reviewToken=prepared["reviewToken"]))
    execute.assert_not_called()


def test_analyzer_user_file_requires_separate_opt_in(monkeypatch, tmp_path):
    path = tmp_path / "document.txt"
    path.write_text("data")
    current = state(analyzed_paths={path}, generations={"analyzer": 1}, analyzer=Mock())
    move = Mock(return_value=tmp_path / ".Trash/document.txt")
    log_summary = Mock()
    monkeypatch.setattr(web, "Cleaner", lambda config: SimpleNamespace(
        move_analyzer_item_to_trash=move, log_space_summary=log_summary,
    ))
    route = handler(current)
    payload = {"path": str(path)}
    prepared = route._route_post("/api/analyze/trash", dict(payload, reviewOnly=True))
    assert prepared["review"]["requiresExtraOptIn"] is True
    with pytest.raises(PermissionError, match="opt-in"):
        route._route_post("/api/analyze/trash", dict(payload, reviewToken=prepared["reviewToken"]))
    move.assert_not_called()
    prepared = route._route_post("/api/analyze/trash", dict(payload, reviewOnly=True))
    route._route_post("/api/analyze/trash", dict(payload, reviewToken=prepared["reviewToken"], extraOptIn=True))
    move.assert_called_once()
    assert move.call_args.args[0] == path and move.call_args.args[1] >= 0
