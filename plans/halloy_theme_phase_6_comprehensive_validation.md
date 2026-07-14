# Halloy Theme Phase 6 — Comprehensive Validation

## Purpose

Close the remaining validation gap for the Halloy-compatible theme system by exercising the subsystem as an integrated product rather than only as isolated parser, registry, route, and controller units.

The existing implementation already has broad unit and contract coverage. This phase must prove that the complete theme lifecycle behaves correctly across public pages, administrative pages, HTMX navigation, stale preferences, custom themes, browser storage failures, system color-scheme changes, and materially different palettes.

This phase is validation-focused. It should not redesign the parser, registry, token model, or browser preference architecture unless testing exposes a concrete defect.

## Current state

The following areas are already implemented:

- typed Halloy TOML parsing;
- strict color validation and canonicalization;
- Halloy-to-`AinewsTheme` translation;
- bundled resource manifest and package-safe loading;
- external custom-theme discovery and override precedence;
- path, symlink, count, and file-size hardening;
- code-defined emergency fallback;
- cacheable theme CSS delivery;
- separate application and palette stylesheets;
- versioned browser preference storage;
- legacy dark/light migration;
- system mode and cross-tab synchronization;
- accessible theme selector;
- operator validation CLI;
- authenticated diagnostics;
- extensive unit and route tests.

The remaining risk is integration behavior that cannot be fully demonstrated by static source assertions or pure-Python unit tests.

## Outcomes

At completion:

1. The complete browser stylesheet lifecycle is tested or reproducibly smoke-tested.
2. Representative dark, light, low-saturation, warm, high-chroma, and custom themes are reviewed.
3. Public, standalone, and administrative templates remain fully styled after theme activation.
4. HTMX and full-page navigation preserve theme state without adding theme-specific cache variants.
5. Stale, invalid, missing, and failed theme selections recover deterministically.
6. Accessibility checks cover real rendered states, not only token-pair calculations.
7. Docker and packaged-resource behavior is exercised in a production-like environment.
8. A documented validation matrix and evidence record are available for release review.

---

## Workstream 1 — Define the integrated validation matrix

Create a single source of truth for the matrix, either in this plan's implementation notes, a dedicated test manifest, or `docs/theme-validation.md`.

### Theme representatives

Use at least the following categories:

- configured default dark theme;
- configured default light theme;
- very dark/high-contrast theme;
- low-saturation dark theme;
- bright light theme;
- warm theme;
- high-chroma theme;
- one custom external theme;
- emergency fallback theme;
- one theme with non-fatal diagnostics.

Choose concrete bundled IDs from the manifest and record them in the validation document so the matrix is deterministic.

### Page representatives

Cover at minimum:

- public home/feed page;
- topic/category page;
- search or filtered state;
- article/detail page;
- newsletter subscription surface;
- empty state;
- application error page;
- admin login;
- admin 2FA setup and verification;
- authenticated admin dashboard;
- one data-dense admin table/form page;
- standalone verification page;
- share redirect page.

### Viewports

Validate at minimum:

- 320px;
- 375px;
- 768px;
- 1280px or wider.

### State dimensions

Cover:

- system mode with dark OS preference;
- system mode with light OS preference;
- explicit dark theme;
- explicit light theme;
- explicit custom theme;
- migrated legacy `dark` value;
- migrated legacy `light` value;
- invalid stored preference;
- selected theme removed from registry;
- localStorage unavailable;
- CSS route failure;
- repeated rapid theme changes;
- cross-tab preference change;
- HTMX fragment navigation;
- full-page navigation.

Avoid taking a full Cartesian product. Define a risk-weighted matrix that covers every page family, viewport class, theme class, and failure mode at least once.

### Acceptance criteria

- The matrix is committed and reproducible.
- Every roadmap definition-of-done item maps to at least one automated or manual validation step.
- Each manual-only step includes exact setup, expected result, and evidence requirements.

---

