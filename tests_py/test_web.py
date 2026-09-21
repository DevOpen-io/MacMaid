from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import quote

from macmaid.config import Config
from macmaid.web import MacMaidHTTPServer, WebState


def test_web_rejects_foreign_host_and_protects_mutations(tmp_path: Path) -> None:
    server = MacMaidHTTPServer(("127.0.0.1", 0), WebState(Config(home=tmp_path)))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port)
        connection.request("GET", "/api/progress", headers={"Host": "attacker.example"})
        response = connection.getresponse()
        assert response.status == 403
        response.read()

        connection.request("POST", "/api/whitelist", body='{"lines": []}', headers={"Host": f"127.0.0.1:{server.server_port}", "Content-Type": "application/json"})
        response = connection.getresponse()
        assert response.status == 403
        response.read()
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_web_analyzer_returns_navigation_snapshot_and_reuses_cache(tmp_path: Path) -> None:
    root = tmp_path / "root"
    child = root / "child"
    child.mkdir(parents=True)
    (child / "payload.bin").write_bytes(b"x" * 1024)
    server = MacMaidHTTPServer(("127.0.0.1", 0), WebState(Config(home=tmp_path)))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port)
        host = f"127.0.0.1:{server.server_port}"
        target = f"/api/analyze?path={quote(str(root))}&start=true&minSize=1"
        connection.request("GET", target, headers={"Host": host})
        response = connection.getresponse()
        first = json.loads(response.read())
        assert response.status == 200
        assert [entry["name"] for entry in first["entries"]] == ["child"]
        assert {"state", "isDirectory", "humanBytes"}.issubset(first["entries"][0])

        connection.request("GET", f"/api/analyze?path={quote(str(root))}&minSize=1", headers={"Host": host})
        response = connection.getresponse()
        cached = json.loads(response.read())
        assert response.status == 200
        assert cached["cached"] is True
        assert cached["path"] == str(root)
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_app_icon_cache_hits_and_invalidates_on_source_change(tmp_path: Path, monkeypatch) -> None:
    import plistlib
    from unittest.mock import Mock

    from macmaid.features import InstalledApplication
    from macmaid.system import CommandResult
    from macmaid import web

    app_path = tmp_path / "Example.app"
    resources = app_path / "Contents/Resources"
    resources.mkdir(parents=True)
    (app_path / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIconFile": "icon"}))
    icon = resources / "icon.icns"
    icon.write_bytes(b"icns-v1")

    state = WebState(Config(home=tmp_path))
    state.apps = [InstalledApplication("Example", app_path, "org.example.app", "1", 10)]
    server = MacMaidHTTPServer(("127.0.0.1", 0), state)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()

    calls = []

    def fake_sips(executable, arguments, **kwargs):
        calls.append(arguments)
        output = Path(arguments[-1])
        output.write_bytes(b"png-" + str(calls.__len__()).encode())
        return CommandResult(0)

    monkeypatch.setattr(web, "run_command", fake_sips)
    host = f"127.0.0.1:{server.server_port}"
    target = f"/api/apps/icon?path={quote(str(app_path))}"
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port)

        connection.request("GET", target, headers={"Host": host})
        response = connection.getresponse()
        assert response.status == 200 and response.read() == b"png-1"
        assert len(calls) == 1

        connection.request("GET", target, headers={"Host": host})
        response = connection.getresponse()
        assert response.status == 200 and response.read() == b"png-1"
        assert len(calls) == 1  # cache hit: no second conversion

        icon.write_bytes(b"icns-v2-changed-size")
        connection.request("GET", target, headers={"Host": host})
        response = connection.getresponse()
        assert response.status == 200 and response.read() == b"png-2"
        assert len(calls) == 2  # size change invalidated the entry

        connection.request("GET", f"/api/apps/icon?path={quote(str(tmp_path / 'Other.app'))}", headers={"Host": host})
        response = connection.getresponse()
        assert response.status == 404  # unapproved app path is not served
        response.read()
        assert len(calls) == 2
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_app_icon_failed_conversion_is_not_cached(tmp_path: Path, monkeypatch) -> None:
    import plistlib
    from unittest.mock import Mock

    from macmaid.features import InstalledApplication
    from macmaid.system import CommandResult
    from macmaid import web

    app_path = tmp_path / "Broken.app"
    resources = app_path / "Contents/Resources"
    resources.mkdir(parents=True)
    (app_path / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIconFile": "icon"}))
    (resources / "icon.icns").write_bytes(b"icns")

    state = WebState(Config(home=tmp_path))
    state.apps = [InstalledApplication("Broken", app_path, "org.example.broken", "1", 10)]
    server = MacMaidHTTPServer(("127.0.0.1", 0), state)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()

    sips = Mock(return_value=CommandResult(1, stderr="sips failed"))
    monkeypatch.setattr(web, "run_command", sips)
    host = f"127.0.0.1:{server.server_port}"
    target = f"/api/apps/icon?path={quote(str(app_path))}"
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port)
        for _ in range(2):
            connection.request("GET", target, headers={"Host": host})
            response = connection.getresponse()
            assert response.status == 404
            response.read()
        assert sips.call_count == 2  # failures must not populate the cache
        assert not state.icon_cache
    finally:
        server.shutdown(); server.server_close(); thread.join()
