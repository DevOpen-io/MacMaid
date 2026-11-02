# MacMaid Codebase Audit & Migration Baseline

**Date:** 2026-11-02  
**Target Migration Branch:** `feat/rust-native-desktop`  
**Base Commit:** `69965fb` (`v0.15.35`)  
**Auditor:** Senior Rust Systems Engineer & macOS Platform Specialist  

---

## 1. Executive Summary & Verification Baseline

MacMaid is an evidence-based macOS system maintenance, cleanup, disk analysis, developer storage, and memory management tool designed under a fail-closed safety model.

### Pre-Migration Quality Gate Baseline

The baseline verification was executed on Apple Silicon macOS (Darwin arm64):
- **Tooling:** `uv 0.11.31`, `Python 3.15.2`, `rustc 1.98.1`, `cargo 1.98.1`, `Swift 6.4 (swiftlang-6.4.0.34.1)`, `Xcode 27.1`.
- **Ruff check:** 0 errors (`uv run ruff check src/macmaid tests_py`).
- **Mypy check:** 0 errors (`uv run mypy`).
- **Pytest test suite:** **531 passed, 2 skipped** in 73.15s (`uv run pytest`).

All baseline quality gates passed. No baseline tests were modified.

---

## 2. Inventory of Existing User-Facing Features

| Feature Subsystem | Python Implementation | Presentation Layers | Description & Guarantees |
|---|---|---|---|
| **Smart Clean** | `scanner.py`, `cleaner.py` | CLI (`scan`, `clean`), TUI, Web UI | Safe profiles (`safe`, `deep`, `developer`, `aggressive`). Categorized items, path allowlist validation, review requirements, exclusion, whitelisting. |
| **Disk Analyzer** | `analyzer.py`, `features.py` | CLI (`analyze`), TUI, Web UI | Breadth/depth directory size analysis, top directories, largest files, interactive navigation. |
| **Storage Treemap** | Web UI (`WebUI/features/analyzer.js`), `analyzer.py` | Web UI | Proportional nested box visualization of disk consumption with drilldown/zoom. |
| **App Uninstaller** | `features.py` (`ApplicationManager`) | CLI (`apps`), TUI, Web UI | Discovers `/Applications` and `~/Applications` bundles, extracts `CFBundleIdentifier`, searches matching safe/opt-in remnants under `~/Library`, handles Homebrew casks via `brew uninstall --cask`, checks running status. |
| **Memory Management** | `memory.py` (`MemoryService`) | CLI (`memory`), TUI, Web UI | Process table with PID, PPID, RSS, CPU%, memory growth tracking over 120s window, protected processes detection, reviewed termination (`SIGTERM` then `SIGKILL`), auto-manage opt-in. |
| **Developer Storage** | `developer.py` (`DeveloperStorageCenter`) | CLI (`developer`, `developer-caches`), TUI, Web UI | Managed storage detection: Xcode DerivedData/Simulators/DeviceSupport, Docker images/build cache, Cargo cache, Node/npm/pnpm/yarn, Python/pip/conda/poetry, Android SDK/AVD, version managers (mise, asdf, pyenv, rustup, fnm). |
| **Browser Storage** | `browser_storage.py` | CLI (`browser-storage`), Web UI | Strict segregation: disposable caches (Cache, Code Cache, GPUCache) vs protected persistent site data (Cookies, History, Sessions, LocalStorage, IndexedDB). |
| **Duplicate Finder** | `duplicates.py` | CLI (`duplicates`), Web UI | Scans paths for files >= min size, groups by byte length, computes 4KB prefix hash, then full SHA-256 for collision confirmation. Read-only. |
| **Large & Old Files** | `large_files.py` | CLI (`large-files`), Web UI | Finds files exceeding size thresholds (500MB, 1GB, etc.) and modified older than 30, 90, 180, 365 days. |
| **Smart Downloads** | `smart_downloads.py` | CLI (`smart-downloads`), Web UI | Inspects `~/Downloads` for installers (`.dmg`, `.pkg`), archives (`.zip`, `.tar.*`), incomplete downloads (`.crdownload`, `.part`), and duplicates. |
| **Project Purge** | `features.py` (`ProjectPurgeManager`) | CLI (`purge`), TUI, Web UI | Finds build/dependency artifacts (`node_modules`, `target`, `.venv`, `build`, `dist`, `__pycache__`) bounded by project markers (`Cargo.toml`, `package.json`, `pyproject.toml`, `.git`). Moves to Trash. |
| **History & Restore** | `reporting.py`, `cleaner.py`, `features.py` | CLI (`history`, `restore`), TUI, Web UI | Logs operations to `~/Library/Logs/MacMaid/operations.jsonl`. Supports restoring moved items from `~/.Trash` back to original paths with collision checks. |
| **Whitelist Manager** | `config.py` | CLI (`whitelist`), TUI, Web UI | Manages `~/.config/macmaid/whitelist`. Re-validated immediately before every filesystem mutation. |
| **Doctor / System Status** | `features.py` (`doctor`, `system_status`) | CLI (`doctor`, `status`), Web UI | Mac health indicators, disk usage, thermal state, memory pressure, battery cycle/condition, Full Disk Access probe. |
| **Snapshot Management** | `features.py` (`list_snapshots`, `thin_snapshots`) | CLI (`snapshots`), Web UI | Lists and thins APFS Time Machine local snapshots via `tmutil`. |
| **Shell Completion** | `features.py` | CLI (`completion`) | Generates/installs zsh, bash, fish shell completion scripts and rc-file hooks. |
| **Update Checker** | `features.py` | CLI (`update`), Web UI | Checks GitHub latest release and Homebrew formula/cask update state. |

