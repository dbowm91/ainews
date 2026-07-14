# Halloy Theme Verification and Corrective Pass

## Purpose

Close the final verification gaps in the Halloy-compatible theme roadmap without expanding product scope. This pass exists to reconcile strict-validation semantics, ensure CI enforces the intended policy, correct HTTP caching documentation, and produce evidence from a real browser that the theme subsystem behaves correctly under actual stylesheet loading, navigation, preference, and failure conditions.

This is a verification/corrective pass, not a new feature phase. Preserve the current parser, registry, CSS route, browser preference model, selector UX, and operator configuration unless a defect is demonstrated by the work below.

## Current state

The seven roadmap phases are implemented. The repository now includes:

- 48 packaged Halloy-derived themes plus an emergency fallback;
- startup-built theme discovery and translation;
- external theme support with bounded/path-safe loading;
- a permanent application stylesheet and replaceable palette stylesheet;
- versioned browser preferences, system mode, cross-tab synchronization, and selector UI;
- theme-specific CLI validation, diagnostics, package checks, lifecycle tests, accessibility checks, and failure recovery tests;
- a dedicated `theme-validation` GitHub Actions job;
- release-hardening and rollout/rollback documentation.

The remaining concerns are narrow:

1. The CI job runs `scripts/validate_themes.py --bundled --strict`, while release documentation also records hundreds of accepted contrast warnings. The exact strict-mode policy must be made explicit and mechanically consistent.
2. The release-hardening document describes the CSS ETag as weak, while the route uses Flask/Werkzeug `set_etag()` without `weak=True`, which normally emits a strong ETag.
3. Current visual coverage is largely static/contract-level. A real browser must verify stylesheet ownership, no-flash behavior, theme switching, navigation persistence, accessibility interaction, and recovery from stale or failed themes.
4. The repository should produce inspectable release evidence rather than rely only on commit-message claims.

## Non-goals

Do not add:

- new themes;
- a new theme format;
- live theme reload;
- fingerprinted theme URLs;
- arbitrary custom CSS;
- server-side per-user theme persistence;
- a broad frontend testing framework beyond the minimum needed for browser smoke validation;
- visual redesign or token expansion unless a rendered defect proves it necessary.

---

# Workstream 1 — Reconcile strict-validation semantics

## 1.1 Inspect all strict-mode entry points

Trace and document the exact behavior of:

- `scripts/validate_themes.py --strict`;
- `THEMES_STRICT_CONTRAST` in application configuration;
- translation-time fatal contrast checks;
- `classify_contrast_findings()`;
- `classify_accessibility_findings()`;
- bundled-theme validation in CI;
- operator validation examples in documentation.

Create a small policy table distinguishing:

| Finding class | Example | Default mode | CLI `--strict` | `THEMES_STRICT_CONTRAST=true` | Release blocking |
|---|---|---:|---:|---:|---:|
| Parse/format error | invalid TOML, invalid hex | error | error | error | yes |
| Translation invariant failure | unreadable primary text | error | error | error | yes |
| Required accessibility failure | primary text below 4.5:1 | error | error | error | yes |
| Advisory contrast warning | muted/secondary text | warning | define explicitly | define explicitly | policy-dependent |
| Decorative/non-text advisory | category accent edge case | warning/info | define explicitly | define explicitly | no unless explicitly promoted |
| Provenance/package issue | missing manifest file | error | error | error | yes |

Do not leave `--strict` as an ambiguous alias for “fail on every warning” if the bundled set intentionally retains documented advisories.

## 1.2 Choose and codify one strict policy

Recommended policy:

- `--strict` fails on all errors and on a named, stable subset of warnings classified as strict-promotable.
- Accepted advisory findings remain warnings and do not fail CI.
- `THEMES_STRICT_CONTRAST=true` uses the same strict-promotable classification as CLI `--strict`.
- The promotion decision is based on diagnostic code or category, not human-readable text.

Alternative acceptable policy:

- `--strict` fails on every warning.
- If this is selected, all bundled themes and tests must be adjusted so the strict CI command genuinely passes, either by fixing themes, changing mappings, or running non-strict bundled validation in CI with a separate exact-warning-baseline gate.

Do not keep a configuration where CI nominally uses strict mode but succeeds only because warnings are silently excluded without documentation.

## 1.3 Add stable diagnostic classification

Add or centralize helpers such as:

```python
is_fatal_diagnostic(diag)
is_strict_promotable(diag)
is_advisory_diagnostic(diag)
```

