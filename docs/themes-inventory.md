# Theme Inventory & Provenance

This document catalogs every `.toml` file under `resources/themes/`. It is the review record for Phase 1 of the theme subsystem — no source theme collection is committed blindly.

## How appearance is determined

Exact light/dark classification is done at parse time via `detect_appearance()` in `services/themes/translate.py:27`, which measures the relative luminance of `general.background` (preferred) or `buffer.background` (fallback). The "Appearance" column below uses the same luminance threshold (0.5) for approximate classification. Luminance >= 0.5 = light; < 0.5 = dark.

## Inventory

| filename | identifier | display name | appearance | sections | notable fields | upstream | license | redistribution |
|----------|-----------|--------------|------------|----------|----------------|----------|---------|----------------|
| `acton.toml` | `acton` | acton | dark | general, text, buffer | purple bg, rose accent | Halloy built-in | MIT (Halloy) | yes |
| `bam.toml` | `bam` | bam | dark | general, text, buffer | deep green bg, green text | Halloy built-in | MIT (Halloy) | yes |
| `base16-atelier-forest-light.toml` | `base16-atelier-forest-light` | base16-atelier-forest-light | light | general, text, buffer | warm beige bg, muted brown text | Community | MIT (community) | yes |
| `berlin.toml` | `berlin` | berlin | dark | general, text, buffer | dark teal bg, blue text | Halloy built-in | MIT (Halloy) | yes |
| `black but with important highlights.toml` | `black-but-with-important-highlights` | black but with important highlights | dark | general, text, buffer | near-black bg, gray text | Community | MIT (community) | yes |
| `Booberry.toml` | `booberry` | Booberry | dark | general, text, buffer | purple bg, lavender text | Community | MIT (community) | yes |
| `broc.toml` | `broc` | broc | dark | general, text, buffer | olive bg, yellow-green text | Halloy built-in | MIT (Halloy) | yes |
| `Catppuccin Latte.toml` | `catppuccin-latte` | Catppuccin Latte | light | general, text, buffer | pastel blue bg, dark text | Catppuccin | MIT (community) | yes |
| `Catppuccin Macchiato.toml` | `catppuccin-macchiato` | Catppuccin Macchiato | dark | general, text, buffer | dark blue-gray bg, light blue text | Catppuccin | MIT (community) | yes |
| `Catppuccin Mocha.toml` | `catppuccin-mocha` | Catppuccin Mocha | dark | general, text, buffer | near-black bg, light text | Catppuccin | MIT (community) | yes |
| `cork.toml` | `cork` | cork | dark | general, text, buffer | dark green bg, bright green text | Halloy built-in | MIT (Halloy) | yes |
| `Cyberpunk.toml` | `cyberpunk` | Cyberpunk | dark | general, text, buffer | near-black bg, neon green text | Community | MIT (community) | yes |
| `Cyber Red.toml` | `cyber-red` | Cyber Red | dark | general, text, buffer | black bg, red text | Community | MIT (community) | excluded (contrast) |
| `Dark Green.toml` | `dark-green` | Dark Green | dark | general, text, buffer | near-black bg, yellow-green text | Community | MIT (community) | yes |
| `Discord (80_ Saturation).toml` | `discord-80-saturation` | Discord (80_ Saturation) | dark | general, text, buffer | Discord gray bg, light gray text | Community | MIT (community) | yes |
| `Discord.toml` | `discord` | Discord | dark | general, text, buffer | Discord gray bg, light gray text | Community | MIT (community) | yes |
| `Dracula.toml` | `dracula` | Dracula | dark | general, text, buffer | Dracula purple bg, cream text | Dracula | MIT (community) | yes |
| `Ferra Light.toml` | `ferra-light` | Ferra Light | light | general, text, buffer | warm light bg, brown text | Community (Ferra variant) | MIT (community) | yes |
| `ferra.toml` | `ferra` | ferra | dark | general, text, buffer | dark warm bg, peach text | Halloy built-in | MIT (Halloy) | yes |
| `Flexor Dark.toml` | `flexor-dark` | Flexor Dark | dark | general, text, buffer | warm dark bg, cream text | Community | MIT (community) | yes |
| `forest.toml` | `forest` | forest | dark | general, text, buffer | dark green bg, light text | Halloy built-in | MIT (Halloy) | yes |
| `Gruvbox.toml` | `gruvbox` | Gruvbox | dark | general, text, buffer | Gruvbox dark bg, cream text | Gruvbox | MIT (community) | yes |
| `Halcyon Dark.toml` | `halcyon-dark` | Halcyon Dark | dark | general, text, buffer | deep blue bg, light text | Community | MIT (community) | yes |
| `IntelliJ Light.toml` | `intellij-light` | IntelliJ Light | light | general, text, buffer | white bg, black text | Community | MIT (community) | yes |
| `Kanagawa.toml` | `kanagawa` | Kanagawa | dark | general, text, buffer | dark indigo bg, warm text | Community | MIT (community) | yes |
| `lisbon.toml` | `lisbon` | lisbon | dark | general, text, buffer | dark navy bg, blue text | Halloy built-in | MIT (Halloy) | yes |
| `Macaw Dark.toml` | `macaw-dark` | Macaw Dark | dark | general, text, buffer | gray bg, light gray text | Community | MIT (community) | yes |
| `Macaw Light.toml` | `macaw-light` | Macaw Light | light | general, text, buffer | light gray bg, black text | Community | MIT (community) | yes |
| `Matrix.toml` | `matrix` | Matrix | dark | general, text, buffer | black bg, neon green text | Community | MIT (community) | yes |
| `midnight.toml` | `midnight` | midnight | dark | general, text, buffer | dark navy bg, off-white text | Halloy built-in | MIT (Halloy) | yes |
| `Noctis Lilac.toml` | `noctis-lilac` | Noctis Lilac | light | general, text, buffer | light lavender bg, deep purple text | Community | MIT (community) | yes |
| `Nord.toml` | `nord` | Nord | dark | general, text, buffer | Nord dark bg, light blue text | Nord | MIT (community) | yes |
| `Nostromo Terminal.toml` | `nostromo-terminal` | Nostromo Terminal | dark | general, text, buffer | black bg, green text | Community | MIT (community) | yes |
| `One Dark.toml` | `one-dark` | One Dark | dark | general, text, buffer | dark gray bg, light gray text | Community | MIT (community) | yes |
| `oslo.toml` | `oslo` | oslo | dark | general, text, buffer | dark navy bg, blue text | Halloy built-in | MIT (Halloy) | yes |
| `Oxocarbon.toml` | `oxocarbon` | Oxocarbon | dark | general, text, buffer | near-black bg, white text | Community | MIT (community) | yes |
| `plum.toml` | `plum` | plum | dark | general, text, buffer | dark purple bg, cream text | Halloy built-in | MIT (Halloy) | yes |
| `portland.toml` | `portland` | portland | dark | general, text, buffer | gray bg, light gray text | Halloy built-in | MIT (Halloy) | yes |
| `Rose Pine Dawn.toml` | `rose-pine-dawn` | Rose Pine Dawn | light | general, text, buffer | warm light bg, muted coral text | Rose Pine | MIT (community) | excluded (contrast) |
| `Rose Pine Moon.toml` | `rose-pine-moon` | Rose Pine Moon | dark | general, text, buffer | dark indigo bg, rose text | Rose Pine | MIT (community) | yes |
| `Rose Pine.toml` | `rose-pine` | Rose Pine | dark | general, text, buffer | dark purple bg, rose text | Rose Pine | MIT (community) | yes |
| `Solarized Dark.toml` | `solarized-dark` | Solarized Dark | dark | general, text, buffer | Solarized base03 bg, base0 text | Solarized | MIT (community) | yes |
| `Sonokai.toml` | `sonokai` | Sonokai | dark | general, text, buffer | dark gray bg, white text | Community | MIT (community) | yes |
| `sunset.toml` | `sunset` | sunset | dark | general, text, buffer | dark navy bg, orange accent | Halloy built-in | MIT (Halloy) | yes |
| `tofino.toml` | `tofino` | tofino | dark | general, text, buffer | dark blue bg, blue text | Halloy built-in | MIT (Halloy) | yes |
| `Tokyo Night Storm.toml` | `tokyo-night-storm` | Tokyo Night Storm | dark | general, text, buffer | dark navy bg, light blue text | Community | MIT (community) | yes |
| `vanimo.toml` | `vanimo` | vanimo | dark | general, text, buffer | dark maroon bg, magenta text | Halloy built-in | MIT (Halloy) | yes |
| `VESPER.toml` | `vesper` | VESPER | dark | general, text, buffer | near-black bg, white text | Community | MIT (community) | yes |
| `vik.toml` | `vik` | vik | dark | general, text, buffer | dark brown bg, muted red text | Halloy built-in | MIT (Halloy) | yes |
| `Zenburn.toml` | `zenburn` | Zenburn | dark | general, text, buffer | gray bg, olive green text | Zenburn | MIT (community) | yes |

