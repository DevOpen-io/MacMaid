from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .cancellation import CancellationToken
from .models import ActionType, CleanupAction, CleanupCategory, CleanupItem, RiskLevel, ScanResult
from .system import human_bytes, process_running, size_of

SAFE_CACHE_KINDS = {"Cache", "Code Cache", "GPU Cache"}
USER_DATA_KINDS = {"Service Workers", "IndexedDB", "Local Storage", "Cookies", "Sessions"}


@dataclass(frozen=True, slots=True)
class BrowserDefinition:
    name: str
    root: Path
    process: str
    profile_names: tuple[str, ...] = ("Default", "Guest Profile", "System Profile")
    profile_prefixes: tuple[str, ...] = ("Profile ",)


@dataclass(frozen=True, slots=True)
class BrowserStorageArea:
    browser: str
    profile: str
    kind: str
    path: Path
    bytes: int
    risk: RiskLevel
    cleanable: bool
    reason: str
    requires_app_closed: str | None = None

    def web_dict(self) -> dict:
        return {"browser": self.browser, "profile": self.profile, "kind": self.kind,
                "path": str(self.path), "bytes": self.bytes, "humanBytes": human_bytes(self.bytes),
                "risk": "MANUAL" if self.risk is RiskLevel.MANUAL_ONLY else self.risk.name,
                "cleanable": self.cleanable, "selectedByDefault": self.cleanable,
                "reason": self.reason, "requiresAppClosed": self.requires_app_closed or ""}


