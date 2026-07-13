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

Generated theme CSS consists exclusively of CSS custom property definitions within a `:root` block. No element selectors, class selectors, media queries, or other CSS rules are permitted. Structural tokens (fonts, spacing, radius, z-index) are defined in `static/css/variables.css` and must not appear in generated theme CSS. Theme CSS overrides palette tokens only.

## Properties of the translation

- **Pure**: no I/O, no network, no database
- **Deterministic**: same input always produces same output
- **Flask-free**: `services/themes/` has zero Flask imports
- **Strict output model**: `AinewsTheme` uses `extra="forbid"` — unexpected fields raise validation errors
- **Provenance tracking**: every output token records whether it was DIRECT, DEFAULTED, or DERIVED


## 12. Registry, packaging, and configuration (Phase 2)

The Phase 1 parser/translator is one piece of the runtime architecture. Phase 2
adds a startup-built, immutable ``ThemeRegistry`` that powers request-time
theme lookup. The contract below extends the previous sections without
changing them.

### 12.1 Package layout

```text
resources/
└── themes/
    ├── __init__.py            # marks the package for importlib.resources
    ├── manifest.json          # source of truth for bundled themes
    └── *.toml                 # approved Halloy theme files (48 themes)
```

The root uncommitted ``themes/`` directory is no longer used at runtime; it is
excluded from the Docker build context via ``.dockerignore``. Bundled themes
are read from ``resources/themes/`` via ``importlib.resources.files()`` with a
filesystem fallback for editable installs.

### 12.2 Manifest format

``resources/themes/manifest.json`` is the single source of truth for bundled
themes. Each entry is:

```json
{
  "id": "catppuccin-mocha",
  "display_name": "catppuccin mocha",
  "source_filename": "Catppuccin Mocha.toml",
  "appearance": "dark",
  "provenance": "Catppuccin",
  "bundled": true
}
```

The Pydantic-style schema is in ``services/themes/manifest.py``. CI fails on
duplicate IDs, duplicate filenames, missing files, or stale entries.

### 12.3 Configuration contract

Theme behavior is configured via env vars (see ``ProductionConfig`` in
``config.py``):

| Variable | Default | Purpose |
|----------|---------|---------|
| ``THEMES_ENABLED`` | ``true`` | Set ``false`` to disable the theme system; only the emergency theme remains. |
| ``THEMES_CUSTOM_DIR`` | empty | Directory of operator-provided ``.toml`` files. Empty disables external discovery. |
| ``THEMES_ALLOW_CUSTOM`` | ``true`` | When ``false``, the custom directory is ignored even when configured. |
| ``THEMES_DEFAULT`` | empty | Registry fallback ID before per-appearance defaults. |
| ``THEMES_DEFAULT_DARK`` | ``catppuccin-mocha`` | Default for dark-mode requests. |
| ``THEMES_DEFAULT_LIGHT`` | ``catppuccin-latte`` | Default for light-mode requests. |
| ``THEMES_MAX_FILE_BYTES`` | ``262144`` | Per-file byte limit for external themes. Validated 1024..1048576. |
| ``THEMES_STRICT_CONTRAST`` | ``false`` | Reserved for a future strict-contrast policy. |

Changes require a restart. Production startup validates only the byte limit
and the ``THEMES_CUSTOM_DIR``/``THEMES_ALLOW_CUSTOM`` interaction; invalid
default theme IDs degrade gracefully through registry fallback to the
emergency theme.

### 12.4 Registry model

Defined in ``services/themes/registry.py``:

```python
@dataclass(frozen=True)
class ThemeOrigin:
    kind: Literal["bundled", "external", "emergency"]
    source_ref: str

@dataclass(frozen=True)
class RegisteredTheme:
    id: str
    display_name: str
    appearance: Literal["light", "dark"]
    origin: ThemeOrigin
    theme: AinewsTheme
    css: str
    warnings: tuple[ThemeDiagnostic, ...]
    content_digest: str

@dataclass(frozen=True)
class ThemeRegistry:
    themes: Mapping[str, RegisteredTheme]   # MappingProxyType (read-only)
    default_id: str
    default_dark_id: str
    default_light_id: str
```

All structures are frozen; the ``themes`` mapping is wrapped in
``MappingProxyType``. The registry is built once during application startup
via ``build_app_registry(app)`` and attached to ``app.extensions['theme_registry']``.
Request-time access uses the prebuilt registry — no per-request parsing, no
arbitrary filesystem lookups.

### 12.5 Discovery precedence

Precedence is fixed; see ``build_registry`` for the authoritative implementation:

