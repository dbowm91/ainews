# Frontend guide

The frontend is a server-rendered Flask/Jinja UI with HTMX for progressive
navigation and a small vanilla-JavaScript layer for keyboard shortcuts, theme
switching, sharing, bookmarks, and offline feedback.

## Asset sources

- static/css/style.css is the source stylesheet and imports the CSS modules.
- static/css/style.bundled.css is the generated standalone stylesheet used by
  lightweight pages such as email verification and share redirects.
- static/js/app.js, theme.js, toast.js, and admin.js are the JavaScript
  sources. static/js/bundle.min.js is a generated deployment artifact.
- static/css/critical.css and templates/partials/critical_css.html contain
  the above-the-fold styles used before the full stylesheet loads.

After changing CSS, rebuild generated assets from the repository root:

    python scripts/build_assets.py css
    python scripts/build_critical_css.py

After changing JavaScript, rebuild the minified bundle as well:

    python scripts/build_assets.py js

The application serves the source stylesheet on the main layouts so local
changes remain easy to inspect. Generated files must still be refreshed before
packaging or deploying standalone pages.

## UI conventions

- Keep inline scripts nonce-protected; prefer external JavaScript modules.
- Preserve visible focus states and keyboard access when adding controls.
- Use data-article-id for article-level client state such as bookmarks and
  read markers.
- HTMX responses may be full pages or fragments. Route caches must include the
  representation variant so a fragment is never inserted as a document (or
  vice versa).
- Use safe_href for links derived from crawled or model-generated URLs.
- Prefer the semantic CSS variables in static/css/variables.css over new raw
  colors or spacing values.
- Custom themes produced by `services/themes.translate.to_css_variables()` MUST
  emit variables matching the names in `static/css/variables.css`.
- **`--accent` is chrome, `--link` is text.** `--accent` paints borders, badges,
  focus rings and filled button backgrounds; `--link` paints link and headline
  text. A headline painted with `--accent` reads as a link.
- **A filled accent surface has its own label colour.** `--accent-contrast` is
  the label colour of a filled accent surface (`.btn-primary`,
  `.subscribe-btn`). It cannot be a text token: the dark palette's text is
  near-white and the light palette's is near-black, so either can be
  unreadable on the accent fill. The theme translation layer computes it.

## Stylesheet invariants

These invariants are load-bearing. Each was violated at some point and each
violation silently disabled a large part of the design system rather than
producing an obvious error. See `docs/ui-review-2026-10.md`.

- **One cascade.** `static/css/style.css` declares
  `@layer reset, variables, layout, components, pages, utilities`. The inline
  critical stylesheet in `templates/base.html` MUST participate in that layer
  order. An unlayered rule outranks every layered rule regardless of
  specificity, so an unlayered universal reset silently zeroes every
  component's `padding` and `margin`.
- **One palette source.** The fallback palette is defined exactly once, in
  `static/css/variables.css`. Neither the critical stylesheet nor any other
  shipped source may redefine a palette token, because a later unlayered copy
  outranks the theme stylesheet.
- **Theme precedence.** The theme stylesheet MUST load after the sheet that
  carries the fallback palette. `:root` and `[data-theme="light"]` have equal
  specificity, so precedence is decided by document order alone.
- **Generated CSS must be well-formed.** `scripts/build_critical_css.py` must
  emit a brace-balanced stylesheet and must fail the build if it does not.
  A malformed critical stylesheet causes the browser to discard every rule
  after the imbalance point, with no console error.
- **Rebuild after every CSS change.** `python scripts/build_critical_css.py`
  regenerates `templates/partials/critical_css.html`, and
  `python scripts/build_assets.py css` regenerates
  `static/css/style.bundled.css`. Both outputs are committed.
- **The rendered-document cache is scoped per database.** The public routes
  cache their rendered HTML. The cache key namespace includes a hash of the
  database URI, so two deployments that share a Redis instance cannot read
  each other's documents, and the testing configuration disables the cache
  entirely. The in-process layer expires within `L1_CACHE_TTL` seconds so an
  invalidation applied by another worker becomes visible promptly.
