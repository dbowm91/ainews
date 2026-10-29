# Frontend Rendering — Milestone G Closure Matrix

## Scope

This document is the closure record for Milestone G: frontend rendering correctness
and visual identity for the ainews public site.

It covers the public feed (`/`), the topic and tag feeds, the article detail page
(`/article/<id>`), the RSS feed, the error pages, the service worker, the theme
stylesheet route (`/assets/themes/<theme_id>.css`), and the shipped stylesheets
(`static/css/*.css`) together with the inlined critical stylesheet.

Verification date: 2026-10-28. Milestone G plans:
`plans/milestone_g_frontend_rendering_overview.md`,
`plans/milestone_g_01_cascade_and_delivery.md`,
`plans/milestone_g_02_interaction_and_accessibility.md`,
`plans/milestone_g_03_visual_identity.md`,
`plans/milestone_g_closure_pass.md`. Source review: `docs/ui-review-2026-10.md`.

**Verification result:** 4,679 tests passed, 6 skipped (the browser-marked tests
skip when no Chromium binary is installed), 0 failed. Ruff reports the same 5
non-blocking findings as the Release 5 baseline. Mypy is clean over 472 source
files.

## Status definitions

| Status | Meaning |
|--------|---------|
| **complete** | Requirement is implemented, tested, documented, and verified against the codebase |
| **accepted limitation** | Requirement is implemented with a documented scope reduction that does not affect the supported operating model |
| **deferred** | Requirement is explicitly out of scope for the current release train |
| **failed** | Requirement was attempted but does not meet acceptance criteria |

---

## G1 — Cascade and delivery correctness

### G1 A — Critical CSS generator

| Field | Detail |
|-------|--------|
| Requirement | The generated critical stylesheet must be structurally identical to its source: no dropped braces, no dropped rules |
| Status | **complete** |
| Implementation | `scripts/build_critical_css.py:94` — `split_top_level_rules()`; `:141` — `format_css()`; `:174` — `validate_generated_css()`; `:207` — `build_critical_css()` |
| Unit evidence | `tests/test_critical_css_build.py` — 20 tests (brace balance, rule-count parity, committed-partial freshness, mobile media block, reduced-motion block) |
| Integration evidence | `scripts/build_critical_css.py --check` verifies the committed partial against a fresh generation |
| Failure-path evidence | `validate_generated_css()` raises on a three-way disagreement between source, minified form and generated form |
| Documentation | `docs/frontend.md` |
| Notes | The old formatter dropped the extra `}` of an empty fragment, and `minify_css()` collapsed adjacent `}}`. Both are fixed, and the second defect was in a different function than the one first identified |

### G1 B — Cascade contract

| Field | Detail |
|-------|--------|
| Requirement | The inline critical stylesheet must participate in the declared layer order, so component rules are not zeroed by the universal reset |
| Status | **complete** |
| Implementation | `templates/base.html:28` and `templates/base_admin.html:17` — the inline sheet is wrapped in `@layer reset { … }`; `static/css/style.css:3` declares the layer order |
| Unit evidence | `tests/test_cascade_layers.py` — 9 tests (layered inline sheet, single universal reset, single palette source) |
| Integration evidence | `tests/test_frontend_rendering_browser.py::TestComponentSpacing` — 4 browser tests assert computed padding, margin and height |
| Failure-path evidence | The browser tests fail when the inline sheet is unlayered again |
| Documentation | `docs/frontend.md`, `AGENTS.md` |
| Notes | The theme stylesheet stays unlayered so it beats the layered fallback palette |

### G1 C — Theme precedence

| Field | Detail |
|-------|--------|
| Requirement | The active theme's palette must be the palette the browser paints; the fallback palette must be defined in exactly one shipped source |
| Status | **complete** |
| Implementation | `templates/base.html:32` — the theme `<link>` follows the inline critical sheet; `static/css/critical.css` defines no palette token; `static/css/variables.css` is the only shipped palette source |
| Unit evidence | `tests/test_theme_precedence.py` — 9 tests (no palette token in the critical sheet, single palette source, theme sheet ordered after the fallback) |
| Integration evidence | `tests/test_frontend_rendering_browser.py::TestThemeApplies` — 2 browser tests assert the computed background and the declared palette value |
| Failure-path evidence | The browser tests fail when the theme sheet is moved before the fallback sheet |
| Documentation | `docs/frontend.md`, `docs/halloy-theme-contract.md` |
| Notes | The `@import url("/static/css/variables.css")` was removed from the critical sheet: an import there duplicated the palette ahead of the theme |

### G1 D — Article detail page

| Field | Detail |
|-------|--------|
| Requirement | `/article/<id>` must return 200 on both the cache-miss and the cache-hit path |
| Status | **complete** |
| Implementation | `services/related.py:41`, `:105`, `:123`, `:188` — `.unique()` on every `joinedload` query against a collection |
| Unit evidence | `tests/test_frontend_rendering_browser.py::TestArticlePage` — 2 browser tests (first visit, cached visit) |
| Integration evidence | `tests/test_routes.py::TestPublicRoutes::test_article_detail_caches_rendered_html_without_error` |
| Failure-path evidence | The cached-visit test fails when `.unique()` is removed |
| Documentation | `AGENTS.md` (joined-eager-load requirement) |
| Notes | The defect only appeared once the related-article cache was warm, which is why no earlier test caught it |

### G1 E — Error pages

| Field | Detail |
|-------|--------|
| Requirement | A browser navigation to an unknown path must receive the styled HTML error page, not raw JSON |
| Status | **complete** |
| Implementation | `app.py:222` — `_wants_json()` negotiates with `best_match()` instead of membership testing |
| Unit evidence | `tests/test_frontend_rendering_browser.py::TestErrorPages` — 1 browser test asserts status, content type and heading |
| Integration evidence | `tests/test_routes.py` — public route tests |
| Failure-path evidence | Werkzeug's `MIMEAccept` treats `*/*` as matching `application/json`, so membership testing classified every browser navigation as a JSON client |
| Documentation | `docs/frontend.md` |
| Notes | `templates/errors/404.html` and `500.html` now carry a meaningful `<h1>` |

### G1 F — Service worker

| Field | Detail |
|-------|--------|
| Requirement | The service worker must register without a console error |
| Status | **complete** |
| Implementation | `routes/public/feeds.py` — `/service-worker.js` route with `Service-Worker-Allowed: /`; `static/js/app.js` registers `/service-worker.js` and warns on failure |
| Unit evidence | `tests/test_frontend_rendering_browser.py::TestServiceWorker` — 1 browser test asserts no scope error |
| Integration evidence | `tests/test_admin_route_auth.py` — `public.service_worker` in the public-route list |
| Failure-path evidence | Registration failure is surfaced with a console warning instead of failing silently |
| Documentation | `docs/frontend.md` |
| Notes | The scope error was previously whitelisted as benign in the browser smoke suite |

### G1 G — Discarded rules

| Field | Detail |
|-------|--------|
| Requirement | The htmx spinner must be invisible at rest, and the top-stories grid must not leave an empty column |
| Status | **complete** |
| Implementation | `static/css/layout.css` — scale-only `pulse-scale` keyframes; `static/css/articles.css` — `.top-impact-grid` uses `repeat(auto-fit, minmax(min(240px, 100%), 1fr))` |
| Unit evidence | `tests/test_ui_static_contracts.py` — the spinner must not animate opacity, the grid must use an intrinsic track |
| Integration evidence | `tests/test_frontend_rendering_browser.py::TestIndicatorVisibility` — 1 browser test |
| Failure-path evidence | Both static and browser assertions fail when the defect is reintroduced |
| Documentation | `docs/frontend.md` |
| Notes | The fixed 641–900px two-column override was removed |

