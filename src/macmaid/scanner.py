from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

from .cancellation import CancellationToken, ScanCancelled
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
        self._cancellation: CancellationToken | None = None
        self._issues: list[str] = []

    def scan(
        self,
        profile: CleanupProfile = CleanupProfile.SAFE,
        *,
        include_trash: bool = False,
        include_system_temp: bool = False,
        progress: Progress | None = None,
        cancellation: CancellationToken | None = None,
    ) -> ScanResult:
        self._progress = progress
        self._cancellation = cancellation or CancellationToken()
        self._issues = []
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
                ("Package-manager caches", lambda: PackageManagerCacheScanner(self.config).scan(self._cancellation).items),
            ])
        if profile in (CleanupProfile.DEEP, CleanupProfile.AGGRESSIVE):
            phases.append(("Saved application state", self._saved_state))
        if include_system_temp and profile in (CleanupProfile.DEEP, CleanupProfile.AGGRESSIVE):
            phases.append(("Temporary files", lambda: self._temporary(profile)))
        if include_trash:
            phases.append(("Trash", self._trash))

        result = ScanResult(status="scanning")
        try:
            for index, (name, operation) in enumerate(phases):
                self._check_cancelled()
                self._emit(index, len(phases), name, "")
                result.items.extend(operation())
                self._check_cancelled()
                self._emit(index + 1, len(phases), name, "")
        except ScanCancelled:
            result.status = "cancelled"
        seen: set[tuple[str, str, str]] = set()
        unique: list[CleanupItem] = []
        for item in result.items:
            key = (item.category.value, str(item.path or ""), item.action.kind.value)
            if key not in seen:
                seen.add(key)
                unique.append(item)
        result.items = sorted(unique, key=lambda item: (item.category.value, -item.estimated_bytes))
        result.issues = list(self._issues)
        if result.status != "cancelled":
            result.status = "partial" if result.issues else "complete"
            if self._progress:
                self._progress(100, "Partial" if result.issues else "Complete", "")
        else:
            result.notes.append("Scan cancelled; results are incomplete and cannot be cleaned without explicit partial-result authorization.")
        if result.issues:
            result.notes.append(f"Scan incomplete: {len(result.issues)} location(s) could not be read or measured.")
            if any("Operation not permitted" in issue or "Permission denied" in issue for issue in result.issues):
                result.notes.append("macOS privacy/TCC may have blocked access; grant Full Disk Access only if you choose to scan those locations.")
        return result

    def _check_cancelled(self) -> None:
        if self._cancellation:
            self._cancellation.check()

    def _issue(self, path: Path, exc: OSError) -> None:
        if not isinstance(exc, FileNotFoundError):
            self._issues.append(f"{path}: {exc}")

    def _measurement_issue(self, path: Path, message: str) -> None:
        self._issues.append(f"{path}: {message}")

    def _emit(self, current: int, total: int, phase: str, path: str | Path) -> None:
        self._check_cancelled()
        if self._progress:
            self._progress(min(99, int(current / max(total, 1) * 100)), phase, str(path))

    def _candidates(
        self,
        specs: Iterable[tuple[str, Path, RiskLevel, str, ActionType, str | None]],
        category: CleanupCategory,
        maximum: RiskLevel,
    ) -> list[CleanupItem]:
        accepted = []
        for spec in specs:
            self._check_cancelled()
            if spec[2] <= maximum and spec[1].exists() and not self.config.is_whitelisted(spec[1]):
                accepted.append(spec)
        measured = sizes_of((spec[1] for spec in accepted), cancel=self._check_cancelled, on_error=self._measurement_issue)
        return [
            CleanupItem(category, label, path, measured.get(path, 0), risk, reason, CleanupAction(action), app)
            for label, path, risk, reason, action, app in accepted if measured.get(path, 0) > 0
        ]

    def _user_caches(self, profile: CleanupProfile) -> list[CleanupItem]:
        root = Path.home() / "Library/Caches"
        protected_names = {"CloudKit", "FamilyCircle"}
        separate = {"Firefox", "com.apple.Safari", "com.apple.dt.Xcode", "CocoaPods", "org.swift.swiftpm", "org.carthage.CarthageKit"}
        specs = []
        try:
            children = list(root.iterdir())
        except OSError as exc:
            self._issue(root, exc)
            return []
        for child in children:
            self._check_cancelled()
            if child.name in separate or child.name in protected_names or child.name.startswith("com.apple."):
                continue
            specs.append((child.name, child, RiskLevel.SAFE, "Application cache location; contents should be recreatable.", ActionType.REMOVE_PATH, None))
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
            except OSError as exc:
                self._issue(root, exc)
                continue
            for user_profile in profiles:
                self._check_cancelled()
                for leaf in leaves:
                    path = user_profile / leaf
                    specs.append((f"{name} · {user_profile.name} · {leaf}", path, RiskLevel.SAFE, "Browser cache only; history, cookies and site data are excluded.", ActionType.REMOVE_PATH, running))
        firefox = home / "Library/Caches/Firefox/Profiles"
        if firefox.exists():
            try:
                for path in firefox.iterdir():
                    specs.append(("Firefox profile cache", path, RiskLevel.SAFE, "Firefox cache domain, not profile data.", ActionType.REMOVE_PATH, "Firefox" if process_running("Firefox.app") else None))
            except OSError as exc:
                self._issue(firefox, exc)
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
            self._check_cancelled()
            root = home / "Library/Application Support" / folder
            running = name if process_running(process) else None
            for leaf in leaves:
                specs.append((f"{name} · {leaf}", root / leaf, RiskLevel.SAFE, "Known disposable app cache/log leaf; databases and user state are excluded.", ActionType.REMOVE_PATH, running))
        return self._candidates(specs, CleanupCategory.APP_CACHES, profile.maximum_risk)

    def _sandbox_caches(self, profile: CleanupProfile) -> list[CleanupItem]:
        root = Path.home() / "Library/Containers"
        try:
            containers = list(root.iterdir())
        except OSError as exc:
            self._issue(root, exc)
            return []
        specs = []
        for container in containers:
            self._check_cancelled()
            if container.name.startswith("com.apple."):
                continue
            specs.append((f"Sandbox cache · {container.name}", container / "Data/Library/Caches", RiskLevel.SAFE, "Only Data/Library/Caches contents are removed.", ActionType.REMOVE_CHILDREN, None))
        return self._candidates(specs, CleanupCategory.APP_CACHES, profile.maximum_risk)

    def _logs(self, profile: CleanupProfile) -> list[CleanupItem]:
        cutoff = time.time() - (7 if profile is CleanupProfile.SAFE else 1) * 86400
        specs = []
        for root in (Path.home() / "Library/Logs", Path.home() / "Library/DiagnosticReports"):
            self._check_cancelled()
            try:
                children = list(root.iterdir())
            except OSError as exc:
                self._issue(root, exc)
                continue
            for path in children:
                self._check_cancelled()
                try:
                    if path.stat().st_mtime > cutoff or path == self.config.log_dir:
                        continue
                except OSError as exc:
                    self._issue(path, exc)
                    continue
                specs.append((path.name, path, RiskLevel.SAFE, "Old log or diagnostic data.", ActionType.REMOVE_PATH, None))
        return self._candidates(specs, CleanupCategory.LOGS, profile.maximum_risk)

    def _saved_state(self) -> list[CleanupItem]:
        root = Path.home() / "Library/Saved Application State"
        try:
            paths = list(root.iterdir())
        except OSError as exc:
            self._issue(root, exc)
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
            self._check_cancelled()
            try:
                children = list(root.iterdir())
            except OSError as exc:
                self._issue(root, exc)
                continue
            for path in children:
                self._check_cancelled()
                try:
                    stat = path.lstat()
                except OSError as exc:
                    self._issue(path, exc)
                    continue
                if stat.st_uid == os.getuid() and stat.st_mtime < cutoff:
                    specs.append((path.name, path, RiskLevel.MODERATE, "Aged temporary item owned by the current user.", ActionType.REMOVE_PATH, None))
        return self._candidates(specs, CleanupCategory.TEMPORARY, profile.maximum_risk)

    def _trash(self) -> list[CleanupItem]:
        path = Path.home() / ".Trash"
        size = size_of(path, cancel=self._check_cancelled, on_error=self._measurement_issue)
        if not size or self.config.is_whitelisted(path):
            return []
        return [CleanupItem(CleanupCategory.TRASH, "User Trash", path, size, RiskLevel.MODERATE, "Deletes items already in Trash.", CleanupAction(ActionType.REMOVE_CHILDREN))]


