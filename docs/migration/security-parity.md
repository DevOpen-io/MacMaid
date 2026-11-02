# MacMaid Security & Safety Parity Specification

## Overview

MacMaid is designed with a **fail-closed, defense-in-depth** security architecture. Every filesystem mutation, process termination, and system interaction must pass rigorous validation boundaries before execution.

The Rust core (`macmaid-core`) enforces every invariant established in the Python baseline while hardening them through Rust's type system, memory safety guarantees, and low-level POSIX/macOS kernel system calls.

---

## 1. Destructive Operation Lifecycle

Every mutation follows the strict 9-phase lifecycle:

```
[1. Discover]
     │
     ▼
[2. Classify] ──> Categorize risk level (Safe, Moderate, Danger)
     │
     ▼
[3. Validate] ──> Reject hard-blocked roots, symlink ancestors, and whitelisted patterns
     │
     ▼
[4. Review]   ──> Present itemized candidates to user with path, size, and risk badge
     │
     ▼
[5. Confirm]  ──> Require explicit confirmation flag or modal approval
     │
     ▼
[6. Revalidate]─> Re-verify path safety, whitelist, and existence immediately before execution
     │
     ▼
[7. Execute]  ──> Perform descriptor-anchored deletion or renameatx_np(RENAME_EXCL) move
     │
     ▼
[8. Verify]   ──> Stat destination and confirm source no longer exists
     │
     ▼
[9. Record]   ──> Append structured JSON audit record to ~/Library/Logs/MacMaid/operations.jsonl
```

---

## 2. Hard-Blocked Paths & Scope Enforcement

The safety module (`crates/macmaid-core/src/safety.rs`) defines immutable protection barriers.

### 2.1 Hard-Blocked System Roots
The following paths (and any relative or non-canonical representation) can **never** be targeted for deletion or trash moves:
- `/`
- `/Applications`
- `/Applications/Utilities`
- `/Library`
- `/Network`
- `/System`
- `/System/Applications`
- `/System/Library`
- `/bin`, `/sbin`, `/usr`, `/usr/bin`, `/usr/sbin`, `/usr/lib`, `/usr/local`
- `/etc`, `/var`, `/tmp`, `/opt`, `/private`
- `/dev`, `/Volumes`
- User Home directory (`~`)
- User Top-Level Directories:
  - `~/Desktop`
  - `~/Documents`
  - `~/Downloads`
  - `~/Library`
  - `~/Movies`, `~/Music`, `~/Pictures`
  - `~/Applications`
  - `~/.ssh`, `~/.gnupg`, `~/.aws`, `~/.config`

Any attempt to target these paths immediately raises `PathSafetyError::HardBlockedRoot`.

### 2.2 Allowed Deletion Roots
Filesystem deletions are strictly restricted to verified subdirectories:
- `~/Library/Caches`
- `~/Library/Logs`
- `~/Library/DiagnosticReports`
- `~/Library/Saved Application State`
- `~/.Trash`
- Bounded project build artifact directories (e.g., `target/`, `node_modules/`, `build/`, `.gradle/`).

---

## 3. Strict Symlink & Descriptor Security

### 3.1 Symlinked Ancestor Rejection (`_reject_symlink_ancestors`)
Before performing any operation, MacMaid walks the path hierarchy from root to target. If any intermediate component is a symbolic link, the operation is aborted with `PathSafetyError::SymlinkedAncestor`. This prevents symlink spoofing and privilege escalation.

### 3.2 Descriptor-Anchored Traversal & Deletion
MacMaid avoids vulnerable recursive path-string operations (`rm -rf` style) that are susceptible to Time-of-Check to Time-of-Use (TOCTOU) race conditions:
1. Open parent directory with `open(..., O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW)`.
2. Inspect target using `fstatat(dir_fd, name, ..., AT_SYMLINK_NOFOLLOW)`.
3. If deleting a file: call `unlinkat(dir_fd, name, 0)`.
4. If deleting a directory: traverse children via file descriptor using `openat(dir_fd, name, O_DIRECTORY | O_NOFOLLOW)`, remove children, then remove the directory via `unlinkat(dir_fd, name, AT_REMOVEDIR)`.
5. Post-condition check: call `fstatat` again to cryptographically verify the entry was removed.

