from __future__ import annotations

import json
import os
import platform
import plistlib
import re
import shutil
import socket
import sys
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import psutil

from .cancellation import CancellationToken
from .cleaner import Cleaner
from .config import Config
from .models import ActionType, CleanupAction, CleanupCategory, CleanupItem, RiskLevel
from .reporting import FreeSpaceProbe
from .safety import PathSafety, PathSafetyError
from .system import human_bytes, process_running, run_command, size_of, sizes_of, which


@dataclass(slots=True)
class InstalledApplication:
    name: str
    path: Path
    bundle_id: str
    version: str | None
    bytes: int = 0
    brew_cask: str | None = None

    def web_dict(self) -> dict[str, Any]:
        return {"name": self.name, "path": str(self.path), "bundleId": self.bundle_id, "version": self.version or "", "bytes": self.bytes, "brewCask": self.brew_cask or ""}


@dataclass(slots=True)
class AppComponent:
    label: str
    path: Path
    bytes: int
    risk: str
    selected: bool

    def web_dict(self) -> dict[str, Any]:
        return {"label": self.label, "path": str(self.path), "bytes": self.bytes, "risk": self.risk, "selected": self.selected}


@dataclass(frozen=True, slots=True)
class HealthIndicator:
    id: str
    label: str
    state: str
    value: str
    detail: str
    recommendation: str | None
    measured_at: str

    def web_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "label": self.label, "state": self.state,
            "value": self.value, "detail": self.detail,
            "recommendation": self.recommendation, "measuredAt": self.measured_at,
        }


