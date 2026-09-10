from __future__ import annotations

import json
import os
import platform
import plistlib
import re
import socket
import time
from dataclasses import asdict, dataclass
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


def system_status() -> dict[str, Any]:
    # On modern macOS `/` is the small read-only System volume. User files live on the paired Data volume.
    data_volume = Path("/System/Volumes/Data")
    disk_mount = data_volume if data_volume.is_dir() else Path("/")
    disk = psutil.disk_usage(str(disk_mount))
    memory = psutil.virtual_memory()
    battery = psutil.sensors_battery()
    network_before = psutil.net_io_counters()
    disk_before = psutil.disk_io_counters()
    time.sleep(0.1)
    network_after = psutil.net_io_counters()
    disk_after = psutil.disk_io_counters()
    processes = []
    for proc in sorted(psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]), key=lambda p: p.info.get("cpu_percent") or 0, reverse=True)[:6]:
        processes.append({"pid": proc.info["pid"], "cpu": proc.info.get("cpu_percent") or 0, "memory": proc.info.get("memory_percent") or 0, "command": proc.info.get("name") or ""})
    cpu = psutil.cpu_percent(interval=0.1)
    battery_details: dict[str, Any] | None = None
    if battery is not None:
        battery_details = {"percent": battery.percent, "charging": battery.power_plugged, "cycleCount": None, "condition": "Unknown"}
        raw_battery = run_command("/usr/sbin/ioreg", ["-rc", "AppleSmartBattery", "-a"], timeout=5)
        if raw_battery.succeeded:
            try:
                records = plistlib.loads(raw_battery.stdout.encode())
                record = records[0] if records else {}
                battery_details["cycleCount"] = record.get("CycleCount")
                battery_details["condition"] = record.get("BatteryHealth") or record.get("Condition") or "Unknown"
            except (ValueError, plistlib.InvalidFileException):
                pass
    thermal_result = run_command("/usr/bin/pmset", ["-g", "therm"], timeout=5)
    thermal_text = (thermal_result.stdout or thermal_result.stderr).lower()
    thermal = "Unknown"
    if thermal_result.succeeded and "error:" not in thermal_text:
        levels = [int(value) for value in re.findall(r"(?:thermal|performance)[_ ](?:warning[_ ]?)?level\s*=\s*(\d+)", thermal_text)]
        if levels:
            thermal = "Critical" if max(levels) >= 2 else "Elevated" if max(levels) == 1 else "Normal"
    return {
        "cpu": cpu, "cpuPercent": cpu,
        "memoryUsed": memory.used, "memoryTotal": memory.total, "memoryPercent": memory.percent,
        "diskUsed": disk.used, "diskTotal": disk.total, "diskFree": disk.free, "diskPercent": disk.percent,
        "diskMount": str(disk_mount), "diskUsageBasis": "macOS Data volume" if disk_mount == data_volume else "root volume",
        "network": network_after._asdict(), "bootTime": psutil.boot_time(),
        "networkDownPerSecond": max(0, (network_after.bytes_recv - network_before.bytes_recv) * 10),
        "networkUpPerSecond": max(0, (network_after.bytes_sent - network_before.bytes_sent) * 10),
        "diskIOPerSecond": 0 if not disk_before or not disk_after else max(0, ((disk_after.read_bytes + disk_after.write_bytes) - (disk_before.read_bytes + disk_before.write_bytes)) * 10),
        "battery": battery_details, "thermal": thermal, "processes": processes,
    }


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


def doctor() -> list[dict[str, str]]:
    checks = [
        ("macOS", platform.mac_ver()[0] or platform.system()),
        ("Architecture", platform.machine()),
        ("Running as root", "NO (safe)" if os.geteuid() != 0 else "YES — restart without sudo"),
        ("Home", str(Path.home())),
        ("Config writable", "YES" if os.access(Config().config_dir.parent, os.W_OK) else "NO"),
        ("System Integrity Protection", run_command("/usr/bin/csrutil", ["status"], timeout=5).stdout or "Unknown"),
        ("Time Machine", "Available" if which("tmutil") else "Unavailable"),
    ]
    return [{"name": name, "value": value} for name, value in checks]


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


def history(limit: int = 40) -> list[dict[str, Any]]:
    path = Config().operation_log
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


def developer_inventory(kind: str) -> list[dict[str, Any]]:
    from .developer import DeveloperInventory

    category = {"runtimes": "runtime", "environments": "environment", "tools": "tool", "sdks": "sdk"}.get(kind)
    if category is None:
        return []
    return [dict(item.web_dict(), name=item.title, active=item.is_active, detail=item.note) for item in DeveloperInventory().scan(category)]


def completion_script(shell: str) -> str:
    commands = "help version doctor scan clean leftovers installers analyze apps purge status completion developer-caches optimize snapshots history whitelist uninstall ui"
    if shell == "fish":
        return f"complete -c deepclean -f -a '{commands}'"
    if shell == "bash":
        return f"_deepclean() {{ COMPREPLY=( $(compgen -W \"{commands}\" -- \"${{COMP_WORDS[1]}}\") ); }}\ncomplete -F _deepclean deepclean"
    return f"#compdef deepclean\n_arguments '1:command:({commands})' '*::arg:->args'"


def install_completion(shell: str, config: Config | None = None) -> Path:
    config = config or Config(); config.ensure_files()
    marker = "# >>> DeepClean completion >>>"
    end = "# <<< DeepClean completion <<<"
    if shell == "fish":
        destination = Path.home() / ".config/fish/completions/deepclean.fish"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(completion_script("fish") + "\n", encoding="utf-8")
        return destination
    destination = config.config_dir / "completions" / ("zsh/_deepclean" if shell == "zsh" else "deepclean.bash")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(completion_script(shell) + "\n", encoding="utf-8")
    if shell == "zsh":
        rc = Path.home() / ".zshrc"
        block = f'\n{marker}\nfpath=("$HOME/.config/deepclean/completions/zsh" $fpath)\nautoload -Uz compinit\ncompinit\n{end}\n'
    else:
        rc = Path.home() / (".bash_profile" if (Path.home() / ".bash_profile").exists() else ".bashrc")
        block = f'\n{marker}\n[ -f "$HOME/.config/deepclean/completions/deepclean.bash" ] && source "$HOME/.config/deepclean/completions/deepclean.bash"\n{end}\n'
    current = rc.read_text(encoding="utf-8") if rc.exists() else ""
    if marker not in current:
        rc.write_text(current + block, encoding="utf-8")
    return destination


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
