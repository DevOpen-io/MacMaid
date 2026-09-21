from __future__ import annotations

import json
import os
import threading
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import psutil
import pytest

from macmaid import memory
from macmaid import cli
from macmaid.config import Config
from macmaid.system import CommandResult
from macmaid.web import MacMaidHandler, WebState


class FakeProcess:
    def __init__(self, pid=321, created=123.0, exe="/opt/flutter/bin/cache/dart-sdk/bin/dart", args=None, bare=False):
        self.pid = pid
        self.created = created
        self.executable = exe
        self.args = args or [exe, "language-server", "--protocol=lsp"]
        self.rss = 3 * 1024**3
        self.uid = os.getuid()
        self.signals = []
        self.denied = False
        self.bare = bare

    def oneshot(self): return nullcontext()
    @property
    def info(self):
        # A bare psutil.Process(pid) has no .info attribute at all; only
        # process_iter(attrs=...) populates it.
        if self.bare:
            raise AttributeError("'Process' object has no attribute 'info'")
        return {"pid": self.pid, "create_time": self.created,
                "uids": SimpleNamespace(real=self.uid, effective=self.uid),
                "exe": self.executable, "name": Path(self.executable).name,
                "cmdline": self.args,
                "memory_info": None if self.denied else SimpleNamespace(rss=self.rss),
                "cpu_times": SimpleNamespace(user=1.0, system=0.5)}
    def as_dict(self, attrs=None, ad_value=None):
        return {name: (getattr(self, name)() if callable(getattr(self, name)) else getattr(self, name))
                for name in (attrs or ())}
    def create_time(self): return self.created
    def uids(self): return SimpleNamespace(real=self.uid, effective=self.uid)
    def exe(self): return self.executable
    def name(self): return Path(self.executable).name
    def cmdline(self): return self.args
    def memory_info(self):
        if self.denied: raise psutil.AccessDenied(self.pid)
        return SimpleNamespace(rss=self.rss)
    def cpu_times(self): return SimpleNamespace(user=1.0, system=0.5)
    def terminate(self): self.signals.append("TERM")
    def kill(self): self.signals.append("KILL")


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(memory.os, "geteuid", lambda: 501)
    config = Config(home=tmp_path)
    config.ensure_files()
    instance = memory.MemoryService(config, threading.Lock())
    proc = FakeProcess()
    clock = SimpleNamespace(mono=1000.0, wall=100000.0)
    monkeypatch.setattr(memory.time, "monotonic", lambda: clock.mono)
    monkeypatch.setattr(memory.time, "time", lambda: clock.wall)
    monkeypatch.setattr(instance, "_protected_pids", lambda: {0, 1})
    monkeypatch.setattr(memory.psutil, "process_iter", lambda *a, **kw: [proc])
    monkeypatch.setattr(memory.psutil, "Process", lambda pid: proc)
    monkeypatch.setattr(memory.psutil, "virtual_memory", lambda: SimpleNamespace(used=10, total=20, available=10))
    monkeypatch.setattr(memory.psutil, "swap_memory", lambda: SimpleNamespace(used=2))
    monkeypatch.setattr(instance, "_sample_pressure_headroom", lambda now: 10)
    monkeypatch.setattr(memory.psutil, "wait_procs", lambda procs, timeout: (procs, []))
    instance.sample()
    instance.proc = proc
    instance.clock = clock
    return instance


def key(service): return next(iter(service.rows))


def add_rule(service):
    service.configure({"operation": "rule", "key": key(service), "consent": True})
    service.configure({"operation": "pause", "paused": False})
    return service.settings["rules"][0]


def advance(service, seconds):
    service.clock.mono += seconds
    service.clock.wall += seconds
    service.last_sample = service.clock.mono


def record_memory(service, rss, seconds=5):
    """Record one synthetic sample without waiting for wall-clock time."""
    service.clock.mono += seconds
    service.clock.wall += seconds
    service.proc.rss = rss
    service.sample()
    service.automate()


def test_sample_and_history_are_read_only(service):
    row = service.snapshot()["processes"][0]
    assert row["role"] == "dart-analysis" and row["helper"]
    assert row["growthBytes"] is None
    assert service.history(row["key"])["samples"][0]["rssBytes"] == 3 * 1024**3
    assert service.proc.signals == []


