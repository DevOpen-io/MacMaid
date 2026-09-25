"""Bounded process monitoring and explicitly authorized memory interventions."""
from __future__ import annotations

import copy
import json
import math
import os
import plistlib
import re
import secrets
import statistics
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import psutil

from .config import Config
from .review import ReviewItem, ReviewPlan
from .system import run_command

HELPERS = {"dart-analysis", "typescript-server"}
SYSTEM_ROOTS = ("/System/", "/Library/Apple/", "/usr/lib/", "/usr/libexec/", "/usr/sbin/", "/sbin/", "/bin/", "/usr/bin/")

BYTES_PER_MEBIBYTE = 1024**2
BYTES_PER_GIBIBYTE = 1024**3
SECONDS_PER_MINUTE = 60
SAMPLE_INTERVAL_SECONDS = 5
GROWTH_WINDOW_SECONDS = 10 * SECONDS_PER_MINUTE
GROWTH_WINDOW_TOLERANCE_SECONDS = 5
GROWTH_BUCKET_COUNT = 10
GROWTH_REQUIRED_INCREASING_BUCKETS = 7
GROWTH_MINIMUM_BYTES = 256 * BYTES_PER_MEBIBYTE
GROWTH_MINIMUM_RATIO = 0.25
HISTORY_WINDOW_SECONDS = 60 * SECONDS_PER_MINUTE
MAX_HISTORY_SAMPLES = HISTORY_WINDOW_SECONDS // SAMPLE_INTERVAL_SECONDS + 1
MAX_MEMORY_ACTIONS = 100
MAX_EVENTS = 100
MAX_RULES = 100
MAX_EXCLUSIONS = 1000
MIN_RULE_RSS_BYTES = 64 * BYTES_PER_MEBIBYTE
MAX_RULE_RSS_BYTES = 1024 * BYTES_PER_GIBIBYTE
MIN_RULE_DURATION_SECONDS = 30
MAX_RULE_DURATION_SECONDS = HISTORY_WINDOW_SECONDS
MIN_PRESSURE_HEADROOM = 1
MAX_PRESSURE_HEADROOM = 50
DEFAULT_RULE_RSS_BYTES = 2 * BYTES_PER_GIBIBYTE
DEFAULT_RULE_DURATION_SECONDS = 5 * SECONDS_PER_MINUTE
DEFAULT_RULE_PRESSURE_HEADROOM = 15
PRESSURE_CACHE_SECONDS = 30
STALE_SAMPLE_SECONDS = 3 * SAMPLE_INTERVAL_SECONDS
STOP_WAIT_SECONDS = 5

_PROCESS_ATTRS = ("pid", "create_time", "uids", "exe", "name", "cmdline", "memory_info", "cpu_times")
_SAMPLE_ATTRS = (*_PROCESS_ATTRS, "ppid")
AUTOMATION_COOLDOWN_SECONDS = 30 * SECONDS_PER_MINUTE

# Group memory measurement. /usr/bin/footprint is Apple's entitled diagnostic
# tool: it reports the kernel's physical footprint per process and, when given
# a set of PIDs, de-duplicates shared pages across the whole set. It works
# without root for processes owned by the current user; other users' processes
# fail cleanly and stay on the RSS fallback.
FOOTPRINT_PATH = "/usr/bin/footprint"
FOOTPRINT_INTERVAL_SECONDS = 20
FOOTPRINT_BUDGET_SECONDS = 12
FOOTPRINT_BASE_TIMEOUT_SECONDS = 8.0
FOOTPRINT_PER_PID_TIMEOUT_SECONDS = 0.05
FOOTPRINT_CACHE_MAX_AGE_SECONDS = 3 * FOOTPRINT_INTERVAL_SECONDS
FOOTPRINT_MAX_PIDS = 2000
GROUP_HISTORY_MAX_SAMPLES = 48
MAX_BUNDLE_METADATA = 500
HIGH_MEMORY_GROUP_BYTES = 512 * BYTES_PER_MEBIBYTE

_FOOTPRINT_PROC_RE = re.compile(r"^(?P<name>.*?) \[(?P<pid>\d+)\]:.*?Footprint:\s*(?P<bytes>\d+)\s*B\b", re.MULTILINE)
_FOOTPRINT_SUMMARY_RE = re.compile(r"^Summary Footprint:\s*(?P<bytes>\d+)\s*B\b", re.MULTILINE)


class _FootprintAborted(Exception):
    """Raised inside the subprocess wait callback to cancel a footprint pass."""


def bundle_root(executable: str) -> str | None:
    """Outermost ``*.app`` bundle containing the executable, if any.

    Helper frameworks and nested ``*.app`` helpers still live inside the outer
    application bundle, so the first boundary wins: a Chrome Helper under
    ``Google Chrome.app/Contents/Frameworks/...`` resolves to Google Chrome.
    """
    end = executable.find(".app/")
    if end < 0:
        return None
    return executable[: end + len(".app")]


def parse_footprint_output(text: str) -> tuple[dict[int, int], int | None]:
    """Parse ``footprint -f bytes --noCategories`` stdout.

    Returns ``(per_pid_footprints, deduplicated_total)``. The summary is the
    shared-page-de-duplicated total across every measured PID; per-PID values
    are each process's own physical footprint.
    """
    per_pid = {int(match.group("pid")): int(match.group("bytes")) for match in _FOOTPRINT_PROC_RE.finditer(text)}
    summary = _FOOTPRINT_SUMMARY_RE.search(text)
    return per_pid, (int(summary.group("bytes")) if summary else None)


