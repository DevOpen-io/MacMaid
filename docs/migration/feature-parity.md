# MacMaid Complete Feature Parity Matrix

## Executive Overview

This document provides a comprehensive, item-by-item verification matrix confirming 100% functional and behavioral parity between the legacy Python implementation and the new Rust/Swift native desktop architecture.

---

## 1. Feature Parity Matrix

| Feature Area | Legacy Python Module | Rust Workspace Component | Native SwiftUI View (`apps/macos`) | CLI Command | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Smart Clean** | `scanner.py`, `cleaner.py` | `macmaid-core::scanner`, `cleaner` | `SmartCleanView.swift` | `macmaid scan`, `clean` | **100% Parity** |
| **Disk Analyzer** | `analyzer.py` | `macmaid-core::analyzer` | `DiskAnalyzerView.swift` | `macmaid analyze` | **100% Parity** |
| **Storage Treemap** | `WebUI/app.js` (Canvas/DOM) | `macmaid-core::analyzer` | `StorageTreemapView.swift` | N/A (GUI Feature) | **100% Parity** |
| **App Uninstaller** | `features.py` (`InstalledAppFinder`) | `macmaid-core::apps` | `AppUninstallerView.swift` | `macmaid apps`, `leftovers` | **100% Parity** |
| **Memory Monitor** | `features.py` (`MemoryWatcher`) | `macmaid-core::memory` | `MemoryManagementView.swift` | `macmaid memory` | **100% Parity** |
| **Developer Storage** | `developer.py` | `macmaid-core::developer` | `DeveloperStorageView.swift` | `macmaid developer`, `developer-caches` | **100% Parity** |
| **Browser Storage** | `scanner.py` (`BrowserStorage`) | `macmaid-core::browser_storage` | `SmartCleanView.swift` (Category) | `macmaid browser-storage` | **100% Parity** |
| **Duplicate Finder** | `features.py` (`DuplicateFinder`) | `macmaid-core::duplicates` | `DuplicateFinderView.swift` | `macmaid duplicates` | **100% Parity** |
| **Large & Old Files** | `features.py` (`LargeOldFileFinder`) | `macmaid-core::large_files` | `LargeFilesView.swift` | `macmaid large-files` | **100% Parity** |
| **Smart Downloads** | `features.py` (`DownloadsCategorizer`) | `macmaid-core::smart_downloads` | `SmartDownloadsView.swift` | `macmaid smart-downloads`, `installers` | **100% Parity** |
| **Project Purge** | `features.py` (`ProjectPurgeManager`) | `macmaid-core::purge` | `ProjectPurgeView.swift` | `macmaid purge` | **100% Parity** |
| **System Diagnostics** | `features.py` (`HealthDoctor`) | `macmaid-core::doctor` | `HealthDoctorView.swift` | `macmaid doctor` | **100% Parity** |
| **Audit & History** | `cleaner.py` (`AuditLogger`) | `macmaid-core::reporting` | `HistoryView.swift` | `macmaid history` | **100% Parity** |
| **Trash Recovery** | `cleaner.py` (`RecoveryCenter`) | `macmaid-core::recovery` | `HistoryView.swift` | `macmaid restore` | **100% Parity** |
| **Safety & Whitelist** | `safety.py`, `config.py` | `macmaid-core::safety`, `config` | `SettingsView.swift` | `macmaid whitelist` | **100% Parity** |
| **APFS Snapshots** | `system.py` | `macmaid-core::system` | `HealthDoctorView.swift` | `macmaid snapshots` | **100% Parity** |
| **Shell Completions** | `cli.py` (`completion`) | `macmaid-cli::main` | N/A (CLI Feature) | `macmaid completion` | **100% Parity** |
| **Localization** | `i18n.py`, `WebUI/` strings | `macmaid-core::i18n` | `AppState.swift` (`tr()`) | Multi-language UI | **100% Parity** |

---

## 2. Detailed Subsystem Parity

### 2.1 Smart Clean
- **Profiles:** Exactly preserves `safe`, `deep`, `aggressive`, and `developer` scan profiles.
- **Categories:** Preserves User Caches, Log Files, Browser Caches, Crash Reports, Saved Application State, Developer Artifacts, Trash, and System Temp.
- **Dry-run & Execution:** `--scan-only` prints table with sizes and risk badges. Non-dry-run requires explicit confirmation (or `--dry-run false --confirm true` in CLI, interactive confirmation sheet in Desktop UI).
- **Execution Engine:** Atomic descriptor-anchored deletion via `openat(O_DIRECTORY | O_NOFOLLOW)` and `unlinkat`.

### 2.2 Disk Analyzer & Proportional Treemap
- **Incremental Sizing:** Recursive disk tree calculation with real-time item counter callbacks.
- **Breadcrumb Navigation:** Full drill-down through directory hierarchies in native SwiftUI.
- **Interactive Proportional Treemap:** Squarified/proportional 2D rectangle packing with auto-sizing based on byte weight, tooltip hover, and click-to-enter folder zoom.
- **Safe Operations:** Right-click or button to "Move to Trash" with path validation and fail-closed confirmation.