## Workstream 2 — Browser stylesheet lifecycle regression coverage

The prior release-blocking defect involved removal of the main application stylesheet. This phase must protect the corrected ownership model.

### Required assertions

For a normal page after initialization:

1. `#ainews-app-stylesheet` exists.
2. Its URL still targets `static/css/style.css` or the generated application bundle.
3. `#ainews-theme-stylesheet` exists separately.
4. The theme link targets `/assets/themes/<id>.css` after successful activation.
5. Switching themes changes only the palette link.
6. The application stylesheet node is never removed or renamed.
7. At most one active palette link remains after a switch completes.
8. Temporary pending links are removed after success or failure.
9. Failed palette loads leave the application stylesheet and fallback palette usable.
10. Repeated rapid changes do not allow an older request to overwrite the final selected theme.

### Test implementation options

Preferred order:

1. Use an existing browser test framework if one is already present.
2. Add a narrowly scoped browser harness if the repository already carries compatible Node tooling.
3. Use a DOM-capable JavaScript test environment for controller lifecycle logic.
4. If adding a browser dependency would be disproportionate, implement a deterministic manual smoke script and strengthen static contract tests.

Do not add a large browser automation stack without checking repository cost, CI runtime, and maintenance burden.

### Race handling

Explicitly test:

- theme A requested, then theme B before A finishes;
- A loads after B;
- A fails after B succeeds;
- multiple `storage` events arrive in sequence;
- system preference changes during an explicit selection;
- explicit selection changes while system-theme CSS is loading.

The final DOM state and persisted preference must always correspond to the newest user intent.

### Acceptance criteria

- The application stylesheet preservation defect has a direct regression test or an exact automated smoke check.
- Stale asynchronous stylesheet events cannot win over newer selections.
- Palette link cleanup is deterministic.
- Failure recovery does not remove structural CSS.

---

## Workstream 3 — Preference, migration, and persistence validation

Expand validation beyond parser-level preference tests.

### Legacy migration

Validate:

- `ainews-theme=dark` migrates to `theme:<configured dark ID>`;
- `ainews-theme=light` migrates to `theme:<configured light ID>`;
- invalid legacy values migrate to `system`;
- an existing v2 preference is never overwritten by legacy storage;
- migration remains safe when configured defaults are unavailable;
- obsolete legacy keys are removed only according to documented compatibility policy.

### Current preference model

Validate:

- `system` resolves against current OS preference;
- explicit choices ignore later OS changes;
- invalid or malformed IDs resolve to system/default behavior;
- missing registered themes clear or normalize stale preferences;
- localStorage read failures are non-fatal;
- localStorage write failures are non-fatal;
- selector state reflects the effective preference, not merely the last attempted theme;
- cross-tab events update the active palette without feedback loops.

### HTMX and navigation

Validate that:

- the stylesheet nodes live outside HTMX replacement targets;
- selector state survives fragment swaps;
- page fragments do not include theme-specific inline CSS;
- article/feed cache keys remain independent of theme selection;
- full-page navigation rehydrates the same stored preference;
- browser back/forward navigation does not duplicate selector listeners.

### Acceptance criteria

- Preference migration and failure handling are covered at integration level.
- No theme-specific page or fragment cache variation is introduced.
- Repeated HTMX navigation does not duplicate event handlers or stylesheet nodes.

---

## Workstream 4 — Rendered accessibility validation

Token-level contrast calculations are necessary but insufficient. Validate rendered controls and content.

### Required rendered checks

For representative dark and light themes, inspect:

- body text;
- headings;
- muted metadata;
- links and hover/focus states;
- navigation active state;
- article cards;
- buttons and disabled buttons;
- form inputs, placeholders, validation errors, and focus rings;
- success, warning, error, and informational messages;
- category badges;
- theme selector trigger, search field, listbox, and selected option;
- admin tables and bulk-action controls;
- loading indicators and skeleton states;
- empty and error states.

### Non-color cues

