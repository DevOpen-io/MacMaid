from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from pathlib import Path

from macmaid import cleaner, web
from macmaid.config import Config


def test_web_clean_scan_review_and_execute_use_the_same_safe_cleaner(monkeypatch, tmp_path):
    """Exercise the browser-facing HTTP flow rather than calling _route_post directly."""
    home = (tmp_path / "home").resolve()
    target = home / "Library" / "Caches" / "com.example.fixture"
    target.mkdir(parents=True)
    (target / "payload").write_bytes(b"reconstructable cache")

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(web, "Config", lambda: Config(home=home))
    monkeypatch.setattr(cleaner.os, "geteuid", lambda: 501)

    state = web.WebState()
    server = web.MacMaidHTTPServer(("127.0.0.1", 0), state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    host = f"127.0.0.1:{server.server_port}"
    headers = {"Host": host}
    try:
        connection.request("GET", "/", headers=headers)
        response = connection.getresponse()
        cookie = response.getheader("Set-Cookie")
        response.read()
        assert cookie

        connection.request("GET", "/api/scan?profile=safe", headers=headers)
        scan_response = connection.getresponse()
        scan = json.loads(scan_response.read())
        assert scan_response.status == 200
        assert scan["isComplete"] is True
        item_ids = [item["id"] for item in scan["items"]]
        assert len(item_ids) == 1

        mutation_headers = {
            **headers,
            "Origin": f"http://{host}",
            "Content-Type": "application/json",
            "Cookie": cookie.split(";", 1)[0],
        }
        connection.request("POST", "/api/clean", json.dumps({"itemIds": item_ids, "reviewOnly": True}), mutation_headers)
        review_response = connection.getresponse()
        review = json.loads(review_response.read())
        assert review_response.status == 200

        connection.request("POST", "/api/clean", json.dumps({"itemIds": item_ids, "reviewToken": review["reviewToken"]}), mutation_headers)
        clean_response = connection.getresponse()
        cleaned = json.loads(clean_response.read())
        assert clean_response.status == 200
        assert cleaned["success"] is True
        assert cleaned["failed"] == cleaned["skipped"] == 0
        assert not target.exists()
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join()
