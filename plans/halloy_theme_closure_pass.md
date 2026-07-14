# Halloy Theme System Closure Pass

## Purpose

Close the remaining correctness, integration, browser-behavior, diagnostics, caching, and release-readiness gaps in the Halloy-compatible theme subsystem after implementation of phases 1-5.

This is a corrective and validation pass, not a redesign. Preserve the current parser, translation layer, startup-built registry, packaged resources, external-theme override model, theme CSS route, browser-local preference model, and operator validation tooling unless a concrete defect requires a narrow change.

The highest-priority defect is the current stylesheet ownership error: the browser controller treats the main application stylesheet as the replaceable theme stylesheet. Because the theme endpoint serves only a `:root` palette block, successful activation removes the full structural/component stylesheet from the document. This must be corrected before broader polish work.

---

## Current implementation state

The repository now contains:

- `services/themes/` parser, color utilities, models, translator, registry, loader, manifest support, and emergency fallback;
- packaged Halloy themes under `resources/themes/`;
- configurable external Halloy theme discovery with bounded file count/size and traversal/symlink hardening;
- generated palette CSS at `GET /assets/themes/<theme_id>.css`;
- browser preference migration, system mode, searchable selector, storage synchronization, and metadata endpoint;
- theme validation CLI, authenticated diagnostics, contrast checks, provenance/inventory documentation, and release-validation integration;
- a large focused test suite.

Do not duplicate these systems. Tighten their integration and prove end-to-end behavior.

---

# Workstream A — Correct stylesheet ownership and loading

## A1. Separate application CSS from palette CSS

Every themed document must have two independent stylesheet roles:

1. **Application stylesheet** — permanent structural and component CSS.
2. **Theme stylesheet** — replaceable generated palette variables only.

Recommended markup:

```html
<link id="ainews-app-stylesheet"
      rel="stylesheet"
      href="{{ url_for('static', filename='css/style.css') }}">
<link id="ainews-theme-stylesheet"
      rel="stylesheet"
      href="{{ initial_theme_css_url }}">
```

The application stylesheet must never be removed or renamed by `static/js/theme.js`.

The theme stylesheet must appear after the application stylesheet so its custom-property declarations override the fallback palette in `variables.css`.

## A2. Apply the split consistently

Audit and correct all templates that load the theme controller or theme-aware CSS, including at minimum:

- `templates/base.html`;
- `templates/base_admin.html`;
- `templates/admin/login.html`;
- `templates/admin/setup_2fa.html`;
- `templates/admin/verify_2fa.html`;
- `templates/verify.html`;
- `templates/share_redirect.html`;
- any other standalone shell found by searching for `ainews-theme-stylesheet`, `style.css`, `style.bundled.css`, or `theme.js`.

For lightweight standalone pages that intentionally use `style.bundled.css`, retain their full stylesheet and add a separate palette link only if the page supports live theme switching.

## A3. Make the controller theme-link-specific

Refactor `theme.js` so:

- `STYLESHEET_ID` refers only to the palette link;
- no helper can target the application stylesheet;
- a pending palette link is inserted after the application stylesheet or existing palette link;
- on successful load, only the old palette link is removed;
- on failure, the old palette link remains active;
- fallback logic cannot remove structural CSS;
- repeated switches leave exactly one active palette link and no stale pending link.

## A4. Establish initial theme URL server-side

Prefer rendering a valid initial palette URL directly into the theme link from registry metadata/default configuration rather than starting the palette link at `style.css` or an empty invalid URL.

Requirements:

- default dark/light resolution remains compatible with system mode;
- the synchronous bootstrap can update the palette URL before first paint when a stored explicit preference exists;
- registry-unavailable mode leaves the static fallback palette in `variables.css` intact;
- no theme-specific server choice enters article/feed response cache keys.

## A5. Regression tests

Add tests that prove:

- full application CSS remains linked after theme activation;
- palette CSS is a second link;
- palette activation replaces only the palette link;
- failed theme loading preserves both the application stylesheet and previous palette;
- repeated switching leaves one app link and one theme link;
- admin and standalone shells use the same ownership contract;
- no template assigns `ainews-theme-stylesheet` to `style.css` or `style.bundled.css`.

