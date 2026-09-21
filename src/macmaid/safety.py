from __future__ import annotations

import os
import re
from pathlib import Path


class PathSafetyError(ValueError):
    pass


class PathSafety:
    HARD_BLOCKED = {
        Path("/"), Path("/System"), Path("/bin"), Path("/sbin"), Path("/usr"),
        Path("/etc"), Path("/var"), Path("/private"), Path("/Library"),
        Path("/Applications"), Path("/Users"), Path("/Volumes"),
    }

    def __init__(self, extra_allowed_roots: list[Path] | None = None) -> None:
        home = Path.home()
        self.allowed_roots = [
            home / "Library/Caches", home / "Library/Logs", home / "Library/DiagnosticReports",
            home / "Library/Saved Application State", home / "Library/Developer/Xcode/DerivedData",
            home / "Library/Developer/CoreSimulator/Caches", home / ".npm",
            home / ".gradle/caches", home / ".m2/repository", home / ".cargo/registry/cache",
            home / ".cargo/git/db", home / ".bun/install/cache", home / "Library/pnpm/store",
            home / ".pub-cache", home / ".Trash", *(extra_allowed_roots or []),
        ]

    @staticmethod
    def _lexical(raw: str | Path) -> Path:
        text = os.path.expanduser(str(raw))
        if not text or any(char in text for char in ("\0", "\n", "\r")):
            raise PathSafetyError("empty or suspicious path")
        if not text.startswith("/") or ".." in Path(text).parts:
            raise PathSafetyError(f"suspicious path: {text}")
        return Path(os.path.normpath(text))

    @staticmethod
    def _inside(path: Path, root: Path) -> bool:
        return path == root or root in path.parents

    @staticmethod
    def _reject_symlink_ancestors(path: Path) -> None:
        current = path.parent
        while current != current.parent:
            if current.is_symlink():
                raise PathSafetyError(f"symlinked ancestor is not allowed: {current}")
            current = current.parent

    def validate_deletion_path(self, raw: str | Path) -> Path:
        path = self._lexical(raw)
        if path in self.HARD_BLOCKED:
            raise PathSafetyError(f"protected path: {path}")
        allowed = any(self._inside(path, root) for root in self.allowed_roots)
        allowed |= str(path).startswith("/private/tmp/") or str(path).startswith("/private/var/tmp/")
        allowed |= self._allowed_sandbox_cache(path)
        allowed |= self._allowed_app_support_cache(path)
        if not allowed:
            raise PathSafetyError(f"outside cleanup roots: {path}")
        self._reject_symlink_ancestors(path)
        return path

    def validate_trash_candidate(self, raw: str | Path) -> Path:
        path = self._lexical(raw)
        roots = (Path.home() / "Downloads", Path.home() / "Desktop")
        if not any(root in path.parents for root in roots):
            raise PathSafetyError(f"outside Trash candidate roots: {path}")
        self._reject_symlink_ancestors(path)
        return path

    @staticmethod
    def validate_analyzer_candidate(raw: str | Path) -> Path:
        path = PathSafety._lexical(raw)
        home = Path.home()
        if home not in path.parents or path == home:
            raise PathSafetyError("analyzer target must be an item below the current user's home")
        protected = [home / name for name in ("Library", "Applications", "Public", "Desktop", "Documents", "Downloads", "Pictures", "Movies", "Music")]
        if any(path == root for root in protected):
            raise PathSafetyError(f"protected home anchor: {path}")
        if home / "Library" in path.parents:
            raise PathSafetyError(f"protected Library content: {path}")
        if any(part.lower().endswith((".app", ".photoslibrary")) for part in path.relative_to(home).parts):
            raise PathSafetyError(f"protected bundle/library: {path}")
        PathSafety._reject_symlink_ancestors(path)
        try:
            if path.stat().st_uid != os.getuid():
                raise PathSafetyError(f"analyzer target is not owned by the current user: {path}")
        except OSError as exc:
            raise PathSafetyError(f"analyzer target is unavailable: {path}") from exc
        return path

    @staticmethod
    def _allowed_sandbox_cache(path: Path) -> bool:
        root = Path.home() / "Library/Containers"
        try:
            parts = path.relative_to(root).parts
        except ValueError:
            return False
        return len(parts) >= 4 and parts[1:4] == ("Data", "Library", "Caches")

    @staticmethod
    def _allowed_app_support_cache(path: Path) -> bool:
        home = Path.home()
        browser_roots = [
            home / "Library/Application Support/Google/Chrome",
            home / "Library/Application Support/Chromium",
            home / "Library/Application Support/BraveSoftware/Brave-Browser",
            home / "Library/Application Support/Microsoft Edge",
        ]
        leaves = {"Cache", "Code Cache", "GPUCache", "DawnCache", "GrShaderCache", "ShaderCache", "Media Cache"}
        for root in browser_roots:
            try:
                profile, leaf = path.relative_to(root).parts
            except (ValueError, TypeError):
                continue
            if (profile in {"Default", "Guest Profile", "System Profile"} or re.fullmatch(r"Profile \d+", profile)) and leaf in leaves:
                return True
        app_roots = [home / f"Library/Application Support/{name}" for name in ("Code", "Code - Insiders", "Cursor", "Slack", "discord", "Spotify")]
        app_leaves = leaves | {"Caches", "CachedData", "CachedExtensionVSIXs", "CachedProfilesData", "logs"}
        return any(path.parent == root and path.name in app_leaves for root in app_roots)


def manual_cache_allowed(manager: str, path: Path) -> bool:
    home = Path.home(); path = Path(os.path.normpath(str(path.expanduser())))
    exact = {
        "pipx": [home / ".local/pipx/.cache", home / "Library/Caches/pipx", home / ".cache/pipx"],
        "pip": [home / "Library/Caches/pip", home / ".cache/pip"],
        "npm": [home / ".npm", home / ".npm/_npx", home / ".npm/_libvips", home / ".npm/_logs"],
        "bun": [home / ".bun/install/cache"],
        "go": [home / "Library/Caches/go-build", home / ".cache/go-build"],
        "brew-downloads": [home / "Library/Caches/Homebrew", home / ".cache/Homebrew"],
        "gradle": [home / ".gradle/caches"], "cargo-registry": [home / ".cargo/registry/cache"],
        "cargo-git": [home / ".cargo/git/db"], "pixi": [home / "Library/Caches/pixi", home / ".cache/pixi"],
        "rattler": [home / "Library/Caches/rattler", home / ".cache/rattler"],
    }
    if path in exact.get(manager.lower(), []): return True
    roots = {
        "pnpm": [home / "Library/pnpm/store", home / ".local/share/pnpm/store"],
        "yarn-classic": [home / "Library/Caches/Yarn", home / ".cache/yarn"],
        "composer": [home / "Library/Caches/composer", home / ".cache/composer"],
    }
    return any(path == root or root in path.parents for root in roots.get(manager.lower(), []))