class PackageManagerCacheScanner:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()

    def scan(self, cancellation: CancellationToken | None = None) -> ScanResult:
        home = Path.home()
        token = cancellation or CancellationToken()
        items: list[CleanupItem] = []; notes: list[str] = []; issues: list[str] = []

        def probe(executable: str, arguments: list[str], timeout: float = 10):
            token.check()
            return run_command(executable, arguments, timeout=timeout, on_wait=token.check)

        def native(label: str, manager: str, arguments: list[str], path: Path | None, risk: RiskLevel = RiskLevel.MODERATE, executable: str | None = None) -> None:
            token.check()
            command = executable or which(manager)
            if not command or (path and self.config.is_whitelisted(path)): return
            size = size_of(path, cancel=token.check, on_error=lambda target, message: issues.append(f"{target}: {message}")) if path else 0
            items.append(CleanupItem(CleanupCategory.PACKAGE_MANAGERS, label, path, size, risk, f"Uses {manager}'s supported cleanup operation; project data is outside this target.", CleanupAction(ActionType.COMMAND, command, arguments)))

        def manual(label: str, manager: str, path: Path) -> None:
            token.check()
            if not path.exists() or self.config.is_whitelisted(path): return
            size = size_of(path, cancel=token.check, on_error=lambda target, message: issues.append(f"{target}: {message}"))
            if size: items.append(CleanupItem(CleanupCategory.PACKAGE_MANAGERS, label + " · manual fallback", path, size, RiskLevel.MANUAL_ONLY, "Default OFF; requires a second interactive confirmation and a strict cache-only allowlist.", CleanupAction(ActionType.MANUAL_CACHE_FALLBACK, fallback_manager=manager)))

        brew = which("brew")
        if brew:
            raw = probe(brew, ["--cache"]).stdout
            native("Homebrew cleanup", "brew", ["cleanup", "--prune=all"], Path(raw) if raw.startswith("/") else home / "Library/Caches/Homebrew", RiskLevel.SAFE, brew)
        pnpm = which("pnpm")
        if pnpm:
            raw = probe(pnpm, ["store", "path"]).stdout
            native("pnpm store prune", "pnpm", ["store", "prune"], Path(raw) if raw.startswith("/") else home / "Library/pnpm/store", RiskLevel.SAFE, pnpm)
        uv = which("uv")
        if uv:
            raw = probe(uv, ["cache", "dir"]).stdout
            native("uv cache prune", "uv", ["cache", "prune"], Path(raw) if raw.startswith("/") else None, RiskLevel.SAFE, uv)
        go = which("go")
        if go:
            raw = probe(go, ["env", "GOCACHE"]).stdout
            native("Go build/test cache", "go", ["clean", "-cache", "-testcache"], Path(raw) if raw.startswith("/") else None, RiskLevel.SAFE, go)
        bun = which("bun")
        if bun:
            raw = probe(bun, ["pm", "cache"]).stdout
            native("Bun package cache", "bun", ["pm", "cache", "rm"], Path(raw) if raw.startswith("/") else home / ".bun/install/cache", RiskLevel.MODERATE, bun)
        python = which("python3")
        if python:
            raw = probe(python, ["-m", "pip", "cache", "dir"]).stdout
            if raw.startswith("/"): native("Python pip cache", "pip", ["-m", "pip", "cache", "purge"], Path(raw), RiskLevel.MODERATE, python)
        yarn = which("yarn")
        if yarn:
            version = probe(yarn, ["--version"]).stdout
            if version.startswith("1."):
                raw = probe(yarn, ["cache", "dir"]).stdout
                native("Yarn Classic cache", "yarn", ["cache", "clean"], Path(raw) if raw.startswith("/") else None, RiskLevel.MODERATE, yarn)
            else: notes.append(f"Yarn {version} uses project-aware Berry cache semantics and is inventory-only.")
        composer = which("composer")
        if composer:
            raw = probe(composer, ["config", "cache-dir", "--global"]).stdout
            native("Composer cache clear", "composer", ["clear-cache"], Path(raw) if raw.startswith("/") else None, RiskLevel.MODERATE, composer)
        dotnet = which("dotnet")
        if dotnet:
            for location in ("http-cache", "temp", "plugins-cache"):
                native(f".NET / NuGet {location}", "dotnet", ["nuget", "locals", location, "--clear"], None, RiskLevel.MODERATE, dotnet)
        npm = which("npm")
        if npm:
            raw = probe(npm, ["config", "get", "cache"]).stdout
            native("npm cache clean", "npm", ["cache", "clean", "--force"], Path(raw) if raw.startswith("/") else home / ".npm", RiskLevel.AGGRESSIVE, npm)
        conda = which("conda")
        if conda:
            try: roots = [Path(p) for p in __import__("json").loads(probe(conda, ["info", "--json"], 20).stdout).get("pkgs_dirs", [])]
            except ScanCancelled: raise
            except Exception: roots = []
            native("Conda package/index caches", "conda", ["clean", "--all", "-y"], roots[0] if roots else None, RiskLevel.MODERATE, conda)
        micromamba = which("micromamba")
        if micromamba: native("Micromamba package caches", "micromamba", ["clean", "--all", "--yes"], Path(os.environ.get("MAMBA_ROOT_PREFIX", home / "micromamba")) / "pkgs", RiskLevel.MODERATE, micromamba)
        pipx = which("pipx")
        if pipx:
            cache = home / ".cache/pipx"
            pipx_probe = probe(pipx, ["cache", "dir"])
            if pipx_probe.succeeded: native("pipx run cache", "pipx", ["cache", "purge"], Path(pipx_probe.stdout), RiskLevel.SAFE, pipx)
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
        if maven.exists(): notes.append(f"Maven local repository ({size_of(maven, cancel=token.check, on_error=lambda target, message: issues.append(f'{target}: {message}'))} bytes) is inventory-only because it may contain locally-installed artifacts.")
        dart = which("dart"); pub = Path(os.environ.get("PUB_CACHE", home / ".pub-cache"))
        if dart and pub.exists(): native("Dart/Flutter pub cache", "dart", ["pub", "cache", "clean", "--force"], pub, RiskLevel.AGGRESSIVE, dart)
        notes.append("Docker/Podman images and volumes are intentionally never auto-pruned because they may contain irreplaceable local data.")
        token.check()
        return ScanResult(sorted(items, key=lambda item: -item.estimated_bytes), notes,
                          status="partial" if issues else "complete", issues=issues)


