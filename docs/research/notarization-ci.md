# Research: Integrating Developer ID signing + notarization into `macos-dmg.yml`

Tracking issue: DevOpen-io/MacMaid#27

## Question

> What does integrating Apple Developer ID signing + notarization into the existing
> GitHub Actions DMG pipeline (`macos-dmg.yml`) actually require? Cover: Apple
> Developer Program prerequisites and certificate types, the `notarytool` workflow
> for the DMG and the standalone CLI binary, how signing credentials get stored and
> used in GitHub Actions (API key vs Apple ID app-password vs certificate import),
> whether stapling applies, what changes for the Homebrew cask/formula (sha256
> stability, Gatekeeper behavior signed vs unsigned), failure modes, and a rough
> effort estimate. Cite first-party sources (Apple docs). Context: the maintainer
> is willing to pay for the Developer Program; the question is mechanics and
> whether the trade-off is worth it before 1.0.

## TL;DR

The work is mechanical, not architectural: replace the ad-hoc `codesign --sign -`
in `scripts/build-macos-app.sh` with a real **Developer ID Application**
signature (hardened runtime + secure timestamp), import a base64 `.p12` into a
throwaway keychain on the `macos-14` runner, submit the finished DMG plus a `zip`
of the CLI package to the notary service with `xcrun notarytool submit --wait`,
`xcrun stapler staple` the DMG, and compute the sha256s **after** stapling (the
staple rewrites the file). Cost is $99/yr for the Apple Developer Program plus
roughly one to two days of implementation and debugging; the recurring
operational burden is secret rotation and the occasional notarization rejection
that must be diagnosed from the JSON log. Given the maintainer is already willing
to pay, the only real trade-off is pipeline complexity — and it buys the removal
of Gatekeeper's "developer cannot be verified / cannot check for malicious
software" blocking dialogs for every install path.

## Current pipeline (what this changes)

Grounded in this repo, not a hypothetical:

- `.github/workflows/macos-dmg.yml` runs `test` on `macos-latest`, then
  `build-dmg` on `macos-14` (Apple Silicon/arm64), then `release` and
  `update-homebrew-tap` on `ubuntu-latest`.
- `scripts/build-macos-app.sh` freezes the app with PyInstaller `--onedir`,
  assembles `MacMaid.app` by hand (`Contents/MacOS/macmaid-bin`,
  `Contents/Resources/runtime` = PyInstaller `_internal`, a `Contents/Frameworks`
  symlink, a `swiftc`-compiled Cocoa/WebKit launcher when available), writes
  `Info.plist` with `CFBundleIdentifier io.devopen.macmaid`, and finishes with
  `codesign --force --deep --sign - "$APP_ROOT"` — an **ad-hoc** signature
  (line 128-130).
- `scripts/create-dmg.sh` wraps the `.app` in a UDZO disk image via `hdiutil`
  and immediately writes `$DMG.sha256` (line 23-24).
- The workflow separately packages `cli/macmaid` + `_internal` into a
  `MacMaid-*-arm64-cli.tar.gz` and hashes it (workflow lines 68-80).
- The `update-homebrew-tap` job downloads both published artifacts, recomputes
  their sha256s, and renders `Casks/macmaid.rb` + `Formula/macmaid.rb` in
  `DevOpen-io/homebrew-tap` (workflow lines 190-224).

## Prerequisites: Apple Developer Program and certificates

1. **Apple Developer Program membership** — $99 USD per membership year. An
   individual needs an Apple Account with two-factor authentication and a legal
   name; an organization additionally needs legal-entity status, a D-U-N-S
   number, an org-domain email, and a public website.
   Source: <https://developer.apple.com/programs/enroll/>

2. **A "Developer ID Application" certificate**, created in Xcode or in the
   *Certificates, Identifiers & Profiles* section of the developer account. Only
   the team's **Account Holder** can generate it.
   Source: <https://developer.apple.com/developer-id/>

