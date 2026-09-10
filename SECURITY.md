# DeepClean security model

DeepClean is destructive software. Its core invariant is that a cleanup candidate is never sufficient authorization to delete a path.

## Deletion gate

Immediately before deletion, `PathSafety`:

1. expands and standardizes the path;
2. rejects empty, relative, traversal/control-character inputs;
3. blocks broad system roots;
4. requires the path to belong to an allowlisted cleanup domain or an exact known cache pattern;
5. rejects symlinked ancestors that could redirect traversal outside the literal allowed tree;
6. checks the user whitelist again.

`removeChildren` additionally refuses a symlinked cleanup root. Installer cleanup is separately restricted to descendants of the current user's Downloads/Desktop and moves files to Trash.

## Analyze deletion gate

The interactive disk analyzer has a separate, stricter contract because it can display ordinary user files that are not cleanup candidates:

1. Analyze may *read/browse* any path the current process can read, but its `D` action never performs permanent deletion.
2. A selected item can only be moved to `~/.Trash` when it is a strict descendant of the current user's home and is owned by that user.
3. `~/Library` and everything below it are view-only from Analyze; cache cleanup there must go through the normal allowlisted cleanup engine.
4. Major top-level home anchors (`Desktop`, `Documents`, `Downloads`, `Movies`, `Music`, `Pictures`, `Public`, `Applications`) cannot themselves be moved wholesale, though ordinary items inside user-data folders may be explicitly selected.
5. `.app` bundles, Photos libraries, whitelisted paths and symlink-ancestor escapes are refused.
6. A Trash move requires an explicit reviewed UI/CLI action and is recorded in operation history.
7. macOS Trash moves use descriptor-anchored, exclusive rename semantics: no symlink traversal, overwrite, copy fallback or cross-volume fallback.

## Privilege policy

DeepClean does not run its normal cleaner through `sudo`, does not elevate application removal, and does not disable/bypass SIP or TCC. Operations that macOS denies are skipped/failed rather than retried with a broader privilege boundary. The separately reviewed Spotlight rebuild is the only fixed maintenance action that may request native macOS authorization.

## Fail-closed categories

Arbitrary Application Support, Preferences, Containers/Group Containers, credentials, browser persistent site data, user documents, backups, VM/container data and system databases are never generic deletion targets.

## Recovery / audit

- The main `scan`/`clean` flow performs the complete read-only scan and prints an exact structured plan before offering cleanup.
- Review plans include target/manager operation, action type, risk, reason, estimated size and required app closure. Scan estimates are explicitly not promised reclaimed disk space.
- The TUI uses a dedicated review screen with a terminal-style `[y/N]` prompt. Only `y` authorizes; Enter, `n`, Esc, cancel and navigation never execute the callback. Changed selections or scan state invalidate the visible review. USER DATA and MANUAL plans require a second explicit `y` confirmation.
- Interactive terminals require an explicit `y`/`yes` answer to the reviewed-action prompt; Enter and every other answer cancel cleanup.
- `--no-prompt`/`--scan-only` guarantees read-only behavior. `--yes` is the explicit prompt bypass.
- `--apply` remains accepted for backwards-compatible non-interactive automation; it does not bypass the y/N prompt in an interactive terminal.
- Installer cleanup moves files to Trash.
- Time Machine thinning is a separate command with a separate `THIN SNAPSHOTS` confirmation.
- Operations are logged as JSONL in `~/Library/Logs/deepclean/operations.jsonl`; `deepclean history` presents the same records as a readable timeline.
- Backward-compatible item records distinguish scanned estimate, successfully processed estimate, conservative estimated reclaim and reclaim status. Aggregate `operation_summary` records also contain Trash-moved estimates, unknown manager effects and observed free-space deltas. Failed and skipped targets never contribute to processed/reclaim totals.
- The compatibility `freed` field is an estimate, not guaranteed physical-disk reclamation. It excludes Trash moves and unknown manager-command effects. Filesystem-wide before/after observations are labeled separately and are not attributed solely to DeepClean because APFS clones, snapshots, sparse files and concurrent disk activity can affect them.
- Scan/search/analyze work emits live activity/current-path feedback so long-running filesystem reads do not look frozen.
- Read-only scans support cooperative cancellation. Filesystem loops stop at checkpoints, size measurement uses a bounded scheduler, and cancellation of a waiting subprocess terminates its owned process group.
- Completed, partial, cancelled and failed states remain distinct. Permission/TCC limitations are surfaced with affected locations; incomplete bulk-scan results are not cleanup-authorized.
- Scan cancellation never interrupts a cleanup mutation already in progress. Destructive operations continue through post-condition verification and audit.
- `~/.config/deepclean/whitelist` can protect custom paths/globs. Missing, unreadable, malformed, non-UTF-8 or symlinked whitelist state blocks mutation rather than being treated as empty.
- Audit and configuration state directories/files must be user-owned regular paths without symlink redirection before destructive execution starts.

## Local Web mutation boundary

Web mutations require an exact localhost Host and Origin, JSON content type, an HttpOnly SameSite session token, and POST. Mutation requests are serialized; a second request receives a conflict response while one is active. Destructive GET routes do not exist. Every destructive request first obtains a server-generated review plan and a signed, short-lived, single-use token bound to the exact plan and scan generation. Changed scans/selections, expired/replayed tokens and missing user-data opt-in fail closed. Execution-time core validation remains authoritative after review.

