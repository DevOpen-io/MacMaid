from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

from .config import Config
from .models import (
    ActionType, CleanupAction, CleanupCategory, CleanupItem, CleanupProfile, RiskLevel, ScanResult,
)
from .system import process_running, run_command, size_of, sizes_of, which

Progress = Callable[[int, str, str], None]


class Scanner:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        self._progress: Progress | None = None

    def scan(
        self,
        profile: CleanupProfile = CleanupProfile.SAFE,
        *,
        include_trash: bool = False,
        include_system_temp: bool = False,
        progress: Progress | None = None,
    ) -> ScanResult:
        self._progress = progress
        phases: list[tuple[str, Callable[[], list[CleanupItem]]]] = [
            ("User caches", lambda: self._user_caches(profile)),
            ("Browser caches", lambda: self._browser_caches(profile)),
            ("Application caches", lambda: self._application_caches(profile)),
            ("Sandbox caches", lambda: self._sandbox_caches(profile)),
            ("Logs & diagnostics", lambda: self._logs(profile)),
        ]
        if profile.includes_developer:
            phases.extend([
                ("Developer tools", lambda: self._developer(profile)),
                ("Package-manager caches", lambda: PackageManagerCacheScanner(self.config).scan().items),
            ])
        if profile in (CleanupProfile.DEEP, CleanupProfile.AGGRESSIVE):
            phases.append(("Saved application state", self._saved_state))
        if include_system_temp and profile in (CleanupProfile.DEEP, CleanupProfile.AGGRESSIVE):
            phases.append(("Temporary files", lambda: self._temporary(profile)))
        if include_trash:
            phases.append(("Trash", self._trash))

        result = ScanResult()
        for index, (name, operation) in enumerate(phases):
            self._emit(index, len(phases), name, "")
            result.items.extend(operation())
            self._emit(index + 1, len(phases), name, "")
        seen: set[tuple[str, str, str]] = set()
        unique: list[CleanupItem] = []
        for item in result.items:
            key = (item.category.value, str(item.path or ""), item.action.kind.value)
            if key not in seen:
                seen.add(key)
                unique.append(item)
        result.items = sorted(unique, key=lambda item: (item.category.value, -item.estimated_bytes))
        if self._progress:
            self._progress(100, "Complete", "")
        return result

    def _emit(self, current: int, total: int, phase: str, path: str | Path) -> None:
        if self._progress:
            self._progress(min(99, int(current / max(total, 1) * 100)), phase, str(path))

    def _candidates(
        self,
        specs: Iterable[tuple[str, Path, RiskLevel, str, ActionType, str | None]],
        category: CleanupCategory,
        maximum: RiskLevel,
    ) -> list[CleanupItem]:
        accepted = [spec for spec in specs if spec[2] <= maximum and spec[1].exists() and not self.config.is_whitelisted(spec[1])]
        measured = sizes_of(spec[1] for spec in accepted)
        return [
            CleanupItem(category, label, path, measured.get(path, 0), risk, reason, CleanupAction(action), app)
            for label, path, risk, reason, action, app in accepted if measured.get(path, 0) > 0
        ]

    def _user_caches(self, profile: CleanupProfile) -> list[CleanupItem]:
        root = Path.home() / "Library/Caches"
        protected = ("com.apple.bird", "com.apple.cloudd", "com.apple.CloudDocs", "com.apple.nsurlsessiond", "com.apple.akd", "com.apple.accountsd")
        separate = {"Firefox", "com.apple.Safari", "com.apple.dt.Xcode", "CocoaPods", "org.swift.swiftpm", "org.carthage.CarthageKit"}
        specs = []
        try:
            children = list(root.iterdir())
        except OSError:
            return []
        for child in children:
            if child.name in separate or child.name.startswith(protected):
                continue
            risk = RiskLevel.MODERATE if child.name.startswith("com.apple.") else RiskLevel.SAFE
            specs.append((child.name, child, risk, "macOS cache location; contents should be recreatable.", ActionType.REMOVE_PATH, None))
        return self._candidates(specs, CleanupCategory.USER_CACHES, profile.maximum_risk)

    def _browser_caches(self, profile: CleanupProfile) -> list[CleanupItem]:
        home = Path.home()
        browsers = [
            ("Google Chrome", home / "Library/Application Support/Google/Chrome", "Google Chrome.app"),
            ("Brave", home / "Library/Application Support/BraveSoftware/Brave-Browser", "Brave Browser.app"),
            ("Microsoft Edge", home / "Library/Application Support/Microsoft Edge", "Microsoft Edge.app"),
            ("Chromium", home / "Library/Application Support/Chromium", "Chromium.app"),
        ]
        leaves = ("Cache", "Code Cache", "GPUCache", "DawnCache", "GrShaderCache", "ShaderCache", "Media Cache")
        specs = []
        for name, root, process in browsers:
            if not root.exists():
                continue
            running = name if process_running(process) else None
            try:
                profiles = [p for p in root.iterdir() if p.name in ("Default", "Guest Profile", "System Profile") or p.name.startswith("Profile ")]
            except OSError:
                continue
            for user_profile in profiles:
                for leaf in leaves:
                    path = user_profile / leaf
                    specs.append((f"{name} · {user_profile.name} · {leaf}", path, RiskLevel.SAFE, "Browser cache only; history, cookies and site data are excluded.", ActionType.REMOVE_PATH, running))
        firefox = home / "Library/Caches/Firefox/Profiles"
        if firefox.exists():
            try:
                for path in firefox.iterdir():
                    specs.append(("Firefox profile cache", path, RiskLevel.SAFE, "Firefox cache domain, not profile data.", ActionType.REMOVE_PATH, "Firefox" if process_running("Firefox.app") else None))
            except OSError:
                pass
        specs.append(("Safari cache", home / "Library/Caches/com.apple.Safari", RiskLevel.MODERATE, "Safari cache only; website data is excluded.", ActionType.REMOVE_PATH, "Safari" if process_running("Safari.app") else None))
        return self._candidates(specs, CleanupCategory.BROWSER_CACHES, profile.maximum_risk)

    def _application_caches(self, profile: CleanupProfile) -> list[CleanupItem]:
        home = Path.home()
        apps = [
            ("VS Code", "Code", "Visual Studio Code.app"), ("VS Code Insiders", "Code - Insiders", "Visual Studio Code - Insiders.app"),
            ("Cursor", "Cursor", "Cursor.app"), ("Slack", "Slack", "Slack.app"),
            ("Discord", "discord", "Discord.app"), ("Spotify", "Spotify", "Spotify.app"),
        ]
        leaves = ("Cache", "Caches", "Code Cache", "GPUCache", "DawnCache", "CachedData", "CachedExtensionVSIXs", "CachedProfilesData", "logs")
        specs = []
        for name, folder, process in apps:
            root = home / "Library/Application Support" / folder
            running = name if process_running(process) else None
            for leaf in leaves:
                specs.append((f"{name} · {leaf}", root / leaf, RiskLevel.SAFE, "Known disposable app cache/log leaf; databases and user state are excluded.", ActionType.REMOVE_PATH, running))
        return self._candidates(specs, CleanupCategory.APP_CACHES, profile.maximum_risk)

    def _sandbox_caches(self, profile: CleanupProfile) -> list[CleanupItem]:
        root = Path.home() / "Library/Containers"
        try:
            containers = list(root.iterdir())
        except OSError:
            return []
        specs = []
        for container in containers:
            risk = RiskLevel.MODERATE if container.name.startswith("com.apple.") else RiskLevel.SAFE
            specs.append((f"Sandbox cache · {container.name}", container / "Data/Library/Caches", risk, "Only Data/Library/Caches contents are removed.", ActionType.REMOVE_CHILDREN, None))
        return self._candidates(specs, CleanupCategory.APP_CACHES, profile.maximum_risk)

    def _logs(self, profile: CleanupProfile) -> list[CleanupItem]:
        cutoff = time.time() - (7 if profile is CleanupProfile.SAFE else 1) * 86400
        specs = []
        for root in (Path.home() / "Library/Logs", Path.home() / "Library/DiagnosticReports"):
            try:
                children = list(root.iterdir())
            except OSError:
                continue
            for path in children:
                try:
                    if path.stat().st_mtime > cutoff or path == self.config.log_dir:
                        continue
                except OSError:
                    continue
                specs.append((path.name, path, RiskLevel.SAFE, "Old log or diagnostic data.", ActionType.REMOVE_PATH, None))
        return self._candidates(specs, CleanupCategory.LOGS, profile.maximum_risk)

    def _saved_state(self) -> list[CleanupItem]:
        root = Path.home() / "Library/Saved Application State"
        try:
            paths = list(root.iterdir())
        except OSError:
            return []
        specs = [(f"Saved state · {p.name}", p, RiskLevel.MODERATE, "App window/session restoration state, not documents.", ActionType.REMOVE_PATH, None) for p in paths]
        return self._candidates(specs, CleanupCategory.APP_CACHES, RiskLevel.MODERATE)

    def _developer(self, profile: CleanupProfile) -> list[CleanupItem]:
        home = Path.home()
        specs = [
            ("Xcode DerivedData", home / "Library/Developer/Xcode/DerivedData", RiskLevel.SAFE, "Recreatable Xcode builds and indexes.", ActionType.REMOVE_CHILDREN, None),
            ("Xcode cache", home / "Library/Caches/com.apple.dt.Xcode", RiskLevel.SAFE, "Xcode cache data.", ActionType.REMOVE_CHILDREN, None),
            ("CoreSimulator caches", home / "Library/Developer/CoreSimulator/Caches", RiskLevel.MODERATE, "Simulator cache only.", ActionType.REMOVE_CHILDREN, "CoreSimulator"),
            ("CocoaPods cache", home / "Library/Caches/CocoaPods", RiskLevel.SAFE, "Downloaded pod cache.", ActionType.REMOVE_CHILDREN, None),
            ("SwiftPM cache", home / "Library/Caches/org.swift.swiftpm", RiskLevel.SAFE, "SwiftPM cache.", ActionType.REMOVE_CHILDREN, None),
            ("Carthage cache", home / "Library/Caches/org.carthage.CarthageKit", RiskLevel.SAFE, "Carthage cache.", ActionType.REMOVE_CHILDREN, None),
        ]
        items = self._candidates(specs, CleanupCategory.DEVELOPER, profile.maximum_risk)
        xcrun = which("xcrun")
        if xcrun:
            items.append(CleanupItem(CleanupCategory.MAINTENANCE, "Delete unavailable CoreSimulator devices", None, 0, RiskLevel.SAFE, "Uses Apple's simctl manager.", CleanupAction(ActionType.COMMAND, xcrun, ["simctl", "delete", "unavailable"])))
        return items

    def _temporary(self, profile: CleanupProfile) -> list[CleanupItem]:
        cutoff = time.time() - (7 if profile is CleanupProfile.DEEP else 2) * 86400
        specs = []
        for root in (Path("/private/tmp"), Path("/private/var/tmp")):
            try:
                children = list(root.iterdir())
            except OSError:
                continue
            for path in children:
                try:
                    stat = path.lstat()
                except OSError:
                    continue
                if stat.st_uid == os.getuid() and stat.st_mtime < cutoff:
                    specs.append((path.name, path, RiskLevel.MODERATE, "Aged temporary item owned by the current user.", ActionType.REMOVE_PATH, None))
        return self._candidates(specs, CleanupCategory.TEMPORARY, profile.maximum_risk)

    def _trash(self) -> list[CleanupItem]:
        path = Path.home() / ".Trash"
        size = size_of(path)
        if not size or self.config.is_whitelisted(path):
            return []
        return [CleanupItem(CleanupCategory.TRASH, "User Trash", path, size, RiskLevel.MODERATE, "Deletes items already in Trash.", CleanupAction(ActionType.REMOVE_CHILDREN))]


