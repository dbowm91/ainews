# Theme Authoring Guide

This guide covers creating and deploying custom themes for the ainews project. Themes are Halloy-compatible TOML files translated to CSS custom properties at startup.

## Overview

1. Write a `.toml` file following the Halloy theme schema.
2. Validate with `python scripts/validate_themes.py --file theme.toml`.
3. Place validated files in `THEMES_CUSTOM_DIR`.
4. Restart the application.

## Supported TOML Sections

| Section | Model | Description |
|---------|-------|-------------|
| `[general]` | `HalloyGeneral` | Window chrome colors |
| `[text]` | `HalloyText` | Text color palette |
| `[buffer]` | `HalloyBuffer` | Chat buffer and input area |
| `[buttons.primary]` | `HalloyButton` | Primary button states |
| `[buttons.secondary]` | `HalloyButton` | Secondary button states |

### `[general]`

| Field | Description |
|-------|-------------|
| `background` | Main window background |
| `border` | Window border color |
| `horizontal_rule` | Horizontal rule color |
| `unread_indicator` | Unread indicator color |

### `[text]`

| Field | Description |
|-------|-------------|
| `primary` | Primary text color |
| `secondary` | Secondary text color |
| `tertiary` | Tertiary text color |
| `success` | Success text color |
| `error` | Error text color |

### `[buffer]`

| Field | Description |
|-------|-------------|
| `action` | Action/bonus text color |
| `background` | Buffer background color |
| `background_text_input` | Text input background |
| `background_title_bar` | Title bar background |
| `border` | Buffer border color |
| `border_selected` | Selected buffer border |
| `code` | Code text color |
| `highlight` | Highlight/hover color |
| `nickname` | Nickname text color |
| `selection` | Selection background |
| `timestamp` | Timestamp text color |
| `topic` | Topic text color |
| `url` | URL/link color |

### `[buttons.primary]` and `[buttons.secondary]`

| Field | Description |
|-------|-------------|
| `background` | Button background |
| `background_hover` | Button hover state |
| `background_selected` | Button selected state |
| `background_selected_hover` | Button selected+hover state |

## Ignored/Unsupported Fields

- `buffer.server_messages` and other nested table values
- Any unknown top-level sections (e.g., `[theme]`, `[sidebar]`)
- Any unrecognized keys within recognized sections

These are silently ignored — no error, no warning.

## Color Format

**Accepted:**

| Format | Example | Notes |
|--------|---------|-------|
| `#RRGGBB` | `#1e1e2e` | 6-digit hex, alpha defaults to 255 |
| `#RRGGBBAA` | `#1e1e2eff` | 8-digit hex with explicit alpha |

**Rejected (raises `ThemeParseError`):**

| Format | Example | Reason |
|--------|---------|--------|
| Shorthand hex | `#FFF`, `#ABC9` | Must be 6 or 8 hex chars |
| Named colors | `red`, `tomato` | Not supported |
| CSS functions | `var(--color)`, `rgb(...)` | Not supported |
| URL references | `url(...)` | Not supported |
| Missing `#` | `FF0000` | Must start with `#` |
| Non-string values | `255`, `true` | Must be strings |

All hex values are normalized to lowercase in output.

## Defaults and Derivation

When fields are omitted, the translator derives fallback values:

| AinewsTheme field | Source | Fallback when missing |
|-------------------|--------|----------------------|
| `bg_primary` | `general.background` | `#808080` (gray) |
| `bg_secondary` | `buffer.background` | `#808080` |
| `bg_tertiary` | `buffer.background_title_bar` | `#808080` |
| `bg_subtle` | `buffer.background_text_input` | copies `bg_tertiary` |
| `text_primary` | `text.primary` | `#808080` |
| `text_secondary` | `text.secondary` | `#808080` |
| `text_muted` | `buffer.topic` | `#808080` |
| `text_dim` | `buffer.timestamp` | `#808080` |
| `accent` | `buffer.url` | `#808080` |
| `success` | `text.success` | `#808080` |
| `warning` | `buffer.action` | `#808080` |
| `error` | `text.error` | `#808080` |
| `category_ai` | `text.tertiary` | `#808080` |

Some fields are derived from others:

- `bg_input` → `bg_secondary` lightened +0.04
- `bg_hover` → `bg_secondary` lightened +0.06
- `bg_selected` → `derive_border(bg_secondary)`
- `border_light` → 50% mix of `border` and `bg_secondary`
- `border_focus` → `derive_hover(border)`
- `focus_ring` → `accent` lightened +0.1
- `text_inverse` → `safe_foreground(bg_primary, white, black)`
- `appearance` → luminance of `general.background` or `buffer.background`

For a good theme, provide at minimum: `general.background`, `text.primary`, `text.secondary`, `buffer.background`, `buffer.url`, and `buffer.border_selected`.

## Identifier Derivation