def _tree_root(row: dict, by_pid: dict[int, dict], bundled_pids: set[int]) -> dict:
    """Nearest same-executable ancestor of a non-bundled process, or itself.

    Tree grouping is deliberately narrow: a child only joins an ancestor when
    the ancestor runs the same executable image. Shells, terminals and
    unrelated parents never absorb their children.
    """
    current = row
    seen = {row["key"]}
    while row.get("exe"):
        parent = by_pid.get(current.get("ppid") or -1)
        if (
            parent is None
            or parent["key"] in seen
            or parent["pid"] in bundled_pids
            or parent.get("exe") != row.get("exe")
        ):
            return current
        seen.add(parent["key"])
        current = parent
    return current


def build_groups(rows: Iterable[dict]) -> list[dict]:
    """Group process rows into logical application/process families.

    Bundle membership is decided only by the executable's own outermost
    ``.app`` path, never by name matching. Group identity stays immutable per
    membership set; stop/review authorization still binds to each member's
    ``pid:create_time`` key.
    """
    members = [row for row in rows if row.get("pid") is not None]
    by_pid: dict[int, dict] = {}
    for row in members:  # first wins on the (rare) reused-pid collision
        by_pid.setdefault(row["pid"], row)
    bundles = {row["key"]: bundle_root(row.get("exe") or "") for row in members}
    bundled_pids = {row["pid"] for row in members if bundles[row["key"]]}

    grouped: dict[str, dict] = {}
    order: list[str] = []
    for row in members:
        bundle = bundles[row["key"]]
        if bundle:
            group_id = f"app:{bundle}"
            root_key = row["key"]
        else:
            root = _tree_root(row, by_pid, bundled_pids)
            group_id = f"proc:{root['key']}"
            root_key = root["key"]
        group = grouped.get(group_id)
        if group is None:
            group = {
                "id": group_id,
                "kind": "application" if bundle else "process",
                "name": Path(bundle).stem if bundle else "",
                "bundlePath": bundle or "",
                "bundleId": "",
                "rootKey": root_key,
                "children": [],
            }
            grouped[group_id] = group
            order.append(group_id)
        group["children"].append(row)
        if not bundle and row["key"] == root_key:
            group["name"] = row.get("name") or str(row["pid"])
    groups = [grouped[group_id] for group_id in order]
    for group in groups:
        children = sorted(group["children"], key=lambda r: (r.get("rssBytes") is None, -(r.get("rssBytes") or 0)))
        group["children"] = children
        group["memberKeys"] = [row["key"] for row in children]
        group["signature"] = frozenset(group["memberKeys"])
        group["processCount"] = len(children)
        group["protectedCount"] = sum(1 for row in children if row.get("protected"))
        group["eligibleCount"] = group["processCount"] - group["protectedCount"]
        group["growingCount"] = sum(1 for row in children if row.get("growing"))
        deltas = [row["growthBytes"] for row in children if isinstance(row.get("growthBytes"), (int, float))]
        group["growthBytes"] = max(deltas) if deltas else None
        group["allHistoryReady"] = all(row.get("historyReady") for row in children)
        for field in ("growthWindowElapsedSeconds", "growthWindowRemainingSeconds", "growthWindowProgress"):
            values = [row[field] for row in children if isinstance(row.get(field), (int, float))]
            group[field] = sum(values) / len(values) if values else None
        rss_values = [row["rssBytes"] for row in children if isinstance(row.get("rssBytes"), (int, float))]
        group["rssBytes"] = sum(rss_values) if rss_values else None
        cpu_values = [row["cpuPercent"] for row in children if isinstance(row.get("cpuPercent"), (int, float))]
        group["cpuPercent"] = sum(cpu_values) if cpu_values else None
        group["developer"] = any(row.get("category") in ("developer", "flutter") for row in children)
        if not group["name"]:
            group["name"] = group["children"][0].get("name") or group["id"]
    return groups


def classify(executable: str, arguments: list[str]) -> tuple[str, str, str]:
    """Return category, role, and an exact helper entrypoint, never raw arguments."""
    name = Path(executable).name
    # Only the interpreter's actual entrypoint may identify a helper. A script
    # mentioned later as an ordinary argument must not grant automation eligibility.
    tail = arguments[1:]
    allowed_flags = {"--disable-dart-dev", "--disable-service-auth-codes"} if name in {"dart", "dartvm", "dartaotruntime"} else {"--inspect", "--inspect-brk"}
    allowed_prefixes = ("--packages=",) if name in {"dart", "dartvm", "dartaotruntime"} else ("--max-old-space-size=", "--inspect=", "--inspect-brk=", "--inspect-port=")
    entry_arg = ""
    for arg in tail:
        if not arg.startswith("-"):
            entry_arg = arg
            break
        if arg not in allowed_flags and not arg.startswith(allowed_prefixes):
            # Unknown or argument-consuming interpreter options cannot identify a helper.
            break
    scripts = [entry_arg] if entry_arg.startswith("/") else []
    if name in {"dart", "dartvm"} and entry_arg == "language-server":
        return "flutter", "dart-analysis", executable
    if name in {"dart", "dartvm", "dartaotruntime"}:
        entry = next((arg for arg in scripts if Path(arg).name in {
            "analysis_server.dart.snapshot", "analysis_server_aot.dart.snapshot",
        }), "")
        if entry:
            return "flutter", "dart-analysis", entry
        return "flutter", "dart-tool", ""
    if name in {"flutter", "flutter_tester", "dart_mcp_server"}:
        return "flutter", "flutter-tool", ""
    if name == "node":
        entry = next((arg for arg in scripts if Path(arg).name == "tsserver.js"
                      and Path(arg).parent.name == "lib"
                      and Path(arg).parent.parent.name == "typescript"), "")
        if entry:
            return "developer", "typescript-server", entry
    if name in {"node", "java", "javac", "gradle", "adb", "emulator", "swift", "swiftc",
                "clang", "clang++", "rustc", "cargo", "go", "ruby", "xcodebuild", "Simulator"} or name.startswith("python"):
        return "developer", "development-tool", ""
    return "all", "application", ""