class PackageManagerCacheScanner:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()

    def scan(self) -> ScanResult:
        home = Path.home()
        items: list[CleanupItem] = []; notes: list[str] = []

        def native(label: str, manager: str, arguments: list[str], path: Path | None, risk: RiskLevel = RiskLevel.MODERATE, executable: str | None = None) -> None:
            command = executable or which(manager)
            if not command or (path and self.config.is_whitelisted(path)): return
            size = size_of(path) if path else 0
            items.append(CleanupItem(CleanupCategory.PACKAGE_MANAGERS, label, path, size, risk, f"Uses {manager}'s supported cleanup operation; project data is outside this target.", CleanupAction(ActionType.COMMAND, command, arguments)))

        def manual(label: str, manager: str, path: Path) -> None:
            if not path.exists() or self.config.is_whitelisted(path): return
            size = size_of(path)
            if size: items.append(CleanupItem(CleanupCategory.PACKAGE_MANAGERS, label + " · manual fallback", path, size, RiskLevel.MANUAL_ONLY, "Default OFF; requires a second interactive confirmation and a strict cache-only allowlist.", CleanupAction(ActionType.MANUAL_CACHE_FALLBACK, fallback_manager=manager)))

        brew = which("brew")
        if brew:
            raw = run_command(brew, ["--cache"], timeout=10).stdout
            native("Homebrew cleanup", "brew", ["cleanup", "--prune=all"], Path(raw) if raw.startswith("/") else home / "Library/Caches/Homebrew", RiskLevel.SAFE, brew)
        pnpm = which("pnpm")
        if pnpm:
            raw = run_command(pnpm, ["store", "path"], timeout=10).stdout
            native("pnpm store prune", "pnpm", ["store", "prune"], Path(raw) if raw.startswith("/") else home / "Library/pnpm/store", RiskLevel.SAFE, pnpm)
        uv = which("uv")
        if uv:
            raw = run_command(uv, ["cache", "dir"], timeout=10).stdout
            native("uv cache prune", "uv", ["cache", "prune"], Path(raw) if raw.startswith("/") else None, RiskLevel.SAFE, uv)
        go = which("go")
        if go:
            raw = run_command(go, ["env", "GOCACHE"], timeout=10).stdout
            native("Go build/test cache", "go", ["clean", "-cache", "-testcache"], Path(raw) if raw.startswith("/") else None, RiskLevel.SAFE, go)
        bun = which("bun")
        if bun:
            raw = run_command(bun, ["pm", "cache"], timeout=10).stdout
            native("Bun package cache", "bun", ["pm", "cache", "rm"], Path(raw) if raw.startswith("/") else home / ".bun/install/cache", RiskLevel.MODERATE, bun)
        python = which("python3")
        if python:
            raw = run_command(python, ["-m", "pip", "cache", "dir"], timeout=10).stdout
            if raw.startswith("/"): native("Python pip cache", "pip", ["-m", "pip", "cache", "purge"], Path(raw), RiskLevel.MODERATE, python)
        yarn = which("yarn")
        if yarn:
            version = run_command(yarn, ["--version"], timeout=10).stdout
            if version.startswith("1."):
                raw = run_command(yarn, ["cache", "dir"], timeout=10).stdout
                native("Yarn Classic cache", "yarn", ["cache", "clean"], Path(raw) if raw.startswith("/") else None, RiskLevel.MODERATE, yarn)
            else: notes.append(f"Yarn {version} uses project-aware Berry cache semantics and is inventory-only.")
        composer = which("composer")
        if composer:
            raw = run_command(composer, ["config", "cache-dir", "--global"], timeout=10).stdout
            native("Composer cache clear", "composer", ["clear-cache"], Path(raw) if raw.startswith("/") else None, RiskLevel.MODERATE, composer)
        dotnet = which("dotnet")
        if dotnet:
            for location in ("http-cache", "temp", "plugins-cache"):
                native(f".NET / NuGet {location}", "dotnet", ["nuget", "locals", location, "--clear"], None, RiskLevel.MODERATE, dotnet)
        npm = which("npm")
        if npm:
            raw = run_command(npm, ["config", "get", "cache"], timeout=10).stdout
            native("npm cache clean", "npm", ["cache", "clean", "--force"], Path(raw) if raw.startswith("/") else home / ".npm", RiskLevel.AGGRESSIVE, npm)
        conda = which("conda")
        if conda:
            try: roots = [Path(p) for p in __import__("json").loads(run_command(conda, ["info", "--json"], timeout=20).stdout).get("pkgs_dirs", [])]
            except Exception: roots = []
            native("Conda package/index caches", "conda", ["clean", "--all", "-y"], roots[0] if roots else None, RiskLevel.MODERATE, conda)
        micromamba = which("micromamba")
        if micromamba: native("Micromamba package caches", "micromamba", ["clean", "--all", "--yes"], Path(os.environ.get("MAMBA_ROOT_PREFIX", home / "micromamba")) / "pkgs", RiskLevel.MODERATE, micromamba)
        pipx = which("pipx")
        if pipx:
            cache = home / ".cache/pipx"
            probe = run_command(pipx, ["cache", "dir"], timeout=10)
            if probe.succeeded: native("pipx run cache", "pipx", ["cache", "purge"], Path(probe.stdout), RiskLevel.SAFE, pipx)
            else: manual("pipx run cache", "pipx", cache)
        pixi = which("pixi")
        if pixi:
            candidates = [home / "Library/Caches/rattler", home / ".cache/rattler", home / "Library/Caches/pixi", home / ".cache/pixi"]
            native("Pixi caches", "pixi", ["clean", "cache", "--yes"], next((p for p in candidates if p.exists()), None), RiskLevel.MODERATE, pixi)
        if not process_running("GradleDaemon"): manual("Gradle caches", "gradle", home / ".gradle/caches")
        else: notes.append("Gradle caches skipped because a Gradle daemon is running.")
        manual("Cargo registry cache", "cargo-registry", home / ".cargo/registry/cache")
        manual("Cargo git dependency cache", "cargo-git", home / ".cargo/git/db")
        maven = home / ".m2/repository"
        if maven.exists(): notes.append(f"Maven local repository ({size_of(maven)} bytes) is inventory-only because it may contain locally-installed artifacts.")
        dart = which("dart"); pub = Path(os.environ.get("PUB_CACHE", home / ".pub-cache"))
        if dart and pub.exists(): native("Dart/Flutter pub cache", "dart", ["pub", "cache", "clean", "--force"], pub, RiskLevel.AGGRESSIVE, dart)
        notes.append("Docker/Podman images and volumes are intentionally never auto-pruned because they may contain irreplaceable local data.")
        return ScanResult(sorted(items, key=lambda item: -item.estimated_bytes), notes)