class ApplicationManager:
    SAFE_SUFFIXES = [
        ("Cache", "Library/Caches/{id}", "safe", True),
        ("Logs", "Library/Logs/{id}", "safe", True),
        ("Saved State", "Library/Saved Application State/{id}.savedState", "safe", True),
        ("Preferences", "Library/Preferences/{id}.plist", "userData", False),
        ("Application Support", "Library/Application Support/{id}", "userData", False),
        ("Container", "Library/Containers/{id}", "userData", False),
        ("WebKit", "Library/WebKit/{id}", "userData", False),
        ("HTTP Storage", "Library/HTTPStorages/{id}", "userData", False),
    ]

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()

    @staticmethod
    def valid_bundle_id(value: str) -> bool:
        parts = value.split(".")
        return len(parts) >= 2 and all(part and part[0].isalnum() and all(ch.isalnum() or ch in "-_" for ch in part) for part in parts)

    def scan(self, cancellation: CancellationToken | None = None) -> list[InstalledApplication]:
        token = cancellation or CancellationToken()
        apps: list[InstalledApplication] = []
        for root in (Path("/Applications"), Path.home() / "Applications"):
            if not root.exists():
                continue
            for directory, names, _ in os.walk(root):
                token.check()
                base = Path(directory)
                if base.suffix == ".app":
                    names[:] = []
                    continue
                app_dirs = [name for name in names if name.endswith(".app")]
                for name in app_dirs:
                    path = base / name
                    info_path = path / "Contents/Info.plist"
                    try:
                        with info_path.open("rb") as handle:
                            info = plistlib.load(handle)
                    except (OSError, plistlib.InvalidFileException):
                        continue
                    bundle_id = str(info.get("CFBundleIdentifier", ""))
                    display = str(info.get("CFBundleDisplayName") or info.get("CFBundleName") or path.stem)
                    version = info.get("CFBundleShortVersionString")
                    apps.append(InstalledApplication(display, path, bundle_id, str(version) if version else None))
                names[:] = [name for name in names if name not in app_dirs]
        paths = (app.path for app in apps)
        measured = sizes_of(paths, cancel=token.check) if cancellation is not None else sizes_of(paths)
        token.check()
        ownership = self._homebrew_ownership(token) if cancellation is not None else self._homebrew_ownership()
        for app in apps:
            app.bytes = measured.get(app.path, 0)
            if app.path.parent == Path("/Applications"):
                app.brew_cask = ownership.get(app.path.name.lower())
        return sorted(apps, key=lambda app: (-app.bytes, app.name.lower()))

    @staticmethod
    def _homebrew_ownership(cancellation: CancellationToken | None = None) -> dict[str, str | None]:
        brew = which("brew")
        if not brew:
            return {}
        if cancellation: cancellation.check()
        result = run_command(brew, ["info", "--json=v2", "--installed"], timeout=30,
                             on_wait=cancellation.check if cancellation else None)
        if not result.succeeded:
            raise PermissionError("Homebrew application ownership could not be determined")
        try:
            casks = json.loads(result.stdout).get("casks", [])
        except (json.JSONDecodeError, AttributeError) as exc:
            raise PermissionError("Invalid Homebrew ownership response") from exc
        candidates: dict[str, set[str]] = {}
        for cask in casks:
            token = cask.get("token")
            if not token:
                continue
            for artifact in cask.get("artifacts", []):
                if not isinstance(artifact, dict) or "app" not in artifact:
                    continue
                declared = artifact["app"] if isinstance(artifact["app"], list) else [artifact["app"]]
                for raw in declared:
                    key = Path(str(raw)).name.lower()
                    if key.endswith(".app"):
                        candidates.setdefault(key, set()).add(str(token))
        if any(len(tokens) != 1 for tokens in candidates.values()):
            raise PermissionError("Ambiguous Homebrew application ownership")
        return {key: next(iter(tokens)) for key, tokens in candidates.items()}

    def components(self, app: InstalledApplication, cancellation: CancellationToken | None = None) -> list[AppComponent]:
        token = cancellation or CancellationToken()
        token.check()
        if not self.valid_bundle_id(app.bundle_id):
            return []
        result = [AppComponent("Application", app.path, app.bytes or size_of(app.path), "safe", True)]
        candidates = []
        for label, suffix, risk, selected in self.SAFE_SUFFIXES:
            path = Path.home() / suffix.format(id=app.bundle_id)
            if path.exists() or path.is_symlink():
                candidates.append((label, path, risk, selected))
        launch_agent = Path.home() / "Library/LaunchAgents" / f"{app.bundle_id}.plist"
        if launch_agent.exists():
            candidates.append(("Launch Agent", launch_agent, "safe", True))
        paths = (path for _, path, _, _ in candidates)
        measured = sizes_of(paths, cancel=token.check) if cancellation is not None else sizes_of(paths)
        result.extend(AppComponent(label, path, measured.get(path, 0), risk, selected) for label, path, risk, selected in candidates)
        return result

    def remove(
        self,
        app: InstalledApplication,
        selected_paths: Iterable[Path],
        progress: Callable[[int, int, Path], None] | None = None,
    ) -> dict[str, Any]:
        if os.geteuid() == 0:
            raise PermissionError("run DeepClean as your normal user")
        try:
            return self._remove_selected(app, set(selected_paths), progress)
        except Exception as exc:
            item = CleanupItem(CleanupCategory.LEFTOVERS, app.name, app.path, app.bytes,
                               RiskLevel.AGGRESSIVE, "Reviewed application removal", CleanupAction(ActionType.COMMAND if app.brew_cask else ActionType.MOVE_TO_TRASH))
            Cleaner(self.config)._log(item, "failed", str(exc))
            raise

    def _remove_selected(self, app: InstalledApplication, selected: set[Path],
                         progress: Callable[[int, int, Path], None] | None) -> dict[str, Any]:
        current = next((item for item in self.scan() if item.path == app.path), None)
        if current is None or current.bundle_id != app.bundle_id or current.brew_cask != app.brew_cask:
            raise PermissionError("application identity changed after review")
        if app.path.is_symlink() or process_running(str(app.path)):
            raise PermissionError("application is a symlink or currently running")
        allowed = {component.path: component for component in self.components(current)}
        if not selected or not selected.issubset(allowed):
            raise PermissionError("unreviewed application component")
        ordered_leftovers = sorted(selected - {app.path}, key=str)
        free_space = FreeSpaceProbe.capture(selected)
        processed = 0
        trash_moved = 0
        unknown = 0
        total = len(ordered_leftovers) + int(app.path in selected)
        progress_index = 0
        if app.path in selected:
            progress_index += 1
            if progress: progress(progress_index, total, app.path)
            self._remove_bundle(current)
            processed += max(0, allowed[app.path].bytes)
            if current.brew_cask:
                unknown += 1
            else:
                trash_moved += max(0, allowed[app.path].bytes)
        moved = []
        for path in ordered_leftovers:
            progress_index += 1
            if progress: progress(progress_index, total, path)
            if not path.exists() and not path.is_symlink():
                continue
            def validate_component(raw: Path) -> Path:
                if raw not in allowed or raw == current.path:
                    raise PathSafetyError("unreviewed application component")
                if process_running(str(current.path)):
                    raise PermissionError("application is currently running")
                return PathSafety(extra_allowed_roots=[raw]).validate_deletion_path(raw)
            destination = Cleaner(self.config).move_reviewed_item_to_trash(path, validate_component, allowed[path].bytes)
            moved.append(str(destination))
            processed += max(0, allowed[path].bytes)
            trash_moved += max(0, allowed[path].bytes)
        observed, notes = free_space.finish()
        duplicates = [str(item.path) for item in self.scan() if item.bundle_id == app.bundle_id]
        Cleaner(self.config).log_space_summary(
            "application_remove_summary", scanned=sum(max(0, allowed[path].bytes) for path in selected),
            processed=processed, reclaimed=0, trash_moved=trash_moved, observed=observed,
            unknown=unknown, notes=notes,
        )
        return {"success": app.path not in selected or not app.path.exists(), "moved": moved, "duplicates": duplicates,
                "processedEstimatedBytes": processed, "estimatedReclaimedBytes": 0,
                "trashMovedEstimatedBytes": trash_moved, "observedFreeBytesDelta": observed,
                "unknownReclaimCount": unknown, "measurementNotes": notes}

    def _validate_bundle(self, app: InstalledApplication) -> Path:
        path = PathSafety._lexical(app.path)
        roots = (Path("/Applications"), Path.home() / "Applications")
        if path.suffix != ".app" or not any(root in path.parents for root in roots):
            raise PathSafetyError("application is outside approved application roots")
        PathSafety._reject_symlink_ancestors(path)
        if path.is_symlink() or not self.valid_bundle_id(app.bundle_id):
            raise PathSafetyError("invalid application identity")
        info_path = path / "Contents/Info.plist"
        PathSafety._reject_symlink_ancestors(info_path)
        if info_path.is_symlink():
            raise PathSafetyError("symlinked application metadata")
        with info_path.open("rb") as handle:
            info = plistlib.load(handle)
        if info.get("CFBundleIdentifier") != app.bundle_id:
            raise PermissionError("application identity changed after review")
        self.config.require_unprotected(path)
        if process_running(str(path)):
            raise PermissionError("application is currently running")
        return path

    def _remove_bundle(self, app: InstalledApplication) -> None:
        if not app.brew_cask:
            Cleaner(self.config).move_reviewed_item_to_trash(app.path, lambda raw: self._validate_bundle(app), app.bytes)
            return
        item = CleanupItem(CleanupCategory.LEFTOVERS, app.name, app.path, app.bytes,
                           RiskLevel.AGGRESSIVE, "Homebrew cask uninstall", CleanupAction(ActionType.COMMAND))
        cleaner = Cleaner(self.config)
        cleaner._ensure_audit_safe()
        self._validate_bundle(app)
        try:
            brew = which("brew")
            if not brew or not re.fullmatch(r"[a-z0-9][a-z0-9+_.@-]*", app.brew_cask):
                raise PermissionError("Homebrew cask manager or identifier unavailable")
            if self._homebrew_ownership().get(app.path.name.lower()) != app.brew_cask:
                raise PermissionError("Homebrew ownership changed")
            # A cask may own other artifacts not covered by the reviewed bundle path.
            if self.config.patterns(strict=True):
                raise PermissionError("Cask-wide whitelist scope cannot be proven; use Homebrew manually")
            self._validate_bundle(app)
            result = run_command(brew, ["uninstall", "--cask", app.brew_cask], timeout=600)
            if not result.succeeded:
                raise RuntimeError(result.stderr or "Homebrew uninstall failed; no filesystem fallback attempted")
            if app.path.exists() or app.path.is_symlink():
                raise RuntimeError("application still exists after uninstall")
        except Exception:
            # ApplicationManager.remove records the single structured failure.
            raise
        cleaner._log(item, "success", None)