def scan_installers(older_than_days: int = 30, cancellation: CancellationToken | None = None) -> ScanResult:
    token = cancellation or CancellationToken()
    cutoff = time.time() - max(0, older_than_days) * 86400
    extensions = {".dmg", ".pkg", ".mpkg", ".xip", ".iso", ".ipsw"}
    items = []; issues = []
    for root in (Path.home() / "Downloads", Path.home() / "Desktop"):
        candidates = []
        try:
            for path in root.rglob("*"):
                token.check()
                if len(path.relative_to(root).parts) <= 3:
                    candidates.append(path)
        except FileNotFoundError:
            continue
        except OSError as exc:
            issues.append(f"{root}: {exc}")
        for path in candidates:
            token.check()
            try:
                old = path.stat().st_mtime < cutoff
            except OSError as exc:
                issues.append(f"{path}: {exc}")
                continue
            if old and path.is_file() and path.suffix.lower() in extensions:
                items.append(CleanupItem(CleanupCategory.INSTALLERS, path.name, path, size_of(path, cancel=token.check, on_error=lambda target, message: issues.append(f"{target}: {message}")), RiskLevel.SAFE, "Old installer image; moved to Trash.", CleanupAction(ActionType.MOVE_TO_TRASH)))
    return ScanResult(sorted(items, key=lambda item: -item.estimated_bytes), status="partial" if issues else "complete", issues=issues)


