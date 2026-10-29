# UI Review — ainews public site

**Date:** 2026-10-28
**Scope:** public UI (`templates/base.html` and friends, `templates/partials/*`, `static/css/*`, `static/js/*`), plus the live app on `http://127.0.0.1:49300`.
**Method:** read-only. All findings below were measured in a real Chromium browser (Playwright) against the running app, or reproduced from source. No repo file was modified by this review.

**Status:** the site renders and the pipeline works, but **three structural CSS defects silently disable most of the design system**, and **two live functional bugs** break the article page and the error pages. Fixing the CSS defects is the precondition for any visual polish — the current "unpolished" look is mostly damage, not design.

---

## Executive summary

| ID | Severity | Finding |
|----|----------|---------|
| B1 | **Blocker** | Article page (`/article/<id>`) returns **HTTP 500** with a public stack trace. Missing `.unique()`. |
| B2 | **Blocker** | **All 48 themes render identically.** The theme palette never reaches the page. |
| B3 | **Blocker** | Generated critical CSS is **malformed** — 3 closing braces lost. 23 rules silently dropped by the parser. |
| B4 | **Blocker** | **Every component's `padding` and `margin` computes to `0px`.** The entire design system is off. |
| B5 | **Blocker** | Mobile is broken — 859px page in a 390px viewport; the hamburger never appears. |
| M1 | Major | Unlayered critical CSS overrides component link styling app-wide (headlines render link-blue). |
| M2 | Major | 404/500 pages return raw JSON to real browsers; the styled error pages are dead code. |
| M3 | Major | Service worker never registers — no offline support. |
| M4 | Major | Stray `…` spinners permanently visible next to search and subscribe. |
| M5 | Major | `top stories` grid leaves an empty third column. |
| M6 | Major | Reduced-motion support is dead. |
| M7 | Major | Measured WCAG contrast failures (4 in the shipped palette; 4 more in the real themes). |
| M8 | Major | `style.bundled.css` is a plain concatenation used by only 3 templates, and omits the reset — two different cascade worlds. |
| M9 | Major | Tap targets below 24px on pointer-fine devices. |
| M10 | Major | Category filter misuses the ARIA tab pattern. |
| N1–N9 | Minor | Duplicated rules, clipped controls, invisible controls, duplicated `aria-label`, missing `h1`. |

---

## A. Blockers

### B1 — Article detail page returns HTTP 500 with a public stack trace

**Confirmed.** `GET /article/24` → `HTTP 500`, `GET /article/23` → `HTTP 500`.

```
sqlalchemy.exc.InvalidRequestError: The unique() method must be invoked on this
Result, as it contains results that include joined eager loads against collections
```

**Root cause** — `services/related.py:35-43`, the *cache-hit* branch:

```python
articles = (
    db.session.execute(
        select(Article)
        .options(joinedload(Article.tags), joinedload(Article.source))
        .where(Article.id.in_(article_ids))
    )
    .scalars()      # <-- .unique() missing here
    .all()
)
```

`Article.tags` is a collection, so `joinedload` on it requires `.unique()`. The two sibling query sites in the same file **do** call it — `find_related_articles()` at `services/related.py:104` and `find_related_articles_dicts()` at `services/related.py:187`. Only the cached branch is missing it.

**Why it looks intermittent:** on a cache *miss* the code path goes through `find_related_articles()`, which has `.unique()` and works. The cache is then populated. On the **next** request the cache-hit branch runs and raises. So the first load of an article works and every subsequent load 500s.

**Secondary issue — traceback disclosure.** The response is a full Werkzeug debugger page containing absolute server paths (`/Users/davidbowman/projects/ainews/...`). The debugger is active in the app serving on `127.0.0.1:49300`, which is a development-mode configuration; it must not be reachable on any non-loopback bind.

**Fix:** add `.unique()` between `.execute(...)` and `.scalars()` at `services/related.py:41`.

---

### B2 — The theme system is completely inert: all 48 themes render identically

**Confirmed.** The active theme is `catppuccin-latte`. Its generated stylesheet declares:

```
:root { --bg-primary: #dce0e8; ... }
```

The page computes:

```
--bg-primary on :root  =  #ffffff        <-- not the theme value
document.body background = rgb(255,255,255)
```

The site always paints the hardcoded fallback palette from `static/css/variables.css`. The theme selector, the 48 bundled themes, the cross-tab sync, the metadata endpoint and the whole `services/themes/` subsystem change nothing on screen.

**Root cause 1 — source order.** The document order in `<head>` is:

```html
<link id="ainews-app-stylesheet"  href="/static/css/style.css">      <!-- layered -->
<link id="ainews-theme-stylesheet" href="">                           <!-- theme :root -->
<style>/* critical_css.html */</style>                               <!-- @import variables.css -->
```

The inline critical sheet `@import`s `variables.css` **unlayered** and **after** the theme link. Unlayered rules outrank layered ones, and among unlayered rules the later one wins — so the fallback `:root` beats the theme's `:root`.

`static/js/theme.js` keeps this order on theme switches: it inserts the replacement `<link>` immediately *after* the existing theme link (`insertBefore(c, v.nextSibling)`), which is still before the inline `<style>`.

**Root cause 2 — specificity tie.** `variables.css` also defines `[data-theme="light"] { --bg-primary: #ffffff; ... }`. An attribute selector and `:root` both have specificity `(0,1,0)`, and `variables.css` comes later, so it wins on source order too.

**This is a regression introduced in the current worktree.** `git diff HEAD -- static/css/critical.css`:

```diff
-@import "./variables.css";
+@import url("/static/css/variables.css");
```

The old relative form resolved against the *page* URL (`/variables.css`), which returns **HTTP 404** — so the import silently failed, the inline sheet defined no palette, and the theme's `:root` was the only unlayered `:root` and therefore won. Making the import work is correct in isolation, but it is what activates the conflict.

**Validated fix.** Moving the theme `<link>` after the inline critical `<style>` (and leaving the architecture intact):

| | before | after |
|---|---|---|
| `--bg-primary` | `#ffffff` | `#dce0e8` |
| `body` background | `rgb(255,255,255)` | `rgb(220,224,232)` |

Either move the theme link after the inline style, or stop the critical sheet from defining the palette (drop its `@import` of `variables.css` and let `style.css` own the tokens).

> **Test-coverage gap.** The repo has 685+ theme tests and they all pass while the theme is invisible, because they assert on the *text* of the generated CSS rather than on the *cascade outcome*. A browser-level assertion is needed (see §Verification).

---

### B3 — The generated critical CSS is malformed: 3 closing braces are lost

**Confirmed by construction and by measurement.**

```
static/css/critical.css            { = 62   } = 62   balanced
templates/partials/critical_css.html { = 62  } = 59   3 braces LOST
```

Reproduced exactly: `templates/partials/critical_css.html` is byte-identical to a fresh run of `scripts/build_critical_css.py`, so the file is up to date with the source — **the generator itself is broken.**

**Root cause** — `scripts/build_critical_css.py`, `build_critical_css()`:

```python
lines = minified.split("}")
for part in lines:
    if part.endswith("{"): formatted_lines.append(part + "\n")
    else:                   formatted_lines.append(part + " }\n")
```

Splitting on `}` consumes one closing brace per boundary and re-adds only one per part. Every `}}` in the minified CSS therefore loses a brace. The minified source contains exactly **3** `}}` sequences, and exactly **3** braces vanish:

1. `@keyframes progress-bar{…}}`
2. `@media (max-width: 640px){…}}`
3. `@media (prefers-reduced-motion: reduce){…}}`

**What the browser does with it.** Chrome's CSSOM for the inline sheet contains exactly 24 top-level rules and **stops at `@keyframes progress-bar`**. Everything after it is silently discarded by the parser:

| Dropped rule | Consequence |
|---|---|
| `.site-footer` (+3 more) | footer unstyled, no padding, no top border |
| `.htmx-indicator`, `.htmx-request .htmx-indicator` | indicator base rule gone (see M4) |
| `.theme-toggle` (+3) | theme button styling gone |
| `.nav-toggle-label` | **hamburger stays `display:none` forever** |
| `.rss-link` (+2) | RSS icon unstyled |
| **`@media (max-width: 640px)`** (entire block) | **mobile nav never collapses** (see B5) |
| `::-webkit-scrollbar` (+4) | default scrollbars |
| `::selection` | default selection |
| `html.theme-transitioning` (+3) | no theme cross-fade |
| **`@media (prefers-reduced-motion: reduce)`** | **reduced motion ignored** (M6) |

