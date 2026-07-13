# Halloy Theme Compatibility Contract

This document defines the supported Halloy TOML theme schema, translation rules, and CSS output contract for the `services/themes/` subsystem.

## 1. Supported sections

The parser recognizes these top-level TOML tables:

| Section | TOML key | Model |
|---------|----------|-------|
| General | `[general]` | `HalloyGeneral` |
| Text | `[text]` | `HalloyText` |
| Buffer | `[buffer]` | `HalloyBuffer` |
| Primary buttons | `[buttons.primary]` | `HalloyButton` |
| Secondary buttons | `[buttons.secondary]` | `HalloyButton` |

## 2. Supported fields

### `[general]`

| Field | Required | Description |
|-------|----------|-------------|
| `background` | no | Main window background (`#RRGGBB`) |
| `border` | no | Window border color |
| `horizontal_rule` | no | Horizontal rule color |
| `unread_indicator` | no | Unread indicator color |

### `[text]`

| Field | Required | Description |
|-------|----------|-------------|
| `primary` | no | Primary text color |
| `secondary` | no | Secondary text color |
| `tertiary` | no | Tertiary text color |
| `success` | no | Success text color |
| `error` | no | Error text color |

### `[buffer]`

| Field | Required | Description |
|-------|----------|-------------|
| `action` | no | Action/bonus text color |
| `background` | no | Buffer background color |
| `background_text_input` | no | Text input background |
| `background_title_bar` | no | Title bar background |
| `border` | no | Buffer border color |
| `border_selected` | no | Selected buffer border |
| `code` | no | Code text color |
| `highlight` | no | Highlight/hover color |
| `nickname` | no | Nickname text color |
| `selection` | no | Selection background |
| `timestamp` | no | Timestamp text color |
| `topic` | no | Topic text color |
| `url` | no | URL/link color |

### `[buttons.primary]` and `[buttons.secondary]`

| Field | Required | Description |
|-------|----------|-------------|
| `background` | no | Button background |
| `background_hover` | no | Button hover state |
| `background_selected` | no | Button selected state |
| `background_selected_hover` | no | Button selected+hover state |

## 3. Excluded data

- `buffer.server_messages` — nested table (not a scalar color)
- Any nested dict values within `buffer` — filtered out by `_filter_buffer_scalars()` in `services/themes/halloy.py:85`
- Unknown top-level sections — silently ignored
- Unknown keys within recognized sections — silently ignored (models use `extra="ignore"`)

## 4. Color format

**Accepted formats:**
- `#RRGGBB` — 6-digit hex (alpha defaults to 255)
- `#RRGGBBAA` — 8-digit hex with alpha

All hex values are normalized to lowercase in output. No validation difference between uppercase and lowercase input.

## 5. Rejected formats

The `parse_hex_color()` function in `services/themes/colors.py:39` rejects:

| Format | Example | Reason |
|--------|---------|--------|
| Shorthand hex | `#FFF`, `#ABC9` | Not supported (must be 6 or 8 hex chars) |
| Named colors | `red`, `tomato` | Not supported |
| CSS functions | `var(--color)`, `rgb(...)` | Not supported |
| URL references | `url(...)` | Not supported |
| Gradients | `linear-gradient(...)` | Not supported |
| Missing `#` | `FF0000` | Must start with `#` |
| Non-string values | `255`, `true` | Must be string |

All rejections raise `ThemeParseError`.

## 6. Tolerance

The parser is tolerant by design:

- **Unknown sections**: silently ignored (e.g., `[theme]`, `[sidebar]`)
- **Unknown keys**: silently ignored within recognized sections (Pydantic `extra="ignore"`)
- **Missing optional fields**: default to `None`, translation derives fallback values
- **Empty TOML**: raises `ThemeParseError`
- **Invalid TOML syntax**: raises `ThemeParseError` wrapping `tomllib.TOMLDecodeError`
- **Non-hex string values**: raises `ThemeValidationError`

## 7. Limits

