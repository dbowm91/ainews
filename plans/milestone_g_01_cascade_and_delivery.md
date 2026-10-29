# Milestone G1 — Cascade and Delivery Correctness

## Purpose

Close the five blocking rendering defects and the four blocking functional defects identified in `docs/ui-review-2026-10.md`.

This phase restores the site's ability to render at all. It deliberately contains **no cosmetic work**: every change here either repairs the cascade contract, repairs a broken endpoint, or adds the regression test that proves the repair. Visual redesign is deferred to `plans/milestone_g_03_visual_identity.md` because the G1 changes alter the rendered result of every component and would make cosmetic measurements taken beforehand meaningless.

## Current state

The public site loads and returns `200` on feed, topic and tag routes. The article route returns `500`. The theming subsystem runs but has no visible effect. Mobile navigation does not collapse.

Four independent defects combine to produce this state. They must be fixed in the order given, because each one masks the symptoms of the next.

| # | Defect | Layer | Symptom |
|---|---|---|---|
| D1 | Critical CSS generator drops 3 closing braces | Build | 23 rules silently discarded by the parser |
| D2 | Inline critical sheet is outside the cascade layer system | Cascade | Every component's padding/margin computes to `0px`; component link colours overridden |
| D3 | Theme stylesheet loses to the fallback palette | Cascade order | All 48 themes render identically |
| D4 | Cached related-article query is missing `.unique()` | Application | `/article/<id>` returns `500` |

D1 and D2 are both required for the mobile collapse to work. D1 removes the `@media (max-width: 640px)` block entirely; D2 independently makes the navigation overflow because the header's own padding is zeroed.

## Outcomes

At completion:

1. `scripts/build_critical_css.py` produces a brace-balanced stylesheet, and a build-time assertion prevents regression.
2. The inline critical stylesheet participates in the declared cascade layer order.
3. The active theme's palette is the palette the browser paints.
4. `/article/<id>` returns `200` on both cache-miss and cache-hit paths.
5. Browser navigations to error paths receive the styled HTML error pages.
6. The service worker registers successfully with no console error.
7. HTMX indicators are visible only while a request is in flight.
8. `top stories` renders without an empty column.
9. Every repair has a regression test that observes the rendered result, not the generated text.

---

# Workstream A — Repair the critical CSS generator

## A1. Confirm and characterise the defect

`scripts/build_critical_css.py:80-94`:

```python
def build_critical_css() -> str:
    css = CRITICAL_SRC.read_text()
    minified = minify_css(css)
    lines = minified.split("}")
    formatted_lines = []
    for part in lines:
        part = part.strip()
        if not part: continue
        if part.endswith("{"):
            formatted_lines.append(part + "\n")
        else:
            formatted_lines.append(part + " }\n")
    return "".join(formatted_lines).strip() + "\n"
```

`minify_css()` output is balanced (62 `{` / 62 `}`). The formatter then splits on `}` and re-emits exactly one `}` per part, so every adjacent `}}` in the minified text loses one brace. The source contains exactly three such sequences — the closings of `@keyframes progress-bar`, `@media (max-width: 640px)` and `@media (prefers-reduced-motion: reduce)`.

The committed `templates/partials/critical_css.html` is byte-identical to a fresh regeneration, so the file is current with the source and **the generator is the defect**.

## A2. Replace the formatter

Replace the split/re-join with a brace-aware formatter that preserves nesting depth, or emit the minified text directly with only the whitespace trimming that is actually wanted.

Requirements:

- Output must have identical brace counts to the input.
- Output must preserve rule order and selector text exactly.
- Output must remain valid CSS when the input is valid.
- Output must not introduce `}` characters that were not in the source.

## A3. Add a build-time assertion

The generator must refuse to write an unbalanced stylesheet. Add a check that raises on brace-count mismatch, and a check that the number of top-level rules in the output equals the number in the minified input.

## A4. Add a regression test

New test module `tests/test_critical_css_build.py`:

- `test_generated_critical_css_is_brace_balanced` — assert `{` count equals `}` count for the generated output.
- `test_generated_critical_css_matches_source_rule_count` — parse both `static/css/critical.css` and the generated partial and assert equal top-level rule counts.
- `test_generated_critical_css_contains_mobile_media_block` — assert the `@media (max-width: 640px)` block is present and contains `.nav-links` with `display:none`.
- `test_generated_critical_css_contains_reduced_motion_block` — assert the `prefers-reduced-motion` block is present.
- `test_build_script_is_idempotent` — run the generator into a temporary path and assert the result matches the committed partial, so a stale committed file is detected.