Requirements:

- classification derives from stable diagnostic codes/severity metadata;
- CLI, startup validation, tests, and docs use the same policy;
- no duplicate ad hoc warning lists in multiple modules;
- unknown future diagnostic codes default conservatively and are tested;
- JSON output identifies original severity and effective strict severity.

## 1.4 Add exact CLI exit-code tests

Cover at least:

- valid bundled set with accepted advisories;
- one parse error;
- one translation error;
- one strict-promotable warning;
- one advisory warning;
- mixed findings;
- `--strict` with JSON output;
- non-strict validation;
- `THEMES_STRICT_CONTRAST` parity where application configuration is involved.

Assertions must include:

- process exit code;
- summary counts;
- promoted counts;
- diagnostic codes;
- human-readable output;
- JSON schema stability.

## 1.5 Correct CI commands

Update `.github/workflows/ci.yml` so the command reflects the chosen policy.

Possible final form:

```yaml
- name: Validate bundled themes
  run: .venv/bin/python scripts/validate_themes.py --bundled --strict
```

This is acceptable only if the strict semantics are explicit and the command passes locally from a clean checkout.

If accepted advisories are tracked separately, add a deterministic baseline check rather than ignoring count drift. Example:

```yaml
- name: Validate bundled theme advisory baseline
  run: .venv/bin/python scripts/validate_themes.py --bundled --format json --output /tmp/theme-validation.json

- name: Check advisory baseline
  run: .venv/bin/python scripts/check_theme_advisory_baseline.py /tmp/theme-validation.json
```

Prefer checking diagnostic-code counts or an approved manifest over checking one undifferentiated total.

### Workstream 1 acceptance criteria

- CLI and configuration strict behavior are documented and identical where intended.
- CI command semantics are unambiguous.
- A strict-promotable warning demonstrably fails strict validation.
- An accepted advisory demonstrably does not fail if that is the selected policy.
- Bundled theme validation passes from a clean checkout.
- Warning-count or diagnostic-code drift cannot occur silently.

---

# Workstream 2 — Correct HTTP validator documentation and tests

## 2.1 Verify actual ETag form

Inspect the response produced by:

```python
response.set_etag(registered.content_digest)
return response.make_conditional(request)
```

Confirm whether the emitted header is:

```text
ETag: "<digest>"
```

or:

```text
ETag: W/"<digest>"
```

Do not infer from documentation. Assert the actual response header in tests.

## 2.2 Correct terminology

If `set_etag()` is called without `weak=True`, document it as a strong content validator.

Correct all references in:

- `docs/theme-release-hardening.md`;
- `docs/halloy-theme-contract.md`;
- frontend/theme route documentation;
- inline comments or tests.

Use precise wording:

- strong ETag if byte-for-byte content identity is represented;
- weak ETag only if explicitly emitted with `W/`;
- conditional request handling via Werkzeug/Flask;
- `304 Not Modified` contains no response body;
- cache policy remains `public, max-age=300` unless another deliberate decision is made.

## 2.3 Strengthen route tests

Test:

- first request returns `200`, CSS content, ETag, cache-control, and `nosniff`;
- exact `If-None-Match` returns `304`;
- comma-separated ETag list containing the current validator returns `304`;
- nonmatching ETag returns `200`;
- weak request validator behavior follows Werkzeug semantics;
- `HEAD` returns correct headers and no body if supported by Flask route defaults;
- unknown theme remains `404`;
- registry unavailable remains controlled `503`;
- ETag changes when CSS content changes in an isolated registry fixture.

### Workstream 2 acceptance criteria

- Documentation matches the emitted ETag form.
- Conditional request behavior is covered beyond a single exact header string.
- No raw manual ETag parsing is reintroduced.
- Cache behavior remains user-independent and proxy-safe.

---

# Workstream 3 — Add real-browser smoke coverage

## 3.1 Select the minimum browser harness

Preferred approach: Playwright with Chromium only for the blocking smoke lane.

Rationale:

- validates actual stylesheet load/error events;
- supports color-scheme emulation, viewport control, localStorage, multiple pages, and network interception;
- can inspect computed styles and stylesheet ownership;
- provides screenshots/traces as evidence;
- Chromium-only keeps dependency and runtime cost bounded.

Do not create an expansive cross-browser E2E suite in this pass. Firefox/WebKit may remain a documented manual check unless infrastructure already supports them cheaply.

