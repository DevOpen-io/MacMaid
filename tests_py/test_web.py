from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import quote

from deepclean.config import Config
from deepclean.web import DeepCleanHTTPServer, WebState


def test_web_rejects_foreign_host_and_protects_mutations(tmp_path: Path) -> None:
    server = DeepCleanHTTPServer(("127.0.0.1", 0), WebState(Config(home=tmp_path)))
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
    server = DeepCleanHTTPServer(("127.0.0.1", 0), WebState(Config(home=tmp_path)))
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