def scan_installers(older_than_days: int = 30) -> ScanResult:
    cutoff = time.time() - max(0, older_than_days) * 86400
    extensions = {".dmg", ".pkg", ".mpkg", ".xip", ".iso", ".ipsw"}
    items = []
    for root in (Path.home() / "Downloads", Path.home() / "Desktop"):
        try:
            candidates = [path for path in root.rglob("*") if len(path.relative_to(root).parts) <= 3]
        except OSError:
            continue
        for path in candidates:
            try:
                old = path.stat().st_mtime < cutoff
            except OSError:
                continue
            if old and path.is_file() and path.suffix.lower() in extensions:
                items.append(CleanupItem(CleanupCategory.INSTALLERS, path.name, path, size_of(path), RiskLevel.SAFE, "Old installer image; moved to Trash.", CleanupAction(ActionType.MOVE_TO_TRASH)))
    return ScanResult(sorted(items, key=lambda item: -item.estimated_bytes))


def scan_leftovers(config: Config | None = None, older_than_days: int = 30, include_data: bool = False) -> ScanResult:
    config = config or Config()
    installed_ids: set[str] = set()
    for root in (Path("/Applications"), Path.home() / "Applications"):
        try:
            apps = root.rglob("*.app")
            for app in apps:
                try:
                    import plistlib
                    with (app / "Contents/Info.plist").open("rb") as handle:
                        bundle_id = str(plistlib.load(handle).get("CFBundleIdentifier", ""))
                    if len(bundle_id.split(".")) >= 2:
                        installed_ids.add(bundle_id.lower())
                except (OSError, plistlib.InvalidFileException):
                    pass
        except OSError:
            pass
    cutoff = time.time() - max(0, older_than_days) * 86400
    roots = [
        (Path.home() / "Library/Caches", RiskLevel.SAFE),
        (Path.home() / "Library/Logs", RiskLevel.SAFE),
        (Path.home() / "Library/Saved Application State", RiskLevel.MODERATE),
    ]
    if include_data:
        roots.append((Path.home() / "Library/Application Support", RiskLevel.MANUAL_ONLY))
    items = []
    for root, risk in roots:
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for path in children:
            name = path.name.removesuffix(".savedState").lower()
            try:
                if path.stat().st_mtime >= cutoff:
                    continue
            except OSError:
                continue
            if name in installed_ids or config.is_whitelisted(path):
                continue
            if not (name.startswith(("com.", "org.", "io.", "net.")) or path.name.endswith(".savedState")):
                continue
            action = ActionType.REMOVE_PATH if risk is not RiskLevel.MANUAL_ONLY else ActionType.MANUAL_CACHE_FALLBACK
            items.append(CleanupItem(CleanupCategory.LEFTOVERS, path.name, path, size_of(path), risk, "No matching installed app was found; exact identifier-shaped leftover.", CleanupAction(action)))
    return ScanResult(sorted(items, key=lambda item: -item.estimated_bytes))
