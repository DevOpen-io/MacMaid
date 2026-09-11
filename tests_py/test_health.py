from __future__ import annotations

import plistlib

from deepclean import features
from deepclean.system import CommandResult


def _status(**overrides):
    status = {
        "diskTotal": 500 * 1024**3,
        "diskFree": 100 * 1024**3,
        "diskUsageBasis": "macOS Data volume",
        "memoryPressureFreePercent": 50.0,
        "thermal": "Normal",
        "battery": {"percent": 80, "condition": "Normal", "cycleCount": 120},
        "batteryPresent": True,
        "batteryProbeSucceeded": True,
        "healthMeasuredAt": "2026-09-10T12:00:00+00:00",
    }
    status.update(overrides)
    return status


def test_health_indicators_use_pressure_not_ram_occupancy() -> None:
    indicators = {item.id: item for item in features.health_indicators(_status(memoryPercent=99))}

    assert indicators["memory"].state == "normal"
    assert "memory_pressure" in indicators["memory"].detail
    assert {item.id for item in indicators.values()} == {"disk", "memory", "thermal", "battery"}
    assert all(item.measured_at for item in indicators.values())


def test_health_warning_thresholds_have_safe_recommendations() -> None:
    indicators = {item.id: item for item in features.health_indicators(_status(
        diskFree=4 * 1024**3,
        memoryPressureFreePercent=8,
        thermal="Elevated",
        battery={"percent": 72, "condition": "Service Recommended", "cycleCount": 800},
    ))}

    assert indicators["disk"].state == "critical"
    assert indicators["memory"].state == "warning"
    assert indicators["thermal"].state == "warning"
    assert indicators["battery"].state == "critical"
    assert all(indicators[key].recommendation for key in indicators)


def test_missing_battery_is_not_a_health_failure() -> None:
    indicators = {item.id: item for item in features.health_indicators(_status(
        battery=None, batteryPresent=False, batteryProbeSucceeded=True,
    ))}

    assert indicators["battery"].state == "not_applicable"
    assert indicators["battery"].recommendation is None


def test_unreadable_probes_remain_unknown() -> None:
    indicators = {item.id: item for item in features.health_indicators(_status(
        memoryPressureFreePercent=None, thermal="Unknown", battery=None,
        batteryPresent=False, batteryProbeSucceeded=False,
    ))}

    assert indicators["memory"].state == "unknown"
    assert indicators["thermal"].state == "unknown"
    assert indicators["battery"].state == "unknown"


def test_expensive_health_commands_are_rate_limited(monkeypatch) -> None:
    calls: list[str] = []

    def command(executable, _arguments, **_kwargs):
        calls.append(executable)
        if executable.endswith("memory_pressure"):
            return CommandResult(0, "System-wide memory free percentage: 42%")
        if executable.endswith("pmset"):
            return CommandResult(0, "System-wide thermal level = 0")
        return CommandResult(0, "")

    monkeypatch.setattr(features, "run_command", command)
    monkeypatch.setattr(features.psutil, "sensors_battery", lambda: None)
    monkeypatch.setattr(features, "_health_probe_cache", None)

    first = features._expensive_health_probes()
    second = features._expensive_health_probes()

    assert first is second
    assert first["memoryFreePercent"] == 42
    assert first["thermal"] == "Normal"
    assert first["batteryProbeSucceeded"] is True
    assert len(calls) == 3


def test_health_command_failures_are_not_reported_as_normal(monkeypatch) -> None:
    monkeypatch.setattr(features, "run_command", lambda *_a, **_kw: CommandResult(124, stderr="timeout"))
    monkeypatch.setattr(features.psutil, "sensors_battery", lambda: None)
    monkeypatch.setattr(features, "_health_probe_cache", None)

    probes = features._expensive_health_probes(force=True)

    assert probes["memoryFreePercent"] is None
    assert probes["thermal"] == "Unknown"
    assert probes["batteryProbeSucceeded"] is False


def test_unsupported_psutil_battery_sensor_does_not_abort_other_probes(monkeypatch) -> None:
    def command(executable, _arguments, **_kwargs):
        if executable.endswith("memory_pressure"):
            return CommandResult(0, "System-wide memory free percentage: 55%")
        if executable.endswith("pmset"):
            return CommandResult(0, "System-wide thermal level = 0")
        return CommandResult(0, "")

    monkeypatch.setattr(features, "run_command", command)
    monkeypatch.setattr(features.psutil, "sensors_battery", lambda: (_ for _ in ()).throw(OSError("unsupported")))
    monkeypatch.setattr(features, "_health_probe_cache", None)

    probes = features._expensive_health_probes(force=True)

    assert probes["memoryFreePercent"] == 55
    assert probes["thermal"] == "Normal"
    assert probes["batteryPresent"] is False


def test_ioreg_battery_health_is_used_when_psutil_sensor_is_unavailable(monkeypatch) -> None:
    record = plistlib.dumps([{
        "BatteryHealth": "Normal", "CycleCount": 77,
        "CurrentCapacity": 80, "MaxCapacity": 100, "ExternalConnected": True,
    }]).decode()

    def command(executable, _arguments, **_kwargs):
        if executable.endswith("memory_pressure"):
            return CommandResult(0, "System-wide memory free percentage: 50%")
        if executable.endswith("pmset"):
            return CommandResult(0, "System-wide thermal level = 0")
        return CommandResult(0, record)

    monkeypatch.setattr(features, "run_command", command)
    monkeypatch.setattr(features.psutil, "sensors_battery", lambda: None)
    monkeypatch.setattr(features, "_health_probe_cache", None)

    probes = features._expensive_health_probes(force=True)

    assert probes["batteryPresent"] is True
    assert probes["battery"] == {
        "percent": 80.0, "charging": True, "cycleCount": 77, "condition": "Normal",
    }