class BrowserStorageInspector:
    def __init__(self) -> None:
        home = Path.home()
        self.issues: list[str] = []
        self.browsers = [
            BrowserDefinition("Safari", home / "Library/Safari", "Safari.app", ("Default",), ()),
            BrowserDefinition("Google Chrome", home / "Library/Application Support/Google/Chrome", "Google Chrome.app"),
            BrowserDefinition("Chromium", home / "Library/Application Support/Chromium", "Chromium.app"),
            BrowserDefinition("Brave", home / "Library/Application Support/BraveSoftware/Brave-Browser", "Brave Browser.app"),
            BrowserDefinition("Microsoft Edge", home / "Library/Application Support/Microsoft Edge", "Microsoft Edge.app"),
            BrowserDefinition("Arc", home / "Library/Application Support/Arc/User Data", "Arc.app"),
            BrowserDefinition("Firefox", home / "Library/Application Support/Firefox/Profiles", "Firefox.app", (), ()),
        ]

    def scan(self, *, cancellation: CancellationToken | None = None) -> list[BrowserStorageArea]:
        token = cancellation or CancellationToken()
        self.issues = []
        areas: list[BrowserStorageArea] = []
        for browser in self.browsers:
            token.check()
            if not browser.root.exists() and not (browser.name == "Safari" and (Path.home() / "Library/Caches/com.apple.Safari").exists()):
                continue
            for profile in self._profiles(browser):
                token.check()
                areas.extend(self._areas(browser, profile, token))
        return sorted(areas, key=lambda item: (item.browser, item.profile, item.kind))

    def scan_result(self, *, cancellation: CancellationToken | None = None,
                    areas: list[BrowserStorageArea] | None = None) -> ScanResult:
        areas = self.scan(cancellation=cancellation) if areas is None else areas
        items = [self._cleanup_item(area) for area in areas if area.cleanable]
        notes = ["Some browser data was not fully accessible; grant Full Disk Access for complete coverage."] if self.issues else []
        return ScanResult(items=items, notes=notes, status="complete", issues=list(self.issues))

    def _profiles(self, browser: BrowserDefinition) -> Iterable[Path]:
        if browser.name == "Safari":
            yield browser.root
            return
        try:
            children = list(browser.root.iterdir())
        except OSError as exc:
            self.issues.append(f"{browser.name}: {browser.root}: {exc}")
            return
        if browser.name == "Firefox":
            profiles = [item for item in children if item.is_dir() and not item.is_symlink()]
            if not profiles:
                self.issues.append(f"{browser.name}: no profiles found under {browser.root}")
            yield from profiles
            return
        matched = [child for child in children
                   if child.is_dir() and not child.is_symlink()
                   and (child.name in browser.profile_names or any(child.name.startswith(prefix) for prefix in browser.profile_prefixes))]
        if not matched:
            self.issues.append(f"{browser.name}: no profiles found under {browser.root}")
        yield from matched

    def _present(self, path: Path) -> bool:
        try:
            path.lstat()
            return True
        except FileNotFoundError:
            return False
        except PermissionError as exc:
            self.issues.append(f"{path}: {exc}")
            return False
        except OSError:
            return False

    def _areas(self, browser: BrowserDefinition, profile: Path, token: CancellationToken) -> list[BrowserStorageArea]:
        running = browser.name if process_running(browser.process) else None
        if browser.name == "Safari":
            specs = [
                ("Cache", Path.home() / "Library/Caches/com.apple.Safari", True, RiskLevel.MODERATE, "Safari cache; website data excluded."),
                ("Service Workers", profile / "ServiceWorkers", False, RiskLevel.AGGRESSIVE, "Can contain offline site data; not selected automatically."),
                ("Local Storage", profile / "LocalStorage", False, RiskLevel.AGGRESSIVE, "Website data; not selected automatically."),
                ("Cookies", profile / "Cookies", False, RiskLevel.MANUAL_ONLY, "Cookies are user data; never Smart Cleaned."),
            ]
        elif browser.name == "Firefox":
            cache_profile = Path.home() / "Library/Caches/Firefox/Profiles" / profile.name
            specs = [
                ("Cache", cache_profile, True, RiskLevel.SAFE, "Firefox cache domain, not profile data."),
                ("Service Workers", profile / "storage/default", False, RiskLevel.AGGRESSIVE, "Can contain offline site data; not selected automatically."),
                ("IndexedDB", profile / "storage/default", False, RiskLevel.AGGRESSIVE, "Site databases; not selected automatically."),
                ("Cookies", profile / "cookies.sqlite", False, RiskLevel.MANUAL_ONLY, "Cookies are user data; never Smart Cleaned."),
                ("Sessions", profile / "sessionstore-backups", False, RiskLevel.MANUAL_ONLY, "Sessions are user data; never Smart Cleaned."),
            ]
        else:
            specs = [
                ("Cache", profile / "Cache", True, RiskLevel.SAFE, "Browser cache only; history, cookies and site data excluded."),
                ("Code Cache", profile / "Code Cache", True, RiskLevel.SAFE, "Recreatable browser code cache."),
                ("GPU Cache", profile / "GPUCache", True, RiskLevel.SAFE, "Recreatable GPU cache."),
                ("Service Workers", profile / "Service Worker", False, RiskLevel.AGGRESSIVE, "May contain offline site data; not selected automatically."),
                ("IndexedDB", profile / "IndexedDB", False, RiskLevel.AGGRESSIVE, "Site databases; not selected automatically."),
                ("Local Storage", profile / "Local Storage", False, RiskLevel.AGGRESSIVE, "Site local storage; not selected automatically."),
                ("Cookies", profile / "Cookies", False, RiskLevel.MANUAL_ONLY, "Cookies are user data; never Smart Cleaned."),
                ("Sessions", profile / "Sessions", False, RiskLevel.MANUAL_ONLY, "Sessions are user data; never Smart Cleaned."),
            ]
        areas = []
        for kind, path, cleanable, risk, reason in specs:
            token.check()
            if not self._present(path):
                continue
            areas.append(BrowserStorageArea(browser.name, profile.name, kind, path,
                                            size_of(path, cancel=token.check, on_error=lambda target, message: self.issues.append(f"{target}: {message}")),
                                            risk, cleanable, reason, running if cleanable else None))
        return areas

    @staticmethod
    def _cleanup_item(area: BrowserStorageArea) -> CleanupItem:
        return CleanupItem(CleanupCategory.BROWSER_CACHES, f"{area.browser} · {area.profile} · {area.kind}",
                           area.path, area.bytes, area.risk, area.reason,
                           CleanupAction(ActionType.REMOVE_PATH), area.requires_app_closed)