### G1 H — Rendered-document cache

| Field | Detail |
|-------|--------|
| Requirement | The rendered-document cache must not serve one database's pages to a process serving another, and a cache invalidation in one worker must become visible in another |
| Status | **complete** |
| Implementation | `services/cache.py` — `scope_for_database()`, `set_cache_scope()`, `NullResponseCache`; `app.py` — the application factory publishes the scope of its database; `config.py` — `RESPONSE_CACHE_ENABLED`, `L1_CACHE_TTL` |
| Unit evidence | `tests/test_response_cache_scope.py` — 13 tests (scope stability, scope isolation, no credential leakage, null cache, L1 expiry cap) |
| Integration evidence | `tests/test_routes.py::TestPublicRoutes::test_article_detail_caches_rendered_html_without_error` |
| Failure-path evidence | The in-process layer expires within `L1_CACHE_TTL` seconds, so a cross-worker invalidation takes effect instead of being masked for minutes |
| Documentation | `docs/frontend.md` |
| Notes | This defect was found during Milestone G verification: a cached document rendered against the test database was served to the development instance, which made a stylesheet fix appear not to work |

---

## G2 — Interaction and accessibility correctness

### G2 A — Extended contrast validation

| Field | Detail |
|-------|--------|
| Requirement | Theme contrast validation must cover the tokens that actually fail, not only the primary text pair |
| Status | **complete** |
| Implementation | `services/themes/translate.py` — `classify_contrast_findings()` covers `text_secondary`, `text_muted` and `link` against the three surfaces; `services/themes/errors.py` — `THEME_CONTRAST_SECONDARY_AA`, `THEME_CONTRAST_MUTED_AA`, `THEME_CONTRAST_ACCENT_AA` |
| Unit evidence | `tests/test_theme_accessibility_validation.py` — 44 tests (extended matrix, bundled themes meet the extended matrix) |
| Integration evidence | `scripts/validate_themes.py` — `--strict` promotes the new codes |
| Failure-path evidence | Tests cover each newly checked pairing failing in isolation |
| Documentation | `docs/halloy-theme-contract.md` |
| Notes | `is_advisory_diagnostic()` semantics were not changed; `is_advisory_by_default()` expresses "warns by default, fatal under strict" |

### G2 B — Shipped fallback palette

| Field | Detail |
|-------|--------|
| Requirement | Every text-bearing token in the shipped fallback palette must pass AA against the surface it renders on, in both light and dark mode |
| Status | **complete** |
| Implementation | `static/css/variables.css` — both palettes re-ramped; dark `#0b0f16/#111721/#18202c/#1e2733`, light `#e9edf2/#f7f9fb/#dde3ea/#ffffff` |
| Unit evidence | `tests/test_palette_contrast.py` — 18 tests (plain-text AA per token per surface, tinted-badge AA, alpha-variant fidelity, accent label colour) |
| Integration evidence | `tests/test_theme_visual_validation.py` |
| Failure-path evidence | Each token is checked independently against each surface, including the composited 15% badge tint |
| Documentation | `docs/frontend.md`, `docs/halloy-theme-contract.md` |
| Notes | The palette is defined in exactly one shipped source; the theme stylesheet overrides it |

### G2 C — Bundled themes

| Field | Detail |
|-------|--------|
| Requirement | All 48 bundled themes must satisfy the extended contrast matrix |
| Status | **complete** |
| Implementation | `services/themes/translate.py` — `_floor_readable()` / `_apply_text_readability_floor()` raise only the lightness of a failing text tone; `services/themes/colors.py` — `ensure_contrast()`, `on_accent_color()`, `ensure_fill_legible()` |
| Unit evidence | `tests/test_theme_accessibility_validation.py::TestBundledThemeContrast` and `::TestAccentSurfaceLabel` |
| Integration evidence | `scripts/validate_themes.py --bundled --strict` |
| Failure-path evidence | The floor is applied in the translation layer, so an external theme is held to the same rule |
| Documentation | `docs/themes-inventory.md`, `docs/halloy-theme-contract.md` |
| Notes | The floor lives in the translation layer rather than in the 48 upstream TOML files, so the bundled files stay byte-identical to what Halloy ships. 35 themes failed the extended matrix before the floor; 0 fail now |

### G2 D — Target sizes

| Field | Detail |
|-------|--------|
| Requirement | Every interactive control must meet the WCAG 2.2 SC 2.5.8 minimum of 24×24 CSS px, and 44×44 on coarse-pointer devices |
| Status | **complete** |
| Implementation | `static/css/layout.css` — a `@media (pointer: fine)` floor for 13 interactive selectors; the existing `@media (pointer: coarse)` 44 px floor is preserved |
| Unit evidence | `tests/test_ui_static_contracts.py` — the target-size floor is asserted for every listed selector |
| Integration evidence | `tests/test_frontend_rendering_browser.py` |
| Failure-path evidence | The two media queries are mutually exclusive by definition, so the coarse rule always wins on a touch device |
| Documentation | `docs/frontend.md` |
| Notes | The two queries are independent; neither overrides the other |

### G2 E — Category filter semantics

| Field | Detail |
|-------|--------|
| Requirement | The category filter must not use the ARIA tab pattern, because it navigates rather than swaps panels |
| Status | **complete** |
| Implementation | `templates/partials/feed.html` — the filter is a `<nav>` with `aria-current="page"` |
| Unit evidence | `tests/test_ui_static_contracts.py` — no `role="tablist"`, `role="tab"` or `aria-selected` |
| Integration evidence | `tests/test_frontend_rendering_browser.py::TestCategoryFilterSemantics` — 1 browser test |
| Failure-path evidence | Both the static and the browser assertion fail when the tab roles return |
| Documentation | `docs/frontend.md` |

### G2 F — Motion and contrast preferences

| Field | Detail |
|-------|--------|
| Requirement | `prefers-reduced-motion` and `prefers-contrast` must be honoured |
| Status | **complete** |
| Implementation | `static/css/utilities.css` — a global `prefers-reduced-motion: reduce` net naming every animation in the public stylesheets; `static/css/variables.css` — a `prefers-contrast: more` block |
| Unit evidence | `tests/test_critical_css_build.py` — the reduced-motion block survives generation; `tests/test_ui_static_contracts.py` |
| Integration evidence | `tests/test_frontend_rendering_browser.py::TestCriticalStylesheetIsComplete::test_reduced_motion_rule_is_present` |
| Failure-path evidence | The browser test fails when the block is dropped from the generated sheet |
| Documentation | `docs/frontend.md` |

### G2 G — Minor defects N1–N9

| Field | Detail |
|-------|--------|
| Requirement | The nine minor findings of the source review must each have a terminal status |
| Status | **complete** |
| Implementation | N1 duplicate `.search-container` removed; N2 `.search-kbd` moved out of the field; N3 `.search-clear` given explicit 28×28 geometry and a visible resting state; N4 the accent stripe replaced by a short hover/focus marker on hairline rows; N5 `.sort-select` restyled with a custom chevron; N6 the redundant `aria-label` removed; N7 the 404/500 pages given meaningful `<h1>`s; N8 the subscribe spinner marked `aria-hidden="true"`; N9 `static/js/bundle.min.js` confirmed to be loaded by no template |
| Unit evidence | `tests/test_ui_static_contracts.py` — 29 tests (duplicate selector blocks, filter ARIA, spinner animation, intrinsic grid, and the N-series contracts) |
| Integration evidence | `tests/test_frontend_rendering_browser.py` |
| Failure-path evidence | Each static contract fails when its defect is reintroduced |
| Documentation | `docs/frontend.md` |
| Notes | N9 is an accepted limitation: the file is not referenced by any template, and its disposition is deferred to a separate decision |