**Fix:** replace the split/re-join formatter with a brace-aware one (or emit `minify_css()` output directly). The file `static/css/critical.css` is correct and balanced — only the generator needs to change.

---

### B4 — Every component's padding and margin computes to `0px`

**Confirmed by measurement.** Computed styles on the live feed:

| Selector | padding | margin | authored in | expected |
|---|---|---|---|---|
| `.article-card` | `0px` | `0px` | `articles.css:20-21` | `1rem 1.15rem` / `0 .75rem` |
| `.feed-header` | `0px` | `0px` | `articles.css:827` | `1rem` |
| `.subscribe-box` | `0px` | `0px` | `components.css:772` | `.6rem .75rem` |
| `.filter-btn` | `0px` | `0px` | `components.css:724` | `.25rem .5rem` |
| `.tag-pill` | `0px` | `0px` | `articles.css:691` | `.15rem .5rem` |
| `.category-badge` | `0px` | `0px` | `components.css:4` | `.1rem .4rem` |
| `.search-input` | `0px` | `0px` | `articles.css:865` | `.6rem .75rem` |
| `.subscribe-btn` | `0px` | `0px` | `components.css:292` | `.35rem .6rem` |
| `.top-impact-card` | `0px` | `0px` | `articles.css:1142` | `.75rem` |
| `.site-footer` | `0px` | `0px` | `critical.css` (dropped) | `1.25rem` |

Only `.container` (24px 20px) and `.nav-tag` (2.4px 8px) keep their spacing — precisely the two rules authored in the **unlayered** critical sheet.

**Root cause — a cascade-layer inversion.** `static/css/style.css` puts every module into a cascade layer:

```css
@layer reset, variables, layout, components, pages, utilities;
@import url('variables.css') layer(variables);
@import url('components.css') layer(components);
...
```

but `templates/base.html` inlines `partials/critical_css.html` **outside any layer**. In CSS Cascade Layers, *unlayered* declarations outrank *all* layered declarations regardless of specificity. So the critical sheet's universal reset

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
```

beats every `.foo { padding: … }` in `components.css`, `articles.css` and `pages.css` — including `box-sizing`, `padding` and `margin` on every component on the site.

**Validated fix** — put the inline critical sheet in the same cascade as the app stylesheet (e.g. `@layer reset { … }`, matching the layer order already declared in `style.css`):

| | before | after |
|---|---|---|
| `.article-card` padding | `0px` | `16px 18.4px` |
| `.article-card` margin-bottom | `0px` | `12px` |
| `.feed-header` padding | `0px` | `16px` |
| `.filter-btn` padding | `0px` | `4px 8px` |
| `.tag-pill` padding | `0px` | `1.6px 5.6px` |
| `.card-title a` colour | `rgb(9,105,218)` | `rgb(76,79,105)` (text-primary) |

**This single fix is the difference between "unpolished" and "broken".** Until it lands, any styling work will be fighting a reset that deletes all spacing.

---

### B5 — Mobile layout is broken: an 859px page in a 390px viewport

**Confirmed.** Horizontal overflow measured against `documentElement.clientWidth`:

| Viewport | `scrollWidth` | `clientWidth` | Overflow |
|---|---|---|---|
| 375 | 797 | 375 | **+422px** |
| 390 (mobile) | 859 | 390 | **+469px** |
| 583 | 808 | 583 | **+225px** |
| 768 | 850 | 768 | **+82px** |
| 1280 | 1280 | 1280 | ok |
| 1440 | 1440 | 1440 | ok |

At 390px the page renders a 390px-wide strip of content with a ~470px empty void to the right, and a horizontal scrollbar.

**Root cause:** the mobile block `@media (max-width: 640px)` lives in the dropped region of the malformed critical CSS (B3), so:
- `.nav-links { display: none }` never applies → measured `display: flex` at 375px
- `.nav-toggle-label { display: block }` never applies → measured `display: none`
- `.nav { flex-wrap: wrap }`, `.nav-meta { display: none }` never apply

Playwright could not even click the hamburger — the element resolved but was reported **"element is not visible"**.

**Fix:** fix B3 (and B4, which independently causes the nav to overflow) and re-measure.

---

## B. Major

### M1 — Unlayered critical CSS overrides component link styling app-wide

Same cascade-layer inversion as B4, hitting typography and colour instead of spacing:

| Rule | Layer | Effect |
|---|---|---|
| `a { color: var(--accent) }` (`critical.css:58`) | unlayered | beats `.card-title a { color: var(--text-primary) }` (`articles.css:172`) |
| `a:hover { text-decoration: underline }` (`critical.css:64`) | unlayered | beats every `text-decoration: none` hover rule |

**Measured:** `.card-title a` computes to `rgb(9,105,218)` — **the article headline renders in link-blue instead of primary text**, on every card. The `top stories` headlines look correct only because `.top-impact-headline` is a `<span>` inside an `<a class="top-impact-card">` that sets its own colour.

Fixed by the same B4 change.

### M2 — 404 and 500 pages return raw JSON to real browsers

**Confirmed.** `app.py:222`:

```python
def _wants_json() -> bool:
    return (
        request.path.startswith("/api/v1/")
        or request.is_json
        or "application/json" in request.accept_mimetypes   # <-- matches */*
    )
