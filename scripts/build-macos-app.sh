#!/bin/sh
set -eu

fail() { printf '%s\n' "$*" >&2; exit 1; }
info() { printf '%s\n' "$*"; }

[ "$(uname -s)" = "Darwin" ] || fail "macOS app build requires macOS."

SCRIPT_DIR=$(dirname "$0")
ROOT=$(CDPATH= cd "$SCRIPT_DIR/.." 2>/dev/null && pwd -P) || fail "Could not resolve project root."
cd "$ROOT"

MACOS_DEPLOYMENT_TARGET=${MACOS_DEPLOYMENT_TARGET:-13.0}
APP_NAME=${APP_NAME:-MacMaid}
BIN_NAME=${BIN_NAME:-macmaid}
VERSION=${VERSION:-$(awk -F'"' '/^version = / {print $2; exit}' Cargo.toml)}

BUILD_DIR=${BUILD_DIR:-$ROOT/build/macos-app}
APP_ROOT=${APP_ROOT:-$BUILD_DIR/$APP_NAME.app}
APP_MACOS=$APP_ROOT/Contents/MacOS
APP_RESOURCES=$APP_ROOT/Contents/Resources
LOGO_PNG=$ROOT/assets/MacMaid-Logo.png
ICONSET=$BUILD_DIR/MacMaid.iconset
ICON_FILE=MacMaid.icns
CLI_DIR=$BUILD_DIR/cli

info "Building MacMaid Rust release workspace ($VERSION)..."
cargo build --release --workspace

CLI_SRC="$ROOT/target/release/macmaid"
FFI_LIB="$ROOT/target/release/libmacmaid_ffi.a"
FFI_INC="$ROOT/crates/macmaid-ffi/include"

[ -f "$CLI_SRC" ] || fail "Rust CLI binary not found at $CLI_SRC"
[ -f "$FFI_LIB" ] || fail "Rust FFI static library not found at $FFI_LIB"

rm -rf "$APP_ROOT" "$CLI_DIR"
mkdir -p "$BUILD_DIR" "$APP_MACOS" "$APP_RESOURCES" "$CLI_DIR"

# Stage standalone CLI binary
cp "$CLI_SRC" "$CLI_DIR/$BIN_NAME"
chmod 755 "$CLI_DIR/$BIN_NAME"
cp "$CLI_SRC" "$APP_MACOS/$BIN_NAME"
chmod 755 "$APP_MACOS/$BIN_NAME"

# Build native SwiftUI desktop application
info "Compiling native macOS SwiftUI desktop interface with swiftc..."
SWIFT_FILES=$(find "$ROOT/apps/macos/Sources" -name '*.swift' | sort)

swiftc -target "$(uname -m)-apple-macosx$MACOS_DEPLOYMENT_TARGET" \
  -O -parse-as-library \
  -import-objc-header "$FFI_INC/macmaid_ffi.h" \
  -I "$FFI_INC" \
  -L "$ROOT/target/release" \
  -lmacmaid_ffi \
  $SWIFT_FILES \
  -o "$APP_MACOS/$APP_NAME"

# Generate application icon
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
    rm -rf "$ICONSET"
  fi
fi

# Write Info.plist
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
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

# Ad-hoc codesign
if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep --sign - "$APP_ROOT" >/dev/null 2>&1 || info "Ad-hoc codesign failed; continuing."
fi

touch "$APP_ROOT"
info "Built native macOS application at $APP_ROOT"
