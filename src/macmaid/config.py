from __future__ import annotations

import fnmatch
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path


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

    def patterns(self, *, strict: bool = False) -> list[str]:
        try:
            if strict:
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
        value = str(path.expanduser().absolute())
        for pattern in self.patterns():
            prefix = pattern.rstrip("/")
            if value == prefix or value.startswith(prefix + "/") or fnmatch.fnmatch(value, pattern):
                return True
        return False