A real DOM/browser test is preferred. If the repository has no browser runner, add a minimal JavaScript DOM harness or a deterministic Node/jsdom-style test only if dependency policy allows it. Otherwise add static template assertions plus a documented manual browser check; do not claim full browser coverage from route tests alone.

### Workstream A acceptance criteria

- Structural/component styling never disappears after theme activation.
- Exactly one permanent application stylesheet and one replaceable palette stylesheet exist on themed pages.
- Theme load failures are non-destructive.
- Tests catch any future ID collision or app-stylesheet removal.

---

# Workstream B — Correct browser controller semantics

## B1. Fix stale/unknown preference resolution

`resolveTheme()` should not return an unregistered explicit ID for activation.

For a stale `theme:<id>` preference:

1. detect that the ID is absent from registry metadata;
2. reset preference to `system` or the documented fallback policy;
3. resolve the configured system/default theme;
4. avoid issuing a predictable 404 request for the stale ID;
5. update selector state and storage coherently.

Retain route-level 404 behavior for arbitrary external requests.

## B2. Fix transition timing

Review `addThemeTransition()` and related flags.

Desired behavior:

- no transition animation during initial bootstrap/first paint;
- optional transition for subsequent user-initiated theme changes;
- no transition when `prefers-reduced-motion: reduce` is active;
- transition class always removed, including interrupted or failed loads;
- rapid theme changes do not leave the document in a transitioning state.

Rename state variables if necessary so their meaning is obvious.

## B3. Harden rapid-switch race handling

The current pending-link pattern must be robust when users switch themes before a prior stylesheet finishes loading.

Add a monotonically increasing activation generation/token or equivalent mechanism so:

- only the latest requested theme may become active;
- late `load` events from older requests are ignored and cleaned up;
- late `error` events do not trigger fallback over a newer successful request;
- pending links are bounded and removed;
- `_activatedThemeId`, `_resolvedThemeId`, document attributes, selector state, and storage describe the same final theme.

## B4. Clarify failure counter behavior

Review `_stylesheetErrorCount` and `_maxStylesheetErrors`.

Requirements:

- successful loads reset or decay the failure state;
- one transient network failure does not permanently consume the global budget;
- fallback attempts cannot recursively loop;
- after terminal fallback, static fallback palette remains usable even if generated theme CSS is unavailable;
- error state is observable in development without noisy public errors.

## B5. Preserve system-mode semantics

Verify:

- explicit theme selections ignore OS changes;
- system preference changes switch only between configured default dark/light themes;
- system-mode changes do not rewrite the stored preference to an explicit theme;
- cross-tab changes and media-query changes cannot race into inconsistent state;
- legacy `dark`/`light` migration runs once and removes or retires the legacy key according to documented policy.

### Workstream B acceptance criteria

- Unknown preferences recover without a failed CSS request.
- Initial paint does not animate.
- Subsequent switches behave correctly and respect reduced motion.
- Rapid changes are race-safe.
- Failure recovery is bounded and non-destructive.

---

# Workstream C — Metadata and selector correctness

## C1. Remove double escaping

Do not apply HTML escaping to display names before JSON serialization.

`_build_safe_metadata()` should return validated plain strings. Let:

- Jinja `tojson` handle JSON-in-HTML serialization;
- Flask `jsonify` handle API serialization;
- text-node rendering in JavaScript avoid HTML interpretation.

Add tests with display names containing:

- ampersand;
- apostrophe;
- quotation mark;
- less-than/greater-than characters;
- Unicode accents.

The selector should display the original name, not HTML entities.

## C2. Validate metadata schema explicitly

Create a typed or clearly validated metadata construction boundary.

Ensure every public entry contains only:

```text
id
name
appearance
css_url
origin
```

Do not expose source paths, TOML content, diagnostics internals, or emergency themes.

Validate that generated `css_url` values correspond to registry-known normalized IDs.

