"""Process-family grouping and physical-footprint metric tests.

The group memory metric must be an honest measurement: macOS
``footprint(1)`` physical footprint (shared pages de-duplicated) when it
actually ran for the exact membership, otherwise a clearly-labeled RSS
fallback. No synthetic PSS may ever appear.
"""
from __future__ import annotations

import threading
import time
from collections import deque

from macmaid import memory
from macmaid.config import Config
from macmaid.system import CommandResult


def _row(pid, created=100.0, name="proc", exe="/usr/bin/proc", ppid=1, rss=100,
         protected="", category="all", role="application"):
    return {
        "key": f"{pid}:{created}", "pid": pid, "created": created, "name": name,
        "exe": exe, "ppid": ppid, "category": category, "role": role,
        "entrypoint": "", "rssBytes": rss, "cpuPercent": 1.0, "protected": protected,
        "helper": False, "growthBytes": None, "growing": False,
        "historyReady": False, "forceEligible": False,
    }


def _service(tmp_path):
    config = Config(home=tmp_path)
    config.ensure_files()
    service = memory.MemoryService(config, threading.Lock())
    service.footprint_available = True
    return service


CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
HELPER = "/Applications/Google Chrome.app/Contents/Frameworks/Google Chrome Helper.app/Contents/MacOS/Google Chrome Helper"
GPU = "/Applications/Google Chrome.app/Contents/Frameworks/Google Chrome Helper (GPU).app/Contents/MacOS/Google Chrome Helper (GPU)"


def test_app_and_helpers_share_one_bundle_group():
    rows = [
        _row(10, name="Google Chrome", exe=CHROME, ppid=1),
        _row(11, name="Google Chrome Helper", exe=HELPER, ppid=10),
        _row(12, name="Google Chrome Helper (GPU)", exe=GPU, ppid=10),
    ]
    groups = memory.build_groups(rows)
    assert len(groups) == 1
    group = groups[0]
    assert group["kind"] == "application"
    assert group["id"] == "app:/Applications/Google Chrome.app"
    assert group["bundlePath"] == "/Applications/Google Chrome.app"
    assert group["processCount"] == 3
    assert group["rssBytes"] == 300


def test_unrelated_same_name_processes_are_not_merged():
    rows = [
        _row(20, name="node", exe="/usr/local/bin/node", ppid=1),
        _row(21, name="node", exe="/opt/homebrew/bin/node", ppid=1),
        _row(22, name="node", exe="/usr/local/bin/node", ppid=1, created=200.0),
    ]
    groups = memory.build_groups(rows)
    # 20 and 22 share an exe but neither is a parent of the other: no grouping.
    assert len(groups) == 3
    assert all(group["kind"] == "process" for group in groups)


def test_pid_reuse_produces_a_new_group_identity():
    old = memory.build_groups([_row(30, created=100.0, name="worker", exe="/usr/bin/worker")])
    new = memory.build_groups([_row(30, created=200.0, name="worker", exe="/usr/bin/worker")])
    assert old[0]["id"] != new[0]["id"]
    assert old[0]["signature"] != new[0]["signature"]


def test_orphan_process_is_standalone():
    groups = memory.build_groups([_row(40, name="kernelish", exe="/sbin/launchd", ppid=0)])
    assert len(groups) == 1
    assert groups[0]["processCount"] == 1


def test_same_executable_parent_chain_groups_without_a_bundle():
    rows = [
        _row(50, name="worker", exe="/usr/bin/worker", ppid=1),
        _row(51, name="worker", exe="/usr/bin/worker", ppid=50),
        _row(52, name="other", exe="/usr/bin/other", ppid=51),  # different exe: standalone
    ]
    groups = memory.build_groups(rows)
    by_id = {group["id"]: group for group in groups}
    assert len(groups) == 2
    family = by_id["proc:50:100.0"]
    assert family["processCount"] == 2
    assert by_id["proc:52:100.0"]["processCount"] == 1


def test_bundled_children_do_not_attach_to_non_bundle_tree_group():
    rows = [
        _row(60, name="worker", exe="/usr/bin/worker", ppid=1),
        _row(61, name="helper", exe=HELPER, ppid=60),  # bundled: must not join worker's tree
    ]
    groups = memory.build_groups(rows)
    assert len(groups) == 2