def scan_leftovers(config: Config | None = None, older_than_days: int = 30, include_data: bool = False,
                   cancellation: CancellationToken | None = None) -> ScanResult:
    config = config or Config(); token = cancellation or CancellationToken(); issues: list[str] = []
    installed_ids: set[str] = set()
    for root in (Path("/Applications"), Path.home() / "Applications"):
        try:
            for app in root.rglob("*.app"):
                token.check()
                try:
                    import plistlib
                    with (app / "Contents/Info.plist").open("rb") as handle:
                        bundle_id = str(plistlib.load(handle).get("CFBundleIdentifier", ""))
                    if len(bundle_id.split(".")) >= 2:
                        installed_ids.add(bundle_id.lower())
                except (OSError, plistlib.InvalidFileException):
                    continue
        except FileNotFoundError:
            continue
        except OSError as exc:
            issues.append(f"{root}: {exc}")
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
        token.check()
        try:
            children = list(root.iterdir())
        except FileNotFoundError:
            continue
        except OSError as exc:
            issues.append(f"{root}: {exc}")
            continue
        for path in children:
            token.check()
            name = path.name.removesuffix(".savedState").lower()
            try:
                if path.stat().st_mtime >= cutoff:
                    continue
            except OSError as exc:
                issues.append(f"{path}: {exc}")
                continue
            if name in installed_ids or config.is_whitelisted(path):
                continue
            if not (name.startswith(("com.", "org.", "io.", "net.")) or path.name.endswith(".savedState")):
                continue
            action = ActionType.REMOVE_PATH if risk is not RiskLevel.MANUAL_ONLY else ActionType.MANUAL_CACHE_FALLBACK
            items.append(CleanupItem(CleanupCategory.LEFTOVERS, path.name, path, size_of(path, cancel=token.check, on_error=lambda target, message: issues.append(f"{target}: {message}")), risk, "No matching installed app was found; exact identifier-shaped leftover.", CleanupAction(action)))
    return ScanResult(sorted(items, key=lambda item: -item.estimated_bytes), status="partial" if issues else "complete", issues=issues)