def test_pressure_probe_is_memory_only_and_cached(tmp_path, monkeypatch):
    config = Config(home=tmp_path)
    config.ensure_files()
    service = memory.MemoryService(config, threading.Lock())
    calls = []

    def command(executable, arguments, timeout):
        calls.append((executable, arguments, timeout))
        return CommandResult(0, "System-wide memory free percentage: 17.5%")

    monkeypatch.setattr(memory, "run_command", command)
    assert service._sample_pressure_headroom(100.0) == 17.5
    assert service._sample_pressure_headroom(110.0) == 17.5
    assert calls == [("/usr/bin/memory_pressure", ["-Q"], 5)]
    assert service._sample_pressure_headroom(131.0) == 17.5
    assert len(calls) == 2


@pytest.mark.parametrize("exe,args,role", [
    ("/sdk/dart", ["/sdk/dart", "language-server"], "dart-analysis"),
    ("/sdk/dartaotruntime", ["/sdk/dartaotruntime", "/sdk/analysis_server_aot.dart.snapshot"], "dart-analysis"),
    ("/sdk/dart", ["/sdk/dart", "run", "/sdk/analysis_server.dart.snapshot"], "dart-tool"),
    ("/bin/node", ["node", "/x/typescript/lib/tsserver.js"], "typescript-server"),
    ("/bin/node", ["node", "app.js", "/x/typescript/lib/tsserver.js"], "development-tool"),
    ("/bin/node", ["node", "-e", "/x/typescript/lib/tsserver.js"], "development-tool"),
    ("/bin/node", ["node", "--require", "/x/typescript/lib/tsserver.js", "build.js"], "development-tool"),
    ("/bin/node", ["node", "--max-old-space-size=3072", "/x/typescript/lib/tsserver.js"], "typescript-server"),
    ("/sdk/dartvm", ["/sdk/dartvm", "/sdk/analysis_server.dart.snapshot"], "dart-analysis"),
    ("/sdk/dartvm", ["/sdk/dartvm", "/flutter/flutter_tools.snapshot", "run"], "dart-tool"),
    ("/sdk/flutter_tester", ["/sdk/flutter_tester", "test.dill"], "flutter-tool"),
    ("/sdk/dart_mcp_server", ["/sdk/dart_mcp_server"], "flutter-tool"),
    ("/bin/java", ["java", "gradle"], "development-tool"),
    ("/x/not-dart", ["dart", "language-server"], "application"),
])
def test_classification_is_narrow(exe, args, role):
    assert memory.classify(exe, args)[1] == role


def test_growth_requires_time_magnitude_and_sustained_medians():
    samples = [(float(t), 1024**3 + t * 1024**2) for t in range(0, 601, 5)]
    assert memory.growth(samples, 600)["growing"]
    assert not memory.growth(samples[10:], 600)["historyReady"]
    assert not memory.growth([(t, 1024**3) for t, _ in samples], 600)["growing"]
    assert not memory.growth([(t, 1024**3 + (1024**3 if t == 600 else 0)) for t, _ in samples], 600)["growing"]
    assert not memory.growth([(t, 1024**3 + (t % 120) * 1024**2) for t, _ in samples], 600)["growing"]


def test_sampling_gap_and_exited_process_prune_history(service, monkeypatch):
    advance(service, 30)
    service.last_sample -= 30
    service.sample()
    assert len(service.histories[key(service)]) == 1
    monkeypatch.setattr(memory.psutil, "process_iter", lambda *a, **kw: [])
    service.sample()
    assert service.histories == {} and service.rows == {}


def test_review_fingerprint_ignores_rss_but_binds_identity(service):
    first = service.review([key(service)]).fingerprint
    service.proc.rss += 100
    service.sample()
    assert service.review([key(service)]).fingerprint == first
    service.proc.created += 1
    with pytest.raises(PermissionError): service.review([key(service)])
    assert not service.proc.signals


@pytest.mark.parametrize("condition", ["other-user", "system", "ancestor", "excluded", "whitelist", "changed-exe", "changed-entrypoint"])
def test_protected_targets_cannot_be_stopped(service, monkeypatch, condition):
    original = key(service)
    if condition == "other-user": service.proc.uid += 1
    if condition == "system": service.proc.executable = "/System/Library/Finder"
    if condition == "ancestor": monkeypatch.setattr(service, "_protected_pids", lambda: {service.proc.pid})
    if condition == "excluded": service.configure({"operation": "exclude", "key": original})
    if condition == "whitelist": service.config.whitelist_file.write_text(service.proc.executable)
    if condition == "changed-exe": service.proc.executable = "/other/dart"
    if condition == "changed-entrypoint": service.proc.args = [service.proc.executable, "/other/analysis_server.dart.snapshot"]
    result = service.stop([original])
    assert result["outcomes"][0]["outcome"] == "skipped"
    assert not service.proc.signals


