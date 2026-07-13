# Halloy Theme Phase 1 — Inventory and Parser Foundation

## Goal

Establish the complete, tested Halloy parsing and translation foundation without changing visible frontend behavior. The result of this phase is a stable compatibility contract and a pure-Python subsystem that can load a Halloy TOML file and deterministically produce a complete, validated `AinewsTheme` plus CSS custom properties.

## Inputs and constraints

- The repository root contains an uncommitted `themes/` directory with the Halloy theme collection. Treat it as an implementation input, not the final runtime location.
- `ainews` already depends on Python 3.12, Pydantic 2, and `tomllib` is available in the standard library.
- The current frontend palette contract lives primarily in `static/css/variables.css`.
- Do not modify the current browser theme selector or remove dark/light behavior in this phase.
- Do not expose arbitrary Halloy fields directly as CSS.

## Workstream 1 — Inventory and provenance

1. Enumerate every `.toml` file under the root `themes/` directory.
2. For each file, capture:
   - source filename;
   - proposed normalized identifier;
   - display name;
   - inferred light/dark appearance;
   - Halloy sections present;
   - unusual color formats or missing fields;
   - upstream source and license information where available;
   - redistribution status.
3. Detect duplicate identifiers after normalization and duplicate content hashes.
4. Identify themes that cannot be redistributed or whose provenance is unclear; exclude them from the future bundled set until resolved.
5. Add a concise inventory/provenance document or manifest in the implementation commit. Do not commit the source theme collection blindly before this review.

Identifier normalization rules must be explicit and deterministic. Recommended behavior:

- derive from the filename stem;
- Unicode-normalize;
- lowercase;
- replace runs of non-alphanumeric characters with `-`;
- trim leading/trailing separators;
- reject empty results;
- reject collisions rather than silently renaming.

Display names remain separate and may include spaces, punctuation, and Unicode.

## Workstream 2 — Define the Halloy compatibility contract

Document the supported source schema. At minimum parse these common fields:

```toml
[general]
background
border
horizontal_rule
unread_indicator

[text]
primary
secondary
tertiary
success
error

[buffer]
action
background
background_text_input
background_title_bar
border
border_selected
code
highlight
nickname
selection
timestamp
topic
url

[buttons.primary]
background
background_hover
background_selected
background_selected_hover
```

Requirements:

- unknown sections and keys are ignored;
- missing optional fields receive typed defaults or are derived later;
- nested `buffer.server_messages` data is ignored rather than coerced into scalar fields;
- multiple `buttons.*` tables may be parsed, with `primary` preferred by translation;
- invalid root structure and invalid scalar types are reported as typed validation errors;
- parsing does not accept arbitrary CSS expressions.

## Workstream 3 — Add the theme package

Recommended structure:

```text
services/themes/
├── __init__.py
├── colors.py
├── errors.py
├── halloy.py
├── models.py
└── translate.py
```

Responsibilities:

- `errors.py`: typed parsing, validation, translation, and contrast exceptions.
- `models.py`: Halloy section models, complete `HalloyTheme`, `AinewsTheme`, diagnostics structures.
- `halloy.py`: bounded file loading, TOML parsing, source normalization.
- `colors.py`: color parsing and derivation primitives.
- `translate.py`: Halloy-to-`AinewsTheme` mapping and CSS serialization.

Keep Flask, request, template, and configuration imports out of this package. The foundation should be independently testable.

## Workstream 4 — Typed Halloy models

Use Pydantic models with `extra="ignore"` for forward compatibility. Model defaults should be safe and documented, but translation should retain diagnostics indicating when defaults were used.

Implement helpers equivalent in spirit to EggPool's Halloy parser:

- convert scalar mappings into `dict[str, str]` only after validating acceptable source types;
- extract nested button tables;
- exclude nested non-color buffer structures;
- parse from `Path` and package-resource-compatible streams where practical;
- cap file bytes before parsing, with the cap supplied by caller or a safe default.

Do not catch all exceptions and return a default theme inside the parser. The parser should raise typed errors; fallback belongs to the future registry layer.

## Workstream 5 — Color primitives

Implement and test:

- `#RRGGBB` parsing;
- `#RRGGBBAA` parsing with explicit alpha handling;
- canonical lowercase serialization;
- RGB and RGBA conversion;
- relative luminance;
- contrast ratio;
- HSL/HLS lightness calculation;
- bounded lightness adjustment;
- color mixing;
- alpha-composited color generation against transparent output;
- safe foreground selection for a background;
- deterministic derived hover/border variants.

Reject:

- shorthand hex unless explicitly added and tested;
- named colors;
- `var(...)`;
- `url(...)`;
- gradients;
- malformed or oversized strings;
- non-string values.

No unvalidated source value may reach `to_css_variables()`.

## Workstream 6 — Define `AinewsTheme`

Create a strict Pydantic model with `extra="forbid"`. It should include at least:

### Surfaces