### 3.3 Atomic Non-Overwriting Trash Moves (`renameatx_np`)
Moving items to `~/.Trash` utilizes macOS-specific kernel primitives:
- Uses `renameatx_np(source_dir_fd, source_name, trash_dir_fd, dest_name, RENAME_EXCL)`.
- The `RENAME_EXCL` flag (`0x00000004`) guarantees that the destination will never overwrite an existing file.
- If a collision occurs, a deterministic timestamped unique name is generated (`name_YYYYMMDD_HHMMSS.ext`) and retried.
- Inode and device integrity is verified before and after the move `(st_dev, st_ino)` to ensure no hardlink or swap attack occurred.

---

## 4. Whitelist & Protection Configuration

### 4.1 Safe Whitelist Loading
- The whitelist is stored at `~/.config/macmaid/whitelist.conf`.
- Before reading, MacMaid verifies that neither the config file nor its parent directories are symlinks and confirms ownership by the current user UID.
- Patterns support exact directory paths, prefix globs, and tilde expansions.

### 4.2 Fail-Closed Protection Checks
- When evaluating whether a path is protected:
  ```rust
  if !config.is_protected(path).unwrap_or(true) {
      // Safe to process
  } else {
      // Skipped: protected or error evaluating protection
  }
  ```
- If an I/O error or lexical parsing failure occurs during whitelist evaluation, MacMaid fails closed and treats the path as protected.

---

## 5. Process & Permission Safety

### 5.1 Rootless Execution Invariant
MacMaid explicitly checks `getuid() == 0`. Running as `root` or under `sudo` is strictly rejected at startup:
- Protects system-level caches and root-owned application containers from accidental corruption.
- Guarantees that all user actions remain bounded by standard macOS POSIX permissions.

### 5.2 Protected Process Safeguards
The memory management service (`macmaid-core::memory`) validates PIDs before termination:
- System critical processes (`kernel_task`, `launchd`, `WindowServer`, `loginwindow`, `Finder`, `Dock`) cannot be terminated.
- Root-owned processes (UID 0) cannot be terminated.
- MacMaid's own process cannot be terminated.
- Interactive termination requires deliberate user confirmation.

---

## 6. Fault-Injection & Safety Verification Suite

The Rust safety test suite (`crates/macmaid-core/tests/safety_tests.rs`) executes automated fault-injection scenarios:

| Test Case | Scenario / Injected Fault | Expected Result | Verified |
| :--- | :--- | :--- | :--- |
| `test_hard_blocked_roots` | Injected path targets `/`, `/System`, `/Library`, `~`, `~/Desktop` | `Err(PathSafetyError::HardBlockedRoot)` | [x] Passed |
| `test_path_traversal_rejection` | Injected traversal string `~/Library/Caches/../../Desktop` | `Err(PathSafetyError::PathTraversal)` | [x] Passed |
| `test_symlink_ancestor_rejection` | Injected symlink parent directory in traversal chain | `Err(PathSafetyError::SymlinkedAncestor)` | [x] Passed |
| `test_trash_candidate_validation` | Candidate inside `~/Documents` or root `/var` | `Err(PathSafetyError::DisallowedScope)` | [x] Passed |
| `test_analyzer_candidate_validation` | Analyzed candidate outside user-permitted boundaries | Strict validation enforced | [x] Passed |
| `test_manual_cache_allowed_matrix` | Verified permitted vs non-permitted cache directories | Matrix contract satisfied | [x] Passed |
| `test_whitelist_protection` | File matching configured whitelist pattern | `is_protected() == Ok(true)` | [x] Passed |
| `test_descriptor_anchored_deletion` | Direct file and directory removal via `openat`/`unlinkat` | Target deleted; symlink escape blocked | [x] Passed |
| `test_trash_move_exclusive_no_overwrite` | `renameatx_np(RENAME_EXCL)` to existing trash filename | Collision resolved; no overwrite | [x] Passed |
| `test_protected_process_termination_refusal` | PID 1 (launchd) or root process termination attempt | `Err(ProtectedProcess)` | [x] Passed |

All 10 safety and fault-injection tests pass on Apple Silicon macOS.