- **File size**: 256 KB (`MAX_HALLOY_FILE_BYTES = 256 * 1024` in `services/themes/halloy.py:18`)
- Enforced both at raw bytes length and file stat size
- Raises `ThemeParseError` on exceed

## 8. Identifier normalization

The `normalize_identifier()` function in `services/themes/halloy.py:21`:

```python
def normalize_identifier(stem: str) -> str:
    normalized = unicodedata.normalize("NFKD", stem)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    result = re.sub(r"[^a-z0-9]+", "-", lowered)
    result = result.strip("-")
    if not result:
        raise ThemeValidationError(f"Normalized identifier is empty for stem: {stem!r}")
    return result
```

Steps:
1. NFKD Unicode normalization
2. ASCII fold (drop non-ASCII characters)
3. Lowercase
4. Replace runs of `[^a-z0-9]` with single `-`
5. Strip leading/trailing `-`
6. Raise `ThemeValidationError` if result is empty

Examples: `Discord (80_ Saturation)` -> `discord-80-saturation`, `Rose Pine Dawn` -> `rose-pine-dawn`, `Catppuccin Latte` -> `catppuccin-latte`

## 9. Translation rules

`translate_theme()` in `services/themes/translate.py:235` maps Halloy fields to `AinewsTheme` tokens:

| AinewsTheme field | Source Halloy field | Fallback if missing |
|-------------------|--------------------|--------------------|
| `bg_primary` | `general.background` | gray `#808080` |
| `bg_secondary` | `buffer.background` | gray `#808080` |
| `bg_tertiary` | `buffer.background_title_bar` | gray `#808080` |
| `bg_subtle` | `buffer.background_text_input` | copies `bg_tertiary` |
| `bg_input` | `buffer.background_text_input` | `bg_secondary` lightened +0.04 |
| `bg_hover` | `buffer.highlight` | `bg_secondary` lightened +0.06 |
| `bg_selected` | `buffer.selection` | `derive_border(bg_secondary)` |
| `border` | `general.border` | gray `#808080` |
| `border_light` | (derived) | 50% mix of `border` and `bg_secondary` |
| `border_focus` | `buffer.border_selected` | `derive_hover(border)` |
| `text_primary` | `text.primary` | gray `#808080` |
| `text_secondary` | `text.secondary` | gray `#808080` |
| `text_muted` | `buffer.topic` | gray `#808080` |
| `text_dim` | `buffer.timestamp` | gray `#808080` |
| `text_inverse` | (derived) | `safe_foreground(bg_primary, white, black)` |
| `accent` | `buffer.url` | gray `#808080` |
| `accent_hover` | `buttons.primary.background_hover` | `derive_hover(accent)` |
| `accent_active` | `buttons.primary.background_selected` | `derive_border(accent)` |
| `link` | (alias) | same as `accent` |
| `link_hover` | (alias) | same as `accent_hover` |
| `focus_ring` | (derived) | `accent` lightened +0.1 |
| `success` | `text.success` | gray `#808080` |
| `warning` | `buffer.action` | gray `#808080` |
| `error` | `text.error` | gray `#808080` |
| `info` | (alias) | same as `accent` |
| `category_ai` | `text.tertiary` | gray `#808080` |
| `category_privacy` | (alias) | same as `warning` |
| `category_security` | (alias) | same as `error` |
| `category_programming` | (alias) | same as `success` |
| `category_hardware` | (alias) | same as `accent` |
| `category_other` | (alias) | same as `text_muted` |
| `skeleton_base` | (alias) | same as `bg_secondary` |
| `skeleton_shine` | (alias) | same as `bg_tertiary` |
| `selection` | (alias) | same as `bg_selected` |
| `overlay` | (derived) | `composite_over(rgba(0,0,0,0.5), bg_primary)` |
| `appearance` | (derived) | luminance of `general.background` or `buffer.background` |

"Alias" fields are not derived from Halloy; they copy another `AinewsTheme` field directly.

## 10. Contrast policy

Implemented in `classify_contrast_findings()` at `services/themes/translate.py:45`:

| Check | Threshold | Severity | Code |
|-------|-----------|----------|------|
| `text_primary` vs `bg_primary` | < 4.5 | ERROR | `contrast.primary_text` |
| `text_primary` vs `bg_primary` | 4.5-7.0 | WARNING | `contrast.primary_text` (AAA target) |
| `text_secondary` vs `bg_secondary` | < 4.5 | WARNING | `contrast.secondary_text` |
| `accent` vs `bg_primary` | < 4.5 | WARNING | `contrast.accent_link` |
| `text_primary` on `accent` (button) | < 4.5 | WARNING | `contrast.button_text` |
| `focus_ring` vs `bg_primary` | < 3.0 | WARNING | `contrast.focus_ring` |
| `error` vs `bg_primary` | < 4.5 | WARNING | `contrast.error` |
| `success` vs `bg_primary` | < 4.5 | WARNING | `contrast.success` |

- **Primary text < 4.5**: raises `ThemeContrastError` (fatal)
- **Primary text 4.5-7.0**: WARNING diagnostic (non-fatal, AAA not met)
- **All other < 4.5**: WARNING diagnostic (non-fatal)

## 11. CSS output contract

`to_css_variables()` at `services/themes/translate.py:516` emits a `:root` block with variables in this fixed order:

```text
:root {
  --bg-primary: #rrggbb;
  --bg-secondary: #rrggbb;
  --bg-tertiary: #rrggbb;
  --bg-subtle: #rrggbb;
  --bg-input: #rrggbb;
  --bg-hover: #rrggbb;
  --bg-selected: #rrggbb;
  --border: #rrggbb;
  --border-light: #rrggbb;
  --border-focus: #rrggbb;
  --text-primary: #rrggbb;
  --text-secondary: #rrggbb;
  --text-muted: #rrggbb;
  --text-dim: #rrggbb;
  --text-inverse: #rrggbb;
  --accent: #rrggbb;
  --accent-hover: #rrggbb;
  --accent-active: #rrggbb;
  --link: #rrggbb;
  --link-hover: #rrggbb;
  --focus-ring: #rrggbb;
  --success: #rrggbb;
  --warning: #rrggbb;
  --error: #rrggbb;
  --info: #rrggbb;
  --category-ai: #rrggbb;
  --category-privacy: #rrggbb;
  --category-security: #rrggbb;
  --category-programming: #rrggbb;
  --category-hardware: #rrggbb;
  --category-other: #rrggbb;
  --skeleton-base: #rrggbb;
  --skeleton-shine: #rrggbb;
  --selection: #rrggbb;
  --overlay: #rrggbb;
  --accent-alpha-08: rgba(r,g,b,0.0800);
  --accent-alpha-10: rgba(r,g,b,0.1000);
  --accent-alpha-25: rgba(r,g,b,0.2500);
  --green-alpha-10: rgba(r,g,b,0.1000);
  --green-alpha-25: rgba(r,g,b,0.2500);
  --orange-alpha-10: rgba(r,g,b,0.1000);
  --orange-alpha-25: rgba(r,g,b,0.2500);
  --red-alpha-10: rgba(r,g,b,0.1000);
  --red-alpha-25: rgba(r,g,b,0.2500);
  --purple-alpha-10: rgba(r,g,b,0.1000);
  --purple-alpha-25: rgba(r,g,b,0.2500);
}
```

All hex colors are lowercase `#rrggbb`. Alpha variants use `rgba(r,g,b,a)` format where the alpha value matches the existing `static/css/variables.css` contract: `-alpha-08` = `0.08`, `-alpha-10` = `0.10`, `-alpha-25` = `0.25`. The variable names match those in `static/css/variables.css`.

## Properties of the translation

- **Pure**: no I/O, no network, no database
- **Deterministic**: same input always produces same output
- **Flask-free**: `services/themes/` has zero Flask imports
- **Strict output model**: `AinewsTheme` uses `extra="forbid"` — unexpected fields raise validation errors
- **Provenance tracking**: every output token records whether it was DIRECT, DEFAULTED, or DERIVED
