from __future__ import annotations

import os
import ctypes
import re
import signal
import stat
import shutil
import subprocess
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


@dataclass(frozen=True, slots=True)
class CommandResult:
    status: int
    stdout: str = ""
    stderr: str = ""

    @property
    def succeeded(self) -> bool:
        return self.status == 0


def run_command(
    executable: str,
    arguments: Iterable[str] = (),
    *,
    timeout: float = 120,
    on_wait: Callable[[], None] | None = None,
) -> CommandResult:
    try:
        process = subprocess.Popen(
            [executable, *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            shell=False,
        )
    except OSError as exc:
        return CommandResult(127, stderr=str(exc))
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                stdout, stderr = process.communicate(timeout=min(0.1, max(0.001, deadline - time.monotonic())))
                return CommandResult(process.returncode, stdout.strip(), stderr.strip())
            except subprocess.TimeoutExpired:
                if time.monotonic() >= deadline:
                    _kill_command_group(process)
                    return CommandResult(124, stderr="Command timed out")
                if on_wait:
                    on_wait()
    except BaseException:
        _kill_command_group(process)
        raise


def _kill_command_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        # A detached descendant may retain the pipes after the owned group exits.
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
        process.wait(timeout=5)


def which(name: str) -> str | None:
    return shutil.which(name)


def process_running(needle: str) -> bool:
    pgrep = which("pgrep") or "/usr/bin/pgrep"
    result = run_command(pgrep, ["-f", "--", re.escape(needle)], timeout=5)
    if result.status not in (0, 1):
        raise PermissionError("Cannot determine whether the application is running")
    return result.status == 0


def size_of(path: Path, *, cancel: Callable[[], None] | None = None,
            on_error: Callable[[Path, str], None] | None = None) -> int:
    if cancel:
        cancel()
    if not path.exists() and not path.is_symlink():
        return 0
    du = run_command("/usr/bin/du", ["-sk", str(path)], timeout=180, on_wait=cancel)
    if not du.succeeded:
        if on_error:
            on_error(path, du.stderr or du.stdout or "disk usage measurement failed")
        return 0
    try:
        return int(du.stdout.split()[0]) * 1024
    except (IndexError, ValueError):
        if on_error:
            on_error(path, "invalid disk usage measurement")
        return 0


def sizes_of(paths: Iterable[Path], max_workers: int = 4,
             cancel: Callable[[], None] | None = None,
             on_error: Callable[[Path, str], None] | None = None) -> dict[Path, int]:
    pending_paths = iter(sorted(set(paths), key=str))
    worker_count = min(max(1, max_workers), 8)
    results: dict[Path, int] = {}
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = {}
        for _ in range(worker_count):
            path = next(pending_paths, None)
            if path is None:
                break
            if cancel:
                cancel()
            futures[pool.submit(size_of, path, cancel=cancel, on_error=on_error)] = path
        while futures:
            if cancel:
                cancel()
            completed, _ = wait(futures, timeout=0.1, return_when=FIRST_COMPLETED)
            for future in completed:
                path = futures.pop(future)
                results[path] = future.result()
                next_path = next(pending_paths, None)
                if next_path is not None:
                    if cancel:
                        cancel()
                    futures[pool.submit(size_of, next_path, cancel=cancel, on_error=on_error)] = next_path
    return results


@contextmanager
def directory_fd(path: Path):
    """Open every directory component without following links, pinning the parent."""
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("absolute lexical directory required")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        os.close(fd)


def remove_validated_path(path: Path, authorize: Callable[[], None]) -> None:
    """Deletion anchored to a no-follow directory descriptor (no path fallback)."""
    if not shutil.rmtree.avoids_symlink_attacks:
        raise PermissionError("Safe descriptor-based deletion is unavailable")
    with directory_fd(path.parent) as fd:
        authorize()
        try:
            info = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if info.st_uid != os.getuid():
            raise PermissionError("target is not owned by the current user")
        if stat.S_ISDIR(info.st_mode):
            shutil.rmtree(path.name, dir_fd=fd)
        else:
            os.unlink(path.name, dir_fd=fd)
        try:
            os.stat(path.name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise RuntimeError("target still exists after deletion")


def move_to_trash_exclusive(path: Path, destination: Path, authorize: Callable[[], None]) -> None:
    """macOS atomic no-overwrite rename; unsupported/cross-volume moves fail closed."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, "renameatx_np", None)
    if rename is None:
        raise PermissionError("Atomic exclusive Trash moves are unavailable on this platform")
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    with directory_fd(path.parent) as source_fd, directory_fd(destination.parent) as trash_fd:
        authorize()
        source = os.stat(path.name, dir_fd=source_fd, follow_symlinks=False)
        if stat.S_ISLNK(source.st_mode) or source.st_uid != os.getuid():
            raise PermissionError("Trash target changed or is not owned by the current user")
        # RENAME_EXCL, documented in macOS sys/stdio.h. Never fall back to overwrite/copy.
        if rename(source_fd, os.fsencode(path.name), trash_fd, os.fsencode(destination.name), 0x00000004):
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code), str(path))
        moved = os.stat(destination.name, dir_fd=trash_fd, follow_symlinks=False)
        if (source.st_dev, source.st_ino) != (moved.st_dev, moved.st_ino):
            raise RuntimeError("Trash target identity changed during move")
        try:
            os.stat(path.name, dir_fd=source_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise RuntimeError("Trash source still exists after move")


def unique_trash_destination(path: Path) -> Path:
    trash = Path.home() / ".Trash"
    candidate = trash / path.name
    counter = 1
    while candidate.exists() or candidate.is_symlink():
        candidate = trash / f"{path.name} {counter}"
        counter += 1
    return candidate


def human_bytes(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TB"


def is_interactive() -> bool:
    return os.isatty(0) and os.isatty(1)
