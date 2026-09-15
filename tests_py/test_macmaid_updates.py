from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import Mock

from macmaid import web


def handler(state):
    route = object.__new__(web.MacMaidHandler)
    route.server = SimpleNamespace(state=state)
    return route


def state():
    return SimpleNamespace(token="secret", generations={}, review_tokens={}, lock=threading.RLock())


def test_update_check_refreshes_homebrew_and_update_requires_review(monkeypatch):
    current = state()
    route = handler(current)
    status = {"installed": True, "available": True, "installedVersion": "0.9.27", "latestVersion": "0.9.28"}
    check = Mock(return_value=status)
    apply = Mock(return_value=dict(status, updated=True))
    monkeypatch.setattr(web, "macmaid_brew_update_status", check)
    monkeypatch.setattr(web, "apply_macmaid_brew_update", apply)

    assert route._route_post("/api/macmaid/update/check", {}) == status
    assert check.call_args.kwargs == {"refresh": True}

    prepared = route._route_post("/api/macmaid/update", {"reviewOnly": True})
    result = route._route_post("/api/macmaid/update", {"reviewToken": prepared["reviewToken"]})
    assert result["success"] is True and result["updated"] is True
    apply.assert_called_once_with()