## A5. Regenerate and verify

Regenerate the partial, then confirm in a browser that the inline stylesheet's CSSOM now contains every rule the source declares, and that the `@media (max-width: 640px)` block takes effect.

---

# Workstream B — Restore the cascade contract

## B1. State the invariant

The application has two style sources:

1. `static/css/style.css` — imports the modules into named cascade layers.
2. The inline `<style>` in `templates/base.html` — the critical stylesheet.

The invariant must be: **every rule the application ships participates in one cascade**, so that the reset and the component rules resolve by specificity and source order as written.

Today the inline sheet is unlayered. Per the CSS Cascade specification, unlayered declarations outrank *all* layered declarations regardless of specificity. The critical sheet's universal reset therefore beats every `.component { padding: … }` rule in `components.css`, `articles.css` and `pages.css`.

## B2. Bring the inline sheet into the layer order

`static/css/style.css` already declares the layer order:

```css
@layer reset, variables, layout, components, pages, utilities;
```

The critical sheet carries reset and base-element rules (`*`, `html`, `body`, `a`, `.skip-link`, `.sr-only`, the site header/nav/footer, the scrollbar, `::selection`) and must sit in the `reset` layer so that `layout`, `components`, `pages` and `utilities` can override it.

Implementation options, in order of preference:

1. **Preferred** — wrap the inline critical content in `@layer reset { … }`. This requires no change to `style.css` and matches the existing layer names.
2. **Alternative** — move the critical rules into `static/css/base.css` (already imported into `layer(reset)`) and inline only the `@import` of that module. This removes the duplication between `critical.css` and `base.css` entirely and is the cleaner end state, but it enlarges the diff and changes the asset-build contract, so it should be a separate commit.

Note that the inline `@import url("/static/css/variables.css")` inside the critical sheet must be handled explicitly under either option — see Workstream C.

## B3. Remove the duplicated universal reset

`static/css/critical.css:6-10` duplicates the `*` reset. `static/css/base.css` already exists and is imported into `layer(reset)` by `style.css`. Keep one authoritative copy.

If option 2 in B2 is taken, `static/css/critical.css` becomes a thin module and `base.css` absorbs the rest.

## B4. Verify the rendered result

In a browser, assert that these elements have their authored spacing:

| Selector | Authored | Expected computed |
|---|---|---|
| `.article-card` padding | `1rem 1.15rem` | `16px 18.4px` |
| `.article-card` margin-bottom | `0.75rem` | `12px` |
| `.feed-header` padding | `1rem` | `16px` |
| `.filter-btn` padding | `var(--space-2) var(--space-4)` | `4px 8px` |
| `.tag-pill` padding | `var(--space-1) var(--space-4)` | `1.6px 5.6px` |
| `.category-badge` padding | `0.1rem 0.4rem` | `1.6px 6.4px` |

And that `.card-title a` computes to `var(--text-primary)` rather than `var(--accent)` — the unlayered `a { color: var(--accent) }` must no longer outrank the component rule.

## B5. Add a regression test

New test module `tests/test_cascade_layers.py`:

- `test_critical_stylesheet_is_layered` — assert the inline critical content is wrapped in a declared layer, or that it contains no rules at all (option 2 in B2).
- `test_no_unlayered_reset_outranks_components` — static assertion that the shipped critical rules and the component modules declare a consistent cascade order.
- `test_base_reset_and_critical_reset_are_not_duplicated` — assert the `*` reset appears in exactly one shipped source.

These are static guards. The rendered assertions belong in the browser suite (Workstream H).

---

# Workstream C — Restore theme precedence

## C1. Characterise the precedence failure

Three rules define the fallback palette, and the theme sheet is a fourth:

| Source | Selector | Layer | Position |
|---|---|---|---|
| `style.css` → `variables.css` | `:root` | `variables` | early |
| `style.css` → `variables.css` | `[data-theme="light"]` | `variables` | early |
| `static/css/critical.css` `@import` → `variables.css` | `:root`, `[data-theme="light"]` | **unlayered** | after the theme link |
| `/assets/themes/<id>.css` | `:root` | unlayered | before the inline critical sheet |

The inline critical sheet's unlayered copy of `variables.css` outranks the theme sheet's unlayered `:root` by source order, and `[data-theme="light"]` ties the theme's `:root` on specificity while also being later. Both comparisons resolve in favour of the fallback palette.