def test_protected_children_stay_protected_in_mixed_group():
    rows = [
        _row(70, name="App", exe="/Applications/App.app/Contents/MacOS/App"),
        _row(71, name="Helper", exe="/Applications/App.app/Contents/Helper", protected="other-user"),
        _row(72, name="Helper2", exe="/Applications/App.app/Contents/Helper2"),
    ]
    group = memory.build_groups(rows)[0]
    assert group["processCount"] == 3
    assert group["protectedCount"] == 1
    assert group["eligibleCount"] == 2
    assert group["children"][1]["protected"] == "other-user"


def test_parse_footprint_output_extracts_summary_and_per_pid():
    # Real footprint(1) layout: "name [pid]: arch    Footprint: N B" sections,
    # auxiliary data blocks, and a de-duplicated summary line.
    text = (
        "======================================================================\n"
        "Google Chrome [10]: 64-bit    Footprint: 500000000 B (16384 bytes per page)\n"
        "======================================================================\n\n"
        "Auxiliary data:\n    phys_footprint: 500000000 B\n    phys_footprint_peak: 510000000 B\n\n"
        "======================================================================\n"
        "Helper [11]: 64-bit    Footprint: 300000000 B (16384 bytes per page)\n"
        "======================================================================\n\n"
        "Auxiliary data:\n    phys_footprint: 300000000 B\n\n"
        "======================================================================\n"
        "Summary Footprint: 650000000 B\n"
        "======================================================================\n"
    )
    per_pid, summary = memory.parse_footprint_output(text)
    assert per_pid == {10: 500000000, 11: 300000000}
    assert summary == 650000000  # less than the 800MB RSS-style sum: shared pages deduped


def test_parse_footprint_output_tolerates_missing_summary():
    per_pid, summary = memory.parse_footprint_output("noise\n")
    assert per_pid == {} and summary is None


def _footprint_calls(service, monkeypatch, per_pid_map, summary):
    calls = []

    def command(executable, arguments, timeout=120, on_wait=None):
        calls.append(list(arguments))
        pids = [arg for arg in arguments if arg.isdigit()]
        lines = []
        for pid in pids:
            value = per_pid_map.get(int(pid))
            if value is not None:
                lines.append(f"proc [{pid}]: 64-bit    Footprint: {value} B (16384 bytes per page)")
        if summary is not None:
            lines.append(f"Summary Footprint: {summary} B")
        return CommandResult(0, "\n".join(lines))

    monkeypatch.setattr(memory, "run_command", command)
    return calls


def test_physical_footprint_overlay_and_honest_labels(tmp_path, monkeypatch):
    service = _service(tmp_path)
    rows = [
        _row(10, name="Google Chrome", exe=CHROME, rss=500),
        _row(11, name="Helper", exe=HELPER, ppid=10, rss=400),
        _row(90, name="solo", exe="/usr/bin/solo", rss=50),
    ]
    service.rows = {row["key"]: row for row in rows}
    calls = _footprint_calls(service, monkeypatch, {10: 500, 11: 400, 90: 60}, summary=650)

    service.refresh_footprints(force=True)
    groups = {group["id"]: group for group in service.groups_for(rows)}

    chrome = groups["app:/Applications/Google Chrome.app"]
    assert chrome["memoryBytes"] == 650  # deduped total, never the 900 RSS sum
    assert chrome["memoryMetric"] == "physical_footprint"
    assert chrome["memoryDeduplicated"] is True
    assert chrome["memoryPartial"] is False

    solo = groups["proc:90:100.0"]
    assert solo["memoryBytes"] == 60
    assert solo["memoryMetric"] == "physical_footprint"

    # One invocation for the multi-PID family + one batched call for singles.
    assert len(calls) == 2
    assert sum("10" in call and "11" in call for call in calls) == 1
    # No synthetic metric name may appear.
    assert all(group["memoryMetric"] != "pss" for group in groups.values())
    assert "pss" not in repr(groups).lower()


