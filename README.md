# DeepClean

DeepClean is a safe macOS cleanup, application removal, disk analysis and developer-tool maintenance application. The active implementation is Python 3.11+ and is built, locked and installed with `uv`.

The application is fully implemented in Python. The repository contains no legacy implementation source or build artifacts.

## Safety contract

- Run DeepClean as your normal account. The CLI, Web UI and installer reject root execution.
- Installation is user-local through `uv tool`; it does not write to `/usr/local/bin` and does not request sudo.
- Broad roots such as `/`, `/System`, `/Library`, `/Applications`, `/Users` and `/private` are never generic cleanup targets.
- Cleanup candidates are restricted to known cache/log/temp domains and are validated again immediately before mutation.
- Whitelist rules are reread at execution time.
- Symlinked ancestors are rejected.
- Installer files, project artifacts, analyzer selections and application remnants are moved to `~/.Trash` where appropriate.
- Web mutations require a localhost Host/Origin, a same-site session cookie and an item from the latest server-side scan.
- DeepClean never elevates application removal. User-owned, non-cask bundles move to Trash; Homebrew Casks use Homebrew. System-owned bundles that cannot be safely removed are rejected.

Changing the implementation language does not bypass macOS SIP/TCC/filesystem permissions. DeepClean avoids unnecessary elevation by keeping installation and normal operation in user-owned locations.

## Setup

User-local installation, without sudo:

```sh
sh install.sh
```

The installer bootstraps `uv` into the current user's home directory when it is missing, clears browser/AirDrop quarantine metadata from this checkout when allowed, and installs DeepClean as a user-owned `uv tool`. It never writes to `/usr/local` and never needs `sudo`.

