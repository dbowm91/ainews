# Halloy Theme Phase 2 — Registry, Packaging, and Custom Theme Discovery

## Goal

Turn the pure parser/translator from Phase 1 into a production-safe, startup-built theme registry. Package approved Halloy themes with the application, support an operator-configured external theme directory, enforce external-over-bundled precedence safely, and guarantee an emergency fallback independent of TOML resources.

This phase should not yet replace the current browser selector. It establishes the runtime source of truth that later CSS delivery and UI phases will consume.

## Preconditions

- Phase 1 parser, color utilities, translator, diagnostics, and deterministic CSS serialization are complete.
- The root uncommitted `themes/` directory has been inventoried and redistribution status is known.
- Stable normalized identifiers have been assigned.
- A code-defined current-style emergency `AinewsTheme` exists or can be added here.

## Workstream 1 — Final packaged theme location

Choose an application-owned resource location that works in development, Docker, and installed artifacts. Recommended options:

```text
resources/themes/
```

or a Python package resource path such as:

```text
ainews_themes/
```

Do not depend on the repository root or current working directory at runtime. Do not place source TOML under public static hosting unless direct download is an explicit feature.

Copy only approved themes from the root input directory. Preserve upstream filenames only when they are safe and stable; runtime identity must use normalized registry IDs.

Add a manifest containing, at minimum:

- normalized ID;
- display name;
- source filename;
- appearance if known;
- provenance/license reference;
- bundled flag.

The manifest may be generated or maintained, but CI must detect missing files, duplicate IDs, and stale entries.

## Workstream 2 — Packaging and deployment inclusion

Update every relevant packaging path:

- Dockerfile and Docker build context;
- Python package/build configuration if resources are packaged;
- source distribution/wheel settings if applicable;
- release validation scripts;
- documentation inventories;
- `.dockerignore` or `.gitignore` rules that could accidentally omit themes.

Add an artifact-level test that opens the built container/package context and verifies:

- the bundled theme directory exists;
- the manifest exists;
- at least one canonical dark and one canonical light theme are included;
- all manifest entries resolve;
- no unapproved root input directory is required.

## Workstream 3 — Configuration contract

Add configuration using repository conventions. Required semantics:

- theme system enabled/disabled;
- optional external custom directory;
- custom theme allowance;
- default theme ID;
- default dark theme ID;
- default light theme ID;
- maximum theme file size;
- optional strict contrast policy.

Recommended conceptual fields:

```text
THEMES_ENABLED
THEMES_CUSTOM_DIR
THEMES_ALLOW_CUSTOM
THEMES_DEFAULT
THEMES_DEFAULT_DARK
THEMES_DEFAULT_LIGHT
THEMES_MAX_FILE_BYTES
THEMES_STRICT_CONTRAST
```

Requirements:

- defaults work without external configuration;
- relative paths are resolved according to one documented base, preferably configuration-file location or application instance path;
- a missing custom directory logs a warning and continues;
- an unreadable directory logs a redacted warning and continues;
- invalid configured default IDs are corrected through registry fallback, not fatal startup, unless repository policy explicitly makes configuration strict;
- changes require restart in the first release.

## Workstream 4 — Registry model

Add `services/themes/registry.py` with explicit immutable registry structures. Suggested models:

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
    themes: Mapping[str, RegisteredTheme]
    default_id: str
    default_dark_id: str
    default_light_id: str
```

Exact implementation may differ, but consumers must not mutate cached themes or metadata.

Registry API should include:

- `get(theme_id)` with deterministic fallback behavior;
- `get_exact(theme_id)` for validation/404 paths;
- `list_themes()` returning stable display ordering;
- `resolve_system(prefers_dark)`;
- `default_theme`/`emergency_theme` access;
- diagnostics lookup for authenticated operator surfaces.

## Workstream 5 — Bundled discovery

Use package-resource-safe traversal rather than source-checkout-relative `Path` assumptions. For each bundled entry:

1. read through a bounded stream;
2. parse and translate;
3. verify manifest ID and normalized filename behavior;
4. calculate a content digest over canonical source bytes or generated CSS;
5. store translated theme, CSS, metadata, and warnings.

Bundled theme failures should be logged prominently. Policy recommendation:

- failure of a non-default bundled theme: skip and continue;
- failure of configured default: fall through to another valid bundled theme;
- failure of all bundled themes: use emergency theme;
- CI treats any invalid bundled theme as blocking even though production runtime remains resilient.

## Workstream 6 — External directory discovery

External files must be ordinary Halloy-compatible `.toml` files. Initial policy should be flat-directory only.

Discovery rules:

- enumerate direct child `.toml` files only;
- ignore unsupported extensions;
- reject hidden/temp files if appropriate;
- cap number of files to prevent accidental resource abuse;
- cap bytes per file before TOML parsing;
- normalize identifiers from safe filename stems;
- reject normalization collisions within external files;
- parse/translate each file independently;
- skip invalid files while retaining diagnostics;
- never abort the whole registry due to one custom file.

External display names may come from a safe filename-derived label unless Halloy has a trustworthy metadata field. Do not invent a proprietary wrapper requirement.

## Workstream 7 — Path and symlink hardening

Treat custom theme paths as untrusted operator-controlled data.

Requirements:

- resolve the configured root once;
- reject any file whose resolved path is outside the root;
- define symlink policy explicitly; safest initial policy is to reject symlink files and symlink directories;
- never look up a request ID by appending it to the root path;
- all runtime lookup occurs against the prebuilt registry map;
- reject identifiers containing separators, traversal markers, nulls, control characters, or empty normalized forms;
- cap identifier and display-name lengths;
- redact absolute source paths in public diagnostics.

Add tests for `../`, absolute paths, mixed separators, percent-encoded traversal where route integration later decodes values, symlink escape, duplicate names, and Unicode normalization collisions.

## Workstream 8 — Precedence and collision behavior

Required precedence:

```text
external exact normalized ID
    overrides
