from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from macmaid import cleaner as cleaning, web
from macmaid.config import Config
from macmaid.web import WebState


def test_treemap_endpoint_returns_nodes_with_percentage_and_file_count(tmp_path, monkeypatch):
    home = tmp_path / "home"
    folder = home / "folder"
    folder.mkdir(parents=True)
    (folder / "a.bin").write_bytes(b"a" * 10)
    (folder / "b.bin").write_bytes(b"b" * 5)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    state = WebState(Config(home=home))
    handler = object.__new__(web.MacMaidHandler)
    handler.server = SimpleNamespace(state=state)
    try:
        payload = handler._route_get("/api/treemap", {"path": str(home), "start": "true"})
        deadline = time.monotonic() + 2
        node = None
        while time.monotonic() < deadline:
            node = next((item for item in payload["nodes"] if item["name"] == "folder"), None)
            if node is not None:
                break
            time.sleep(0.02)
            payload = handler._route_get("/api/treemap", {"path": str(home)})
        assert node is not None
        assert node["percentage"] > 0
        assert node["fileCount"] == 2
        assert node["cleanupCandidate"] is True
    finally:
        state.analyzer.shutdown()


def test_treemap_open_requires_latest_view(monkeypatch, tmp_path):
    path = tmp_path / "file.txt"
    path.write_text("x")
    run = Mock(return_value=SimpleNamespace(succeeded=True, stdout="", stderr=""))
    monkeypatch.setattr(web, "run_command", run)
    handler = object.__new__(web.MacMaidHandler)
    handler.server = SimpleNamespace(state=SimpleNamespace(treemap_paths={path}))

    assert handler._route_post("/api/treemap/open", {"path": str(path)})["success"] is True
    run.assert_called_once_with("/usr/bin/open", ["-R", str(path)], timeout=15)
    with pytest.raises(PermissionError):
        handler._route_post("/api/treemap/open", {"path": str(tmp_path / "other")})


def test_treemap_cleanup_requires_review_and_uses_trash(monkeypatch, tmp_path):
    home = tmp_path / "home"
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    target = downloads / "old.bin"
    target.write_text("data")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(cleaning.os, "geteuid", lambda: 501)
    config = Config(home=home); config.ensure_files()
    state = SimpleNamespace(config=config, treemap_paths={target}, token="secret", generations={"treemap": 1}, review_tokens={}, lock=__import__("threading").RLock())
    handler = object.__new__(web.MacMaidHandler); handler.server = SimpleNamespace(state=state)

    prepared = handler._route_post("/api/treemap/trash", {"paths": [str(target)], "reviewOnly": True})
    with pytest.raises(PermissionError):
        handler._route_post("/api/treemap/trash", {"paths": [str(target)], "reviewToken": prepared["reviewToken"]})
    prepared = handler._route_post("/api/treemap/trash", {"paths": [str(target)], "reviewOnly": True})
    result = handler._route_post("/api/treemap/trash", {"paths": [str(target)], "reviewToken": prepared["reviewToken"], "extraOptIn": True})

    assert result["success"] is True
    assert not target.exists()
