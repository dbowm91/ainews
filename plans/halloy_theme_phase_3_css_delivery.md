# Halloy Theme Phase 3 — CSS Delivery and Frontend Token Normalization

## Goal

Connect the startup-built theme registry to the frontend through a safe, independently cacheable CSS delivery surface. Refactor the existing CSS variable layer so Halloy themes control palette values only, remove dark/light-specific color assumptions, and keep critical/generated asset paths synchronized while preserving the current default appearance.

This phase should make arbitrary registry themes technically renderable, but it does not yet need to replace the reader-facing binary selector. A controlled development override or test route may be used for validation.

## Preconditions

- Phase 1 provides validated `AinewsTheme` objects and deterministic CSS serialization.
- Phase 2 provides an immutable registry with bundled/external themes, defaults, content digests, and emergency fallback.
- Registry construction occurs once during application startup.
- The current default dark palette is represented by a valid bundled or emergency theme.

## Workstream 1 — Add the theme CSS route

Add a dedicated route with a path-based stable identifier, for example:

```text
GET /assets/themes/<theme_id>.css
```

Use the repository's existing blueprint/static conventions. The route must:

1. validate the route parameter against the registry, never the filesystem;
2. return only prevalidated generated CSS;
3. set `Content-Type: text/css; charset=utf-8`;
4. set an ETag derived from the registry content digest/generated CSS;
5. honor conditional requests and return `304` where supported;
6. set a public cache policy appropriate to process-lifetime immutable content;
7. avoid cookies and personalized response state;
8. return a controlled 404 or documented fallback for unknown exact IDs;
9. never expose source TOML or absolute paths;
10. include appropriate `X-Content-Type-Options` behavior through existing security middleware.

Recommended cache policy when IDs are stable but an operator may replace a custom file after restart:

```text
Cache-Control: public, max-age=300
ETag: strong digest
```

A versioned/digest URL can support immutable one-year caching later. Do not overstate immutability for an external theme whose content can change while retaining the same ID across deployments.

## Workstream 2 — Define fallback versus exact route behavior

Separate two semantics:

- browser preference resolution may fall back to configured defaults;
- requesting an unknown CSS ID should preferably return 404, so stale/broken state is detectable and browser logic can recover.

Do not silently return default CSS under an unknown ID unless the route includes a response header or other reliable signal. A silent 200 masks stale selections and corrupts cache meaning.

The browser phase will handle load failure by clearing/resolving preference.

## Workstream 3 — Split structural and palette tokens

Refactor `static/css/variables.css` conceptually into:

### Structural/design-system tokens

Remain static and non-themeable:

- font families;
- type scale;
- spacing scale;
- max widths;
- radii;
- z-index values;
- motion durations/easing;
- layout constants.

### Palette tokens

Overridden by generated theme CSS:

- backgrounds;
- borders;
- text colors;
- accents/links/focus;
- status colors;
- category colors;
- skeleton/selection/overlay colors;
- palette-derived shadow or glow colors.

### Semantic aliases

Continue to map components to intent:

- `--color-bg-page`;
- `--color-bg-surface`;
- `--color-bg-elevated`;
- `--color-text-heading`;
- `--color-text-body`;
- `--color-interactive`;
- `--color-border-default`;
- `--color-success`, etc.

Keep a complete fallback palette in static CSS. Pages must remain readable before theme CSS loads and when it fails.

## Workstream 4 — Expand semantic granularity where required

Audit component usage and add tokens where a single current variable is overloaded. Likely additions:

- page versus card versus header versus input surface;
- hover versus selected surface;
- default versus strong versus focus border;
- link versus general accent;
- button background and button foreground;
- inverse text;
- focus ring;
- overlay and shadow color.

Prefer semantic aliases over selectors tied to a named theme. Do not add `[data-theme-id="..."]` special cases for ordinary palette compatibility.

## Workstream 5 — Replace fixed alpha values

Current alpha variables embed RGB values from the existing blue/green/orange/red palette. Replace them with generated values supplied by `AinewsTheme` CSS output.

Required tokens include at least:

- `--accent-alpha-08`;
- `--accent-alpha-10`;
- `--accent-alpha-25`;
- `--green-alpha-10`;
- `--green-alpha-25`;
- `--orange-alpha-10`;
- `--orange-alpha-25`;
- `--red-alpha-10`;
- `--red-alpha-25`;
- `--purple-alpha-10` and `--purple-alpha-25` if still consumed.

The fallback static palette must define matching defaults.

Use canonical server-generated `rgba(...)` values for deterministic broad support. `color-mix()` may remain for non-critical decorative effects only if browser policy permits.

## Workstream 6 — Hard-coded color audit

Search all frontend sources for:

- `#...`;
- `rgb`, `rgba`, `hsl`, `hsla`;
- named colors;
- inline `style` colors;
- SVG `fill` and `stroke`;
- JavaScript chart/color constants;
- `manifest.json` theme/background colors;
- email/standalone-page palettes;
- box shadows and gradients.

Classify each finding:

1. theme-dependent and must become a semantic token;
2. structural shadow/overlay that can remain but needs light-theme validation;
3. externally dictated brand color;
4. generated asset that must be synchronized;
5. intentionally fixed accessibility cue;
6. dead/duplicate style.

