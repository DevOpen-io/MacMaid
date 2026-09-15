#!/bin/sh
set -eu

fail() { printf '%s\n' "$*" >&2; exit 1; }
info() { printf '%s\n' "$*"; }

[ "$(uname -s)" = "Darwin" ] || fail "macOS app build requires macOS."

SCRIPT_DIR=$(dirname "$0")
ROOT=$(CDPATH= cd "$SCRIPT_DIR/.." 2>/dev/null && pwd -P) || fail "Could not resolve project root."
cd "$ROOT"

UV=${UV:-$(command -v uv 2>/dev/null || true)}
[ -n "$UV" ] || fail "uv is required."

PYTHON_VERSION=${PYTHON_VERSION:-3.11}
APP_NAME=${APP_NAME:-MacMaid}
BIN_NAME=${BIN_NAME:-macmaid}
VERSION=${VERSION:-$("$UV" run python - <<'PY'
from macmaid import __version__
print(__version__)
PY
)}
BUILD_DIR=${BUILD_DIR:-$ROOT/build/macos-app}
DIST_DIR=$BUILD_DIR/dist
WORK_DIR=$BUILD_DIR/work
SPEC_DIR=$BUILD_DIR/spec
ENTRYPOINT=$BUILD_DIR/macmaid_entry.py
APP_ROOT=${APP_ROOT:-$BUILD_DIR/$APP_NAME.app}
APP_MACOS=$APP_ROOT/Contents/MacOS
APP_RESOURCES=$APP_ROOT/Contents/Resources
APP_RUNTIME=$APP_RESOURCES/runtime
APP_FRAMEWORKS=$APP_ROOT/Contents/Frameworks
LOGO_PNG=$ROOT/assets/MacMaid-Logo.png
ICONSET=$BUILD_DIR/MacMaid.iconset
ICON_FILE=MacMaid.icns

rm -rf "$APP_ROOT" "$DIST_DIR" "$WORK_DIR" "$SPEC_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR" "$WORK_DIR" "$SPEC_DIR" "$APP_MACOS" "$APP_RESOURCES"

cat > "$ENTRYPOINT" <<'PY'
from macmaid import main

if __name__ == "__main__":
    main()
PY

info "Building standalone MacMaid binary..."
"$UV" run --python "$PYTHON_VERSION" --with pyinstaller pyinstaller \
  --noconfirm \
  --clean \
  --onedir \
  --name "$BIN_NAME" \
  --distpath "$DIST_DIR" \
  --workpath "$WORK_DIR" \
  --specpath "$SPEC_DIR" \
  --paths "$ROOT/src" \
  --add-data "$ROOT/src/macmaid/WebUI:macmaid/WebUI" \
  --collect-all textual \
  "$ENTRYPOINT"

BUNDLE_DIR=$DIST_DIR/$BIN_NAME
[ -x "$BUNDLE_DIR/$BIN_NAME" ] || fail "PyInstaller did not produce $BUNDLE_DIR/$BIN_NAME"
install -m 755 "$BUNDLE_DIR/$BIN_NAME" "$APP_MACOS/macmaid-bin"
cp -R "$BUNDLE_DIR/_internal" "$APP_RUNTIME"
ln -s Resources/runtime "$APP_FRAMEWORKS"

SWIFT_APP_SRC="$ROOT/src/macmaid/native/MacMaidApp.swift"
if command -v swiftc >/dev/null 2>&1 && [ -f "$SWIFT_APP_SRC" ]; then
  info "Compiling native Cocoa/WebKit window wrapper with swiftc..."
  swiftc -O -framework Cocoa -framework WebKit "$SWIFT_APP_SRC" -o "$APP_MACOS/$APP_NAME"
else
  info "swiftc not found; using fallback shell launcher."
  cat > "$APP_MACOS/$APP_NAME" <<'APP'
#!/bin/sh
HERE=$(CDPATH= cd "$(dirname "$0")" 2>/dev/null && pwd -P)
exec "$HERE/macmaid-bin" ui "$@"
APP
  chmod 755 "$APP_MACOS/$APP_NAME"
fi

if [ -f "$LOGO_PNG" ]; then
  cp "$LOGO_PNG" "$APP_RESOURCES/MacMaid-Logo.png"
  if command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1; then
    rm -rf "$ICONSET"
    mkdir -p "$ICONSET"
    sips -z 16 16 "$LOGO_PNG" --out "$ICONSET/icon_16x16.png" >/dev/null
    sips -z 32 32 "$LOGO_PNG" --out "$ICONSET/icon_16x16@2x.png" >/dev/null
    sips -z 32 32 "$LOGO_PNG" --out "$ICONSET/icon_32x32.png" >/dev/null
    sips -z 64 64 "$LOGO_PNG" --out "$ICONSET/icon_32x32@2x.png" >/dev/null
    sips -z 128 128 "$LOGO_PNG" --out "$ICONSET/icon_128x128.png" >/dev/null
    sips -z 256 256 "$LOGO_PNG" --out "$ICONSET/icon_128x128@2x.png" >/dev/null
    sips -z 256 256 "$LOGO_PNG" --out "$ICONSET/icon_256x256.png" >/dev/null
    sips -z 512 512 "$LOGO_PNG" --out "$ICONSET/icon_256x256@2x.png" >/dev/null
    sips -z 512 512 "$LOGO_PNG" --out "$ICONSET/icon_512x512.png" >/dev/null
    sips -z 1024 1024 "$LOGO_PNG" --out "$ICONSET/icon_512x512@2x.png" >/dev/null
    iconutil -c icns "$ICONSET" -o "$APP_RESOURCES/$ICON_FILE"
  fi
fi

cat > "$APP_ROOT/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>$APP_NAME</string>
  <key>CFBundleIdentifier</key><string>io.devopen.macmaid</string>
  <key>CFBundleName</key><string>$APP_NAME</string>
  <key>CFBundleDisplayName</key><string>$APP_NAME</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleIconFile</key><string>$ICON_FILE</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
</dict>
</plist>
PLIST

if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep --sign - "$APP_ROOT" >/dev/null 2>&1 || info "Ad-hoc codesign failed; continuing."
fi

touch "$APP_ROOT"
info "$APP_ROOT"
