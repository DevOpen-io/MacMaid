<p align="center">
  <img src="assets/MacMaid-Logo.png" alt="MacMaid logo" width="140" height="140">
</p>

<h1 align="center">MacMaid</h1>

<p align="center">
  Safe macOS cleanup, disk analysis, app removal and developer-tool maintenance.
</p>

MacMaid helps you understand what is using space on your Mac and clean reviewed, recoverable targets without turning maintenance into a risk. It is built for normal user accounts, does not ask you to run the app with `sudo`, and keeps destructive actions behind review/confirmation flows.

## <img src="assets/triangle-alert.svg" alt="Warning" width="32" align="top"> Important safety notice

> **Some tools and features in this project were developed with AI assistance.**
>
> They are reviewed and tested by the maintainer, but no cleanup utility can be guaranteed risk-free. **Review selected targets carefully, keep backups of important data, and use the software at your own risk.**

---

## Installation

### Homebrew

After the release workflow has published a version to the Homebrew tap:

```sh
# On Homebrew 6.0+, third-party taps must be trusted before tapping:
brew trust devopen-io/tap

brew tap DevOpen-io/tap
brew install --cask macmaid   # installs MacMaid.app
brew install macmaid          # installs the macmaid CLI command
```

Then run:

```sh
macmaid
macmaid ui
```

The current Homebrew/GitHub Release packages are Apple Silicon (`arm64`) only.

> [!NOTE]
> **First Launch on macOS (Gatekeeper / "Apple could not verify..." alert):**  
> Because MacMaid is an open-source tool without paid Apple Developer notarization, macOS Gatekeeper may show an alert on first launch stating *"Apple could not verify MacMaid..."*.
>
> To open it:
> 1. Go to **System Settings** → **Privacy & Security**.
> 2. Scroll down to the **Security** section.
> 3. Click **Open Anyway** next to the MacMaid blocked notification, then confirm with **Open**.
>
> Alternatively, you can remove the macOS quarantine flag via Terminal:
> ```sh
> xattr -cr /Applications/MacMaid.app
> # or if using local user Applications:
> xattr -cr ~/Applications/MacMaid.app
> ```

### Standalone local app build

For a local production-style install from this repository:

```sh
make prod-install
```

This builds a standalone `macmaid` binary, installs it to `~/.local/bin/macmaid`, and creates:

```text
~/Applications/MacMaid.app
```

Open it with:

```sh
open ~/Applications/MacMaid.app
```

### Developer install

For development:

```sh
uv sync --all-groups
uv run macmaid --help
```

User-local tool install without sudo:

```sh
sh install.sh
```

If `~/.local/bin` is not on your `PATH`, run:

```sh
uv tool update-shell
```

---

## Quick usage

```sh
macmaid                         # Terminal UI
macmaid ui                      # Web UI on 127.0.0.1:8123
macmaid doctor                  # Capability diagnostics
macmaid status                  # Read-only system snapshot
macmaid memory                  # Process memory and growth snapshot
macmaid memory --stop PID       # Review only; add --apply to request SIGTERM
macmaid scan --profile safe --scan-only
macmaid analyze ~/Projects
macmaid duplicates --path ~/Downloads --min-size 10MB
macmaid large-files --path ~/Downloads --min-size 1GB
macmaid smart-downloads
macmaid browser-storage
macmaid developer storage
macmaid history
```

Destructive CLI actions require `--apply`, and non-interactive automation should also use `--yes` after reviewing the output.

---

## What MacMaid can do

- **Smart Clean** — finds safe cache/log/temp cleanup candidates.
- **Storage Treemap** — visual folder-size map with drill-down navigation.
- **Disk Analyzer** — incremental directory analysis without waiting for the full tree to finish.
- **App removal review** — inventories apps and related components before removal.
- **Memory** — tracks process memory growth, supports reviewed bulk stopping, and offers opt-in helper rules.
- **Developer Storage** — shows Xcode, Node.js, Python, Rust, Android and Docker-related storage.
- **Browser Storage Inspector** — separates safe browser caches from user data like sessions, cookies and local storage.
- **Duplicate Finder** — read-only duplicate detection with no automatic deletion.
- **Large & Old Files** — helps review large user files without auto-selecting them.
- **Smart Downloads** — reviews installers, archives, incomplete downloads and duplicate downloads.
- **History & restore** — records Trash moves and supports restore where possible.

---

## Safety model

MacMaid is intentionally conservative:

- Run as your normal user, never as root.
- No broad `rm -rf` style cleanup.
- No silent deletion of documents, browser sessions, credentials, databases or app support data.
- Cleanup paths are validated again immediately before mutation.
- Symlinked ancestors are rejected for destructive operations.
- User-visible file cleanup normally moves items to `~/.Trash` instead of permanently deleting them.
- Web UI mutations require localhost session/origin checks. Manual cleanup and process stopping require a fresh server-side review token; automatic helper rules require explicit stored consent.
- macOS privacy/TCC limitations are reported; MacMaid does not bypass them.

If MacMaid cannot prove an operation is safe, it skips or blocks it.

---

## Web UI

```sh
macmaid ui
```

The dashboard listens only on:

```text
http://127.0.0.1:8123
```

If MacMaid is already running on that port, launching it again opens the existing session instead of crashing.

### Memory

The **Memory** panel shows per-process RSS, CPU, and sustained ten-minute growth so you can investigate unusual usage; growth is only a signal, and RSS is not guaranteed reclaimable memory.

Stopping a process always requires review, while optional rules can send SIGTERM only to recognized Dart analysis or TypeScript server helpers after their RSS, duration, and memory-pressure limits are met. Rules never force-stop, protected or excluded processes remain untouched, and monitoring ends when MacMaid closes.

---

## Development

```sh
make sync
make check
make build
```

Direct equivalents:

```sh
uv run pytest
uv run python -m compileall -q src/macmaid
uv build
```

The Python package lives in `src/macmaid`; bundled Web UI files live in `src/macmaid/WebUI`.

---

## CI/CD

GitHub Actions are configured to:

- run tests on code changes,
- build an Apple Silicon DMG on `main` pushes,
- publish immutable GitHub Release assets for the version in `pyproject.toml`,
- update the Homebrew tap when `HOMEBREW_TAP_TOKEN` is configured.

The project version is the source of truth. CI creates an immutable matching release tag only to provide stable download URLs for GitHub Releases and Homebrew.

Documentation-only changes such as `README.md` or other Markdown files do not trigger the CI/build workflows.

To release a new version, update both:

```text
pyproject.toml
src/macmaid/__init__.py
```

then commit and push to `main`.

---

## Uninstall

Homebrew install:

```sh
brew uninstall --cask macmaid  # removes MacMaid.app
brew uninstall macmaid         # removes the macmaid CLI command
```

To also remove MacMaid config/log data, use Homebrew zap:

```sh
brew uninstall --zap --cask macmaid
```

Local/source install:

```sh
./uninstall.sh
```

To also remove MacMaid config/log data:

```sh
./uninstall.sh --purge-data
```

The uninstall script removes user-local tool installs and the local `~/Applications/MacMaid.app` created by `make prod-install`.

---

## Compatibility

MacMaid targets macOS 13+ and Python 3.11+. The source/dev install can run on Intel or Apple Silicon Macs. The current packaged DMG/Homebrew cask is Apple Silicon only until Intel release builds are enabled again.

Some folders may require macOS privacy permissions such as Full Disk Access. MacMaid reports those limitations instead of trying to bypass system security.