## C3. Review selector scalability and accessibility

With the full packaged theme set, verify:

- search remains responsive;
- duplicate display names are distinguishable where necessary;
- bundled/custom origin grouping or labels are understandable;
- keyboard navigation does not trap focus;
- Escape closes and restores focus;
- mobile bottom-sheet behavior does not hide the selected state;
- ARIA roles and active-descendant behavior match actual interaction;
- no raw HTML is inserted from metadata.

### Workstream C acceptance criteria

- Theme names render exactly as authored.
- Metadata is context-safe without pre-escaping artifacts.
- Selector remains usable with all bundled and custom themes.

---

# Workstream D — Diagnostics and provenance accuracy

## D1. Record registry build time on the registry

The diagnostics `built_at` field currently must represent actual registry construction time, not response generation time.

Add an immutable timestamp to `ThemeRegistry` or a registry metadata object at build completion. Return that value from diagnostics.

If response generation time is also useful, expose it separately as `generated_at`.

## D2. Record override provenance during registry construction

Do not infer external-over-bundled overrides from the final resolved theme map.

When an external theme replaces a bundled ID, record explicit provenance such as:

```text
overrides_origin = bundled
overrides_display_name = ...
override_source_id = ...
```

Public diagnostics may expose only a boolean and safe identifier/name. Internal paths must remain redacted.

Ensure diagnostics correctly report external overrides after the bundled entry has been replaced.

## D3. Correct aggregate semantics

Review diagnostic counts so:

- `warning_count` counts warnings only, not warnings plus errors, unless named accordingly;
- errors and warnings have separate totals;
- `valid` follows the same policy as the validation CLI;
- emergency fallback presence is distinct from emergency fallback being actively selected due to failure;
- total theme count semantics are documented and stable;
- duplicate diagnostic codes are aggregated deterministically.

## D4. Add registry health summary

Expose a bounded authenticated summary that can answer:

- registry built successfully;
- configured defaults resolved;
- bundled manifest loaded;
- custom directory enabled/disabled;
- custom files accepted/rejected counts;
- emergency fallback currently required or merely available;
- critical validation errors present.

Do not expose filesystem paths or raw exception text.

### Workstream D acceptance criteria

- `built_at` is truthful.
- Override reporting is accurate.
- Aggregate diagnostics use consistent definitions.
- Admin diagnostics distinguish fallback availability from fallback activation.

---

# Workstream E — HTTP and caching correctness

## E1. Use Werkzeug/Flask ETag handling

Replace raw string equality against `If-None-Match` with framework parsing that handles:

- multiple validators;
- weak validators where appropriate;
- quoted values;
- wildcard semantics;
- standard conditional response behavior.

Prefer `response.set_etag(...)`, `request.if_none_match`, and/or `response.make_conditional(request)` as appropriate.

## E2. Ensure complete 304 headers

A 304 response should retain required or useful cache metadata consistently, including ETag and cache policy according to framework behavior.

Add tests for:

- exact ETag;
- multiple ETags;
- weak ETag;
- nonmatching ETag;
- wildcard;
- malformed header fallback;
- GET and, if supported by Flask route semantics, HEAD.

## E3. Review cache lifetime and URL versioning

The current five-minute cache is safe but leaves performance on the table for immutable process-lifetime content.

Choose and document one model:

1. short cache plus ETag; or
2. long cache with digest/version in URL; or
3. long cache plus restart-stable digest query parameter.

Do not use long immutable caching on a URL whose external override content can change across restarts without a URL/version change.

A reasonable closure outcome is to retain `max-age=300` with correct ETags, document the rationale, and defer fingerprinted URLs.

## E4. Security headers and error behavior

Verify:

- `Content-Type: text/css; charset=utf-8`;
- `X-Content-Type-Options: nosniff`;
- unknown IDs return controlled 404 without reflected untrusted text in an HTML error body where avoidable;
- unavailable registry behavior is consistent and non-cacheable;
- theme metadata cache policy matches startup immutability and configuration behavior.

### Workstream E acceptance criteria