If adding Playwright is operationally unacceptable, create a deterministic manual browser smoke script and evidence template. However, automated Chromium smoke is strongly preferred because the original release-blocking defect was invisible to static tests.

## 3.2 Add a browser-smoke test server fixture

Provide a deterministic test application startup path that:

- uses testing configuration;
- does not require external Redis, Celery, or production services for public/theme pages;
- binds to an ephemeral or fixed CI-local port;
- exposes at least home, admin login, metadata, and theme CSS routes;
- has a predictable bundled registry;
- shuts down cleanly after tests.

Avoid launching the full production stack solely for theme browser tests unless existing compose-smoke infrastructure is reused.

## 3.3 Test permanent versus replaceable stylesheets

In a real browser, assert:

1. `#ainews-app-stylesheet` points to the main application CSS.
2. `#ainews-theme-stylesheet` is a distinct link.
3. After initial theme activation, the app stylesheet remains connected.
4. Theme switching changes only the palette stylesheet URL.
5. Repeated switching leaves one app link and one active palette link.
6. No stale `-pending` theme links remain.
7. Layout-critical computed styles remain present after switching.

Use computed-style assertions on representative elements, for example:

- body font family or display/layout rule from app CSS;
- container width/margins;
- card border radius/padding;
- active palette background and text colors.

This proves that palette switching does not remove structural CSS.

## 3.4 Test initial bootstrap and visible flash behavior

Automate a bounded no-flash check:

- preload localStorage with an explicit non-default theme before navigation;
- record document attributes and computed colors at the earliest practical browser lifecycle points;
- verify the selected theme is active by first stable paint or before content is visibly exposed;
- confirm app CSS remains present throughout;
- capture a trace or screenshot on failure.

Do not claim mathematically zero FOUC from static assertions. Define a measurable release criterion, such as:

- no frame after initial content visibility uses a palette different from the resolved selection;
- no structural unstyled-content frame is observed;
- `data-theme-id` and palette stylesheet agree once `DOMContentLoaded` fires.

If implementation cannot meet this due to stylesheet network latency, document the exact fallback behavior and correct the bootstrap ordering.

## 3.5 Test preference behavior

Cover:

- no preference + OS dark;
- no preference + OS light;
- explicit dark theme;
- explicit light theme;
- legacy `dark` migration;
- legacy `light` migration;
- invalid stored ID;
- removed/nonexistent selected theme;
- localStorage unavailable or throwing;
- system mode responding to emulated OS scheme change;
- explicit mode ignoring OS scheme change;
- persistence after full reload.

Assert localStorage values, document attributes, selected UI option, and actual palette URL.

## 3.6 Test rapid switching and race handling

Trigger multiple theme selections faster than stylesheet responses complete.

Use route interception to delay selected CSS requests and force out-of-order completion.

Assert:

- last requested theme wins;
- stale load events cannot replace the active theme;
- pending links are cleaned up;
- `_activatedThemeId`, document attributes, selector state, and active CSS URL agree;
- no uncaught exceptions occur;
- the permanent app stylesheet remains untouched.

This converts existing source-contract race tests into actual browser evidence.

## 3.7 Test CSS failure recovery

Intercept one or more theme CSS requests and return:

- `404`;
- `503`;
- aborted network request;
- delayed response beyond the normal switch window.

Assert:

- current structural styling remains intact;
- controller falls back according to policy;
- invalid explicit preference is cleared or normalized as documented;
- selector and document attributes settle on the fallback;
- no infinite retry loop occurs;
- retry threshold behavior is bounded;
- subsequent valid theme selection still succeeds.

## 3.8 Test HTMX and full-page navigation

Validate that:

- active theme survives an HTMX navigation/swap;
- no extra palette stylesheet is inserted by fragments;
- full-page navigation restores the same explicit preference;
- system mode remains system mode rather than persisting a resolved explicit ID;
- standalone pages such as admin login/verification retain dual stylesheet ownership.

## 3.9 Test selector accessibility interaction

In Chromium, verify:

- trigger is keyboard focusable;
- Enter/Space opens selector;
- Escape closes it and restores focus;
- arrow-key navigation follows implemented semantics;
- search filters visible options;
- selected item exposes correct `aria-checked` or selected state;
- focus is visible under representative dark and light themes;
- reduced-motion emulation suppresses theme transition animation where expected.

Do not rely solely on template string assertions.

## 3.10 Capture evidence