@dataclass(slots=True)
class ProjectArtifact:
    project_name: str
    project_path: Path
    artifact_name: str
    path: Path
    bytes: int
    modified: float
    dependency: bool
    selected: bool

    def web_dict(self) -> dict[str, Any]:
        return {"projectName": self.project_name, "projectPath": str(self.project_path), "artifactName": self.artifact_name, "path": str(self.path), "bytes": self.bytes, "modified": self.modified, "dependency": self.dependency, "selected": self.selected}


class ProjectPurgeManager:
    MARKERS = {".git", "package.json", "Cargo.toml", "Package.swift", "pyproject.toml", "go.mod", "Gemfile", "pom.xml", "build.gradle", "build.gradle.kts", "pubspec.yaml", "composer.json"}
    LOCAL = {"target", ".build", "build", "dist", ".next", ".nuxt", ".svelte-kit", ".turbo", ".parcel-cache", ".vite", "coverage", ".dart_tool"}
    DEPENDENCIES = {"node_modules", "Pods", ".venv", "venv"}

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()

    def default_roots(self) -> list[Path]:
        names = ("Projects", "Project", "GitHub", "Developer", "dev", "src", "Work", "work", "Code", "code", "Repos", "repos", "Workspace", "workspace", "orchids-projects")
        return [Path.home() / name for name in names if (Path.home() / name).is_dir()]

    def scan(self, roots: Iterable[Path] | None = None,
             cancellation: CancellationToken | None = None) -> list[ProjectArtifact]:
        token = cancellation or CancellationToken()
        candidates: list[tuple[Path, Path, bool]] = []
        for root in roots or self.default_roots():
            root = Path(root).expanduser().absolute()
            if root.is_symlink() or not root.is_dir() or Path.home() not in root.parents:
                continue
            for directory, names, files in os.walk(root, followlinks=False):
                token.check()
                here = Path(directory)
                if ".git" in names: names.remove(".git")
                for name in list(set(names).intersection(self.LOCAL | self.DEPENDENCIES)):
                    artifact = here / name; project = self._project_root(here, root)
                    if project and not artifact.is_symlink(): candidates.append((project, artifact, name in self.DEPENDENCIES))
                    names.remove(name)
                names[:] = [name for name in names if not name.startswith(".") or name in {".build", ".next", ".nuxt", ".svelte-kit", ".turbo", ".parcel-cache", ".vite", ".venv"}]
        paths = (path for _, path, _ in candidates)
        measured = sizes_of(paths, cancel=token.check) if cancellation is not None else sizes_of(paths)
        result = []
        now = time.time()
        for project, path, dependency in candidates:
            try:
                modified = path.stat().st_mtime
            except OSError:
                continue
            age = (now - modified) / 86400
            result.append(ProjectArtifact(project.name, project, path.name, path, measured.get(path, 0), modified, dependency, age >= (30 if dependency else 7)))
        return sorted(result, key=lambda item: -item.bytes)

    def validate(self, artifact: ProjectArtifact) -> bool:
        path = artifact.path
        try:
            PathSafety.validate_analyzer_candidate(path)
            PathSafety._lexical(artifact.project_path)
        except (OSError, PathSafetyError):
            return False
        if not path.exists() or path.is_symlink() or path.name not in self.LOCAL | self.DEPENDENCIES:
            return False
        if Path.home() not in path.absolute().parents or artifact.project_path not in path.parents: return False
        try:
            if path.stat().st_uid != os.getuid(): return False
            PathSafety._reject_symlink_ancestors(path)
        except (OSError, PathSafetyError): return False
        return self._project_root(path.parent, artifact.project_path) == artifact.project_path

    def _project_root(self, start: Path, boundary: Path) -> Path | None:
        current = start.absolute(); boundary = boundary.absolute()
        while current == boundary or boundary in current.parents:
            if any((current / marker).exists() for marker in self.MARKERS): return current
            if current == boundary: break
            current = current.parent
        return None

    def purge(
        self,
        artifacts: Iterable[ProjectArtifact],
        progress: Callable[[int, int, Path], None] | None = None,
    ) -> dict[str, Any]:
        if os.geteuid() == 0:
            raise PermissionError("run DeepClean as your normal user")
        targets = list(artifacts)
        free_space = FreeSpaceProbe.capture(artifact.path for artifact in targets)
        moved, failed, processed = [], [], 0
        for index, artifact in enumerate(targets, 1):
            if progress: progress(index, len(targets), artifact.path)
            def validate_artifact(raw: Path) -> Path:
                if raw != artifact.path or not self.validate(artifact):
                    raise PathSafetyError("project identity or artifact safety changed")
                return PathSafety.validate_analyzer_candidate(raw)
            try:
                destination = Cleaner(self.config).move_reviewed_item_to_trash(artifact.path, validate_artifact, artifact.bytes)
                moved.append(str(destination))
                processed += max(0, artifact.bytes)
            except (OSError, ValueError, RuntimeError):
                failed.append(str(artifact.path))
        observed, notes = free_space.finish()
        Cleaner(self.config).log_space_summary(
            "project_purge_summary", scanned=sum(max(0, item.bytes) for item in targets),
            processed=processed, reclaimed=0, trash_moved=processed, observed=observed,
            unknown=0, notes=notes, failed=len(failed),
        )
        return {"success": not failed, "freed": 0, "estimatedReclaimedBytes": 0,
                "processedEstimatedBytes": processed, "trashMovedEstimatedBytes": processed,
                "observedFreeBytesDelta": observed, "measurementNotes": notes,
                "moved": moved, "failed": failed}


