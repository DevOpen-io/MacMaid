"""Bounded process monitoring and explicitly authorized memory interventions."""
from __future__ import annotations

import copy
import json
import math
import os
import re
import secrets
import statistics
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

from .config import Config
from .review import ReviewItem, ReviewPlan
from .system import run_command

HELPERS = {"dart-analysis", "typescript-server"}
SYSTEM_ROOTS = ("/System/", "/Library/Apple/", "/usr/lib/", "/usr/libexec/", "/usr/sbin/", "/sbin/", "/bin/", "/usr/bin/")


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


def growth(samples: list[tuple[float, int]], now: float) -> dict:
    window = [(stamp, rss) for stamp, rss in samples if stamp >= now - 600]
    if not window or window[0][0] > now - 595:
        return {"growthBytes": None, "growing": False, "historyReady": False}
    medians = []
    for minute in range(10):
        values = [rss for stamp, rss in window if now - 600 + minute * 60 <= stamp < now - 540 + minute * 60]
        if not values:
            return {"growthBytes": None, "growing": False, "historyReady": False}
        medians.append(statistics.median(values))
    delta = window[-1][1] - window[0][1]
    increasing = sum(b > a for a, b in zip(medians, medians[1:]))
    return {"growthBytes": delta, "growing": delta > 256 * 1024**2 and delta > window[0][1] * .25 and increasing >= 7,
            "historyReady": True}


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
        self.events: deque = deque(maxlen=100)
        self.metrics: dict = {}
        self.error = ""
        self.settings_error = ""
        self.last_sample = 0.0
        self.pressure_sampled_at = 0.0
        self.pressure_headroom: float | None = None
        self.settings = self._read_settings()

    def _read_settings(self) -> dict:
        default = {"paused": True, "rules": [], "exclusions": []}
        try:
            self.config._require_owned_regular_file(self.path, allow_missing=True)
            try:
                fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
            except FileNotFoundError:
                self.settings_error = ""
                return default
            with os.fdopen(fd, encoding="utf-8") as handle:
                value = json.load(handle)
            self._validate_settings(value)
            self.settings_error = ""
            return value
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.settings_error = f"Memory rules disabled: {exc}. Restore or remove memory.json, then restart MacMaid."
            return default

    @staticmethod
    def _validate_settings(value: dict) -> None:
        if not isinstance(value, dict) or type(value.get("paused")) is not bool:
            raise ValueError("Invalid memory settings")
        if not isinstance(value.get("rules"), list) or not isinstance(value.get("exclusions"), list):
            raise ValueError("Invalid memory rules or exclusions")
        if len(value["rules"]) > 100 or len(value["exclusions"]) > 1000:
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
            for field, low, high in (("rssBytes", 64 * 1024**2, 1024**4), ("durationSeconds", 30, 3600),
                                     ("pressureBelow", 1, 50), ("lastAttempt", 0, 10**12), ("failures", 0, 100)):
                number = rule.get(field)
                if type(number) not in (int, float) or not math.isfinite(number) or not low <= number <= high:
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

    def shutdown(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=12)

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
            self.stop_event.wait(5)

    def _protected_pids(self) -> set[int]:
        current = psutil.Process()
        return {0, 1, current.pid, *(p.pid for p in current.parents()), *(p.pid for p in current.children(recursive=True))}

    def _describe(self, proc: psutil.Process, protected: set[int]) -> dict:
        with proc.oneshot():
            pid, created = proc.pid, proc.create_time()
            uid = proc.uids()
            exe = proc.exe()
            name = proc.name()
            category, role, entry = classify(exe, proc.cmdline())
            rss = proc.memory_info().rss
            cpu = proc.cpu_times()
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
                "exe": exe, "category": category, "role": role, "entrypoint": entry,
                "rssBytes": rss, "cpuTime": cpu.user + cpu.system, "protected": reason,
                "helper": role in HELPERS and not reason}

    def _sample_pressure_headroom(self, now: float) -> float | None:
        """Read only macOS memory pressure, without unrelated battery/thermal probes."""
        if self.pressure_sampled_at and now - self.pressure_sampled_at < 30:
            return self.pressure_headroom
        result = run_command("/usr/bin/memory_pressure", ["-Q"], timeout=5)
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
            if self.last_sample and now - self.last_sample > 15:
                self.histories.clear()
                self.cpu_previous.clear()
                self.above_since.clear()
            for proc in psutil.process_iter():
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
                                 "exe": "", "category": "all", "role": "application", "entrypoint": "",
                                 "rssBytes": None, "cpuPercent": None, "protected": "unverified-identity",
                                 "helper": False, "growthBytes": None, "growing": False,
                                 "historyReady": False, "forceEligible": False}
                    continue
                key = row["key"]
                history = self.histories.setdefault(key, deque(maxlen=721))
                history.append((now, row["rssBytes"]))
                while history and history[0][0] < now - 3600:
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

    def snapshot(self) -> dict:
        with self.lock:
            rows = [dict(row, forceEligible=key in self.survivors and not row["protected"])
                    for key, row in self.rows.items()]
            return copy.deepcopy({"processes": rows, "metrics": self.metrics,
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
        if not isinstance(keys, list) or not 1 <= len(keys) <= 100 or any(not isinstance(k, str) for k in keys) or len(set(keys)) != len(keys):
            raise ValueError("Select between 1 and 100 distinct processes")
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
            _, alive = psutil.wait_procs([proc for _, proc, _ in pending], timeout=5)
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
                _, row = self._target(body.get("key"))
                if not row["helper"] or body.get("consent") is not True:
                    raise PermissionError("Choose a recognized helper and explicitly accept interruption")
                previous = next((r for r in self.settings["rules"] if (r["exe"], r["role"], r["entrypoint"]) ==
                                 (row["exe"], row["role"], row["entrypoint"])), None)
                rule = {"id": previous["id"] if previous else secrets.token_hex(12), "exe": row["exe"],
                        "entrypoint": row["entrypoint"], "role": row["role"], "consent": True, "enabled": True,
                        "rssBytes": body.get("rssBytes", 2 * 1024**3), "durationSeconds": body.get("durationSeconds", 300),
                        "pressureBelow": body.get("pressureBelow", 15), "lastAttempt": previous["lastAttempt"] if previous else 0,
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
                if now - self.last_sample > 15:
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
                        if now - since < rule["durationSeconds"] or pressure is None or pressure >= rule["pressureBelow"] or wall - rule["lastAttempt"] < 1800:
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