---

## G3 — Visual identity

### G3 A — Editorial type hierarchy

| Field | Detail |
|-------|--------|
| Requirement | Headlines must dominate the page, and body prose must sit on a readable measure |
| Status | **complete** |
| Implementation | `static/css/variables.css` — the scale is re-based (xs 11–12 … 5xl 40–48); `static/css/articles.css` — body prose re-points to `--text-lg`, `.card-title` to `--text-xl`/650/1.28, `.article-title` to `--text-3xl`/700/1.18 |
| Unit evidence | `tests/test_ui_static_contracts.py` — the prose and title token assignments are asserted |
| Integration evidence | `tests/test_frontend_rendering_browser.py::TestComponentSpacing` |
| Failure-path evidence | The static assertions fail when a prose rule is re-pointed at a display token |
| Documentation | `docs/frontend.md` |
| Notes | `--text-6xl` and `--text-7xl` were dead tokens and were removed |

### G3 B — Accent discipline

| Field | Detail |
|-------|--------|
| Requirement | `--accent` is chrome; `--link` is the text token. Headlines are body text, not links |
| Status | **complete** |
| Implementation | `static/css/variables.css` — `--link` and `--link-hover`; `services/themes/translate.py` — `link` carries the accent hue and is floored for legibility; `static/css/components.css` — `a { color: var(--link) }` |
| Unit evidence | `tests/test_palette_contrast.py` — `--link` is a text-bearing token checked on every surface |
| Integration evidence | `tests/test_frontend_rendering_browser.py::TestCardTitleColour` — 1 browser test |
| Failure-path evidence | The browser test fails when a headline is painted with the accent colour |
| Documentation | `docs/halloy-theme-contract.md` |

### G3 C — Layout

| Field | Detail |
|-------|--------|
| Requirement | The feed must be a two-column page above 1024 px, the toolbar must be a single row, and article cards must be hairline rows |
| Status | **complete** |
| Implementation | `static/css/pages.css` — `.page-grid`, `.page-rail`, `.container--wide`; `templates/base.html` — `.page-grid` / `.page-rail` / `#content.page-main`; `templates/partials/feed.html` — the single-row `.feed-toolbar`; `static/css/articles.css` — hairline rows with a 1.5rem rhythm |
| Unit evidence | `tests/test_ui_static_contracts.py` |
| Integration evidence | `tests/test_frontend_rendering_browser.py::TestPageLayout` — 2 browser tests (two columns above 1024 px, one below) |
| Failure-path evidence | The browser tests fail when the grid changes to a single column above the breakpoint |
| Documentation | `docs/frontend.md` |
| Notes | Below 1024 px the rail collapses to a compact band carrying the pipeline state and the subscribe call to action; the topics list and the impact leaders duplicate the main column and are hidden at that width |

### G3 D — Pipeline provenance

| Field | Detail |
|-------|--------|
| Requirement | The feed must show where each article came from. Pipeline *state* belongs to the admin area and is not shown on the public index |
| Status | **complete** |
| Implementation | `services/article_provenance.py` — `reading_time_minutes()`, `agent_provenance()`, `is_pipeline_produced()`; `services/feed_stats.py` — grouped aggregates in one query for the topic taxonomy and the impact ranking; `templates/partials/article_card.html` — the source line and the subordinate agent line. The per-status pipeline counts stay in the service for the admin screens |
| Unit evidence | `tests/test_ui_static_contracts.py` — the template renders the provenance fields |
| Integration evidence | `tests/test_frontend_rendering_browser.py` |
| Failure-path evidence | The static assertion fails when the provenance line is removed |
| Documentation | `docs/frontend.md` |
| Notes | `services/feed_stats.py` uses grouped aggregates rather than eager collection loads, so the rail does not scale with the feed size |

### G3 E — Surface ramps

| Field | Detail |
|-------|--------|
| Requirement | Surfaces must be a designed ramp rather than ad-hoc greys |
| Status | **complete** |
| Implementation | `static/css/variables.css` — a four-step ramp per mode, with `--bg-subtle`, `--bg-hover` and `--bg-input` aliased to ramp steps; `services/themes/translate.py` — `--bg-elevated` is emitted by `to_css_variables()` |
| Unit evidence | `tests/test_palette_contrast.py` — the surface tokens are checked per token |
| Integration evidence | `tests/test_theme_visual_validation.py` |
| Failure-path evidence | The tests fail when a ramp step is removed or an alias is repointed |
| Documentation | `docs/halloy-theme-contract.md` |

### G3 F — Component geometry

| Field | Detail |
|-------|--------|
| Requirement | One button geometry, two badge geometries, a legible primary action |
| Status | **complete** |
| Implementation | `static/css/components.css` — one button geometry (34 px, `--radius-md`, sans `--text-md`, 12 px padding) shared by `.btn` and `.subscribe-btn`; two badge geometries (filled `.badge`/`.category-badge`/`.pipeline-badge`, outlined `.tag-pill`/`.nav-tag`); `services/themes/translate.py` — `--accent-contrast` is the label colour of a filled accent surface |
| Unit evidence | `tests/test_palette_contrast.py::TestAccentSurfaceLabel`; `tests/test_ui_static_contracts.py` |
| Integration evidence | `tests/test_frontend_rendering_browser.py::TestStylesheetDelivery` |
| Failure-path evidence | The label colour is checked against the accent fill and the hover fill of every bundled theme |
| Documentation | `docs/halloy-theme-contract.md` |
| Notes | The subscribe button was labelled with `--text-primary` on the accent fill: 1.63:1 in the light theme. `--accent-contrast` raises it to 4.91:1 and is now a contract token of every theme |

---

## Defect register

Every finding of `docs/ui-review-2026-10.md`, with its terminal status.

| ID | Finding | Severity | Status | Evidence that closed it |
|----|---------|----------|--------|--------------------------|
| B1 | Article detail page returns HTTP 500 | blocker | **complete** | `services/related.py` `.unique()`; browser test for the cached visit |
| B2 | All 48 themes render identically | blocker | **complete** | `tests/test_theme_precedence.py`; `TestThemeApplies` browser tests |
| B3 | Generated critical CSS drops 3 closing braces | blocker | **complete** | `scripts/build_critical_css.py` `validate_generated_css()`; `tests/test_critical_css_build.py` |
| B4 | Every component's padding and margin computes to 0px | blocker | **complete** | `@layer reset` wrapper; `tests/test_cascade_layers.py`; `TestComponentSpacing` browser tests |
| B5 | Mobile layout overflows by up to 469 px | blocker | **complete** | `TestNoHorizontalOverflow` browser test at 375/390/583/768/1024/1280/1440 px |
| M1 | Unlayered critical CSS overrides component link styling | major | **complete** | `tests/test_theme_precedence.py`; `TestCardTitleColour` browser test |
| M2 | 404 and 500 pages return raw JSON to browsers | major | **complete** | `app.py:_wants_json()`; `TestErrorPages` browser test |
| M3 | Service worker never registers | major | **complete** | `/service-worker.js` route with `Service-Worker-Allowed: /`; `TestServiceWorker` browser test |
| M4 | Stray `…` spinners permanently visible | major | **complete** | scale-only keyframes; `TestIndicatorVisibility` browser test |
| M5 | `top stories` leaves an empty third column | major | **complete** | intrinsic grid track; `tests/test_ui_static_contracts.py` |
| M6 | Reduced-motion support is dead | major | **complete** | `prefers-reduced-motion` net in `static/css/utilities.css`; browser test |
| M7 | Measured WCAG contrast failures | major | **complete** | extended matrix; `tests/test_palette_contrast.py`; bundled themes remediated |
| M8 | Two different cascade worlds | major | **complete** | `tests/test_cascade_layers.py` — one layer order, one palette source |
| M9 | Tap targets below 24 px | major | **complete** | `@media (pointer: fine)` target floor; `tests/test_ui_static_contracts.py` |
| M10 | Category filter misuses the ARIA tab pattern | major | **complete** | `<nav aria-current="page">`; `TestCategoryFilterSemantics` browser test |
| N1 | `.search-container` defined twice | minor | **complete** | duplicate selector check in `tests/test_ui_static_contracts.py` |
| N2 | `.search-kbd` clipped by the input edge | minor | **complete** | moved outside the field; static contract |
| N3 | `.search-clear` invisible but space-occupying | minor | **complete** | explicit 28×28 geometry and a visible resting state |
| N4 | Accent stripe overlapped by the bookmark button | minor | **complete** | replaced by a short hover/focus marker on hairline rows |
| N5 | `.sort-select` renders as a raw browser control | minor | **complete** | custom chevron, `appearance: none` |
| N6 | Verbose duplicate `aria-label` on the card title | minor | **complete** | removed; static contract |
| N7 | 404 page has no `<h1>` | minor | **complete** | meaningful `<h1>` on 404 and 500 |
| N8 | Subscribe spinner is a permanent glyph | minor | **complete** | `aria-hidden="true"` plus the shared spinner fix |
| N9 | `static/js/bundle.min.js` is a dead 65 KB artifact | minor | **accepted limitation** | asserted to be loaded by no template; disposition deferred |

