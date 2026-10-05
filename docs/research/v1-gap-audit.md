# MacMaid 0.15.26 — public-1.0 gap audit

Research output for DevOpen-io/MacMaid#31. Findings only; no priority or verdict
is assigned beyond the requested `candidate-in-scope-for-1.0` / `post-1.0`
marking, which flags whether an item is the kind of thing a public-1.0 bar
would plausibly cover, not whether the maintainer should do it.

## Question

> Where does MacMaid 0.15.26 fall short of a credible public-1.0 macOS cleanup
> tool? Survey the landscape a public user compares against (Pearcleaner,
> AppCleaner, CleanMyMac, OnyX): first-run experience, permission guidance
> (Full Disk Access / TCC), update delivery for non-Homebrew installs,
> support/issue surfaces (issue templates, docs), and macOS version support
> policy. Then audit this repo against that bar and produce a gap list, each
> item marked candidate-in-scope-for-1.0 vs post-1.0. Report findings, not
> verdicts.

## Landscape survey

### Pearcleaner (alienator88/Pearcleaner)

- **First-run experience:** Native SwiftUI app. Permission requirements are
  stated up front in the README ("Full Disk permission to search for files;
  Privileged Helper to perform actions on system folders") and the docs site
  explains the FDA grant. Users can pick which page the app opens on at
  launch.
- **Update delivery (non-Homebrew):** GitHub Releases zips (separate
  Apple Silicon and Intel builds) plus Homebrew cask plus source build.
  Pearcleaner checks for updates to itself and to other installed apps at
  launch (opt-out in Settings → General), with a dedicated Updater view;
  Homebrew/Sparkle deduplication avoids double-updating the same app. A
  `pear://checkUpdates` deep link exists.
- **Support/issue surfaces:** Active GitHub issue tracker with numbered
  issues referenced per release line; documentation site (pearcleaner.com)
  covering install paths, permissions, Homebrew, source builds; GitHub wiki
  (deep-link guide).
- **macOS support policy:** Explicit published matrix — macOS 13 Ventura
  through 26 Tahoe supported, betas explicitly unsupported, pre-13 dropped
  "due to missing Swift/SwiftUI APIs required by the app."
- **License/distribution:** Apache 2.0 with Commons Clause ("fair-code");
  ~12K stars.

Sources:
- https://github.com/alienator88/Pearcleaner
- https://pearcleaner.com/
- https://github.com/alienator88/Pearcleaner/releases/tag/5.4.2
- https://github.com/alienator88/Pearcleaner/wiki/Deep-Link-Guide

### AppCleaner (FreeMacSoft)

- **First-run experience:** Drag-an-app-onto-window GUI, minimal. Recent
  release notes state "AppCleaner now prompts for Full Disk Access. Without
  it, some files may fail to be removed" — i.e., a launch-time FDA prompt
  rather than a settings screen users must discover.
- **Update delivery (non-Homebrew):** Direct download from freemacsoft.net
  with built-in auto-update (the Homebrew cask is flagged `auto-updates`,
  i.e. Sparkle-style self-update independent of Homebrew).
- **Support/issue surfaces:** Vendor site with per-OS download table and
  release notes; closed-source freeware, no public issue tracker.
- **macOS support policy:** Ships separate builds per OS range: 3.7 for
  macOS 15+, 3.6.8 for macOS 10.14–15.6, 3.6 for 10.13, 3.4 for 10.10–10.12,
  2.3 for 10.6–10.9. Users must pick the matching build; third-party docs
  warn that the wrong build can misbehave.

Sources:
- https://freemacsoft.net/appcleaner/
- https://freemacsoft.net/appcleaner/releasenotes.html
- https://formulae.brew.sh/cask/appcleaner

### CleanMyMac (MacPaw)

- **First-run experience:** Guided commercial product. An in-app "Assistant"
  surfaces an "Allow Full Disk Access" recommendation with a direct path to
  System Settings → Privacy & Security → Full Disk Access, backed by
  step-by-step knowledge-base articles per macOS generation (Ventura+ vs
  Big Sur/Monterey instructions differ).
- **Update delivery (non-Homebrew):** Direct download with built-in updater,
  Mac App Store build, and Setapp distribution — every channel self-updates.
- **Support/issue surfaces:** Full knowledge base (permissions, OS support,
  FAQs per product version), in-app support, vendor support portal.
- **macOS support policy:** Published supported-OS list — macOS 11 Big Sur
  through the current release; Catalina 10.15 and earlier explicitly not
  supported. Legacy product line (CleanMyMac 3) documented separately with
  its own OS range.

Sources:
- https://macpaw.com/support/cleanmymac/knowledgebase/operating-systems
- https://macpaw.com/support/cleanmymac/knowledgebase/full-disk-access
- https://apps.apple.com/us/app/cleanmymac/id1339170533?mt=12
- https://macpaw.com/support/cleanmymac-x/knowledgebase/permissions

### OnyX (Titanium Software)

- **First-run experience:** Freeware utility; on launch it verifies the
  startup disk and requires the build matching the running macOS major
  version — the version check itself is the guardrail.
- **Update delivery (non-Homebrew):** Direct download per OS version;
  Homebrew cask also exists. Old versions remain downloadable but are
  explicitly discontinued and no longer updated.
- **Support/issue surfaces:** Vendor site with release notes; email-based
  support; no public issue tracker.
- **macOS support policy:** Strictest in the comparison set — one OnyX
  version per macOS major version (4.8.5 for Sequoia 15, 4.6.2 for
  Sonoma 14, 5.x for Tahoe 26 / newer), with explicit instruction to use
  only the matching build.

Sources:
- https://titanium-software.fr/en/onyx
- https://formulae.brew.sh/cask/onyx
- https://www.titanium-software.fr/en/onyx_release.html

### What the comparison bar looks like

Across the four, a public-1.0 cleanup tool is consistently expected to have:
a first launch that is either frictionless (signed/notarized binary) or
actively guides the user past Gatekeeper; proactive FDA/TCC guidance at
first run or via an always-visible surface (not only a buried settings
card); a self-update or update-notification path for users who did not
install via Homebrew; a discoverable support surface (issue templates,
docs/FAQ, security reporting); and a written macOS version support policy
(matrix or per-OS builds).

## Repo audit — what MacMaid 0.15.26 actually does

Verified in the worktree at `research/v1-gap-audit` (base `03f46c7`):

- **Install surfaces.** Homebrew cask + formula (README.md:23-43,
  `.github/workflows/macos-dmg.yml:171-229`), DMG release asset
  (`macos-dmg.yml:39-88`), user-local `uv tool` install (`install.sh`),
  PyInstaller app bundle (`scripts/prod-install.sh`).
- **Signing/notarization.** Builds are ad-hoc codesigned only
  (`prod-install.sh:69-72`, `156-158`); the README documents a manual
  Gatekeeper bypass via "Open Anyway" or `xattr -cr` (README.md:45-59).
- **Update flow.** `macmaid_brew_update_status()` and
  `apply_macmaid_brew_update()` shell out to `brew` only
  (`src/macmaid/features.py:693-732`); a non-Homebrew install returns
  `"MacMaid is not installed by Homebrew"`. Exposed in the Web UI via
  `/api/macmaid/update/check` and `/api/macmaid/update`
  (`src/macmaid/web_mutations.py:222-230`) and the TUI "Check for Updates"
  menu entry (`src/macmaid/tui.py:60`). The CLI parser has no `update`
  subcommand (`src/macmaid/cli.py:40-79`).
- **Permission guidance.** `macos_permission_report()` probes read access
  and infers FDA plus launch context (app vs CLI)
  (`src/macmaid/system.py:100-175`). Web UI Settings has an "Access &
  Permissions" card whose Manage button opens the FDA pane via
  `x-apple.systempreferences:...Privacy_AllFiles`
  (`index.html:2008-2022`, `web_mutations.py:199-207`). `macmaid doctor`
  surfaces the same data for the CLI (`cli.py:44`, `features.py` doctor).
  There is no first-run wizard, onboarding screen, or launch-time FDA
  prompt anywhere (no matches for onboarding/welcome/first-run in `src/`).
- **Support surfaces.** `.github/` contains only `workflows/` (`ci.yml`,
  `macos-dmg.yml`) — no ISSUE_TEMPLATE, no PULL_REQUEST_TEMPLATE, no
  dependabot/SECURITY contact config. `SECURITY.md` documents the deletion
  safety model only; it contains no vulnerability-reporting policy or
  contact. Repo docs are README.md, SECURITY.md, ROADMAP.md (Turkish),
  CONTRIBUTING.md, developer.md, FALLBACK_POLICY.md,
  ARCHITECTURE_DIAGRAM.md, PYTHON_PORT_AUDIT.md — no FAQ, troubleshooting
  guide, or CHANGELOG.md. Release notes are auto-generated from commit
  subjects (`macos-dmg.yml:133-158`).
- **macOS version policy.** One line — "MacMaid targets macOS 13+"
  (README.md:260-264); `LSMinimumSystemVersion` 13.0
  (`prod-install.sh:130`); runtime gate `macos_major >= 13`
  (`features.py:747`). No statement about new major releases, betas, or how
  long older macOS versions stay supported.
- **Architecture coverage.** Packaged DMG and Homebrew artifacts are
  arm64-only (`macos-dmg.yml:43-44`, tap cask `depends_on arch: :arm64`);
  README says Intel is source/dev-install only "until Intel release builds
  are enabled again" (README.md:262). Meanwhile the Web UI About card
  advertises "Apple Silicon & Intel (Universal)" (`index.html:2049-2051`).
- **First-run.** `macmaid` drops straight into the TUI; the app bundle
  opens the Web UI. Nothing proactively requests or explains FDA; the CLI
  case is harder still because FDA must be granted to the user's terminal
  app, which the permission report distinguishes (`launchContext`,
  `system.py:168-171`) but no user-facing doc explains.
- **Localization.** EN/TR only, per AGENTS.md; AppCleaner, CleanMyMac and
  OnyX all ship many more languages.
- **Feature breadth.** Compared to Pearcleaner specifically (the closest
  OSS peer): MacMaid lacks a Finder extension, drag-and-drop app
  uninstall, a "watch the Trash" sentinel, a Homebrew package manager UI,
  an updater for third-party apps, and a menu-bar component — all of which
  Pearcleaner ships.

## Gap list

| # | Gap vs the public-1.0 bar | Evidence | Scope marking |
|---|---------------------------|----------|---------------|
| 1 | No update path for non-Homebrew installs: DMG/app-bundle and `install.sh`/`prod-install` users get only "not installed by Homebrew"; no GitHub-Release check, no in-app notification, no self-update. Every comparator delivers updates on its direct-download channel (Pearcleaner launch check + Updater, AppCleaner auto-update, CleanMyMac built-in updater, OnyX update check). | `features.py:693-732`, `web_mutations.py:222-230`, `tui.py:60` | candidate-in-scope-for-1.0 |
| 2 | No update surface on the CLI at all — `update` exists only as TUI/Web UI screens; `macmaid update` / `macmaid update --check` do not exist. | `cli.py:40-79` | candidate-in-scope-for-1.0 |
| 3 | Unsigned/unnotarized binaries: ad-hoc `codesign -` only; first launch requires manual "Open Anyway" or `xattr -cr`. All four comparators ship Gatekeeper-clean binaries. Requires a paid Apple Developer ID, so it is a maintainer/distribution decision rather than a code change. | `prod-install.sh:69-72`, README.md:45-59 | candidate-in-scope-for-1.0 |
| 4 | No first-run/onboarding flow and no proactive FDA prompt: AppCleaner prompts at launch, CleanMyMac's Assistant recommends FDA, Pearcleaner onboards permissions; MacMaid's FDA state is only discoverable inside Settings/doctor after the user goes looking. | no onboarding code in `src/`; `index.html:2008-2022`; `system.py:100-175` | candidate-in-scope-for-1.0 |
| 5 | CLI launch-context FDA gap not explained to users: under `macmaid`, FDA must be granted to the host terminal app; the code distinguishes `launchContext: app|cli` but no README/FAQ tells a terminal user what to grant. | `system.py:168-171` | candidate-in-scope-for-1.0 |
| 6 | No written macOS version support policy beyond "13+": no support matrix, no beta stance, no statement on how new major releases are handled; comparators publish matrices (Pearcleaner), per-OS builds (OnyX, AppCleaner), or supported-OS lists (CleanMyMac). | README.md:260-264, `features.py:747`, `prod-install.sh:130` | candidate-in-scope-for-1.0 |
| 7 | Apple Silicon-only packaged builds: DMG/Homebrew arm64-only; Intel users must build from source. Pearcleaner ships both arch zips. Also the Web UI About card says "Apple Silicon & Intel (Universal)", which is inaccurate for distributed builds. | `macos-dmg.yml:40-44`, README.md:262, `index.html:2049-2051` | candidate-in-scope-for-1.0 |
| 8 | No issue/report intake structure: no ISSUE_TEMPLATE, no SUPPORT.md, no PR template; `.github/` holds only workflows. Pearcleaner runs a structured numbered-issue tracker. | `.github/` contents | candidate-in-scope-for-1.0 |
| 9 | SECURITY.md is a safety-model document with no vulnerability-reporting policy (no contact, no disclosure process). | SECURITY.md (entire file) | candidate-in-scope-for-1.0 |
| 10 | No user-facing troubleshooting/FAQ doc: Gatekeeper, `brew trust` on Homebrew 6.0+, FDA-for-Terminal and DMG-vs-source differences are scattered through README install notes; comparators ship a knowledge base or docs site. | README.md:25-59; no docs/ dir | candidate-in-scope-for-1.0 |
| 11 | No curated changelog: GitHub Release notes are auto-generated commit-subject lists; there is no CHANGELOG.md or per-release notes comparable to AppCleaner/OnyX release-notes pages. | `macos-dmg.yml:133-158` | candidate-in-scope-for-1.0 |
| 12 | No launch-time update notification in the app/Web UI: the check only runs when the user opens the updates screen (TUI auto-checks on screen entry; Web UI on button press). Pearcleaner/CleanMyMac check at launch. | `web_mutations.py:222-230`; commit `c77d227` | candidate-in-scope-for-1.0 |
| 13 | ROADMAP.md and CONTRIBUTING-adjacent docs are Turkish-only while the product is EN/TR bilingual — inconsistent public-facing language coverage for contributors. | ROADMAP.md | candidate-in-scope-for-1.0 |
| 14 | Limited localization (EN/TR) vs ~20 languages for AppCleaner, broad coverage for CleanMyMac/OnyX. | AGENTS.md i18n rule; `i18n.py` | post-1.0 |
| 15 | Missing comparator feature surfaces that are not core-cleanup: Finder extension, drag-and-drop uninstall, Trash sentinel monitor, Homebrew package management UI, third-party app updater, menu-bar app (all Pearcleaner); App Store distribution (CleanMyMac). | — | post-1.0 |
| 16 | No support-bundle / "report a problem" diagnostic export (`macmaid doctor` output is view-only; nothing packages it for attaching to an issue). | `cli.py:44`, `features.py` doctor | post-1.0 |
| 17 | No crash-reporting or feedback channel inside the app (comparators vary; MacPaw has full support infra). | — | post-1.0 |
| 18 | No Intel-native or universal packaged binary channel and no Rosetta guidance — folded out of #7 only if Intel support is deferred as a policy decision. | `macos-dmg.yml:43-44` | post-1.0 (if deferred) |
