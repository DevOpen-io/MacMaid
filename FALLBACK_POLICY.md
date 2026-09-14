# MacMaid fallback policy

Fallbacks are not a license to delete more aggressively. Every long-running/destructive subsystem follows the same order:

1. **Manager/native operation** — preferred whenever the owning tool or macOS API exposes a supported operation.
2. **Bounded MacMaid fallback** — only when MacMaid can prove the fallback target/operation is narrower than the original request and does not contain user or manager state.
3. **Skip / fail closed** — if ownership, layout, recoverability, or state consistency is uncertain.

A failed native command never turns an arbitrary path into an `rm -rf` target.

## Fallback matrix

| Area | Primary | Fallback | Decision |
|---|---|---|---|
| Homebrew app uninstall | `brew uninstall --cask` | None | **Fail closed**. Command/ownership failure never becomes raw bundle deletion. Non-cask user-owned bundles and reviewed remnants use Trash. |
| App leftovers | Exact bundle-ID-derived components | None beyond Trash move | Exact paths only; no fuzzy recursive search fallback. |
| Package caches: Homebrew downloads | `brew cleanup` | Verified `~/Library/Caches/Homebrew` contents | **Second-confirmation** if native cleanup fails. This fallback only clears downloads/cache; it does not emulate old-version cleanup. |
| Package caches: pnpm | `pnpm store prune` | Verified standard pnpm store | **Second-confirmation**. Store contents can be fetched again; custom stores are not recursively removed. |
| Package caches: Go build cache | `go clean -cache -testcache` | Standard macOS/Linux Go build-cache root only | **Second-confirmation**. A custom `GOCACHE` path is not trusted for raw recursive cleanup. |
| Package caches: Bun | `bun pm cache rm` | Verified Bun install cache | **Second-confirmation**. |
| Package caches: pip | `pip cache purge` | Standard pip cache roots | **Second-confirmation**. |
| Package caches: Yarn Classic | `yarn cache clean` | Standard Yarn Classic cache roots | **Second-confirmation**. Yarn 2+ is not mapped to the Classic fallback. |
| Package caches: Composer | `composer clear-cache` | Standard Composer cache roots | **Second-confirmation**. Custom cache locations do not receive raw fallback permission. |
| Package caches: npm | `npm cache clean --force` | Standard `~/.npm` cache root | **Second-confirmation**, aggressive profile only. |
| Package caches: pipx | `pipx cache purge` | Proven pipx run-cache roots only | **Second-confirmation**. Installed pipx apps/venvs are outside the fallback. |
| Package caches: Gradle | Gradle-managed cleanup | `~/.gradle/caches` | **Manual/default-OFF only**, only when no Gradle daemon is active. Gradle already performs its own retention cleanup. |
| Package caches: Cargo | Cargo automatic GC / normal Cargo use | Registry archive and git dependency cache leaves only | **Manual/default-OFF only**. Installed Cargo binaries are excluded. |
| Package caches: Maven | Maven/local-repository APIs | None | **No raw fallback**. The local repository mixes downloaded cache with locally built/installed artifacts. |
| Package caches: Dart/Flutter | `dart pub cache clean` | None | **No raw fallback**. `PUB_CACHE` also participates in globally activated tool state/binaries on legacy pub workflows. |
| Package caches: uv | `uv cache prune/clean` | None | **No raw fallback**. Direct cache mutation is intentionally avoided. |
| Package caches: Conda/Micromamba | manager `clean` command | None | **No raw fallback**. Environment/package-link state must stay manager-owned. |
| Package caches: .NET/NuGet | `dotnet nuget locals ... --clear` | None | **No raw fallback**. Global package/cache locations and layouts can vary; global packages may be needed for restores. |
| Package caches: Pixi/Rattler | `pixi clean cache` | None | **No raw fallback** until a narrower stable cache contract is proven. |
| Developer runtime removal | owning version manager | None | **No raw fallback**. Removing version directories behind managers can leave shims/manifests/toolchain metadata inconsistent. |
| Conda/Micromamba environments | owning manager | None | **No raw fallback**. Active/base environments stay protected. |
| Global developer CLI tools | owning package manager | None | **No raw fallback**. Raw file removal can leave package-manager metadata and command shims behind. |
| Android SDK/NDK/AVD | `sdkmanager` / `avdmanager` | None | **No raw fallback**. SDK package registries and AVD metadata remain manager-owned. |
| Xcode Simulator | `xcrun simctl` | None | **No raw fallback**. CoreSimulator metadata must remain consistent. |
| Project Purge | MacMaid validation | Move artifact to Trash | **Primary operation is already reversible**; no permanent-delete fallback. |
| Disk Analyzer deletion | MacMaid validation | Move selected item to Trash | **Primary operation is already reversible**; protected Library/app/photo roots stay blocked. |
| Installer cleanup | MacMaid validation | Move installer to Trash | **Primary operation is already reversible**. |
| DNS optimization | `dscacheutil -flushcache` | `killall -HUP mDNSResponder` | **Automatic bounded fallback**. No network preferences are changed. |
| Quick Look / Finder / Dock / LaunchServices | macOS command | None | **Fail closed** rather than deleting preferences/databases. |
| Spotlight | `mdutil` | None | **No database deletion fallback** and MacMaid never force-enables indexing. |
| Time Machine snapshots | `tmutil` | None | **No APFS/private filesystem fallback**. |
| MacMaid uninstall | remove fixed MacMaid-owned paths | None | Scope is already fixed and minimal. |

## Recursive fallback rules

Even an approved cache fallback must satisfy all of the following immediately before mutation:

- path is a manager-specific allowlisted cache root;
- path is under the current user's home directory;
- the target/root is not a symbolic link and no ancestor escape is present;
- readable, valid MacMaid whitelist state proves that neither the path nor any child may be protected;
- `PathSafety` accepts the exact root/child;
- when the manager has a meaningful process signature, no conflicting install/build/cleanup process is active;
- fallback is interactive and receives a separate `y/N` confirmation;
- `--yes`, CI, cron and other non-interactive execution do not enable the fallback.

MacMaid describes these operations as the risk class of `rm -rf <cache>/*` so users understand the consequence, but the implementation does not shell out to an arbitrary `rm -rf`. The Python cleaner iterates and revalidates every child before using bounded filesystem operations.
