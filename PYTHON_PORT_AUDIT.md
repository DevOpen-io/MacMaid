# Python port audit

MacMaid 0.9.16 is a Python 3.11+ application managed by `uv`. Its CLI, full-screen TUI, local Web UI server, scanning, cleanup, app uninstaller, disk analyzer, Project Purge, developer inventory/removal, optimization, status, snapshots, history, whitelist, shell completion, install and uninstall paths all execute from the `macmaid` Python package.

## Distribution

- `uv build` generates the source package and wheel under the ignored `dist/` directory when a release artifact is needed.
- Entrypoint: `macmaid = macmaid.cli:main`
- Runtime dependency: `psutil`; the HTTP server and TUI use the Python standard library.
- Web assets are included inside the wheel and do not depend on the checkout.

## Privilege boundary

Installation and normal operation are user-local and reject root execution. MacMaid never restarts itself with `sudo` and application removal never elevates. The separately reviewed advanced Spotlight rebuild may invoke one native macOS authorization dialog scoped to that fixed maintenance operation; cancellation fails closed.

## Mutation invariant

Every destructive feature follows scan/review, identity or path revalidation, execution, and post-condition verification. Generic deletion is limited to exact cache/log/temp allowlists. Installer files, analyzer selections, app remnants and project artifacts use Trash where appropriate. Developer runtimes, environments, tools and SDKs are removed only through their owning manager.

## Verification

The project check runs Python bytecode compilation, the pytest safety/Web suite, CLI version/help smoke checks and `uv build`. The Web server additionally enforces loopback binding, Host/Origin checks, an HttpOnly SameSite session cookie and server-side latest-scan selection for mutations.