### Findings raised during Milestone G verification

| ID | Finding | Severity | Status | Evidence that closed it |
|----|---------|----------|--------|--------------------------|
| V1 | A cached document rendered against the test database was served to the development instance, so a stylesheet repair appeared not to work | major | **complete** | database-scoped cache keys; `tests/test_response_cache_scope.py` |
| V2 | A cache invalidation in one worker left other workers serving the stale document for minutes | major | **complete** | `L1_CACHE_TTL` caps the in-process lifetime; `tests/test_response_cache_scope.py` |
| V3 | The subscribe button label was 1.63:1 on the accent fill | major | **complete** | `--accent-contrast` contract token; `tests/test_palette_contrast.py` |
| V4 | The CLI ignored its documented `AINEWS_*` path overrides and read the repository checkout instead | major | **complete** | `ainews_cli/context.py` `path_env_overrides()`; `tests/test_cli.py::TestPathEnvOverrides` |
| V5 | The application ignored its documented `LLM_PROVIDERS_FILE` override and always read the repository checkout | major | **complete** | `schemas/llm.py` `default_providers_path()`; `tests/test_smoke_migrations.py` |
| V13 | The configuration cache key named only the kind of configuration, so one `providers.yaml` could be served in place of another | major | **complete** | `schemas/common.py` `config_cache_key()`; every config loader now keys on the source file; `tests/test_config_cache_key.py` |
| V6 | The cross-file validator did not understand the ID-keyed provider mapping the CLI writes | major | **complete** | `ainews_config/validation.py` `_get_providers()`; `tests/test_config_validation.py` |
| V7 | The CLI context cached its configuration for the life of the process | minor | **complete** | `CLIContext.reset()` on every invocation |
| V8 | A headline rendered the literal text `&#8217;` | minor | **complete** | `schemas/item.py` decodes entities at ingestion; `tests/test_raw_item_schema.py` |
| V9 | `systemctl` was invoked unguarded on hosts without systemd | minor | **complete** | `ainews_cli/service/commands.py` `_run_systemctl()` |
| V10 | The logrotate sensitive-path check missed a symlink to `/etc` where `/etc` is itself a symlink | minor | **complete** | `ainews_cli/service/logrotate_commands.py` `_is_within()` |
| V11 | `clear_app_cache()` rebound the cache dictionary, so the Celery workers kept serving a stale application after an admin changed the configuration | major | **complete** | `celery_support.py` `clear_app_cache()` empties the cache in place; `tests/test_celery_app_cache.py` |
| V12 | The `pipeline_logs` cleanup test failed depending on test order, because the stale application read a different in-memory database | major | **complete** | `tests/test_celery_app_cache.py`; the cleanup tests are order-independent again |

---

## Previously invisible defects

Every defect in this milestone passed the existing suite. The reason is recorded here
so that a future reader can see what the tests asserted, and why it was not enough.

| Defect | Why the existing suite passed it |
|---|---|
| Theme palette inert | Tests assert the *text* of the generated CSS and the presence of a `<link>`; none observed the computed palette |
| Component spacing zeroed | No test computed a component's padding or margin |
| Mobile overflow | The browser smoke tests exercised theme switching at one viewport; none asserted `scrollWidth <= clientWidth` |
| Critical CSS malformed | No test compared brace counts or parsed rule counts |
| Article page 500 | The route was not exercised with a warm related-article cache |
| Error pages returning JSON | No test sent a browser-like `Accept` header |
| Service worker scope rejected | The console-error guard explicitly whitelisted it as benign |

The last row is the clearest signal. The whitelist also carried a
`variables.css` MIME-type entry, which is now diagnosed and removed: every
stylesheet the page loads is served as `text/css`, and
`tests/test_frontend_rendering_browser.py::TestStylesheetDelivery` asserts that
directly, so a regression cannot hide behind a whitelist entry again.

---

## Defects found during the live dev-instance restart

Restarting the local dev instance against the current code surfaced three
defects outside the frontend scope. They share one root cause: nothing in the
suite exercised the Celery beat, so the pipeline could be silently dead while
every test passed.

| Defect | Symptom | Why the existing suite passed it |
|---|---|---|
| Nine of fourteen beat tasks were never registered | `Received unregistered task of type 'tasks.cleanup.cleanup_stale_limiter_slots'` — newsletters, trend-memory consolidation, limiter-slot cleanup and subscriber cleanup never ran | `tasks/__init__.py` imported only a subset of the task modules; the worker bootstraps with `import tasks`, so a task in an unimported module never registers |
| Every beat task failed its signature guard | `Invalid signature for publish_scheduled_articles` — scheduled articles were never published | `verify_task()` fails closed when `CELERY_TASK_SECRET` is unset, and beat-dispatched tasks carry no signature. The environment was missing the secret, so the guard rejected every dispatch |
| `retry_stuck` aborted the whole sweep | `TypeError: can't subtract offset-naive and offset-aware datetimes` | The `MagicMock` fixture built its article with an *aware* `updated_at`; SQLite returns the value *naive*, so the arithmetic only fails against a real database |

All three are fixed and covered:

- `tasks/__init__.py` imports every task module, and
  `tests/test_celery_beat_task_registration.py` asserts that each task string in
  `Config.get_beat_schedule()` resolves to a registered task.
- `CELERY_TASK_SECRET` is configured for the dev instance. The fail-closed
  behaviour is deliberate and unchanged — a missing secret in production is
  still a startup error.
- `tasks/retry.py` normalizes timestamps with `_as_utc_aware()`, and
  `tests/test_pipeline/test_retry.py::TestStuckArticleTimezoneHandling` uses the
  naive value SQLite actually returns.

The observable effect, from the Celery result backend in Redis db 1: a beat tick
produced **0 successes and 2 failures** before the fix and **9 successes and 0
failures** after it.

---

## Defects found while exercising the rendered site

A second pass over the dev instance — clicking every link instead of loading
each URL — surfaced seven defects in the rendered site. Every one of them
passed the existing suite, because the suite asserted *markup* while the
defects were in *behaviour*.

