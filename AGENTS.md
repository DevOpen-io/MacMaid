# MacMaid Agent Rules

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
