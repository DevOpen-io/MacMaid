# MacMaid Agent Rules

All contributors — human or agent — must follow the engineering standard in
[`CONTRIBUTING.md`](CONTRIBUTING.md) at the repository root. It defines the
safety contract, refactoring rules, testing standard (including the
mutation/fault-injection requirement), and the required verification suite.
Read it before making changes.

## Mandatory Quality Gate

No change is considered ready to merge if Ruff or mypy reports even a single error.

Required checks:

```bash
uv run ruff check src/macmaid tests_py
uv run mypy
```

Rules:

- Ruff result: **0 errors**
- mypy result: **0 errors**
- "It was already in the baseline" is not an acceptable excuse.
- New `# type: ignore`, `noqa`, broad `Any`, `cast()`, or config exclusions must not be used to hide errors.
- If an exception is genuinely required, it must be documented with an explicit technical reason, the narrowest possible scope, and a test.
- Ruff/mypy scope must not be narrowed.
- `src/macmaid` and `tests_py` must not be removed from Ruff scope.
- mypy must continue to check the entire `src/macmaid` package.
- If either check fails after a refactor or feature, the work is not complete.

In short:

**Ruff != 0 or mypy != 0 → no merge.**

## Shared Core Services

CLI, TUI, and Web/Application UI must all use the same feature and core implementations (`scanner.py`, `cleaner.py`, `analyzer.py`, `features.py`, `developer.py`, `safety.py`, `system.py`). UI layers must not contain their own business logic, filesystem traversal, disk measurement, or safety checks; they serve only as adapters/presentation over the shared core services.

- Never duplicate scanning, deletion, uninstall, purge, or analysis logic inside `cli.py`, `tui.py`, `web.py`, or `WebUI/`.
- When a surface needs behavior the core lacks, extend the core module first, then call it from the UI layer.
- A safety fix or feature change must land in the shared core so every surface inherits it; never fix a shared operation in only one interface.
- Dependency direction is one-way: UI layers may import core modules, but core modules must never import `cli.py`, `tui.py`, `web.py`, or `WebUI/` code.

## Versioning

After every user-visible code change, update the release version before completing the task. MacMaid uses Semantic Versioning (`MAJOR.MINOR.PATCH`):

- **MAJOR**: incompatible public API/CLI/Web API changes, removed supported behavior, or a release requiring explicit migration.
- **MINOR**: backwards-compatible user-visible features or substantial new capabilities.
- **PATCH**: backwards-compatible bug fixes, safety fixes, UI fixes, internal improvements, and dependency-only maintenance.

For `0.x` releases, retain this policy: use `0.(MINOR + 1).0` for incompatible changes and `0.MINOR.(PATCH + 1)` for compatible fixes.

Keep every version surface synchronized:

- `pyproject.toml`
- `src/macmaid/__init__.py`
- `uv.lock`
- `src/macmaid/WebUI/index.html`

Do not hardcode the version in packaging scripts. `scripts/prod-install.sh` must read `macmaid.__version__` when writing the app bundle metadata.

The project version remains the sole versioning source. Agents must never create, amend, force-update, or push local Git tags. The release CI job alone creates one immutable `v<project-version>` tag for GitHub Release asset URLs and Homebrew-tap downloads. If that tag already points to another commit, bump the project version; never move the tag.

Add or update release-facing tests when version surfaces change, and verify the relevant test suite before reporting completion.

## UI Localization

Every user-visible string added or changed in the TUI or Web UI must have Turkish and English translations. Add both entries to the shared localization catalog and render the string through the existing localization helper; do not introduce untranslated UI copy, including empty states, hints, confirmations, errors, progress, and history text.

## Web UI Icons

All user-interface icons come from the shared `SF_SYMBOLS` catalog in `src/macmaid/WebUI/app.js`, named after the Apple SF Symbols they approximate (`gearshape`, `trash`, `memorychip`, `magnifyingglass`, …). SF Symbols itself cannot be embedded in a web surface, so each entry is a hand-drawn monochrome SVG approximation rendered through the shared `sfSymbol()` helper and hydrated from `data-icon` attributes.

- Do not mix emoji, Unicode glyphs, or unrelated icon packs for UI actions/navigation/status indicators.
- When a new icon is needed, add it once to `SF_SYMBOLS` and reference it by name — never hardcode per-surface icon choices.
- Keep names aligned with real SF Symbol semantics so the same action maps to the same symbol everywhere (sidebar, cards, buttons, modals, Memory UI).
- Terminal surfaces (CLI/TUI) use plain text and ASCII status markers (`+`, `x`, `!`, `~`, `.`, `*`); do not add Unicode icon glyphs there.
