from __future__ import annotations

import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

import pytest

from macmaid import system


def test_command_drains_output_larger_than_pipe_buffer():
    result = system.run_command(sys.executable, ["-c", "import sys; sys.stdout.write('x'*200000); sys.stderr.write('y'*200000)"], timeout=10)
    assert result.succeeded
    assert len(result.stdout) == len(result.stderr) == 200000


def test_missing_executable_is_a_controlled_failure(monkeypatch):
    popen = Mock(side_effect=FileNotFoundError("missing"))
    monkeypatch.setattr(system.subprocess, "Popen", popen)
    result = system.run_command("not-installed", ["uninstall", "test"], timeout=2)
    assert result.status == 127
    assert popen.call_args.kwargs["shell"] is False
    assert popen.call_args.args[0] == ["not-installed", "uninstall", "test"]


def test_timeout_kills_process_group_and_reaps(monkeypatch):
    process = Mock(pid=987654)
    process.communicate.side_effect = [subprocess.TimeoutExpired("fake", 1), ("", "")]
    monkeypatch.setattr(system.subprocess, "Popen", Mock(return_value=process))
    kill = Mock()
    monkeypatch.setattr(system.os, "killpg", kill)
    assert system.run_command("fake", timeout=0).status == 124
    kill.assert_called_once_with(process.pid, system.signal.SIGKILL)
    assert process.communicate.call_count == 2


def test_wait_callback_exception_does_not_leak_process(monkeypatch):
    process = Mock(pid=987654)
    process.communicate.side_effect = [subprocess.TimeoutExpired("fake", 1), ("", "")]
    monkeypatch.setattr(system.subprocess, "Popen", Mock(return_value=process))
    kill = Mock()
    monkeypatch.setattr(system.os, "killpg", kill)
    def fail(): raise ValueError("UI disconnected")
    with pytest.raises(ValueError): system.run_command("fake", timeout=5, on_wait=fail)
    kill.assert_called_once()


@pytest.mark.parametrize("status, expected", [(0, True), (1, False), (2, None), (124, None), (127, None)])
def test_process_detection_fails_closed(monkeypatch, status, expected):
    monkeypatch.setattr(system, "which", lambda name: "fake-pgrep")
    query = Mock(return_value=system.CommandResult(status))
    monkeypatch.setattr(system, "run_command", query)
    if expected is None:
        with pytest.raises(PermissionError): system.process_running("Example.app")
    else:
        assert system.process_running("Example.app") is expected
    assert query.call_args.args[1] == ["-f", "--", r"Example\.app"]


def test_native_trash_move_never_overwrites(tmp_path):
    root = tmp_path.resolve()
    source, destination = root / "source", root / "destination"
    source.write_text("source")
    destination.write_text("existing")
    with pytest.raises(FileExistsError): system.move_to_trash_exclusive(source, destination, lambda: None)
    assert source.read_text() == "source" and destination.read_text() == "existing"


def test_native_trash_move_refuses_missing_capability(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    source = root / "source"
    source.write_text("source")
    monkeypatch.setattr(system.ctypes, "CDLL", lambda *args, **kwargs: object())
    with pytest.raises(PermissionError): system.move_to_trash_exclusive(source, root / "destination", lambda: None)
    assert source.exists()


def test_trash_move_uses_verified_atomic_fallback_when_tcc_blocks_trash_directory(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    source, trash = root / "source", root / "trash"
    source.write_text("reviewed")
    trash.mkdir()
    original = system.directory_fd

    @contextmanager
    def tcc_limited(path):
        if path == trash:
            raise PermissionError("Operation not permitted")
        with original(path) as fd:
            yield fd

    monkeypatch.setattr(system, "directory_fd", tcc_limited)
    system.move_to_trash_exclusive(source, trash / "source", lambda: None)
    assert not source.exists() and (trash / "source").read_text() == "reviewed"


def test_anchored_move_does_not_follow_replaced_parent(tmp_path):
    root = tmp_path.resolve()
    parent, outside, trash = root / "parent", root / "outside", root / "trash"
    for path in (parent, outside, trash): path.mkdir()
    (parent / "source").write_text("reviewed")
    (outside / "source").write_text("protected")
    def change():
        parent.rename(root / "original")
        parent.symlink_to(outside, target_is_directory=True)
    system.move_to_trash_exclusive(parent / "source", trash / "source", change)
    assert (trash / "source").read_text() == "reviewed"
    assert (outside / "source").read_text() == "protected"


def test_anchored_deletion_does_not_follow_symlink_child(tmp_path):
    root = tmp_path.resolve()
    cache, outside = root / "cache", root / "outside"
    cache.mkdir(); outside.mkdir()
    (outside / "precious").write_text("keep")
    (cache / "linked").symlink_to(outside, target_is_directory=True)
    system.remove_validated_path(cache, lambda: None)
    assert not cache.exists()
    assert (outside / "precious").read_text() == "keep"


def test_anchored_deletion_rejects_symlink_ancestor(tmp_path):
    root = tmp_path.resolve()
    outside = root / "outside"
    outside.mkdir(); (outside / "file").write_text("keep")
    link = root / "link"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError): system.remove_validated_path(link / "file", lambda: None)
    assert (outside / "file").exists()


def test_iter_app_bundles_never_descends_into_symlinked_dirs(tmp_path):
    root = (tmp_path / "root").resolve()
    outside = tmp_path / "outside"
    (outside / "Hidden.app").mkdir(parents=True)
    (root / "real" / "Visible.app").mkdir(parents=True)
    (root / "linked").symlink_to(outside, target_is_directory=True)

    found = {path.name for path in system.iter_app_bundles(root)}

    assert found == {"Visible.app"}


def test_iter_app_bundles_descend_flag_controls_bundle_traversal(tmp_path):
    root = tmp_path.resolve()
    nested = root / "Outer.app" / "Contents" / "Helper.app"
    nested.mkdir(parents=True)

    assert [p.name for p in system.iter_app_bundles(root)] == ["Outer.app"]
    assert {p.name for p in system.iter_app_bundles(root, descend_bundles=True)} == {"Outer.app", "Helper.app"}


def test_iter_app_bundles_reports_unreadable_dirs_via_on_error(tmp_path):
    root = tmp_path.resolve()
    locked = root / "locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        errors = []
        list(system.iter_app_bundles(root, on_error=lambda path, exc: errors.append((path, exc))))
    finally:
        locked.chmod(0o700)

    assert [path for path, _ in errors] == [locked]
    assert isinstance(errors[0][1], OSError)