def analyze_directory(path: Path, top: int = 30, min_file_bytes: int = 100_000_000) -> dict[str, Any]:
    path = path.expanduser().absolute()
    try:
        children = list(path.iterdir())
    except OSError as exc:
        return {"path": str(path), "entries": [], "error": str(exc)}
    measured = sizes_of(children)
    entries = []
    for child in sorted(children, key=lambda item: -measured.get(item, 0))[:max(1, top)]:
        view_only = child == Path.home() / "Library" or child.suffix == ".app" or ".photoslibrary" in child.name.lower()
        entries.append({"name": child.name, "path": str(child), "bytes": measured.get(child, 0), "directory": child.is_dir(), "viewOnly": view_only})
    largest = []
    for directory, names, files in os.walk(path, followlinks=False):
        names[:] = [name for name in names if not name.startswith(".") and not name.endswith((".app", ".photoslibrary"))]
        for name in files:
            if name.startswith("."): continue
            candidate = Path(directory) / name
            try: size = candidate.stat().st_size
            except OSError: continue
            if size >= min_file_bytes: largest.append({"name": name, "path": str(candidate), "bytes": size, "directory": False, "viewOnly": False})
    largest.sort(key=lambda item: -item["bytes"])
    return {"path": str(path), "parent": str(path.parent), "entries": entries, "largestFiles": largest[:max(1, top)]}


_HEALTH_PROBE_TTL_SECONDS = 30.0
_health_probe_lock = threading.Lock()
_health_probe_cache: tuple[float, dict[str, Any]] | None = None


def _measured_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _expensive_health_probes(*, force: bool = False) -> dict[str, Any]:
    """Read bounded macOS health probes, caching them to avoid polling commands every UI tick."""
    global _health_probe_cache
    now = time.monotonic()
    with _health_probe_lock:
        if not force and _health_probe_cache and now - _health_probe_cache[0] < _HEALTH_PROBE_TTL_SECONDS:
            return _health_probe_cache[1]

        measured_at = _measured_now()
        pressure_result = run_command("/usr/bin/memory_pressure", ["-Q"], timeout=5)
        pressure_match = re.search(r"System-wide memory free percentage:\s*(\d+(?:\.\d+)?)%", pressure_result.stdout)
        memory_free_percent = (min(100.0, max(0.0, float(pressure_match.group(1))))
                               if pressure_result.succeeded and pressure_match else None)

        thermal_result = run_command("/usr/bin/pmset", ["-g", "therm"], timeout=5)
        thermal_text = (thermal_result.stdout or thermal_result.stderr).lower()
        thermal = "Unknown"
        if thermal_result.succeeded and "error:" not in thermal_text:
            levels = [int(value) for value in re.findall(r"(?:thermal|performance)[_ ](?:warning[_ ]?)?level\s*=\s*(\d+)", thermal_text)]
            if levels:
                thermal = "Critical" if max(levels) >= 2 else "Elevated" if max(levels) == 1 else "Normal"

        try:
            battery = psutil.sensors_battery()
        except (OSError, psutil.Error):
            battery = None
        battery_details: dict[str, Any] | None = None
        battery_probe = run_command("/usr/sbin/ioreg", ["-rc", "AppleSmartBattery", "-a"], timeout=5)
        battery_record: dict[str, Any] | None = None
        battery_probe_readable = False
        if battery_probe.succeeded:
            try:
                records = plistlib.loads(battery_probe.stdout.encode()) if battery_probe.stdout else []
                if isinstance(records, list) and (not records or isinstance(records[0], dict)):
                    battery_record = records[0] if records else None
                    battery_probe_readable = True
            except (ValueError, plistlib.InvalidFileException):
                battery_record = None
        if battery is not None or battery_record is not None:
            current_capacity = battery_record.get("CurrentCapacity") if battery_record else None
            max_capacity = battery_record.get("MaxCapacity") if battery_record else None
            record_percent = None
            if isinstance(current_capacity, (int, float)) and isinstance(max_capacity, (int, float)) and max_capacity > 0:
                record_percent = min(100.0, max(0.0, current_capacity / max_capacity * 100))
            battery_details = {
                "percent": battery.percent if battery is not None else record_percent,
                "charging": battery.power_plugged if battery is not None else bool(
                    battery_record.get("IsCharging") or battery_record.get("ExternalConnected")
                ),
                "cycleCount": battery_record.get("CycleCount") if battery_record else None,
                "condition": ((battery_record.get("BatteryHealth") or battery_record.get("Condition"))
                              if battery_record else "Unknown"),
            }

        probes = {
            "measuredAt": measured_at,
            "memoryFreePercent": memory_free_percent,
            "thermal": thermal,
            "battery": battery_details,
            "batteryProbeSucceeded": battery_probe.succeeded and battery_probe_readable,
            "batteryPresent": battery is not None or battery_record is not None,
        }
        _health_probe_cache = (now, probes)
        return probes


