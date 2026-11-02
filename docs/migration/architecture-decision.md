# MacMaid Architecture Decision Record: Rust Core & Native macOS Desktop

**Date:** 2026-11-02  
**Status:** Approved  
**Decision:** Migrate to a Cargo Workspace (Rust Core, CLI, C-FFI) with a Native SwiftUI/AppKit macOS Desktop Application  

---

## 1. Context & Problem Statement

MacMaid was originally built as a Python application with a localhost HTTP server running on `127.0.0.1:8123` and a WKWebView wrapper (`MacMaidApp.swift`). While this allowed rapid early development, it introduced significant drawbacks:
- Python runtime dependency, pyinstaller bundle bloat (~80MB+), and slow startup.
- Inherent security surface of a localhost HTTP daemon receiving mutation commands.
- Memory overhead of Python processes and browser rendering engines.
- Inability to provide genuine native macOS controls, animations, and fluid window management.

The goal is to migrate MacMaid completely to Rust for all core operations, provide an independent native Rust CLI binary, and provide a genuine native macOS desktop UI using SwiftUI/AppKit communicating with the Rust core via a typed, thread-safe, panic-bounded C ABI interface.

---

## 2. Decision Matrix: UI Architecture

| Option | Pros | Cons | Decision |
|---|---|---|---|
| **A. Rust Core + Native SwiftUI / AppKit Desktop** | Genuine macOS controls, SF Symbols, native window management, zero browser overhead, excellent performance, direct OS integration, conforms to Apple Human Interface Guidelines. | Requires C-ABI / FFI bridge between Swift and Rust. | **SELECTED (Preferred & Implemented)** |
| **B. All-Rust GUI (e.g. Slint / iced)** | Single-language stack. | Non-native widget rendering on macOS, lack of standard macOS menus, sheet modals, standard file dialogs, and accessibility integration; looks out of place on modern macOS. | Rejected |
| **C. Tauri / Webview** | Reuses web assets. | Violates user requirement ("Run without a browser... Do not default to Tauri or an embedded WKWebView... genuine desktop application"). | Rejected |
| **D. Python with PySide / PyQt** | Keeps Python code. | Heavyweight, violates the non-Python requirement. | Rejected |

---

## 3. Workspace Architecture

The Rust workspace consists of:

```
MacMaid/
├── Cargo.toml                  # Workspace definition
├── crates/
│   ├── macmaid-core/          # Shared business logic, models, scanning, cleaning, safety, analyzer, memory, developer, etc.
│   │   ├── Cargo.toml
│   │   └── src/
│   ├── macmaid-cli/           # Standalone command-line binary `macmaid`
│   │   ├── Cargo.toml
│   │   └── src/
│   └── macmaid-ffi/           # C ABI dynamic/static library (`libmacmaid_ffi.a` + `macmaid_ffi.h`)
│       ├── Cargo.toml
│       └── src/
├── apps/
│   └── macos/                 # Native macOS SwiftUI / AppKit desktop application
│       ├── MacMaid/
│       │   ├── App/           # Lifecycle, Menu, Window commands
│       │   ├── Bridge/        # Swift wrappers over macmaid-ffi C ABI
│       │   ├── Models/        # Observable state objects
│       │   ├── Views/         # Native SwiftUI views (Clean, Analyzer, Treemap, Apps, Memory, Developer, Files, Health, History, Settings)
│       │   └── Resources/     # Assets, icons, strings
│       └── Makefile / scripts
├── tests/                     # Integration and safety fault-injection tests
└── docs/migration/            # Migration reports and documentation
```

---

## 4. Concurrency & Safety Model

1. **Panic Containment:**
   All FFI boundaries are wrapped with `std::panic::catch_unwind`. Any unexpected panic returns a structured error code (`MACMAID_ERR_PANIC`) rather than unwinding across foreign stack frames.
2. **Memory Ownership:**
   - Buffers allocated in Rust are freed in Rust via explicit destructor functions (`macmaid_free_string`, `macmaid_free_bytes`).
   - Swift consumes UTF-8 strings and converts them to Swift `String` instances immediately.
3. **Thread Safety & Cancellation:**
   - Long-running filesystem scans and analysis run on Rust background worker threads.
   - Operations take an atomic `CancellationToken`. Swift can trigger cancellation from UI buttons asynchronously.
   - Progress callbacks are delivered to Swift via function pointers and dispatched to the UI thread via `DispatchQueue.main`.
4. **Filesystem Safety Invariants:**
   - Descriptor-anchored operations using macOS `openat`, `fstatat`, `unlinkat`.
   - `RENAME_EXCL` via `renameatx_np` for atomic Trash moves.
   - Re-validation immediately before destructive actions.