Do not mechanically replace all black shadows with accent colors. Add `--shadow-color`/`--overlay` when appropriate and preserve subtle visual hierarchy for light and dark themes.

## Workstream 7 — Gradients, shadows, and decorative effects

Review current gradients such as article-card accent bars and feed-header surfaces. Ensure they do not assume:

- dark page background;
- bright blue accent;
- transparent endpoints only visible on dark surfaces;
- black shadows with excessive contrast on light themes.

Introduce derived tokens where needed:

```text
--surface-gradient-start
--surface-gradient-end
--shadow-color
--accent-glow
--overlay
```

These remain palette outputs, not arbitrary theme CSS.

Retain `prefers-reduced-motion` behavior and ensure theme changes do not introduce motion when reduced motion is requested.

## Workstream 8 — SVG and icon theming

Audit inline and static SVGs used by the frontend:

- logo/brand assets;
- navigation icons;
- category icons;
- status icons;
- manifest/favicon behavior where relevant.

Prefer `currentColor` or semantic CSS variables for UI icons. Keep actual brand artwork fixed only when intentional.

Static SVG files cannot always consume page CSS variables when loaded as images; choose among inline SVG, mask usage, or generated variants deliberately. Do not introduce unbounded per-theme image generation.

## Workstream 9 — Critical CSS integration

The frontend guide identifies multiple critical/generated style outputs. Update the pipeline so:

- structural variables are included in critical CSS;
- the fallback palette is complete in critical CSS;
- obsolete `[data-theme="light"]` palette duplication is not baked into generated output once migration is complete;
- selected theme CSS can override fallback values immediately;
- `static/css/critical.css` and `templates/partials/critical_css.html` remain generated from one source;
- asset-check scripts detect stale output.

Do not inline the full selected theme CSS into every page; that would duplicate content and couple public HTML caches to reader preference. The fallback palette may be inline/critical, while selected theme CSS is independently loaded.

## Workstream 10 — Bundled standalone CSS

Update `static/css/style.bundled.css` and any standalone verification/share pages. Decide their supported behavior explicitly:

- preferred: include the complete fallback palette and allow the same theme stylesheet/bootstrap when full document controls are present;
- acceptable for minimal redirect/verification surfaces: use the fallback/default theme only, documented and visually validated.

No standalone page may become unreadable because it expected `[data-theme="light"]` overrides that were removed.

## Workstream 11 — Development and test activation

Before Phase 4 selector work, provide a safe way to render pages under a chosen registry theme during tests/development. Options:

- test-only template context override;
- environment/config default theme;
- direct inclusion of a known theme CSS URL in a fixture;
- authenticated development query override that is not enabled in production.

Avoid public query-string page variants that would fragment caches.

## Workstream 12 — CSP and security review

Ensure the route and loading mechanism comply with existing Flask-Talisman/CSP policy:

- stylesheet route is same-origin;
- no inline un-nonced scripts are added;
- generated CSS contains custom-property declarations only;
- serialization cannot close a declaration block or inject selectors;
- display names never enter CSS;
- content type is exact;
- route parameter is escaped in logs and responses.

Add an explicit test using malicious-looking Halloy values and IDs to prove they are rejected before CSS output.

## Tests

Add tests for:

1. valid theme CSS response;
2. content type and charset;
3. ETag and conditional `304` behavior;
4. cache-control header;
5. exact unknown ID behavior;
6. no source path/TOML leakage;
7. route lookup never calls filesystem parsing;
8. deterministic output matching registry CSS;
9. complete fallback static variables;
10. complete generated theme variables;
11. no obsolete fixed RGB alpha values in the source token layer;
12. asset-generation/check consistency;
13. critical CSS synchronization;
14. standalone page readability hooks;
15. CSP-compatible stylesheet/link markup;
16. injection payload rejection;
17. light and dark theme route rendering in templates;
18. HTMX fragments remain free of theme-specific styles.

Add a static audit test or script that reports hard-coded colors outside an allowlist. Start advisory if necessary, then make it blocking once classified.

## Validation

Run:

```bash
.venv/bin/pytest tests/test_theme_routes.py tests/test_theme_css_contract.py tests/test_routes.py -q
.venv/bin/python scripts/build_critical_css.py --check
python scripts/build_assets.py css
.venv/bin/ruff check . --exclude .venv
.venv/bin/mypy services/themes routes
```

Then run the repository's full asset/release checks appropriate to frontend changes.

## Deliverables

- safe theme CSS endpoint;
- ETag/cache behavior;
- static fallback palette plus generated palette overrides;
- structural/palette/semantic token separation;
- generated alpha values;
- classified hard-coded color audit and conversions;
- updated critical and bundled CSS outputs;
- CSP/security tests;
- default-theme visual parity evidence.

## Acceptance criteria

- Any valid registry theme can be rendered by loading its CSS URL.
- CSS route output is deterministic, cacheable, and path-safe.
- Page/fragment response caches remain theme-neutral.
- Static fallback styling is complete and readable.
- Existing fixed accent/status alpha colors no longer leak into arbitrary themes.
- Core public and admin components use semantic tokens rather than binary-theme overrides.
- Critical and bundled CSS consistency checks pass.
- Default appearance has no material unintended regression.
- Existing binary selector may remain temporarily, but it now operates against a token system capable of arbitrary Halloy themes.