def health_indicators(status: dict[str, Any]) -> list[HealthIndicator]:
    measured_at = str(status["healthMeasuredAt"])
    total = int(status["diskTotal"])
    free = int(status["diskFree"])
    free_percent = (free / total * 100) if total > 0 else 0.0
    if total <= 0:
        disk_state, disk_recommendation = "unknown", None
    elif free_percent < 5 or free < 5 * 1024**3:
        disk_state, disk_recommendation = "critical", "Free disk space soon; macOS and apps need working space."
    elif free_percent < 10 or free < 20 * 1024**3:
        disk_state, disk_recommendation = "warning", "Review large or safely cleanable items before space becomes critical."
    else:
        disk_state, disk_recommendation = "normal", None
    indicators = [HealthIndicator(
        "disk", "Disk space", disk_state,
        "Unknown" if total <= 0 else f"{human_bytes(free)} available ({free_percent:.0f}%)",
        f"Measured on {status.get('diskUsageBasis', 'the active data volume')}; warning below 10% or 20 GB, critical below 5% or 5 GB.",
        disk_recommendation, measured_at,
    )]

    memory_free = status.get("memoryPressureFreePercent")
    if memory_free is None:
        memory_state, memory_value, memory_recommendation = "unknown", "Unknown", None
        memory_detail = "The macOS memory-pressure probe was unavailable or unreadable; RAM fullness is not used as a substitute."
    else:
        memory_free = float(memory_free)
        memory_state = "critical" if memory_free < 5 else "warning" if memory_free < 15 else "normal"
        memory_value = f"{memory_free:.0f}% pressure headroom"
        memory_detail = "Based on macOS memory_pressure headroom, not the percentage of RAM currently occupied."
        memory_recommendation = ("Close or restart memory-heavy apps if the system is unresponsive."
                                 if memory_state in {"warning", "critical"} else None)
    indicators.append(HealthIndicator(
        "memory", "Memory pressure", memory_state, memory_value, memory_detail,
        memory_recommendation, measured_at,
    ))

    thermal = str(status.get("thermal", "Unknown"))
    thermal_state = {"Normal": "normal", "Elevated": "warning", "Critical": "critical"}.get(thermal, "unknown")
    indicators.append(HealthIndicator(
        "thermal", "Thermal state", thermal_state, thermal,
        "Reported by macOS power-management thermal warning levels; unavailable sensors remain unknown.",
        "Reduce sustained workload and ensure ventilation." if thermal_state in {"warning", "critical"} else None,
        measured_at,
    ))

    battery = status.get("battery")
    if not status.get("batteryPresent") and status.get("batteryProbeSucceeded"):
        battery_state, battery_value = "not_applicable", "No battery detected"
        battery_detail, battery_recommendation = "This Mac reports no internal smart battery.", None
    elif not battery:
        battery_state, battery_value = "unknown", "Unknown"
        battery_detail, battery_recommendation = "Battery presence or health could not be read.", None
    else:
        condition = str(battery.get("condition") or "Unknown")
        normalized = condition.casefold()
        if normalized in {"normal", "good"}:
            battery_state, battery_recommendation = "normal", None
        elif normalized in {"service battery", "replace now", "service recommended"}:
            battery_state, battery_recommendation = "critical", "Review Battery settings and arrange service if macOS recommends it."
        elif normalized == "unknown":
            battery_state, battery_recommendation = "unknown", None
        else:
            battery_state, battery_recommendation = "warning", "Review the battery-health recommendation in macOS Settings."
        battery_value = f"{condition} · {battery.get('percent', '—')}%"
        cycles = battery.get("cycleCount")
        battery_detail = f"Smart-battery condition reported by macOS{f'; {cycles} cycles' if cycles is not None else ''}."
    indicators.append(HealthIndicator(
        "battery", "Battery health", battery_state, battery_value, battery_detail,
        battery_recommendation, measured_at,
    ))
    return indicators


def system_status(*, force_health_refresh: bool = False) -> dict[str, Any]:
    # On modern macOS `/` is the small read-only System volume. User files live on the paired Data volume.
    data_volume = Path("/System/Volumes/Data")
    disk_mount = data_volume if data_volume.is_dir() else Path("/")
    disk = psutil.disk_usage(str(disk_mount))
    memory = psutil.virtual_memory()
    network_before = psutil.net_io_counters()
    disk_before = psutil.disk_io_counters()
    time.sleep(0.1)
    network_after = psutil.net_io_counters()
    disk_after = psutil.disk_io_counters()
    processes = []
    try:
        visible_processes = sorted(
            psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
            key=lambda p: p.info.get("cpu_percent") or 0, reverse=True,
        )[:6]
        for proc in visible_processes:
            processes.append({"pid": proc.info["pid"], "cpu": proc.info.get("cpu_percent") or 0, "memory": proc.info.get("memory_percent") or 0, "command": proc.info.get("name") or ""})
    except (OSError, psutil.Error):
        # Process visibility can be restricted independently of the health probes.
        processes = []
    cpu = psutil.cpu_percent(interval=0.1)
    probes = _expensive_health_probes(force=force_health_refresh)
    try:
        boot_time = psutil.boot_time()
    except (OSError, psutil.Error):
        boot_time = time.time()
    status = {
        "cpu": cpu, "cpuPercent": cpu,
        "memoryUsed": memory.used, "memoryTotal": memory.total, "memoryPercent": memory.percent,
        "diskUsed": disk.used, "diskTotal": disk.total, "diskFree": disk.free, "diskPercent": disk.percent,
        "diskMount": str(disk_mount), "diskUsageBasis": "macOS Data volume" if disk_mount == data_volume else "root volume",
        "network": network_after._asdict(), "bootTime": boot_time,
        "networkDownPerSecond": max(0, (network_after.bytes_recv - network_before.bytes_recv) * 10),
        "networkUpPerSecond": max(0, (network_after.bytes_sent - network_before.bytes_sent) * 10),
        "diskIOPerSecond": 0 if not disk_before or not disk_after else max(0, ((disk_after.read_bytes + disk_after.write_bytes) - (disk_before.read_bytes + disk_before.write_bytes)) * 10),
        "battery": probes["battery"], "thermal": probes["thermal"], "processes": processes,
        "memoryPressureFreePercent": probes["memoryFreePercent"],
        "batteryProbeSucceeded": probes["batteryProbeSucceeded"],
        "batteryPresent": probes["batteryPresent"], "healthMeasuredAt": probes["measuredAt"],
    }
    status["healthIndicators"] = [item.web_dict() for item in health_indicators(status)]
    return status


