#!/bin/sh
set -eu

fail() { printf '%s\n' "$*" >&2; exit 1; }
info() { printf '%s\n' "$*"; }

[ "$(id -u)" -ne 0 ] || fail "Do not uninstall MacMaid with sudo/root."

# Remove shell completion hooks first. Prefer the installed command if present;
# fall back to the source checkout when running from the repo.
OLD_COMMAND=$(printf '%s%s' deep clean)
if command -v macmaid >/dev/null 2>&1; then
  macmaid uninstall >/dev/null 2>&1 || true
elif command -v "$OLD_COMMAND" >/dev/null 2>&1; then
  "$OLD_COMMAND" uninstall >/dev/null 2>&1 || true
elif command -v uv >/dev/null 2>&1; then
  uv run macmaid uninstall >/dev/null 2>&1 || true
fi

UV=$(command -v uv 2>/dev/null || true)
if [ -n "$UV" ]; then
  "$UV" tool uninstall macmaid >/dev/null 2>&1 || true
  "$UV" tool uninstall "$OLD_COMMAND" >/dev/null 2>&1 || true
fi

python3 - "$HOME" "${1:-}" <<'PY'
from __future__ import annotations

import shutil
import sys
from pathlib import Path

home = Path(sys.argv[1]).expanduser().resolve()
mode = sys.argv[2] if len(sys.argv) > 2 else ""

def inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False

# Production install artifacts created by make prod-install.
legacy_command = "deep" + "clean"
for binary in (home / ".local/bin/macmaid", home / f".local/bin/{legacy_command}"):
    if binary.exists() or binary.is_symlink():
        if binary.parent == home / ".local/bin":
            binary.unlink()
            print(f"Removed {binary}")

legacy_app = "Deep" + "Clean.app"
for app in (home / "Applications/MacMaid.app", home / f"Applications/{legacy_app}"):
    if app.exists():
        applications = home / "Applications"
        if app.name in {"MacMaid.app", legacy_app} and inside(app.resolve(), applications.resolve()):
            shutil.rmtree(app)
            print(f"Removed {app}")

if mode == "--purge-data":
    config = home / ".config/macmaid"
    logs = home / "Library/Logs/MacMaid"
    print("Remove ~/.config/macmaid and ~/Library/Logs/MacMaid? [y/N]: ", end="", flush=True)
    answer = sys.stdin.readline().strip().lower()
    if answer in {"y", "yes"}:
        for target, root in ((config, home / ".config"), (logs, home / "Library/Logs")):
            if target.exists() and inside(target.resolve(), root.resolve()):
                shutil.rmtree(target)
                print(f"Removed {target}")
    else:
        print("User data preserved.")
PY

info "MacMaid removed. If your shell still has a cached command path, open a new terminal or run: hash -r"