bundled exact normalized ID
    overrides
emergency fallback only through default resolution
```

External overrides should replace the entire translated theme, not merge Halloy fields with the bundled file.

Collision rules:

- duplicate bundled IDs: build/CI failure;
- duplicate external IDs: skip all colliding external entries or select none, with a clear diagnostic; do not depend on filesystem enumeration order;
- external ID matching bundled: intentional override, recorded in metadata/diagnostics;
- ID matching reserved emergency identifier: reject external entry.

## Workstream 9 — Startup lifecycle and caching

Construct the registry once during application initialization and attach it through the established application service/config mechanism. Do not parse themes per request.

The registry should cache:

- parsed Halloy result;
- translated `AinewsTheme`;
- generated CSS;
- metadata;
- warnings/errors;
- list ordering;
- content digest/ETag material.

No live file watcher in this phase. Restart/reload is the refresh mechanism. Document this clearly.

If application factories are used in tests, ensure registry creation is deterministic and injectable so tests can supply temporary resource/custom directories.

## Workstream 10 — Emergency fallback

Define one complete theme in Python code, independent of TOML resources. It should closely match the current dark palette and include every required token.

Emergency behavior must work when:

- package resources are unavailable;
- manifest is malformed;
- every bundled theme fails;
- custom directory is unavailable;
- configured defaults do not exist.

The emergency theme must have a reserved ID that external files cannot override.

## Workstream 11 — Diagnostics and logging foundation

Registry build should produce structured diagnostics containing:

- theme ID when available;
- origin kind;
- error code/category;
- safe source label, not absolute path publicly;
- parser/translation warning summaries;
- whether an external override occurred;
- fallback decisions.

Logs should distinguish expected operator mistakes from internal packaged-resource failures. Avoid logging entire TOML content.

## Tests

Add tests for:

1. bundled discovery from package-like resources;
2. external discovery from a temporary directory;
3. external-over-bundled precedence;
4. duplicate bundled IDs;
5. duplicate external IDs independent of enumeration order;
6. invalid external theme isolation;
7. missing/unreadable external directory;
8. unsupported extensions and nested directories;
9. file count and byte limits;
10. path traversal and absolute-path rejection;
11. symlink file/directory escape;
12. Unicode normalization collisions;
13. invalid configured default fallback;
14. all-resource failure -> emergency theme;
15. immutable registry/list results;
16. no repeated parsing after startup;
17. stable ordering and metadata;
18. Docker/package inclusion checks.

## Validation

Run focused tests plus:

```bash
.venv/bin/pytest tests/test_theme_registry.py tests/test_theme_packaging.py -q
.venv/bin/ruff check services/themes tests/test_theme_registry.py tests/test_theme_packaging.py
.venv/bin/mypy services/themes
```

Run a Docker build or the repository's release validation path that proves resources are included.

## Deliverables

- approved bundled theme resource set and manifest;
- theme configuration fields and validation;
- immutable startup-built `ThemeRegistry`;
- custom directory discovery and override behavior;
- safe path/symlink/identifier handling;
- complete cached CSS and metadata entries;
- emergency theme;
- packaging and registry tests;
- restart-required semantics documented.

## Acceptance criteria

- Runtime does not depend on the root uncommitted `themes/` directory.
- Bundled themes are present in Docker/release artifacts.
- Custom Halloy files load from an explicitly configured directory.
- Invalid custom files cannot abort startup.
- External overrides are deterministic and visible in diagnostics.
- Request-time lookup never touches arbitrary filesystem paths.
- Themes are parsed once per application process.
- All-default failure resolves to the emergency palette.
- No visible selector behavior changes yet.