OPTIMIZATIONS = [
    {"id": "dns", "title": "Flush DNS cache", "risk": "SAFE", "recommended": True},
    {"id": "quicklook", "title": "Refresh Quick Look cache", "risk": "SAFE", "recommended": True},
    {"id": "finder", "title": "Refresh Finder", "risk": "SAFE", "recommended": True},
    {"id": "dock", "title": "Refresh Dock", "risk": "SAFE", "recommended": True},
    {"id": "launchservices", "title": "Rebuild LaunchServices registration", "risk": "MODERATE", "recommended": True},
    {"id": "spotlight-health", "title": "Check Spotlight indexing", "risk": "SAFE", "recommended": True},
    {"id": "spotlight-rebuild", "title": "Reindex Spotlight", "risk": "ADVANCED", "recommended": False},
]


def run_optimization(task_id: str) -> dict[str, Any]:
    if task_id == "spotlight-reindex":
        task_id = "spotlight-rebuild"
    if task_id == "spotlight-rebuild":
        command = "/usr/bin/mdutil -E /"
        escaped = command.replace("\\", "\\\\").replace('"', '\\"')
        script = f'do shell script "{escaped}" with administrator privileges'
        result = run_command("/usr/bin/osascript", ["-e", script], timeout=600)
        return {"success": result.succeeded, "output": result.stdout, "error": result.stderr}
    commands = {
        "dns": [("/usr/bin/dscacheutil", ["-flushcache"]), ("/usr/bin/killall", ["-HUP", "mDNSResponder"])],
        "quicklook": [("/usr/bin/qlmanage", ["-r", "cache"])],
        "finder": [("/usr/bin/killall", ["Finder"])],
        "dock": [("/usr/bin/killall", ["Dock"])],
        "launchservices": [("/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister", ["-kill", "-r", "-domain", "local", "-domain", "system", "-domain", "user"])],
        "spotlight-health": [("/usr/bin/mdutil", ["-s", "/"])],
    }
    attempts = commands.get(task_id)
    if not attempts:
        return {"success": False, "error": "unknown optimization"}
    last = None
    for executable, arguments in attempts:
        last = run_command(executable, arguments, timeout=600)
        if last.succeeded:
            return {"success": True, "output": last.stdout}
    return {"success": False, "error": (last.stderr or last.stdout) if last else "unavailable"}


def compatibility_checks() -> list[dict[str, Any]]:
    system_name = platform.system()
    macos_version = platform.mac_ver()[0]
    architecture = platform.machine()
    try:
        macos_major = int(macos_version.split(".", 1)[0])
    except (ValueError, IndexError):
        macos_major = 0

    macos_ok = system_name == "Darwin" and macos_major >= 13
    architecture_name = {"arm64": "Apple Silicon", "x86_64": "Intel"}.get(architecture)
    architecture_ok = architecture_name is not None
    python_ok = sys.version_info >= (3, 11)
    return [
        {"name": "macOS", "value": macos_version or f"Unavailable ({system_name})", "ok": macos_ok},
        {"name": "Architecture", "value": f"{architecture} ({architecture_name})" if architecture_name else architecture or "Unknown", "ok": architecture_ok},
        {"name": "Python", "value": platform.python_version(), "ok": python_ok},
    ]


def doctor() -> list[dict[str, Any]]:
    config_writable = os.access(Config().config_dir.parent, os.W_OK)
    tmutil = which("tmutil")
    checks = compatibility_checks()
    checks.extend([
        {"name": "Running as root", "value": "NO (safe)" if os.geteuid() != 0 else "YES — restart without sudo", "ok": os.geteuid() != 0},
        {"name": "Home", "value": str(Path.home()), "ok": True},
        {"name": "Config writable", "value": "YES" if config_writable else "NO", "ok": config_writable},
        {"name": "System Integrity Protection", "value": run_command("/usr/bin/csrutil", ["status"], timeout=5).stdout or "Unknown", "ok": None},
        {"name": "Time Machine", "value": "Available" if tmutil else "Unavailable", "ok": tmutil is not None},
    ])
    return checks


def list_snapshots() -> list[str]:
    result = run_command("/usr/bin/tmutil", ["listlocalsnapshots", "/"], timeout=30)
    return result.stdout.splitlines() if result.succeeded else []


def thin_snapshots(bytes_to_free: int, config: Config | None = None) -> dict[str, Any]:
    cleaner = Cleaner(config)
    cleaner._ensure_audit_safe()
    free_space = FreeSpaceProbe.capture([Path("/")])
    result = run_command("/usr/bin/tmutil", ["thinlocalsnapshots", "/", str(max(0, bytes_to_free)), "4"], timeout=600)
    observed, notes = free_space.finish()
    if result.succeeded:
        cleaner.log_space_summary(
            "snapshot_thin_summary", scanned=0, processed=0, reclaimed=0,
            trash_moved=0, observed=observed, unknown=1, notes=notes,
        )
    return {"success": result.succeeded, "output": result.stdout, "error": result.stderr,
            "requestedReclaimBytes": max(0, bytes_to_free), "estimatedReclaimedBytes": 0,
            "observedFreeBytesDelta": observed, "unknownReclaimCount": int(result.succeeded),
            "measurementNotes": notes}


def history(limit: int = 40, config: Config | None = None) -> list[dict[str, Any]]:
    path = (config or Config()).operation_log
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-max(1, limit):]
    except OSError:
        return []
    records = []
    for line in reversed(lines):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return records


