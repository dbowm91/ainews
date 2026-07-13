# Halloy Theme Phase 5 — Operator Support, Validation, Diagnostics, and Documentation

## Goal

Finish the supported custom-theme contract for operators and theme authors. Add a first-class validation command, authenticated diagnostics, accessibility checks, deployment/configuration documentation, and blocking CI validation for the bundled Halloy set.

This phase assumes themes can already be parsed, registered, served as CSS, and selected in the browser. It converts that capability into a maintainable, supportable feature.

## Preconditions

- The bundled theme resource set and manifest exist.
- External theme discovery and precedence are implemented.
- Registry entries include origin, appearance, warnings, digest, and translated CSS.
- Browser selection can distinguish built-in and custom themes.
- Theme CSS route and fallback behavior are stable.

## Workstream 1 — Add a theme validation CLI/script

Add a command consistent with repository conventions, for example:

```bash
python scripts/validate_themes.py
```

Required modes:

```bash
# Validate all packaged themes
python scripts/validate_themes.py --bundled

# Validate a custom directory
python scripts/validate_themes.py --directory /path/to/themes

# Validate one Halloy file
python scripts/validate_themes.py --file /path/to/theme.toml

# Emit translated CSS for inspection
python scripts/validate_themes.py --file theme.toml --print-css

# Machine-readable diagnostics
python scripts/validate_themes.py --bundled --format json
```

The exact interface may use Click/argparse according to repository practice.

The validator must reuse production parser/translator/registry helpers. Do not duplicate compatibility logic in the script.

Exit behavior:

- `0`: all requested themes valid; warnings allowed unless strict mode;
- nonzero: invalid theme, identifier collision, unreadable input, critical contrast failure, or packaged-manifest mismatch;
- `--strict`: warnings designated as policy failures also produce nonzero status.

Output should distinguish:

- source/identifier error;
- TOML parsing error;
- invalid color;
- missing/defaulted field;
- derived value;
- contrast warning;
- critical contrast failure;
- duplicate normalized ID;
- external override;
- packaging/manifest failure.

Never print secrets or unrelated configuration. Absolute file paths are acceptable in local CLI output but must not be reused in public web diagnostics.

## Workstream 2 — Add authenticated diagnostics

Expose registry health to administrators through one or both of:

- an authenticated admin page;
- an authenticated JSON endpoint.

Suggested data:

```text
theme_count_total
theme_count_bundled
theme_count_custom
default_id
default_dark_id
default_light_id
emergency_fallback_active
registry_built_at/process startup marker
```

Per-theme diagnostics:

```text
id
display_name
appearance
origin
valid/registered state
warning count
warning codes
content digest prefix
overrides bundled ID: yes/no
```

Excluded/invalid custom files may be shown by safe source label and error category. Do not expose absolute paths, stack traces, full TOML content, or generated CSS by default.

The endpoint must follow existing admin authentication, CSRF, and cache-control conventions. Diagnostics should not be public merely because the public news frontend is public.

## Workstream 3 — Contrast and accessibility validation

Implement reusable checks over translated `AinewsTheme` values.

Required pairings:

- primary text / page background;
- body text / card or content background;
- secondary text / content background;
- muted metadata / content background when metadata remains meaningful;
- link / page and content backgrounds;
- accent/button foreground / accent/button background;
- focus ring / page, card, and input surfaces;
- error text / relevant surface;
- success text / relevant surface;
- input text / input background;
- selected text / selected surface if applicable.

Use WCAG contrast calculations and document policy thresholds. Distinguish normal text, large text, and non-text controls.

Policy recommendation:

- invalid CSS color: reject;
- unreadable primary/body/control foreground with no safe derivation: reject;
- successful deterministic safe foreground derivation: register with diagnostic;
- marginal secondary/muted contrast: warning unless information is otherwise inaccessible;
- decorative category accent weakness: warning only when color is not the sole cue.

Add checks proving status/category distinctions also include labels/icons/text and do not depend solely on color.

## Workstream 4 — Bundled-theme CI gate

Add a blocking CI/release validation step that:

1. loads the packaged manifest;
2. resolves every bundled file;
3. parses and translates each theme;
4. asserts complete CSS token output;
5. detects duplicate IDs and manifest drift;
6. runs critical contrast policy;
7. verifies designated default light/dark themes exist and match appearance classification;
8. verifies no packaged theme unexpectedly falls back to emergency;
9. verifies theme count is nonzero and within expected bounds;
10. optionally stores JSON diagnostics as an artifact on failure.

Integrate with `scripts/validate_release.sh` or the current equivalent so local release validation and CI remain aligned.

Do not make external operator themes part of CI; only production parser tests and bundled resources are blocking.

## Workstream 5 — Custom directory operational contract

Document and test:

- configured path resolution;
- flat `.toml` file requirement;
- read-only directory support;
- restart requirement;
- external-over-bundled precedence;
- duplicate-ID behavior;
- invalid-file isolation;
- maximum file size/count;
- symlink policy;
- filename-to-ID normalization;
- how removed themes affect stored browser preferences;
- how to inspect diagnostics;
- how to validate before restart.

Provide Docker/Compose examples following repository deployment layout, conceptually:

```yaml
services:
  ainews:
    volumes:
      - ./themes:/config/ainews/themes:ro
```

Use the actual configuration and persistent-data paths selected by implementation. Do not document a fictional path.

Clarify whether custom themes should be included in backup procedures. Since themes are operator-managed files, backups should either include the configured directory or explicitly state that it is external configuration requiring separate backup.

