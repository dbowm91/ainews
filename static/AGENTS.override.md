# Static Assets Conventions

Contextual conventions for agents working in the `static/` directory.

## CSS Architecture

### CSS Module Architecture
Rules are organized into focused modules in `static/css/`.
- `variables.css`: **Canonical source** for all CSS custom properties (`:root` block, `[data-theme="light"]` block). Do NOT duplicate these blocks elsewhere.
- `critical.css`: Should import `variables.css` via `@import "./variables.css"`, NOT contain duplicate `:root` blocks.
- `layout.css`: Layout rules unique to that file only. Remove exact duplicates of rules that exist in `critical.css`.
- `articles.css`: Feed, cards, pagination.
- Avoid inline styles; use utility classes from `utilities.css`.

### CSS Consolidation Note
When editing CSS variables, always edit `variables.css`. If `critical.css` or `critical_css.html` need updating, ensure all three files stay in sync using the build script at `scripts/build_critical_css.py`.

### CSS @layer Organization
`static/css/style.css` uses `@layer reset, variables, layout, components, pages, utilities;` with layered `@import` statements.

## JavaScript

### Container Queries
`.article-feed` has `container-type: inline-size` with `@supports` fallback in `static/css/articles.css`.

### Share Accessibility (JS Merged)
`static/js/share-a11y.js` merged into `static/js/app.js` with focus management and `aria-expanded` fixes. Script tags removed from `templates/base.html` and `templates/base_admin.html`.

### Client-Side Bookmarking
Articles support localStorage-based bookmark toggle via `.bookmark-btn` elements in cards and detail views. State managed in `static/js/app.js` under `bookmarked_articles` key.