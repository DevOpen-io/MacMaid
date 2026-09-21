from __future__ import annotations

import os
import ctypes
import re
import signal
import stat
import shutil
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator


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
    try:
        if on_wait is None:
            try:
                stdout, stderr = process.communicate(timeout=timeout)
                return CommandResult(process.returncode, stdout.strip(), stderr.strip())
            except subprocess.TimeoutExpired:
                _kill_command_group(process)
                return CommandResult(124, stderr="Command timed out")
        deadline = time.monotonic() + timeout
        while True:
            try:
                stdout, stderr = process.communicate(timeout=min(0.1, max(0.001, deadline - time.monotonic())))
                return CommandResult(process.returncode, stdout.strip(), stderr.strip())
            except subprocess.TimeoutExpired:
                if time.monotonic() >= deadline:
                    _kill_command_group(process)
                    return CommandResult(124, stderr="Command timed out")
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


def _directory_access(path: Path) -> str:
    if not path.exists():
        return "not_applicable"
    try:
        with os.scandir(path) as entries:
            next(entries, None)
    except PermissionError:
        return "denied"
    except OSError:
        return "unavailable"
    return "granted"


def macos_permission_report(home: Path | None = None) -> dict:
    """Probe the current process's read access without changing files or TCC state."""
    home = home or Path.home()

    def grouped_status(entries: list[tuple[str, Path]]) -> tuple[str, int, int, list[dict[str, str]]]:
        existing = [(name, path) for name, path in entries if path.exists()]
        if not existing:
            return "not_applicable", 0, 0, []
        details = [{"name": name, "status": _directory_access(path)} for name, path in existing]
        statuses = [detail["status"] for detail in details]
        granted = statuses.count("granted")
        if granted == len(statuses):
            status = "granted"
        elif granted:
            status = "limited"
        elif "denied" in statuses:
            status = "denied"
        else:
            status = "unavailable"
        return status, granted, len(statuses), details

    cache_paths = [("~/Library/Caches", home / "Library/Caches")]
    browser_paths = [
        ("Google Chrome", home / "Library/Application Support/Google/Chrome"),
        ("Brave", home / "Library/Application Support/BraveSoftware/Brave-Browser"),
        ("Microsoft Edge", home / "Library/Application Support/Microsoft Edge"),
        ("Chromium", home / "Library/Application Support/Chromium"),
        ("Firefox", home / "Library/Caches/Firefox/Profiles"),
    ]
    protected_paths = [
        ("Mail", home / "Library/Mail"),
        ("Safari", home / "Library/Safari"),
    ]

    container_root = home / "Library/Containers"
    container_paths: list[tuple[str, Path]] = []
    if _directory_access(container_root) == "granted":
        try:
            container_paths = [
                (path.name, path / "Data/Library/Caches")
                for path in sorted(container_root.iterdir(), key=lambda item: item.name.casefold())
                if not path.name.startswith("com.apple.") and (path / "Data/Library/Caches").exists()
            ]
        except OSError:
            container_paths = []

    groups = []
    for identifier, paths in (
        ("userCaches", cache_paths),
        ("browserProfiles", browser_paths),
        ("appSandboxes", container_paths),
        ("protectedData", protected_paths),
    ):
        status, accessible, total, entries = grouped_status(paths)
        groups.append({
            "id": identifier,
            "status": status,
            "accessible": accessible,
            "total": total,
            "entries": entries,
        })

    protected = next(group for group in groups if group["id"] == "protectedData")
    full_disk_access = (
        "granted" if protected["status"] == "granted" and protected["total"] > 0
        else "not_granted" if protected["status"] in {"denied", "limited"}
        else "unknown"
    )
    executable = Path(sys.executable)
    launch_context = "app" if ".app/Contents/" in str(executable) else "cli"
    return {
        "launchContext": launch_context,
        "fullDiskAccess": full_disk_access,
        "checks": groups,
        "note": "Capability probe only; macOS does not expose a definitive Full Disk Access query API.",
    }


def which(name: str) -> str | None:
    return shutil.which(name)


