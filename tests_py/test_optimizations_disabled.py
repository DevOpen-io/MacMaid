from __future__ import annotations

from types import SimpleNamespace

import pytest

from macmaid import cli, features, web
from macmaid.config import Config


def test_optimize_command_is_removed() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["optimize"])
    assert exc.value.code == 2  # argparse rejects unknown commands


def test_optimize_symbols_and_completion_are_removed() -> None:
    assert not hasattr(features, "OPTIMIZATIONS")
    assert not hasattr(features, "run_optimization")
    for shell in ("zsh", "bash", "fish"):
        assert "optimize" not in features.completion_script(shell)


def test_optimize_api_endpoints_are_removed(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(web, "Config", lambda: Config(home=tmp_path))
    handler = object.__new__(web.MacMaidHandler)
    handler.server = SimpleNamespace(state=SimpleNamespace(config=Config(home=tmp_path)))
    with pytest.raises(FileNotFoundError):
        handler._route_get("/api/optimize", {})