class RecoveryCenter:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()

    def entries(self, limit: int = 200) -> list[dict[str, Any]]:
        return [self._with_status(record) for record in history(limit, self.config)]

    def restore(self, operation_id: str, trash_path: str, *, copy: bool = False) -> dict[str, Any]:
        record = self._find_record(operation_id, trash_path)
        source = self._validate_trash_path(Path(str(record["trash_path"])))
        original = self._validate_original_path(Path(str(record["original_path"])))
        if copy:
            destination = self._copy_destination(original)
            self._copy_source(source, destination)
            action = "restore_copy"
        else:
            if original.exists() or original.is_symlink():
                raise FileExistsError(f"Restore conflict: {original}")
            os.replace(source, original)
            destination = original
            action = "restore"
        self._audit_recovery(action, record, destination)
        return {"success": True, "operation_id": operation_id, "original_path": str(original),
                "trash_path": str(source), "restored_path": str(destination), "copied": copy}

    def conflict(self, operation_id: str, trash_path: str) -> dict[str, Any]:
        record = self._find_record(operation_id, trash_path)
        source = self._validate_trash_path(Path(str(record["trash_path"])))
        original = self._validate_original_path(Path(str(record["original_path"])))
        return {"operation_id": operation_id, "trash_path": str(source), "original_path": str(original),
                "trashExists": source.exists(), "originalExists": original.exists() or original.is_symlink(),
                "restorable": bool(record.get("restorable")) and source.exists()}

    def _find_record(self, operation_id: str, trash_path: str) -> dict[str, Any]:
        if not operation_id or not trash_path:
            raise ValueError("operation_id and trash_path are required")
        for record in history(1000, self.config):
            if (record.get("recordType") == "item" and record.get("operation_id") == operation_id
                    and record.get("trash_path") == trash_path):
                if not record.get("restorable"):
                    raise PermissionError("History item is not restorable")
                if not record.get("original_path"):
                    raise PermissionError("History item has no original path")
                return record
        raise FileNotFoundError("Restorable history item was not found")

    def _validate_trash_path(self, raw: Path) -> Path:
        path = PathSafety._lexical(raw)
        trash = self.config.home / ".Trash"
        if trash not in path.parents:
            raise PathSafetyError("Recovery source must be inside the current user's Trash")
        PathSafety._reject_symlink_ancestors(path)
        if path.is_symlink() or not path.exists() or path.lstat().st_uid != os.getuid():
            raise PathSafetyError("Recovery source is unavailable or unsafe")
        return path

    def _validate_original_path(self, raw: Path) -> Path:
        path = PathSafety._lexical(raw)
        if self.config.home not in path.parents:
            raise PathSafetyError("Recovery destination must be below HOME")
        parent = path.parent
        PathSafety._reject_symlink_ancestors(parent)
        if not parent.exists() or parent.is_symlink() or not parent.is_dir() or parent.lstat().st_uid != os.getuid():
            raise PathSafetyError("Recovery destination parent is unavailable or unsafe")
        return path

    def _copy_destination(self, original: Path) -> Path:
        if not original.exists() and not original.is_symlink():
            return original
        stem = original.stem if original.suffix else original.name
        suffix = original.suffix
        for index in range(1, 1000):
            extra = "Restored copy" if index == 1 else f"Restored copy {index}"
            candidate = original.with_name(f"{stem} ({extra}){suffix}")
            if not candidate.exists() and not candidate.is_symlink():
                return candidate
        raise FileExistsError("No collision-free restore-copy destination is available")

    def _copy_source(self, source: Path, destination: Path) -> None:
        if source.is_dir():
            shutil.copytree(source, destination, symlinks=True)
        else:
            shutil.copy2(source, destination, follow_symlinks=False)
        if not destination.exists() and not destination.is_symlink():
            raise RuntimeError("Restore copy post-condition failed")

    def _audit_recovery(self, action: str, record: dict[str, Any], destination: Path) -> None:
        Cleaner(self.config)._append_record({
            "timestamp": datetime.now(timezone.utc).isoformat(), "recordType": "recovery",
            "operation_id": record.get("operation_id"), "action": action, "result": "success",
            "original_path": record.get("original_path"), "trash_path": record.get("trash_path"),
            "restored_path": str(destination), "size": record.get("size", record.get("bytes", 0)),
            "restorable": False,
        })

    def _with_status(self, record: dict[str, Any]) -> dict[str, Any]:
        copy = dict(record)
        if record.get("action") in {ActionType.COMMAND.value, ActionType.COMMAND_WITH_CACHE_FALLBACK.value}:
            copy["restoreStatus"] = "Not Restorable"
        elif not record.get("restorable"):
            copy["restoreStatus"] = "Not Restorable"
        elif record.get("trash_path") and Path(str(record["trash_path"])).exists():
            copy["restoreStatus"] = "Restorable"
        else:
            copy["restoreStatus"] = "Trash item missing"
            copy["restorable"] = False
        return copy


def developer_inventory(kind: str) -> list[dict[str, Any]]:
    from .developer import DeveloperInventory

    category = {"runtimes": "runtime", "environments": "environment", "tools": "tool", "sdks": "sdk"}.get(kind)
    if category is None:
        return []
    return [dict(item.web_dict(), name=item.title, active=item.is_active, detail=item.note) for item in DeveloperInventory().scan(category)]