def test_stop_survivor_requires_separate_force_review(service, monkeypatch):
    target = key(service)
    with pytest.raises(PermissionError): service.review([target], force=True)
    monkeypatch.setattr(memory.psutil, "wait_procs", lambda procs, timeout: ([], procs))
    assert service.stop([target])["outcomes"][0]["outcome"] == "still-running"
    assert service.snapshot()["processes"][0]["forceEligible"]
    assert service.review([target], force=True).requires_extra_opt_in
    monkeypatch.setattr(memory.psutil, "wait_procs", lambda procs, timeout: (procs, []))
    assert service.stop([target], force=True)["outcomes"][0]["outcome"] == "exited"
    assert service.proc.signals == ["TERM", "KILL"]


def test_stop_partial_outcomes_and_audit_do_not_log_arguments(service):
    service.proc.args += ["--token=secret"]
    result = service.stop([key(service), "999:1"])
    assert {r["outcome"] for r in result["outcomes"]} == {"exited", "skipped"}
    audit = service.config.operation_log.read_text()
    assert "secret" not in audit and '"automatic": false' in audit


def test_identity_recheck_supports_bare_process_without_info(service, monkeypatch):
    # psutil.Process(pid) has no .info attribute; _target must collect fields itself.
    bare = FakeProcess(bare=True)
    monkeypatch.setattr(memory.psutil, "Process", lambda pid: bare)
    plan = service.review([key(service)])
    assert [item.key for item in plan.items] == [key(service)]
    assert service.stop([key(service)])["outcomes"][0]["outcome"] == "exited"
    assert bare.signals == ["TERM"]


def test_force_stop_supports_bare_process_without_info(service, monkeypatch):
    bare = FakeProcess(bare=True)
    monkeypatch.setattr(memory.psutil, "Process", lambda pid: bare)
    monkeypatch.setattr(memory.psutil, "wait_procs", lambda procs, timeout: ([], procs))
    target = key(service)
    assert service.stop([target])["outcomes"][0]["outcome"] == "still-running"
    assert service.review([target], force=True).requires_extra_opt_in
    monkeypatch.setattr(memory.psutil, "wait_procs", lambda procs, timeout: (procs, []))
    assert service.stop([target], force=True)["outcomes"][0]["outcome"] == "exited"
    assert bare.signals == ["TERM", "KILL"]


def test_automation_stop_supports_bare_process_without_info(service, monkeypatch):
    add_rule(service)
    bare = FakeProcess(bare=True)
    monkeypatch.setattr(memory.psutil, "Process", lambda pid: bare)
    service.automate()
    advance(service, 300)
    service.metrics["pressureHeadroom"] = 10
    service.automate()
    assert bare.signals == ["TERM"]
    assert service.snapshot()["events"][0]["automatic"] is True


def test_automation_requires_sustained_rss_and_pressure(service):
    add_rule(service)
    service.automate()
    advance(service, 299)
    service.automate()
    assert not service.proc.signals
    advance(service, 1)
    service.metrics["pressureHeadroom"] = None
    service.automate()
    assert not service.proc.signals
    service.metrics["pressureHeadroom"] = 30
    service.automate()
    assert not service.proc.signals
    service.metrics["pressureHeadroom"] = 10
    service.automate()
    assert service.proc.signals == ["TERM"]
    saved = json.loads(service.path.read_text())
    assert saved["rules"][0]["lastAttempt"] == service.clock.wall
    service.automate()
    advance(service, 300)
    service.automate()
    assert service.proc.signals == ["TERM"]


def test_thirty_second_rule_uses_real_sample_sequence_without_sleeping(service):
    threshold = 2 * 1024**3
    service.configure({
        "operation": "rule", "key": key(service), "consent": True,
        "rssBytes": threshold, "durationSeconds": 30, "pressureBelow": 15,
    })
    service.configure({"operation": "pause", "paused": False})

    # The first above-threshold observation starts the timer. Six subsequent
    # five-second records are required before an action is eligible.
    service.automate()
    observed = []
    for _ in range(5):
        record_memory(service, threshold + 512 * 1024**2)
        observed.append(service.snapshot()["processes"][0]["rssBytes"])
        assert service.proc.signals == []

    record_memory(service, threshold + 512 * 1024**2)
    observed.append(service.snapshot()["processes"][0]["rssBytes"])

    assert observed == [threshold + 512 * 1024**2] * 6
    assert service.proc.signals == ["TERM"]
    event = service.snapshot()["events"][0]
    assert event["automatic"] is True and event["outcome"] == "exited"