1. External exact normalized ID overrides bundled exact normalized ID.
2. External overrides replace the entire translated theme, not fields.
3. The emergency theme has identifier ``__emergency__`` and cannot be shadowed.
4. Invalid configured defaults fall back through:

   ``THEMES_DEFAULT`` → ``THEMES_DEFAULT_DARK`` → ``THEMES_DEFAULT_LIGHT`` → emergency
   
   missing IDs are non-fatal because the registry always has the emergency
   entry.

### 12.6 External directory discovery

External ``.toml`` files are read directly from ``THEMES_CUSTOM_DIR`` with
these guarantees:

- Only direct child ``.toml`` files are read (nested directories are ignored).
- Subdirectories are ignored (flat discovery only in this phase).
- Hidden/temp files (``.*``, ``~*``) are skipped.
- File count capped at ``MAX_EXTERNAL_FILES`` (200) to prevent resource abuse.
- Per-file size capped at ``MAX_EXTERNAL_FILE_BYTES`` (matches the parser).
- Duplicate normalized IDs in the directory are skipped with a diagnostic.
- Symlinks (file and directory) are rejected before parsing.
- Path traversal (``../``, absolute paths, percent-encoded escapes) is rejected.
- One bad file does not abort the registry — diagnostic is emitted instead.

The display name is derived from the normalized identifier (``rose-pine-dawn``
→ ``"rose pine dawn"``). Halloy has no trustworthy metadata field for this.

### 12.7 Emergency fallback

``services/themes/emergency.py`` defines a complete ``AinewsTheme`` in Python
literals (no I/O). It has the reserved identifier ``__emergency__`` and
includes every required token for the dark palette used historically by
``static/css/variables.css``.

The emergency theme is inserted last into the merged map so it cannot be
shadowed by bundled or external entries. It is the always-present final
fallback for ``ThemeRegistry.get()``.

### 12.8 Restart semantics

Themes are parsed once per application process. Operators who change the
custom directory or the bundled resource set must restart the web and worker
processes for the changes to take effect. There is no live file watcher in
this phase.

Tests in ``tests/test_theme_registry.py`` and ``tests/test_theme_packaging.py``
cover every acceptance criterion in this section.

## 13. CSS delivery route (Phase 3)

Phase 3 adds a public HTTP route that serves pre-generated CSS from the
startup-built registry, completing the pipeline from TOML source to
browser-consumable tokens.

### 13.1 Route

``GET /assets/themes/<theme_id>.css``

- **Blueprint:** ``routes/themes.py``, registered as ``themes_bp`` (no auth,
  public GET-only).
- **Registration order:** ``themes_bp`` is registered BEFORE ``public_bp`` in
  ``app.py:_register_blueprints()`` so that ``/assets/themes/`` paths take
  precedence over any public catch-all routes.
- **404 for unknown IDs:** Uses ``registry.get_exact()`` — unknown IDs return
  404, not fallback CSS. This prevents stale or invalid theme references from
  silently falling back to a different theme.

### 13.2 Response headers

| Header | Value |
|--------|-------|
| ``Content-Type`` | ``text/css; charset=utf-8`` |
| ``Cache-Control`` | ``public, max-age=300`` |
| ``ETag`` | ``"`` + content digest (SHA-256 of CSS body) + ``"`` (set via ``response.set_etag()``) |
| ``X-Content-Type-Options`` | ``nosniff`` |

### 13.3 Cache lifetime rationale

The ``Cache-Control: public, max-age=300`` header is a deliberate choice
balancing freshness against performance:

- **External themes can change across restarts without URL changes.** Unlike
  fingerprinted asset URLs (e.g., ``style.a1b2c3.css``), theme CSS URLs are
  stable identifiers (``/assets/themes/catppuccin-mocha.css``). Long immutable
  caching (``max-age=31536000``) would serve stale CSS until the hard expiry.
- **300 seconds (5 minutes)** is long enough to avoid redundant requests on
  page navigations but short enough that a restart-driven change propagates
  within a reasonable window.
- **ETags provide revalidation for freshness.** Clients that still hold
  cached CSS will send ``If-None-Match`` with the previous ``ETag``. The
  route returns ``304 Not Modified`` when the content digest has not changed,
  avoiding unnecessary re-transmission.
- **Fingerprinted URLs are deferred as future work.** A URL scheme like
  ``/assets/themes/<id>.<digest>.css`` would allow immutable caching, but
  adds complexity to the client-side preference system and the metadata
  endpoint. The current approach is correct for the current feature set.

### 13.4 Conditional requests

