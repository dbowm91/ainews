# Milestone G Overview: Frontend Rendering Correctness and Visual Identity

## Purpose

Milestone G closes the frontend rendering defects found in the 2026-10-28 UI review and then rebuilds the public site's visual identity so it reads as a technical AI publication rather than an unstyled debug page.

The work is corrective first and cosmetic second. Three structural CSS defects currently disable most of the design system, and two live functional bugs break the article page and the error pages. Cosmetic work performed before the corrective work would be silently cancelled out by a reset that deletes every component's spacing.

Source review and measurements: `docs/ui-review-2026-10.md`.

## Why this milestone is first

The article detail page — the single most important page on a news site — returns **HTTP 500** with a full Werkzeug debugger traceback containing absolute server paths. Every reader who clicks a headline currently lands on a stack trace instead of the article.

The theme subsystem is inert. All 48 bundled themes render the same hardcoded fallback palette, so the theme selector, the cross-tab preference sync, the metadata endpoint and the whole `services/themes/` package have no effect on screen. The repo carries 685+ theme tests, all passing, because they assert on the *text* of the generated CSS rather than on the *cascade outcome*.

Mobile is unusable. At a 390px viewport the document is 859px wide, the hamburger button never appears, and the navigation never collapses.

These are release blockers for a public launch, not polish items.

## Current state

Measured in a real Chromium browser against the running application on `127.0.0.1:49300`.

### Cascade state

| Fact | Measurement |
|---|---|
| Critical CSS braces | `static/css/critical.css` = 62 `{` / 62 `}` (balanced); `templates/partials/critical_css.html` = 62 `{` / 59 `}` (3 lost) |
| Rules Chrome actually parses | The inline critical sheet's CSSOM stops at `@keyframes progress-bar`; 23 later rules are dropped |
| Layering | `style.css` declares `@layer reset, variables, layout, components, pages, utilities`; the critical sheet is inlined **outside any layer** |
| Cascade result | Unlayered `* { margin: 0; padding: 0 }` outranks every layered `.foo { padding: … }` |
| Computed spacing | `.article-card` padding `0px`, margin-bottom `0px`; `.feed-header` `0px`; `.filter-btn` `0px`; `.tag-pill` `0px`; `.subscribe-btn` `0px` |
| Theme precedence | Theme sheet declares `--bg-primary: #dce0e8`; page computes `#ffffff` |

### Functional state

| Endpoint | Result |
|---|---|
| `GET /article/<id>` | **HTTP 500** — `InvalidRequestError: The unique() method must be invoked on this Result…` |
| `GET /nonexistent` (browser Accept header) | Raw JSON `{"error": "Not found"}`; `templates/errors/404.html` unreachable from a browser |
| Service worker | Registration rejected on every page load: scope `/` is not under the max scope `/static/` |
| Overflow at 375 / 390 / 583 / 768 | `scrollWidth` exceeds `clientWidth` by 422 / 469 / 225 / 82 px |

### Cause of the article 500

`services/related.py:35-43`, the *cache-hit* branch, is missing `.unique()`:

```python
articles = (
    db.session.execute(
        select(Article)
        .options(joinedload(Article.tags), joinedload(Article.source))
        .where(Article.id.in_(article_ids))
    )
    .scalars()      # <-- .unique() missing
    .all()
)
```

`Article.tags` is a collection, so `joinedload` on it requires `.unique()`. The two sibling query sites in the same module — `find_related_articles()` at `services/related.py:104` and `find_related_articles_dicts()` at `services/related.py:187` — both call it. The failure looks intermittent because the cache-miss path works and populates the cache; every subsequent request takes the broken branch.

## Primary affected areas

- `scripts/build_critical_css.py` — critical CSS generator
- `static/css/critical.css`, `static/css/style.css`, `static/css/layout.css`, `static/css/articles.css`, `static/css/components.css`, `static/css/variables.css`
- `templates/base.html`, `templates/partials/critical_css.html`, `templates/partials/feed.html`, `templates/partials/article_card.html`, `templates/partials/subscribe_box.html`, `templates/errors/404.html`, `templates/errors/500.html`
- `services/related.py` — related-article lookup
- `app.py` — `_wants_json()` and the error handlers
- `static/js/app.js` — service worker registration
- `services/themes/translate.py` — contrast validation coverage
- `tests/`, `.github/workflows/ci.yml`, `docs/frontend.md`

## Workstreams

### G1 — Cascade and delivery correctness

Goal: Make the critical stylesheet well-formed, put it inside the same cascade as the application stylesheet, restore theme precedence, and repair the article page, error pages, and service worker.

Core tasks:

1. Replace the brace-dropping formatter in `scripts/build_critical_css.py` and regenerate the partial.
2. Move the inline critical sheet into `@layer(reset)` so it participates in the declared layer order.
3. Make the theme stylesheet win over the fallback palette, without changing the `:root`-only theme output contract.
4. Add `.unique()` to the cached related-article query.
5. Fix `_wants_json()` so browser navigations receive HTML error pages.
6. Correct the service worker registration scope.
7. Stop the indicator animation from overriding the hidden state.
8. Replace the fixed three-column `top stories` grid with an intrinsic one.

Detailed plan: `plans/milestone_g_01_cascade_and_delivery.md`.

### G2 — Interaction and accessibility correctness

Goal: Restore the accessibility guarantees the codebase already claims but does not currently deliver, and close the measured contrast and target-size gaps.

Core tasks:

1. Extend theme contrast validation to `--text-secondary`, `--text-muted` and `--accent` against the surfaces they are used on.
2. Correct the failing contrast pairs in the shipped fallback palette.
3. Enforce minimum target sizes on pointer-fine devices, not only coarse pointers.
4. Replace the ARIA tab misuse on the category filter with a correct navigation pattern.
5. Restore the dropped `prefers-reduced-motion` and `prefers-contrast` handling.
6. Close the nine minor defects: duplicated rules, clipped and invisible controls, duplicated `aria-label`, missing `h1`.

Detailed plan: `plans/milestone_g_02_interaction_and_accessibility.md`.

### G3 — Visual identity for a technical AI publication

Goal: Rebuild the public site's visual language once the cascade is trustworthy, using the design direction in `docs/ui-review-2026-10.md` §D.

Core tasks:

1. Establish the editorial type hierarchy (headline / deck / meta / badge tiers).
2. Apply accent discipline — accent reserved for interactive and active states.
3. Introduce a two-column layout at wide viewports with a left rail carrying live pipeline provenance.
4. Replace the boxed card treatment with hairline-divided editorial rows.
5. Rebuild the feed toolbar as a single row.
6. Restructure `top stories` as a lead plus two secondary items.
7. Design a dedicated dark surface ramp instead of borrowing GitHub's fallback.
8. Surface the agentic pipeline — stage, model, quality score — as first-class metadata.

Detailed plan: `plans/milestone_g_03_visual_identity.md`.

### G4 — Closure and verification

Goal: Prove the milestone with browser-level assertions rather than static contract checks, and produce an inspectable closure record.

Core tasks:

1. Add the browser assertions that would have caught the original defects.
2. Extend CI with a rendering-gate job.
3. Produce `docs/frontend-rendering-closure.md` with the closure matrix.
4. Reconcile `docs/frontend.md` and the asset rebuild workflow.

Detailed plan: `plans/milestone_g_closure_pass.md`.

## Exit criteria

- `GET /article/<id>` returns `200` and renders the article headline, for both cache-miss and cache-hit requests.
- The generated critical stylesheet is brace-balanced and its parsed rule count equals the source rule count.
- `getComputedStyle(document.documentElement).getPropertyValue('--bg-primary')` changes when the active theme changes, and equals the theme's declared value.
- `getComputedStyle(document.querySelector('.article-card')).padding` is non-zero, and its `margin-bottom` is non-zero.
- `document.documentElement.scrollWidth <= clientWidth` at 375, 390, 768, 1280 and 1440 px.
- The mobile navigation toggle is visible and functional at 390 px.
- A browser navigation to an unknown path renders `templates/errors/404.html`.
- The service worker registers without a console error.
- No unexpected console errors on any public page.
- All WCAG AA contrast pairs used in the public UI pass at their rendered size.
- The public site is delivered through one stylesheet path with one cascade model.

## Non-goals

Do not:

- replace the Halloy theme format, the `:root`-only palette contract, or the browser-local preference model;
- add live theme reload or server-side per-user theme persistence;
- introduce a frontend framework, bundler runtime, or build pipeline beyond the existing `scripts/build_assets.py` and `scripts/build_critical_css.py`;
- change the theme selection API, the CSS route contract, or the metadata endpoint shape;
- redesign the admin interface beyond the shared cascade repair that affects it;
- change the pipeline, LLM, or article-generation behaviour.

## General implementation constraints

- Corrective work lands before cosmetic work, in separate commits.
- Every fix carries a regression test. A test that asserts on generated CSS *text* is not sufficient for a cascade defect — the assertion must observe the *rendered* result.
- Do not weaken the theme contract, the contrast policy, or the accessibility guarantees to make tests pass.
- The theme output contract (`docs/halloy-theme-contract.md`) stays `:root`-only; precedence is fixed by stylesheet ordering, not by changing the emitted selector.
- Rebuild generated assets (`scripts/build_assets.py css`, `scripts/build_critical_css.py`) whenever a source module changes, and commit the regenerated output.
- Preserve `instance/dev.db`; use `instance/dev-fresh.db` for validation runs.
- Keep the application bound to `127.0.0.1` during validation.
- Prefer small, reviewable commits; a phase may be several commits but must not mix corrective and cosmetic changes.
