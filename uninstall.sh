#!/bin/sh
set -eu

[ "$(id -u)" -ne 0 ] || { printf '%s\n' "Do not uninstall DeepClean with sudo/root." >&2; exit 2; }
UV=$(command -v uv 2>/dev/null || true)
[ -n "$UV" ] || { printf '%s\n' "uv was not found." >&2; exit 1; }
"$UV" tool uninstall deepclean || true

if [ "${1:-}" = "--purge-data" ]; then
  printf 'Remove ~/.config/deepclean and ~/Library/Logs/DeepClean? [y/N]: '
  read answer
  case "$answer" in
    y|Y|yes|YES)
      rm -rf "$HOME/.config/deepclean" "$HOME/Library/Logs/DeepClean"
      printf '%s\n' "DeepClean user data removed."
      ;;
    *) printf '%s\n' "User data preserved." ;;
  esac
fi

printf '%s\n' "DeepClean tool removed."
