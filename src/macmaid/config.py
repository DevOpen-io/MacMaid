from __future__ import annotations

import fnmatch
import json
import os
import secrets
import stat
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .i18n import DEFAULT_LANGUAGE, normalize_language


def whitelist_match(path: Path, patterns: Iterable[str]) -> bool:
    """Return True when ``path`` is covered by any whitelist pattern.

    Matching semantics mirror :meth:`Config.is_whitelisted`: exact match,
    literal prefix, or glob. Callers that evaluate many paths should fetch
    ``config.patterns()`` once and reuse the snapshot here.
    """
    value = str(path.expanduser().absolute())
    for pattern in patterns:
        prefix = pattern.rstrip("/")
        if value == prefix or value.startswith(prefix + "/") or fnmatch.fnmatch(value, pattern):
            return True
    return False


@dataclass(frozen=True, slots=True)
class Config:
    home: Path = field(default_factory=Path.home)

    @property
    def config_dir(self) -> Path:
        return self.home / ".config" / "macmaid"

    @property
    def whitelist_file(self) -> Path:
        return self.config_dir / "whitelist"

    @property
    def preferences_file(self) -> Path:
        return self.config_dir / "preferences.json"

    @property
    def log_dir(self) -> Path:
        return self.home / "Library" / "Logs" / "MacMaid"

    @property
    def operation_log(self) -> Path:
        return self.log_dir / "operations.jsonl"

    def _ensure_owned_directory(self, path: Path) -> None:
        home = self.home.absolute()
        path = path.absolute()
        if path != home and home not in path.parents:
            raise PermissionError("MacMaid state directory must remain below HOME")
        home_info = home.lstat()
        if stat.S_ISLNK(home_info.st_mode) or not stat.S_ISDIR(home_info.st_mode) or home_info.st_uid != os.getuid():
            raise PermissionError("HOME must be a user-owned directory, not a symlink")
        current = home
        for part in path.relative_to(home).parts:
            current /= part
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
                raise PermissionError(f"Unsafe MacMaid state directory: {current}")

    def _require_owned_regular_file(self, path: Path, *, allow_missing: bool = False) -> None:
        self._ensure_owned_directory(path.parent)
        try:
            info = path.lstat()
        except FileNotFoundError:
            if allow_missing:
                return
            raise PermissionError(f"Required MacMaid state file is missing: {path}")
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise PermissionError(f"Unsafe MacMaid state file: {path}")

    def ensure_files(self) -> None:
        self._ensure_owned_directory(self.config_dir)
        self._ensure_owned_directory(self.log_dir)
        try:
            fd = os.open(self.whitelist_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            self._require_owned_regular_file(self.whitelist_file)
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write("# One absolute path or glob per line.\n# ~/Library/Caches/com.example.keep\n")
        try:
            fd = os.open(self.preferences_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            self._require_owned_regular_file(self.preferences_file)
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"language": DEFAULT_LANGUAGE}, handle)
                handle.write("\n")

    def preferences(self) -> dict[str, str]:
        self._require_owned_regular_file(self.preferences_file)
        fd = os.open(self.preferences_file, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as handle:
                value = json.load(handle)
        finally:
            os.close(fd)
        if not isinstance(value, dict):
            raise ValueError("Invalid MacMaid preferences")
        return {"language": normalize_language(value.get("language"))}

    def set_language(self, language: str) -> None:
        language = normalize_language(language)
        self._require_owned_regular_file(self.preferences_file)
        temporary = self.config_dir / f".preferences.{os.getpid()}.{secrets.token_hex(8)}.tmp"
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"language": language}, handle)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._require_owned_regular_file(self.preferences_file)
            os.replace(temporary, self.preferences_file)
            self._require_owned_regular_file(self.preferences_file)
        finally:
            temporary.unlink(missing_ok=True)

    def validate_whitelist(self, lines: list[str]) -> list[str]:
        """Validate and normalize user-maintained whitelist entries without writing them."""
        sanitized: list[str] = []
        for raw_line in lines:
            if not isinstance(raw_line, str):
                raise ValueError("Whitelist entries must be text")
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "\x00" in line or "\n" in line or "\r" in line:
                raise ValueError("Whitelist entries must be one line each")
            path = Path(line).expanduser()
            if not path.is_absolute() or ".." in path.parts:
                raise ValueError("Whitelist entries must be absolute paths without '..'")
            sanitized.append(str(path))
        return sanitized

    def replace_whitelist(self, lines: list[str]) -> None:
        """Atomically replace user-maintained whitelist entries after validation."""
        sanitized = self.validate_whitelist(lines)
        self._require_owned_regular_file(self.whitelist_file)
        temporary = self.config_dir / f".whitelist.{os.getpid()}.{secrets.token_hex(8)}.tmp"
        payload = ("\n".join(sanitized) + "\n").encode("utf-8")
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
            self._require_owned_regular_file(self.whitelist_file)
            os.replace(temporary, self.whitelist_file)
            self._require_owned_regular_file(self.whitelist_file)
        finally:
            temporary.unlink(missing_ok=True)

    def patterns(self, *, strict: bool = False) -> list[str]:
        try:
            if strict:
                # Operation-time reads must be fail-closed: the file has to be a
                # regular, user-owned, non-symlinked target.
                self._require_owned_regular_file(self.whitelist_file)
                fd = os.open(self.whitelist_file, os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    info = os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                        raise PermissionError("Unsafe whitelist file")
                    with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as handle:
                        lines = handle.read().splitlines()
                finally:
                    os.close(fd)
            else:
                # Scan-time reads are best-effort filters: follow symlinks so a
                # symlinked whitelist (dotfiles managers) still hides entries.
                lines = self.whitelist_file.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            if strict:
                raise PermissionError("Whitelist cannot be read; operation blocked") from exc
            return []
        patterns = [str(Path(line.strip()).expanduser()) for line in lines if line.strip() and not line.lstrip().startswith("#")]
        if strict and any(not Path(pattern).is_absolute() or ".." in Path(pattern).parts for pattern in patterns):
            raise PermissionError("Whitelist contains an invalid path; operation blocked")
        return patterns

    def require_unprotected(self, path: Path) -> None:
        """Reject protected trees, including potential glob matches below the target.

        A conservative literal prefix avoids traversing huge trees or following links.
        Wildcards may protect more siblings than necessary; never fewer.
        """
        value = str(path)
        for pattern in self.patterns(strict=True):
            prefix = pattern.rstrip("/")
            if value == prefix or value.startswith(prefix + "/") or fnmatch.fnmatch(value, pattern):
                raise PermissionError(f"path is whitelisted: {path}")
            first_glob = min((pattern.find(c) for c in "*?[" if c in pattern), default=-1)
            literal = Path(pattern if first_glob < 0 else pattern[:first_glob].rsplit("/", 1)[0] or "/")
            if path == literal or path in literal.parents or (first_glob >= 0 and literal in path.parents):
                raise PermissionError(f"target may contain whitelisted data: {path}")

    def is_whitelisted(self, path: Path) -> bool:
        return whitelist_match(path, self.patterns())
