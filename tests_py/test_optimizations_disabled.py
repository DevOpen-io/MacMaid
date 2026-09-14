from __future__ import annotations

from macmaid import features


def test_maintenance_commands_are_disabled_without_spawning_subprocesses(monkeypatch) -> None:
    command_called = False

    def unexpected_command(*_args, **_kwargs):
        nonlocal command_called
        command_called = True
        raise AssertionError("a disabled optimization must not launch a command")

    monkeypatch.setattr(features, "run_command", unexpected_command)

    assert features.OPTIMIZATIONS == []
    result = features.run_optimization("launchservices")

    assert result == {"success": False, "error": features.OPTIMIZATION_UNAVAILABLE_REASON}
    assert not command_called