```

Werkzeug's `MIMEAccept` treats a wildcard `*/*` as matching `application/json`. Every Chrome navigation sends `Accept: text/html,…,*/*;q=0.8`, so `_wants_json()` returns **True for every browser page view**.

Verified:

| Accept header | Response |
|---|---|
| `text/html` (curl) | styled `templates/errors/404.html` |
| realistic Chrome header | `{"error": "Not found"}` — raw JSON in Chrome's JSON viewer |

`templates/errors/404.html` and `templates/errors/500.html` are effectively **dead code for browsers**.

**Fix:** negotiate on the *best* match rather than membership, e.g. `request.accept_mimetypes.best_match(["text/html", "application/json"]) == "text/html"`, or drop the `accept_mimetypes` test and rely on the `/api/v1/` prefix plus `request.is_json`.

### M3 — Service worker never registers: no offline support

`static/js/app.js:408`:

```js
navigator.serviceWorker.register('/static/service-worker.js', {scope: '/'}).catch(function() {});
```

The script is served from `/static/`, so its maximum allowed scope is `/static/`. Requesting scope `/` is rejected. Console error on every page load:

```
The path of the provided scope ('/') is not under the max scope allowed ('/static/').
Adjust the scope, move the Service Worker script, or use the Service-Worker-Allowed HTTP header.
```

The registration fails silently (`.catch(function(){})`), so the "you appear to be offline" toast and the PWA manifest imply an offline capability that does not exist.

**Fix:** register with `{scope: '/static/'}` (and keep the app shell pages out of the offline scope), or serve the worker from the root with `Service-Worker-Allowed: /`.

### M4 — Stray `…` spinners are permanently visible

**Confirmed.** Measured on the feed: `#search-spinner` and `#subscribe-spinner` both compute `opacity: 0.46` with `animation-name: pulse`, at rest.

Cause: `static/css/layout.css:3` applies an infinite animation to the indicator itself:

```css
.htmx-indicator.spinner { animation: pulse 1.5s ease-in-out infinite; }
@keyframes pulse { 0%,100% { opacity: .4 } 50% { opacity: 1 } }
```

A CSS animation overrides the base `opacity` declaration, so the `opacity: 0` from htmx's injected indicator style (and from the critical sheet's `.htmx-indicator` rule) is ignored. The spinner is visible on every page, sitting outside the search field and beside the subscribe button.

**Fix:** animate a non-`opacity` property (or a transform), or scope the animation to `.htmx-request .htmx-indicator.spinner` so it only runs during a request.

### M5 — `top stories` leaves an empty third column

`static/css/articles.css:1133`:

```css
.top-impact-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }
```