def ensure_tool_search_path() -> None:
    """Append well-known tool install locations to PATH when they are missing.

    Finder, LaunchAgent and .app launches receive a minimal PATH that lacks
    Homebrew and version-manager bins. Interactive terminals already contain
    these directories, which makes this merge a no-op outside GUI contexts.
    """
    home = Path.home()
    static_dirs: list[Path] = [
        Path("/opt/homebrew/bin"), Path("/opt/homebrew/sbin"),
        Path("/usr/local/bin"), Path("/usr/local/sbin"),
        home / ".local/bin", home / ".volta/bin", home / ".bun/bin",
        home / ".deno/bin", home / ".cargo/bin",
        home / ".asdf/shims", home / ".local/share/mise/shims",
    ]
    versioned: list[Path] = []
    for parent in (home / ".nvm/versions/node", home / ".local/share/mise/installs/node",
                   home / ".asdf/installs/nodejs", home / ".local/state/fnm_multishells"):
        try:
            versioned.extend(sorted(parent.glob("*/bin"), key=str, reverse=True))
        except OSError:
            continue
    current = [part for part in os.environ.get("PATH", "").split(os.pathsep) if part]
    known = set(current)
    additions: list[str] = []
    for candidate in (*static_dirs, *versioned):
        try:
            if candidate.is_dir() and str(candidate) not in known:
                known.add(str(candidate))
                additions.append(str(candidate))
        except OSError:
            continue
    if additions:
        os.environ["PATH"] = os.pathsep.join([*current, *additions])


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
             on_error: Callable[[Path, str], None] | None = None,
             on_result: Callable[[Path, int], None] | None = None) -> dict[Path, int]:
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
                if on_result:
                    on_result(path, results[path])
                next_path = next(pending_paths, None)
                if next_path is not None:
                    if cancel:
                        cancel()
                    futures[pool.submit(size_of, next_path, cancel=cancel, on_error=on_error)] = next_path
    return results


def iter_app_bundles(
    root: Path,
    *,
    descend_bundles: bool = False,
    on_error: Callable[[Path, OSError], None] | None = None,
) -> Iterator[Path]:
    """Yield ``*.app`` bundle paths under ``root`` without following symlinked dirs.

    ``descend_bundles=False`` treats a matched bundle as a leaf (app inventory
    semantics). ``True`` also descends into bundles so helper apps nested under
    ``Contents/`` are found — leftover detection needs those bundle IDs,
    otherwise their support data looks orphaned. Unreadable directories are
    skipped; pass ``on_error`` when the caller must know enumeration was partial.
    """
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            with os.scandir(directory) as entries:
                children = list(entries)
        except OSError as exc:
            if on_error is not None:
                on_error(directory, exc)
            continue
        for entry in children:
            is_bundle = entry.name.endswith(".app") and entry.is_dir()
            if is_bundle:
                yield Path(entry.path)
            if entry.is_dir(follow_symlinks=False) and (descend_bundles or not is_bundle):
                stack.append(Path(entry.path))


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
    """macOS atomic no-overwrite rename; supports TCC-restricted ~/.Trash safely."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, "renameatx_np", None)
    if rename is None:
        raise PermissionError("Atomic exclusive Trash moves are unavailable on this platform")
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int

    def rename_exclusive(source_fd: int, source_name: bytes, trash_fd: int, trash_name: bytes) -> None:
        # RENAME_EXCL, documented in macOS sys/stdio.h. Never fall back to overwrite/copy.
        if rename(source_fd, source_name, trash_fd, trash_name, 0x00000004):
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code), str(path))

    with directory_fd(path.parent) as source_fd:
        authorize()
        source = os.stat(path.name, dir_fd=source_fd, follow_symlinks=False)
        if stat.S_ISLNK(source.st_mode) or source.st_uid != os.getuid():
            raise PermissionError("Trash target changed or is not owned by the current user")
        try:
            trash_context = directory_fd(destination.parent)
            trash_fd = trash_context.__enter__()
        except PermissionError:
            # macOS can permit an atomic rename into ~/.Trash while denying directory-descriptor opens
            # through TCC. Keep the operation exclusive and verify the original source identity.
            authorize()
            rename_exclusive(-2, os.fsencode(str(path)), -2, os.fsencode(str(destination)))  # AT_FDCWD on macOS
            moved = destination.lstat()
        else:
            try:
                rename_exclusive(source_fd, os.fsencode(path.name), trash_fd, os.fsencode(destination.name))
                moved = os.stat(destination.name, dir_fd=trash_fd, follow_symlinks=False)
            finally:
                trash_context.__exit__(None, None, None)
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
