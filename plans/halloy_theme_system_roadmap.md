# Halloy-Compatible Theme System Roadmap

> **Note:** This is a historical planning document. Phases 1–6 are complete and Phase 7 (release hardening) is underway. The roadmap below is preserved for reference.

## Purpose

Introduce a Halloy-compatible theming subsystem for the `ainews` frontend. The system must package the approved Halloy themes currently present in the uncommitted repository-root `themes/` directory, translate Halloy TOML into `ainews` semantic CSS variables, preserve client-side reader preferences, and allow operators to add or override themes through a configurable external directory.

The implementation should reuse the proven architecture from `eggstack/eggpool` where appropriate: typed Halloy parsing, a translation layer, safe theme discovery, external-over-bundled precedence, deterministic CSS generation, caching, and safe fallback behavior. It should not copy EggPool's dashboard-specific token model or query-string theme persistence.

## Current state

The frontend is Flask/Jinja with HTMX and a small vanilla-JavaScript layer. `static/css/variables.css` already centralizes the majority of palette values through semantic CSS custom properties. The current theme controller stores `dark` or `light` in `localStorage`, applies a `data-theme` attribute, and follows the operating-system preference when no explicit preference exists.

Generated and duplicated style surfaces include:

- `static/css/style.css`
- `static/css/style.bundled.css`
- `static/css/critical.css`
- `templates/partials/critical_css.html`

These must remain synchronized and must no longer assume only two palettes.

## Target architecture

```text
Bundled Halloy TOML files ----\
                               > ThemeRegistry
External Halloy directory ----/       |
                                       v
                           Halloy parser/validator
                                       |
                                       v
                          Halloy -> AinewsTheme
                                       |
                                       v
                       deterministic CSS variables
                                       |
                         +-------------+-------------+
                         |                           |
                  cacheable CSS route         metadata for UI
                         |                           |
                         +-------------+-------------+
                                       |
                                       v
                          browser theme controller
```

Server responsibilities:

- discover bundled and external themes;
- validate identifiers and paths;
- parse Halloy TOML;
- translate to an `ainews` semantic token model;
- derive missing values and alpha colors;
- calculate diagnostics and critical contrast checks;
- serialize deterministic CSS;
- cache themes, CSS, metadata, and the theme list;
- provide a permanent emergency fallback.

Browser responsibilities:

- persist reader preference locally;
- support `system` plus explicit theme selections;
- migrate existing `dark` and `light` values;
- activate the selected theme before first meaningful paint;
- update the theme selector and accessibility state;
- react to OS color-scheme changes only in `system` mode.

Theme selection must not enter article/feed cache keys. HTMX fragments must remain theme-neutral.

## Design invariants

1. A malformed custom theme cannot prevent application startup or page rendering.
2. An unknown or removed selected theme falls back deterministically.
3. If the configured default fails, a code-defined emergency theme remains available.
4. External themes override bundled themes only by exact normalized identifier.
5. User-controlled values are never directly interpolated into filesystem paths.
6. Halloy values are validated and canonicalized before CSS serialization.
7. Themes may change palette tokens only; layout, spacing, typography, radii, z-index, and scripts are outside the theme contract.
8. The theme registry is immutable during a process lifetime in the first release; theme changes require restart.
9. Public errors and responses never expose source filesystem paths.
10. The shipped theme set is verified in Docker and release artifacts.

## Semantic token contract

The first implementation should define an `AinewsTheme` model covering at least:

- backgrounds: primary, secondary, tertiary, subtle, input, hover, selected;
- borders: default, light, focus;
- text: primary, secondary, muted, dim, inverse;
- interactive: accent, accent hover, accent active, link, link hover, focus ring;
- status: success, warning, error, info;
- category accents: AI, privacy, security, programming, hardware, other;
- loaders/overlays: skeleton base, skeleton shine, selection, overlay;
- derived alpha tokens for accent, success, warning, and error.

The generated CSS should continue to expose existing variables such as `--bg-primary`, `--text-primary`, `--accent`, `--green`, and the existing semantic aliases, minimizing component churn.

## Roadmap phases

### Phase 1: inventory and parser foundation

Inventory the root `themes/` directory, verify provenance and redistribution terms, assign stable identifiers, document the supported Halloy schema, implement typed parsing and color primitives, define `AinewsTheme`, implement translation and deterministic CSS serialization, and add focused unit tests. No visible UI change.

Detailed handoff: `plans/halloy_theme_phase_1_parser_foundation.md`.

### Phase 2: registry, package resources, and custom directory

Move approved themes into application-owned package resources. Add a startup-built registry, safe identifier normalization, bundled discovery, external custom-theme discovery, external-over-bundled precedence, diagnostics, caching, file-size bounds, symlink/path protections, and the emergency fallback. Verify Docker and release inclusion.

