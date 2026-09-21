"""Navigation must never trigger scans, heavy probes, or network checks.

Two layers of protection:
- Static guards on WebUI app.js / TUI navigation handlers (mutation-proof:
  re-adding a scan call to a navigation handler fails these tests).
- Behavioral tests: real TUI page navigation via Textual's test harness and
  real HTTP GETs against a live MacMaidHTTPServer.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
from http.client import HTTPConnection
from pathlib import Path

import pytest

from macmaid import tui, web
from macmaid.config import Config
from macmaid.web import MacMaidHTTPServer, WebState

ROOT = Path(__file__).parents[1]
APP_JS = (ROOT / "src/macmaid/WebUI/app.js").read_text()


def _function_body(source: str, name: str) -> str:
    """Extract a JS function's `{...}` body by brace matching.

    The parameter list is skipped with paren matching first so default
    parameters like `${tab}` templates cannot fake the body brace.
    """
    match = re.search(rf"function {re.escape(name)}\s*\(", source)
    assert match, f"{name} not found"
    depth = 0
    index = match.end() - 1  # at the opening paren
    while index < len(source):
        char = source[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                break
        index += 1
    start = source.index("{", index)
    depth = 0
    for index in range(start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"{name} body never closed")


def _listener_body(source: str, selector: str) -> str:
    """Extract the click-listener block registered for a CSS selector."""
    match = re.search(rf"querySelectorAll\('{re.escape(selector)}'\)\.forEach\(pill => {{", source)
    assert match, f"{selector} listener not found"
    start = match.end() - 1
    depth = 0
    for index in range(start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"{selector} listener never closed")


# ---------------------------------------------------------------------------
# WebUI static guards
# ---------------------------------------------------------------------------

def test_more_subtab_navigation_never_starts_heavy_scans() -> None:
    body = _function_body(APP_JS, "activateMoreSubtab")
    for forbidden in ("fetchBrowserStorage(", "fetchSmartDownloads(", "fetchDuplicates(",
                      "fetchLargeFiles(", "fetchTreemap(", "runDiskAnalyzer("):
        assert forbidden not in body, f"navigation triggers {forbidden}"
    assert "reconnectTreemap(" in body


def test_developer_subtab_navigation_never_scans_storage() -> None:
    body = _function_body(APP_JS, "activateDeveloperSubtab")
    for forbidden in ("scanDeveloperStorage(", "scanDeveloperCaches(", "scanDeveloperRuntimes(",
                      "scanDeveloperEnvironments(", "scanDeveloperTools(", "scanDeveloperSDKs("):
        assert forbidden not in body, f"navigation triggers {forbidden}"


def test_treemap_reconnect_never_starts_a_new_analysis() -> None:
    body = _function_body(APP_JS, "reconnectTreemap")
    assert "fetchTreemap(" in body
    # The reconnect call must pass polling=true so the backend sees start=false.
    reconnect_call = re.search(r"fetchTreemap\(([^)]*)\)", body)
    assert reconnect_call and "true" in reconnect_call.group(1), reconnect_call
    # fetchTreemap must derive the `start` query flag from the polling flag.
    fetch_body = _function_body(APP_JS, "fetchTreemap")
    assert re.search(r"start:\s*polling\s*\?\s*'false'\s*:\s*'true'", fetch_body), fetch_body


def test_age_pills_filter_cached_results_without_rescanning() -> None:
    installers = _listener_body(APP_JS, ".installer-age-pill")
    leftovers = _listener_body(APP_JS, ".leftover-age-pill")
    assert "scanInstallers(" not in installers and "renderInstallers(" in installers
    assert "scanLeftovers(" not in leftovers and "renderLeftovers(" in leftovers
    # Discovery itself must run at the lowest threshold so the cached result is
    # a superset the pills can filter.
    assert "olderThan=0" in _function_body(APP_JS, "scanInstallers")
    assert "olderThan=0" in _function_body(APP_JS, "scanLeftovers")


def test_status_polling_is_page_scoped_to_dashboard() -> None:
    assert APP_JS.count("setInterval(fetchStatus") == 1
    poll_body = _function_body(APP_JS, "syncStatusPolling")
    assert "setInterval(fetchStatus" in poll_body and "clearInterval" in poll_body
    nav_body = _function_body(APP_JS, "activateTopLevelTab")
    assert "syncStatusPolling()" in nav_body and "fetchStatus(" not in nav_body


def test_settings_open_uses_cached_permission_report() -> None:
    assert "if (!state.permissionReport) fetchPermissionReport();" in APP_JS


def test_domcontentloaded_does_not_start_global_polling() -> None:
    init = APP_JS[APP_JS.rindex("document.addEventListener('DOMContentLoaded'"):]
    assert "setInterval(fetchStatus" not in init
    assert "pollLiveProgress()" in init  # one-shot probe for in-flight operations stays


# ---------------------------------------------------------------------------
# TUI: navigation opens menus; scans require explicit actions
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_tui(monkeypatch, tmp_path):
    monkeypatch.setattr(tui, "Config", lambda: Config(home=tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(tui, "system_status", lambda **kw: {
        "cpuPercent": 1.0, "memoryPercent": 1.0, "diskPercent": 1.0,
        "memoryUsed": 1, "memoryTotal": 2, "diskUsed": 1, "diskTotal": 2,
        "networkDownPerSecond": 0, "networkUpPerSecond": 0, "diskIOPerSecond": 0,
        "thermal": "Normal", "battery": None, "processes": [], "healthIndicators": [],
    })


def test_tui_navigation_opens_menu_pages_without_workers(monkeypatch) -> None:
    async def exercise() -> None:
        app = tui.MacMaidTUI()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            calls: list[str] = []
            monkeypatch.setattr(app, "_scan_apps", lambda: calls.append("apps"))
            monkeypatch.setattr(app, "_scan_projects", lambda: calls.append("purge"))
            monkeypatch.setattr(app, "_load_status", lambda: calls.append("status"))
            monkeypatch.setattr(app, "_load_memory", lambda: calls.append("memory"))
            monkeypatch.setattr(app, "_check_macmaid_update", lambda: calls.append("update"))
            monkeypatch.setattr(app, "_request_analysis", lambda *a, **kw: calls.append("analyzer"))

            for key in ("apps", "analyzer", "purge", "status"):
                app.open_page(key)
                await pilot.pause()
                assert app.current_page == key, key  # menu page, not results
            app.open_page("memory")
            await pilot.pause()
            assert app.current_page == "memory"
            app.open_page("update")
            await pilot.pause()
            assert app.current_page == "update-results"
            assert calls == [], calls

            # Explicit menu action still starts the scan.
            app._run_menu_action("apps-scan")
            assert calls == ["apps"]
    asyncio.run(exercise())


def test_tui_update_page_entry_never_runs_brew(monkeypatch) -> None:
    def explode(**kwargs):
        raise AssertionError("brew subprocess started from navigation")

    monkeypatch.setattr(tui, "macmaid_brew_update_status", explode)

    async def exercise() -> None:
        app = tui.MacMaidTUI()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.open_page("update")
            await pilot.pause()
            assert app.current_page == "update-results"
    asyncio.run(exercise())


# ---------------------------------------------------------------------------
# Web backend: passive GETs must not spawn work
# ---------------------------------------------------------------------------

@pytest.fixture
def web_server(tmp_path):
    state = WebState(Config(home=tmp_path))
    server = MacMaidHTTPServer(("127.0.0.1", 0), state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = f"127.0.0.1:{server.server_port}"
    try:
        yield server, state, host
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _get(host: str, target: str):
    connection = HTTPConnection("127.0.0.1", int(host.rsplit(":", 1)[1]))
    connection.request("GET", target, headers={"Host": host})
    response = connection.getresponse()
    payload = json.loads(response.read() or b"{}")
    connection.close()
    return response.status, payload


def test_update_get_is_passive_and_never_invokes_brew(web_server, monkeypatch) -> None:
    server, state, host = web_server

    def explode(**kwargs):
        raise AssertionError("brew subprocess started by a passive GET")

    monkeypatch.setattr(web, "macmaid_brew_update_status", explode)
    status, payload = _get(host, "/api/macmaid/update")
    assert status == 200
    assert payload["installed"] is False

    # An explicit check's result is served from cache afterwards.
    state.macmaid_update = {"available": True, "installed": True, "latestVersion": "9.9.9"}
    status, payload = _get(host, "/api/macmaid/update")
    assert status == 200 and payload["latestVersion"] == "9.9.9"


def test_treemap_get_without_start_never_creates_a_job(web_server, tmp_path) -> None:
    from urllib.parse import quote

    server, state, host = web_server
    status, payload = _get(host, f"/api/treemap?path={quote(str(tmp_path))}")
    assert status == 200
    assert payload["isComplete"] is True and payload["status"] == "idle"
    assert state.analyzer.progress()["active"] is False


def test_installers_response_carries_age_for_client_side_filtering(web_server, monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    old = downloads / "old.dmg"
    old.write_bytes(b"o")
    old_mtime = time.time() - 40 * 86400
    os.utime(old, (old_mtime, old_mtime))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    server, state, host = web_server
    status, payload = _get(host, "/api/installers?olderThan=0")
    assert status == 200
    ages = {item["path"]: item.get("ageDays") for item in payload["installers"]}
    assert ages[str(old)] >= 40
