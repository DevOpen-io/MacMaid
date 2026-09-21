# Contributing to MacMaid

Thank you for contributing to MacMaid.

MacMaid is a macOS cleanup, maintenance, application-removal, disk-analysis, developer-tooling, and memory-management utility. Because many features interact with user files, processes, applications, and system tooling, **correctness and safety always take priority over code brevity, abstraction, or raw performance**.

This document defines the minimum engineering standard for changes to the project.

---

## Core Engineering Priorities

Use this order when making decisions:

1. **Safety**
2. **Correctness**
3. **Backward-compatible behavior**
4. **Testability**
5. **Readability and maintainability**
6. **Performance**
7. **Code size / abstraction**

A refactor is not successful simply because it removes lines of code.

A change should make the system measurably safer, clearer, easier to maintain, easier to test, or faster **without weakening existing guarantees**.

---

## Safety Contract

Do not weaken MacMaid's safety model.

Contributors must preserve the following principles:

- MacMaid must not run its main application flow as root.
- Destructive operations must fail closed.
- Unsafe, ambiguous, stale, or unverifiable targets must be rejected.
- User-visible destructive actions must preserve existing review and confirmation requirements.
- Reversible operations should continue to use Trash where designed.
- Runtime, SDK, package-manager, and developer-tool removals should use their owning manager whenever possible.
- Paths must be revalidated at execution time, not only during discovery.
- Symlink, ownership, path traversal, PID reuse, stale-token, and TOCTOU protections must not be bypassed for performance or convenience.
- Review tokens, fingerprints, generations, identity checks, and one-time-use semantics are security boundaries, not optional UX behavior.

Do not replace a safety check with an assumption such as "the UI already validated this."

---

## Do Not Rewrite Proven Safety-Critical Code Without a Strong Reason

Some code is intentionally more complex because the problem is complex.

Do not simplify or rewrite security-critical behavior only to reduce line count.

Examples include:

- validated path deletion
- fd-anchored filesystem operations
- Trash movement and post-condition verification
- execution-time revalidation
- process identity verification
- PID + creation-time checks
- review token / fingerprint validation
- whitelist enforcement
- cancellation-aware bounded scheduling
- analyzer traversal protections

If a simpler implementation changes an invariant, it is not equivalent.

---

## Refactoring Rules

Refactors must preserve observable behavior unless the behavior change is intentional, documented, and tested.

When refactoring:

- Work in small stages.
- Do not combine multiple high-risk architectural changes into one step.
- Run focused tests after each stage.
- Run the full verification suite before considering the work complete.
- Prefer explicit code over overly generic abstractions.
- Do not create helpers that require many special-case flags just to remove duplication.
- Do not move hidden mutable state from one abstraction to another.
- Do not trade security validation for caching or performance.
- Caches must have a clear invalidation strategy.
- Concurrency changes must consider races, stale state, cancellation, lock ordering, and TOCTOU windows.
- Public APIs, CLI behavior, TUI behavior, Web UI behavior, and desktop behavior should remain compatible unless a change is intentionally versioned.

Before introducing an abstraction, ask:

> Is the new code genuinely simpler and safer, or is the complexity only being moved somewhere else?

---

## Performance Changes

Performance work must preserve correctness.

Prefer removing repeated expensive work over weakening validation.

Examples of acceptable optimization strategies:

- avoid repeated full scans when a narrow revalidation is sufficient
- batch subprocess or process metadata queries where semantics remain identical
- parallelize independent probes with bounded concurrency
- cache immutable or safely invalidated data
- eliminate unnecessary serialization or polling
- reuse scan-time estimates only where audit semantics remain correct

When practical, provide before/after measurements.

Do not use microbenchmarks to justify behavior changes that reduce safety.

---

# Testing Standard

Passing tests are not enough.

A good test must be capable of rejecting incorrect code.

MacMaid treats test quality as part of production correctness.

---

## Never Change a Test Just to Make New Code Pass

When a production change causes a test to fail, first determine whether:

1. the production code is wrong,
2. the documented contract intentionally changed, or
3. the test itself was incorrect.

Do not automatically update expected values to match new behavior.

Do not:

- weaken assertions without justification
- replace exact behavioral assertions with "did not raise"
- change an expected failure into success only because implementation changed
- add `skip`, `xfail`, broad `try/except`, or loose comparisons to silence regressions
- modify mocks solely to match a new implementation
- remove an edge case because it makes the implementation difficult

