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


def test_app_command_announces_web_ui_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    _isolated_config(monkeypatch, tmp_path)
    real_exists = Path.exists
    monkeypatch.setattr(Path, "exists", lambda self: False if self.name == "MacMaid.app" else real_exists(self))
    served: list[tuple[int, bool]] = []
    import macmaid.web
    monkeypatch.setattr(macmaid.web, "serve", lambda port, open_browser: served.append((port, open_browser)))
    cli.main(["app", "--no-open"])
    assert served == [(8123, False)]
    assert "starting the Web UI instead" in capsys.readouterr().out


def test_app_command_falls_back_when_open_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    _isolated_config(monkeypatch, tmp_path)
    fake_home = tmp_path / "home"
    (fake_home / "Applications/MacMaid.app").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    real_exists = Path.exists
    monkeypatch.setattr(Path, "exists", lambda self: True if self.name == "MacMaid.app" else real_exists(self))
    from macmaid.system import CommandResult
    monkeypatch.setattr(cli, "run_command", lambda *a, **k: CommandResult(1, stderr="executable is missing"))
    served: list[tuple[int, bool]] = []
    import macmaid.web
    monkeypatch.setattr(macmaid.web, "serve", lambda port, open_browser: served.append((port, open_browser)))
    cli.main(["app", "--no-open"])
    assert served == [(8123, False)]
    out = capsys.readouterr().out
    assert "Could not open" in out and "executable is missing" in out


def test_whitelist_lists_rules_and_path(monkeypatch, tmp_path, capsys):
    _isolated_config(monkeypatch, tmp_path)
    (tmp_path / ".config/macmaid").mkdir(parents=True)
    (tmp_path / ".config/macmaid/whitelist").write_text("/tmp/keep\n# comment\n\n/tmp/other\n")
    cli.main(["whitelist"])
    output = capsys.readouterr().out
    assert "/tmp/keep" in output and "/tmp/other" in output
    assert "# comment" not in output
    assert "2 protected paths" in output
    assert str(tmp_path / ".config/macmaid/whitelist") in output


def test_fda_hint_prints_terminal_app_guidance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(cli, "macos_permission_report", lambda home: {
        "fullDiskAccess": "not_granted", "launchContext": "cli"})
    cli._fda_hint(Config(home=tmp_path))
    err = capsys.readouterr().err
    assert "Full Disk Access" in err and "terminal app" in err


def test_fda_hint_silent_when_granted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(cli, "macos_permission_report", lambda home: {"fullDiskAccess": "granted"})
    cli._fda_hint(Config(home=tmp_path))
    assert capsys.readouterr().err == ""