Confirm that important states remain distinguishable through at least one non-color signal:

- text label;
- icon;
- shape;
- border;
- weight;
- accessible name.

### Browser preferences

Validate:

- `prefers-reduced-motion` suppresses theme-switch transitions;
- forced-colors mode remains usable;
- high-contrast overrides do not hard-code assumptions that conflict with custom themes;
- keyboard focus remains visible;
- theme selector is fully keyboard operable;
- screen-reader labels and expanded/selected states update correctly.

### Tooling

Use automated accessibility tooling only as a supplement. Manual keyboard and visual checks are still required for the selector and dynamic stylesheet behavior.

### Acceptance criteria

- Critical rendered text/control contrast passes the documented policy.
- No essential state relies on color alone.
- Theme selector works with keyboard-only interaction.
- Reduced-motion and forced-color behaviors are documented and validated.

---

## Workstream 5 — Visual regression and palette sampling

The goal is not pixel-identical output across themes. The goal is layout stability, readable hierarchy, and preservation of theme identity.

### Capture targets

Capture screenshots or equivalent evidence for the representative matrix across:

- home/feed;
- article/detail;
- admin login;
- one authenticated admin page;
- one standalone page;
- mobile navigation open state;
- theme selector open state.

### Review criteria

Check for:

- invisible or near-invisible borders;
- text blending into surfaces;
- hover and selected states indistinguishable from default state;
- category badges with unreadable labels;
- focus rings hidden against page or control backgrounds;
- gradients or shadows that assume a dark base;
- SVG icons with fixed colors;
- hard-coded browser chrome/theme-color mismatch;
- layout shift when palette CSS loads;
- unthemed flash;
- selector overflow with the full bundled theme set;
- mobile bottom-sheet clipping;
- admin tables losing row separation.

### Theme exceptions

If a bundled theme fails critical usability checks:

1. Determine whether translation is wrong.
2. Determine whether the semantic token model is insufficient.
3. Determine whether the upstream palette itself is unsuitable.
4. Prefer correcting translation or deriving a safe value.
5. Exclude the theme only when critical readability cannot be preserved without destroying its identity.
6. Document all exclusions and warnings in the inventory/provenance files.

### Acceptance criteria

- Representative screenshots or review evidence are attached to the handoff or release record.
- Any theme-specific exceptions are documented with reason and diagnostic code.
- No unresolved critical visual defect remains on core pages.

---

## Workstream 6 — Failure-mode and recovery testing

Exercise failures deliberately.

### Registry failures

Test:

- bundled manifest missing;
- one bundled file missing;
- all bundled themes invalid;
- configured default missing;
- configured dark default invalid;
- configured light default invalid;
- emergency fallback only;
- external directory missing;
- external directory unreadable;
- external file invalid;
- external file oversized;
- external file count limit exceeded;
- symlink escape;
- normalized identifier collision;
- external override of bundled theme.

### Runtime/browser failures

Test:

- metadata script absent;
- malformed metadata JSON;
- metadata endpoint unavailable;
- theme CSS route returns 404;
- theme CSS route returns 503;
- stylesheet load event never fires;
- localStorage throws;
- `matchMedia` unavailable;
- selected theme disappears between deployments;
- stale browser cache presents an old preference.

### Expected behavior

Every failure must result in one of:

- deterministic fallback to a valid default;
- deterministic fallback to the emergency theme;
- continuation with static fallback palette;
- clear authenticated diagnostics;
- non-fatal public behavior.

No failure may:

- remove the application stylesheet;
- expose filesystem paths;
- trigger unbounded retry loops;
- repeatedly issue failed stylesheet requests;
- persist an unusable preference indefinitely;
- prevent application startup unless an explicitly strict production policy requires it.

### Acceptance criteria

- Failure behavior is tested and documented.
- Emergency fallback behavior is demonstrated in a production-like app startup.
- Public pages remain usable under theme subsystem degradation.

---

## Workstream 7 — Production-like package and Docker validation