## C2. Decide the precedence contract

The theme contract in `docs/halloy-theme-contract.md` requires the generated CSS to be a `:root`-only palette block. **That contract must not change.** Precedence is fixed by ordering, not by altering the emitted selector.

Target precedence, from strongest to weakest:

1. the active theme's `:root` palette;
2. the fallback palette in `variables.css`;
3. nothing else may define a palette token.

## C3. Implement

Two changes are required together:

1. **The critical stylesheet must not define palette tokens.** Remove the `@import url("/static/css/variables.css")` from `static/css/critical.css`. `style.css` already imports `variables.css` into `layer(variables)` and remains the single source of the fallback palette. The critical sheet should reference the tokens, not define them.
   - This also resolves the origin defect: the previous relative `@import "./variables.css"` resolved against the *page* URL (`/variables.css`), which returns `404`, and the recent change to an absolute URL made the import succeed and thereby activated the conflict. Removing the import removes the ambiguity permanently.
2. **The theme stylesheet must load after the fallback palette.** In `templates/base.html`, the theme `<link>` must be positioned after the element that carries the fallback palette. `static/js/theme.js` replaces the theme link in place (`insertBefore(c, v.nextSibling)`), so the initial markup position determines the final position — the link must be moved to after the application stylesheet's layer-resolved content in the cascade, not merely reordered relative to the inline sheet.

The precise arrangement must satisfy: theme `:root` beats `variables.css` `:root` and `[data-theme="light"]`. Because `:root` and `[data-theme="light"]` have equal specificity `(0,1,0)`, this requires the theme sheet to be **later in document order** than the sheet that carries `variables.css`.

Concretely: the theme `<link>` must follow the application stylesheet in document order, and the application stylesheet must not be preceded by any unlayered palette definition.

## C4. Verify

In a browser:

| Assertion | Before | After |
|---|---|---|
| `--bg-primary` for `catppuccin-latte` | `#ffffff` | `#dce0e8` (the theme's declared value) |
| `document.body` background | `rgb(255,255,255)` | `rgb(220,224,232)` |
| `--bg-primary` after `window.AinewsTheme.activate('catppuccin-mocha')` | unchanged | the mocha value |

Also verify with `data-theme="light"` applied, to confirm the theme still wins against the `[data-theme="light"]` block.

## C5. Add a regression test

New test module `tests/test_theme_precedence.py`:

- `test_critical_css_does_not_define_palette_tokens` — assert `static/css/critical.css` contains no `--bg-primary`, `--text-primary`, `--accent` or any other palette token definition.
- `test_variables_css_is_defined_once` — assert the palette token block exists in exactly one shipped source.
- `test_theme_link_follows_application_stylesheet` — assert the DOM order in `templates/base.html` places the theme stylesheet after the sheet that carries the fallback palette.

---

# Workstream D — Restore the article page

## D1. Add the missing `.unique()`

`services/related.py:35-43`:

```python
articles = (
    db.session.execute(
        select(Article)
        .options(joinedload(Article.tags), joinedload(Article.source))
        .where(Article.id.in_(article_ids))
    )
    .unique()          # <-- add
    .scalars()
    .all()
)
```

This matches the two sibling call sites at `services/related.py:104` and `services/related.py:187`.

## D2. Confirm the failure mode is closed

The defect only manifests on a **cache hit**. Verify both paths:

1. Request `/article/<id>` with an empty response cache → `200`.
2. Request `/article/<id>` again with the cache warm → `200`.
3. Confirm `services/related.py` is no longer in the traceback of any failing request.

Note that the response cache is keyed `pub:related:{article_id}` with a 600s TTL, so the second request in a test must target the same article within the TTL.

## D3. Audit for the same pattern elsewhere

Search the repository for `joinedload` on a collection relationship without a following `.unique()`:

- `routes/admin/metrics.py:38,52,66`
- `routes/admin/newsletters.py:245`
- `routes/admin/review.py:28-30`
- `routes/admin/dashboard.py:32,65`
- `routes/admin/api/articles.py:110,531`
- `routes/admin/articles.py:109`
- `routes/public/links.py:42-45`

`routes/public/links.py:42-45` uses `Article.query.options(...).get_or_404(...)`, which resolves the entity directly and does not require `.unique()` — confirmed by direct execution. The others must each be confirmed either way. Any site that iterates a `Result` with a collection eager load and no `.unique()` is a latent `500`.

## D4. Add a regression test

Extend `tests/test_routes.py`:

- `test_article_detail_returns_200` — asserts `200` and that the headline appears in the response body.
- `test_article_detail_returns_200_on_cache_hit` — requests the same article twice and asserts `200` on the second, with the related-articles cache populated.
- `test_article_detail_with_related_articles` — seeds a second article sharing a tag so the related path is exercised.

---

# Workstream E — Restore HTML error pages

## E1. Characterise the negotiation defect

`app.py:222-228`:

```python
def _wants_json() -> bool:
    return (
        request.path.startswith("/api/v1/")
        or request.is_json
        or "application/json" in request.accept_mimetypes
    )
```

Werkzeug's `MIMEAccept` treats a wildcard `*/*` as matching `application/json`. Every Chrome navigation sends `Accept: text/html,…,*/*;q=0.8`, so `_wants_json()` returns `True` for every browser page view.

Verified:

| Accept header | Response |
|---|---|
| `text/html` | styled `templates/errors/404.html` |
| realistic Chrome navigation header | `{"error": "Not found"}` |

`templates/errors/404.html` and `templates/errors/500.html` are therefore unreachable from a browser.

## E2. Fix the negotiation

Negotiate on the *best* match rather than on membership:

```python
request.accept_mimetypes.best_match(["text/html", "application/json"]) == "application/json"
```

The `/api/v1/` prefix rule and `request.is_json` must be preserved so API clients are unaffected.

## E3. Check the debugger exposure separately

The `500` response rendered a full Werkzeug debugger page with absolute server paths. The debugger is enabled by the development configuration used on `127.0.0.1:49300`. Confirm that:

- the production configuration (`config.py`, `ProductionConfig`) never enables the debugger;
- any deployment that binds beyond loopback cannot serve debugger tracebacks.

This is a configuration invariant, not a code change, unless the review shows the debugger can be enabled in production.

## E4. Add a regression test

Extend `tests/test_routes.py`:

- `test_404_returns_html_for_browser_accept` — send a realistic browser `Accept` header and assert the response is `text/html` and contains the styled error page's markup.
- `test_404_returns_json_for_api_path` — assert `/api/v1/...` still receives JSON.
- `test_500_returns_html_for_browser_accept` — force an error and assert HTML.

---

# Workstream F — Correct the service worker registration

## F1. Characterise

`static/js/app.js:408`:

```js
navigator.serviceWorker.register('/static/service-worker.js', {scope: '/'}).catch(function() {});
```

The script is served from `/static/`, so its maximum permitted scope is `/static/`. Requesting `/` is rejected and the failure is swallowed by the empty `.catch()`.

Every public page therefore logs:

```
The path of the provided scope ('/') is not under the max scope allowed ('/static/').
```

## F2. Fix

Either:

- register with `{scope: '/static/'}` and keep the app shell out of the offline scope; or
- serve the worker from the site root and set `Service-Worker-Allowed: /`.

The first option is smaller and does not change the asset layout. It must be reconciled with what `static/service-worker.js` actually caches — if the worker precaches application routes, its scope must cover them.

## F3. Make the failure visible

Replace the empty `.catch()` with a handler that logs a warning. A silently failing service worker is what allowed this defect to persist.

## F4. Add a regression test

- `tests/test_service_worker_registration.py` — assert the registration scope is one the script path permits, and that the error handler is not a no-op.

Also remove the "Service Worker" entry from the benign-console-error whitelist in `tests/test_theme_browser_smoke.py:159-162`, so the console error becomes a test failure.

---

# Workstream G — Correct the indicator and grid defects

## G1. Stop the spinner animation from overriding the hidden state

`static/css/layout.css:3-5`:

```css
.htmx-indicator.spinner {
  animation: pulse 1.5s ease-in-out infinite;
}
```

`@keyframes pulse` animates `opacity` between `0.4` and `1`. A CSS animation overrides the base `opacity` declaration, so the `opacity: 0` that hides the indicator has no effect. `#search-spinner` and `#subscribe-spinner` are therefore visible at rest on every page.

Fix by animating a property that does not compete with the visibility state — a `transform` or a custom property — or by scoping the animation to `.htmx-request .htmx-indicator.spinner` so it only runs while a request is in flight.

Note that the `.htmx-indicator { opacity: 0 }` rule in `static/css/critical.css:193` is currently dropped by the Workstream A defect. After A is fixed it will apply again; the animation fix is still required because animations outrank normal declarations.

## G2. Replace the fixed three-column `top stories` grid

`static/css/articles.css:1133-1137`:

```css
.top-impact-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
}
```

With fewer than three stories the remaining columns are empty, leaving a ~270px void inside the panel.

Change to an intrinsic track, `repeat(auto-fit, minmax(<min>, 1fr))`, or render only as many columns as there are items. The `max-width: 640px` override at `static/css/articles.css:1187` must continue to produce a single column.

## G3. Add a regression test

- `tests/test_ui_static_contracts.py` — assert the spinner animation does not target `opacity`; assert `.top-impact-grid` uses an intrinsic track; assert the `top stories` panel contains no empty column when fewer than three stories are present.

---

# Workstream H — Browser-level regression coverage

## H1. Why browser-level assertions are required

The existing 685+ theme tests assert on the *text* of generated CSS. Every defect in this phase passed them. The assertions added here must observe the *rendered* result.

The harness in `tests/test_theme_browser_smoke.py` already provides a background Flask server fixture, a `browser_context_args` viewport override and a console-error guard. Extend it rather than building a second harness.

## H2. Assertions to add

New test module `tests/test_frontend_rendering_browser.py`, marked `@pytest.mark.browser`:

| Test | Assertion |
|---|---|
| `test_article_page_renders` | `GET /article/<id>` → `200`, headline present |
| `test_theme_changes_palette` | `--bg-primary` differs before and after `window.AinewsTheme.activate(...)` and equals the theme's declared value |
| `test_components_have_authored_spacing` | `.article-card` padding and margin are non-zero and match the authored values |
| `test_no_horizontal_overflow_at_viewports` | `scrollWidth <= clientWidth` at 375, 390, 768, 1280, 1440 |
| `test_mobile_nav_toggle_visible_and_collapses` | at 390 px the toggle is visible, and activating it collapses the links |
| `test_404_returns_html` | browser navigation to an unknown path returns the styled error page |
| `test_no_service_worker_console_error` | no scope error in the console |
| `test_no_htmx_indicator_visible_at_rest` | indicator elements compute to zero opacity before any request |
| `test_no_unexpected_console_errors` | extend the existing guard; remove the service-worker exemption |

## H3. CI wiring

Add a `frontend-rendering` job to `.github/workflows/ci.yml`, modelled on the existing `theme-browser-smoke` job:

```yaml
  frontend-rendering:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --frozen --all-extras
      - run: .venv/bin/playwright install --with-deps chromium
      - run: .venv/bin/python -m pytest tests/test_frontend_rendering_browser.py -v --timeout=180
```

Alternatively, fold the new module into the existing `theme-browser-smoke` job if the runtime budget allows.

---

# Acceptance criteria

- [ ] `scripts/build_critical_css.py` emits a brace-balanced stylesheet and refuses to write an unbalanced one.
- [ ] `templates/partials/critical_css.html` is regenerated and committed.
- [ ] The inline critical stylesheet participates in the declared cascade layer order.
- [ ] `static/css/critical.css` defines no palette tokens.
- [ ] The active theme's palette is the palette the browser paints, for dark and light.
- [ ] `GET /article/<id>` returns `200` on the cache-hit path.
- [ ] A browser navigation to an unknown path returns the styled HTML error page.
- [ ] The service worker registers without a console error.
- [ ] HTMX indicators are hidden at rest.
- [ ] `top stories` renders no empty column.
- [ ] No horizontal overflow at 375, 390, 768, 1280, 1440 px.
- [ ] The mobile navigation toggle is visible and functional at 390 px.
- [ ] The new browser assertions and the build-time assertion are in CI.
- [ ] `ruff check` and `mypy` are clean for all changed files.
- [ ] The full test suite passes.

# Risk and rollback

| Risk | Mitigation |
|---|---|
| Moving the theme link changes the cascade for every theme | Verify in a browser against at least one dark and one light bundled theme before merging |
| Layering the critical sheet changes element rendering across all pages | Screenshot the feed, article, topic, tag, 404 and admin-login pages before and after, and compare |
| Regenerating the critical partial produces a large diff | Review the diff for rule-count parity; the byte size should change only by the whitespace difference |
| The `.unique()` change alters related-article ordering | `unique()` preserves row order; confirm the related list is unchanged in the rendered page |
| Removing the palette from the critical sheet causes a flash of unstyled content | Verify first paint in the browser; if the flash appears, keep the token definitions in `layer(variables)` rather than unlayered |

Each workstream is independently revertable. No workstream requires a data migration, a schema change or a configuration change.
