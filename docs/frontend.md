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

## Checking frontend changes

Run the focused route and asset checks while iterating:

    .venv/bin/pytest tests/test_routes.py tests/test_safe_href_filter.py -q
    .venv/bin/python scripts/build_critical_css.py --check
    .venv/bin/ruff check . --exclude .venv

The full release procedure, including Docker and smoke checks, is documented
in the [release checklist](release_checklist.md).

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

### Restart requirement

Theme changes require a process restart. No live file watcher.