- Conditional requests are HTTP-correct.
- Cache behavior is documented and tested.
- Error responses do not reflect unsafe identifiers or leak internals.

---

# Workstream F — CSS contract and visual closure

## F1. Verify fallback layering

The static stylesheet must contain a complete usable fallback palette.

Generated theme CSS must override palette variables only and must not redefine:

- layout dimensions;
- spacing;
- typography scale/families;
- z-index;
- component selectors;
- arbitrary properties outside the approved token contract.

Add an allowlist-based CSS contract test for generated theme output.

## F2. Remove obsolete binary assumptions

Search for and classify remaining uses of:

```text
[data-theme="light"]
[data-theme="dark"]
ainews-theme
LIGHT
DARK
```

Retain only:

- compatibility migration code;
- appearance-specific behavior that intentionally applies to all light or dark themes;
- documented emergency fallback behavior.

Remove stale binary toggle code, duplicate styles, and documentation once migration compatibility is preserved.

## F3. Review non-CSS theme-colored surfaces

Audit and decide behavior for:

- `<meta name="theme-color">`;
- PWA manifest theme/background colors;
- SVG fills/strokes;
- Chart.js or canvas colors;
- QR/auth pages;
- email or newsletter HTML;
- browser form controls and `color-scheme`;
- selection color;
- focus indicators;
- forced-colors/high-contrast modes.

At minimum, update document `theme-color` dynamically from safe metadata or a generated CSS token if practical. If not included in this pass, document the fixed behavior and ensure it does not create illegible browser chrome.

## F4. Representative visual matrix

Manually or automatically validate:

- default dark theme;
- default light theme;
- one high-chroma dark theme;
- one low-saturation dark theme;
- one warm light theme;
- one external custom theme.

Pages:

- home/feed;
- search/filter state;
- topic/tag feeds;
- article detail;
- subscription/verification;
- admin login and 2FA;
- representative admin tables/forms;
- empty/error states;
- share redirect.

Viewports:

```text
320px
375px
768px
1280px+
```

Check first paint, switch behavior, HTMX navigation, focus states, contrast, overflow, and component persistence.

### Workstream F acceptance criteria

- Generated CSS is palette-only.
- The static fallback remains complete.
- Obsolete binary assumptions are removed or explicitly retained for compatibility.
- Representative public/admin pages are visually validated across light/dark/custom themes.

---

# Workstream G — End-to-end and failure-mode testing

## G1. Browser integration test matrix

Add the strongest practical automated coverage for:

- initial system theme;
- stored explicit theme;
- legacy migration;
- theme switch success;
- stylesheet 404;
- registry metadata absent;
- localStorage unavailable;
- rapid consecutive changes;
- cross-tab storage event;
- OS preference change;
- HTMX navigation;
- full-page navigation;
- app stylesheet persistence;
- selector keyboard behavior.

If introducing Playwright/Selenium is disproportionate, create a small deterministic browser smoke harness and document remaining manual coverage. Do not add a heavy dependency without considering CI and maintenance cost.

## G2. Server failure modes

Test:

- registry failed to build;
- configured defaults invalid;
- emergency fallback only;
- custom directory disappears;
- custom override becomes invalid;
- selected custom theme removed after restart;
- metadata endpoint unavailable;
- generated CSS empty;
- theme count at configured maximum;
- malformed identifiers and encoded traversal attempts.

## G3. Release artifact validation

Extend release checks to verify:

- packaged theme manifest exists;
- expected canonical bundled themes exist;
- theme resources are present in Docker image;
- validation CLI runs inside release/container environment;
- theme routes work in Compose smoke;
- static and theme stylesheet links both render in smoke HTML;
- generated assets are current.

## G4. Full repository validation

Run and record:

```bash
python scripts/validate_themes.py --bundled --strict
python scripts/build_assets.py css
python scripts/build_assets.py js
python scripts/build_critical_css.py --check
pytest tests/test_theme_*.py -q
pytest -q
ruff check . --exclude .venv
mypy .
./scripts/validate_release.sh --full
```