- `bg_primary`
- `bg_secondary`
- `bg_tertiary`
- `bg_subtle`
- `bg_input`
- `bg_hover`
- `bg_selected`

### Borders

- `border`
- `border_light`
- `border_focus`

### Text

- `text_primary`
- `text_secondary`
- `text_muted`
- `text_dim`
- `text_inverse`

### Interactive

- `accent`
- `accent_hover`
- `accent_active`
- `link`
- `link_hover`
- `focus_ring`

### Semantic status

- `success`
- `warning`
- `error`
- `info`

### Category colors

- `category_ai`
- `category_privacy`
- `category_security`
- `category_programming`
- `category_hardware`
- `category_other`

### Other palette values

- `skeleton_base`
- `skeleton_shine`
- `selection`
- `overlay`
- `appearance` (`light` or `dark`)

Alpha variants may be stored fields or generated properties, but CSS output must include all existing accent/status alpha variables.

## Workstream 7 — Translation rules

Implement a pure function similar to:

```python
def translate_theme(halloy: HalloyTheme) -> ThemeTranslationResult:
    ...
```

The result should include:

- `theme: AinewsTheme`;
- `warnings: tuple[ThemeDiagnostic, ...]`;
- metadata indicating which values were direct, defaulted, or derived.

Baseline mappings:

- `general.background` -> primary/chrome background baseline;
- `buffer.background` -> secondary/content surface;
- `buffer.background_title_bar` -> tertiary surface;
- `buffer.background_text_input` -> input/subtle surface;
- `general.border` -> default border;
- `buffer.border_selected` -> focus border;
- `text.primary` -> primary text;
- `text.secondary` -> secondary text;
- `buffer.topic` -> muted text;
- `buffer.timestamp` -> dim text;
- `buffer.url` -> link/accent;
- `text.tertiary` -> secondary accent/category AI;
- `text.success` -> success;
- `buffer.action` -> warning;
- `text.error` -> error;
- `buffer.highlight` -> hover surface;
- `buffer.selection` -> selected/selection surface.

Detect light versus dark by measured background luminance or lightness, not names.

Derive missing values narrowly. Preserve palette identity; do not globally force every theme toward the current GitHub-like palette.

## Workstream 8 — Contrast policy

Calculate contrast for:

- primary text versus page background;
- body text versus card/content background;
- link versus page/content backgrounds;
- button text versus button/accent background;
- focus ring versus common surfaces;
- error/success text where used semantically.

Classify findings:

- error: invalid/unreadable core pairing that cannot be safely derived;
- warning: marginal contrast or decorative issue;
- derived: source value replaced by a deterministic safe foreground.

Keep the policy conservative in this phase. Critical primary text/control failures may reject translation. Decorative category colors should not reject a theme when not the sole carrier of meaning.

## Workstream 9 — CSS serialization

Implement deterministic serialization that emits a complete `:root` block using existing `ainews` variable names, including:

- background, border, text, accent, and status variables;
- skeleton variables;
- derived alpha variants;
- semantic aliases already consumed by the frontend;
- optional metadata comments only if stable and useful.

Properties must have a fixed order. Output must be byte-stable for identical input to support ETags and golden tests.

Do not emit layout, font, spacing, radius, z-index, or animation variables from themes.

## Test plan

Add focused tests covering:

1. full representative Halloy file;
2. minimal valid file;
3. unknown sections and fields;
4. missing optional sections;
5. nested `buttons.*` extraction;
6. nested `buffer.server_messages` exclusion;
7. six-digit and eight-digit colors;
8. uppercase normalization;
9. invalid hex, non-string values, empty files, invalid TOML;
10. bounded file size;
11. light/dark classification;
12. direct and derived token mappings;
13. complete token coverage;
14. deterministic CSS output;
15. alpha values tracking the active accent/status colors;
16. contrast warnings and critical failures;
17. no Flask application context required.

Use several materially different fixtures: dark, light, warm, low-saturation, and high-chroma.

## Validation commands

At minimum run:

```bash
.venv/bin/pytest tests/test_theme_colors.py tests/test_theme_halloy.py tests/test_theme_translate.py -q
.venv/bin/ruff check services/themes tests/test_theme_*.py
.venv/bin/mypy services/themes
```

Also run the repository's appropriate fast validation command if available.

## Deliverables

- inventory/provenance record for the root theme collection;
- documented Halloy compatibility contract;
- `services/themes` parser/translation foundation;
- strict `AinewsTheme` model;
- deterministic CSS serializer;
- representative fixtures and focused tests;
- no visible frontend behavior change.

## Acceptance criteria

- Every approved sample theme parses or has a documented exclusion reason.
- Invalid source values cannot reach CSS output.
- Translation yields a complete token set without Flask dependencies.
- CSS output is deterministic and contains all required palette variables.
- Light/dark classification and alpha derivation are tested.
- Critical contrast failures are handled explicitly.
- Existing dark/light behavior and all existing tests remain intact.
