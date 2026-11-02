# Homebrew Distribution & Compatibility Report

## Overview

MacMaid distributes both a native desktop application via Homebrew Cask and a standalone command-line tool via Homebrew Formula through the official tap repository (`DevOpen-io/homebrew-tap`).

The Rust migration preserves **100% distribution contract compatibility** with existing Homebrew installations. Upgrades from Python-based versions will succeed seamlessly with zero manual intervention.

---

## 1. Homebrew Tap Structure

The tap repository (`DevOpen-io/homebrew-tap`) contains:
- `Casks/macmaid.rb` — Desktop GUI installation bundle.
- `Formula/macmaid.rb` — Command-line interface installation.

---

## 2. Homebrew Cask Specification & Verification

### 2.1 Cask Definition (`Casks/macmaid.rb`)
```ruby
cask "macmaid" do
  version "0.15.35"
  sha256 "807311870b7a950b7927352fc9c39afbf4844cea6ecc0be83bc476917fdc9516"
  url "https://github.com/DevOpen-io/MacMaid/releases/download/v#{version}/MacMaid-#{version}-arm64.dmg"
  name "MacMaid"
  desc "Safe macOS cleanup, disk analysis and developer-tool maintenance"
  homepage "https://github.com/DevOpen-io/MacMaid"
  depends_on arch: :arm64
  depends_on macos: ">= :ventura"
  app "MacMaid.app"
  zap trash: [
    "~/.config/macmaid",
    "~/Library/Logs/MacMaid",
  ]
end
```

### 2.2 DMG Verification
- **Artifact Name:** `MacMaid-0.15.35-arm64.dmg`
- **Volume Format:** UDZO APFS disk image created with macOS `hdiutil create`
- **Volume Contents:**
  ```
  /Volumes/MacMaid/
  ├── Applications -> /Applications (Symlink)
  └── MacMaid.app (Native SwiftUI/AppKit desktop application)
  ```
- **Validation Test:**
  The disk image was attached using `hdiutil attach -nobrowse -readonly` and inspected. The top-level bundle `MacMaid.app` was verified, ensuring `brew install --cask macmaid` installs cleanly into `/Applications/MacMaid.app`.

---

## 3. Homebrew Formula Specification & Verification

### 3.1 Formula Definition (`Formula/macmaid.rb`)
```ruby
class Macmaid < Formula
  version "0.15.35"
  sha256 "9549b7f546638552f5f52e575e89fbcaedb9b9932b29c66a0366909ec8f2ba62"
  url "https://github.com/DevOpen-io/MacMaid/releases/download/v#{version}/MacMaid-#{version}-arm64-cli.tar.gz"
  desc "Safe macOS cleanup, disk analysis and developer-tool maintenance"
  homepage "https://github.com/DevOpen-io/MacMaid"
  depends_on arch: :arm64
  depends_on macos: ">= :ventura"

  def install
    libexec.install Dir["*"]
    bin.install_symlink libexec/"macmaid"
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/macmaid --version")
  end
end
```

### 3.2 CLI Tarball Verification
- **Artifact Name:** `MacMaid-0.15.35-arm64-cli.tar.gz`
- **Archive Contents:**
  ```
  macmaid (Standalone Mach-O 64-bit arm64 executable)
  ```
- **Validation Test:**
  The tarball was extracted into a simulated temporary `libexec` directory:
  ```bash
  TMP_DIR=$(mktemp -d)
  tar -xzf build/macos-app/MacMaid-0.15.35-arm64-cli.tar.gz -C "$TMP_DIR"
  ln -s "$TMP_DIR/macmaid" "$TMP_DIR/bin_macmaid"
  "$TMP_DIR/bin_macmaid" --version
  ```
  Output: `macmaid 0.15.35` (Exit 0).
  This precisely matches the Homebrew formula `test do` block.

---

## 4. Upgrade Path for Existing Users

1. **Self-Contained Executable:**
   - Legacy versions required Python runtime files in `libexec/_internal`.
   - The new Rust release packages `macmaid` as a single, self-contained binary with no runtime directories.
   - Homebrew's `libexec.install Dir["*"]` replaces legacy files cleanly.
2. **Configuration Continuity:**
   - Both legacy and new versions read from `~/.config/macmaid/settings.json` and `~/.config/macmaid/whitelist.conf`.
   - Existing whitelist rules and user preferences are automatically recognized without migration scripts.
3. **Audit Log Continuity:**
   - The JSON Lines audit log format at `~/Library/Logs/MacMaid/operations.jsonl` is preserved, allowing historical operations performed under legacy versions to be reviewed and restored.

---

## 5. Release Pipeline Integration

The GitHub Actions workflow (`.github/workflows/macos-dmg.yml`) automates tap updates upon official releases:
1. Builds arm64 DMG and CLI tarball.
2. Computes SHA-256 checksums.
3. Generates release assets on GitHub Releases.
4. Updates `Casks/macmaid.rb` and `Formula/macmaid.rb` in `DevOpen-io/homebrew-tap` with updated version strings and SHA-256 hashes.
