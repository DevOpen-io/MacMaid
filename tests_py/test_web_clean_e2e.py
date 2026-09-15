from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from pathlib import Path

from macmaid import cleaner, web
from macmaid.config import Config


def test_static_assets_revalidate_without_retransferring_unchanged_content(monkeypatch, tmp_path):
    home = (tmp_path / "home").resolve()
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(web, "Config", lambda: Config(home=home))

    server = web.MacMaidHTTPServer(("127.0.0.1", 0), web.WebState())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    headers = {"Host": f"127.0.0.1:{server.server_port}"}
    try:
        connection.request("GET", "/app.js", headers=headers)
        first = connection.getresponse()
        etag = first.getheader("ETag")
        first.read()
        assert first.status == 200
        assert etag

        connection.request("GET", "/app.js", headers={**headers, "If-None-Match": etag})
        cached = connection.getresponse()
        assert cached.status == 304
        assert cached.read() == b""

        # The session-bearing document must never return 304 with a stale token.
        connection.request("GET", "/", headers={**headers, "If-None-Match": etag})
        index = connection.getresponse()
        index.read()
        assert index.status == 200
        assert index.getheader("Set-Cookie")
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join()


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