---

## 3. CLI Command Surface & Contract

| Command | Arguments / Flags | Expected Behavior |
|---|---|---|
| `macmaid --version` | None | Prints `macmaid <version>`. Must match Formula test contract. |
| `macmaid --help` | None | Prints available subcommands. Exit code 0. |
| `macmaid doctor` | None | Evaluates macOS capabilities, Full Disk Access, permissions, tool paths. |
| `macmaid status` | None | Reports disk, battery condition, memory pressure, thermal status. |
| `macmaid scan` / `clean` | `--profile {safe,deep,developer,aggressive}`, `--trash`, `--system-temp`, `--scan-only` / `--no-prompt`, `--apply`, `--yes` | Scans cleanup candidates. In interactive terminal, `--apply` prompts with `Type CLEAN to execute`. `--yes` bypasses prompt. |
| `macmaid leftovers` | `--older-than <days>`, `--include-data`, `--apply`, `--yes` | Scans and removes uninstalled application leftovers. |
| `macmaid installers` | `--older-than <days>`, `--apply`, `--yes` | Scans and moves old downloads/desktop installers to Trash. |
| `macmaid analyze` | `[path]`, `--top <N>`, `--min-size <size>`, `--plain` | Analyzes disk usage of specified directory (default `~`). |
| `macmaid duplicates` | `--path <p>`, `--min-size <size>` | Finds byte-exact duplicate files (read-only). |
| `macmaid large-files` | `--path <p>`, `--min-size <size>`, `--older-than-days {30,90,180,365}` | Finds user files matching size and age filters. |
| `macmaid smart-downloads`| `--older-than-days <days>` | Classifies items in Downloads folder. |
| `macmaid browser-storage`| None | Inspects disposable vs persistent browser storage. |
| `macmaid apps` | None | Lists installed application bundles and estimated sizes. |
| `macmaid purge` | `--path <p>`, `--apply`, `--yes` | Scans and removes build/dependency artifacts in project directories. |
| `macmaid memory` | `--stop <PID>`, `--limit <N>`, `--growing`, `--watch <sec>`, `--sort {memory,rss,growth,cpu,name,pid}`, `--filter {all,applications,developer,flutter,growing,high,protected}`, `--apply`, `--yes` | Inspects processes and memory; allows reviewed termination. |
| `macmaid completion` | `[zsh\|bash\|fish]`, `--print`, `--install` | Prints completion script or installs to user shell directory. |
| `macmaid developer-caches`| `--scan-only`, `--apply`, `--yes` | Scans and cleans package manager caches. |
| `macmaid developer` | `[kind: storage\|runtimes\|environments\|tools\|sdks]` | Inspects developer tools and runtimes. |
| `macmaid snapshots` | `--thin <GB>`, `--apply`, `--yes` | Lists or thins APFS local snapshots via `tmutil`. |
| `macmaid history` | `--limit <N>` | Displays recent operation logs. |
| `macmaid restore` | `--operation-id <ID>`, `--trash-path <path>`, `--copy` | Restores an item moved to Trash during a prior operation. |
| `macmaid whitelist` | None | Displays protected paths and glob patterns from whitelist. |
| `macmaid update` | `--apply` | Checks or applies updates via Homebrew. |
| `macmaid uninstall` | `--purge-data` | Uninstalls MacMaid configuration, logs, and completion hooks. |
| `macmaid ui` | `--port <port>`, `--no-open`, `--app` | Launches native desktop app / UI. |

