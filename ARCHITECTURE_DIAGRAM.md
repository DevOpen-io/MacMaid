# MacMaid Architecture Diagram

## System Overview

MacMaid is a Python-based macOS cleanup, maintenance, and system optimization tool with a safety-first architecture. The system is designed around a core principle: **never compromise user data safety for disk space recovery**.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MACMAID SYSTEM ARCHITECTURE                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Core Architecture Layers

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACES                                  │
├──────────────────────────────────────────────────────────────────────────────┤
│  CLI (cli.py)  │  TUI (tui.py)  │  Web UI (web.py + WebUI/)                   │
│  ┌──────────┐  │  ┌──────────┐  │  ┌──────────────────────────────────────┐  │
│  │ argparse│  │  │ Textual  │  │  │ ThreadingHTTPServer + React frontend │  │
│  │ commands│  │  │ Terminal │  │  │ Localhost:8123 with session tokens   │  │
│  └──────────┘  │  └──────────┘  │  └──────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                           FEATURE LAYER (features.py)                         │
├──────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │ApplicationManager│  │ProjectPurgeManager│  │RecoveryCenter           │  │
│  │- App uninstall   │  │- Project cleanup  │  │- Restore from Trash     │  │
│  │- Leftover removal │  │- Build artifacts  │  │- Operation history      │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────────────┘  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │OPTIMIZATIONS     │  │system_status()   │  │doctor()                  │  │
│  │- DNS cache       │  │- Disk/health info │  │- Diagnostics            │  │
│  │- Quick Look      │  │- Memory pressure  │  │- Environment check      │  │
│  │- Spotlight       │  │- Thermal state    │  │                          │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         DOMAIN LOGIC LAYER                                     │
├──────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │Scanner           │  │Cleaner           │  │DeveloperInventory        │  │
│  │(scanner.py)      │  │(cleaner.py)      │  │(developer.py)            │  │
│  │- Cleanup discovery│  │- Safe execution  │  │- Runtime management     │  │
│  │- Risk classification│  │- Path validation │  │- Environment cleanup    │  │
│  │- Size measurement │  │- Whitelist check  │  │- SDK inventory          │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────────────┘  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │IncrementalAnalyzer│ │PackageManagerCache│ │Specialized Scanners      │  │
│  │(analyzer.py)      │ │Scanner            │ │- Duplicates              │  │
│  │- Disk usage       │ │- Manager cleanup  │ │- Large files             │  │
│  │- Tree navigation  │ │- Cache detection  │ │- Smart downloads         │  │
│  │- Background work  │ │                   │ │- Browser storage         │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         SAFETY & SYSTEM LAYER                                 │
├──────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │PathSafety        │  │Config            │  │System                   │  │
│  │(safety.py)       │  │(config.py)       │  │(system.py)              │  │
│  │- Path validation │  │- Whitelist       │  │- Subprocess execution   │  │
│  │- Symlink safety  │  │- State files     │  │- Disk measurement       │  │
│  │- Protected roots  │  │- Audit logs      │  │- macOS integration      │  │
│  │- Allowlist check  │  │- Directory safety│  │- Process management     │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         CORE MODELS (models.py)                                │
├──────────────────────────────────────────────────────────────────────────────┤
│  RiskLevel: SAFE, MODERATE, AGGRESSIVE, MANUAL_ONLY                           │
│  CleanupProfile: SAFE, DEEP, DEVELOPER, AGGRESSIVE                            │
│  CleanupCategory: USER_CACHES, BROWSER_CACHES, DEVELOPER, etc.                │
│  ActionType: REMOVE_PATH, COMMAND, MOVE_TO_TRASH, etc.                       │
│  CleanupItem: Individual cleanup target with metadata                         │
│  ScanResult: Collection of cleanup items with status                          │
│  OperationResult: Execution results with space reclaimed                      │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow: Cleanup Operation