If a contract intentionally changes, document the reason in the change and update the relevant tests explicitly.

---

## Test Public Behavior, Not Only Implementation Details

Prefer testing public entry points and externally observable results.

For example:

- test `Scanner.scan()` rather than only an internal whitelist helper
- test that a process stop request is rejected after identity changes
- test that a file is actually moved or rejected
- test the API mutation plus resulting state, not only HTTP 200
- test that a cache invalidates when its identity signature changes
- test that browser-gated behavior actually runs in a browser when browser behavior matters

Implementation-detail tests are acceptable when they protect an important invariant, but they should not replace end-to-end behavioral tests.

---

## Mock and Fake Fidelity

Mocks and fake objects must approximate the real dependency's behavior.

A mock that behaves differently from the real library can hide production bugs.

When adding or modifying a test double:

- compare its behavior with the real dependency
- preserve exception behavior
- preserve missing-attribute behavior
- preserve return-value semantics
- preserve permission/access-denied behavior
- avoid adding convenience attributes that do not exist in production
- prefer small integration tests when fidelity is uncertain

This is especially important for:

- `psutil`
- filesystem APIs
- symlinks
- ownership and permissions
- subprocesses
- Homebrew
- macOS command-line utilities
- browser behavior

---

# Mutation / Fault-Injection Requirement

Critical regression tests should prove that they can detect the bug they are intended to prevent.

For high-risk code, use controlled fault injection or mutation testing where practical.

The expected cycle is:

1. Correct production code → **PASS**
2. Reintroduce the target bug temporarily → **FAIL**
3. Restore correct implementation → **PASS**

Examples of useful mutations:

- remove an identity check
- remove a protected-process guard
- allow PID reuse
- disable a whitelist check
- bypass a symlink restriction
- make a review token reusable
- skip a generation/fingerprint check
- remove a post-condition
- break cache invalidation
- change a depth boundary
- alter a selection limit
- change `>` to `>=`
- change `and` to `or`
- return success without performing the destructive action

Temporary mutations must never remain in committed code.

A critical test that still passes after its protected behavior is deliberately broken is a **test coverage gap**.

---

## Security Regression Tests

Security-sensitive changes should normally include both positive and negative tests.

Where relevant, cover:

- symlink traversal
- directory replacement races
- path traversal
- absolute-path escape
- ownership mismatch
- permission mismatch
- stale discovery state
- whitelist changes after discovery
- PID reuse
- process identity changes
- stale review tokens
- token reuse
- generation mismatch
- fingerprint mismatch
- protected processes
- app-running gates
- destructive post-conditions
- cache invalidation
- fail-closed behavior when metadata is unavailable

---

## Browser and Web Tests

Keep test categories explicit.

Do not call all web tests "Browser E2E."

Use these terms consistently:

- **Unit / Service tests** — Python or JS logic without HTTP/browser
- **Web/API tests** — in-process or HTTP-level behavior without a real browser
- **Browser E2E tests** — actual Playwright/Chromium execution
- **Combined web-surface verification** — aggregate reporting only

All environment-gated browser tests intended for regression protection must also be executed in CI.

A test file that exists but is never run by CI is not reliable regression coverage.

---

# Required Verification

Before submitting a substantial change, run the applicable checks.

```bash
uv sync --all-groups
uv run pytest
uv run ruff check src/macmaid
uv run mypy
uv run python -m compileall -q src/macmaid
node --check src/macmaid/WebUI/app.js
node --check src/macmaid/WebUI/memory.js
uv build
git diff --check
```

For browser tests:

```bash
MACMAID_BROWSER_TESTS=1 uv run pytest \
  tests_py/test_memory_browser.py \
  tests_py/test_webui_devcaches_e2e.py -q
```

If the project configuration changes, update this document and CI together.

---

## Focused Tests During Development

Do not rely only on the final full-suite run.

After modifying a subsystem, run its focused tests first.

Examples:

- memory changes → memory + review + API memory tests
- scanner changes → scanner + safety + whitelist tests
- uninstall changes → application manager + execution safety tests
- filesystem changes → system safety + Trash + symlink tests
- Web mutation changes → web/API + browser tests
- localization changes → i18n + Web UI catalog tests

Then run the full suite.

---

# Static Analysis and Code Quality

New or modified production code should remain clean under the project's configured tooling.

Do not introduce new:

- Ruff violations
- type-checking errors
- unused imports
- dead branches
- hidden mutable global state
- unexplained magic numbers
- duplicated security logic
- broad exception handlers that hide errors

