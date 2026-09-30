"""CLI boundary contract: expected user-facing errors exit 1 without a traceback."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from macmaid import cli
from macmaid.config import Config


def _isolated_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "Config", lambda: Config(home=tmp_path))


def test_restore_unknown_history_item_exits_cleanly(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    _isolated_config(monkeypatch, tmp_path)
    with pytest.raises(SystemExit) as stopped:
        cli.main(["restore", "--operation-id", "missing", "--trash-path", str(tmp_path / "gone")])
    assert stopped.value.code == 1
    captured = capsys.readouterr()
    assert "macmaid: error:" in captured.err
    assert "not found" in captured.err.lower()
    assert "Traceback" not in captured.err + captured.out


def test_memory_stop_missing_pid_exits_cleanly(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    _isolated_config(monkeypatch, tmp_path)
    service = SimpleNamespace(
        sample=lambda: None,
        refresh_footprints=lambda force=True: None,
        snapshot=lambda: {"processes": []},
    )
    monkeypatch.setattr(cli, "MemoryService", lambda config, lock: service)
    with pytest.raises(SystemExit) as stopped:
        cli.main(["memory", "--stop", "999999"])
    assert stopped.value.code == 1
    captured = capsys.readouterr()
    assert "macmaid: error:" in captured.err
    assert "999999" in captured.err
    assert "Traceback" not in captured.err + captured.out


def test_memory_watch_out_of_range_exits_cleanly(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    _isolated_config(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "MemoryService", lambda config, lock: SimpleNamespace())
    with pytest.raises(SystemExit) as stopped:
        cli.main(["memory", "--watch", "99999"])
    assert stopped.value.code == 1
    assert "--watch must be between" in capsys.readouterr().err


def test_clean_help_uses_its_own_program_name(capsys) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(["clean", "--help"])
    assert stopped.value.code == 0
    output = capsys.readouterr().out
    assert "usage: macmaid clean" in output
    assert "usage: macmaid scan" not in output


def test_argparse_errors_still_exit_2(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _isolated_config(monkeypatch, tmp_path)
    with pytest.raises(SystemExit) as stopped:
        cli.main(["restore"])
    assert stopped.value.code == 2


def test_unexpected_errors_still_raise(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _isolated_config(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "doctor", lambda: (_ for _ in ()).throw(KeyError("boom")))
    with pytest.raises(KeyError):
        cli.main(["doctor"])