With two articles, the third column is an empty ~270px void inside the panel. **Fix:** `repeat(auto-fit, minmax(260px, 1fr))`, or render only as many columns as there are items.

### M6 — Reduced-motion support is dead

`@media (prefers-reduced-motion: reduce)` sits in the dropped region of the critical CSS (B3). It was the global safety net (`*, *::before, *::after { animation-duration: .01ms !important; … }`). The layered `articles.css` blocks at `articles.css:97` and `articles.css:1192` still cover the two hover transforms, but nothing else is covered.

Fixed by B3.

### M7 — Measured WCAG contrast failures

Computed in-browser against the **shipped fallback palette** (what users actually see today, because of B2):

| Element | Size | Foreground | Background | Ratio | Required | |
|---|---|---|---|---|---|---|
| `.card-summary` | 16px | `rgb(110,119,129)` | `rgb(246,248,250)` | **4.27** | 4.5 | FAIL |
| `.nav-links a` | 15px | `rgb(110,119,129)` | `rgb(246,248,250)` | **4.27** | 4.5 | FAIL |
| `.tag-pill` | 12px | `rgb(9,105,218)` | `rgb(234,238,242)` | **4.45** | 4.5 | FAIL |
| `.category-badge` (`.cat-ai`) | 12px | `rgb(130,80,223)` | composited `rgb(229,223,246)` | **3.89** | 4.5 | FAIL |
| `.card-title a` | 16px | `rgb(9,105,218)` | `rgb(246,248,250)` | 4.88 | 4.5 | pass |

And for the theme users are *meant* to be seeing — `catppuccin-latte` on its own surfaces:

| Element | Foreground | Background | Ratio | Required | |
|---|---|---|---|---|---|
| body text | `#6c6f85` | `#e6e9ef` | **4.06** | 4.5 | FAIL |
| muted text | `#8c8fa1` | `#e6e9ef` | **2.63** | 4.5 | FAIL |
| muted text | `#8c8fa1` | `#eff1f5` | **2.83** | 4.5 | FAIL |
| accent link | `#1e66f5` | `#e6e9ef` | **4.04** | 4.5 | FAIL |

This is a **gap in the theme validator**: `services/themes/translate.py` checks only *primary text vs primary background* for the fatal contrast error and emits advisory warnings for a fixed 14-pairing matrix. It never checks `--text-secondary`, `--text-muted` or `--accent` against the surfaces they are actually used on — which is where these failures live. Once B2 is fixed, these themes will be visible for the first time and the failures will be user-facing.

### M8 — Two different cascade worlds

- `templates/base.html` → `static/css/style.css` → 7 separate `@import` requests, all layered.
- `templates/admin/login.html`, `templates/verify.html`, `templates/share_redirect.html` → `static/css/style.bundled.css` → a plain concatenation with **no `@layer`** and **no critical reset**.