def test_thirty_second_rule_resets_after_one_below_threshold_record(service):
    threshold = 2 * 1024**3
    service.configure({
        "operation": "rule", "key": key(service), "consent": True,
        "rssBytes": threshold, "durationSeconds": 30, "pressureBelow": 15,
    })
    service.configure({"operation": "pause", "paused": False})
    service.automate()

    for _ in range(5):
        record_memory(service, threshold + 1)
    record_memory(service, threshold)  # Equality is not above the threshold.
    for _ in range(6):
        record_memory(service, threshold + 1)
        assert service.proc.signals == []

    record_memory(service, threshold + 1)
    assert service.proc.signals == ["TERM"]


def test_thirty_second_rule_requires_pressure_strictly_below_limit(service, monkeypatch):
    pressure = SimpleNamespace(value=15)
    monkeypatch.setattr(service, "_sample_pressure_headroom", lambda now: pressure.value)
    service.configure({
        "operation": "rule", "key": key(service), "consent": True,
        "rssBytes": 2 * 1024**3, "durationSeconds": 30, "pressureBelow": 15,
    })
    service.configure({"operation": "pause", "paused": False})
    service.automate()

    for _ in range(6):
        record_memory(service, 3 * 1024**3)
    assert service.proc.signals == []

    pressure.value = 14
    record_memory(service, 3 * 1024**3)
    assert service.proc.signals == ["TERM"]


def test_thirty_second_history_is_ordered_but_not_called_ten_minute_growth(service):
    target = key(service)
    base = 1024**3
    expected = [base + step * 64 * 1024**2 for step in range(1, 7)]

    for rss in expected:
        record_memory(service, rss)

    samples = service.history(target)["samples"]
    assert [sample["rssBytes"] for sample in samples[-6:]] == expected
    assert [round(sample["secondsAgo"]) for sample in samples[-6:]] == [25, 20, 15, 10, 5, 0]
    row = service.snapshot()["processes"][0]
    assert row["historyReady"] is False
    assert row["growing"] is False
    assert row["growthBytes"] is None


def test_rule_matches_only_the_exact_recognized_helper(service, monkeypatch):
    decoy = FakeProcess(
        pid=322,
        exe="/opt/node/bin/node",
        args=["node", "app.js", "/x/typescript/lib/tsserver.js"],
    )
    monkeypatch.setattr(memory.psutil, "process_iter", lambda *a, **kw: [service.proc, decoy])
    monkeypatch.setattr(memory.psutil, "Process", lambda pid: service.proc if pid == service.proc.pid else decoy)
    service.sample()
    target = key(service)
    service.configure({
        "operation": "rule", "key": target, "consent": True,
        "rssBytes": 2 * 1024**3, "durationSeconds": 30, "pressureBelow": 15,
    })
    service.configure({"operation": "pause", "paused": False})
    service.automate()

    for _ in range(6):
        record_memory(service, 3 * 1024**3)

    assert service.proc.signals == ["TERM"]
    assert decoy.signals == []
    assert next(row for row in service.rows.values() if row["pid"] == decoy.pid)["helper"] is False


def test_rule_update_is_deduplicated_persisted_and_deletable(service):
    target = key(service)
    first = service.configure({
        "operation": "rule", "key": target, "consent": True,
        "rssBytes": 2 * 1024**3, "durationSeconds": 30, "pressureBelow": 15,
    })["settings"]["rules"][0]
    updated = service.configure({
        "operation": "rule", "key": target, "consent": True,
        "rssBytes": 4 * 1024**3, "durationSeconds": 45, "pressureBelow": 12,
    })["settings"]["rules"]

    assert len(updated) == 1
    assert updated[0]["id"] == first["id"]
    assert (updated[0]["rssBytes"], updated[0]["durationSeconds"], updated[0]["pressureBelow"]) == (
        4 * 1024**3, 45, 12,
    )
    restored = memory.MemoryService(service.config, threading.Lock())
    assert restored.settings["rules"] == updated

    result = service.configure({"operation": "delete-rule", "id": first["id"]})
    assert result["settings"]["rules"] == []
    assert json.loads(service.path.read_text())["rules"] == []