If the client sends ``If-None-Match`` with a matching ETag, the route returns
``304 Not Modified`` with no body. This avoids re-transmitting unchanged CSS.
Conditional request handling uses ``response.set_etag()`` and
``response.make_conditional(request)`` from Werkzeug for standards-compliant
ETag matching, weak comparison, and multiple validator support.

### 13.5 CSS output structure

``to_css_variables()`` emits a ``:root`` block in this fixed order:

1. **Palette variables** — ``--bg-*``, ``--border-*``, ``--text-*``, ``--accent-*``,
   ``--link-*``, ``--focus-ring``, ``--success``, ``--warning``, ``--error``,
   ``--info``, ``--category-*``, ``--skeleton-*``, ``--selection``, ``--overlay``
2. **Alpha variants** — ``--accent-alpha-*``, ``--green-alpha-*``,
   ``--orange-alpha-*``, ``--red-alpha-*``, ``--purple-alpha-*``,
   ``--category-*-alpha-{15,40}``
3. **Legacy aliases** — ``--green`` (alias for ``--success``), ``--orange``
   (alias for ``--warning``), ``--red`` (alias for ``--error``), ``--purple``
   (alias for ``--info``), ``--accent-dim`` (alias for ``--accent-active``)
4. **Semantic aliases** — ``--success``, ``--warning``, ``--error``, ``--info``

Both legacy and semantic names are emitted. Components should prefer semantic
names; legacy names remain available for backward compatibility.

The entire output is a single `:root` block containing only custom property definitions. No other CSS constructs (selectors, at-rules, comments) are present in generated theme CSS.

### 13.6 Fallback palette

``static/css/variables.css`` defines complete fallback defaults for all
structural tokens (fonts, spacing, radius, z-index) and palette tokens.
Theme CSS overrides palette tokens only; structural tokens remain fixed
regardless of theme selection.

### 13.7 Category badge variables

Category badges use ``--category-{name}-alpha-{15,40}`` variables instead of
hardcoded ``rgba()`` values. The 15% variant is for badge backgrounds; the
40% variant is for badge borders. These are generated by
``to_css_variables()`` from the theme's category colors.

### 13.8 Build pipeline

- **Critical CSS:** ``templates/partials/critical_css.html`` is generated from
  ``static/css/critical.css`` via ``scripts/build_critical_css.py``.
- **Bundled CSS:** ``static/css/style.bundled.css`` is generated by
  ``scripts/build_assets.py css``.
- **Registry access:** Use ``get_app_registry()`` from
  ``services/themes/loader.py`` (or ``app.extensions['theme_registry']``)
  to access the prebuilt ``ThemeRegistry`` at request time.

## 14. Browser preference system (Phase 4)

Phase 4 adds client-side theme persistence, system mode, an accessible
selector UI, and cross-tab synchronization. The server-side registry and
CSS delivery (Phases 2–3) are unchanged.

### 14.1 Preference schema

The preference is stored in ``localStorage`` under the key
``ainews-theme-preference-v2``. Accepted values:

- ``"system"`` — follow the OS ``prefers-color-scheme`` media query.
- ``"theme:<normalized-id>"`` — explicit selection (e.g.,
  ``"theme:catppuccin-mocha"``).

Any other value is treated as corrupt and cleared.

### 14.2 Legacy migration

On first read, ``theme.js`` checks the legacy key ``ainews-theme``
(``"dark"`` or ``"light"``) and maps it to the configured default:

- ``"dark"`` → ``"theme:<THEMES_DEFAULT_DARK>"``
- ``"light"`` → ``"theme:<THEMES_DEFAULT_LIGHT>"``

The legacy key is deleted after migration. Migration is idempotent.

### 14.3 Registry metadata exposure

Server-side injection uses two complementary paths:

1. **Context processor** — ``inject_theme_metadata()`` in
   ``routes/themes.py`` injects a ``theme_metadata`` dict into every
   template context.
2. **JSON script tag** — Templates embed the metadata as
   ``<script id="ainews-theme-metadata" type="application/json">``. No
   CSP nonce is required because ``type="application/json"`` is not
   executable.

Metadata structure:

```json
{
  "defaults": { "dark": "<id>", "light": "<id>" },
  "themes": [
    { "id": "<id>", "name": "<display>", "appearance": "dark|light",
      "css_url": "/assets/themes/<id>.css", "origin": "bundled|external" }
  ]
}
```

Emergency themes (``__emergency__``) are excluded from the metadata.

### 14.4 System mode

When preference is ``"system"``:

- ``matchMedia('(prefers-color-scheme: dark)')`` determines the active
  appearance.