## Summary

- **50 themes total** (including Ferra Light, the two Discord variants, and Rose Pine variants)
- **48 themes translate successfully** (all themes pass parse; 2 fail contrast — see below)
- **48 bundled** in `resources/themes/`
- **6 light themes**: base16-atelier-forest-light, Catppuccin Latte, Ferra Light, IntelliJ Light, Macaw Light, Noctis Lilac
- **42 dark themes**: all others
- **16 Halloy built-in**: acton, bam, berlin, broc, cork, ferra, forest, lisbon, midnight, oslo, plum, portland, sunset, tofino, vanimo, vik
- **34 community themes**: all remaining (including Catppuccin, Dracula, Gruvbox, Nord, Rose Pine, Solarized, Zenburn, etc.)

## Contrast exclusions (translation failures)

These themes parse successfully but `translate_theme()` raises `ThemeContrastError` because `text.primary` vs `general.background` falls below the WCAG AA threshold of 4.5. They are excluded from the bundle; re-inclusion would require explicit contrast remapping or a per-theme override, which is not currently planned.

| Theme | text.primary | general.background | Measured contrast | Notes |
|-------|--------------|---------------------|-------------------|-------|
| `Cyber Red.toml` | `#e41951` (red) | `#0a0000` (near-black red) | 4.50 | Both reds are too close in luminance; the original Halloy theme intentionally uses red text on near-black background. |
| `Rose Pine Dawn.toml` | `#d7827e` (rose) | `#f4ede8` (warm off-white) | 2.45 | Rose Pine Dawn is a deliberately low-contrast pastel palette; the rose accent is not intended to be primary text. |