def test_cooldown_survives_service_restart(service):
    add_rule(service)
    service.automate(); advance(service, 300); service.automate()
    restored = memory.MemoryService(service.config, threading.Lock())
    assert restored.settings["rules"][0]["lastAttempt"] == service.clock.wall


@pytest.mark.parametrize("block", ["disabled", "pause", "exclusion", "lock", "rss-drop", "identity", "shutdown"])
def test_automation_blocks_unsafe_or_ineligible_actions(service, block):
    add_rule(service)
    service.automate(); advance(service, 300)
    if block == "disabled":
        service.settings["rules"][0]["enabled"] = False; service._save_settings()
    if block == "pause": service.configure({"operation": "pause", "paused": True})
    if block == "exclusion": service.configure({"operation": "exclude", "key": key(service)})
    if block == "lock": service.mutation_lock.acquire()
    if block == "rss-drop": service.proc.rss = 1
    if block == "identity": service.proc.created += 1
    if block == "shutdown": service.stop_event.set()
    try: service.automate()
    finally:
        if block == "lock": service.mutation_lock.release()
    assert not service.proc.signals


def test_rule_pauses_after_two_failures_and_never_force_stops(service, monkeypatch):
    add_rule(service)
    monkeypatch.setattr(memory.psutil, "wait_procs", lambda procs, timeout: ([], procs))
    service.automate(); advance(service, 300); service.automate()
    advance(service, 1800); service.automate(); advance(service, 300); service.automate()
    assert service.proc.signals == ["TERM", "TERM"]
    assert service.settings["rules"][0]["enabled"] is False


def test_rule_requires_consent_and_known_helper(service):
    with pytest.raises(PermissionError): service.configure({"operation": "rule", "key": key(service)})
    service.proc.executable = "/Applications/Editor.app/Contents/MacOS/editor"
    service.proc.args = [service.proc.executable]
    service.sample()
    with pytest.raises(PermissionError): service.configure({"operation": "rule", "key": key(service), "consent": True})


@pytest.mark.parametrize("field,value", [("rssBytes", -1), ("rssBytes", float("nan")), ("durationSeconds", 0), ("pressureBelow", True)])
def test_invalid_rule_thresholds_do_not_persist(service, field, value):
    with pytest.raises(ValueError): service.configure({"operation": "rule", "key": key(service), "consent": True, field: value})
    assert not service.path.exists()


def test_corrupt_and_symlink_settings_fail_closed(service, tmp_path):
    service.path.write_text('{"paused": false, "rules": "bad"}')
    service.settings = service._read_settings()
    assert service.settings["paused"] and service.settings_error
    with pytest.raises(PermissionError): service.stop([key(service)])
    service.path.unlink()
    target = tmp_path / "outside.json"
    target.write_text('{}')
    service.path.symlink_to(target)
    service.settings = service._read_settings()
    assert service.settings["paused"] and service.settings_error
    assert target.read_text() == '{}'


def test_audit_failure_prevents_signal(service, tmp_path):
    target = tmp_path / 'log'
    target.write_text('unchanged')
    service.config.operation_log.symlink_to(target)
    with pytest.raises(PermissionError): service.stop([key(service)])
    assert not service.proc.signals


def test_route_requires_exact_fresh_review_and_opt_in(service):
    state = WebState(service.config)
    state.memory = service
    handler = object.__new__(MacMaidHandler)
    handler.server = SimpleNamespace(state=state)
    payload = {"keys": [key(service)]}
    with pytest.raises(PermissionError): handler._route_post('/api/memory/stop', payload)
    reviewed = handler._route_post('/api/memory/stop', dict(payload, reviewOnly=True))
    with pytest.raises(PermissionError): handler._route_post('/api/memory/stop', dict(payload, reviewToken=reviewed['reviewToken']))
    reviewed = handler._route_post('/api/memory/stop', dict(payload, reviewOnly=True))
    result = handler._route_post('/api/memory/stop', dict(payload, reviewToken=reviewed['reviewToken'], extraOptIn=True))
    assert result['outcomes'][0]['outcome'] == 'exited'
    with pytest.raises(PermissionError): handler._route_post('/api/memory/stop', dict(payload, reviewToken=reviewed['reviewToken'], extraOptIn=True))
    assert service.proc.signals == ['TERM']


def test_worker_stops_without_extra_sampling(service, monkeypatch):
    called = threading.Event()
    def sample():
        service.stop_event.set()
        called.set()
    monkeypatch.setattr(service, 'sample', sample)
    service.start()
    assert called.wait(2)
    service.shutdown()
    assert not service.thread.is_alive()