The filename stem is normalized to a theme ID:

1. NFKD Unicode normalization
2. ASCII fold (non-ASCII characters dropped)
3. Lowercase
4. Runs of `[^a-z0-9]` replaced with single `-`
5. Leading/trailing `-` stripped

**Examples:**

| Filename | Theme ID |
|----------|----------|
| `Catppuccin Mocha.toml` | `catppuccin-mocha` |
| `Rose Pine Dawn.toml` | `rose-pine-dawn` |
| `Discord (80_ Saturation).toml` | `discord-80-saturation` |
| `Solarized Dark.toml` | `solarized-dark` |

A filename that normalizes to an empty string raises `ThemeValidationError`.

## Display Name

Display name is derived from the normalized ID by replacing `-` with spaces: `rose-pine-dawn` → `rose pine dawn`. There is no trusted metadata field in Halloy TOML for display names.

## Light/Dark Classification

Appearance is derived from the luminance of `general.background` or `buffer.background`. The translator auto-classifies the theme as `"light"` or `"dark"` based on the resulting perceptual lightness.

## Contrast Requirements

WCAG AA compliance is checked automatically:

| Check | Threshold | Severity |
|-------|-----------|----------|
| Primary text vs primary background | < 4.5:1 | ERROR (fatal) |
| Primary text vs primary background | 4.5–7.0:1 | WARNING (AAA not met) |
| Secondary text vs buffer background | < 4.5:1 | WARNING |
| Accent vs primary background | < 4.5:1 | WARNING |
| Text on button (accent) | < 4.5:1 | WARNING |
| Focus ring vs primary background | < 3.0:1 | WARNING |
| Error vs primary background | < 4.5:1 | WARNING |
| Success vs primary background | < 4.5:1 | WARNING |

A primary text contrast below 4.5:1 raises `ThemeContrastError` and the theme is rejected. All other contrast issues are non-fatal warnings.

## Validation

### Single file

```bash
python scripts/validate_themes.py --file my-theme.toml
```

### With CSS output

```bash
python scripts/validate_themes.py --file my-theme.toml --print-css
```

### Directory of themes

```bash
python scripts/validate_themes.py --directory /path/to/themes/
```

### Machine-readable output

```bash
python scripts/validate_themes.py --bundled --format json
```

### Strict mode (warnings become errors)

```bash
python scripts/validate_themes.py --file my-theme.toml --strict
```

The script exits nonzero on failure, making it suitable for CI.

## External Override Semantics

External themes in `THEMES_CUSTOM_DIR` **completely replace** bundled themes with the same normalized ID. This is a full replacement, not a field-level merge. If your external theme overrides `catppuccin-mocha`, the bundled `catppuccin-mocha` is entirely discarded.

The emergency theme (`__emergency__`) cannot be overridden by external themes.

## Restart and Browser Cache

- **Restart required**: Theme files are parsed once at application startup. Adding, removing, or modifying files requires a process restart.
- **Browser cache**: The CSS route serves with `ETag` and `Cache-Control: public, max-age=300`. When the CSS content changes, the ETag changes automatically. Hard-refresh (`Ctrl+Shift+R`) or wait up to 5 minutes for the browser to re-fetch.
- **Cross-tab sync**: The browser preference system syncs across tabs via `storage` events. Switching themes in one tab immediately updates all other open tabs.

## Minimal Valid Example

```toml
[general]
background = "#1e1e2e"
border = "#45475a"
horizontal_rule = "#313244"
unread_indicator = "#cba6f7"

[text]
primary = "#cdd6f4"
secondary = "#a6adc8"
tertiary = "#cba6f7"
success = "#a6e3a1"
error = "#f38ba8"

[buffer]
action = "#fab387"
background = "#1e1e2e"
background_text_input = "#181825"
background_title_bar = "#181825"
border = "#11111b"
border_selected = "#b4befe"
highlight = "#45475a"
selection = "#313244"
timestamp = "#bac2de"
topic = "#7f849c"
url = "#89b4fa"
```

This produces a dark theme with good contrast. The `general.background` luminance classifies it as dark. Primary text (`#cdd6f4`) on primary background (`#1e1e2e`) gives a contrast ratio well above 4.5:1.

## Deployment (Docker)

Mount your custom themes directory as a read-only volume:

```yaml
services:
  ainews:
    volumes:
      - ./my-themes:/config/ainews/themes:ro
```

Set the environment variable:

```bash
THEMES_CUSTOM_DIR=/config/ainews/themes
THEMES_ALLOW_CUSTOM=true
```

Restart the container after adding or changing theme files.

## Further Reading

- `docs/halloy-theme-contract.md` — Full parser, translation, and CSS output contract
- `docs/themes-inventory.md` — Inventory of all 48 bundled themes
- `docs/theme-troubleshooting.md` — Troubleshooting guide