These themes remain valid Halloy themes and parse without errors — only the translation step fails. They are excluded from the bundle; re-inclusion would require explicit contrast remapping or a per-theme override, which is not currently planned.

## Rendered palette vs source TOML

The translation layer applies a readability floor, so the palette the browser
paints is not always the palette the source TOML declares. The floor raises
the lightness of a `text_secondary`, `text_muted` or `link` tone that is
unreadable on the theme's own surfaces; hue and saturation are preserved, so
the palette still reads as the theme it came from. The upstream Halloy files
in `resources/themes/` are byte-identical to what Halloy ships.

**33 of the 48 bundled themes** have at least one adjusted token:

| Theme | Adjusted tokens |
|-------|-----------------|
| `catppuccin-latte` | `text_secondary` `#6C6F85` → `#5f6275`; `link` `#1E66F5` → `#0a55ea` |
| `discord-80-saturation` | `text_secondary` `#9C9DA2` → `#afb0b4`; `link` `#2AAAF8` → `#50b9f9` |
| `discord` | `text_secondary` `#9C9DA2` → `#afb0b4`; `link` `#2AAAF8` → `#50b9f9` |
| `dracula` | `text_secondary` `#727794` → `#8d91a8` |
| `ferra-light` | `text_secondary` `#A79891` → `#72635c`; `link` `#6360D6` → `#5754d3` |
| `flexor-dark` | `link` `#4385BE` → `#4989c0` |
| `gruvbox` | `link` `#458588` → `#509b9e` |
| `kanagawa` | `text_secondary` `#727169` → `#94938a` |
| `macaw-dark` | `link` `#2884FC` → `#539dfd` |
| `macaw-light` | `text_secondary` `#6C6F85` → `#696c81`; `link` `#1E66F5` → `#1661f5` |
| `noctis-lilac` | `text_secondary` `#75718E` → `#65617a`; `link` `#00C6E0` → `#006f7d` |
| `nord` | `text_secondary` `#616E88` → `#a6afc0` |
| `one-dark` | `text_secondary` `#878E9B` → `#999faa` |
| `oxocarbon` | `text_secondary` `#525252` → `#848484` |
| `rose-pine-moon` | `text_secondary` `#908CAA` → `#928eac` |
| `solarized-dark` | `text_secondary` `#586E75` → `#859ca3`; `link` `#2AA198` → `#2daba1` |
| `sonokai` | `text_secondary` `#7F8490` → `#9a9ea7` |
| `zenburn` | `text_secondary` `#95958A` → `#aaaaa1` |
| `acton` | `text_secondary` `#CE779D` → `#dea3bc` |
| `bam` | `text_secondary` `#557528` → `#7baa3a` |
| `base16-atelier-forest-light` | `text_secondary` `#766E6B` → `#6b6461`; `link` `#407EE7` → `#1a5ed2` |
| `berlin` | `text_secondary` `#2A6D8D` → `#459dc7` |
| `black-but-with-important-highlights` | `text_secondary` `#8F8F8F` → `#989898` |
| `broc` | `text_secondary` `#857D50` → `#b3ac81` |
| `cork` | `text_secondary` `#3A793F` → `#5cb162` |
| `forest` | `text_secondary` `#A49D87` → `#a9a28d`; `link` `#9A8C98` → `#aba0aa` |
| `lisbon` | `text_secondary` `#48709D` → `#7a9cc2` |
| `midnight` | `text_secondary` `#778DA9` → `#788eaa` |
| `plum` | `text_secondary` `#72778E` → `#a5a8b7` |
| `portland` | `text_secondary` `#8F8F8F` → `#989898` |
| `tofino` | `text_secondary` `#4363A2` → `#7a94c8` |
| `vanimo` | `text_secondary` `#994386` → `#c376b2` |
| `vik` | `text_secondary` `#823722` → `#d16c4f` |

