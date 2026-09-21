# MacMaid Agent Rules

All contributors — human or agent — must follow the engineering standard in
[`CONTRIBUTING.md`](CONTRIBUTING.md) at the repository root. It defines the
safety contract, refactoring rules, testing standard (including the
mutation/fault-injection requirement), and the required verification suite.
Read it before making changes.

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

All user-interface icons must come from the Lucide icon set (`lucide-icons`). Do not mix emoji, SF Symbols, bespoke glyphs, or unrelated icon packs for UI actions/navigation/status indicators. When a new icon is needed in the Web UI, use the existing Lucide rendering helper and add the Lucide icon path there if it is not already available.