def test_membership_change_invalidates_cached_footprint(tmp_path, monkeypatch):
    service = _service(tmp_path)
    rows_v1 = [
        _row(10, name="Google Chrome", exe=CHROME, rss=500),
        _row(11, name="Helper", exe=HELPER, ppid=10, rss=400),
    ]
    service.rows = {row["key"]: row for row in rows_v1}
    _footprint_calls(service, monkeypatch, {10: 500, 11: 400, 12: 200}, summary=650)
    service.refresh_footprints(force=True)

    # A new child joins: the signature changes and the old value must not apply.
    rows_v2 = [*rows_v1, _row(12, name="Helper2", exe=HELPER, ppid=10, rss=200)]
    service.rows = {row["key"]: row for row in rows_v2}
    group = service.groups_for(rows_v2)[0]
    assert group["memoryMetric"] == "rss"
    assert group["memoryBytes"] == group["rssBytes"] == 1100

    service.refresh_footprints(force=True)
    group = service.groups_for(rows_v2)[0]
    assert group["memoryMetric"] == "physical_footprint"
    assert group["memoryBytes"] == 650
    assert group["memoryPartial"] is False


def test_footprint_failure_falls_back_to_labeled_rss(tmp_path, monkeypatch):
    service = _service(tmp_path)
    rows = [_row(10, exe=CHROME, rss=500), _row(11, exe=HELPER, ppid=10, rss=400)]
    service.rows = {row["key"]: row for row in rows}
    monkeypatch.setattr(memory, "run_command",
                        lambda *a, **kw: CommandResult(1, "", "denied"))
    service.refresh_footprints(force=True)
    group = service.groups_for(rows)[0]
    assert group["memoryMetric"] == "rss"
    assert group["memoryBytes"] == 900
    assert group["memoryDeduplicated"] is False


def test_missing_footprint_binary_never_spawns(tmp_path, monkeypatch):
    service = _service(tmp_path)
    service.footprint_available = False
    rows = [_row(10, exe=CHROME, rss=500)]
    service.rows = {row["key"]: row for row in rows}
    calls = []
    monkeypatch.setattr(memory, "run_command", lambda *a, **kw: calls.append(a) or CommandResult(0, ""))
    service.refresh_footprints(force=True)
    assert calls == []
    assert service.groups_for(rows)[0]["memoryMetric"] == "rss"


def test_other_user_processes_are_never_measured(tmp_path, monkeypatch):
    service = _service(tmp_path)
    rows = [
        _row(10, exe=CHROME, rss=500),
        _row(11, exe=HELPER, ppid=10, rss=400, protected="other-user"),
    ]
    service.rows = {row["key"]: row for row in rows}
    calls = _footprint_calls(service, monkeypatch, {10: 500}, summary=500)
    service.refresh_footprints(force=True)
    assert all("11" not in call for call in calls)
    group = service.groups_for(rows)[0]
    # Partial measurement is honestly reported, not silently treated as complete.
    assert group["memoryPartial"] is True
    assert group["memoryMetric"] == "physical_footprint"
    # And it must NOT feed growth history — a partial footprint would fake a
    # memory drop for the unmeasured member.
    assert not service.group_histories.get("app:/Applications/Google Chrome.app")


def test_full_coverage_records_footprint_history(tmp_path, monkeypatch):
    service = _service(tmp_path)
    rows = [_row(10, exe=CHROME, rss=500), _row(11, exe=HELPER, ppid=10, rss=400)]
    service.rows = {row["key"]: row for row in rows}
    _footprint_calls(service, monkeypatch, {10: 500, 11: 400}, summary=650)
    service.refresh_footprints(force=True)
    history = service.group_histories["app:/Applications/Google Chrome.app"]
    assert len(history) == 1
    _, value, signature = history[0]
    assert value == 650
    assert signature == frozenset(row["key"] for row in rows)
    service.refresh_footprints(force=True)
    assert len(service.group_histories["app:/Applications/Google Chrome.app"]) == 2