### Package-resource validation

Verify themes work when:

- running from a source checkout;
- running from the normal Docker image;
- running from any supported installed-package layout;
- current working directory is unrelated to the repository root.

Assert:

- `resources/themes/manifest.json` is present;
- canonical bundled themes are present;
- resource APIs resolve files without direct source-tree paths;
- emergency fallback does not depend on package data;
- external themes load from a read-only mounted directory.

### Docker smoke

Build and run the production image with:

1. bundled themes only;
2. a read-only external theme directory;
3. an invalid external theme alongside a valid one;
4. overridden bundled theme ID;
5. no custom directory.

Verify CSS and metadata routes from outside the container.

### Acceptance criteria

- Docker image includes all approved bundled resources.
- External themes work from a read-only volume.
- Invalid custom themes do not prevent startup.
- Theme validation command works inside or alongside the production artifact.

---

## Workstream 8 — Validation automation and CI integration

### Fast lane

Run on ordinary changes:

- theme parser/translation tests;
- registry and route tests;
- CSS contract tests;
- preference/controller unit tests;
- bundled theme validation;
- manifest/resource checks.

### Extended lane

Run on theme/frontend/release changes or scheduled CI:

- browser stylesheet lifecycle test;
- representative visual captures;
- Docker theme smoke;
- accessibility smoke;
- external custom-theme mount test.

### Runtime control

Keep validation proportionate:

- avoid launching a browser for every pure backend change;
- mark extended tests clearly;
- use deterministic fixtures;
- prevent screenshot churn from timestamps or dynamic content;
- document local commands.

### Acceptance criteria

- CI has an explicit blocking theme validation stage.
- Extended validation can be run locally and in release CI.
- Failure output identifies the theme, page/state, and violated contract.

---

## Workstream 9 — Evidence and sign-off record

Create a closure record containing:

- commit range validated;
- commands run;
- test counts;
- lint/type-check results;
- Docker image/build identifier;
- representative themes reviewed;
- pages/viewports reviewed;
- screenshots or artifact locations;
- known non-blocking warnings;
- excluded themes and reasons;
- final go/no-go decision.

This can be a release checklist, pull-request body, CI artifact, or committed validation document.

### Acceptance criteria

- Release reviewers can determine exactly what was validated.
- Manual checks are not represented as automated checks.
- Remaining warnings are explicit and bounded.

---

## Recommended implementation order

1. Define the matrix and representative themes.
2. Add stylesheet lifecycle/race regression coverage.
3. Validate preference migration, HTMX, and cross-tab behavior.
4. Add rendered accessibility and visual sampling.
5. Exercise registry/browser failure modes.
6. Validate Docker/package resources.
7. Integrate fast and extended CI lanes.
8. Produce sign-off evidence.

## Files likely to change

Potential files include:

- `tests/test_theme_preferences.py`;
- `tests/test_theme_css_contract.py`;
- `tests/test_theme_routes.py`;
- `tests/test_theme_registry.py`;
- `tests/test_theme_packaging.py`;
- new browser/integration test files;
- browser test configuration if already supported;
- `scripts/validate_release.sh`;
- `scripts/validate_themes.py`;
- `docs/theme-validation.md`;
- `docs/theme-troubleshooting.md`;
- CI workflow files;
- Docker smoke/test scripts.

Do not modify production theme logic merely to make tests easier unless the change improves a real boundary or observability contract.

## Completion criteria

Phase 6 is complete when:

- the integrated matrix is documented;
- application and palette stylesheet ownership has direct regression coverage;
- asynchronous theme-switch races are covered;
- public/admin/standalone pages are sampled across representative palettes;
- stale and failed preferences recover correctly;
- HTMX and full-page navigation preserve theme state;
- rendered accessibility checks pass;
- package and Docker resource behavior is demonstrated;
- fast and extended validation lanes are available;
- a release evidence record exists;
- no unresolved critical integration defect remains.