def completion_script(shell: str) -> str:
    commands = "doctor scan clean leftovers installers smart-downloads analyze duplicates large-files apps purge status completion developer-caches developer optimize snapshots history restore whitelist uninstall ui web gui dashboard"
    if shell == "fish":
        return f"complete -c deepclean -f -a '{commands}'"
    if shell == "bash":
        return f"_deepclean() {{ COMPREPLY=( $(compgen -W \"{commands}\" -- \"${{COMP_WORDS[1]}}\") ); }}\ncomplete -F _deepclean deepclean"
    optimization_ids = " ".join(task["id"] for task in OPTIMIZATIONS)
    return f'''#compdef deepclean

_deepclean() {{
  local context state state_descr line
  typeset -A opt_args
  local -a commands
  commands=(
    'doctor:Check macOS and DeepClean capabilities'
    'scan:Scan cleanup candidates safely'
    'clean:Alias for scan'
    'leftovers:Find application leftovers'
    'installers:Find old installer files'
    'smart-downloads:Classify Downloads installers archives incomplete files and duplicates'
    'analyze:Analyze disk usage'
    'duplicates:Find byte-for-byte duplicate files'
    'large-files:Find large and old user files'
    'apps:List installed applications'
    'purge:Find generated project artifacts'
    'status:Show evidence-based Mac health'
    'completion:Print or install shell completion'
    'developer-caches:Scan package-manager caches'
    'developer:List managed runtimes environments tools or SDKs'
    'optimize:Review macOS maintenance tasks'
    'snapshots:List or thin local snapshots'
    'history:Show operation history'
    'restore:Restore a restorable Trash history item'
    'whitelist:Print the whitelist path'
    'uninstall:Uninstall DeepClean'
    'ui:Open the local Web UI'
    'web:Alias for ui'
    'gui:Alias for ui'
    'dashboard:Alias for ui'
  )

  _arguments -C \\
    '(-h --help)'{{-h,--help}}'[show help]' \\
    '(- 1 *)--version[show version]' \\
    '1:command:->command' \\
    '*::argument:->arguments'

  case $state in
    command)
      _describe -t commands 'DeepClean command' commands
      ;;
    arguments)
      case $words[2] in
        scan|clean)
          _arguments \\
            '--profile[select scan profile]:profile:(safe deep developer aggressive)' \\
            '--trash[include Trash in the scan]' \\
            '--system-temp[include eligible system temporary files]' \\
            '--scan-only[scan without prompting for cleanup]' \\
            '--no-prompt[alias for --scan-only]' \\
            '--apply[request cleanup after review]' \\
            '--yes[acknowledge a reviewed non-interactive operation]'
          ;;
        leftovers)
          _arguments '--older-than[minimum age in days]:days:' '--include-data[include separately classified application data]' '--apply[request cleanup after review]' '--yes[acknowledge a reviewed non-interactive operation]'
          ;;
        installers)
          _arguments '--older-than[minimum age in days]:days:' '--apply[request cleanup after review]' '--yes[acknowledge a reviewed non-interactive operation]'
          ;;
        analyze)
          _arguments '1:path:_files' '--top[number of largest files]:count:' '--min-size[minimum file size]:size:' '--plain[use plain output]'
          ;;
        purge)
          _arguments '*--path[project root]:project root:_directories' '--apply[request Trash moves after review]' '--yes[acknowledge a reviewed non-interactive operation]'
          ;;
        completion)
          _arguments '1:shell:(zsh bash fish)' '--print[print completion script]' '--install[install completion for the selected shell]'
          ;;
        developer-caches)
          _arguments '--scan-only[scan without prompting for cleanup]' '--apply[request cleanup after review]' '--yes[acknowledge a reviewed non-interactive operation]'
          ;;
        developer)
          _arguments '1:inventory kind:(runtimes environments tools sdks)'
          ;;
        optimize)
          _arguments '--task[select one maintenance task]:task:({optimization_ids})' '--all[select every task including advanced tasks]' '--apply[request execution after review]' '--yes[acknowledge a reviewed non-interactive operation]'
          ;;
        snapshots)
          _arguments '--thin[request reclaim target]:gigabytes:' '--apply[request execution after review]' '--yes[acknowledge a reviewed non-interactive operation]'
          ;;
        history)
          _arguments '--limit[maximum history records]:count:'
          ;;
        ui|web|gui|dashboard)
          _arguments '--port[localhost port]:port:' '--no-open[do not open the browser]'
          ;;
        uninstall)
          _arguments '--purge-data[also remove DeepClean configuration and logs]'
          ;;
        *)
          _arguments '(-h --help)'{{-h,--help}}'[show help]'
          ;;
      esac
      ;;
  esac
}}

_deepclean "$@"'''


def install_completion(shell: str, config: Config | None = None) -> Path:
    config = config or Config(); config.ensure_files()
    home = config.home
    marker = "# >>> DeepClean completion >>>"
    end = "# <<< DeepClean completion <<<"
    if shell == "fish":
        destination = home / ".config/fish/completions/deepclean.fish"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(completion_script("fish") + "\n", encoding="utf-8")
        return destination
    destination = config.config_dir / "completions" / ("zsh/_deepclean" if shell == "zsh" else "deepclean.bash")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(completion_script(shell) + "\n", encoding="utf-8")
    if shell == "zsh":
        rc = home / ".zshrc"
        block = f'\n{marker}\nfpath=("$HOME/.config/deepclean/completions/zsh" $fpath)\nautoload -Uz compinit\ncompinit\n{end}\n'
    else:
        rc = home / (".bash_profile" if (home / ".bash_profile").exists() else ".bashrc")
        block = f'\n{marker}\n[ -f "$HOME/.config/deepclean/completions/deepclean.bash" ] && source "$HOME/.config/deepclean/completions/deepclean.bash"\n{end}\n'
    current = rc.read_text(encoding="utf-8") if rc.exists() else ""
    if marker not in current:
        rc.write_text(current + block, encoding="utf-8")
    return destination


def completion_activation_hint(shell: str) -> str:
    if shell == "zsh":
        return 'fpath=("$HOME/.config/deepclean/completions/zsh" $fpath); autoload -Uz compinit; compinit'
    if shell == "bash":
        return 'source "$HOME/.config/deepclean/completions/deepclean.bash"'
    return 'source "$HOME/.config/fish/completions/deepclean.fish"'


def remove_completion_hooks() -> None:
    marker = "# >>> DeepClean completion >>>"; end = "# <<< DeepClean completion <<<"
    for rc in (Path.home() / ".zshrc", Path.home() / ".bashrc", Path.home() / ".bash_profile"):
        try: text = rc.read_text(encoding="utf-8")
        except OSError: continue
        while marker in text and end in text[text.index(marker):]:
            start = text.index(marker); finish = text.index(end, start) + len(end)
            if finish < len(text) and text[finish] == "\n": finish += 1
            text = text[:start] + text[finish:]
        rc.write_text(text, encoding="utf-8")
    fish = Path.home() / ".config/fish/completions/deepclean.fish"
    fish.unlink(missing_ok=True)
