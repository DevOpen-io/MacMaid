from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import Mock

from macmaid import features, web, web_mutations
from macmaid.system import CommandResult


def handler(state):
    route = object.__new__(web.MacMaidHandler)
    route.server = SimpleNamespace(state=state)
    return route


def state():
    return SimpleNamespace(token="secret", generations={}, review_tokens={}, lock=threading.RLock())


def test_homebrew_outdated_exit_one_with_json_means_update_available(monkeypatch):
    monkeypatch.setattr(features, "which", lambda name: "brew")
    responses = iter([
        CommandResult(0),
        CommandResult(1, '{"formulae": [], "casks": [{"name": "macmaid", "installed_versions": ["0.9.29"], "current_version": "0.9.30"}]}'),
    ])
    monkeypatch.setattr(features, "run_command", lambda *args, **kwargs: next(responses))

    assert features.macmaid_brew_update_status() == {
        "available": True, "installed": True, "installedVersion": "0.9.29",
        "latestVersion": "0.9.30", "reason": None,
    }


def test_update_check_refreshes_homebrew_and_update_requires_review(monkeypatch):
    current = state()
    route = handler(current)
    status = {"installed": True, "available": True, "installedVersion": "0.9.27", "latestVersion": "0.9.28"}
    check = Mock(return_value=status)
    apply = Mock(return_value=dict(status, updated=True))
    monkeypatch.setattr(web_mutations, "macmaid_brew_update_status", check)
    monkeypatch.setattr(web_mutations, "apply_macmaid_brew_update", apply)

    assert route._route_post("/api/macmaid/update/check", {}) == status
    assert check.call_args.kwargs == {"refresh": True}

    prepared = route._route_post("/api/macmaid/update", {"reviewOnly": True})
    result = route._route_post("/api/macmaid/update", {"reviewToken": prepared["reviewToken"]})
    assert result["success"] is True and result["updated"] is True
    apply.assert_called_once_with()