| Defect | Symptom | Root cause | Fix |
|---|---|---|---|
| Article click answered HTTP 500 | No article could be opened by clicking; only "open in new tab" worked | `routes/public/links.py` rendered `partials/article_detail.html`, a template that did not exist | Template created; `templates/article.html` now includes it, so the page and the fragment cannot drift |
| Nav link produced a different, edge-to-edge layout | Clicking a nav link replaced the whole document with a bare fragment: no header, no footer, content at full width | `hx-boost="true"` on `<body>` made every anchor an HTMX request; the server answered with `partials/feed.html` and htmx replaced the entire `<body>` | `hx-boost` removed from `base.html` and `base_admin.html`; in-page updates declare their own `hx-get` with an explicit target |
| A cached fragment was served to a full page load | Navigating to a URL after an in-page swap produced a document with no header and no navigation | The fragment and the page share a URL, and the cacheable response carried no `Vary` header, so the browser's HTTP cache keyed them only by URL | `app.py` adds `Vary: HX-Request` to every response; the service worker no longer stores HTMX responses |
| Stylesheet changes never reached the browser | The site kept rendering with the previous milestone's CSS: the feed rail spanned the full width instead of a 260px column | The service worker served `/static/` cache-first under a constant cache name (`self.__SW_VERSION` was never set), so the cache was never invalidated | The cache name now carries a fingerprint of the shipped assets; `/static/` is fetched network-first with the HTTP cache bypassed |
| Article body showed literal Markdown | The "condensed article" section displayed `**bold**` and `### heading` markers | The body was emitted into the template verbatim | `services/markup.py` renders Markdown (or HTML) to sanitized HTML; the templates use the `body_html` / `markdown_html` / `inline_html` filters |
| Article body was one wall of text | Some articles rendered as a single unbroken paragraph | The sanitize allowlist omitted block level elements, so an HTML body's `<p>` tags were stripped and every paragraph was welded together | The allowlist now keeps block elements; `paragraphize()` additionally splits text that arrives as a single run |
| Admin navigation was broken | Every admin page raised `htmx is not defined`; `/admin/trend-memory` answered HTTP 500; a dashboard link answered HTTP 405 | The inline nonce script configured `htmx.config` before the deferred bundle had executed; one template referenced the non-existent `admin.article_detail` endpoint; one anchor pointed at a POST-only route | The nonce script waits for htmx; the endpoint is `public.article_detail`; the anchor is a POST form; `admin/partials/pipeline_logs.html` was missing and is now created |
| Stylesheet changes never reached the browser | The site kept rendering with the previous milestone's CSS: the feed rail spanned the full width instead of a 260px column | The service worker served `/static/` cache-first under a constant cache name (`self.__SW_VERSION` was never set), and the assets were served with a one year `max-age` under URLs that do not change when their contents do | The cache name now carries a fingerprint of the shipped assets; `/static/` is fetched network-first, and `SEND_FILE_MAX_AGE_DEFAULT = 0` makes the browser revalidate with the ETag |
| Infinite scroll nested a second feed container | Loading the next page inserted the new cards inside a duplicated `#feed` element | The scroll fragment was a full page fragment while the sentinel swaps itself with `hx-swap="outerHTML"`; it also dropped the active sort order | `templates/partials/cards.html` now contains only the cards and the next sentinel, and keeps the sort |
| Dead letters page answered HTTP 500 | The page failed as soon as it had a stuck article to show | The template called a `now()` helper that was never registered, and the article timestamp is a timezone-less column | A `now` global returns naive UTC, matching what SQLite returns for `db.DateTime`; the template normalises the timestamp before comparing |

The fourth row is the most expensive one to diagnose, because the server was
serving the correct CSS the whole time. The browser was not asking for it: the
service worker's cache-first strategy returned whatever the client had first
loaded, and the cache name never changed.

### Regression coverage

| Area | Module |
|---|---|
| Template existence, fragment/full-page split, `Vary`, Markdown rendering, no pipeline internals on the public index | `tests/test_public_page_contracts.py` |
| Markdown and HTML rendering, sanitization, paragraph structure, fallback bodies | `tests/test_markup_rendering.py` |
| Service worker version injection, network-first static fetch, no HTMX caching, asset revalidation | `tests/test_service_worker_cache.py` |
| Admin nav targets, endpoint namespaces, POST-only anchors, htmx bootstrap, dead letters | `tests/test_admin_navigation.py` |

`tests/test_public_page_contracts.py::TestTemplateReferences` asserts that
every template a route renders exists on disk. That single assertion covers
the class of defect that produced the HTTP 500 on the article route and the
HTTP 500 on the pipeline logs route.

---

## Defects found while rebuilding the page frame

A third pass, driven from the rendered site rather than from the source,
surfaced eleven more defects. Six were structural (the frame changed
between pages), three were visual (an invisible box, a stranded control, a
sliver of colour), one was a contract mismatch between a route and its
template, and one made every subsequent change look like it had not landed.

| Defect | Symptom | Root cause | Fix |
|---|---|---|---|
| The article page opened with 563px of blank space | The headline started far below the fold, above a large empty region | The detail fragment rendered a loading skeleton inside a `.htmx-indicator` wrapper. The skeleton ships *with the response*, so it arrived after the request it was meant to cover — it could never be seen, but at 476px tall it still reserved its box | The skeleton is removed: a placeholder that lives in the response cannot cover the request. `.htmx-indicator` now takes `display: none` at rest and `display: revert` while `htmx-request` is set |
| Only the index carried the sidebar | Navigating between the index, a topic tab and an article changed the whole page frame | `show_rail` was set on the index route only; the rail block in `base.html` was empty and every template had to include the rail itself | The rail is included by `base.html` and every public route sets `"show_rail": True` |
| The article page's header dropped the topic links | The header was visibly shorter on an article than on the feed | The article route did not pass `categories`, and the navigation renders the topic taxonomy from it | The article route passes `"categories": _get_categories()` |
| The tag page carried a second, different sidebar | The tag page showed a tag cloud beside the rail, so the frame was different again | The tag page had its own `.tag-layout` with a `.tag-sidebar` | The tag cloud moved into the rail as a third section; the tag page uses the standard frame |
| The subscribe form competed with the sidebar | The rail carried a subscribe form above the discovery links, and the topic header carried a second one | The form was placed in the rail when the rail was the index-only sidebar | The form lives in the footer, once, on every page |
| "What to watch" was hidden behind a disclosure | The most forward-looking part of every summary was collapsed behind a click | The condensed article rendered it as a `<details>` element | It is a plain section, like every other part of the summary |
| The admin dashboard's recent-articles table had five blank columns | The table rendered with an empty title, topic, score, impact and created column, and no error anywhere | The route selected `id, original_title, pipeline_status, source.name` while the template rendered `original_title`, `category`, `pipeline_status`, `selector_result.score`, `impact_score` and `created_at`. A column that is not selected renders empty rather than raising | The query selects every column the template renders, and the dashboard also links into the new per-article audit trail |
| A 3px sliver of accent colour ran along the top of every page | A blue line was visible across the top-left of the viewport, in every theme | The skip link was offset with `top: -40px`, but its own height was 43px, so 3px stayed on screen | The skip link is hidden with `transform: translateY(-100%)` |
| The sort control was stranded on a line of its own | The feed toolbar had a search field and the filter chips on the first row and the sort dropdown alone, half way down, on the second | The toolbar was a single wrapping flex row and the sort control was pushed to the end | The toolbar is a column: the search field and the sort control share the first row, the filter chips take the second. On a phone the sort control drops below the field so the placeholder is not cut short |
| Every template and CSS change looked like it had not landed | A changed page kept rendering the previous markup — including the previous inlined critical stylesheet — for up to five minutes | The rendered-document cache was enabled in the development configuration, and the cached document contains the inlined critical CSS | `RESPONSE_CACHE_ENABLED = False` in `DevelopmentConfig`; production keeps the cache |
| The admin subnav wrapped onto a second row | The admin header grew to three rows and pushed the page content down | `.admin-subnav` wrapped, and adding the pipeline-audit link made the row too long | The subnav scrolls horizontally on one row, like the primary navigation |