```
USER REQUEST (CLI/TUI/Web)
        │
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 1. SCANNING PHASE (Scanner)                                                   │
└──────────────────────────────────────────────────────────────────────────────┘
        │
        ├─► User caches → ~/Library/Caches/*
        ├─► Browser caches → Chrome/Firefox/Safari cache directories
        ├─► Application caches → VS Code, Slack, Discord, etc.
        ├─► Sandbox caches → ~/Library/Containers/*/Data/Library/Caches
        ├─► Logs & diagnostics → Old log files (>7 days)
        ├─► Developer tools → Xcode DerivedData, CocoaPods, SwiftPM
        ├─► Package managers → brew, npm, pnpm, uv, cargo, etc.
        ├─► Temporary files → /private/tmp, /private/var/tmp
        └─► Trash → ~/.Trash contents
        │
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 2. VALIDATION PHASE                                                            │
└──────────────────────────────────────────────────────────────────────────────┘
        │
        ├─► PathSafety.validate_deletion_path()
        │   ├─► Lexical validation (no "..", absolute paths)
        │   ├─► HARD_BLOCKED check (/, /System, /Applications, etc.)
        │   ├─► Allowed roots check (~/Library/Caches, etc.)
        │   ├─► Symlink ancestor rejection
        │   └─► Sandbox/App Support cache validation
        │
        ├─► Config.require_unprotected()
        │   └─► Whitelist pattern matching
        │
        ├─► Risk level classification
        │   └─► SAFE, MODERATE, AGGRESSIVE, MANUAL_ONLY
        │
        └─► Application running check
            └─► process_running() for app-specific caches
        │
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 3. REVIEW PHASE (review.py)                                                    │
└──────────────────────────────────────────────────────────────────────────────┘
        │
        ├─► cleanup_plan() → Generate operation review
        ├─► User confirmation (interactive CLI/TUI/Web)
        ├─► Risk-based warnings
        └─► Space estimation
        │
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 4. EXECUTION PHASE (Cleaner)                                                   │
└──────────────────────────────────────────────────────────────────────────────┘
        │
        ├─► Pre-execution validation
        │   ├─► os.geteuid() == 0 check (NEVER run as root)
        │   ├─► Re-validate PathSafety (TOCTOU protection)
        │   ├─► Re-check whitelist
        │   └─► Ensure audit logs are safe
        │
        ├─► Execute based on ActionType:
        │   │
        │   ├─► REMOVE_PATH → remove_validated_path()
        │   │   └─► Directory descriptor-based deletion
        │   │
        │   ├─► REMOVE_CHILDREN → Recursive child deletion
        │   │   └─► Keep parent directory structure
        │   │
        │   ├─► MOVE_TO_TRASH → move_to_trash_exclusive()
        │   │   ├─► Atomic renameatx_np (macOS-specific)
        │   │   ├─► RENAME_EXCL flag (no overwrite)
        │   │   └─► Post-condition verification
        │   │
        │   ├─► COMMAND → run_command()
        │   │   ├─► Manager-specific cleanup (brew cleanup, etc.)
        │   │   ├─► Shell=False, explicit arguments
        │   │   └─► Timeout + process group killing
        │   │
        │   └─► MANUAL_CACHE_FALLBACK → Strict allowlist check
        │       └─► manual_cache_allowed() validation
        │
        ├─► Post-execution verification
        │   ├─► Target no longer exists
        │   ├─► Trash destination exists (if moved)
        │   └─► Filesystem free space measurement
        │
        └─► Audit logging
            ├─► JSONL operation log
            ├─► Operation ID tracking
            ├─► Restorable flag for Trash moves
            └─► Space reclamation metrics
```

## Key Safety Mechanisms

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                      DEFENSE IN DEPTH STRATEGY                                 │
└──────────────────────────────────────────────────────────────────────────────┘

1. LAYER 1: Path Validation (PathSafety)
   ├─► HARD_BLOCKED: /, /System, /bin, /sbin, /usr, /etc, /var, /Library, /Applications, /Users, /Volumes
   ├─► ALLOWED_ROOTS: ~/Library/Caches, ~/Library/Logs, ~/.npm, ~/.gradle/caches, etc.
   ├─► Symlink ancestor rejection
   └─► Lexical validation (no "..", absolute paths only)

2. LAYER 2: Whitelist Protection (Config)
   ├─► User-controlled whitelist file
   ├─► Pattern matching (glob support)
   ├─► Strict validation at execution time
   └─► Fail-closed if whitelist unreadable

3. LAYER 3: Ownership Validation
   ├─► All targets must be owned by current user (os.getuid())
   ├──► No root operations (os.geteuid() == 0 check)
   ├─► Directory descriptor-based operations
   └─► Symlink rejection at every level

4. LAYER 4: Risk Classification
   ├─► SAFE: Recreatable caches, logs
   ├─► MODERATE: Apple system caches, temp files
   ├─► AGGRESSIVE: Package manager caches
   └─► MANUAL_ONLY: Requires explicit second confirmation