- **Never judge a rendering fix from a cached page.** A cached document hides
  the change you just made. Flush the public cache before verifying a
  stylesheet change in a browser. The development configuration therefore
  disables the rendered-document cache entirely; production keeps it.
- **Nothing invisible may occupy layout.** An element hidden with
  `opacity: 0` is still in the flow and still pushes everything below it
  down. Hide it with `display: none` and restore the natural display type
  (`display: revert`) only while the state is active. A loading placeholder
  that ships *inside the response* can never cover the request, so it is
  never rendered at all.
- **The route must select what the template renders.** A template reads
  attributes off the row the route hands it. A column missing from the
  `SELECT` list renders as an empty cell rather than raising, so the mismatch
  is silent.
- **Derived surface tokens live in `variables.css`.** The glass surfaces and
  the page gradient are derived from palette tokens with `color-mix()` and
  are defined once, in `static/css/variables.css`. The theme output stays
  palette-only: `services/themes/translate.py` must not learn about
  `color-mix`, `to_css_variables()` must keep emitting a `:root` block of
  custom properties and nothing else.
- **The page canvas is `html`, the gradient is `body`.** `html` carries
  `background: var(--bg-primary)` and `body` carries
  `background-color: transparent` plus the gradient image. An opaque body
  background hides the gradient painted on it.
- **The background does not travel with the content.** Every background layer
  on `body` is `background-attachment: fixed`. The bottom-most layer is a
  single flat colour, `--bg-tint`, derived from the theme: it is what shows
  through where the gradient does not reach, so the gradient reads as a shape
  standing against a field rather than as the page itself.
- **One hover state per card.** A card changes one thing when the pointer
  arrives, and its link handles its own affordance. No rule that targets a
  card may select on a hovered descendant (`:has(...)`) — that is what makes
  two treatments fight and the row flicker. Transitions share a duration and
  a curve.
- **A navigation link that scrolls out of sight is a broken link.** The admin
  header is a two-row grid and both nav rows wrap rather than scroll.

## Page frame

The header, the sidebar and the footer are the frame. They are the same on
every public page, and a change to one of them is a change to all of them.

- The rail is included by `templates/base.html`; every public route sets
  `"show_rail": True`. The article route also passes `"categories"`, which
  the navigation renders the topic taxonomy from.
- The subscribe form lives in the footer, once, on every page. It is not in
  the rail and not in a page header.
- The rail collapses below 1024px to a single scrollable row of topic chips.
- Prose blocks are capped at `72ch`. The article column is about 110
  characters wide without the cap.

## Checking frontend changes

Run the focused route and asset checks while iterating:

    .venv/bin/pytest tests/test_routes.py tests/test_safe_href_filter.py -q
    .venv/bin/python scripts/build_critical_css.py --check
    .venv/bin/ruff check . --exclude .venv

The full release procedure, including Docker and smoke checks, is documented
in the [release checklist](release_checklist.md).

Rendering defects — theme precedence, component spacing, horizontal overflow,
mobile navigation — are only observable in a browser. A static check on
generated CSS text cannot detect them. Use the browser assertions:

    .venv/bin/pytest tests/test_frontend_rendering_browser.py -v --timeout=180

## Theme system

### Module structure

The theme system lives in `services/themes/` with these modules:

| Module | Purpose |
|--------|---------|
| `colors.py` | Pure hex color math (WCAG contrast, HSL, compositing) |
| `errors.py` | Exception classes and diagnostic codes |
| `models.py` | Pydantic schemas (HalloyTheme, AinewsTheme) |
| `halloy.py` | TOML parser and identifier normalization |
| `translate.py` | Halloy→AinewsTheme translation and CSS serialization |
| `manifest.py` | Packaged-theme metadata schema |
| `registry.py` | Startup-built immutable registry |
| `loader.py` | Flask bridge (builds and attaches registry) |
| `emergency.py` | Code-defined fallback theme |

### Bundled resources

