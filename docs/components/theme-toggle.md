# Theme Selector

The theme selector switches between color schemes managed by the Halloy theme system. It replaces the legacy `theme_toggle.html` partial and provides an accessible, searchable popover for theme selection.

## Legacy Fallback

`templates/partials/theme_toggle.html` is a legacy fallback. Base templates (`base.html`, `base_admin.html`) now use `templates/partials/theme_selector.html` instead. The legacy toggle only supports binary dark/light switching via `localStorage.theme`. The selector supports arbitrary themes, system mode, and cross-tab sync.

## Preference Schema

Theme preference is stored in `localStorage` under the key `ainews-theme-preference-v2`:

- `"system"` — Follow OS preference via `matchMedia('(prefers-color-scheme: dark)')`
- `"theme:<normalized-id>"` — Explicit theme selection (e.g., `"theme:catppuccin-mocha"`)

### Legacy Migration

On first access, `theme.js` reads the legacy `ainews-theme` key (`"dark"` or `"light"`) and migrates it to the v2 schema by mapping to the configured default theme IDs:

- `"dark"` → `"theme:<THEMES_DEFAULT_DARK>"`
- `"light"` → `"theme:<THEMES_DEFAULT_LIGHT>"`

The legacy key is then removed.

## Registry Metadata

Templates receive `theme_metadata` via a context processor injected by `routes/themes.py`. This is embedded as a `<script id="ainews-theme-metadata" type="application/json">` tag (no nonce needed — `type="application/json"` is not executable).

Structure:

```json
{
  "defaults": {
    "dark": "catppuccin-mocha",
    "light": "catppuccin-latte"
  },
  "themes": [
    {
      "id": "catppuccin-mocha",
      "name": "catppuccin mocha",
      "appearance": "dark",
      "css_url": "/assets/themes/catppuccin-mocha.css",
      "origin": "bundled"
    }
  ]
}
```

Emergency themes are excluded from the metadata.

## No-Flash Bootstrap

`static/js/theme.js` runs synchronously as an IIFE before first paint:

1. Reads `ainews-theme-preference-v2` from localStorage (migrates legacy key if present)
2. Parses `#ainews-theme-metadata` JSON
3. Resolves active theme (explicit ID or OS-based via matchMedia)
4. Sets `data-theme-id`, `data-theme-appearance`, and `data-theme` on `<html>`
5. Updates `#ainews-theme-stylesheet` `<link>` `href` to the theme's CSS URL
6. Falls back to static styling on any failure

## Stylesheet Controller

`window.AinewsTheme` public API:

| Method | Description |
|--------|-------------|
| `activate(themeId)` | Switch to an explicit theme. Preloads CSS, activates, removes old stylesheet. |
| `setSystem()` | Switch to system mode (OS preference). |
| `getActiveThemeId()` | Returns the currently active theme ID. |
| `getPreference()` | Returns the stored preference (`"system"` or `"theme:<id>"`). |
| `getRegistry()` | Returns the parsed registry metadata. |
| `isSystemMode()` | Returns `true` if in system-follow mode. |

Atomic switching: preload new stylesheet → activate → remove old. Max 3 stylesheet error retries before clearing preference.

## System Mode

When preference is `"system"`, `theme.js` uses `matchMedia('(prefers-color-scheme: dark)')` to map the OS preference to the configured default theme IDs (`defaults.dark` / `defaults.light`). An event listener tracks OS changes while in system mode; changes are ignored for explicit theme selections.

## Selector UI

`templates/partials/theme_selector.html` provides an accessible popover with:

- **Search:** Filter themes by name
- **Grouped options:** System / Built-in / Custom sections
- **Keyboard navigation:** Arrow keys, Enter to select, Escape to close
- **Mobile:** Bottom-sheet layout on small screens
- **ARIA:** `role="listbox"`, `aria-label`, `aria-activedescendant` for screen readers

## Cross-Tab Sync

A `storage` event listener on the v2 key synchronizes preference changes across tabs. Incoming preferences are validated against the registry. Write-back loops are avoided by checking if the incoming value matches the current in-memory state. Unknown theme IDs fall back to the default.

## Metadata Endpoint

`GET /api/v1/themes/metadata` returns the same JSON structure as the context processor. Response: `Cache-Control: public, max-age=60`. No auth required.

## Related Files

- `static/js/theme.js` — Bootstrap, controller, cross-tab sync
- `templates/partials/theme_selector.html` — Selector popover partial
- `templates/partials/theme_toggle.html` — Legacy fallback (binary dark/light only)
- `routes/themes.py` — Context processor, metadata endpoint, CSS delivery
- `tests/test_theme_preferences.py` — 22 tests for preference system