def growth_window_progress(window: list[tuple[float, int]], now: float) -> dict[str, float]:
    """Progress metadata for the growth collection window.

    Derived from the exact same in-window sample set the readiness check
    inspects: ``window[0]`` is the oldest sample inside ``GROWTH_WINDOW_SECONDS``,
    so UI progress can never claim more history than the detector has.
    """
    elapsed = max(0.0, now - window[0][0]) if window else 0.0
    return {
        "growthWindowElapsedSeconds": elapsed,
        "growthWindowRemainingSeconds": max(0.0, float(GROWTH_WINDOW_SECONDS) - elapsed),
        "growthWindowProgress": min(1.0, elapsed / GROWTH_WINDOW_SECONDS),
    }


def growth(samples: list[tuple[float, int]], now: float, *, min_buckets: int = GROWTH_BUCKET_COUNT) -> dict:
    window = [(stamp, rss) for stamp, rss in samples if stamp >= now - GROWTH_WINDOW_SECONDS]
    progress = growth_window_progress(window, now)
    if not window or window[0][0] > now - (GROWTH_WINDOW_SECONDS - GROWTH_WINDOW_TOLERANCE_SECONDS):
        return {"growthBytes": None, "growing": False, "historyReady": False, **progress}
    medians = []
    for minute in range(GROWTH_BUCKET_COUNT):
        start = now - GROWTH_WINDOW_SECONDS + minute * SECONDS_PER_MINUTE
        values = [rss for stamp, rss in window if start <= stamp < start + SECONDS_PER_MINUTE]
        if not values:
            continue
        medians.append(statistics.median(values))
    if len(medians) < min_buckets:
        return {"growthBytes": None, "growing": False, "historyReady": False, **progress}
    delta = window[-1][1] - window[0][1]
    increasing = sum(b > a for a, b in zip(medians, medians[1:]))
    return {"growthBytes": delta, "growing": delta > GROWTH_MINIMUM_BYTES and delta > window[0][1] * GROWTH_MINIMUM_RATIO and increasing >= GROWTH_REQUIRED_INCREASING_BUCKETS,
            "historyReady": True, **progress}