### Pipeline audit trail

The trend-memory page showed what the editor agent **remembered** between
runs. Nothing showed what the pipeline **did**. Two admin surfaces now
close that gap:

| Surface | Route | Content |
|---|---|---|
| Activity feed | `/admin/pipeline-audit` | Every stage the pipeline recorded, newest first, filterable by stage, level and article, with a per-stage activity summary and the operator action log |
| Per-article trail | `/admin/articles/<id>/audit` | The stage timeline of one article, the provenance the pipeline wrote onto the article row (selector verdict, writer model, impact, quality gate, degradations, retries, versions), and the version history |

`services/pipeline_audit.py` assembles both. It is a service layer module:
it imports models and the database extension, never Flask and never the
routes. The admin articles table, the dashboard's recent-articles table and
the activity feed all link into the per-article trail.

### Visual refresh

The visual identity keeps the themes and adds depth on top of them.

| Change | Detail |
|---|---|
| Page gradient | A soft wash across the top of the page, built from the active theme's own accent tokens. The canvas is `html { background: var(--bg-primary) }` and the gradient is painted on `body` with `background-color: transparent` |
| Translucent surfaces | The sticky header, the footer, the admin cards, the stat boxes, the subscribe box and the theme popover use derived glass tokens. The sticky header blurs what scrolls under it, so the feed glides beneath the bar |
| Derived tokens | `--surface-glass`, `--surface-glass-strong`, `--surface-glass-subtle`, `--surface-border` and the `--glow-*` tokens are defined once in `static/css/variables.css` with `color-mix()` over palette tokens, so they follow whichever theme is active |
| Prose measure | The prose blocks are capped at `72ch`; the 868px article column is about 110 characters per line without it |
| Mobile | The rail collapses to a single scrollable row of topic chips below 1024px; the feed toolbar stacks; the footer subscribe strip stays a single column |

The theme CSS output contract is unchanged: `to_css_variables()` still emits
a `:root` block of palette custom properties only, with no selectors and no
media queries. The translucency is derived from the palette in the shipped
stylesheet, not baked into the theme.

### A fourth pass: the hover, the background and the operator's settings

A fourth pass, driven from the operator's own use of the site, surfaced
eight more defects and three missing capabilities.