- The matching default theme ID (``defaults.dark`` or ``defaults.light``)
  is resolved from the registry metadata.
- An ``addEventListener('change', ...)`` on the media query updates the
  active theme when the OS preference changes.
- When an explicit theme is selected, OS change events are ignored.

### 14.5 Selector UI

``templates/partials/theme_selector.html`` replaces the legacy
``theme_toggle.html`` partial. Requirements:

- Accessible popover with ``role="listbox"`` and ``aria-label``.
- Search input filters themes by display name.
- Grouped sections: System, Built-in, Custom.
- Keyboard navigation: Arrow keys, Enter to select, Escape to close.
- Mobile: bottom-sheet layout via CSS media query.
- Screen reader announcements via ``aria-live`` region.

### 14.6 Cross-tab synchronization

A ``storage`` event listener on the v2 key propagates preference changes
across tabs:

- Incoming values are validated against the registry.
- Unknown theme IDs fall back to the configured default.
- Write-back loops are prevented by comparing the incoming value to the
  current in-memory preference before writing.

### 14.7 Storage and privacy

- Preference is stored entirely in browser ``localStorage``. No server
  round-trip for reading or writing preferences.
- No cookies are set for theme preference.
- The metadata endpoint (``GET /api/v1/themes/metadata``) returns only
  theme IDs, names, appearances, CSS URLs, and origins. No user data is
  included.
- ``Cache-Control: public, max-age=60`` on the metadata endpoint allows
  CDN caching without user-specific variation.

## 15. Custom directory operational contract (Phase 5)

Phase 5 extends the theme subsystem with operator-managed custom themes and
comprehensive troubleshooting. The contract below governs runtime behavior of
the ``THEMES_CUSTOM_DIR`` directory.

### 15.1 Flat ``.toml`` file requirement

Only direct child ``.toml`` files in the custom directory are discovered.
Nested directories, subdirectories, and non-``.toml`` files are ignored.
The discovery is flat — no recursive traversal.

### 15.2 Read-only directory support

The theme system never writes to the custom directory. Read-only mounts
(``:ro`` in Docker) are fully supported and recommended for production
deployments. File permissions must allow the application user (UID 1000 in
the Dockerfile) to read all ``.toml`` files.

### 15.3 Restart requirement

Themes are parsed once per application process at startup. There is no live
file watcher. Adding, removing, or modifying files in the custom directory
requires a restart of the web and worker processes for changes to take effect.

### 15.4 External-over-bundled precedence

An external theme with the same normalized identifier as a bundled theme
**completely replaces** the bundled entry. This is a wholesale replacement —
not a field-level merge. The bundled version is discarded entirely from the
registry.

### 15.5 Duplicate-ID behavior

If multiple files in the custom directory produce the same normalized
identifier, only the first file encountered (sorted by filename) is loaded.
Subsequent duplicates are skipped with a ``themes.external.duplicate``
diagnostic.

### 15.6 Invalid-file isolation

A single invalid file does not abort registry construction. The file is
skipped, a diagnostic is emitted, and all other valid files continue to be
processed. This ensures one broken theme does not prevent other custom
themes from loading.

### 15.7 Maximum file size and count

- **Per-file size**: Capped at ``THEMES_MAX_FILE_BYTES`` (default 256 KB,
  validated range 1024–1048576). Enforced at both raw bytes length and file
  stat size.
- **File count**: Capped at ``MAX_EXTERNAL_FILES`` (200) to prevent resource
  abuse. Files beyond the limit are skipped with a
  ``themes.custom_file.count_limit`` diagnostic.

### 15.8 Symlink policy

Both directory-level and file-level symlinks are rejected before parsing.
This prevents symlink-based path traversal and ensures the theme system
operates on regular files only.

- Directory root must not be a symlink (``themes.custom_dir.symlink``).
- Individual ``.toml`` files must not be symlinks
  (``themes.custom_file.unsafe_path``).
- Path traversal (``../``, absolute paths, percent-encoded escapes) is
  rejected.

### 15.9 Filename-to-ID normalization

Filenames are normalized to theme identifiers via ``normalize_identifier()``
in ``services/themes/halloy.py``:

1. NFKD Unicode normalization
2. ASCII fold (non-ASCII characters dropped)
3. Lowercase
4. Runs of ``[^a-z0-9]`` replaced with single ``-``
5. Leading/trailing ``-`` stripped

If the result is empty, the file is skipped with a
``themes.custom_file.invalid_id`` diagnostic.

### 15.10 Removed themes and browser preferences

When an external theme is removed from the custom directory:

1. The theme no longer appears in the registry after restart.
2. Browsers with the removed theme ID stored in ``localStorage`` fall back
   to the configured default theme (``THEMES_DEFAULT_DARK`` or
   ``THEMES_DEFAULT_LIGHT`` depending on appearance).
3. The ``theme.js`` client-side bootstrap validates the stored preference
   against the registry metadata on every page load. Unknown IDs trigger
   automatic fallback.
4. No user action is required — the fallback is seamless.

### 15.11 Inspecting diagnostics

**Human-readable output:**

```bash
python scripts/validate_themes.py --directory /path/to/themes
```

**Machine-readable output (JSON):**

```bash
python scripts/validate_themes.py --directory /path/to/themes --format json
```

**Runtime diagnostics:** Startup logs include diagnostics for every skipped
or overridden theme. Search for diagnostic codes (e.g.,
``themes.external.parse``, ``themes.custom_file.size_limit``) in the
application log.

**Browser-side metadata:** The embedded ``#ainews-theme-metadata`` JSON
script tag on every page includes the full registry (IDs, names, appearances,
CSS URLs, origins). Use DevTools console:

```javascript
JSON.parse(document.getElementById('ainews-theme-metadata').textContent)
```

### 15.12 Validating before restart

Always validate custom themes before restarting the application:

```bash
# Validate a single file
python scripts/validate_themes.py --file my-theme.toml

# Validate an entire directory
python scripts/validate_themes.py --directory /path/to/themes

# Validate with CSS output for visual inspection
python scripts/validate_themes.py --file my-theme.toml --print-css

# Strict mode: warnings become errors
python scripts/validate_themes.py --directory /path/to/themes --strict
```

The script exits nonzero on failure, making it safe for CI/CD pipelines.

## 16. Troubleshooting

### Custom theme does not appear

| Check | Diagnostic | Resolution |
|-------|------------|------------|
| File is a direct child of `THEMES_CUSTOM_DIR` | — | Move file to the root of the directory |
| `THEMES_CUSTOM_DIR` is set | `themes.custom_dir.missing` | Set the env var |
| `THEMES_ALLOW_CUSTOM=true` | `themes.custom_dir.disabled` | Set to `true` |
| File count ≤ 200 | `themes.custom_file.count_limit` | Remove unused themes |
| File size ≤ 256 KB | `themes.custom_file.size_limit` | Reduce file size |
| Not a symlink | `themes.custom_dir.symlink` | Use a regular file |
| Unique normalized ID | `THEME_ID_COLLISION` | Rename the file |
| Restart performed | — | Restart web and worker processes |

### Theme rejected as invalid

| Check | Diagnostic | Resolution |
|-------|------------|------------|
| Valid TOML syntax | `THEME_PARSE_INVALID_TOML` | Fix TOML syntax errors |
| Colors are `#RRGGBB` or `#RRGGBBAA` | `THEME_COLOR_INVALID` | Replace invalid color values |
| File has at least one recognized section | `THEME_PARSE_INVALID_TOML` | Add `[general]`, `[text]`, or `[buffer]` |
| Primary text contrast ≥ 4.5:1 | `THEME_CONTRAST_CRITICAL` | Increase text/bg contrast |
| File ≤ 256 KB | `themes.custom_file.size_limit` | Reduce file size |

### Duplicate identifier

Two files produce the same normalized ID. Rename one or remove the duplicate.

### Stale browser preference

Open DevTools → Application → Local Storage → delete
`ainews-theme-preference-v2`. The selector will fall back to the configured
default on next page load.

### CSS appears cached after file replacement

The CSS route uses `ETag` (content hash) and `Cache-Control: max-age=300`.
Hard-refresh (`Ctrl+Shift+R`) to bypass. Confirm a new `ETag` in the
Network tab.

### Default light/dark misclassification

Appearance auto-detection uses luminance of `general.background`. If the
background is borderline, the classification may differ from intent. Ensure
background luminance is clearly above 50% for light or below 50% for dark.

### Missing mounted directory

Verify the Docker volume mount and that the path exists inside the container.
Use `docker exec -it <container> ls -la <path>`.

### Permissions / read-only behavior

Read-only mounts (`:ro`) are supported. Ensure the application user (UID
1000) can read the files. Fix with `chmod -R 644` on files and `chmod 755`
on the directory.

### Emergency fallback active

`THEME_EMERGENCY_FALLBACK` indicates no bundled or external themes loaded.
Check `THEMES_ENABLED`, `THEMES_CUSTOM_DIR`, and `THEMES_ALLOW_CUSTOM`.
Run `python scripts/validate_themes.py --bundled` to identify bundled
parse failures.
