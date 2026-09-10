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

Install [uv](https://docs.astral.sh/uv/), then:

```sh
uv sync --all-groups
uv run deepclean --help
```

User-local installation, without sudo:

```sh
./install.sh
# equivalent:
uv tool install --force .
```

If `~/.local/bin` is not on `PATH`, run `uv tool update-shell` once.

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
deepclean purge --path ~/Projects
deepclean developer-caches --scan-only
deepclean developer runtimes
deepclean optimize
deepclean snapshots
deepclean history
deepclean completion zsh --print
deepclean ui
```

The profiles are `safe`, `deep`, `developer` and `aggressive`. Before authorization the CLI prints the exact target/manager command, action type, risk, reason, app-close requirement and scan-size estimate. Destructive CLI operations require `--apply`; automation can additionally use `--yes`. Manual-only candidates are never selected by unattended execution.

Cancelled, permission-limited and failed scans are not reported as “clean.” Their status and inaccessible locations are shown explicitly, and incomplete bulk-scan results cannot be sent to cleanup.

Space reporting deliberately separates the reviewed scan estimate, the estimate for successfully processed targets, the conservative estimated reclaim, and the observed filesystem-wide free-space change. Trash moves are reported separately and are never counted as freed space. Manager effects remain unknown unless they can be measured safely. Observed changes are not attributed solely to DeepClean because APFS clones, snapshots, sparse files and concurrent disk activity can affect them.

## Terminal UI

Running `deepclean` without arguments opens the Textual dashboard. It has persistent navigation, descriptive tool pages, live system metrics, background workers, review tables and a dedicated pre-operation review screen. Nothing starts until the exact displayed plan receives an explicit `y` response at its terminal-style `[y/N]` prompt; Enter, `n` and Esc safely cancel. User-data or MANUAL selections require a second explicit `y` confirmation. Use arrow keys or `j`/`k` to move, Enter to open, `h` or `Ctrl+N` to focus the sidebar, `l` to focus page content, `1`–`9` to jump directly, Space to toggle reviewed rows, `r` to refresh and `Esc` to return to the dashboard.

The TUI exposes Smart Clean, application/component removal, incremental disk analysis, Project Purge, developer inventory/cache cleanup, optimization, live status, leftovers, installers, snapshots, doctor, history and whitelist information. Long-running scans execute outside the UI event loop, so navigation remains responsive. Press `c` on a scan/result screen to request cooperative cancellation; active filesystem walks, bounded size workers and waiting subprocesses stop at safe checkpoints. Cleanup mutations are never force-cancelled.

## Web UI

```sh
deepclean ui
# or
./start-web.sh
```

The bundled dashboard listens only on `127.0.0.1:8123`. It exposes system status, Smart Clean, application inventory/removal, Project Purge, installer and leftover review, disk analysis, developer caches/inventory, snapshots, optimization, doctor, history and whitelist controls. Destructive requests use a two-step server-reviewed flow: the UI displays the server's exact plan, then submits a short-lived, single-use token bound to that selection and scan generation.

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

## Uninstall

```sh
./uninstall.sh
# preserve config/logs by default

./uninstall.sh --purge-data
# asks before deleting DeepClean-owned user data
```

DeepClean supports macOS 13+ on Apple Silicon and Intel. `uv` installs and manages the required Python 3.11+ runtime and dependencies in the user's own environment.