def test_core_process_actions_reject_root(service, monkeypatch):
    monkeypatch.setattr(memory.os, "geteuid", lambda: 0)
    result = service.stop([key(service)])
    assert result["outcomes"][0]["outcome"] == "skipped"
    assert not service.proc.signals


def test_automation_stops_at_most_one_helper_per_cycle(service, monkeypatch):
    other = FakeProcess(pid=322)
    monkeypatch.setattr(memory.psutil, "process_iter", lambda *a, **kw: [service.proc, other])
    monkeypatch.setattr(memory.psutil, "Process", lambda pid: service.proc if pid == 321 else other)
    service.sample()
    add_rule(service)
    service.automate(); advance(service, 300); service.automate()
    assert len(service.proc.signals) + len(other.signals) == 1


def test_removed_process_and_permission_denial_do_not_signal(service, monkeypatch):
    original = key(service)
    def missing(pid):
        raise psutil.NoSuchProcess(pid)
    monkeypatch.setattr(memory.psutil, "Process", missing)
    assert service.stop([original])["outcomes"][0]["outcome"] == "skipped"
    assert not service.proc.signals
    service.proc.denied = True
    service.sample()
    assert service.snapshot()["processes"][0]["protected"] == "unverified-identity"


def test_histories_are_bounded_to_an_hour(service):
    target = key(service)
    for _ in range(800):
        advance(service, 5)
        service.sample()
    assert len(service.histories[target]) <= 721
    assert service.history(target)["samples"][0]["secondsAgo"] <= 3600


def test_doctor_uses_structured_health_status(service, monkeypatch, capsys):
    monkeypatch.setattr(cli, "Config", lambda: service.config)
    monkeypatch.setattr(cli, "doctor", lambda: [
        {"name": "Missing tool", "value": "Unavailable", "ok": False},
        {"name": "Ready tool", "value": "Available", "ok": True},
        {"name": "Neutral tool", "value": "Unknown", "ok": None},
    ])
    cli.main(["doctor"])
    output = capsys.readouterr().out
    assert "■ Unavailable" in output
    assert "✓ Available" in output
    assert "✓ Unknown" not in output and "■ Unknown" not in output


def test_cli_memory_stop_is_review_only_without_apply(service, monkeypatch, capsys):
    monkeypatch.setattr(cli, "Config", lambda: service.config)
    monkeypatch.setattr(cli, "MemoryService", lambda config, lock: service)
    cli.main(["memory", "--stop", str(service.proc.pid), "--limit", "5"])
    output = capsys.readouterr().out
    assert "Exact operation review" in output
    assert "No changes made" in output
    assert service.proc.signals == []


def test_cli_memory_apply_stops_only_reviewed_pid(service, monkeypatch, capsys):
    monkeypatch.setattr(cli, "Config", lambda: service.config)
    monkeypatch.setattr(cli, "MemoryService", lambda config, lock: service)
    cli.main(["memory", "--stop", str(service.proc.pid), "--apply", "--yes"])
    assert service.proc.signals == ["TERM"]
    assert "exited" in capsys.readouterr().out


def test_cli_memory_snapshot_rich_rendering(service, monkeypatch, capsys):
    monkeypatch.setattr(cli, "Config", lambda: service.config)
    monkeypatch.setattr(cli, "MemoryService", lambda config, lock: service)
    cli.main(["memory", "--limit", "5"])
    output = capsys.readouterr().out
    assert "MacMaid Memory Monitor" in output
    assert "Process" in output
    assert "RSS" in output
    assert "dart" in output


def test_cli_memory_growing_requires_a_ten_minute_watch(service, monkeypatch):
    monkeypatch.setattr(cli, "Config", lambda: service.config)
    monkeypatch.setattr(cli, "MemoryService", lambda config, lock: service)
    with pytest.raises(ValueError, match="--watch 600"):
        cli.main(["memory", "--growing"])


def test_cli_memory_watch_collects_multiple_samples(service, monkeypatch, capsys):
    monkeypatch.setattr(cli, "Config", lambda: service.config)
    monkeypatch.setattr(cli, "MemoryService", lambda config, lock: service)
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: advance(service, seconds))
    cli.main(["memory", "--watch", "10", "--sort", "cpu", "--filter", "growing"])
    output = capsys.readouterr().out
    assert "MacMaid Memory Monitor" in output
    assert "Process" in output
    assert len(service.histories[key(service)]) == 4