- Location: `resources/themes/` (Python package)
- Manifest: `resources/themes/manifest.json` (source of truth)
- 48 bundled themes (Halloy built-in, Catppuccin, Dracula, Gruvbox, Nord, etc.)

### Registry lifecycle

1. `build_app_registry(app)` called during Flask app factory
2. Loads bundled manifest via `importlib.resources` (filesystem fallback)
3. Scans external directory if `THEMES_CUSTOM_DIR` configured
4. Builds immutable `ThemeRegistry` (MappingProxyType)
5. Attaches to `app.extensions['theme_registry']`
6. Request-time access via `get_app_registry()` — no per-request parsing

### CSS delivery

- Route: `GET /assets/themes/<theme_id>.css`
- Serves pre-generated CSS from registry (no per-request translation)
- 304 via ETag, 300s cache, nosniff
- 404 for unknown IDs (not fallback)

### Token layers

1. **Palette variables** — direct theme colors
2. **Alpha variants** — rgba overlays for hover/selection states
3. **Legacy aliases** — backward-compatible names (--green, --orange, etc.)
4. **Semantic aliases** — component-facing names (--color-bg-page, etc.)

Two tokens are derived rather than taken from the theme:

- `--link` carries the accent hue but is floored for legibility on the theme's
  own surfaces. `--accent` stays the author's brand colour, because it is used
  for chrome, not for body text.
- `--accent-contrast` is the label colour of a filled accent surface. It is
  chosen independently of the theme's text palette, and the hover fill is moved
  if it would make that label illegible.

`--bg-elevated` is a deliberate addition to the theme contract: it is the
lightest surface step, used for raised chrome such as the subscribe box.

### Browser preference

- Key: `ainews-theme-preference-v2` in localStorage
- Values: `"system"` or `"theme:<normalized-id>"`
- System mode: `matchMedia('(prefers-color-scheme: dark)')`
- Cross-tab sync via `storage` event listener
- Legacy migration from `ainews-theme` key

### HTMX constraints

- Theme CSS loads as a `<link>` stylesheet, not via HTMX
- Selector UI is a standalone popover (not an HTMX fragment)
- Theme changes are instant (pre-generated CSS, no server round-trip)

### Generated assets

```bash
python scripts/build_assets.py css    # Rebuilds style.bundled.css
python scripts/build_assets.py js     # Rebuilds bundle.min.js
```

### Security

- Theme CSS route is public (no auth) — themes are not sensitive
- Metadata endpoint excludes emergency themes
- No user data in theme preference storage
- Admin diagnostics require authentication

### Testing

```bash
.venv/bin/pytest tests/test_theme_*.py -q
.venv/bin/python scripts/validate_themes.py --bundled --strict
```

The browser assertions live in `tests/test_frontend_rendering_browser.py` and
are marked `browser`. They need a Chromium binary; without one they skip
cleanly, so the default test job is unaffected. The `theme-browser-smoke` CI
job installs Chromium and runs both browser modules.

```bash
.venv/bin/pytest tests/test_frontend_rendering_browser.py -v --timeout=180
```

### Restart requirement

Theme changes require a process restart. No live file watcher.

## Related plans

| Plan | Purpose |
|------|---------|
| `docs/ui-review-2026-10.md` | Source review and measurements behind the current frontend state |
| `plans/milestone_g_frontend_rendering_overview.md` | Milestone G entry point |
| `plans/milestone_g_01_cascade_and_delivery.md` | Cascade, theme precedence, article page, error pages, service worker |
| `plans/milestone_g_02_interaction_and_accessibility.md` | Contrast, target sizes, ARIA, user preferences, minor defects |
| `plans/milestone_g_03_visual_identity.md` | Type hierarchy, layout, components, pipeline provenance |
| `plans/milestone_g_closure_pass.md` | Verification gates and the closure record |
| `docs/frontend-rendering-closure.md` | Closure matrix for Milestone G: every defect, its status and the evidence that closed it |
| `plans/release_readiness_roadmap.md` | Top-level roadmap; Milestone G is registered there |
