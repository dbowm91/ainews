# Theme Provenance

This document records how bundled themes were selected, evaluated, and included in the ainews theme collection. It is the authoritative provenance record for Workstream 9 of the Phase 5 plan.

## Theme Selection

The 48 bundled themes were selected from two primary sources:

### Halloy built-in themes (16)

All themes shipped with the [Halloy IRC client](https://github.com/squidowl/halloy) were included. These are the canonical reference set for the Halloy TOML theme format and serve as the baseline for compatibility testing.

### Popular community themes (32)

Community themes were selected based on:

- **Popularity** — themes associated with well-known color palettes (Catppuccin, Dracula, Gruvbox, Nord, Rose Pine, Solarized, Zenburn) that have broad adoption across developer tools
- **Appearance diversity** — ensuring adequate representation of both light and dark themes (6 light, 42 dark in the bundle)
- **Style variety** — ranging from minimalist (One Dark, Nord) to expressive (Cyberpunk, Kanagawa) to terminal-oriented (Nostromo Terminal, Matrix)
- **Halloy compatibility** — all themes must parse under `parse_halloy_toml()` without errors

## Evaluation Criteria

Each theme was evaluated against three criteria before inclusion:

### 1. Contrast

The `translate_theme()` function measures the WCAG AA contrast ratio of `text.primary` against `general.background`. Themes must achieve a minimum ratio of 4.5:1. Two themes failed this check and were excluded:

- **Cyber Red** — 4.50:1 (borderline, red-on-near-black intentionally low contrast)
- **Rose Pine Dawn** — 2.45:1 (deliberately low-contrast pastel palette)

### 2. Parse compatibility

Every `.toml` file must parse under `parse_halloy_toml()` and pass `AinewsTheme` validation (strict mode with `extra="forbid"`). No themes failed this check — all 50 evaluated files are valid Halloy TOML.

### 3. Translation completeness

Themes must produce a complete CSS variable output from `to_css_variables()`. Partial translations (missing required color fields) would be excluded. All themes that pass contrast also pass translation.

## License Verification

Every bundled theme is verified to be MIT-licensed. The verification process:

1. Checked the upstream source repository or distribution channel for a LICENSE file or explicit MIT declaration
2. Confirmed no additional restrictions (non-commercial, attribution-only, etc.) beyond MIT
3. Recorded the provenance field in `resources/themes/manifest.json` for traceability

All themes are redistributed as-is with no modifications. The MIT license permits redistribution provided the copyright notice and permission notice are included, which is satisfied by the manifest attribution.

## Manifest Tracking

Each theme's metadata is recorded in `resources/themes/manifest.json` with these fields:

- `id` — normalized identifier (lowercase, hyphen-separated)
- `display_name` — human-readable name
- `source_filename` — original `.toml` filename
- `appearance` — `light` or `dark` (determined by `detect_appearance()`)
- `provenance` — source category (e.g., "Halloy built-in", "Catppuccin", "Community")
- `bundled` — whether the theme is included in the default bundle

The manifest is the source of truth for theme metadata. The inventory table in `docs/themes-inventory.md` is a human-readable rendering of the same data.

## Adding New Themes (Operator Workflow)

To add a new theme to the bundle:

### 1. Obtain the theme file

Place the `.toml` file in the uncommitted `themes/` directory at the repo root (for evaluation) or directly in `resources/themes/` (if already verified).

### 2. Verify compatibility

Run the theme parser to confirm the file is valid:

```python
from services/themes import parse_halloy_toml, translate_theme, detect_appearance

theme = parse_halloy_toml("path/to/theme.toml")
appearance = detect_appearance(theme)
css = translate_theme(theme)
```

### 3. Check contrast

Verify the contrast ratio meets WCAG AA (4.5:1). The `classify_contrast_findings()` function will flag issues:

```python
from services/themes import classify_contrast_findings

diagnostics = classify_contrast_findings(theme)
# Check for CRITICAL-level findings
```

### 4. Update the manifest

Add an entry to `resources/themes/manifest.json`:

```json
{
  "id": "your-theme-id",
  "display_name": "Your Theme Name",
  "source_filename": "Your Theme.toml",
  "appearance": "dark",
  "provenance": "Community",
  "bundled": true
}
```

### 5. Update documentation

- Add a row to the inventory table in `docs/themes-inventory.md`
- Update the summary counts
- If the theme is from a named project, add it to the provenance summary and license notices

### 6. Run tests

```bash
pytest tests/test_theme_packaging.py -v
pytest tests/test_theme_registry.py -v
```

## Requesting Theme Additions (Contributor Workflow)

To request a theme addition without modifying the codebase:

1. **Open an issue** with the title `Theme: <theme name>`
2. **Include the source** — link to the upstream theme file or repository
3. **Include the license** — confirm MIT or compatible license
4. **Include a preview** — screenshot or description of the theme's appearance

Issues will be reviewed for contrast compatibility, license clarity, and fit within the existing collection.

## Theme Exclusion Policy

Themes may be excluded from the bundle for the following reasons:

- **Contrast failure** — primary text vs background below WCAG AA (4.5:1)
- **Parse failure** — invalid Halloy TOML structure
- **License incompatibility** — non-MIT license or additional restrictions
- **Duplicate** — substantially identical to an existing theme (e.g., a variant that only changes one color)

Excluded themes are documented in `docs/themes-inventory.md` under "Excluded Themes" with the specific reason. They are excluded from the bundle; re-inclusion would require explicit contrast remapping or a per-theme override, which is not currently planned.