## Known limitation

No third-party cleaner can prove the semantics of every app's private cache. A buggy application may store important data in a directory it calls a cache. Use `scan` first, maintain backups, and whitelist anything you know is expensive or important to regenerate.


## Interactive analyzer cache

Analyze keeps size results only in process memory. Navigation cache entries never broaden deletion permissions. After an Analyze Trash operation, the exact removed row is deleted from cache and only ancestor branches containing that change are marked dirty. Returning to an unaffected parent therefore reuses trusted read-only measurements instead of repeating a full subtree scan. `R` explicitly refreshes the current directory.

A cached size is display metadata only: `Cleaner.move_analyzer_item_to_trash` revalidates the selected path, ownership, protected roots, whitelists and symlink ancestors immediately before every Trash move.

## Developer runtime removal

Developer Tools never treats an executable or large directory merely found on disk as safe to delete. A developer item is removable only when DeepClean can associate it with a supported owning manager, prove active/base/dependency protection state, and invoke that manager without arbitrary shell text. Supported direct manager removals include mise, asdf, pyenv, rbenv/ruby-build, rustup, fnm, nodenv/node-build and selected Homebrew resources. NVM, SDKMAN!, uv-managed CPython and Volta images are currently inventory-only where dependency safety or shell-independent removal cannot be proven. Failed manager safety queries fail closed.

The same ownership rule applies beyond runtimes. Conda/Micromamba non-base environments use their environment-removal commands only after manager-reported base/active identity is known; base and active environments are protected. Homebrew formulae with dependents or active executables remain protected. Poetry environments, Android Virtual Devices/system images and Xcode DeviceSupport are inventory-only because they may contain user data or their usage cannot be proven. Available/booted Xcode Simulator items stay protected; only unavailable, shutdown simulator items with supported identifiers are offered through `simctl`.

Developer discovery and disk sizing follow the same no-silent-work invariant as cleanup scans: long manager commands and `du` measurements keep live activity visible.

## Optimize safety boundary

Optimize is intentionally bounded maintenance, not a license to reset arbitrary macOS state. The recommended set may refresh DNS/Quick Look/Finder/Dock/LaunchServices and inspect Spotlight health. Full Spotlight reindex is separate and advanced. DeepClean does not delete Dock databases, purge memory, remove swap, reset Wi-Fi/Bluetooth preferences, or rebuild font caches as general-purpose optimizations.


## App uninstall boundary (v0.9.0)

App uninstall is evidence-based. The application bundle path comes from an enumerated `.app`; remnants are derived from the exact `CFBundleIdentifier`, not broad substring recursion. Caches/logs/saved state and exact user LaunchAgents are safe defaults. HTTP storage, Preferences, `Application Support`, Containers and WebKit are visible but opt-in because they may hold user/session state. Homebrew Casks are routed through Homebrew only while exact ownership remains proven; command failure never falls back to raw deletion. Non-cask bundles and selected remnants move to Trash after identity, ownership, parent-root, whitelist, symlink and running-process revalidation. DeepClean does not elevate application removal.

## Project Purge boundary (v0.9.0)

Project Purge never treats a directory name alone as proof that deletion is safe. A candidate must have a known artifact basename, be owned by the current user, live under the home directory, and have a project marker in its bounded ancestry. The same conditions are checked again immediately before deletion. Local build artifacts and network-restored dependency directories are separate risk classes; recent/dependency artifacts are conservative by default.

## Status / completion boundary (v0.9.0)

The live status dashboard is read-only. It uses public/kernel/userland metrics available without installing a privileged helper; when a true temperature/GPU metric cannot be obtained safely, DeepClean does not fabricate one. Shell completion installation only writes DeepClean-owned completion files plus a clearly marked rc-file block that can be removed during `--purge-data` uninstall.

## Destructive safety hardening (v0.9.2)

A red-team pass added additional fail-closed boundaries: application bundle identifiers must match a strict reverse-DNS-safe grammar before they can generate leftover paths; app-uninstall components are re-derived and revalidated immediately before every Trash move; active developer runtimes/environments are not removable; HTTP storage is treated as opt-in user data; and Project Purge rejects symlinked targets/ancestors and moves artifacts to Trash instead of permanently deleting them. Homebrew cask ownership requires declared cask app-artifact evidence rather than fuzzy name matching.

## Fallback hierarchy

DeepClean does not treat a failed native command as permission to delete more broadly. The project-wide order is: owning manager/macOS API first; a narrower, explicitly proven fallback only where recoverability and scope are clear; otherwise skip/fail closed. Cache fallbacks are manager-specific and interactive. Manager-owned runtime/environment/SDK state never falls back to raw recursive directory deletion. See `FALLBACK_POLICY.md` for the current matrix.


## Destructive post-condition verification (v0.9.7)

Cleanup success is no longer inferred only from a zero exit status. File deletions use descriptor-anchored, no-follow traversal and verify disappearance; remove-children actions block the entire target if any descendant may be whitelisted; Trash operations verify source disappearance, destination identity and exclusive naming; app uninstall verifies the `.app` path is absent and reports duplicate same-bundle-ID copies; developer manager removals rescan inventory before claiming removal. Whitelist state is reloaded immediately before destructive actions. Missing, unreadable, malformed or non-UTF-8 whitelist state blocks mutation.