### 2.3 Application Removal & Leftovers
- **Discovery:** Scans `/Applications`, `/System/Applications`, and `~/Applications`.
- **Metadata Extraction:** Parses `Info.plist` (CFBundleIdentifier, CFBundleName, CFBundleShortVersionString) using native `plist` crate.
- **Homebrew Cask Detection:** Checks `brew list --cask` to prevent breaking Homebrew-managed applications without explicit user notice.
- **Leftover Detection:** Identifies related bundle directories across `~/Library/Application Support`, `~/Library/Caches`, `~/Library/Preferences`, `~/Library/Saved Application State`, `~/Library/Logs`, `~/Library/Containers`.
- **Safe Uninstallation:** Validates bundle identity, verifies application is not currently executing, moves bundle and selected leftovers atomically to Trash.

### 2.4 Process & Memory Management
- **Metrics:** Gathers per-process PID, Process Name, RSS (Resident Set Size), Virtual Memory, CPU%, and Execution Path using kernel `sysinfo` APIs.
- **Growth Slope Tracking:** Computes rolling slope across time-series samples to detect memory leaks.
- **Protected Processes:** Strictly prevents terminating root-owned processes, critical macOS system daemons (kernel_task, launchd, WindowServer, Finder, Dock), and MacMaid itself.
- **Termination Lifecycle:** Explicit user review required before sending `SIGTERM` or `SIGKILL`.

### 2.5 Developer Storage Management
- **Xcode:** DerivedData, Archives, iOS DeviceSupport, CoreSimulator Caches, simulator runtime images.
- **Docker:** Build cache, unused images, dead containers (delegated safely to `docker system prune` or direct cache cleanup).
- **Cargo / Rust:** `~/.cargo/registry/cache`, `target/` directories in known workspaces.
- **Node.js / npm / pnpm / yarn:** Global cache directories (`~/.npm`, `~/.yarn/cache`, `~/.pnpm-store`).
- **Python:** pip cache, virtualenv caches.
- **Gradle & Android:** Android SDK build-tools, emulator virtual device storage (AVD), Gradle wrapper caches.

### 2.6 Duplicate File Finder
- **Two-Phase Hashing:**
  1. Quick 4KB prefix SHA-256 hash to eliminate non-matching candidates.
  2. Full SHA-256 content hash on matching sizes.
- **Read-Only Invariant:** Strictly read-only output. Never automatically deletes duplicate files. Provides verified duplicate paths for user review.

### 2.7 Browser Storage Separation
- **Disposable Caches:** WebKit / Chromium `Cache`, `Code Cache`, `GPUCache`.
- **Protected Persistent State:** Explicitly excludes cookies, `Login Data`, `Web Data`, IndexedDB, and active session files.

### 2.8 Audit Logging & Recovery
- **Audit File:** Operations appended in JSON Lines format to `~/Library/Logs/MacMaid/operations.jsonl`.
- **Record Schema:** `timestamp`, `operation_id`, `category`, `path`, `action_type`, `estimated_bytes`, `status`, `trash_path`.
- **Safe Recovery:** `RecoveryCenter` verifies item exists in `~/.Trash`, confirms destination safety, and restores atomically via `renameatx_np(RENAME_EXCL)` or safe fallback.

---

## 3. CLI Command Parity Matrix

Every single command supported by legacy MacMaid is implemented and tested in `crates/macmaid-cli`:

| Command | Arguments / Flags | Description | Verified |
| :--- | :--- | :--- | :--- |
| `macmaid doctor` | N/A | System health and Full Disk Access diagnostics | [x] |
| `macmaid status` | N/A | System storage and memory overview | [x] |
| `macmaid scan` | `--profile`, `--trash`, `--system-temp`, `--scan-only` | Scan cleanup candidates | [x] |
| `macmaid clean` | `--profile`, `--trash`, `--system-temp`, `--dry-run`, `--confirm` | Clean candidates with confirmation | [x] |
| `macmaid analyze` | `<PATH>`, `--top` | Analyze directory storage breakdown | [x] |
| `macmaid duplicates` | `<PATH>`, `--min-size` | Find duplicate files by SHA-256 hash | [x] |
| `macmaid large-files`| `<PATH>`, `--min-size`, `--older-than-days`, `--top` | Scan large and old files | [x] |
| `macmaid smart-downloads` | `--older-than-days` | Categorize downloads folder | [x] |
| `macmaid browser-storage` | N/A | Inspect browser caches | [x] |
| `macmaid apps` | `--unused-days`, `--casks-only`, `--sort` | List installed applications | [x] |
| `macmaid leftovers`| N/A | Detect orphaned application leftovers | [x] |
| `macmaid purge` | `--path`, `--clean` | Purge developer build artifacts | [x] |
| `macmaid memory` | `--limit`, `--sort`, `--kill-pid` | Inspect processes and manage memory | [x] |
| `macmaid developer`| N/A | Inspect developer caches and tools | [x] |
| `macmaid developer-caches` | `--clean` | Clean package manager and build caches | [x] |
| `macmaid installers` | N/A | Scan leftover disk images and pkg installers | [x] |
| `macmaid snapshots`| N/A | Inspect local APFS snapshots | [x] |
| `macmaid history` | `--limit` | Display operation audit log | [x] |
| `macmaid restore` | `<PATH>` | Restore an item moved to Trash | [x] |
| `macmaid whitelist`| `add <PATTERN>`, `remove <PATTERN>`, `list` | Manage protected paths and rules | [x] |
| `macmaid completion`| `<SHELL>`, `--print`, `--install` | Generate shell completions (zsh, bash, fish)| [x] |
| `macmaid update` | N/A | Check for new releases | [x] |
| `macmaid uninstall`| N/A | Remove MacMaid installation | [x] |
| `macmaid ui` | N/A | Launch native macOS Desktop Application | [x] |