5. LAYER 5: Application State Protection
   ├─► Process running detection
   ├─► App closure requirement before cleanup
   └─► Active runtime protection (developer tools)

6. LAYER 6: Execution-Time Revalidation
   ├─► TOCTOU protection (Time-Of-Check-Time-Of-Use)
   ├─► Path re-validation before deletion
   ├─► Whitelist re-check before execution
   └─► Post-condition verification

7. LAYER 7: Audit Trail
   ├─► JSONL operation log
   ├─► Operation ID tracking
   ├─► Restorable flag for Trash moves
   └─► Filesystem free space measurement
```

## Module Responsibilities

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ models.py          │ Core data structures and enums                           │
│                   │ CleanupItem, ScanResult, RiskLevel, ActionType, etc.     │
├──────────────────────────────────────────────────────────────────────────────┤
│ config.py          │ Configuration and state management                       │
│                   │ Whitelist, audit logs, directory safety                  │
├──────────────────────────────────────────────────────────────────────────────┤
│ safety.py          │ Path validation and safety gates                         │
│                   │ PathSafety class, manual_cache_allowed()                  │
├──────────────────────────────────────────────────────────────────────────────┤
│ system.py          │ Low-level macOS operations                               │
│                   │ Subprocess execution, disk measurement, process mgmt      │
├──────────────────────────────────────────────────────────────────────────────┤
│ scanner.py         │ Cleanup discovery (READ-ONLY)                            │
│                   │ Cache scanning, package manager detection                │
├──────────────────────────────────────────────────────────────────────────────┤
│ cleaner.py         │ Cleanup execution with safety validation                 │
│                   │ Deletion, Trash moves, command execution, audit logging  │
├──────────────────────────────────────────────────────────────────────────────┤
│ developer.py       │ Developer tool management                                │
│                   │ Runtime inventory, environment cleanup, SDK management   │
├──────────────────────────────────────────────────────────────────────────────┤
│ analyzer.py        │ Incremental disk analysis                               │
│                   │ Background tree traversal, size measurement, navigation   │
├──────────────────────────────────────────────────────────────────────────────┤
│ features.py        │ High-level features                                      │
│                   │ App management, project purge, optimizations, recovery    │
├──────────────────────────────────────────────────────────────────────────────┤
│ cli.py             │ Command-line interface                                   │
│                   │ argparse commands, interactive prompts, output formatting │
├──────────────────────────────────────────────────────────────────────────────┤
│ tui.py             │ Terminal UI (Textual)                                    │
│                   │ Interactive menus, progress bars, keyboard navigation     │
├──────────────────────────────────────────────────────────────────────────────┤
│ web.py             │ Web UI and API layer                                     │
│                   │ HTTP server, session management, REST endpoints         │
├──────────────────────────────────────────────────────────────────────────────┤
│ review.py          │ Operation review and planning                            │
│                   │ cleanup_plan(), developer_plan(), validation tokens      │
├──────────────────────────────────────────────────────────────────────────────┤
│ reporting.py       │ Space measurement and reporting                          │
│                   │ FreeSpaceProbe, disk usage tracking                      │
├──────────────────────────────────────────────────────────────────────────────┤
│ cancellation.py    │ Cancellation token management                           │
│                   │ CancellationToken, ScanCancelled exception                 │
├──────────────────────────────────────────────────────────────────────────────┤
│ duplicates.py      │ Duplicate file detection                                 │
│                   │ Hash-based duplicate finding                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ large_files.py     │ Large/old file scanning                                  │
│                   │ Size and age-based file discovery                         │
├──────────────────────────────────────────────────────────────────────────────┤
│ smart_downloads.py │ Smart downloads cleanup                                  │
│                   │ Intelligent download file categorization                  │
├──────────────────────────────────────────────────────────────────────────────┤
│ browser_storage.py │ Browser storage inspection                               │
│                   │ Cache, cookies, history analysis                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Concurrency Model

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                      CONCURRENCY STRATEGY                                      │
└──────────────────────────────────────────────────────────────────────────────┘

Scanner:
├─► Sequential phase execution (user caches → browser → application → ...)
├─► Parallel size measurement within phases (ThreadPoolExecutor, max 8 workers)
├─► Cancellation token support
└─► Progress callbacks for UI updates

Analyzer (IncrementalAnalyzer):
├─► Process-local singleton with thread-safe state
├─► Bounded ThreadPoolExecutor (max 8 workers)
├─► Job-based navigation with pause/resume
├─► Cancellation support with stale work rejection
├─► Cache-aware (resume previous navigation instantly)
└─► Background size measurement with streaming results

Web Server:
├─► ThreadingHTTPServer (multi-threaded request handling)
├─► Thread-safe WebState with RLock
├─► ProgressState with thread-safe updates
├─► Mutation lock for destructive operations
└─► Session token validation

TUI:
├─► Textual event loop (single-threaded UI)
├─► Worker threads for blocking operations
├──► Background scanning
├──► Background cleanup execution
└──► Background size measurement
```

