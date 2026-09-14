#!/bin/sh
set -eu

fail() { printf '%s\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = "Darwin" ] || fail "DMG creation requires macOS."

SCRIPT_DIR=$(dirname "$0")
ROOT=$(CDPATH= cd "$SCRIPT_DIR/.." 2>/dev/null && pwd -P) || fail "Could not resolve project root."
cd "$ROOT"

APP_PATH=${1:-build/macos-app/MacMaid.app}
OUT_DMG=${2:-build/macos-app/MacMaid.dmg}
VOLNAME=${VOLNAME:-MacMaid}
STAGING=$(mktemp -d "${TMPDIR:-/tmp}/macmaid-dmg.XXXXXX")
trap 'rm -rf "$STAGING"' EXIT INT TERM

[ -d "$APP_PATH" ] || fail "App bundle not found: $APP_PATH"
mkdir -p "$(dirname "$OUT_DMG")"
cp -R "$APP_PATH" "$STAGING/"
ln -s /Applications "$STAGING/Applications"
rm -f "$OUT_DMG"
hdiutil create -volname "$VOLNAME" -srcfolder "$STAGING" -ov -format UDZO "$OUT_DMG" >/dev/null
shasum -a 256 "$OUT_DMG" | awk '{print $1}' > "$OUT_DMG.sha256"
printf '%s\n' "$OUT_DMG"