`scripts/build_assets.py` simply concatenates the seven modules with comment banners. So the bundled pages get a different cascade (unlayered → the components' own rules win) and a different reset (no `*` reset, so they render with correct spacing — which is why the admin login screenshot looks *better* spaced than the public feed).

Also note the public site never uses the bundle, so the 74KB `style.bundled.css` is fetched by three rarely-visited pages, while the main site pays 7 extra round trips.

**Fix:** one canonical delivery path — serve the bundle (built with the same layers) to all pages, or drop the bundle and use one stylesheet everywhere. Add a CI check that the bundle is regenerated from current sources.

### M9 — Tap targets below 24px

Measured at 1280px (pointer: fine):

| Element | Size |
|---|---|
| `button.subscribe-btn` | **59 × 14** |
| `select.sort-select` | 858 × 16 |
| `summary.share-btn` | 16 × 16 |
| `a.filter-btn` | 15–75 × 21 |
| `a.tag-pill` | 35–68 × 21 |
| `input.search-input` | 858 × 21 |

`static/css/layout.css:67` gives 44px targets under `@media (pointer: coarse)`, so touch devices are covered — but mouse users get 14–21px targets. (Several of these are *caused* by B4: with padding restored, `.subscribe-btn` and `.filter-btn` grow back to usable sizes.)

### M10 — Category filter misuses the ARIA tab pattern

`templates/partials/feed.html:33-38`:

```html
<div id="category-filter" class="filter-bar" role="tablist" aria-label="Category filter">
  <a href="/" role="tab" aria-selected="true" class="filter-btn active">all</a>
  …
```

These are ordinary navigation links. As `role="tab"` they promise a tab widget: no `tabpanel`, no arrow-key navigation, no `aria-controls`, and `aria-selected` is not valid on a link that navigates. Screen readers announce "tab" for what is a link.

**Fix:** drop `role="tablist"`/`role="tab"` and use `aria-current="page"` on the active link, or implement a real tab widget.

---

## C. Minor

| ID | Finding | Location |
|---|---|---|
| N1 | `.search-container` is defined **twice** in the same file (identical declarations). | `articles.css:836` and `articles.css:861` |
| N2 | The `/` keyboard hint (`.search-kbd`) is clipped by the input's right edge and collides with the clear button and the spinner. | `articles.css:841` / `feed.html:27-29` |
| N3 | `.search-clear` (`&times;`) has no visible styling — padding is 0 (B4), so the control is effectively invisible while still occupying space. | `feed.html:27` |
| N4 | `.article-card::before` (the 3px accent stripe) is overlapped by the bookmark button, because the card has no padding (B4). | `articles.css:29` |
| N5 | `select.sort-select` renders as a raw full-width browser control. | `articles.css` / `feed.html:40` |
| N6 | The card title link carries `aria-label="Read article: <full headline>"` that duplicates the visible text, producing very verbose announcements. | `article_card.html:21` |
| N7 | `templates/errors/404.html` renders no `<h1>` (the 404 page has zero headings). | `templates/errors/404.html` |
| N8 | The `subscribe-spinner` is inside the `<form>` and is a permanent `…` glyph (M4). | `subscribe_box.html:28` |
| N9 | `static/js/bundle.min.js` is a generated artifact that is never loaded by any template (dead 65KB). | `static/js/bundle.min.js` |

---

## D. Direction for a "techy AI news" look

This is the styling direction, to be applied **after** B1–B5 are fixed — until the reset stops deleting spacing, every one of these will be cancelled out.

**1. Editorial type hierarchy.** Currently the headline (`1rem`) and the deck (`--text-lg`) are nearly the same size, so nothing dominates. Target:

| Element | Size / weight | Face |
|---|---|---|
| Card headline | 19–21px / 650 / `line-height 1.28` | sans |
| Deck / summary | 15px / 400 / `line-height 1.55` | sans, `--text-muted` |
| Meta row (source · author · time) | 12px | mono, `--text-dim` |
| Badges, labels, section rules | 11–12px / 600 / `letter-spacing .05em` | mono, uppercase |

Keep mono strictly for metadata, badges and labels. The intent is already there — it is just currently applied to almost everything, including the site tagline.

**2. Accent discipline.** Reserve `--accent` for interactive and active states (links on hover, the active category, focus rings, the primary button). Today the accent also carries every headline (M1) and the RSS icon, so nothing reads as "the interactive part".

**3. Two-column layout at ≥1024px.** `--max-width` is 900px in a single column. A 200px left rail (live pipeline status, topic counts, subscribe) plus a 680px main column reads far more like a technical publication and uses the space that currently sits empty.

**4. Replace the boxed `feed-header` chrome with a single toolbar row.** Search on the left, category filter as a segmented control in the middle, sort on the right, one hairline rule underneath. The current nested boxes (`feed-header` → `subscribe-box` → bordered controls) stack four rectangles inside one another.

**5. Card treatment.** Replace the boxed card with a hairline-divided list: 1px bottom rule, no per-card border, generous vertical rhythm (`1.5rem` between entries). This is both denser (more articles per screen) and more "editorial" than the current rounded boxes. Keep the 3px accent stripe but move it to the top edge of the card and only on hover/focus.

**6. Make the pipeline visible — this is the on-brand differentiator.** The site already stores `pipeline_status` and `impact_score` per article and shows a `DONE` chip. Surface the agentic provenance as a proper metadata line: `source · author · time · reading time · ✦ condensed by agent`. A small "pipeline" panel in the rail showing stages, model and quality score would reinforce exactly what makes this product different.

**7. `top stories` as a lead + two secondaries**, not a 3-column grid with an empty slot. Lead story gets the large type; the other two get a compact treatment.

**8. Dark palette should be designed, not borrowed.** The fallback dark palette is GitHub's. Give it a real dark surface ramp (`--bg-primary` → `--bg-secondary` → `--bg-tertiary` → `--bg-elevated`) with a deliberate border ramp and a single accent that works across all 48 themes.

**9. Honour the accessibility preferences already declared.** Restore `@media (prefers-reduced-motion: reduce)` (M6) and `@media (prefers-contrast: high)` (currently present in `variables.css` but only adjusting 4 tokens).

**10. Fix the contrast floor in the theme validator** (M7) — `--text-secondary`, `--text-muted` and `--accent` must be checked against the surfaces they are used on, not just primary text vs background.

---

## E. Suggested fix order

**Phase 0 — blockers (small, independent diffs).**

1. `scripts/build_critical_css.py` — fix the brace-dropping formatter; regenerate `templates/partials/critical_css.html`. → *B3, M6*
2. `templates/base.html` — move the theme `<link>` after the inline critical `<style>`; **or** remove the `@import` of `variables.css` from `static/css/critical.css`. → *B2*
3. `static/css/critical.css` + `templates/base.html` — put the inline critical sheet into `@layer(reset)` to match `style.css`. → *B4, M1*
4. `services/related.py:41` — add `.unique()`. → *B1*
5. `app.py:_wants_json` — negotiate with `best_match`. → *M2*
6. `static/js/app.js:408` — correct the service worker scope. → *M3*
7. `static/css/layout.css:3` — stop the spinner animation from overriding `opacity`. → *M4*
8. `static/css/articles.css:1133` — `auto-fit` the `top stories` grid. → *M5*

**Phase 1 — visual polish.** Re-baseline the screenshots after Phase 0, then apply §D, plus M7 (contrast), M9 (target sizes), M10 (ARIA), N1–N9.

**Phase 2 — consolidation.** M8 (single stylesheet delivery path) and the theme validator's contrast coverage.

---

## F. Verification plan

Phase 0 is only "done" when these pass. All are cheap and belong in CI:

1. **Critical CSS is well-formed** — assert `text.count("{") == text.count("}")` and that the parsed rule count equals the source rule count. Catches B3 at build time.
2. **The theme actually paints** — in a browser, read `getComputedStyle(document.documentElement).getPropertyValue('--bg-primary")` before and after `window.AinewsTheme.activate(<id>)` and assert the value changed and matches the theme's declared value. Catches B2.
3. **Components have their authored spacing** — assert `getComputedStyle(document.querySelector('.article-card')).padding !== '0px'` and `marginBottom !== '0px'`. Catches B4.
4. **No horizontal overflow** at 375 / 390 / 768 / 1280 / 1440: `documentElement.scrollWidth <= clientWidth`. Catches B5.
5. **The article page returns 200** and renders the headline. Catches B1.
6. **Error pages return HTML** for a browser `Accept` header. Catches M2.
7. **Contrast floors** for `--text-secondary`, `--text-muted` and `--accent` on each bundled theme's surfaces. Catches M7.

The existing 685+ theme tests should be kept, but they assert on generated CSS text; assertions 2–4 are the ones that would have caught B2, B4 and B5.

---

## Reproduction

The audit scripts used for this review are outside the repo and left in place for re-runs:

- `/tmp/ainews_ui_audit.py` — viewport sweep, stylesheet ordering, theme application
- `/tmp/ainews_cssom_probe.py` — CSSOM rule matching
- `/tmp/ainews_page_sweep.py` — per-page metrics, contrast, tap targets
- `/tmp/ainews_spacing_probe.py` — computed padding/margin per component
- `/tmp/ainews_fix_validation.py` — in-browser validation of the proposed fixes
- `/tmp/ainews_shots/` — captured screenshots

They run against the live app on `http://127.0.0.1:49300` using the repo's Playwright install and the Chromium 1248 binary at
`~/Library/Caches/ms-playwright/chromium-1248/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`.