Every theme additionally gains two derived tokens that no source TOML declares:
`--link` (the accent hue, floored for legibility) and `--accent-contrast`
(the label colour of a filled accent surface). `--bg-elevated` is derived from
`bg_tertiary`. See `docs/halloy-theme-contract.md` §10.3 and §10.4.

## Normalized identifier examples

The `normalize_identifier()` function in `services/themes/halloy.py:21` applies: NFKD Unicode normalization, ASCII fold, lowercase, replace `[^a-z0-9]+` with `-`, strip leading/trailing `-`.

| Filename stem | Normalized identifier |
|---------------|----------------------|
| `Discord (80_ Saturation)` | `discord-80-saturation` |
| `Catppuccin Latte` | `catppuccin-latte` |
| `base16-atelier-forest-light` | `base16-atelier-forest-light` |
| `black but with important highlights` | `black-but-with-important-highlights` |
| `Noctis Lilac` | `noctis-lilac` |
| `Rose Pine Dawn` | `rose-pine-dawn` |
| `Cyber Red` | `cyber-red` |
| `Solarized Dark` | `solarized-dark` |
| `Tokyo Night Storm` | `tokyo-night-storm` |
| `Nostromo Terminal` | `nostromo-terminal` |
| `Macaw Light` | `macaw-light` |
| `Ferra Light` | `ferra-light` |
| `Halcyon Dark` | `halcyon-dark` |
| `IntelliJ Light` | `intellij-light` |
| `One Dark` | `one-dark` |
| `Rose Pine Moon` | `rose-pine-moon` |
| `Flexor Dark` | `flexor-dark` |
| `Dark Green` | `dark-green` |

## Provenance Summary

| Source | Count | License | Themes |
|--------|-------|---------|--------|
| Halloy built-in | 16 | MIT | acton, bam, berlin, broc, cork, ferra, forest, lisbon, midnight, oslo, plum, portland, sunset, tofino, vanimo, vik |
| Catppuccin | 3 | MIT | catppuccin-latte, catppuccin-macchiato, catppuccin-mocha |
| Dracula | 1 | MIT | dracula |
| Gruvbox | 1 | MIT | gruvbox |
| Nord | 1 | MIT | nord |
| Rose Pine | 3 | MIT | rose-pine, rose-pine-moon, rose-pine-dawn* |
| Solarized | 1 | MIT | solarized-dark |
| Zenburn | 1 | MIT | zenburn |
| Community (Base16) | 1 | MIT | base16-atelier-forest-light |
| Community (Ferra variant) | 1 | MIT | ferra-light |
| Community (other) | 19 | MIT | remaining themes |

*Rose Pine Dawn is excluded from the bundle due to contrast failure (see Contrast exclusions above).

## License Notices

All bundled themes are distributed under the MIT license. The following
upstream projects are acknowledged:

- **Halloy** (https://github.com/squidowl/halloy) — built-in themes
- **Catppuccin** (https://github.com/catppuccin/catppuccin) — pastel theme palette
- **Dracula** (https://github.com/dracula/dracula-theme) — dark theme
- **Gruvbox** (https://github.com/morhetz/gruvbox) — retro groove theme
- **Nord** (https://www.nordtheme.com/) — arctic, north-bluish color palette
- **Rose Pine** (https://rosepinetheme.com/) — all natural pine, faux fur and a bit of soho vibes
- **Solarized** (https://ethanschoonover.com/solarized/) — precision engineered color palette
- **Zenburn** (https://github.com/MBernebe/nicE-rofi-themes) — low contrast color scheme

No modifications were made to any bundled theme files. All themes are
redistributed as-is from their upstream sources with attribution in the
manifest.

## Excluded Themes

The following themes were evaluated but excluded from the bundle:

| Theme | Reason |
|-------|--------|
| Cyber Red | Primary text contrast below WCAG AA (4.50:1) |
| Rose Pine Dawn | Primary text contrast below WCAG AA (2.45:1) |

These themes remain valid Halloy files but fail the ainews translation
step's critical contrast requirement. They may be supported in a future
phase with explicit contrast remapping.
