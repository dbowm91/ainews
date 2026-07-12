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
    node build/generate-critical-css.js

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

## Checking frontend changes

Run the focused route and asset checks while iterating:

    .venv/bin/pytest tests/test_routes.py tests/test_safe_href_filter.py -q
    .venv/bin/python scripts/build_critical_css.py --check
    .venv/bin/ruff check . --exclude .venv

The full release procedure, including Docker and smoke checks, is documented
in the [release checklist](release_checklist.md).