3. **Certificate type matters.** Apple is explicit that notarization only
   accepts software signed with a Developer ID certificate — not "Mac
   Distribution", not ad-hoc (`--sign -`, which is what the build script does
   today), not "Apple Development". Mach-O binaries, bundles, apps, command-line
   tools, and disk images are all signed with a **Developer ID Application**
   certificate; a separate "Developer ID Installer" certificate only exists for
   `.pkg` installers (MacMaid ships a DMG + tarball, so it isn't needed).
   Source: <https://developer.apple.com/documentation/security/resolving-common-notarization-issues#Use-a-valid-Developer-ID-certificate>

4. **Per-binary signing requirements.** Every executable in the submission must
   have: a valid Developer ID signature, the **hardened runtime** flag
   (`codesign --options runtime`), a **secure timestamp** (`codesign
   --timestamp`, which contacts `timestamp.apple.com`), no
   `com.apple.security.get-task-allow` entitlement, and linkage against the
   macOS 10.9+ SDK.
   Sources:
   <https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution#Prepare-your-software-for-notarization>,
   <https://developer.apple.com/documentation/security/resolving-common-notarization-issues>

   For this repo that means the Swift launcher, `macmaid-bin`, **and every
   Mach-O inside `Contents/Resources/runtime`/PyInstaller `_internal`** (the
   Python dylibs and `.so` files) must be signed — and the same signed files are
   what get copied into `cli-package/`, so the CLI tarball inherits signed
   binaries for free *if* signing happens before packaging (workflow lines 68-79
   currently copy `cli/` or `dist/` output; ordering must be: sign bundle →
   copy into cli-package → tar). `codesign --deep` can sign nested code
   recursively, but Apple's recommended approach is signing inside-out; either
   way, verify with `codesign -vvv --deep --strict` and `spctl -vvv --assess
   --type exec`.
   Source: <https://developer.apple.com/documentation/security/resolving-common-notarization-issues#Ensure-a-valid-code-signature>

## Credentials in GitHub Actions

Three independent credentials are involved; all belong in repository secrets
(<https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions>):

### 1. The signing certificate (`.p12` import into a runner keychain)

GitHub's own documentation for exactly this scenario: export the Developer ID
certificate + private key as a `.p12`, store it base64-encoded as a secret
(e.g. `BUILD_CERTIFICATE_BASE64`) plus `P12_PASSWORD` and a throwaway
`KEYCHAIN_PASSWORD`, then in the workflow create and unlock a temporary
keychain, `security import` the `.p12`, and `security
set-key-partition-list` so `codesign` doesn't prompt. GitHub-hosted runners are
ephemeral VMs, so the imported key material is destroyed with the runner — the
cleanup step is only needed for self-hosted runners.
Source: <https://docs.github.com/en/actions/deployment/deploying-xcode-applications/installing-an-apple-certificate-on-macos-runners-for-xcode-development>

### 2. Notary service authentication — pick one of two

`notarytool` supports exactly two credential types
(<https://developer.apple.com/documentation/technotes/tn3147-migrating-to-the-latest-notarization-tool#Migrate-your-credentials>):

- **App Store Connect API key (recommended for CI).** Generate a *Team* key in
  App Store Connect → Users and Access → Integrations → App Store Connect API;
  download the `.p8` private key (downloadable **once**, Apple keeps no copy).
  Pass `--key <path-to-.p8> --key-id <10-char key id> --issuer <issuer UUID>`
  to `notarytool`. Important constraints: individual keys cannot use the
  `notaryTool` endpoint (team keys are required on the documented path), the
  issuer ID is required for team keys, and a Developer-role key is sufficient —
  the key does not need Admin. Store the `.p8` as a base64 secret, the key ID
  and issuer as plain secrets/vars.
  Sources:
  <https://developer.apple.com/documentation/appstoreconnectapi/creating-api-keys-for-app-store-connect-api>,
  <https://developer.apple.com/documentation/technotes/tn3147-migrating-to-the-latest-notarization-tool#App-Store-Connect-API-key>

- **Apple ID + app-specific password.** `--apple-id <id> --team-id <TEAMID>
  --password <app-specific-password>`. Requires 2FA on the account (mandatory
  anyway); generated at account.apple.com → Sign-In and Security → App-Specific
  Passwords; max 25 active; **all are revoked automatically whenever the primary
  Apple Account password changes** — a recurring CI-breakage vector the API key
  avoids.
  Sources: <https://support.apple.com/en-us/102654>,
  <https://developer.apple.com/documentation/technotes/tn3147-migrating-to-the-latest-notarization-tool#App-specific-password>

  On CI there is no persistent keychain worth using, so the
  `notarytool store-credentials` / `--keychain-profile` convenience flow is a
  local-development nicety, not a CI mechanism — pass the flags directly from
  secrets.
  Source: <https://developer.apple.com/documentation/security/customizing-the-notarization-workflow#Upload-your-app-to-the-notarization-service>

### 3. The existing `HOMEBREW_TAP_TOKEN` — unchanged.

## The `notarytool` workflow for this repo's two artifacts

The notary service accepts **UDIF disk images, ZIP archives, and signed flat
installer packages** — and generates tickets for nested contents too (a DMG
containing the `.app` yields tickets for both).
Source: <https://developer.apple.com/documentation/security/customizing-the-notarization-workflow#Upload-your-app-to-the-notarization-service>

- **The DMG** (`MacMaid-*-arm64.dmg`): after `create-dmg.sh`, run
  `xcrun notarytool submit "$DMG" --key AuthKey.p8 --key-id … --issuer …
  --wait`. `--wait` blocks until the service returns `Accepted` or `Invalid`
  (no polling needed; typical turnaround is under 5 minutes, 98% within 15).
  Then `xcrun stapler staple "$DMG"` and only then compute the sha256.
- **The CLI tarball**: a `.tar.gz` is **not** a submittable container. The
  correct move is to submit a ZIP of the same signed `cli-package/` directory
  (built with `ditto -c -k --keepParent`, per Apple's ZIP example) purely as a
  notarization vehicle — the ZIP itself is discarded, and the identical signed
  bytes inside the `tar.gz` are covered by the ticket because tickets are keyed
  by code signature/CD hash, not by container.
  Source: <https://developer.apple.com/documentation/security/customizing-the-notarization-workflow>

## Stapling: where it applies and where it can't

- `xcrun stapler staple` works on apps, bundles, **disk images**, and flat
  installer packages — so staple the DMG (and optionally the `.app` inside it
  before DMG creation).
- **Zips can't be stapled**, and **standalone binaries can't be stapled at
  all**: "Although tickets are created for standalone binaries, it's not
  currently possible to staple tickets to them." That's fine — the notary
  service also publishes the ticket online, and Gatekeeper looks it up over the
  network at first launch, so the stapled DMG is an offline-lookup optimization
  rather than a correctness requirement.
  Source: <https://developer.apple.com/documentation/security/customizing-the-notarization-workflow#Staple-the-ticket-to-your-distribution>

**Consequence for sha256 stability:** `stapler` rewrites the DMG in place. The
`$DMG.sha256` file and the Homebrew cask `sha256` stanza must be computed from
the **post-staple** bytes; likewise the tarball must be created from the
post-signing (but un-stapled) bytes. The pipeline already hashes at the right
layer — the reordering is just: build → sign → DMG/zip → notarize → staple →
hash → upload → tap update. The existing `update-homebrew-tap` job needs *no*
template changes: it re-hashes whatever it downloads, so it automatically picks
up the stapled hashes.

## Gatekeeper: signed + notarized vs today's unsigned artifacts

Apple's own user-facing doc states that macOS Catalina and later "requires
software to be notarized", that unsigned/unverifiable apps trigger "Apple cannot
check … for malicious software" and "the developer cannot be verified" alerts
("Move to Trash"/"Done" — no direct Open button), and that the only path past
them is System Settings → Privacy & Security → **Open Anyway**.
Source: <https://support.apple.com/en-us/102445>

With Developer ID + notarization, first launch becomes a single "downloaded
from the internet, Apple checked it" confirmation — for the DMG-installed app
and for the CLI binary alike (the online ticket covers the tarball's `macmaid`
even though nothing can be stapled to it). On the Homebrew side, Homebrew's own
security doc notes that a cask's `sha256` "proves that the downloaded bytes
match the package metadata, but it does not prove who produced those bytes",
and that code signing, notarization and Gatekeeper are the compensating checks
for cask-installed vendor binaries; the cask-specific policy also requires that
artifacts "must pass Homebrew's Gatekeeper checks and must not require …
Gatekeeper to be disabled or bypassed" — i.e. unsigned builds are a barrier to
ever moving from the third-party tap to `homebrew/cask`.
Sources: <https://docs.brew.sh/Homebrew-Security-and-Supply-Chain#casks-have-a-different-trust-model>,
<https://docs.brew.sh/Acceptable-Casks#platform-compatibility-and-macos-security-protections>

## Concrete changes required (checklist)

1. Enroll in the Developer Program; create a Developer ID Application
   certificate; export `.p12`; create an App Store Connect **Team** API key
   (Developer role suffices) and download the `.p8`.
2. Add secrets: `MACOS_CERTIFICATE` (b64 `.p12`), `MACOS_CERTIFICATE_PWD`,
   `MACOS_KEYCHAIN_PWD`, `APPSTORE_KEY` (b64 `.p8`), `APPSTORE_KEY_ID`,
   `APPSTORE_ISSUER`.
3. Workflow: add a keychain-import step (GitHub's documented recipe) before
   `build-macos-app.sh`.
4. `build-macos-app.sh`: replace `codesign --force --deep --sign -` with
   Developer ID signing — sign every Mach-O inside `runtime/`/`_internal`
   (inside-out), the Swift launcher, `macmaid-bin`, then the `.app` itself, all
   with `--options runtime --timestamp`; keep the ad-hoc fallback for local
   unsigned builds so contributor builds don't break.
5. Workflow: after `create-dmg.sh`, `notarytool submit "$DMG" --wait`; on
   `Accepted`, `stapler staple "$DMG"`; move the DMG sha256 computation after
   the staple; build the CLI zip from `cli-package/`, notarize it, then create
   the `.tar.gz` + `.sha256` (tarball order unchanged — sign before packaging).
6. Optionally gate the whole thing on `secrets.* != ''` so forks and PR builds
   keep working unsigned.

## Failure modes to expect

- **`status: Invalid` submissions.** The `notarytool log <submission-id>` JSON
  names the offending file; classic causes for a PyInstaller tree are an
  unsigned nested `.dylib`/`.so` in `_internal`, a missing hardened-runtime
  flag, or a missing secure timestamp ("The binary is not signed with a valid
  Developer ID certificate", "The signature does not include a secure
  timestamp", "The executable does not have the hardened runtime enabled").
  Sources: <https://developer.apple.com/documentation/security/customizing-the-notarization-workflow#Check-the-status-of-your-request>,
  <https://developer.apple.com/documentation/security/resolving-common-notarization-issues>
- **Post-sign mutation.** Anything that modifies the bundle after signing
  (e.g. the `touch "$APP_ROOT"` in `build-macos-app.sh` line 132 touches only
  the directory timestamp and is safe, but any file edit is not) invalidates
  the signature → "The signature of the binary is invalid."
- **Credential breakage.** App-specific passwords silently die when the Apple
  Account password is reset; `.p8` keys must be re-issued if revoked/lost
  (single download); the `.p12` password or an expired certificate (Developer
  ID certs are long-lived but do expire) fails at `security import`/`codesign`.
  Source: <https://support.apple.com/en-us/102654>
- **Timestamp server / notary service reachability.** `codesign --timestamp`
  needs `timestamp.apple.com`; `notarytool` uploads via S3 Transfer
  Acceleration; `stapler` needs CloudKit ranges — all fine on GitHub-hosted
  runners, but transient Apple outages will turn `submit --wait` into a retry
  or a blocked release.
  Sources: <https://developer.apple.com/documentation/security/resolving-common-notarization-issues#Include-a-secure-timestamp>,
  <https://developer.apple.com/documentation/security/customizing-the-notarization-workflow#Ensure-your-build-server-has-network-access>
- **Checksum ordering.** Hashing the DMG before stapling (or hashing the
  tarball before signing) produces cask/formula `sha256` mismatches at install
  time — Homebrew refuses installs whose bytes don't match the pinned checksum.
  Source: <https://docs.brew.sh/Homebrew-Security-and-Supply-Chain#checksummed-downloads-pinned-in-reviewed-metadata>
- **Interaction with the immutable-tag gate.** The release job already refuses
  to re-tag a moved `v<version>`; a mid-pipeline notarization failure after the
  tag exists means the fix lands on a new commit and needs a version bump per
  repo policy — same blast radius as today's build failures.
- **Hardened-runtime entitlement surprises.** PyInstaller-frozen Python
  normally works with the runtime enabled (all bundled libraries are signed by
  the same identity, so library validation passes), but if runtime loads
  unsigned third-party code at any point it may need
  `com.apple.security.cs.disable-library-validation` — the notary log and a
  launch test on a clean machine are the arbiter.
  Source: <https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution>

## Effort estimate

- One-time account/certificate work: ~1–2 hours (enrollment approval can add a
  human wait).
- Pipeline changes (keychain import step, signing refactor, two `notarytool`
  submissions, staple, hash reorder): ~1 day of edits plus CI iteration.
- Debugging PyInstaller nested-binary signing and any hardened-runtime
  entitlement issue: up to ~0.5–1 day contingency.
- **Total: roughly 1–2 days to first green notarized release**, then ~$99/yr and
  occasional secret rotation (cert renewal on expiry, `.p8` revocation hygiene).
  Every release thereafter adds ~5–15 minutes of Apple-side latency to the
  `build-dmg` job.

## Verdict

Worth doing before 1.0: the cost is a bounded two-day change plus $99/yr, and
the payoff is the difference between "click Open" and a two-step Settings
workaround for every new user — plus it unblocks future promotion of the tap to
`homebrew/cask`, whose policy requires Gatekeeper-clean artifacts.
