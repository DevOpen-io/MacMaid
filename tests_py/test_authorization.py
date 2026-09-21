from __future__ import annotations

import threading
from http.client import HTTPConnection
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, Mock

import pytest

from macmaid import cli, tui, web
from macmaid.config import Config
from macmaid.features import AppComponent, InstalledApplication, ProjectArtifact
from macmaid.models import ActionType, CleanupAction, CleanupCategory, CleanupItem, OperationResult, RiskLevel, ScanResult


def review_state(**values):
    defaults = dict(token="test-secret", generations={}, review_tokens={}, lock=threading.RLock(),
                    progress=web.ProgressState())
    defaults.update(values)
    return SimpleNamespace(**defaults)


def reviewed_request(handler, path, payload):
    prepared = handler._route_post(path, dict(payload, reviewOnly=True))
    return handler._route_post(path, dict(payload, reviewToken=prepared["reviewToken"], extraOptIn=True))


def item():
    return CleanupItem(CleanupCategory.USER_CACHES, "Fixture", None, 0, RiskLevel.SAFE,
                       "test", CleanupAction(ActionType.COMMAND))


def test_all_application_surfaces_refuse_root(monkeypatch):
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    with pytest.raises(SystemExit) as exc:
        cli.main(["status"])
    assert exc.value.code == 2
    monkeypatch.setattr(tui.os, "geteuid", lambda: 0)
    with pytest.raises(PermissionError, match="root"):
        tui.MacMaidTUI()
    monkeypatch.setattr(web.os, "geteuid", lambda: 0)
    with pytest.raises(PermissionError, match="root"):
        web.serve(0, False)


@pytest.mark.parametrize("apply, yes, interactive, answer, expected", [
    (False, False, False, "", False), (True, False, False, "", False),
    (True, False, True, "n", False), (True, False, True, "y", True),
    (True, True, False, "", True),
])
def test_cli_dry_run_and_explicit_authorization(monkeypatch, tmp_path, capsys, apply, yes, interactive, answer, expected):
    monkeypatch.setattr(cli, "Config", lambda: Config(home=tmp_path))
    execute = Mock(return_value=OperationResult())
    monkeypatch.setattr(cli, "Cleaner", lambda config: SimpleNamespace(execute=execute))
    monkeypatch.setattr(cli, "is_interactive", lambda: interactive)
    monkeypatch.setattr("builtins.input", lambda prompt: answer)
    cli._run_clean_result(ScanResult([item()]), SimpleNamespace(apply=apply, yes=yes, scan_only=False))
    assert execute.called is expected
    output = capsys.readouterr().out
    if apply:
        assert "Exact operation review" in output and "Manager/system command" in output
        assert "APFS" in output
    if expected:
        assert execute.call_args.kwargs == {"apply": True, "assume_yes": True}