Detailed handoff: `plans/halloy_theme_phase_2_registry_packaging.md`.

### Phase 3: CSS delivery and token normalization

Add a cacheable theme CSS route, split structural variables from palette variables, generate alpha colors from active palettes, audit hard-coded colors and SVGs, integrate theme delivery with critical and bundled CSS, and preserve visual parity for the default theme.

Detailed handoff: `plans/halloy_theme_phase_3_css_delivery.md`.

### Phase 4: browser controller and selector

Replace binary state with a versioned preference model, migrate legacy values, implement no-flash activation, add system light/dark pair resolution, build an accessible theme selector, and verify HTMX/full-page persistence.

Detailed handoff: `plans/halloy_theme_phase_4_browser_selection.md`.

### Phase 5: operator support, validation, and documentation

Add a theme validation command, authenticated diagnostics, contrast checks, configuration documentation, custom-theme authoring guidance, deployment volume examples, and operator troubleshooting. Establish CI validation for all bundled themes.

Detailed handoff: `plans/halloy_theme_phase_5_operator_validation.md`.

### Phase 6: comprehensive validation

Add parser, translation, registry, route, JavaScript, failure-mode, accessibility, and visual-regression matrices. Cover materially different light and dark themes and all core public/admin pages at mobile and desktop widths.

### Phase 7: release hardening and closure

Measure startup and first-paint cost; review CSS injection, traversal, symlink, identifier collision, CSP, and cache behavior; verify Docker/release artifacts; remove obsolete binary-theme assumptions while retaining legacy preference migration for a compatibility period.

## Recommended configuration contract

Exact names should follow the repository's configuration conventions, but the behavior should correspond to:

```yaml
frontend:
  themes:
    enabled: true
    custom_dir: null
    default: catppuccin-mocha
    default_dark: catppuccin-mocha
    default_light: rose-pine-dawn
    allow_custom: true
    strict_contrast: false
    max_file_bytes: 262144
```

Recommended first-release policy:

- bundled themes always remain available;
- custom themes are enabled only through an explicitly configured directory;
- custom files must be ordinary Halloy-compatible `.toml` files;
- restart is required after changing theme files;
- critical readability failures reject a theme, while non-critical contrast issues produce diagnostics;
- no live filesystem watcher or remote theme fetching.

## Explicit non-goals

- arbitrary custom CSS;
- remote theme URLs or browser uploads;
- theme-provided JavaScript;
- fonts, spacing, layout, or typography customization;
- database persistence for anonymous reader preferences;
- server-side per-reader HTML variants;
- a proprietary `ainews` theme format;
- browser theme editing;
- automatic upstream Halloy synchronization.

## Principal risks

### Semantic-token insufficiency

Arbitrary Halloy palettes may reveal that components currently sharing one token need separate card, input, hover, header, and selected-state tokens. Expand the semantic layer rather than adding component-specific raw colors.

### Incorrect-theme flash

Theme CSS may arrive after fallback critical CSS. Use an early preference bootstrap, a complete static fallback palette, and independently cacheable theme CSS.

### Accessibility variance

Halloy themes were not necessarily designed for long-form web content. Validate primary text, body text, links, buttons, focus rings, and semantic status text. Derive safe foregrounds narrowly; do not homogenize palette identity.

### External-theme safety

Treat operator-provided TOML as untrusted data. Enforce strict color parsing, bounded input, safe registry lookup, no arbitrary CSS, path confinement, and redacted diagnostics.

### Packaging drift

Themes may work in a checkout but disappear from Docker or installed artifacts. Add blocking artifact-content tests.

## Definition of done

The roadmap is complete when:

1. Approved Halloy themes are packaged with documented provenance.
2. Halloy TOML translates into a complete `AinewsTheme` token set.
3. Invalid input cannot inject arbitrary CSS or escape configured roots.
4. Operators can mount a read-only directory of Halloy-compatible `.toml` files.
5. External themes override bundled themes by normalized identifier.
6. Parsing and translation happen once per process, not per page request.
7. Readers can select bundled/custom themes and persist choices locally.
8. System mode maps OS preference to configured light/dark themes.
9. Existing `dark` and `light` preferences migrate safely.
10. Theme choice does not fragment page or fragment response caches.
11. HTMX navigation preserves the active theme.
12. Critical and generated CSS remain synchronized.
13. Core public and admin pages consume semantic palette tokens.
14. All bundled themes pass parser, translation, contrast, and artifact checks.
15. Custom-theme validation and operator documentation are available.
16. Docker/release artifacts contain the bundled themes.
17. A code-defined emergency theme remains usable if every TOML resource fails.
18. Full repository validation passes.