| Defect | Symptom | Root cause | Fix |
|---|---|---|---|
| Hovering an article card flickered | Moving the pointer over a headline made the card jump between two treatments mid-gesture | The card carried three competing hover rules: an accent bar along its top edge, a border colour that changed on hover, and a `.article-card:has(a:hover)` block that repainted the background, added a shadow and lifted the row by 2px | One treatment: the card changes the hairline under it, the headline handles its own colour and underline. The top bar is removed, the `:has(...)` rule is removed, and the transitions share a duration and a curve |
| The page background travelled with the content | The gradient sat at the top of the document and scrolled away | The background layers had no `background-attachment` | Every layer is `fixed`, so the gradient stays where the reader put it |
| There was no field for the background to stand against | The gradient was the page, so it had nothing to read as a shape | The page painted `--bg-primary` and nothing else | A single flat colour, `--bg-tint`, derived from the theme (`92%` of `--bg-primary` and `8%` of the theme's own text colour), is the bottom-most background layer. It is a whisper away from the theme's background and stands against the gradient |
| Boxes were opaque | The gradient was visible only in the gaps between cards | Only the sticky surfaces had been made translucent | The article summary, the related cards, the share card, the share dropdown, the toast, the bulk-action bar, the login box and the verification card all use a derived translucent surface |
| Admin links scrolled out of sight | "trend memory" and the settings link were unreachable without a horizontal scroll that had no visible scrollbar | The admin header put the primary nav, the secondary nav and the logout button on one row, and both nav rows scrolled horizontally | The header is a two-row grid: the primary sections on the first row, the remaining admin sections on the second. Both rows wrap instead of scrolling, so every section stays visible |
| The settings tables overflowed the viewport on a phone | The page scrolled sideways | The tables had no scroll container | Each table sits in an `.admin-table-wrapper`, as the other admin tables do |
| A providers file written by the CLI could not be read by the application | Every provider disappeared and the application failed to start with a `ValidationError` | The loader normalises the provider **list** into a mapping keyed by provider id, and the CLI wrote that mapping back out. The application reads a list | Both writers emit the list. The CLI converts the mapping back in `_commit_providers`; the admin panel writes the list directly |
| A hosted provider with no credential reported a green tick | The test button said "ok" for a provider that could not serve a request | The probe checked reachability only | The probe reports "no credential configured" for a hosted provider with no credential |

### Operator settings

| Capability | Surface | Where it is stored |
|---|---|---|
| Which provider and model each pipeline stage uses | `/admin/settings` → *pipeline stages* | `pipeline.yaml` |
| Which providers exist, which are enabled, which is the default, which models they offer | `/admin/settings` → *providers*, with a **test** button that probes the endpoint and lists its models | `providers.yaml` |
| A provider that needs no credential, running on this machine | A provider marked **local** may have an empty `api_key` and may point at a private address. The SSRF guard is relaxed for it, and only for it | `providers.yaml` |
| The name the site credits for its summaries | `/admin/settings` → *agent name*, site-wide and per topic | `topics.yaml` |

Every change goes through the configuration transaction engine, so it is
validated, backed up and reversible. The credential a provider uses is
never rendered on the page and never returned by the test endpoint.

The shipped `local` provider points at `http://127.0.0.1:1234/v1` with the
model `google/gemma-4-e2b` and is disabled by default.

### Regression coverage

| Area | Module |
|---|---|
| Invisible layout placeholders, the rail on every public page, the subscribe form in the footer, the disclosure removal, the toolbar, the prose measure, the derived tokens, the development cache | `tests/test_public_layout_contracts.py` |
| The pipeline audit service, the activity feed, the per-article trail, the admin links, the dashboard's audit and memory panels | `tests/test_admin_pipeline_audit.py` |
| The dashboard's recent-articles table: the query's column list and the rendered cells | `tests/test_admin_navigation.py` |
| The hover consolidation, the fixed background, the faint colour layer, the translucent surfaces, the two-row admin header | `tests/test_frontend_visual_contracts.py` |
| The settings service, the provider file shape, the local provider without a credential, the agent name, the settings routes, the CLI writing the same shape | `tests/test_admin_settings.py` |
| The provider chain surviving an unusable provider, a stage failure being recorded rather than raised, the reasoning-content fallback | `tests/test_provider_chain_resilience.py` |
| The provider probe proving the endpoint works, sending the provider's headers, reporting the configured model | `tests/test_provider_probe.py` |

Every guard was verified to fail against the pre-fix state by re-introducing
each defect one at a time and confirming that the corresponding test turns
red.

---

## Defects found while running the pipeline against the local model

A fourth pass, driven by running the pipeline end to end against a local
inference server, surfaced five defects. All of them made the pipeline look
*stalled* rather than broken, which is why they hid so well: the worker
received a task and never mentioned it again.

| Defect | Symptom | Root cause | Fix |
|---|---|---|---|
| One unusable fallback provider took the whole chain down | The pipeline produced no article at all, on any provider | `get_provider_chain()` yielded the primary and then walked the fallbacks. A fallback that could not be constructed — a missing credential — raised out of the generator, which discarded the primary that had already been yielded | A provider that fails to construct is skipped and logged, never fatal. The same applies to the primary |
| The chain reported an open circuit on every call | The worker log filled with "circuit open, trying fallbacks" while the primary was healthy | The warning sat outside the `if breaker.can_execute()` block, so it was logged unconditionally | The warning is logged only when the circuit is actually open |
| A provider-resolution failure left no trace | The article stayed in `pending` forever, with no pipeline log, no error and no metric | `run_stage()` resolved the provider chain **outside** the stage's try block, so the failure escaped the stage untouched | Provider resolution routes through `_handle_stage_exception`, which writes the pipeline log and the article error, or through `_handle_circuit_open_module`, which degrades the article to review |
| A reasoning model was treated as an empty response | A provider that had answered looked like it had returned nothing | `google/gemma-4-e2b` and `muse-spark-1.3-contributor` spend part of the token budget thinking and can leave `content` empty while the answer sits in `reasoning_content` | The OpenAI adapter falls back to `reasoning_content` when `content` is empty |
| The provider probe reported a green tick on a broken provider | The **test provider** button said "ok" for a provider that could not serve a request, and said "failed" for one that could | The probe only tried `GET /models` and treated a 404 as success, and it sent the credential but not the provider's own routing headers | The probe falls back to one minimal completion when `/models` answers 404 or 405, and sends the provider's declared headers. Success means the endpoint served a well-formed response |

### Provider verification

| Provider | Endpoint | Model | Result |
|---|---|---|---|
| `local` | `http://127.0.0.1:1234/v1` | `google/gemma-4-e2b`, `google/gemma-4-e4b` | Probe ok in 2ms, 4 chat models discovered (the embedding model is filtered out). A full article ran select → research → write → edit in 40s on e2b and in 59s on e4b, both `done` with no retries |
| `opencode` | `https://opencode.ai/inference/go/openai/v1` | `muse-spark-1.3-contributor` | Probe ok in 899ms, structured selection in 8.8s |

The local endpoint implements `response_format: {"type": "json_schema"}` with
`strict: true`, which is what the pipeline uses. It does **not** implement
`{"type": "json_object"}` — that answers HTTP 400. The gateway in front of
`opencode` does not implement `/models` at all and requires an
`x-opencode-session` routing header; the probe now proves that provider with
a completion and sends the header.

## Defects found while operating the admin panel

A fifth pass, driven by the operator using the admin panel to run the site
rather than to look at it, surfaced eight defects. They shared a shape: the
panel accepted the click, and then did something the operator could not see
or could not undo.

| Defect | Symptom | Root cause | Fix |
|---|---|---|---|
| Every form post on the admin panel failed | "trigger crawl now" answered `CSRF token missing`. The same failure hid behind newsletters, trend memory and topic notes | The CSRF guard read the token from the `X-CSRFToken` header only. An HTML form posts it in the `csrf_token` field and cannot send a custom header | The guard accepts the header, the form field or a JSON body. A form post is answered with a redirect and a flash message instead of a raw JSON body |
| Buttons rendered as bare text | The "trigger crawl now" button had no padding, no height and no radius | `.btn-primary` only sets the colours. The geometry lives in `.btn`, and the templates wrote `class="btn-primary"` without it | Every button in every template carries the base class. `.btn-link` was added, because a template used a class the stylesheet never defined |
| Saving a setting looked like ignoring the click | Every admin action redirected back with no sign of what had happened | The routes had always called `flash()`, but no template ever called `get_flashed_messages()` | `templates/base_admin.html` renders the flashes |
| The topics the site follows were not editable | The only way to add, rename or remove a topic was to edit `topics.yaml` in a text editor | The settings panel exposed the providers, the pipeline stages and the agent name, and nothing else | The panel lists every topic, with its name, description, colour, query and how many sources follow it. Topics can be added, changed and removed |
| Removing a topic broke the configuration | The validator rejected every source that followed the deleted topic | The removal only touched `topics.yaml`, and left the references in `sources.yaml` | The removal strips the topic from every source's include list in the same transaction, and reports which sources it touched |
| The pipeline schedule was not editable | The crawl interval could only be changed in `pipeline.yaml` | The panel had no schedule section | The panel exposes the crawl interval, the retry interval, the scheduled-publish interval, the auto-approve interval and the newsletter hour |
| There was no way to publish without a human | The review queue filled with articles nobody was going to read, and the site went quiet | `pipeline.review.auto_approve` did not exist. Every article the pipeline was unsure about waited for a person | Auto-review mode. The switch is on the panel, and it publishes an article the moment it reaches the review queue |
| A trend memory could never be read | The signal was clipped at 300 pixels behind an ellipsis | The cell itself carried the clipping | The cell shows a truncated preview, and a pulldown reveals the whole stored signal |

### Auto-review mode

Auto-review mode is the one setting with an outward-facing consequence, so
it is worth stating exactly what it does.

`pipeline.review.auto_approve` is **off** by default. A site that never asked
for autonomy does not get it. When it is on:

* An article the pipeline routes to review is approved and published
  immediately, exactly as a human approver would have done.
* The approval is the same transition the admin panel's "approve" button
  performs, so an auto-approved article and a human-approved one end up in
  the same state.
* The review dispatch is skipped, because the article was published rather
  than queued, and re-running the editor on a published article would edit
  it twice.
* A beat task drains the queue once a minute, which covers the articles that
  were already waiting when the switch was turned on.

A broken configuration fails **closed**: the articles wait for a human, which
is the safe direction.

### Admin panel verification

| Check | Result |
|---|---|
| Manual crawl from the admin panel | `pipeline_runs` row 79, `triggered_by: manual`, `status: completed` |
| Auto-review mode, inline path | An article routed to review through `tasks.pipeline._transition_article_status` was published on sight: `Article 71 approved (auto_review)`, status `done`, `published_at` set |
| Auto-review mode, beat path | Three articles waiting in the review queue were published by the beat task within one minute, all `done` with `published_at` set |
| Topics round trip | A topic added, renamed and removed through the panel, with the source references cleaned up |
| Schedule round trip | The crawl interval was changed to 17 and back, and survived the round trip |
| Auto-review switch round trip | Switched on and off, and the panel reported the state after a reload |
| Trend memory pulldown | 33 entries on the page; the summary shows 120 characters and the opened body shows the whole 777-character signal |
| Button geometry | The "trigger crawl now" button computes to `inline-flex`, 34px high, 4px radius |
| Browser journey | 27 checks, all passed (`/tmp/ainews_admin_journey.py`) |
| Ruff | 5 errors, the exact Release-5 baseline — no new findings |
| Mypy | Clean, 496 source files |

New test module: `tests/test_admin_settings_panel.py` (59 tests), auto-included
by CI (`.github/workflows/ci.yml` runs `pytest tests/`).

## The SQLite write lock

The sixth pass was driven by autonomy itself: with the pipeline running
unattended, a single slow model call stopped the whole site.

The symptom was not a slow page. It was a database that could no longer be
written to at all. Every admin action that saves a setting failed with
`sqlite3.OperationalError: database is locked`, and the health check reported
`database: ok` because reads were still fine — SQLite allows readers while a
writer holds the lock.

### What happened

`post_finalize_article()` set `published_at` and then asked the model for a
trend-memory proposal, committing only afterwards. The session had a pending
`UPDATE`, so the next autoflush took SQLite's single write lock — and the lock
was held for the whole duration of the model call.

The beat task that was running at the time had a 180-second hard limit. It
expired, Celery SIGKILLed the worker, and the worker died **holding the write
lock**. A killed process never rolls back, so the lock outlived the worker that
took it, and every other writer in the deployment failed from then on.

The stack was captured from a live hang:

```
httpcore/_backends/sync.py:128 in read
openai/_base_client.py:1297 in post
services/llm/openai.py:251 in _do_chat_with_schema
services/trend_memory.py:210 in _call_llm_for_memory
services/trend_memory.py:242 in propose_trend_memory
services/pipeline_degradation.py:249 in post_finalize_article
services/auto_review.py:160 in _post_finalize
services/auto_review.py:120 in publish_article
```

### The fix

| Change | Effect |
|---|---|
| `post_finalize_article()` commits the publication **before** any slow work | The write lock is released before the model is asked anything. A publication is durable even if the model never answers |
| The trend-memory proposal runs in its own task (`tasks/trend_memory.py::propose_trend_memory_for_article`, 900s soft / 960s hard) | The publication path never waits on a model, and a slow local model gets the time it needs instead of a 180-second wall |
| `propose_trend_memory()` reads its inputs into locals and commits **before** the model call | The model call runs with no open transaction at all, so it cannot hold the write lock |
| `propose_trend_memory()` catches every provider failure except `SoftTimeLimitExceeded` | A failed proposal is a missing insight, not an unpublished article |

The beat task now only publishes. The insight work is a separate, generous,
failure-tolerant step.

### Lock verification

| Check | Result |
|---|---|
| The model call runs with no open transaction | Asserted by `tests/test_publication_lock.py` — the session has no transaction during the call |
| The publication is durable while the model waits | Asserted by taking a rollback mid-request and finding the publication still committed |
| The publication is committed before the trend-memory dispatch | Asserted by ordering |
| The proposal has its own task with a generous limit | Asserted: 900s soft, 960s hard |
| The beat task makes no model call | Asserted |
| Live, after the fix | The beat fired at 15:38:08 and 15:39:08 without hanging. `propose_trend_memory_for_article` was received and ran as a separate task. No `TimeLimitExceeded`, no `database is locked` |
| A direct write while the pipeline ran | Completed in 0.003s |

New test module: `tests/test_publication_lock.py` (14 tests), auto-included by
CI (`.github/workflows/ci.yml` runs `pytest tests/`).

## The state machine dropped articles

The seventh pass came out of reading the live database rather than the code.
The pipeline was running, the beat task was firing on time, and the site was
serving articles — and yet **30 articles in the live database were dead**,
all with the same `last_error`:

```
Dead-lettered: stuck in 'pending' beyond 60 minutes
```

The cause was in `constants.py::VALID_TRANSITIONS`, the table that says which
pipeline status may follow which.

### A missing edge does not refuse a transition — it strands the article

`_transition_article_status` raises `InvalidStateTransitionError` when the
table forbids a transition. That raise happens **in the middle of a stage**,
so the article is left exactly where it was. It never advances, never reaches
a terminal state, and never logs an error that says what actually went wrong.
An hour later the retry task finds it, decides it is stuck, and dead-letters
it.

Three edges were missing, and all three are on the normal path of an
autonomous run:

| Edge | Performed by | What happened |
|---|---|---|
| `pending -> skipped` | `tasks/select.py` — the selector rejects the article | The single most common outcome of a crawl threw. Eight articles in the live database hit it |
| `writing -> review` | `tasks/write.py` — the writer's quality gate | A degenerate draft could not be routed to review |
| `pending -> failed` | `tasks/pipeline.py` — the pipeline timeout | A pending article that timed out could not be failed |

### A published article has to stay published

The editor can be re-dispatched onto an article that has already been
finalized. Before auto-review mode, the transition table refused `done ->
review` and protected the article — four live articles still carry
`last_error: Invalid pipeline transition for article N: done -> review`, and
all four are published and intact.

Auto-review mode short-circuits every transition *to* review and hands it to
`route_to_review`, which does not validate. Without a guard, a re-dispatched
editor would have dragged a live article back into the review queue, or
published it a second time and run the post-publication work twice.

`services/auto_review.py::route_to_review` now refuses to touch an article
that is already `done`.

### The rule

**Every edge in `VALID_TRANSITIONS` has to match a transition the pipeline
actually performs.** When a `_transition_article_status` call is added, the
edge has to be added in the same change.

### Verification

| Check | Result |
|---|---|
| The three edges are allowed | Asserted by `tests/test_pipeline_transitions.py` |
| The terminal states stay terminal | `done -> review` and `done -> failed` are still refused |
| A published article is not queued | Asserted |
| A published article is not published a second time | Asserted |
| The admin API's manual status change | Uses the same table, so the new edges are valid there too |
| Live, against the running worker | A pending article with no real content was handed to the selector. It reached `skipped` with `last_error` empty — the transition that used to raise `InvalidStateTransitionError` and strand the article for an hour |
| Test suite | 5,040 passed, 6 skipped, 0 failed |
| Ruff | 5 errors, the exact Release-5 baseline — no new findings |
| Mypy | Clean, 496 source files |

New test module: `tests/test_pipeline_transitions.py` (16 tests),
auto-included by CI (`.github/workflows/ci.yml` runs `pytest tests/`).

## Residual risk

| Item | Type | Why it is accepted |
|------|------|--------------------|
| `static/js/bundle.min.js` is a dead artifact | accepted limitation | It is referenced by no template; the assertion that it stays unreferenced prevents it from being loaded by accident, and its removal is a packaging decision outside this milestone |
| The admin interface is not redesigned | accepted limitation | Out of scope for the public-site milestone. The admin templates share the cascade repair but keep their own layout |
| The theme preference is browser-local | accepted limitation | The browser-local preference model is the intended design; multi-device sync is a separate requirement |
| Pipeline state is no longer shown on the public index | accepted limitation | It was relocated to the admin area, where the information belongs. The rail now shows only the topic taxonomy and the editor's impact ranking |
| Themes are parsed once per process | accepted limitation | Restart-based theme semantics are documented; a live file watcher would need its own invalidation contract |
| The rendered-document cache holds full HTML for five minutes | accepted limitation | It is what makes the public site cheap to serve. It is now scoped per database, invalidated across workers within seconds, disabled in the development configuration and disabled entirely in the testing configuration |
| The cached document embeds the inlined critical stylesheet | accepted limitation | A CSS change therefore reaches cached pages only after the cache entry expires. Production accepts the five minute window; development runs with the cache disabled |
| Surfaces use `color-mix()` for their translucency | accepted limitation | A browser without `color-mix()` support drops the declaration and falls back to the opaque palette colour. The layout is unaffected, the surfaces are simply not translucent |
| The review → edit re-dispatch loop is unbounded in manual mode | known defect, not fixed | `tasks/AGENTS.override.md` mandates that the edit stage calls `_dispatch_next(..., next_status=REVIEW)` when it routes to review, and the quality gate fails the same way every time — article 66 logged "Quality gate requires review" eight times in four minutes. The loop is dead in auto-review mode (the `_dispatch_next` skip): zero `edit_article` dispatches and zero pipeline log rows for article 66 after 15:30. A bounded fix using the existing `MAX_TOTAL_RETRIES` budget was designed but not applied, because changing the mandated dispatch is the operator's call. `route_to_review` refusing to touch a published article now stops the loop from damaging anything |

---

## Deferred items

| Item | Reason | Revisit when |
|------|--------|--------------|
| Admin interface redesign | Out of scope for the public-site milestone; the admin templates share the cascade repair but have their own layout | A separate milestone |
| Per-user server-side theme persistence | The browser-local preference model is the intended design | If multi-device sync becomes a requirement |
| Real-time pipeline status in the admin dashboard | Requires a push channel or polling | When the feed volume justifies it |
| Live theme reload without restart | The current semantics are documented as restart-based | If custom themes become commonly edited |
| `static/js/bundle.min.js` disposition | Needs confirmation of its packaging purpose | Before the next release |