@pytest.mark.parametrize("fault", ["host", "origin", "missing-origin", "missing-cookie", "wrong-cookie", "content-type", "none"])
def test_web_mutation_session_gates(monkeypatch, tmp_path, fault):
    monkeypatch.setattr(web, "Config", lambda: Config(home=tmp_path))
    state = web.WebState()
    route = Mock(return_value={"success": True})
    monkeypatch.setattr(web.MacMaidHandler, "_route_post", route)
    server = web.MacMaidHTTPServer(("127.0.0.1", 0), state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        host = f"127.0.0.1:{server.server_port}"
        headers = {"Host": host, "Origin": f"http://{host}", "Content-Type": "application/json",
                   "Cookie": f"macmaid_session={state.token}"}
        if fault == "host": headers["Host"] = "attacker.example"
        elif fault == "origin": headers["Origin"] = "https://attacker.example"
        elif fault == "missing-origin": headers.pop("Origin")
        elif fault == "missing-cookie": headers.pop("Cookie")
        elif fault == "wrong-cookie": headers["Cookie"] = "macmaid_session=wrong"
        elif fault == "content-type": headers["Content-Type"] = "text/plain"
        connection.request("POST", "/api/clean", body="{}", headers=headers)
        response = connection.getresponse()
        assert response.status == (200 if fault == "none" else 403)
        response.read()
        assert route.called is (fault == "none")
    finally:
        connection.close(); server.shutdown(); server.server_close(); thread.join()


def test_web_serializes_mutations(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "Config", lambda: Config(home=tmp_path))
    state = web.WebState()
    route = Mock(return_value={"success": True})
    monkeypatch.setattr(web.MacMaidHandler, "_route_post", route)
    server = web.MacMaidHTTPServer(("127.0.0.1", 0), state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        host = f"127.0.0.1:{server.server_port}"
        headers = {"Host": host, "Origin": f"http://{host}", "Content-Type": "application/json",
                   "Cookie": f"macmaid_session={state.token}"}
        state.mutation_lock.acquire()
        connection.request("POST", "/api/clean", body="{}", headers=headers)
        response = connection.getresponse()
        assert response.status == 409
        response.read()
        route.assert_not_called()
    finally:
        if state.mutation_lock.locked(): state.mutation_lock.release()
        connection.close(); server.shutdown(); server.server_close(); thread.join()


@pytest.mark.parametrize("path", ["/api/clean", "/api/purge", "/api/analyze/trash", "/api/duplicates/trash", "/api/large-files/trash", "/api/smart-downloads/trash", "/api/browser-storage/clean", "/api/treemap/trash", "/api/treemap/open", "/api/apps/uninstall", "/api/developer/remove"])
def test_get_routes_never_mutate(monkeypatch, tmp_path, path):
    monkeypatch.setattr(web, "Config", lambda: Config(home=tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    purge = Mock()
    monkeypatch.setattr(web.ProjectPurgeManager, "purge", purge)
    state = web.WebState()
    handler = object.__new__(web.MacMaidHandler)
    handler.server = SimpleNamespace(state=state)
    try:
        if path == "/api/purge":
            handler._route_get(path, {})  # The shared GET path is a read-only project scan.
        else:
            with pytest.raises(FileNotFoundError): handler._route_get(path, {})
        purge.assert_not_called()
    finally:
        state.analyzer.shutdown()


def test_web_cleanup_requires_exact_reviewed_nonmanual_ids(monkeypatch):
    reviewed = item()
    execute = Mock(return_value=OperationResult())
    monkeypatch.setattr(web, "Cleaner", lambda config: SimpleNamespace(execute=execute))
    state = review_state(scan=ScanResult([reviewed]), config=object())
    handler = object.__new__(web.MacMaidHandler)
    handler.server = SimpleNamespace(state=state)
    for ids in (["unknown"], [reviewed.id, "unknown"]):
        with pytest.raises(PermissionError): handler._route_post("/api/clean", {"itemIds": ids})
    execute.assert_not_called()
    prepared = handler._route_post("/api/clean", {"itemIds": [reviewed.id], "dryRun": True, "reviewOnly": True})
    assert prepared["review"]["items"][0]["target"]
    result = handler._route_post("/api/clean", {"itemIds": [reviewed.id], "dryRun": True, "reviewToken": prepared["reviewToken"]})
    assert result["dryRun"]
    assert execute.call_args.kwargs["apply"] is False
    reviewed.risk = RiskLevel.MANUAL_ONLY
    with pytest.raises(PermissionError): handler._route_post("/api/clean", {"itemIds": [reviewed.id]})


def test_web_app_and_purge_delegate_to_shared_managers(monkeypatch, tmp_path):
    app_path = tmp_path / "Example.app"
    app = InstalledApplication("Example", app_path, "org.example.app", "1", 10)
    component = AppComponent("Application", app_path, 10, "safe", True)
    project = tmp_path / "project"
    artifact = ProjectArtifact("project", project, "node_modules", project / "node_modules", 10, 0, True, True)
    config = object()
    state = review_state(apps=[app], projects=[artifact], config=config)
    handler = object.__new__(web.MacMaidHandler)
    handler.server = SimpleNamespace(state=state)
    remove, purge = Mock(return_value={"success": True}), Mock(return_value={"success": True})
    app_manager = Mock(return_value=SimpleNamespace(remove=remove, components=lambda app: [component]))
    purge_manager = Mock(return_value=SimpleNamespace(purge=purge))
    monkeypatch.setattr(web, "ApplicationManager", app_manager)
    monkeypatch.setattr(web, "ProjectPurgeManager", purge_manager)
    with pytest.raises(PermissionError): handler._route_post("/api/apps/uninstall", {"path": str(tmp_path / "Other.app")})
    with pytest.raises(PermissionError): handler._route_post("/api/purge", {"paths": [str(tmp_path / "source")]})
    remove.assert_not_called(); purge.assert_not_called()
    reviewed_request(handler, "/api/apps/uninstall", {"path": str(app_path)})
    reviewed_request(handler, "/api/purge", {"paths": [str(artifact.path)]})
    assert app_manager.call_args_list == [((config,), {}), ((config,), {})]
    purge_manager.assert_called_once_with(config)
    remove.assert_called_once_with(app, [app_path], progress=ANY)
    purge.assert_called_once_with([artifact], progress=ANY)