def test_singles_batch_is_not_starved_by_multi_groups(tmp_path, monkeypatch):
    """With a crowded multi-group queue the singles batch must still run inside
    the same budgeted pass — otherwise single-process footprint growth never
    reaches readiness."""
    service = _service(tmp_path)
    rows = []
    for i in range(20):  # 20 multi-process app families
        rows.append(_row(100 + i * 2, name=f"App{i}", exe=f"/Applications/App{i}.app/Contents/MacOS/App{i}"))
        rows.append(_row(101 + i * 2, name=f"App{i} Helper", exe=f"/Applications/App{i}.app/Contents/Helper", ppid=100 + i * 2))
    rows.append(_row(999, name="solo", exe="/usr/bin/solo", rss=50))
    service.rows = {row["key"]: row for row in rows}

    clock = [0.0]
    calls = []

    def fake_command(executable, arguments, timeout=120, on_wait=None):
        clock[0] += 4.0  # each invocation burns 4 s of the 12 s budget
        calls.append(list(arguments))
        return CommandResult(0, "proc [999]: 64-bit    Footprint: 60 B (16384 bytes per page)\nSummary Footprint: 700 B")

    monkeypatch.setattr(memory.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(memory, "run_command", fake_command)
    service.refresh_footprints(force=True)
    assert any("999" in call for call in calls), "singles batch starved by multi queue"


def test_footprint_pass_is_batched_not_per_process(tmp_path, monkeypatch):
    service = _service(tmp_path)
    rows = [_row(1000 + i, name=f"p{i}", exe=f"/usr/bin/p{i}", rss=10) for i in range(600)]
    service.rows = {row["key"]: row for row in rows}
    calls = _footprint_calls(service, monkeypatch, {}, summary=None)
    service.refresh_footprints(force=True)
    # 600 singleton groups -> exactly one batched invocation, never 600.
    assert len(calls) == 1


def test_bundle_metadata_is_cached(tmp_path, monkeypatch):
    service = _service(tmp_path)
    reads = []
    original_load = memory.plistlib.load

    def counting_load(handle):
        reads.append(1)
        return original_load(handle)

    monkeypatch.setattr(memory.plistlib, "load", counting_load)
    plist = tmp_path / "X.app" / "Contents" / "Info.plist"
    plist.parent.mkdir(parents=True)
    plist.write_bytes(memory.plistlib.dumps({"CFBundleIdentifier": "dev.test.X", "CFBundleName": "TestX"}))
    for _ in range(3):
        assert service._bundle_metadata(str(tmp_path / "X.app")) == ("TestX", "dev.test.X")
    assert len(reads) == 1


def test_build_groups_scales_to_large_process_counts():
    import time as real_time
    rows = []
    for i in range(600):
        rows.append(_row(2000 + i, name=f"p{i}", exe=f"/usr/bin/p{i}"))
    for i in range(50):  # one app family of 50 helpers
        rows.append(_row(3000 + i, name="Chrome Helper", exe=HELPER, ppid=1))
    start = real_time.monotonic()
    groups = memory.build_groups(rows)
    elapsed = real_time.monotonic() - start
    assert len(groups) == 601
    assert elapsed < 0.5


def test_group_collecting_progress_is_the_average_of_children():
    rows = [
        _row(10, exe=CHROME), _row(11, exe=HELPER, ppid=10), _row(12, exe=GPU, ppid=10),
    ]
    rows[0]["growthWindowElapsedSeconds"] = 60.0
    rows[0]["growthWindowRemainingSeconds"] = 540.0
    rows[0]["growthWindowProgress"] = 0.1
    rows[1]["growthWindowElapsedSeconds"] = 180.0
    rows[1]["growthWindowRemainingSeconds"] = 420.0
    rows[1]["growthWindowProgress"] = 0.3
    rows[2]["growthWindowElapsedSeconds"] = 300.0
    rows[2]["growthWindowRemainingSeconds"] = 300.0
    rows[2]["growthWindowProgress"] = 0.5
    group = memory.build_groups(rows)[0]
    assert group["growthWindowElapsedSeconds"] == 180.0
    assert group["growthWindowRemainingSeconds"] == 420.0
    assert group["growthWindowProgress"] == 0.3


def test_group_collecting_progress_is_absent_without_child_data():
    group = memory.build_groups([_row(10, exe=CHROME), _row(11, exe=HELPER, ppid=10)])[0]
    assert group["growthWindowElapsedSeconds"] is None
    assert group["growthWindowRemainingSeconds"] is None
    assert group["growthWindowProgress"] is None


def _fp_history(service, group_id, signature, samples):
    """Inject measured footprint samples: list of (seconds_ago, bytes)."""
    now = time.monotonic()
    hist = deque(maxlen=memory.GROUP_HISTORY_MAX_SAMPLES)
    for seconds_ago, value in samples:
        hist.append((now - seconds_ago, value, signature))
    service.group_histories[group_id] = hist


def _windowed_rise(base_mb, step_mb, count=10):
    """One sample per minute-bucket covering the growth window, rising steadily."""
    base = base_mb * 2**20
    return [(598 - i * 60, base + i * step_mb * 2**20) for i in range(count)]


def test_footprint_history_flags_compressed_style_growth(tmp_path):
    """The exact blind spot: child RSS flat (compressed pages) but measured
    group footprint rising >256 MB — the group must flag growing."""
    service = _service(tmp_path)
    rows = [_row(10, exe=CHROME, rss=100), _row(11, exe=HELPER, ppid=10, rss=100)]
    signature = frozenset(row["key"] for row in rows)
    _fp_history(service, "app:/Applications/Google Chrome.app", signature,
                _windowed_rise(100, 30))  # +270 MB sustained
    group = service.groups_for(rows)[0]
    assert group["growthMetric"] == "physical_footprint"
    assert group["growing"] is True
    assert group["growthBytes"] > 256 * 2**20
    assert group["allHistoryReady"] is True
    assert group["historyReady"] is True


def test_footprint_history_flat_means_not_growing(tmp_path):
    service = _service(tmp_path)
    rows = [_row(10, exe=CHROME, rss=100), _row(11, exe=HELPER, ppid=10, rss=100)]
    signature = frozenset(row["key"] for row in rows)
    _fp_history(service, "app:/Applications/Google Chrome.app", signature,
                _windowed_rise(500, 0))  # flat 500 MB
    group = service.groups_for(rows)[0]
    assert group["growthMetric"] == "physical_footprint"
    assert group["growing"] is False
    assert group["growthBytes"] == 0
    assert group["allHistoryReady"] is True


def test_footprint_history_never_crosses_membership_boundary(tmp_path):
    """Samples from an older membership must not count toward the trend —
    a member change makes the totals incomparable."""
    service = _service(tmp_path)
    rows = [_row(10, exe=CHROME, rss=100), _row(11, exe=HELPER, ppid=10, rss=100)]
    current = frozenset(row["key"] for row in rows)
    stale = frozenset({rows[0]["key"]})  # the helper had not joined yet
    gid = "app:/Applications/Google Chrome.app"
    now = time.monotonic()
    hist = deque(maxlen=memory.GROUP_HISTORY_MAX_SAMPLES)
    # Old membership: tiny footprint. New membership: flat 500 MB. If the
    # boundary were ignored the delta would look like a +490 MB explosion.
    for i in range(6):
        hist.append((now - 598 - (5 - i) * 20, 10 * 2**20, stale))
    for i in range(10):
        hist.append((now - 598 + i * 60, 500 * 2**20, current))
    service.group_histories[gid] = hist
    group = service.groups_for(rows)[0]
    assert group["growthMetric"] == "physical_footprint"
    assert group["growing"] is False
    assert group["growthBytes"] == 0


def test_short_footprint_history_falls_back_to_rss_growth(tmp_path):
    service = _service(tmp_path)
    rows = [_row(10, exe=CHROME, rss=100), _row(11, exe=HELPER, ppid=10, rss=100)]
    rows[0]["growthBytes"] = 40 * 2**20  # child RSS verdict exists
    signature = frozenset(row["key"] for row in rows)
    _fp_history(service, "app:/Applications/Google Chrome.app", signature,
                [(40, 300 * 2**20), (20, 320 * 2**20)])  # too short for a window
    group = service.groups_for(rows)[0]
    assert group["growthMetric"] == "rss"
    assert group["growthBytes"] == 40 * 2**20
    assert group["growing"] is False


def test_snapshot_payload_is_additive_and_grouped(tmp_path):
    service = _service(tmp_path)
    rows = [_row(10, exe=CHROME, rss=500), _row(11, exe=HELPER, ppid=10, rss=400)]
    service.rows = {row["key"]: row for row in rows}
    payload = service.snapshot()
    assert "processes" in payload and "groups" in payload
    assert len(payload["processes"]) == 2
    group = payload["groups"][0]
    assert group["id"] == "app:/Applications/Google Chrome.app"
    assert group["memoryMetric"] in {"physical_footprint", "rss", "unavailable"}
    assert {row["key"] for row in group["children"]} == {"10:100.0", "11:100.0"}
    # Group payload must be JSON-serializable (no frozensets leak).
    import json
    json.dumps(payload["groups"])