Where constants represent system behavior, prefer named constants over repeated literals.

Examples:

- sample intervals
- growth windows
- review limits
- cache TTLs
- cooldown periods
- maximum selection sizes

---

## Type Checking

Type coverage may be expanded incrementally.

When modifying a module not yet covered by strict type checking, avoid making future adoption harder.

Prefer:

- precise return types
- `Callable` over the builtin `callable`
- typed dataclasses for structured state
- explicit `Optional` / union handling
- narrow exception handling

Do not add meaningless casts merely to silence the type checker.

---

# Filesystem and Configuration Changes

When writing user files:

- preserve existing symlink behavior unless intentionally changing it
- preserve file mode where appropriate
- do not silently replace symlinks with regular files
- use atomic writes for regular files when safe
- understand that atomic replacement may affect inode-based metadata
- do not assume Linux and macOS expose identical filesystem APIs
- test macOS-specific behavior when relevant

Security-sensitive configuration reads should remain fail-closed at execution time.

Discovery-time behavior may be more permissive only when execution-time validation remains authoritative.

---

# Process and Memory Features

Process actions are high risk.

Any change involving process review, stop, force-stop, or automation must preserve:

- PID + creation-time identity
- executable / entrypoint verification where applicable
- protected-process checks
- user ownership checks
- review fingerprint binding
- single-use review tokens
- separate SIGTERM and SIGKILL flows
- force-stop eligibility checks
- fail-closed behavior when process metadata cannot be verified

Automation must never gain broader process authority as a side effect of refactoring.

---

# Subprocess and External Tooling

External tool integrations must handle:

- tool missing
- non-zero exit
- malformed output
- timeouts
- cancellation
- output format drift
- partially available metadata

Do not replace authoritative manager queries with inferred data unless equivalence has been validated against real systems.

If an optimization produces mismatches against the authoritative source, keep the authoritative source.

---

# Documentation and Behavior Changes

If a change affects user-visible behavior, update the appropriate documentation.

Examples:

- CLI flags
- API fields
- confirmation behavior
- localization keys
- destructive-action semantics
- supported package managers
- scanner depth or scope
- memory thresholds
- version numbers

Avoid documentation drift.

If code and documentation disagree, treat that as a defect.

---

# Versioning

Keep version surfaces synchronized.

At minimum, verify the version in all project-defined version locations, including package metadata and user-visible surfaces.

Use semantic versioning sensibly:

- **PATCH** — bug fix, security hardening, internal correction without intended breaking API changes
- **MINOR** — backward-compatible feature
- **MAJOR** — intentionally breaking contract

Do not bump the version merely because internal code moved between files.

---

# Pull Request Expectations

A good pull request should explain:

- what problem is being solved
- why the existing behavior is insufficient
- what invariants must remain unchanged
- what changed
- what did not change
- safety implications
- performance implications
- tests added or modified
- mutation/fault-injection proof for critical regressions
- commands used for verification
- known remaining risks or deferred work

For risky refactors, prefer several focused pull requests over one massive rewrite.

---

# Final Contributor Checklist

Before considering a change complete:

- [ ] Existing behavior is preserved unless intentionally changed.
- [ ] Safety guarantees are not weakened.
- [ ] No destructive path relies only on UI-side validation.
- [ ] Execution-time revalidation remains intact.
- [ ] New caches have correct invalidation.
- [ ] Concurrency and cancellation behavior was considered.
- [ ] New/changed tests verify behavior, not only implementation details.
- [ ] Mocks/fakes resemble real dependency behavior.
- [ ] Critical regression tests fail when the target bug is temporarily reintroduced.
- [ ] No assertions were weakened merely to make tests pass.
- [ ] Full test suite passes.
- [ ] Real browser E2E tests pass when relevant.
- [ ] Ruff passes for configured production scope.
- [ ] Mypy passes for configured scope.
- [ ] Python compilation check passes.
- [ ] JavaScript syntax checks pass.
- [ ] Package build succeeds.
- [ ] `git diff --check` passes.
- [ ] Documentation is updated if behavior changed.
- [ ] Version surfaces are synchronized when a release version changes.

---

## Guiding Principle

> A green test suite is useful only when incorrect code makes it red.

MacMaid contributors should optimize for **provable correctness, safe behavior, and maintainable code**, not simply for fewer lines, more abstractions, or a passing CI badge.