## Workstream 6 — Theme authoring guide

Add a focused guide covering:

- supported Halloy tables and fields;
- ignored/unsupported fields;
- accepted `#RRGGBB` and `#RRGGBBAA` formats;
- defaults and derivation behavior;
- identifier derivation from filename;
- display-name behavior;
- light/dark classification;
- contrast requirements;
- validation command;
- external override semantics;
- restart and browser-cache behavior.

Include a minimal valid Halloy-compatible example:

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

Do not require an `ainews`-specific wrapper or arbitrary CSS section.

## Workstream 7 — Reader-facing documentation

Document:

- where the selector is located;
- system mode behavior;
- explicit theme behavior;
- device/browser-local persistence;
- how to reset preference;
- what happens when a custom theme is removed;
- that theme choice does not affect content or account data.

Keep this concise and suitable for a public user help surface.

## Workstream 8 — Frontend architecture documentation

Update `docs/frontend.md` with:

- `services/themes` module structure;
- bundled resource location and manifest;
- registry startup lifecycle;
- external directory precedence;
- CSS route and cache behavior;
- structural versus palette token layers;
- browser preference/bootstrap lifecycle;
- HTMX constraints;
- generated asset commands;
- security invariants;
- focused test commands;
- restart requirement.

Update configuration/deployment/security/testing/release docs where relevant. Avoid duplicating the complete contract in many files; establish one canonical guide and link to it.

## Workstream 9 — Theme source provenance documentation

For bundled themes, retain a manifest or document recording:

- theme name/ID;
- upstream project/source;
- license;
- local source filename;
- any local modifications;
- date/version snapshot if available.

Ensure required licenses/notices are included in release artifacts. Do not claim all Halloy themes share one license without verification.

If some root themes were excluded, document the exclusion reason internally rather than silently dropping them.

## Workstream 10 — Operational logging and troubleshooting

Define stable diagnostic codes such as:

```text
THEME_PARSE_INVALID_TOML
THEME_COLOR_INVALID
THEME_ID_COLLISION
THEME_PATH_OUTSIDE_ROOT
THEME_SYMLINK_REJECTED
THEME_CONTRAST_WARNING
THEME_CONTRAST_CRITICAL
THEME_DEFAULT_MISSING
THEME_EXTERNAL_OVERRIDE
THEME_RESOURCE_MISSING
THEME_EMERGENCY_FALLBACK
```

Use codes in CLI output, logs, tests, and admin diagnostics where practical. This makes support less dependent on exact prose.

Troubleshooting guide should cover:

- custom theme does not appear;
- theme rejected as invalid;
- duplicate identifier;
- stale browser preference;
- CSS appears cached after file replacement;
- default light/dark misclassification;
- missing mounted directory;
- permissions/read-only behavior;
- emergency fallback active.

## Workstream 11 — Performance and limits reporting

The validator and diagnostics should expose enough data to detect accidental bloat:

- number of themes;
- total source bytes;
- total generated CSS bytes;
- registry build duration in tests/diagnostic logs;
- warnings/errors count.

Do not add high-cardinality public metrics per theme unless operationally justified. A startup log summary is sufficient initially.

Set and document limits for:

- max file bytes;
- max external file count;
- max identifier length;
- max display-name length;
- max diagnostics retained.

## Tests

Add tests for:

1. CLI validates bundled set successfully;
2. single-file valid/invalid exit codes;
3. directory collision and invalid-file reporting;
4. JSON output schema and safe serialization;
5. `--strict` warning behavior;
6. CSS print mode emits only validated output;
7. admin diagnostics require authentication;
8. diagnostics redact absolute paths and TOML content;
9. bundled/custom counts and override markers;
10. emergency fallback reporting;
11. every required contrast pairing;
12. safe derivation versus rejection policy;
13. manifest/resource drift;
14. default light/dark existence and classification;
15. license/provenance manifest completeness where machine-checkable;
16. Docker read-only custom-directory workflow;
17. restart semantics/documented non-live behavior;
18. release validation invokes bundled-theme check.

## Validation commands

Run:

```bash
.venv/bin/python scripts/validate_themes.py --bundled --strict
.venv/bin/pytest tests/test_theme_validation_cli.py tests/test_theme_diagnostics.py tests/test_theme_accessibility.py -q
.venv/bin/ruff check scripts/validate_themes.py services/themes tests/test_theme_*.py
.venv/bin/mypy scripts/validate_themes.py services/themes
./scripts/validate_release.sh --fast
```

Before closure, run full release validation, Docker build, and Compose smoke paths.

## Deliverables

- production-reused theme validation command;
- authenticated registry diagnostics;
- documented contrast/accessibility policy;
- blocking bundled-theme CI/release gate;
- custom-directory operator guide;
- Halloy-compatible theme author guide;
- reader preference help;
- updated frontend/configuration/deployment/security/testing docs;
- provenance/license manifest and notices;
- stable diagnostic codes and troubleshooting guide.

## Acceptance criteria

- Operators can validate a Halloy file or directory before deployment.
- All bundled themes pass a blocking CI/release validation command.
- Critical contrast failures are detected consistently by production and CLI code.
- Admin diagnostics show registry/default/override state without leaking paths.
- A read-only custom theme mount is documented and tested.
- Theme authors can create compatible files without learning a proprietary format.
- Bundled theme provenance and redistribution notices are complete.
- Release validation proves themes are packaged and defaults are valid.
- Documentation accurately reflects restart, precedence, fallback, and browser persistence behavior.