---

## 4. Security Invariants & Destructive Operation Boundaries

1. **Non-Root Execution:**
   - Must fail immediately if `getuid() == 0` or `geteuid() == 0`.
   - Never escalate via `sudo` or request administrator credentials except explicitly for `mdutil` (Spotlight).
2. **Path Allowlist & Hard-Blocked Roots:**
   - Root filesystem and system folders (`/`, `/System`, `/Library`, `/Applications`, `/Users`, `/Volumes`, `/bin`, `/sbin`, `/usr`, `/etc`, `/var`, `/private`) are hard-blocked.
   - Deletion targets must strictly reside within pre-authorized domains (`~/Library/Caches`, `~/Library/Logs`, `~/Library/Developer/Xcode/DerivedData`, `.npm`, `.cargo/registry/cache`, etc.) or verified application support cache leaves.
3. **Symlink Ancestor Defense:**
   - Traversal must reject any path where any ancestor is a symbolic link.
   - Symlinks themselves are never followed during deletions.
4. **Descriptor-Anchored Filesystem Operations:**
   - Parent directory pinned with `O_RDONLY | O_DIRECTORY | O_NOFOLLOW`.
   - Operations performed via `*at` calls (`fstatat`, `unlinkat`, `renameatx_np`).
   - Ownership verified: `st_uid == getuid()`.
5. **Exclusive Atomic Trash Moves:**
   - Moves to `~/.Trash` must use macOS `renameatx_np` with `RENAME_EXCL` (`0x00000004`).
   - Never overwrite, never copy-and-delete fallback.
   - Post-condition check: compare `(st_dev, st_ino)` of source before move and destination after move. Source must be gone, destination must match.
6. **Execution-Time Revalidation:**
   - Every target is re-validated at the moment of execution against whitelist and safety rules. Pre-scan results do not authorize mutation.
7. **Process PID Reuse Defense:**
   - Process termination verifies executable path and creation time before sending signals (`SIGTERM`, `SIGKILL`).
   - Protected processes (PID 1, `WindowServer`, `loginwindow`, Finder, Dock, Terminal, etc.) are unkillable.

---

## 5. Application State & Storage Formats

1. **Configuration Directory:** `~/.config/macmaid/`
   - `whitelist`: Plain text, UTF-8, line-separated exact paths or glob patterns.
   - `settings.json`: Key-value JSON (e.g. `{"language": "en"}`).
2. **Log & Audit Directory:** `~/Library/Logs/MacMaid/`
   - `operations.jsonl`: Line-delimited JSON records.
   - Record fields: `timestamp`, `operation_id`, `category`, `label`, `path`, `status`, `error`, `trash_path`, `processed_estimated_bytes`, `estimated_reclaimed_bytes`, `reclaim_status`.
   - Summary records: `operation_summary` with `freed`, `failed`, `skipped`, `scanned_estimated_bytes`, `trash_moved_estimated_bytes`, `observed_free_bytes_delta`.

---

## 6. Homebrew Distribution Contract

- **Homebrew Cask (`Casks/macmaid.rb`):**
  - Installs `MacMaid.app` inside `/Applications`.
  - Artifact name: `MacMaid-{VERSION}-arm64.dmg`.
  - SHA-256 verified.
  - `zap trash: ["~/.config/macmaid", "~/Library/Logs/MacMaid"]`.
- **Homebrew Formula (`Formula/macmaid.rb`):**
  - Installs standalone CLI executable `macmaid` into `libexec/` and symlinks into `bin/macmaid`.
  - Artifact name: `MacMaid-{VERSION}-arm64-cli.tar.gz`.
  - Verifies: `macmaid --version`.
  - No Python runtime or external dependencies required.