class MemoryService:
    def __init__(self, config: Config, mutation_lock: Any) -> None:
        self.config = config
        self.mutation_lock = mutation_lock
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.path = config.config_dir / "memory.json"
        self.rows: dict[str, dict] = {}
        self.histories: dict[str, deque] = {}
        self.cpu_previous: dict[str, tuple[float, float]] = {}
        self.above_since: dict[tuple[str, str], float] = {}
        self.survivors: set[str] = set()
        self.events: deque = deque(maxlen=MAX_EVENTS)
        self.metrics: dict = {}
        self.error = ""
        self.settings_error = ""
        self.last_sample = 0.0
        self.pressure_sampled_at = 0.0
        self.pressure_headroom: float | None = None
        self.settings: dict = {"paused": True, "rules": [], "exclusions": []}
        self._settings_signature: tuple[int, int, int, int] | None = None
        # Group memory measurement state. Keyed by member-key signatures so a
        # changed membership can never inherit a stale footprint.
        self.pid_footprints: dict[str, tuple[int, float]] = {}
        self.group_footprints: dict[str, dict] = {}
        # (stamp, bytes, signature) samples — group growth is computed from
        # measured footprint so compressed-memory growth stays visible.
        self.group_histories: dict[str, deque] = {}
        self.footprint_available: bool | None = None
        self.footprint_ran_at = 0.0
        self.footprint_thread: threading.Thread | None = None
        self._bundle_meta: dict[str, tuple[str, str]] = {}
        self.settings = self._read_settings()

    def _read_settings(self) -> dict:
        default = {"paused": True, "rules": [], "exclusions": []}
        try:
            info = self.path.lstat()
        except OSError:
            info = None
        if info is not None and self._settings_signature == (info.st_mtime_ns, info.st_size, info.st_ino, info.st_uid):
            return self.settings
        try:
            self.config._require_owned_regular_file(self.path, allow_missing=True)
            try:
                fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
            except FileNotFoundError:
                self.settings_error = ""
                self._settings_signature = None
                return default
            with os.fdopen(fd, encoding="utf-8") as handle:
                value = json.load(handle)
                opened = os.fstat(handle.fileno())
            self._validate_settings(value)
            self.settings_error = ""
            self._settings_signature = (opened.st_mtime_ns, opened.st_size, opened.st_ino, opened.st_uid)
            return value
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self._settings_signature = None
            self.settings_error = f"Memory rules disabled: {exc}. Restore or remove memory.json, then restart MacMaid."
            return default

    @staticmethod
    def _validate_settings(value: dict) -> None:
        if not isinstance(value, dict) or type(value.get("paused")) is not bool:
            raise ValueError("Invalid memory settings")
        if not isinstance(value.get("rules"), list) or not isinstance(value.get("exclusions"), list):
            raise ValueError("Invalid memory rules or exclusions")
        if len(value["rules"]) > MAX_RULES or len(value["exclusions"]) > MAX_EXCLUSIONS:
            raise ValueError("Too many memory rules or exclusions")
        for path in value["exclusions"]:
            if not isinstance(path, str) or not Path(path).is_absolute() or "\x00" in path:
                raise ValueError("Invalid excluded executable")
        ids = set()
        for rule in value["rules"]:
            if not isinstance(rule, dict) or not isinstance(rule.get("id"), str) or rule["id"] in ids:
                raise ValueError("Invalid rule identity")
            ids.add(rule["id"])
            if rule.get("role") not in HELPERS or rule.get("consent") is not True or type(rule.get("enabled")) is not bool:
                raise ValueError("Unapproved helper rule")
            for field in ("exe", "entrypoint"):
                if not isinstance(rule.get(field), str) or not Path(rule[field]).is_absolute() or "\x00" in rule[field]:
                    raise ValueError("Invalid helper path")
            for field, low, high in (("rssBytes", MIN_RULE_RSS_BYTES, MAX_RULE_RSS_BYTES), ("durationSeconds", MIN_RULE_DURATION_SECONDS, MAX_RULE_DURATION_SECONDS),
                                     ("pressureBelow", MIN_PRESSURE_HEADROOM, MAX_PRESSURE_HEADROOM), ("lastAttempt", 0, 10**12), ("failures", 0, MAX_RULES)):
                number = rule.get(field)
                if (not isinstance(number, (int, float)) or isinstance(number, bool)
                        or not math.isfinite(number) or not low <= number <= high):
                    raise ValueError(f"Invalid {field}")

    def _save_settings(self) -> None:
        if self.settings_error:
            raise PermissionError(self.settings_error)
        self._validate_settings(self.settings)
        self.config._require_owned_regular_file(self.path, allow_missing=True)
        temporary = self.path.with_name(f".memory.{secrets.token_hex(8)}.tmp")
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.settings, handle)
                handle.flush()
                os.fsync(handle.fileno())
            self.config._require_owned_regular_file(self.path, allow_missing=True)
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def start(self) -> None:
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, name="macmaid-memory", daemon=True)
            self.thread.start()
        if self.footprint_thread is None:
            self.footprint_thread = threading.Thread(target=self._footprint_loop, name="macmaid-footprint", daemon=True)
            self.footprint_thread.start()

    def shutdown(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=12)
        if self.footprint_thread:
            self.footprint_thread.join(timeout=12)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.sample()
                if not self.stop_event.is_set():
                    self.automate()
            except (OSError, ValueError, psutil.Error) as exc:
                with self.lock:
                    self.error = f"Memory monitoring unavailable: {exc}"
                    self.above_since.clear()
            self.stop_event.wait(SAMPLE_INTERVAL_SECONDS)

    def _protected_pids(self) -> set[int]:
        current = psutil.Process()
        return {0, 1, current.pid, *(p.pid for p in current.parents()), *(p.pid for p in current.children(recursive=True))}

    def _describe(self, proc: psutil.Process, protected: set[int]) -> dict:
        # process_iter(attrs=...) pre-populates proc.info in one pass; a bare
        # psutil.Process has no .info attribute at all (AttributeError), so the
        # fallback must use getattr rather than `proc.info or ...`.
        info = getattr(proc, "info", None) or proc.as_dict(attrs=list(_SAMPLE_ATTRS), ad_value=None)
        if any(info.get(key) is None for key in _PROCESS_ATTRS):
            raise psutil.AccessDenied(proc.pid)
        pid, created = proc.pid, info["create_time"]
        uid = info["uids"]
        exe, name = info["exe"], info["name"]
        category, role, entry = classify(exe, info["cmdline"])
        rss = info["memory_info"].rss
        cpu = info["cpu_times"]
        reason = ""
        if uid.real != os.getuid() or uid.effective != os.getuid():
            reason = "other-user"
        elif pid in protected:
            reason = "macmaid-or-ancestor"
        elif not exe or not Path(exe).is_absolute():
            reason = "unverified-identity"
        elif exe.startswith(SYSTEM_ROOTS):
            reason = "system-process"
        elif exe in self.settings["exclusions"]:
            reason = "excluded"
        return {"key": f"{pid}:{created}", "pid": pid, "created": created, "name": name,
                "exe": exe, "ppid": info.get("ppid"), "category": category, "role": role, "entrypoint": entry,
                "rssBytes": rss, "cpuTime": cpu.user + cpu.system, "protected": reason,
                "helper": role in HELPERS and not reason}

    def _sample_pressure_headroom(self, now: float) -> float | None:
        """Read only macOS memory pressure, without unrelated battery/thermal probes."""
        if self.pressure_sampled_at and now - self.pressure_sampled_at < PRESSURE_CACHE_SECONDS:
            return self.pressure_headroom
        result = run_command("/usr/bin/memory_pressure", ["-Q"], timeout=STOP_WAIT_SECONDS)
        match = re.search(r"System-wide memory free percentage:\s*(\d+(?:\.\d+)?)%", result.stdout)
        self.pressure_headroom = (
            min(100.0, max(0.0, float(match.group(1))))
            if result.succeeded and match else None
        )
        self.pressure_sampled_at = now
        return self.pressure_headroom

    def sample(self) -> None:
        now = time.monotonic()
        protected = self._protected_pids()
        rows = {}
        with self.lock:
            self.settings = self._read_settings()
            if self.last_sample and now - self.last_sample > STALE_SAMPLE_SECONDS:
                self.histories.clear()
                self.cpu_previous.clear()
                self.above_since.clear()
            for proc in psutil.process_iter(attrs=list(_SAMPLE_ATTRS), ad_value=None):
                try:
                    row = self._describe(proc, protected)
                except psutil.NoSuchProcess:
                    continue
                except (OSError, psutil.AccessDenied):
                    # Show inaccessible processes without inventing an actionable identity.
                    key = f"{proc.pid}:unavailable"
                    try:
                        name = proc.name()
                    except (OSError, psutil.Error):
                        name = str(proc.pid)
                    rows[key] = {"key": key, "pid": proc.pid, "created": None, "name": name,
                                 "exe": "", "ppid": None, "category": "all", "role": "application", "entrypoint": "",
                                 "rssBytes": None, "cpuPercent": None, "protected": "unverified-identity",
                                 "helper": False, "growthBytes": None, "growing": False,
                                 "historyReady": False, "forceEligible": False,
                                 "growthWindowElapsedSeconds": None,
                                 "growthWindowRemainingSeconds": None,
                                 "growthWindowProgress": None}
                    continue
                key = row["key"]
                history = self.histories.setdefault(key, deque(maxlen=MAX_HISTORY_SAMPLES))
                history.append((now, row["rssBytes"]))
                while history and history[0][0] < now - HISTORY_WINDOW_SECONDS:
                    history.popleft()
                previous = self.cpu_previous.get(key)
                row["cpuPercent"] = max(0, (row["cpuTime"] - previous[1]) / (now - previous[0]) * 100) if previous and now > previous[0] else 0
                self.cpu_previous[key] = (now, row.pop("cpuTime"))
                row.update(growth(list(history), now))
                row["forceEligible"] = key in self.survivors and not row["protected"]
                rows[key] = row
            self.rows = rows
            self.histories = {key: value for key, value in self.histories.items() if key in rows}
            self.cpu_previous = {key: value for key, value in self.cpu_previous.items() if key in rows}
            self.survivors.intersection_update(rows)
            self.last_sample = now
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        pressure = self._sample_pressure_headroom(now)
        with self.lock:
            self.metrics = {"used": memory.used, "total": memory.total, "available": memory.available,
                            "swap": swap.used, "pressureHeadroom": pressure, "measuredAt": time.time()}
            self.error = ""

    def _bundle_metadata(self, bundle_path: str) -> tuple[str, str]:
        """Cached (display name, bundle id) for an .app path; never raises."""
        cached = self._bundle_meta.get(bundle_path)
        if cached is not None:
            return cached
        name, bundle_id = Path(bundle_path).stem, ""
        try:
            with (Path(bundle_path) / "Contents/Info.plist").open("rb") as handle:
                info = plistlib.load(handle)
            bundle_id = str(info.get("CFBundleIdentifier", ""))
            name = str(info.get("CFBundleDisplayName") or info.get("CFBundleName") or name)
        except (OSError, ValueError, TypeError):
            pass
        if len(self._bundle_meta) < MAX_BUNDLE_METADATA:
            self._bundle_meta[bundle_path] = (name, bundle_id)
        return name, bundle_id

    def _measure_pids(self, pids: list[int]) -> tuple[dict[int, int], int | None]:
        """One footprint invocation for a PID set; returns per-PID bytes + deduped total.

        Never raises: missing binary, vanished PIDs, denied targets and
        timeouts all collapse to empty results.
        """
        if not pids:
            return {}, None
        timeout = min(60.0, FOOTPRINT_BASE_TIMEOUT_SECONDS + len(pids) * FOOTPRINT_PER_PID_TIMEOUT_SECONDS)

        def still_running() -> None:
            if self.stop_event.is_set():
                raise _FootprintAborted()

        try:
            result = run_command(
                FOOTPRINT_PATH,
                ["-f", "bytes", "--noCategories", *(str(pid) for pid in pids[:FOOTPRINT_MAX_PIDS])],
                timeout=timeout, on_wait=still_running,
            )
        except _FootprintAborted:
            return {}, None
        if not result.succeeded:
            return {}, None
        return parse_footprint_output(result.stdout)

    def _footprint_loop(self) -> None:
        """Slow-cadence group measurement; never blocks the 5s sampler."""
        while not self.stop_event.is_set():
            try:
                self.refresh_footprints()
            except Exception:  # measurement is best-effort; sampling must continue
                pass
            self.stop_event.wait(FOOTPRINT_INTERVAL_SECONDS)

    def _measurable(self, row: dict) -> bool:
        """footprint(1) can only inspect same-UID, identified processes."""
        return row.get("pid") is not None and row.get("rssBytes") is not None and row.get("protected") != "other-user"

    def refresh_footprints(self, *, force: bool = False) -> None:
        """Measure group physical footprints via footprint(1), time-boxed.

        Multi-process groups get their own invocation so the shared pages
        between members are de-duplicated. Single-process groups share one
        batched call — their per-PID footprint is already the exact group
        footprint. Stalest groups are measured first and the pass stops at
        FOOTPRINT_BUDGET_SECONDS; leftovers keep their previous values.
        """
        now = time.monotonic()
        if not force and self.footprint_ran_at and now - self.footprint_ran_at < FOOTPRINT_INTERVAL_SECONDS:
            return
        if self.footprint_available is None:
            self.footprint_available = Path(FOOTPRINT_PATH).is_file()
        if not self.footprint_available:
            self.footprint_ran_at = now
            return
        with self.lock:
            groups = build_groups(self.rows.values())
        if not groups:
            return
        deadline = now + FOOTPRINT_BUDGET_SECONDS
        multi = sorted((g for g in groups if g["processCount"] > 1),
                       key=lambda g: self.group_footprints.get(g["id"], {}).get("at", 0.0))
        singles = [g["children"][0] for g in groups if g["processCount"] == 1 and self._measurable(g["children"][0])]
        single_group_ids = {g["children"][0]["key"]: g["id"] for g in groups if g["processCount"] == 1}
        sampled_at = time.monotonic()
        # One batched call measures every single-process group. It competes in
        # the same stalest-first queue as multi groups — otherwise a crowded
        # system starves it of the per-minute samples growth detection needs.
        singles_stale = min((self.pid_footprints.get(row["key"], (0, 0.0))[1] for row in singles), default=0.0)
        singles_pending = bool(singles)
        for group in multi:
            if self.stop_event.is_set() or time.monotonic() >= deadline:
                break
            group_stale = self.group_footprints.get(group["id"], {}).get("at", 0.0)
            if singles_pending and singles_stale <= group_stale:
                self._measure_singles(singles, single_group_ids, sampled_at)
                singles_pending = False
            pids = [row["pid"] for row in group["children"] if self._measurable(row)]
            if not pids:
                continue
            per_pid, summary = self._measure_pids(pids)
            if summary is None:
                continue
            stamp = time.monotonic()
            covered = frozenset(row["key"] for row in group["children"] if self._measurable(row))
            with self.lock:
                self.group_footprints[group["id"]] = {
                    "signature": group["signature"], "bytes": summary, "at": stamp,
                    "covered": covered,
                }
                for row in group["children"]:
                    if row["pid"] in per_pid:
                        self.pid_footprints[row["key"]] = (per_pid[row["pid"]], stamp)
                # History only tracks fully-covered measurements — a partial
                # footprint would fake a memory drop for missing members.
                if covered == group["signature"]:
                    self.group_histories.setdefault(
                        group["id"], deque(maxlen=GROUP_HISTORY_MAX_SAMPLES)
                    ).append((sampled_at, summary, group["signature"]))
        if singles_pending and not self.stop_event.is_set() and time.monotonic() < deadline:
            self._measure_singles(singles, single_group_ids, sampled_at)
        with self.lock:
            live = {group["id"] for group in groups}
            self.group_histories = {gid: hist for gid, hist in self.group_histories.items() if gid in live}
        self.footprint_ran_at = time.monotonic()

    def _measure_singles(self, singles: list[dict], single_group_ids: dict[str, str], sampled_at: float) -> None:
        """One batched footprint call for every single-process group."""
        per_pid, _ = self._measure_pids([row["pid"] for row in singles])
        stamp = time.monotonic()
        with self.lock:
            for row in singles:
                if row["pid"] in per_pid:
                    self.pid_footprints[row["key"]] = (per_pid[row["pid"]], stamp)
                    group_id = single_group_ids.get(row["key"])
                    if group_id is not None:
                        self.group_histories.setdefault(
                            group_id, deque(maxlen=GROUP_HISTORY_MAX_SAMPLES)
                        ).append((sampled_at, per_pid[row["pid"]], frozenset({row["key"]})))

    def groups_for(self, rows: Iterable[dict]) -> list[dict]:
        """Build groups and overlay the latest honest memory metric per group.

        ``memoryMetric`` is ``physical_footprint`` only when footprint(1)
        actually measured this exact membership; otherwise the group reports
        combined RSS. A membership change invalidates the cached footprint via
        the signature check — a stale value is never carried to a new family.
        """
        now = time.monotonic()
        groups = build_groups(rows)
        for group in groups:
            entry = self.group_footprints.get(group["id"])
            if (
                entry is not None
                and entry["signature"] == group["signature"]
                and now - entry["at"] < FOOTPRINT_CACHE_MAX_AGE_SECONDS
            ):
                group["memoryBytes"] = entry["bytes"]
                group["memoryMetric"] = "physical_footprint"
                group["memoryDeduplicated"] = group["processCount"] > 1
                group["memoryPartial"] = entry.get("covered", group["signature"]) != group["signature"]
                group["memoryMeasuredAt"] = entry["at"]
            elif (
                group["processCount"] == 1
                and (pid_entry := self.pid_footprints.get(group["memberKeys"][0])) is not None
                and now - pid_entry[1] < FOOTPRINT_CACHE_MAX_AGE_SECONDS
            ):
                group["memoryBytes"] = pid_entry[0]
                group["memoryMetric"] = "physical_footprint"
                group["memoryDeduplicated"] = False
                group["memoryPartial"] = False
                group["memoryMeasuredAt"] = pid_entry[1]
            else:
                group["memoryBytes"] = group["rssBytes"]
                group["memoryMetric"] = "rss" if group["rssBytes"] is not None else "unavailable"
                group["memoryDeduplicated"] = False
                group["memoryPartial"] = False
                group["memoryMeasuredAt"] = None
            group["highMemory"] = bool(group["memoryBytes"] and group["memoryBytes"] >= HIGH_MEMORY_GROUP_BYTES)
            fp_growth = self._group_footprint_growth(group)
            if fp_growth is not None:
                group["growthBytes"] = fp_growth["growthBytes"]
                group["growing"] = fp_growth["growing"]
                group["growthMetric"] = "physical_footprint"
                group["allHistoryReady"] = True
                for field in ("growthWindowElapsedSeconds", "growthWindowRemainingSeconds", "growthWindowProgress"):
                    group[field] = fp_growth[field]
            else:
                group["growing"] = group["growingCount"] > 0
                group["growthMetric"] = "rss" if group["growthBytes"] is not None else None
            group["historyReady"] = group["allHistoryReady"]
            if group["kind"] == "application":
                name, bundle_id = self._bundle_metadata(group["bundlePath"])
                group["name"], group["bundleId"] = name, bundle_id
            group["signature"] = sorted(group["memberKeys"])
        return groups

    def _group_footprint_growth(self, group: dict) -> dict | None:
        """Growth verdict from measured footprint history, if the window is covered.

        Only the contiguous trailing run of samples matching the *current*
        membership signature is comparable — a member join/leave changes what
        the total means, so older samples can never count toward the trend.
        """
        with self.lock:
            history = list(self.group_histories.get(group["id"]) or ())
        run: list[tuple[float, int]] = []
        for stamp, value, signature in reversed(history):
            if signature != group["signature"]:
                break
            run.append((stamp, value))
        if len(run) < 2:
            return None
        # Footprint cadence (~20 s plus rotation) is coarser than the 5 s RSS
        # sampler; an occasional empty minute bucket must not stall readiness.
        result = growth(list(reversed(run)), time.monotonic(), min_buckets=8)
        return result if result["historyReady"] else None

    def snapshot(self) -> dict:
        with self.lock:
            now = time.monotonic()
            footprints = {key: value for key, (value, stamp) in self.pid_footprints.items()
                          if now - stamp < FOOTPRINT_CACHE_MAX_AGE_SECONDS}
            rows = [dict(row, forceEligible=key in self.survivors and not row["protected"],
                         footprintBytes=footprints.get(key))
                    for key, row in self.rows.items()]
            groups = self.groups_for(rows)
            return copy.deepcopy({"processes": rows, "groups": groups, "metrics": self.metrics,
                                  "settings": self.settings, "events": list(self.events),
                                  "error": self.error or self.settings_error})

    def history(self, key: str) -> dict:
        with self.lock:
            now = time.monotonic()
            return {"samples": [{"secondsAgo": max(0, now - stamp), "rssBytes": rss}
                                for stamp, rss in self.histories.get(key, ())]}

    def _target(self, key: str) -> tuple[psutil.Process, dict]:
        if os.geteuid() == 0:
            raise PermissionError("Memory actions must never run as root")
        if not isinstance(key, str) or key not in self.rows:
            raise ValueError("Process is no longer in the current snapshot")
        original = self.rows[key]
        proc = psutil.Process(original["pid"])
        row = self._describe(proc, self._protected_pids())
        if row["key"] != key or row["exe"] != original["exe"] or row["entrypoint"] != original["entrypoint"]:
            raise PermissionError("Process identity changed; refresh and review again")
        if row["protected"]:
            raise PermissionError(f"Protected process: {row['protected']}")
        self.config.require_unprotected(Path(row["exe"]))
        if row["entrypoint"]:
            self.config.require_unprotected(Path(row["entrypoint"]))
        return proc, row

    def review(self, keys: list[str], force: bool = False) -> ReviewPlan:
        if not isinstance(keys, list) or not 1 <= len(keys) <= MAX_MEMORY_ACTIONS or any(not isinstance(k, str) for k in keys) or len(set(keys)) != len(keys):
            raise ValueError(f"Select between 1 and {MAX_MEMORY_ACTIONS} distinct processes")
        with self.lock:
            self.settings = self._read_settings()
            if self.settings_error:
                raise PermissionError(self.settings_error)
            items = []
            for key in sorted(keys):
                _, row = self._target(key)
                if force and key not in self.survivors:
                    raise PermissionError("Force Stop requires a previous normal stop attempt")
                items.append(ReviewItem(key, row["name"], f"{row['exe']} {row['entrypoint']} (PID {key})", "Force Stop" if force else "Stop",
                                        "MANUAL", "May interrupt work or lose unsaved changes."))
            return ReviewPlan("Force Stop processes" if force else "Stop processes", tuple(items),
                              "Only the listed processes will receive SIGKILL." if force else "Only the listed processes will receive SIGTERM. Applications may lose unsaved work.",
                              "RSS includes shared memory and is not a reclaim estimate. No applications will be restarted.")

    def _audit(self, event: dict) -> None:
        event = dict(event, service="memory", time=time.time(),
                     timestamp=datetime.now(timezone.utc).isoformat(), recordType="memory",
                     label=event.get("name", event.get("key", "Process")), result=event["outcome"],
                     restorable=False)
        path = self.config.operation_log
        self.config._require_owned_regular_file(path, allow_missing=True)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")
        self.events.appendleft(event)

    def stop(self, keys: list[str], *, force: bool = False, automatic: bool = False, rule_id: str | None = None) -> dict:
        # Caller holds the shared mutation lock; each identity is checked again at signal time.
        outcomes = []
        before = psutil.virtual_memory().available
        pending = []
        with self.lock:
            self.settings = self._read_settings()
            if self.settings_error:
                raise PermissionError(self.settings_error)
            for key in keys:
                try:
                    proc, row = self._target(key)
                    if automatic:
                        rule = next((r for r in self.settings["rules"] if r["id"] == rule_id), None)
                        pressure = self.metrics.get("pressureHeadroom")
                        if (self.settings["paused"] or not rule or not rule["enabled"]
                                or self.stop_event.is_set() or not row["helper"]
                                or (row["exe"], row["role"], row["entrypoint"]) != (rule["exe"], rule["role"], rule["entrypoint"])
                                or row["rssBytes"] <= rule["rssBytes"] or pressure is None
                                or pressure >= rule["pressureBelow"]):
                            raise PermissionError("Automatic rule no longer authorizes this process")
                    if force and (automatic or key not in self.survivors):
                        raise PermissionError("Force Stop is not authorized")
                    self._audit({"key": key, "name": row["name"], "action": "force-stop" if force else "stop",
                                 "automatic": automatic, "outcome": "requested"})
                    if force:
                        proc.kill()
                    else:
                        proc.terminate()
                    pending.append((key, proc, row["name"]))
                except (OSError, ValueError, psutil.Error) as exc:
                    outcomes.append({"key": key, "outcome": "skipped", "detail": str(exc)})
            _, alive = psutil.wait_procs([proc for _, proc, _ in pending], timeout=STOP_WAIT_SECONDS)
            for key, proc, name in pending:
                outcome = "still-running" if proc in alive else "exited"
                if outcome == "still-running" and not force:
                    self.survivors.add(key)
                elif outcome == "exited":
                    self.survivors.discard(key)
                outcomes.append({"key": key, "name": name, "outcome": outcome})
            for result in outcomes:
                self._audit(dict(result, automatic=automatic, action="force-stop" if force else "stop"))
        after = psutil.virtual_memory().available
        return {"outcomes": outcomes, "observedAvailableDelta": after - before,
                "caveat": "System-wide change; not attributable solely to stopped processes."}

    def configure(self, body: dict) -> dict:
        with self.lock:
            self.settings = self._read_settings()
            if self.settings_error:
                raise PermissionError(self.settings_error)
            op = body.get("operation")
            if op == "pause" and type(body.get("paused")) is bool:
                self.settings["paused"] = body["paused"]
            elif op == "exclude":
                key = body.get("key")
                if not isinstance(key, str) or key not in self.rows or not self.rows[key]["exe"]:
                    raise ValueError("Choose a current process")
                exe = self.rows[key]["exe"]
                self.settings["exclusions"] = sorted(set([*self.settings["exclusions"], exe]))
            elif op == "unexclude":
                self.settings["exclusions"] = [p for p in self.settings["exclusions"] if p != body.get("exe")]
            elif op == "delete-rule":
                self.settings["rules"] = [r for r in self.settings["rules"] if r["id"] != body.get("id")]
            elif op == "rule":
                key = body.get("key")
                if not isinstance(key, str):
                    raise ValueError("Choose a current process")
                _, row = self._target(key)
                if not row["helper"] or body.get("consent") is not True:
                    raise PermissionError("Choose a recognized helper and explicitly accept interruption")
                previous = next((r for r in self.settings["rules"] if (r["exe"], r["role"], r["entrypoint"]) ==
                                 (row["exe"], row["role"], row["entrypoint"])), None)
                rule = {"id": previous["id"] if previous else secrets.token_hex(12), "exe": row["exe"],
                        "entrypoint": row["entrypoint"], "role": row["role"], "consent": True, "enabled": True,
                        "rssBytes": body.get("rssBytes", DEFAULT_RULE_RSS_BYTES), "durationSeconds": body.get("durationSeconds", DEFAULT_RULE_DURATION_SECONDS),
                        "pressureBelow": body.get("pressureBelow", DEFAULT_RULE_PRESSURE_HEADROOM), "lastAttempt": previous["lastAttempt"] if previous else 0,
                        "failures": 0}
                self.settings["rules"] = [r for r in self.settings["rules"] if r["id"] != rule["id"]] + [rule]
            else:
                raise ValueError("Invalid memory settings operation")
            self._save_settings()
            self.above_since.clear()
            return {"settings": copy.deepcopy(self.settings)}

    def automate(self) -> None:
        if not self.mutation_lock.acquire(blocking=False):
            return
        try:
            with self.lock:
                self.settings = self._read_settings()
                if self.settings_error or self.settings["paused"] or self.error or self.stop_event.is_set():
                    self.above_since.clear()
                    return
                now, wall = time.monotonic(), time.time()
                if now - self.last_sample > STALE_SAMPLE_SECONDS:
                    self.above_since.clear()
                    return
                pressure = self.metrics.get("pressureHeadroom")
                eligible = set()
                for rule in self.settings["rules"]:
                    if not rule["enabled"]:
                        continue
                    for key, row in self.rows.items():
                        pair = (rule["id"], key)
                        if row["protected"] or (row["exe"], row["role"], row["entrypoint"]) != (rule["exe"], rule["role"], rule["entrypoint"]):
                            continue
                        if row["rssBytes"] <= rule["rssBytes"]:
                            continue
                        eligible.add(pair)
                        since = self.above_since.setdefault(pair, now)
                        if now - since < rule["durationSeconds"] or pressure is None or pressure >= rule["pressureBelow"] or wall - rule["lastAttempt"] < AUTOMATION_COOLDOWN_SECONDS:
                            continue
                        # Recheck live RSS and identity, then persist cooldown before sending any signal.
                        rule["lastAttempt"] = wall
                        self._save_settings()
                        result = self.stop([key], automatic=True, rule_id=rule["id"])
                        rule = next(r for r in self.settings["rules"] if r["id"] == pair[0])
                        rule["failures"] = 0 if result["outcomes"][0]["outcome"] == "exited" else rule["failures"] + 1
                        if rule["failures"] >= 2:
                            rule["enabled"] = False
                        self._save_settings()
                        self.above_since.pop(pair, None)
                        return
                self.above_since = {pair: stamp for pair, stamp in self.above_since.items() if pair in eligible}
        finally:
            self.mutation_lock.release()