On CI failure, retain:

- Playwright trace;
- screenshot;
- console log;
- network log for theme CSS requests.

On success, produce a concise test summary. Avoid committing routine generated screenshots unless the repository adopts screenshot baselines deliberately.

### Workstream 3 acceptance criteria

- Real Chromium executes theme switching and recovery tests.
- Structural CSS remains attached through all scenarios.
- Out-of-order stylesheet responses cannot activate stale themes.
- Explicit/system/legacy preferences work in the browser.
- HTMX and full-page navigation preserve the intended preference.
- CSS route failures leave the application usable.
- CI retains actionable artifacts on browser-test failure.

---

# Workstream 4 — Manual cross-browser and visual verification record

## 4.1 Run a bounded manual matrix

Perform a final manual pass in at least:

- Chromium/Chrome;
- Firefox;
- Safari/WebKit on macOS if available.

Use representative themes:

- `catppuccin-mocha`;
- `catppuccin-latte`;
- `nord`;
- `gruvbox`;
- `dracula`;
- one external custom theme;
- emergency fallback where practical.

Use representative pages:

- public home/feed;
- article detail;
- search/HTMX navigation;
- admin login;
- one data-dense admin page;
- 404/error page;
- theme selector open state.

Use viewports:

- 320px;
- 375px;
- 768px;
- 1280px or larger.

## 4.2 Record observed results

Add a dated section or separate record under `docs/` containing:

- commit SHA tested;
- operating system;
- browser and version;
- test themes/pages/viewports;
- pass/fail result;
- known non-blocking visual differences;
- screenshots only for defects or representative evidence;
- tester name/identifier if repository convention permits.

Do not mark unexecuted matrix cells as passed. Clearly distinguish:

- automated browser coverage;
- manual coverage;
- static contract coverage;
- deferred non-blocking combinations.

## 4.3 Verify visual-specific risks

Explicitly inspect:

- no unstyled content after theme activation;
- no header/nav jump;
- selector remains within viewport;
- mobile bottom sheet is usable;
- light themes do not retain dark-only shadows or browser chrome assumptions;
- focus rings remain visible;
- muted text remains readable;
- category/status cues are not color-only;
- form controls and autofill remain legible;
- native select/input appearance does not clash severely;
- scrollbar and selection colors remain acceptable where styled;
- meta `theme-color` behavior is understood, even if static.

### Workstream 4 acceptance criteria

- At least one real pass each in Chromium, Firefox, and Safari/WebKit is recorded where available.
- Failures are either corrected or explicitly documented as accepted non-blocking limitations.
- The validation record does not overstate unexecuted coverage.

---

# Workstream 5 — CI and release evidence

## 5.1 Add a browser smoke CI job

Add a separate job, for example `theme-browser-smoke`, rather than burying browser setup in unit-test jobs.

Suggested structure:

```yaml
theme-browser-smoke:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.12"
    - uses: astral-sh/setup-uv@v4
    - run: uv sync --frozen --all-extras
    - run: <install browser test dependency/browser>
    - run: <execute theme browser smoke suite>
    - uses: actions/upload-artifact@v4
      if: failure()
      with:
        name: theme-browser-smoke-artifacts
        path: <trace/screenshot directory>
```

Pin or lock the browser-test dependency according to repository conventions.

## 5.2 Ensure job dependencies are intentional

Decide whether browser smoke is:

- blocking for all pull requests touching theme/frontend files;
- blocking on all pull requests;
- blocking only on `main` and release branches.

Recommended initial policy: run on all CI invocations because the suite should remain small. If runtime is high, use path filtering only after ensuring changes to shared templates/build tooling cannot bypass it.

## 5.3 Produce machine-readable release evidence

Extend release validation to produce or verify:

- bundled validation summary;
- strict-policy result;
- theme-specific pytest result;
- browser smoke result;
- package-resource result;
- asset consistency result;
- lint/type-check result;
- clean-checkout command list.

A concise Markdown closure record is sufficient, but every claim must reference an executable command or CI job.

## 5.4 Verify from a clean checkout

Run, in order:

```bash
uv sync --frozen --all-extras
python scripts/validate_themes.py --bundled --strict
pytest <theme test selection>
<browser smoke command>
ruff check <changed/theme-related paths or full repo>
mypy <configured target>
python scripts/build_assets.py css
python scripts/build_critical_css.py
python scripts/build_assets.py js
# verify no generated diff
git diff --exit-code
```