Use the repository’s canonical commands if they differ. Do not regenerate assets without committing and testing all resulting artifacts.

### Workstream G acceptance criteria

- The release-blocking integration defect has an automated regression test.
- Failure modes recover to a usable fallback.
- Release artifacts contain and serve the theme resources.
- Full repository validation passes.

---

# Workstream H — Documentation and cleanup

## H1. Correct architecture documentation

Update theme documentation to state explicitly:

- application CSS and palette CSS are separate resources;
- generated theme CSS contains variables only;
- the app stylesheet is permanent;
- theme selection is browser-local;
- registry refresh requires restart;
- stale selections fall back without requesting unknown CSS where implemented;
- cache and ETag behavior;
- diagnostics timestamp and override semantics.

## H2. Update troubleshooting guidance

Include symptoms and checks for:

- page loses layout after theme switch;
- palette CSS 404;
- custom theme ignored;
- selector name displays entities;
- stale localStorage selection;
- theme validation contrast failure;
- Docker image missing resources;
- external override not reported.

## H3. Remove dead code and comments

Remove:

- unused serializer maps/helpers;
- obsolete toggle functions;
- misleading phase/workstream comments in production code once implementation is stable;
- duplicated migration constants;
- stale docs claiming behavior that has changed.

Keep comments that explain invariants and security boundaries.

### Workstream H acceptance criteria

- Documentation matches final behavior.
- No dead binary-theme path remains outside deliberate migration support.
- Production code comments describe invariants rather than implementation history.

---

# Recommended commit sequence

Implement as small, reviewable commits:

1. **Fix stylesheet ownership and template integration**
   - separate permanent app link and replaceable palette link;
   - add static/template regressions.

2. **Harden browser activation state machine**
   - stale preference recovery;
   - transition correction;
   - rapid-switch race handling;
   - failure-counter cleanup.

3. **Correct metadata and selector rendering**
   - remove pre-escaping;
   - add special-character tests;
   - tighten metadata schema.

4. **Correct diagnostics provenance and timestamps**
   - registry `built_at`;
   - explicit override provenance;
   - aggregate semantics.

5. **Harden HTTP conditional caching**
   - framework ETag handling;
   - 304/header tests;
   - documented cache policy.

6. **Visual/CSS cleanup and binary-assumption removal**
   - palette-only allowlist;
   - meta/PWA/forced-color review;
   - representative visual matrix.

7. **End-to-end and release closure**
   - browser/failure-mode tests;
   - Docker/resource smoke;
   - full validation;
   - documentation cleanup.

Do not combine all work into one large commit. The first commit should restore frontend correctness independently of later polish.

---

# Definition of done

The Halloy theme line of work is closed when all of the following are true:

1. Theme activation never removes the application stylesheet.
2. All themed templates use separate permanent app CSS and replaceable palette CSS links.
3. Theme load failure preserves the previous palette and complete page styling.
4. Rapid theme switches are race-safe and leave one active palette link.
5. Unknown/stale stored IDs recover without requesting unregistered theme CSS.
6. Initial load does not animate; later changes respect reduced-motion policy.
7. Theme display names render without HTML-entity corruption.
8. Public metadata contains only safe, documented fields.
9. Diagnostics report actual registry build time and accurate external override provenance.
10. Warning/error/validity aggregates use consistent semantics.
11. Theme CSS conditional requests use standards-compliant ETag handling.
12. Generated theme CSS remains restricted to approved custom properties.
13. The static stylesheet contains a complete emergency/fallback palette.
14. Obsolete binary dark/light assumptions are removed except migration and deliberate appearance hooks.
15. Representative public and admin pages are visually validated across dark, light, and custom themes.
16. Browser-level or equivalent integration tests cover stylesheet persistence and switching failure modes.
17. Docker/release artifacts contain the packaged themes and pass validation in the deployed environment.
18. Focused theme tests, full tests, Ruff, mypy, asset checks, and release validation pass.
19. Documentation matches the final loading, fallback, caching, diagnostics, and customization behavior.
20. No known release-blocking defect remains in the Halloy theme subsystem.