For development, install [uv](https://docs.astral.sh/uv/) manually, then:

```sh
uv sync --all-groups
uv run deepclean --help
```

Manual equivalent:

```sh
uv tool install --python 3.11 --force .
```

Production-style local install:

```sh
make prod-install
```

This builds a standalone PyInstaller binary, installs it to `~/.local/bin/deepclean`, creates `~/Applications/DeepClean.app` as a Web UI launcher, clears quarantine metadata when allowed, and applies an ad-hoc local code signature. Apple notarization still requires an Apple Developer ID certificate and cannot be done generically from another user's Mac.

If `~/.local/bin` is not on `PATH`, run `uv tool update-shell` once.

`./install.sh` detects zsh, bash or fish and installs command/argument completion automatically. New terminal sessions load it without another setup step. For an existing installation, run:

```sh
deepclean completion zsh --install
```

The command prints the exact one-line activation command for the current terminal. A child installer cannot modify the already-running parent shell; this limitation applies to all shell-completion installers.

## Main commands

```sh
deepclean                         # interactive menu
deepclean doctor
deepclean status
deepclean scan --profile safe --scan-only
deepclean scan --profile developer --scan-only
deepclean scan --profile safe --apply
deepclean apps
deepclean analyze ~/Projects
deepclean duplicates --path ~/Downloads --min-size 10MB
deepclean large-files --path ~/Downloads --min-size 1GB --older-than-days 90
deepclean smart-downloads --older-than-days 30
deepclean browser-storage
deepclean purge --path ~/Projects
deepclean developer-caches --scan-only
deepclean developer storage
deepclean developer runtimes
deepclean optimize
deepclean snapshots
deepclean history
deepclean restore --operation-id <id> --trash-path <path> [--copy]
deepclean completion zsh --print
deepclean ui
```

The profiles are `safe`, `deep`, `developer` and `aggressive`. Before authorization the CLI prints the exact target/manager command, action type, risk, reason, app-close requirement and scan-size estimate. Destructive CLI operations require `--apply`; automation can additionally use `--yes`. Manual-only candidates are never selected by unattended execution.

Cancelled, permission-limited and failed scans are not reported as “clean.” Their status and inaccessible locations are shown explicitly, and incomplete bulk-scan results cannot be sent to cleanup.

Space reporting deliberately separates the reviewed scan estimate, the estimate for successfully processed targets, the conservative estimated reclaim, and the observed filesystem-wide free-space change. Trash moves are reported separately and are never counted as freed space. Manager effects remain unknown unless they can be measured safely. Observed changes are not attributed solely to DeepClean because APFS clones, snapshots, sparse files and concurrent disk activity can affect them.

Duplicate File Finder is read-only during scanning and verifies candidates in the order `size → partial hash → full hash`; hardlinks/same-inode paths are not counted as duplicates. No duplicate is selected automatically, and moving a reviewed duplicate to Trash goes through the same preview, confirmation, PathSafety and history pipeline as analyzer Trash actions.

Large & Old Files is also read-only during scanning. It supports 500 MB, 1 GB, 5 GB and 10 GB size filters plus 30/90/180/365-day age filters, and labels Large files, Old files, Archives, Videos, Disk images and Downloads. These are user files, so nothing is selected automatically.

Smart Downloads scans `~/Downloads` for installers (`.dmg`, `.pkg`, `.xip`, `.iso`, `.ipsw`), archives (`.zip`, `.rar`, `.7z`), incomplete downloads (`.crdownload`, `.download`, `.part`), old matching downloads and byte-for-byte duplicates. Documents, photos and source code are not automatically classified as junk.

Developer Storage Center groups Xcode, Node.js, Python, Rust, Android and Docker storage in the Developer Tools area. It is read-only inventory: Docker volumes are never auto-deleted, project `node_modules`/`target` directories are shown for review, and manager-owned runtimes/caches continue to use their manager-specific cleanup/removal flows.

Browser Storage Inspector separates Safari, Chrome, Chromium, Brave, Edge, Firefox and Arc cache/site-data areas. Smart Clean only targets safe cache leaves (`Cache`, `Code Cache`, `GPU Cache`); Service Workers, IndexedDB, Local Storage, Cookies and Sessions are shown as user data and are not selected automatically.

Storage Treemap in the Web UI uses the existing incremental Disk Analyzer backend. It shows folder size, percentage and file count, supports drill-down/back navigation, can reveal reviewed paths in Finder, and routes cleanup candidate review through the same Trash safety pipeline.

Recovery history records each item with `operation_id`, original path, Trash path, timestamp, size and whether it is restorable. Restorable Trash entries can be restored from the Web UI or with `deepclean restore`; use `--copy` to avoid moving the Trash item back. If the original path already exists, normal restore fails closed and Restore as copy chooses a collision-free sibling. Package-manager cleanup commands are shown as Not Restorable because their managers perform the mutation.

## Terminal UI

Running `deepclean` without arguments opens the Textual dashboard. It has persistent navigation, descriptive tool pages, live system metrics, background workers, review tables and a dedicated pre-operation review screen. Nothing starts until the exact displayed plan receives an explicit `y` response at its terminal-style `[y/N]` prompt; Enter, `n` and Esc safely cancel. User-data or MANUAL selections require a second explicit `y` confirmation. Use arrow keys or `j`/`k` to move, Enter to open, `h` or `Ctrl+N` to focus the sidebar, `l` to focus page content, `1`–`9` to jump directly, Space to toggle reviewed rows, `r` to refresh and `Esc` to return to the dashboard.

The TUI exposes Smart Clean, application/component removal, incremental disk analysis, Duplicate File Finder, Project Purge, developer inventory/cache cleanup, optimization, evidence-based Mac health, leftovers, installers, snapshots, doctor, history/recovery status and whitelist information. Mac health reports disk headroom, macOS memory-pressure headroom, thermal state and battery condition with measurement time and safe guidance; it does not invent a health score or act automatically. Expensive native probes are rate-limited and unavailable readings remain unknown. Long-running scans execute outside the UI event loop, so navigation remains responsive. Press `c` on a scan/result screen to request cooperative cancellation; active filesystem walks, bounded size workers and waiting subprocesses stop at safe checkpoints. Cleanup mutations are never force-cancelled.

## Web UI

```sh
deepclean ui
# or
./start-web.sh
```

The bundled dashboard listens only on `127.0.0.1:8123`. It exposes the same read-only Mac health indicators, Smart Clean, application inventory/removal, Project Purge, installer and leftover review, disk analysis, Duplicate File Finder, developer caches/inventory, snapshots, optimization, doctor, history/recovery and whitelist controls. Destructive requests use a two-step server-reviewed flow: the UI displays the server's exact plan, then submits a short-lived, single-use token bound to that selection and scan generation.

Disk Analyzer lists a directory immediately and measures each visible child in a bounded background worker pool. Navigation never waits for the current directory to finish: moving elsewhere cancels its disk I/O while preserving completed measurements in the Web UI session cache. Returning shows that cache immediately and resumes only unfinished entries. The explicit Analyze/refresh action can force a fresh measurement. The progress HUD can stop Smart Clean or analyzer work through the shared cancellation API.

## Development

```sh
make sync
make check
make build
```

Direct equivalents:

```sh
uv run pytest
uv run python -m compileall -q src/deepclean
uv build
```

The wheel contains the Web UI assets, so an installed `uv tool` does not depend on the source checkout.

## Compatibility and release validation

DeepClean targets macOS 13 and newer on both Apple Silicon (`arm64`) and Intel (`x86_64`), with Python 3.11 or newer. Platform-specific features are capability-detected: a missing package manager or native command produces an empty/limited result instead of enabling a filesystem fallback. Finder-launched applications may have a shorter `PATH`; install managers normally and treat Doctor's unavailable result as authoritative for that session.

The 2026-09-11 release check was run on macOS 26.2 (build 25C56), Apple Silicon, with Python 3.11.15. The 201-test automated suite covers both architecture identifiers, missing `PATH`/manager commands, empty inventories, permission-denied directories, Unicode and space-containing paths, 80×24 and 120×40 TUI navigation, CLI dry-run/confirmation, and Web Host/Origin/session gates. No physical Intel runner was available for this check, so Intel remains a target supported by architecture-neutral code and automated regression tests, not a claim of same-day hardware validation. macOS 13–15 likewise remain supported targets but were not physically exercised in this local run.

APFS allocation, snapshots and concurrent disk activity can make observed free-space changes differ from scan estimates. TCC can hide otherwise valid locations; DeepClean reports those scans as incomplete and never bypasses macOS security controls. Battery and thermal sensors may be absent, and those health values remain unknown rather than being presented as normal.

## Uninstall

```sh
./uninstall.sh
# preserve config/logs by default

./uninstall.sh --purge-data
# asks before deleting DeepClean-owned user data
```

`uv` installs and manages the required Python runtime and dependencies in the user's own environment.