Use repository-standard command wrappers where available.

If full repository tests are too costly, record both:

- required theme/release gate;
- broader suite status or reason it was not run.

### Workstream 5 acceptance criteria

- CI includes an actual browser smoke job.
- Failure artifacts are uploaded.
- Strict validation passes under documented semantics.
- Generated assets are reproducible.
- Closure evidence references actual commands/jobs.
- No release claim depends only on a commit message.

---

# Workstream 6 — Documentation reconciliation

Update the following as needed:

- `docs/theme-release-hardening.md`;
- `docs/theme-validation.md`;
- `docs/halloy-theme-contract.md`;
- `docs/theme-authoring.md`;
- `docs/theme-troubleshooting.md`;
- `docs/configuration.md`;
- `AGENTS.md` and the ainews skill documentation;
- the roadmap closure status.

Required corrections:

1. Define strict versus advisory validation semantics.
2. State the exact ETag strength emitted by the route.
3. Distinguish static contract tests from real-browser tests.
4. Record which browsers/viewports were actually executed.
5. Document browser smoke commands and failure artifacts.
6. State whether the 644-warning figure remains current, is split by diagnostic code, or is replaced by a baseline artifact.
7. Avoid saying “all matrix cells passed” unless they were actually executed.
8. Mark this corrective pass complete only after CI/browser evidence exists.

### Workstream 6 acceptance criteria

- Documentation matches code and CI.
- Strict-mode wording is consistent everywhere.
- ETag wording is technically accurate.
- Automated and manual evidence are clearly separated.
- Roadmap closure claim is evidence-backed.

---

# Implementation sequence

## Commit 1 — Strict policy and tests

- inspect and centralize diagnostic classification;
- reconcile CLI and configuration behavior;
- add exit-code and JSON tests;
- update theme-validation CI command/baseline;
- update strict-mode documentation.

## Commit 2 — HTTP validator correction

- verify ETag strength;
- expand conditional request tests;
- correct documentation and comments.

## Commit 3 — Browser smoke harness

- add minimal Playwright/Chromium setup;
- add deterministic test-server fixture;
- implement stylesheet ownership, preference, race, failure, navigation, and selector tests;
- add CI job and failure artifacts.

## Commit 4 — Manual verification and closure evidence

- execute bounded browser matrix;
- record real results;
- reconcile validation/release docs;
- run clean-checkout release commands;
- update roadmap closure record.

Keep commits separable so policy changes, browser infrastructure, and documentation evidence can be reviewed independently.

---

# Required tests

At minimum, add or update tests for:

- strict CLI exit semantics;
- advisory versus strict-promotable diagnostics;
- configuration/CLI parity;
- warning baseline drift;
- strong/weak ETag assertion;
- multi-value `If-None-Match`;
- `304` body behavior;
- permanent application stylesheet ownership in browser;
- atomic palette replacement;
- rapid-switch last-request-wins behavior;
- failed stylesheet fallback;
- explicit/system/legacy preference behavior;
- OS scheme changes;
- cross-tab synchronization;
- HTMX navigation;
- full reload persistence;
- selector keyboard interaction;
- reduced-motion behavior;
- standalone template theme activation.

---

# Definition of done

This verification/corrective pass is complete when:

1. `--strict` behavior is explicitly defined and shared with application strict-contrast behavior.
2. CI enforces the selected strict policy without contradictory accepted-warning claims.
3. Diagnostic drift is detected by code/category rather than an opaque total alone.
4. ETag documentation matches the actual emitted validator strength.
5. Conditional HTTP behavior is covered with standards-relevant cases.
6. A real Chromium browser test verifies that the application stylesheet is never replaced.
7. Browser tests verify atomic theme switching and stale-load race prevention.
8. Browser tests verify explicit, system, legacy, invalid, and unavailable-storage preference paths.
9. Browser tests verify CSS failure recovery and bounded retries.
10. Browser tests verify HTMX and full-page persistence.
11. Browser tests verify core keyboard/accessibility behavior of the selector.
12. Browser CI uploads traces/screenshots on failure.
13. A bounded Firefox and Safari/WebKit manual pass is recorded where available.
14. Validation documentation distinguishes static, automated-browser, and manual evidence.
15. Clean-checkout validation and generated-asset reproducibility pass.
16. The final roadmap closure record references executable evidence rather than commit-message assertions.

No further theme roadmap phase should be opened after this pass unless the verification work finds a substantive product defect.