## Package Manager Integration

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                  PACKAGE MANAGER CLEANUP STRATEGY                              │
└──────────────────────────────────────────────────────────────────────────────┘

Preferred: Manager's Official Command
├─► brew: brew cleanup --prune=all
├─► pnpm: pnpm store prune
├─► uv: uv cache prune
├─► go: go clean -cache -testcache
├─► bun: bun pm cache rm
├─► pip: python -m pip cache purge
├─► yarn: yarn cache clean (v1 only)
├─► composer: composer clear-cache
├─► dotnet: dotnet nuget locals --clear
├─► conda: conda clean --all
└─► npm: npm cache clean --force (AGGRESSIVE)

Fallback: Manual Cache Deletion (MANUAL_ONLY risk)
├─► Strict allowlist via manual_cache_allowed()
├─► Exact path matching only
├─► Requires second interactive confirmation
└─► Used only when manager command unavailable

Runtime Management (developer.py):
├─► mise: mise uninstall <tool>@<version>
├─► asdf: asdf uninstall <tool> <version>
├─► pyenv: pyenv uninstall -f <version>
├─► rbenv: rbenv uninstall -f <version>
├─► nodenv: nodenv uninstall -f <version>
├─► rustup: rustup toolchain uninstall <version>
├─► fnm: fnm uninstall <version>
├─► Homebrew: brew uninstall --formula <formula>
└─► Conda: conda env remove -p <path> -y
```

## Risk-Based Cleanup Profiles

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    CLEANUP PROFILES                                             │
└──────────────────────────────────────────────────────────────────────────────┘

SAFE Profile:
├─► Maximum risk: SAFE
├─► User caches (non-Apple)
├─► Browser caches
├─► Application caches
├─► Logs (>7 days old)
└─► No developer tools

DEEP Profile:
├─► Maximum risk: MODERATE
├─► Everything in SAFE
├─► Apple system caches
├─► Saved application state
├─► Temporary files (>7 days old)
└─► No developer tools

DEVELOPER Profile:
├─► Maximum risk: MODERATE
├─► Everything in SAFE
├─► Developer tools (Xcode, CocoaPods, SwiftPM)
├─► Package manager caches
└─► No temporary files

AGGRESSIVE Profile:
├─► Maximum risk: AGGRESSIVE
├─► Everything in DEEP + DEVELOPER
├─► Temporary files (>2 days old)
├─► Package manager caches (including npm)
└─► Requires explicit confirmation
```

## Key Design Principles

1. **Fail-Closed**: If safety cannot be established, skip the operation
2. **Never Run as Root**: MacMaid must never run with sudo/root privileges
3. **Trash Before Delete**: Prefer moving to Trash over permanent deletion
4. **Manager-Owned Resources**: Use manager commands for package manager cleanup
5. **TOCTOU Protection**: Re-validate paths at execution time
6. **User Data Boundary**: Distinguish between caches and user data
7. **Auditability**: Log all destructive operations with structured records
8. **macOS Compatibility**: Support both Apple Silicon and Intel Macs
9. **Capability Detection**: Detect features rather than assume by OS version
10. **Minimal Dependencies**: Prefer stdlib over external packages

## File System Safety

```
Protected Operations:
├─► Use directory descriptors (avoid path-based race conditions)
├─► Atomic operations where possible (renameatx_np for Trash)
├─► No symlink following during recursive operations
├─► Ownership validation at every level
└─► Post-condition verification

Forbidden Patterns:
├─► os.system() / subprocess.run(shell=True)
├─► eval() / exec()
├─► rm -rf / sudo rm
├─► Arbitrary command interpolation
└─► Following symlinks blindly
```

This architecture ensures MacMaid can safely clean macOS systems while protecting user data and maintaining system integrity.