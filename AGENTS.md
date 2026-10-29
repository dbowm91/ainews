# AI News Agent Instructions

This document provides instructions and context for agents working on the AI News project.

## Core Principles

1.  **Fail-Closed Security:** In production, any security check failure (e.g., insecure permissions, missing secrets) MUST prevent the application from starting.
2.  **Clean Layering:**
    *   **Adapters** should NOT contain business logic or import from `services`.
    *   **Services** should NOT import from `Adapters` (use `schemas` or `models` for shared types).
    *   **Utils** should contain pure helper functions with minimal dependencies.
3.  **Test-Driven Correctness:** Every bug fix MUST include a reproduction test case. Every new feature MUST have unit tests targeting 80% coverage.
4.  **Type Safety:** Aim for 0 Mypy errors. Use explicit typing and avoid `Any` where possible.
5.  **Performance:** Be mindful of LLM latency. Use caching, batching, and async patterns where appropriate.

## Milestone G Closure Status

Milestone G (frontend rendering correctness and visual identity) has been implemented and closed:
- **Scope:** Public feed, topic and tag feeds, article detail page, RSS feed, error pages, service worker, theme stylesheet route, and the shipped stylesheets
- **Defects closed:** 5 blockers, 10 major, 9 minor from `docs/ui-review-2026-10.md`, plus 10 defects found during verification
- **Test suite:** 4,679 passed, 6 skipped (browser-marked tests skip without a Chromium binary)
- **New test modules:** `tests/test_critical_css_build.py`, `tests/test_cascade_layers.py`, `tests/test_theme_precedence.py`, `tests/test_palette_contrast.py`, `tests/test_ui_static_contracts.py`, `tests/test_frontend_rendering_browser.py`, `tests/test_response_cache_scope.py`, `tests/test_raw_item_schema.py`, `tests/test_celery_app_cache.py`, `tests/test_config_cache_key.py`
- **Closure matrix:** docs/frontend-rendering-closure.md
- **Contracts:** docs/halloy-theme-contract.md, docs/frontend.md, docs/themes-inventory.md
- **CI:** the browser suite runs in the `theme-browser-smoke` job, which installs Chromium
- **Deferred items:** admin interface redesign, server-side theme persistence, real-time rail status, live theme reload, `static/js/bundle.min.js` disposition

## Release 5 Closure Status

Release 5 closure work has been completed with the following results:
- **Baseline:** Commit 330e9fd4760207256c058f762376a9a11a99bb10 (2026-07-17)
- **Closure commit:** e34adfc (2026-07-17)
- **Test suite:** 4,471 passed, 1 pre-existing (pipeline_logs fixture), 5 skipped
- **Shell tests:** 235 passed (147 installer + 34 E2E + 54 logrotate real-world)
- **Mypy:** Clean (scripts/ excluded from type checking)
- **Ruff:** 5 non-blocking warnings (3 C901 + 1 BLE001 + 1 test C901)
- **Security review:** 0 critical, 0 high, 5 medium (fixed), 4 low (accepted)
- **JSON contracts:** schema_version: 1 on 12 command families, 48 contract tests
- **Closure matrix:** docs/config-cli-roadmap-closure.md
- **Baseline evidence:** docs/config-cli-release-5-baseline.md
- **Security review:** docs/config-cli-security-review.md
- **Migration guide:** docs/migrating-repository-install.md
- **Final closure:** docs/config-cli-release-5-closure.md
- **Deferred items:** backup.py decomposition (tests pass), clean-host lifecycle (needs CI), systemd PID 1 validation (needs container)

## Project Structure

*   `app.py`: Application factory and configuration.
*   `models/`: Database models package (SQLAlchemy). Contains `source.py`, `article.py`, `tag.py`, `newsletter.py`, `pipeline.py`, etc.
*   `services/`: Business logic, LLM interaction, third-party service wrappers. `services/auto_review.py` holds the auto-review mode: the switch, the single routing decision, the single approval primitive, and the queue drain.
*   `adapters/`: Infrastructure-specific code (RSS, Web, API). Should NOT import from `services/`.
*   `tasks/`: Celery tasks for the newsletter pipeline.
*   `routes/`: Flask blueprints for public and admin interfaces.
*   `schemas/`: Pydantic models for validation and serialization.
*   `utils/`: Pure helper functions with minimal dependencies (e.g., `utils/url.py` for URL normalization).
*   `ainews_config/`: Configuration engine package (CLI-independent). Contains path resolver, field registry, loader, validator, and transactional writer.
*   `ainews_cli/`: Operator CLI package (Typer-based). Entry point: `ainews_cli.main:app`. Commands: version, onboard, providers (list/add/test/models/set-default/assign/remove), sources (list/show/add/update/enable/disable/remove/test/import-opml/export-opml), topics (list/show/add/update/remove), pipeline (show/validate/set-profile/assign/unassign/diff), start/stop/restart/status/logs/health/smoke, config (path/show/check/get/set/set-secret/unset/diff/rollback), doctor, update (check/plan/apply/rollback/status), channel (show/set), uninstall. Subpackages: `providers/` (adapter protocol, registry, built-in adapters), `sources/` (adapter protocol, registry, OPML, built-in adapters), `topics/` (models, commands), `pipeline/` (models, commands), `lifecycle/` (Docker Compose/bare metal drivers), `doctor/` (diagnostic checks), `update/` (GitHub API client, update engine, state machine), `channel/` (release channel management), `uninstall/` (safe removal with path ownership validation).

## Known Issues & Gotchas

### Database Setup
Always ensure `import models` happens before `db.create_all()` in the app context to ensure all tables are created.

### Rate Limiter Pattern
The rate limiter uses Redis slots. Always release slots in a `finally` block to avoid leaks. The `run_stage()` function resolves provider/model before acquiring limiter resources, ensuring correct release on early return.
- Always use `provider_id or rc.provider` (the actual provider used) as fallback when releasing
- Always use `model or rc.model` (the actual model used) as fallback when releasing

### URL Validation Layering
SSRF protection (`validate_url_safe`, `UnsafeURLError`) is in `utils/url.py`. Adapters import from `utils/url.py` for clean layering. `services/url.py` has duplicate implementations and should not be imported by adapters.

### URL Validation Duplication
`utils/url.py` and `services/url.py` have duplicate SSRF protection implementations. `services/url.py` re-exports `TRACKING_PARAMS`, `normalize_title`, and `normalize_url` from `utils/url.py`, but duplicates `UnsafeURLError`, `_resolve_and_check`, and `validate_url_safe` with its own config support. Use `utils/url.py` for adapters (clean layering), `services/url.py` for services (has config support).

### utils/url.py Not Pure
Despite docstring claims, `utils/url.py` has global mutable state (`_dns_cache`, `_dns_cache_lock`, `_dns_executor`). Don't assume pure function behavior. `validate_url_safe()` performs actual DNS resolution with caching.

### validate_url_safe Exception Types
`validate_url_safe()` raises `UnsafeURLError` for all invalid URL cases (empty URL, unsupported scheme, missing hostname, DNS failure, blocked IP). `UnsafeURLError` inherits from `ValueError`, so callers can catch either type.

### Context Window
LLM prompts can grow large. Use the token budgeting and `summarize_context()` caching in `services/prompts.py`.

### Linting
We use `ruff` for linting. Run `ruff check . --exclude .venv` before committing.

### Mypy
We use `mypy` for type checking (required in CI). Legacy modules (`models/`, `adapters/`, `tasks/`, `routes/`, `services/subagent/`, `services/llm/`, `services/search/`) have `ignore_errors = true` overrides. Focus on new code and use explicit typing. Run `mypy . --exclude .venv` before committing.

### 2FA Backup Codes
Admin users with 2FA enabled have 8 backup codes stored as JSON. Use `verify_backup_code()` and `consume_backup_code()` from `services/totp.py`.

### MagicMock in Tests
Some pipeline tests fail due to MagicMock objects being JSON serialized - this is a test infrastructure issue, not a code bug. When patching functions, patch where they're looked up at runtime, not where they're defined.

### Safe Fetch Test Mocking
Tests in `tests/test_safe_fetch.py` use `_patch_for_local_server()` to bypass SSRF validation for local test servers (since loopback IPs are blocked by default). The `_patch_for_redirect_test()` variant lets `validate_url_safe()` run for redirect targets while bypassing initial URL validation. DNS cache is cleared before/after each test via the `_clear_dns_cache` autouse fixture in `conftest.py`.

Obsolete `socket.create_connection` monkeypatch tests have been renamed/updated to verify transport-layer pinning directly (e.g., `test_adapter_does_not_mutate_global_socket_state`, `test_socket_create_connection_not_patched`). Connection-layer HTTPS tests (`test_https_connects_to_pinned_ip_preserves_sni`, `test_https_host_header_uses_original_hostname`, `test_https_non_default_port_in_host_header`) verify that HTTPS connections use pinned IPs while preserving the original hostname for SNI.

### Safe Fetch Coding Guidance
All HTTP fetching for untrusted URLs must go through `safe_fetch_url()` in `services/safe_fetch.py`. Never call `trafilatura.fetch_url()`, `requests.get()`, `httpx.get()`, `urlopen()`, or `urllib.request` directly for untrusted content. Never monkeypatch `socket.create_connection` or `urllib3.util.connection.create_connection` — safe fetch uses thread-safe custom urllib3 connection classes (`PinnedHTTPConnection`, `PinnedHTTPSConnection`) instead. The release checklist `rg` pattern catches violations. `services/content_extractor.py` demonstrates the correct integration pattern: lazy import of `safe_fetch_url`, custom timeout and byte limits passed via kwargs, and proper exception handling for `UnsafeFetchError` and `SafeFetchError`.

`PinnedIPAdapter` stores `original_port` and `scheme` alongside the pinned IP and original hostname. The `Host` header is set per-request in `send()`: non-default ports (e.g., `example.com:8080`) are included; default ports (80 for HTTP, 443 for HTTPS) are omitted. Each redirect hop creates a fresh `requests.Session` that is closed in a `finally` block to prevent resource leaks.

### Safe Fetch DNS Resolution Policy
The safe fetch client uses a fail-closed DNS resolution policy:
- ALL resolved IPs must pass validation (no partial acceptance)
- DNS is resolved once per request and cached with TTL
- Connection pinning prevents TOCTOU DNS rebinding attacks
- Thread-safe custom urllib3 connection classes (`PinnedHTTPConnection`, `PinnedHTTPSConnection`) connect to validated IPs without process-global socket monkeypatching
- All resolved IPs are recorded for audit trail
- See `services/safe_fetch.py` module docstring for full details

### PipelineLog meta field
The PipelineLog model uses `meta` (not `metadata`) for JSON field due to SQLAlchemy reserved name restriction.

### Newsletter Associations
`newsletter_articles` and `newsletter_subscribers` association tables exist in `models/newsletter.py` with many-to-many relationships.

### Tasks→Services Layer
Tasks layer IS allowed to import from services layer. This is not a layer violation - tasks are orchestrators that use business logic. The layer restriction is: Adapters cannot import from Services.

### Production Config Validation
`ProductionConfig.validate()` (config.py:320-336) uses `ConfigValidationResult` to accumulate all validation errors and raise a single `RuntimeError`. Helpers: `_validate_debug()`, `_validate_session_security()`, `_validate_secrets()`, `_validate_llm_providers()`. LLM provider validation is fail-closed — catches `FileNotFoundError` and generic `Exception` as validation issues (not silent warnings). `_validate_llm_providers()` tracks `valid_provider_ids` and `_validate_default_provider()` verifies the default provider's config is valid (not just enabled). Tests in `tests/test_production_config.py` (56 tests). To add new validation: add a helper function that calls `result.add(field, message, fix_hint)` and call it from `ProductionConfig.validate()`.

### Theme CSS Variable Naming
Both old (`--green`, `--accent-dim`) and new (`--success`, `--accent-active`) variable names are emitted by `to_css_variables()`. Components should prefer the semantic names but legacy names remain available. The `--accent-dim` alias maps to `--accent-active`.

### Category Badge Alpha Variables
Category badges use `--category-{name}-alpha-{15,40}` variables. These are generated by `to_css_variables()` from the theme's category colors. The 15% variant is for backgrounds, 40% for borders.

### Theme Route Registration
The `themes_bp` blueprint is registered in `app.py:_register_blueprints()` BEFORE `public_bp` to ensure `/assets/themes/` paths take precedence.

### Cascade Contract
The inline critical stylesheet is wrapped in `@layer reset { … }` in `templates/base.html` and `templates/base_admin.html`, and the theme `<link>` is placed AFTER it. The theme stylesheet stays unlayered so it beats the layered fallback palette. The critical sheet defines no palette token: `static/css/variables.css` is the only shipped palette source, and `static/css/style.css` declares the layer order `reset, variables, layout, components, pages, utilities`.

`scripts/build_critical_css.py` must emit a brace-balanced stylesheet and fails the build otherwise. Run it after every change to `static/css/critical.css`, and run `scripts/build_assets.py css` after every change to any stylesheet. Both outputs are committed.

### Rendered-Document Cache
The public routes cache their rendered HTML in `services/cache.py`. The cache namespace is scoped to a hash of the database URI, so two deployments sharing a Redis instance cannot read each other's documents. The testing configuration sets `RESPONSE_CACHE_ENABLED = False`. The in-process layer expires within `L1_CACHE_TTL` seconds (default 5) so that an invalidation applied by another worker becomes visible promptly.

### Configuration Cache Keys
The configuration cache in `services/config_cache.py` is shared by every process on the host. A cache key must therefore identify the source file, not only the kind of configuration — use `schemas.common.config_cache_key(name, path)`. A key that names only the kind lets one file be served in place of another: a process pointing `LLM_PROVIDERS_FILE` at a different providers.yaml would be served the repository's.

### Theme Subsystem (services/themes/)
- **Location:** `services/themes/` — parser foundation for Halloy TOML themes.
- **Public API:** `load_halloy_theme()`, `parse_halloy_toml()`, `translate_theme()`, `detect_appearance()`, `to_css_variables()`, `classify_contrast_findings()`. Re-exported from `services/themes/__init__.py`.
- **DO NOT import Flask into `services/themes/`.** The package is independently testable with zero framework dependencies.
- **Invalid source values cannot reach CSS output.** `parse_hex_color()` rejects shorthand hex, named colors, `var()`, `url()`, gradients — only `#RRGGBB` and `#RRGGBBAA` are accepted. All rejections raise `ThemeParseError`.
- **Generated CSS is palette-only.** `to_css_variables()` emits only a `:root` block with custom property definitions. No selectors, media queries, or other CSS rules. Structural tokens live in `static/css/variables.css`.
- **Translation is pure and deterministic.** `translate_theme()` and `to_css_variables()` have no I/O, no network, no database. Same input always produces same output.
- **256 KB file size cap** (`MAX_HALLOY_FILE_BYTES`). Enforced at both raw bytes and file stat.
- **Strict `AinewsTheme`** (`extra="forbid"`) catches unexpected tokens. Halloy models are tolerant (`extra="ignore"`).
- **Contrast policy:** Primary text vs primary bg < 4.5 is a fatal `ThemeContrastError`. Other contrast issues are non-fatal `ThemeDiagnostic(WARNING)`.
- **Strict validation policy:** `--strict` only promotes warnings in `STRICT_PROMOTABLE_CODES` frozenset: `THEME_CONTRAST_CRITICAL`, `THEME_REGISTRY_EMPTY`, `THEME_BUNDLED_EMPTY`, `THEME_MANIFEST_DRIFT`, `THEME_DEFAULT_MISSING`. Advisory contrast warnings (644 AAA-threshold pairings) remain non-blocking under `--strict`. Helpers: `is_fatal_diagnostic()`, `is_strict_promotable()`, `is_advisory_diagnostic()` in `services/themes/errors.py`.
- See `docs/halloy-theme-contract.md` for the full source schema, translation rules, and CSS output contract.
- See `docs/themes-inventory.md` for the theme collection inventory and provenance review.

### Theme Subsystem Phase 2 — Registry, Packaging, Custom Themes
- **Bundled location:** `resources/themes/` is a Python package containing the manifest and bundled `.toml` files (no longer the root uncommitted `themes/`).
- **Manifest:** `resources/themes/manifest.json` is the source of truth for bundled theme metadata; `services/themes/manifest.py` defines the Pydantic-style schema.
- **Build path:** `services/themes/registry.py` exposes `ThemeRegistry`, `RegisteredTheme`, `ThemeOrigin`, `RegistryDiagnostics`, and the `build_registry(bundled, settings)` factory. Strictly pure Python — never imports Flask.
- **Flask bridge:** `services/themes/loader.py` (the only Flask-aware module in the package) reads bundled themes via `importlib.resources.files()` with a filesystem fallback, then attaches the registry to `app.extensions['theme_registry']`. Use `build_app_registry(app)` from `create_app()`.
- **Configuration:** `THEMES_ENABLED`, `THEMES_CUSTOM_DIR`, `THEMES_ALLOW_CUSTOM`, `THEMES_DEFAULT[_DARK|_LIGHT]`, `THEMES_MAX_FILE_BYTES`, `THEMES_STRICT_CONTRAST` in `config.py:_validate_themes()`. Defaults work without any external configuration.
- **Emergency fallback:** `services/themes/emergency.py` defines a code-defined `AinewsTheme` with reserved id `__emergency__`. Always present in the registry; cannot be overridden by external themes. Used whenever TOML resources are unavailable, configured defaults fail to resolve, or every bundled theme fails to parse.
- **External precedence:** External themes with the same normalized ID replace bundled themes wholesale (no field merging). Duplicate external IDs are skipped with a diagnostic; filesystem enumeration order is irrelevant.
- **Safety:** External root must not be a symlink, individual files must not be symlinks, child paths must resolve inside the root, and identifiers are rejected if they contain separators, nulls, control characters, or exceed 64 chars. The `.dockerignore` excludes the uncommitted `themes/` directory at the repo root.
- **Restart semantics:** Themes are parsed once per application process. Operators changing the custom directory must restart. No live file watcher.
- **Tests:** `tests/test_theme_registry.py` (registry discovery + precedence) and `tests/test_theme_packaging.py` (manifest + bundled inclusion + loader integration).

### Theme CSS Delivery (Phase 3)
- **Route:** `GET /assets/themes/<theme_id>.css` — serves pre-generated CSS from the startup-built registry.
- **Blueprint:** `routes/themes.py`, registered as `themes_bp` (no auth, public GET-only).
- **Response:** `text/css; charset=utf-8`, `Cache-Control: public, max-age=300`, `ETag` from content digest, `X-Content-Type-Options: nosniff`.
- **304 handling:** Uses Werkzeug's response.make_conditional(request) for standards-compliant conditional requests (weak ETags, multiple validators, quoted values).
- **ETag is strong:** Generated via `set_etag()` without `weak=True` (strong ETag semantics).
- **404 for unknown IDs:** Uses `registry.get_exact()` — unknown IDs return 404, not fallback CSS.
- **CSS output structure:** `to_css_variables()` emits: palette variables → alpha variants → accent-dim alias → legacy status aliases → semantic aliases.
- **Palette-only output:** Generated theme CSS contains only CSS custom property definitions within a :root block. No element/class selectors, media queries, or other CSS rules are present.
- **Fallback palette:** `static/css/variables.css` defines complete fallback defaults. Theme CSS overrides palette tokens only; structural tokens (fonts, spacing, radius, z-index) remain fixed.
- **Token naming:** Components use `--green`, `--orange`, `--red`, `--purple`, `--pink` (legacy). Theme system adds `--success`, `--warning`, `--error`, `--info` (semantic). Both sets are emitted.
- **Alpha variants:** `--accent-alpha-*`, `--green-alpha-*`, `--orange-alpha-*`, `--red-alpha-*`, `--purple-alpha-*`, `--category-*-alpha-{15,40}`.
- **Category badges:** Use `--category-{name}-alpha-{15,40}` variables instead of hardcoded rgba.
- **Critical CSS:** `templates/partials/critical_css.html` is generated from `static/css/critical.css` via `scripts/build_critical_css.py`.
- **Bundled CSS:** `static/css/style.bundled.css` is generated by `scripts/build_assets.py css`.

### Theme Browser Selection (Phase 4)
- **Preference schema:** `ainews-theme-preference-v2` localStorage key with values `"system"` or `"theme:<normalized-id>"`. Legacy `ainews-theme` values (`dark`/`light`) are migrated to configured default theme IDs on first access.
- **Registry metadata:** Templates receive `theme_metadata` via context processor from `routes/themes.py`. Embedded as `#ainews-theme-metadata` JSON script tag (no nonce needed — `type="application/json"` is not executable). Includes `defaults.dark`, `defaults.light`, and per-theme `name`, `appearance`, `css_url`, `origin`. Emergency themes excluded.
- **No-flash bootstrap:** `theme.js` manages two independent stylesheet roles: a permanent application stylesheet (`#ainews-app-stylesheet`) and a replaceable palette stylesheet (`#ainews-theme-stylesheet`). Only the palette link is updated; the app link is never removed or modified. Reads/migrates preference, parses registry, resolves active theme, sets `data-theme-id`, `data-theme-appearance`, and `data-theme` on `<html>`. Falls back to static styling on failure.
- **Stylesheet controller:** `window.AinewsTheme` public API with `activate(themeId)`, `setSystem()`, `getActiveThemeId()`, `getPreference()`, `getRegistry()`, `isSystemMode()`. Atomic switching of the palette link via preload → activate → remove old. Only the palette link is swapped; the app link is permanent. Max 3 stylesheet error retries before clearing preference.
- **System mode:** Uses `matchMedia('(prefers-color-scheme: dark)')` to map OS preference to configured `default_dark`/`default_light` theme IDs. Listens for OS changes while in system mode; ignores changes for explicit selections.
- **Selector UI:** `templates/partials/theme_selector.html` — accessible popover with search, grouped options (system/built-in/custom), keyboard navigation, mobile bottom-sheet.
- **Cross-tab sync:** `storage` event listener on the v2 key. Validates incoming preferences, avoids write-back loops, falls back on unknown IDs.
- **Metadata endpoint:** `GET /api/v1/themes/metadata` returns same JSON as context processor, `Cache-Control: public, max-age=60`. No auth required.

### Theme Validation CLI
`scripts/validate_themes.py` validates themes using production helpers. Modes: `--bundled` (all packaged), `--directory DIR` (scan custom), `--file FILE` (single). Flags: `--strict` (only strict-promotable warnings fail, see `STRICT_PROMOTABLE_CODES`), `--format json` (machine-readable), `--print-css` (emit CSS). Integrated into `scripts/validate_release.sh`.

### Theme Admin Diagnostics
`GET /api/v1/themes/diagnostics` (admin-authenticated) returns registry health, per-theme validity, aggregate diagnostic counts, `built_at` (real ISO timestamp of registry construction), and `overrides_bundled` per theme. Does not expose absolute paths, TOML content, or generated CSS. Uses `Cache-Control: no-store`.

### Theme Contrast Policy
`classify_contrast_findings()` checks 14 WCAG contrast pairings. `classify_accessibility_findings()` checks category badges (3:1) and status colors (4.5:1). Critical primary text < 4.5 raises `ThemeContrastError`. All other failures are warnings.

The matrix also covers `text_secondary`, `text_muted` and `link` against `bg_primary`, `bg_secondary` and `bg_tertiary`. The diagnostic codes are `THEME_CONTRAST_SECONDARY_AA`, `THEME_CONTRAST_MUTED_AA` and `THEME_CONTRAST_ACCENT_AA`; all three are in `STRICT_PROMOTABLE_CODES`, so they warn by default and fail under `--strict` / `THEMES_STRICT_CONTRAST`.

### Theme Palette Derivation
The translation layer derives three tokens that no source TOML declares:
- `--link` carries the accent hue and is floored for legibility on the theme's own surfaces. `--accent` stays the author's brand colour because it paints chrome, not body text.
- `--accent-contrast` is the label colour of a filled accent surface. It is chosen independently of the theme's text palette, because no text token is legible on both a light and a dark accent fill. The hover fill is moved if it would make that label illegible.
- `--bg-elevated` is the lightest surface step, used for raised chrome.

`translate_theme()` also applies a readability floor to `text_secondary`, `text_muted` and `link`: only the lightness moves, hue and saturation are preserved. 33 of the 48 bundled themes therefore render a palette that differs from their source TOML; `docs/themes-inventory.md` records every adjustment.

### Theme Diagnostic Codes
Stable codes in `THEME_DIAGNOSTIC_CODES` dict in `services/themes/errors.py`. Use these in CLI output, logs, tests, and admin diagnostics. `get_diagnostic_description(code)` returns human-readable description. `STRICT_PROMOTABLE_CODES` frozenset defines which warnings become errors under `--strict` mode. `is_fatal_diagnostic()`, `is_strict_promotable()`, `is_advisory_diagnostic()` classify diagnostics by severity tier.

### Theme Comprehensive Validation (Phase 6)
- **Validation matrix**: `docs/theme-validation.md` defines the complete validation matrix with 11 theme representatives, 34 page families, 5 viewports, 16 state dimensions, and 57 risk-weighted matrix cells.
- **Lifecycle regression**: `tests/test_theme_lifecycle.py` (45 tests) validates dual-stylesheet ownership, standalone page support, CSS route integration, metadata integrity, and race condition contracts.
- **Preference validation**: `tests/test_theme_preference_validation.py` (38 tests) validates preference parsing, legacy migration, HTMX/navigation, selector state, and cross-tab sync contracts.
- **Failure recovery**: `tests/test_theme_failure_recovery.py` (73 tests) validates registry build failures, external directory pathologies, route-level failures, recovery assertions, and browser-side failure mode contracts.
- **Accessibility validation**: `tests/test_theme_accessibility_validation.py` (32 tests) validates WCAG contrast for bundled themes, category badge/status color/focus ring contrast, template ARIA attributes, keyboard navigation, reduced-motion support, and screen reader structure.
- **Visual validation**: `tests/test_theme_visual_validation.py` (23 tests) validates CSS variable completeness, palette lightness distribution, layout structure (no hardcoded colors), theme selector visual structure, and CSS output consistency.
- **Package validation**: `tests/test_theme_package_validation.py` (31 tests) validates manifest loadability, bundled theme parseability, emergency theme availability, registry build from package resources, CSS route for all bundled themes, and metadata endpoint completeness.
- **CI integration**: `theme-validation` job in `.github/workflows/ci.yml` runs validation CLI and all theme-specific tests. `theme-browser-smoke` job runs Playwright/Chromium browser tests.
- **Total theme test count**: 685+ tests across 16 test files (plus 14 Playwright browser smoke tests).

### Installer Source Acquisition
The installer downloads release artifacts from GitHub. It requires `curl` (preferred) or `wget`. The installer does NOT clone the repository — it downloads immutable versioned tarballs. The `main` channel is for development/evaluation only; `stable` is the default production path.

### Logrotate Commands Namespace
Logrotate commands are under `ainews logrotate {configure-rotation,validate-rotation,remove-rotation}`, NOT `ainews logs`. The `logs` command is reserved for viewing service logs via the lifecycle driver.

## Architecture Conventions

### Type Checking Pattern
When a service needs to reference adapter types for type hints only (not runtime), use the `TYPE_CHECKING` block pattern:
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from adapters.base import RawItem
```
This allows static type analysis without creating runtime imports between services and adapters.

### Subagent Function Signatures
The actual `run_subagent` signature is:
```python
def run_subagent(task_type: str, stage: str, prompt_data: dict, response_model: Type[BaseModel], article_id: int | None = None) -> SubagentResponse
```
Not the documented `run_subagent(task, context, tools, model)`.

### Pipeline Stage Status Values
Pipeline stages use these statuses in `_STAGE_TASKS`: `pending`, `selecting`, `selected`, `researching`, `writing`, `written`, `editing`, `review`. The `review` status is handled by `tasks/edit.py`.

### Model Field Naming
- `Source.type` is actually `source_type` in the model
- `Source.last_fetch_at` is actually `last_crawled`
- `Article.finalized_at` doesn't exist - use `published_at`
- `TrendMemory.observation` is actually `signal`
- `TrendMemory.embedding` is `db.Text` (not a vector type)
- `Source.adapter_config` doesn't exist (documented but never implemented) - adapter config is in `schemas/source.py` as `SourceConfig.config`

### Fallback Chain Behavior
The LLM provider fallback chain is **dynamic** - determined by enabled providers in `providers.yaml` configuration order, not hardcoded. The `get_provider_chain()` function in `services/llm/__init__.py` iterates through enabled providers and filters out those with open circuits.

A provider that cannot be constructed is skipped, not fatal — see *One Unusable Provider Must Not Take the Chain Down*.

### Celery Beat Schedule
Key scheduled tasks:
- `run-all-sources`: Every 30 minutes (crawl_interval)
- `generate-newsletters`: Daily at newsletters_hour (default 8 AM ET)
- `backfill-embeddings`: Daily at 2 AM
- `cleanup-old-logs`: Daily at cleanup_logs_hour (default 3 AM)
- `publish-scheduled-articles`: Every 5 minutes (publish_interval)
- `auto-approve-review-articles`: Every 1 minute (`schedule.auto_approve_interval_minutes`) — publishes the review queue when auto-review mode is on
- `retry-stuck`: Every 60 minutes
- `consolidate-trend-memory`: Daily at 3:30 AM
- `purge-trend-memory`: Daily at 3:45 AM
- `cleanup-old-versions`: Daily at 3:45 AM
- `cleanup-expired-verifications`: Every 15 minutes
- `cleanup-stale-limiter-slots`: Every 5 minutes
- `retry-failed-newsletter-deliveries`: Every 2 hours
- `recalculate-impact-scores`: Daily at 4 AM
- `cleanup-inactive-subscribers`: Daily at 1 AM

### Celery Beat Task Registration
Every module that defines a Celery task **must** be imported in `tasks/__init__.py`. The worker bootstraps with `from celery_app import celery_app` followed by `import tasks`, so a task whose module is never imported never registers and the beat dispatch fails at runtime with `Received unregistered task of type '...'` — silently, because the failure only appears when the beat actually fires. `tasks/cleanup.py`, `tasks/newsletter.py` and `tasks/subscribers.py` are easy to forget; they are not imported by any other task module.

The invariant is enforced by `tests/test_celery_beat_task_registration.py`, which asserts every task string in `Config.get_beat_schedule()` resolves to a registered task.

### Celery Task Signature Verification
`verify_task()` **fails closed** when `CELERY_TASK_SECRET` is not configured. Beat-dispatched tasks carry no `_signature`, so with no secret configured every beat task raises `Invalid task signature` and the pipeline silently stops. `CELERY_TASK_SECRET` is required in production (min 32 chars) and must also be set for a local dev instance. The fail-closed behaviour is deliberate and covered by `tests/test_task_security.py::test_verify_task_fails_closed_on_missing_secret` — fix a missing secret in the environment, not by weakening the check.

### Naive Datetime Columns
`db.DateTime` columns are declared without a timezone, but their defaults write `datetime.now(timezone.utc)`. SQLite returns those values back **naive**, so an aware `now` cannot be subtracted from them — `TypeError: can't subtract offset-naive and offset-aware datetimes`. Normalize before mixing: `tasks/retry.py` uses `_as_utc_aware()` for this. Beware that `MagicMock` fixtures usually set *aware* datetimes and therefore hide this class of bug; a regression test must use the naive value SQLite actually returns.

### Debugging the Beat
Beat failures are invisible in the worker log at `--loglevel=WARNING` unless they raise. Check the result backend instead — `CELERY_RESULT_BACKEND` defaults to Redis **db 1**, not db 0, and every task result is stored as `celery-task-meta-<uuid>`:
```bash
redis-cli -n 1 --scan --pattern 'celery-task-meta-*'
```

### One URL, Two Documents
A route that answers an HTMX request returns a **bare fragment**; the same URL returns a **complete page** for a normal navigation. Two consequences, both of which have broken this app before:

* **The browser HTTP cache must be told they differ.** A cacheable response has to carry `Vary: HX-Request`, otherwise the fragment cached by an in-page swap is handed to a later full page load — the reader then gets a document with no header, no footer and no navigation. `app.py` sets this in the `vary_on_htmx_request` after-request hook.
* **The service worker must not store HTMX responses** for the same reason. `static/service-worker.js` returns early for a request carrying the `HX-Request` header.

The application-level response cache in `services/cache.py` already separates the two via `_request_variant()` (`page` vs `fragment`). The browser cache and the service worker are separate caches with separate keys.

### No Body-Level hx-boost
`hx-boost="true"` on `<body>` turns every anchor into an HTMX request. The server answers with a bare fragment and htmx replaces the **whole `<body>`** with it, which strips the header, the footer and the `#content` wrapper. The result renders edge to edge and looks nothing like the rest of the site. It also destroys `#content`, which is the swap target every article link depends on, so no article can be opened afterwards.

Page-level navigation is a normal full page load. In-page updates (search, sort, infinite scroll, article detail) declare their own `hx-get` with an explicit `hx-target` and `hx-swap`.

### HTMX Swap Targets Are Fragments
Any template an HTMX request renders has to be a fragment with no `<html>`, `<head>` or `<body>`. The full page and the fragment must not drift apart, so the fragment is the single source of truth and the full page includes it (`templates/partials/article_detail.html` included by `templates/article.html`; `templates/admin/partials/pipeline_logs.html` included by `templates/admin/pipeline_logs.html`).

`tests/test_public_page_contracts.py` asserts that every template a route renders exists on disk — a missing one is a HTTP 500 on that path, and nothing else in the suite notices.

### Deferred Scripts and Inline Configuration
`htmx.min.js` is loaded with `defer`, so it has not executed while the document is being parsed. An inline `<script>` in `<head>` that touches `htmx.config` therefore raises `ReferenceError: htmx is not defined` on **every** admin page. Wait for htmx to exist before configuring it (`window.htmx` guard, applied on `htmx:load` / `DOMContentLoaded` / `load`).

### Service Worker Cache Versioning
`static/service-worker.js` names its cache `ainews-<version>`. The version is a fingerprint of the shipped static assets (`services/static_version.py`), injected into the worker script by `routes/public/feeds.py:service_worker`. A changed stylesheet therefore produces a different worker script, a new cache name, and an activation that purges the stale cache.

A cache-first strategy without a version bump pins every returning visitor to the assets they first loaded, so CSS and JS changes never reach the browser. The worker fetches `/static/` **network-first** with `cache: 'reload'`, which bypasses the browser's own HTTP cache, and keeps the cache purely as the offline fallback.

### Static Assets Must Be Revalidated
`SEND_FILE_MAX_AGE_DEFAULT = 0` (`config.py`), so static assets are served with `Cache-Control: no-cache` and an ETag.

The asset URLs do not change when their contents do — there is no content hash in the filename — so a long `max-age` pins the browser to the stylesheet it happened to load first. The server serves the correct CSS, the browser never asks for it, and the site keeps rendering with the previous milestone's styles. This is the failure mode that makes a CSS change look like it "did not work"; check the `Cache-Control` header on the stylesheet before suspecting the stylesheet itself.

The theme stylesheet (`/assets/themes/<id>.css`) is generated per request and keeps its own `max-age=300`; it is not part of the static tree.

### Article Bodies Are Markdown
The writer stage emits the body as Markdown (some models emit HTML). `services/markup.py` renders it and sanitizes it; the templates use the `body_html`, `markdown_html` and `inline_html` filters. Emitting `{{ fa.body }}` directly shows the reader literal `**bold**` and `### heading` markers.

`sanitize_final_article` uses the same allowlist, and that allowlist **must include block level elements**. A previous allowlist (`a`, `b`, `i`, `ul`, `li`) dropped `<p>`, so an HTML body was flattened into one wall of text before it was ever stored. `paragraphize()` additionally guarantees paragraph structure for text that arrives as a single unbroken run, which is what a degraded (fallback) article body looks like.

### Pipeline Internals Belong in Admin
The public index is a reading surface. Pipeline state — in-flight counts, per-status breakdowns, quality scores, degradation counters — is operational information and lives in the admin area. `services/feed_stats.py` exposes the per-status counts for the admin screens; the feed rail does not use them.

### Nothing Invisible May Occupy Layout
An element that is hidden with `opacity: 0` is **still in the flow**. It takes up its box, and everything below it is pushed down by exactly that much.

Two instances of this have shipped:

* The article detail fragment rendered a loading skeleton inside a `.htmx-indicator` wrapper. The skeleton shipped *with the response*, so it arrived after the request it was meant to cover had already finished — it could never be seen, and at 476px tall it pushed the headline **563px** down the page. A placeholder that lives in the response cannot cover the request. The indicator now carries `display: none` at rest and `display: revert` while `htmx-request` is set.
* The skip link was offset with `top: -40px`. Its own height is unknown, so a 3px sliver of accent colour stayed visible along the top edge of every page. Hide it with `transform: translateY(-100%)` instead.

The general rule: **if it is not visible, it is not in the layout.** `display: none` at rest, and restore the natural display type (`revert`) only while the state is active.

### The Route Must Pass What the Template Renders
A template reads attributes off the object the route hands it. A column that is missing from the route's `SELECT` list is not an error — it renders as an **empty cell**. The admin dashboard's recent-articles table selected `id, original_title, pipeline_status, source.name` while the template rendered `original_title`, `category`, `pipeline_status`, `selector_result.score`, `impact_score` and `created_at`, so five of its seven columns were silently blank.

When a template renders an attribute of a query row, that attribute has to be in the query. `tests/test_admin_navigation.py` asserts the column list and the rendered cells.

### The Page Frame Is the Same On Every Public Page
The sidebar, the header links and the footer are the **frame**. They must not appear on one page and disappear on the next.

* The rail lives in `templates/base.html` and every public route sets `"show_rail": True`. A route that forgets it loses the sidebar silently.
* The article route also passes `"categories"`, without which the header renders without the topic links and the frame changes.
* The subscribe form lives in the footer, once, on every page. It is not in the rail and not in the topic header.

### The Subscribe Form Lives in the Footer
The rail is a discovery surface: what the reader can browse. A subscribe form in the rail competes with the discovery links for attention and pushes the rail down the page. The footer carries it as a centred strip.

### Prose Needs a Measure
The article column is 868px wide next to the rail. At the body size that is roughly 110 characters per line, well past the point where the eye loses the start of the next line. The prose blocks are capped at `72ch`; the headings are not.

### Theme-Aware Glass and Gradients
The theme CSS output is **palette only** — a `:root` block of custom properties, no selectors and no media queries. That contract is unchanged.

Translucency and the page gradient are therefore built from the palette with `color-mix()` in `static/css/variables.css`:

```css
--surface-glass: color-mix(in srgb, var(--bg-secondary) 74%, transparent);
--glow-accent: color-mix(in srgb, var(--accent) 13%, transparent);
```

These are **derived** tokens, not palette tokens: they are defined once, they follow whichever theme is active, and the theme system never has to know about them. `services/themes/translate.py` must not learn about `color-mix` — that would break the palette-only contract.

A browser without `color-mix()` drops the declaration and falls back to the opaque palette colour, so the layout is never broken by it.

The page canvas is `html { background: var(--bg-primary) }` and the gradient is painted on `body` with `background-color: transparent`. If the body keeps an opaque background, the gradient is painted behind it and never seen.

### The Development Response Cache Hides Your Changes
`RESPONSE_CACHE_ENABLED` is `False` in `DevelopmentConfig` and `True` in production.

The cached document is the **rendered HTML**, and that HTML inlines the critical stylesheet. With the cache on, a template or CSS change keeps serving the previous markup — including the previous inlined CSS — for up to the cache TTL, so the page looks unchanged and the change looks like it "did not take effect". This cost a full debugging cycle once already.

### Pipeline Audit Trail
The pipeline writes its own log (`PipelineLog`), but nothing surfaced it: there was a page for what the agent **remembered** (trend memory) and no equivalent for what the pipeline **did**. Two admin surfaces now close that gap:

* `/admin/pipeline-audit` — the activity feed, filterable by stage, level and article, plus the operator action log.
* `/admin/articles/<id>/audit` — the full trail of one article: the stage timeline, the provenance the pipeline recorded on the article row, and the version history.

`services/pipeline_audit.py` assembles both. It is a service: it imports models and the database extension, never Flask and never the routes.

The dashboard carries a summary of both — `dashboard_summary()` in the audit service, `memory_summary()` in `services/trend_memory.py` — so the operator sees the state of the pipeline and of the memory without a second click. Both payloads are **JSON-safe**: the dashboard stats blob is stored in the response cache, which serialises it with `json.dumps`. A datetime or a dataclass in the payload breaks the cache write and takes the panels with it.

### One Hover State Per Card
An article card used to carry three competing hover treatments: an accent bar along its top edge (`.article-card::before`), a border colour that changed on hover, and a `.article-card:has(a:hover)` block that repainted the background, added a drop shadow and lifted the row by 2px. Hovering a headline crossed from one treatment to another mid-gesture, so the row flickered.

The rule now: **a card changes one thing, and its link handles its own affordance.** `.article-card:hover` changes the hairline under the row and nothing else; the headline changes colour and grows its underline. No rule that targets a card may select on a hovered descendant (`:has(...)`) — that is what made the two treatments fight.

Transitions share a duration and a curve (`0.25s ease` for colour, `0.35s cubic-bezier(0.4, 0, 0.2, 1)` for the underline), so nothing snaps.

### The Background Does Not Travel With the Content
The page background is painted on `body` with `background-attachment: fixed`, so the gradient stays where the reader put it instead of scrolling away. The bottom-most background layer is a single flat colour, `--bg-tint`, derived from the theme:

```css
--bg-tint: color-mix(in srgb, var(--bg-primary) 92%, var(--text-primary) 8%);
```

It is what shows through where the gradient does not reach, so the gradient reads as a shape standing against a field rather than as the page itself. `body` still paints `background-color: var(--bg-primary)` — that is what a browser test asserts, and the tint layer is a separate *image* layer painted on top of it.

### The Provider File Is a List
`providers.yaml` holds a **list** of provider definitions:

```yaml
providers:
  - id: local
    type: openai
    enabled: false
    config: {base_url: "http://127.0.0.1:1234/v1", model: "google/gemma-4-e2b", local: true}
```

The loader (`ainews_config/loader.py`) normalises that list into a mapping keyed by provider id, and the CLI used to write the **mapping** back out. The application reads a list, so a providers file written by the CLI was a file the application could not load — a `ValidationError` at startup, with every provider gone.

Both writers now emit the list: the CLI in `ainews_cli/providers/commands.py::_commit_providers`, the admin panel in `services/admin_settings.py::update_providers`. **Any code that writes `providers.yaml` must convert the mapping back to a list.** The regression test is `tests/test_admin_settings.py::TestTheCliWritesTheSameShape`.

### A Provider May Need No Credential
An API provider can be declared `local: true`. That means two things:

* `api_key` may be empty — `OpenAIConfig` only requires a credential for a hosted provider.
* the SSRF guard allows a private address for it — `validate_url_safe(url, allow_private=True)`.

The relaxation is **explicit and per provider**: it is the operator declaring "this endpoint is on my machine". Everything else about the URL is still checked, and the guard still fails closed on a DNS error. A provider declared local is an operator statement, in the same trust class as the provider file itself.

The OpenAI SDK refuses to construct a client without a key, so a local provider gets the placeholder `local-no-key-required`, which local servers ignore.

### The Agent Name Is an Operator Setting
The site credits a summary with "this summary brought to you by *X*". `X` is now configurable: a site-wide name and a per-topic override, both edited in `/admin/settings` and stored in `topics.yaml`:

```yaml
site:
  agent_name: "The Correspondent"
topics:
  ai:
    agent_name: "The Lab Assistant"
```

The resolution order is topic override → site-wide name → the model that wrote the article → `ai agent`. `services/agent_identity.py` owns it; the template filter is `|agent_name`. The admin audit page keeps showing the **real** writer model — provenance must stay truthful.

### The Admin Header Is Two Rows
The admin header is a CSS grid with two rows: the primary sections on the first, the remaining admin sections on the second. They used to share one row, which left the primary nav so narrow that its last links scrolled out of sight behind a scrollbar with no visible scrollbar.

**A navigation link that scrolls out of sight is a broken link.** Both rows wrap rather than scroll, and no admin section may be added that cannot be seen.

### One Unusable Provider Must Not Take the Chain Down
`get_provider_chain()` yields the primary provider and then walks the enabled fallbacks. A fallback that **cannot be constructed** — a missing credential, a malformed block — used to raise out of the generator, which discarded the primary that had already been yielded. The pipeline was left with no provider at all.

A provider that fails to construct is now **skipped and logged** (`Skipping LLM fallback provider %r`), never fatal. The same applies to the primary: an unusable primary falls through to the fallbacks.

The "circuit open, trying fallbacks" warning is only logged when the circuit is actually open. It used to be logged unconditionally, on every call, which made a healthy primary look broken.

The regression tests are `tests/test_provider_chain_resilience.py::TestProviderChainResilience`.

### A Stage Failure Has to Be Recorded, Not Just Raised
`run_stage()` resolves the provider chain. That resolution used to happen **outside** the stage's try block, so a failure escaped the stage untouched: no `pipeline_logs` row, no `last_error` on the article, no metric. The article sat in `pending` with nothing to show for it, and the worker log showed a task that was received and never mentioned again.

**Anything that can fail inside a stage belongs inside the stage's error handling.** Provider resolution now routes through `_handle_stage_exception` (which writes the pipeline log and the article error) or `_handle_circuit_open_module` (which degrades the article to review). The limiter and the stage lock stay outside the try, because `task_self.retry()` raises a `Retry` that must not be swallowed.

The regression test is `tests/test_provider_chain_resilience.py::TestRunStageProviderResolution`.

### A Reasoning Model Can Answer With No Content
`google/gemma-4-e2b` and `muse-spark-1.3-contributor` are reasoning models. They spend part of the token budget thinking, and can return the answer in `reasoning_content` with `content` empty — most often when `max_tokens` is small enough that the thinking consumes it all.

The OpenAI adapter falls back to `reasoning_content` when `content` is empty (`services/llm/openai.py::_message_text`). A provider must not look broken because a model thought for a while.

Two practical consequences:

* **A small `max_tokens` is not a cheap probe.** A 16-token budget was spent entirely on reasoning and produced no answer. Probes and smoke tests need a realistic budget.
* **The local endpoint does not implement `response_format: {"type": "json_object"}`** (HTTP 400). It does implement `json_schema` with `strict: true`, which is what the pipeline uses.

### The Probe Has to Prove the Endpoint Works
The admin panel's "test provider" button and the CLI's `providers test` share one probe. Two things used to make it lie:

* It only tried `GET /models`. An OpenAI-compatible gateway that does not implement that route answers 404, and the probe reported **success** — a green tick on a provider that could not serve a request at all.
* It sent the credential but **not the provider's own headers**. A gateway that needs a routing header (`x-opencode-session`, for instance) rejected every probe, so a working provider was reported as broken.

The probe now falls back to one minimal completion when `/models` answers 404 or 405, and sends the provider's declared headers. Success means the endpoint served a well-formed response — a 200 with a choice — not merely that something answered. A reasoning model that returns an empty message still counts as a pass.

The regression tests are `tests/test_provider_probe.py`.

### A Form Post Carries the CSRF Token in a Field
The CSRF guard on the admin endpoints (`routes/decorators.py::validate_csrf_token`) used to read the token from the `X-CSRFToken` **header only**. A plain HTML form cannot send a custom header — it posts the token in the `csrf_token` field — so every form post on the admin panel failed with `CSRF token missing`. The "trigger crawl" button was the visible symptom, but newsletters, trend memory and topic notes were all broken the same way.

The guard now accepts the token from the header, the form field, or a JSON body.

**A form post is not a JSON client.** A form-encoded POST that did not ask for JSON is answered with a redirect and a flash message (`routes/decorators.py::wants_html`), not with a raw `{"message": ...}` body. Flask-WTF's global `CSRFProtect` only reads the header and the form field, so a token in a JSON body works on the exempt API blueprint (`admin_api_bp`) and nowhere else.

The regression tests are `tests/test_admin_settings_panel.py::TestFormPostCarriesTheCsrfToken`.

### A Button Without `.btn` Is Not a Button
`.btn-primary` only sets the colours. The geometry — the 34px height, the radius, the font, the inline-flex box — lives in `.btn`. A template that wrote `class="btn-primary"` produced a control that was technically a button and looked like a word. `.btn-delete` and `.btn-logout` carry their own complete geometry and are the only exceptions.

**Every button in every template carries the base class.** `tests/test_admin_settings_panel.py::TestButtonsAreStyled` walks the templates and fails on any that does not.

### A Flash Message Nobody Renders Is No Message At All
The admin routes have always reported what they did through `flash()`, but no template ever called `get_flashed_messages()`. Saving a setting looked exactly like a page that ignored the click.

`templates/base_admin.html` now renders the flashes. Any new admin view that reports through `flash()` inherits this.

### Auto-Review Mode Publishes What Would Otherwise Wait
The pipeline routes an article to the `review` queue whenever a quality gate fails or an editor asks for a second look. That is the right default: a human decides whether a shaky article goes out. It is the wrong default for a site that wants fully autonomous generation, because the queue fills with articles nobody is going to read.

`pipeline.review.auto_approve` (in `pipeline.yaml`, and on the admin settings panel) turns that around: an article that reaches the review queue is approved and published immediately, exactly as a human approver would have done.

Three things have to agree, and they live in `services/auto_review.py`:

* `is_auto_approve_enabled()` reads the switch. It **fails closed** — a broken configuration leaves the articles waiting for a human, which is the safe direction.
* `route_to_review()` is the single decision point. Every path that sends an article to review goes through it, so the pipeline stages cannot disagree about whether the mode is on. `tasks/pipeline.py::_transition_article_status` and the degradation paths in `services/pipeline_degradation.py` all call it.
* `approve_article()` is the single approval primitive. The admin panel's "approve" button calls it too, so an auto-approved article and a human-approved one end up in the same state.

Two consequences worth knowing:

* **The review dispatch is skipped in auto-review mode.** `services/pipeline_utils.py::_dispatch_next` returns early for `next_status == "review"`, because the article was published rather than queued, and re-running the editor on a published article would edit it twice.
* **The beat task is the safety net.** `tasks.scheduler.auto_approve_review_articles` runs every `schedule.auto_approve_interval_minutes` and drains the queue. It covers the articles that were already waiting when the switch was turned on, and the ones queued by a path that bypasses the pipeline stages. Every task that defines a Celery task must be imported in `tasks/__init__.py` or the beat dispatch fails at runtime — see *Celery Beat Task Registration*.

The regression tests are `tests/test_admin_settings_panel.py::TestAutoReviewMode`.

### Removing a Topic Has to Remove Its References
The configuration validator rejects a source that follows a topic that does not exist. So deleting a topic from `topics.yaml` without touching `sources.yaml` leaves the configuration invalid for everything else.

`services/admin_settings.py::remove_topic` removes the topic and strips it from every source's `topics.include` list in the same transaction, and reports which sources it touched.

### A Submit Button Can Only Belong to One Form
The settings panel edits every topic in one form, and each row also carries a "remove" button. HTML does not allow a nested form, so the remove button carries `form="topic-delete-<id>"` and points at a form that lives outside the table.

**A `button` with a `form` attribute still matches a selector like `form[action="..."] button[type="submit"]`,** because it is a descendant of that form even though it submits another one. A test that means to click "save" must therefore target the save button specifically. For the same reason the save button is the **first** control in the topics form: the destructive per-row buttons come later in tab order.

### Never Hold the SQLite Write Lock Across a Model Call
SQLite allows one writer. A session with a pending `UPDATE` takes the write lock at the next autoflush — and holds it until the transaction ends. If a model call happens between the write and the commit, the write lock is held for the whole duration of the model call.

That is exactly what `post_finalize_article()` used to do: it set `published_at`, then asked the model for a trend-memory proposal before committing. The publication was durable only once the model answered. On a slow local model the beat task hit its 180s hard timeout, Celery SIGKILLed the worker, and the write lock stayed held — every other writer in the process then failed with `database is locked`, because the killed worker never got to roll back.

**Commit the publication before the slow work.** `post_finalize_article()` now commits first, then dispatches the trend-memory proposal as a **separate task** (`tasks/trend_memory.py::propose_trend_memory_for_article`, 900s soft / 960s hard). The proposal reads its inputs into locals and releases the transaction (`_release_transaction()`) before calling the model, so the model call never runs inside a transaction at all. The response is buffered in memory and written in one short transaction once it is complete.

**A provider failure must not undo a publication.** `propose_trend_memory()` catches everything except `SoftTimeLimitExceeded` — a failed proposal is a missing insight, not an unpublished article.

**A slow model must never be on the publication path.** If a model call has to happen inline, it has to be after the commit and outside any transaction.

The regression tests are `tests/test_publication_lock.py`.

**A Celery task runs under its own app context, and therefore its own session.** `celery_app.py::FlaskTask.__call__` pushes a fresh `app_context()` for every task execution, and Flask-SQLAlchemy scopes the session to that context. A task therefore does **not** use the session of the code that called it — it reads the article again, on its own session.

That matters twice:

* `_release_transaction()` commits the session the article is **attached to**, not the ambient one. Committing a different session would leave the write lock held.
* A test that asserts "the model call ran with no open transaction" has to look at the session **the task is using**. Asserting on the fixture's session measures the fixture, not the task — and it fails intermittently, because whether the shared task is bound to `FlaskTask` depends on import order.

### A Missing Transition Edge Strands the Article
`constants.py::VALID_TRANSITIONS` says which pipeline status may follow which. A missing edge does not merely refuse a transition: `_transition_article_status` raises `InvalidStateTransitionError` **in the middle of a stage**, and the article is left exactly where it was. It then sits there until `tasks/retry.py` dead-letters it an hour later as "stuck in 'pending' beyond 60 minutes". Thirty articles in the live database died that way.

Three edges were missing, and all three are on the normal path of an autonomous run:

| Edge | Performed by | Consequence when missing |
|---|---|---|
| `pending -> skipped` | `tasks/select.py` — the selector rejects the article | The single most common outcome of a crawl threw |
| `writing -> review` | `tasks/write.py` — the writer's quality gate | A degenerate draft could not be routed to review |
| `pending -> failed` | `tasks/pipeline.py` — the pipeline timeout | A pending article that timed out could not be failed |

**Every edge in the table has to match a transition the pipeline actually performs.** When you add a `_transition_article_status` call, add the edge to `VALID_TRANSITIONS` in the same change. The regression test is `tests/test_pipeline_transitions.py`.

**A published article stays published.** The editor can be re-dispatched onto an article that has already been finalized. Before auto-review mode, the transition table refused `done -> review` and protected the article. `_transition_article_status` now short-circuits every transition *to* review and hands it to `route_to_review`, which does not validate — so `services/auto_review.py::route_to_review` refuses to touch an article that is already `done`. Without that guard a re-dispatched editor would drag a live article back into the review queue, or publish it a second time and run the post-publication work twice.

### run_stage Function Signature
The `run_stage()` function in `tasks/pipeline.py:353-362` has this signature:
```python
def run_stage(
    stage: str,
    article_id: int,
    work_fn,
    task_self,
    run_id=None,
    skip_next: str = "finalize",
    retry_countdown: int = 30,
    retry_max: int = 15,
):
```
Note: Selector stage uses `retry_max=20` (hardcoded in `tasks/select.py:202`), not the default 15.

### Logout Requires POST
The logout endpoint at `/admin/logout` requires POST method only (not GET). This is intentional CSRF protection. Do not use GET for logout.

## Design Notes for Future Agents

### Documentation Alignment Rules
- Never put production-required env vars (`SECRET_KEY`, `ADMIN_PASSWORD`, `CELERY_TASK_SECRET`) under "optional" documentation sections.
- Never document `localhost` Ollama as Docker-compatible without caveats — `localhost` inside Docker refers to the container itself.
- Do not add enabled providers without corresponding validation tests in `tests/test_production_config.py`.
- Keep `.env.example`, README quickstart, and `docs/configuration.md` in sync when changing production requirements. `tests/test_docs_env_consistency.py` enforces this automatically.
- The canonical source of truth for production requirements is `ProductionConfig.validate()` in `config.py`.

### SubagentConfig is NOT SubagentStageConfig
`SubagentConfig` in `schemas/pipeline.py:121-125` is the container for subagent stage configs. It does NOT have an `enabled` field at the top level. The `enabled` field is on `SubagentStageConfig` (line 94).

### api_tokens Blueprint IS Registered
The `api_tokens_bp` blueprint IS registered in `app.py` WITHOUT `url_prefix`. The routes themselves include the full `/api-tokens` path (e.g., `/api-tokens/`, `/api-tokens/<id>`). Any documentation claiming it is "not registered" or has `url_prefix="/api-tokens"` is incorrect.

### API Token Lifecycle
API tokens use the format `ak_<prefix>.<secret>`. The full token is returned once at creation time and never stored. Only the hashed secret (via werkzeug password hashing) is persisted in `ApiToken.token_hash`. Verification in `verify_api_token()` (`routes/admin/__init__.py:16`) parses the token, looks up by prefix, checks `revoked_at` and `expires_at`, then verifies the secret against the stored hash. Expired and revoked tokens are rejected. Prefix collision handling iterates all candidates matching the prefix, so collisions cannot break valid tokens. `services/api_tokens.py` contains `generate_api_token()`, `hash_api_token_secret()`, `verify_api_token_secret()`, and `parse_api_token()`. Existing tokens from before the redesign are invalid — regeneration is required.

### StageConfig is a Stub
The `StageConfig` schema in `schemas/pipeline.py` is an empty stub (only has `tools` field). The actual stage configuration is handled by `SubagentStageConfig` and `RoleConfig`.

### ToolDefinition Schema
The `ToolDefinition` in `services/llm/base.py` is a `@dataclass` with fields: `name`, `description`, `parameters`, `required`, and `fn`. It does NOT have a `cached` field as older documentation suggested.

### RSSAdapter Session Independence
`RSSAdapter` creates its own `requests.Session` with its own `SSRFSafeRedirectHandler`, while `APIAdapter` and `WebAdapter` share the global session from `get_crawl_session()`. This is BY DESIGN - different adapter types have different session management requirements.

### APIAdapter/WebAdapter close() is No-Op
`APIAdapter` and `WebAdapter` implement `close()` as a no-op (empty pass). They do NOT close the shared global session because doing so would break other adapters using the same session. `RSSAdapter` creates its own session and correctly closes it in `close()`.

### Adapter Config Validation
`SourceConfig.config` in `schemas/source.py` has a `field_validator` that validates config against the appropriate adapter schema (RSSConfig, APIConfig, or WebConfig) based on the source type.

### schemas/common.py Layer Violation
The `schemas/common.py` module imports from `services.config_cache`. This is intentional - config caching requires services layer knowledge. Documented with a comment explaining the layer violation is necessary.

### extract_text trafilatura ImportError
The `extract_text()` function in `utils/html.py` logs a warning when trafilatura is not available, rather than silently passing on the ImportError.

### Quality Gate Routing
Each pipeline stage has quality gates that can route articles to `review` for manual inspection even when the stage "succeeds":
- `select`: Low confidence (score OK but confidence="low") → `review`
- `research`: Degenerate research brief (fails `_is_degenerate_research()`) → `review`
- `write`: Degenerate draft (fails `_is_degenerate_write()`) → `review`
- `edit`: Validation failure → `review`
- `edit`: Quality report failure (`build_quality_report()` in `tasks/edit.py:378-419`) → `review`

### Limiter Slot Leak Fix
In `tasks/pipeline.py:run_stage()`, the limiter release uses `provider_id or rc.provider` and `model or rc.model` as fallbacks to prevent slot leaks when `_run_stage_core` raises before returning provider info.

### Middleware Clone Fix (Fixed)
`run_subagent_with_tools()` in `services/subagent/runner.py:349-355` creates a new `ToolDefinition` object when wrapping functions, preventing middleware compounding on cached tool definitions.

### Subagent Exception Handling
`ProviderServerError` and `AuthError` are caught in the subagent chain's exception handler (`services/subagent/chain.py:161-162`) and in the single-step runner (`services/subagent/runner.py:141`). These are non-retryable errors — the subagent returns a fallback response rather than retrying. `ProviderTimeoutError` is retryable via the self-correction mechanism.

### Subagent Tool Count
The subagent system has **14 tools** (not 9 as some docs claim). 12 context tools + 2 search tools. Registered in `services/subagent/tools.py:306-603`. The tools are: `get_topic_note`, `context_notes`, `related_articles`, `get_trend_memory`, `get_article_by_id`, `search_articles`, `get_source_health`, `get_topic_gap_report`, `get_source_performance`, `get_quality_report`, `find_dedupe_candidates`, `estimate_stage_cost`, `web_search`, `get_search_provider`.

### QualityReport Model
The `QualityReport` model exists in `models/quality.py:10-51` with fields: `article_id`, `article_version_id`, `stage`, `overall_score`, `groundedness`, `coherence`, `completeness`, `safety`, `citation_score`, `claim_score`, `passed`, `needs_review`, `findings` (JSON), `meta` (JSON), `created_at`. The quality report service is in `services/quality_report.py` with `build_quality_report()` (line 438) and `persist_quality_report()` (line 531).

### Hybrid Search Function Name
The hybrid search function is `search_articles()` in `services/search/hybrid.py:329`, NOT `hybrid_search()`. Also has `cosine_similarity` (line 41) and `reciprocal_rank_fusion` (line 67).

### Experiments Config Location
Experiment configuration lives in `PipelineRootConfig.experiments` (added to `schemas/pipeline.py`). Callers must use `load_pipeline_config()` from `schemas.pipeline` to access experiments — NOT `get_config()` which returns an `AppConfig` dataclass without `.get()` method.

### Circuit Breaker Key Convention
Circuit breaker keys use the **role** convention: `llm:{provider}:{model}:{selector|researcher|writer|editor}`. The `record_provider_success()` and `record_provider_failure()` functions accept `stage=` parameter which must use the role name (e.g., `"selector"`, NOT `"select"`). This ensures the circuit breaker sees success signals from the same key that `get_provider_chain()` checks.

### Post-Finalization Processing
`post_finalize_article()` in `services/pipeline_degradation.py` handles: `published_at` timestamp, SLA metrics, trend memory, webhook dispatch, and embedding generation. Called by both `_finalize()` (degradation path) and `_post_finalize_article()` in `tasks/edit.py` (normal path).

It **commits the publication before any slow work**. The trend-memory proposal is dispatched to its own task rather than run inline, so no model call ever happens while the SQLite write lock is held — see *Never Hold the SQLite Write Lock Across a Model Call*.

### Adapter Per-Request Headers
`APIAdapter` and `WebAdapter` pass headers via `headers=` parameter to `session.get()` instead of mutating the shared session's headers. This prevents race conditions when concurrent Celery workers use the same session.

### SSRFSafeRedirectHandler
`SSRFSafeRedirectHandler.__call__` in `adapters/session.py` validates redirect URLs via `validate_url_safe(location)` and returns a new `PreparedRequest` with the redirect URL set. The handler uses thread-local storage for redirect counting to ensure per-request scoping.

### Docker Deployment Modes
Four deployment modes are documented in `docs/deployment.md#docker-with-ollama`:
- **Mode A (Cloud provider):** Simplest. Set API key in `.env`, enable provider in `providers.yaml`.
- **Mode B (Ollama Compose service):** Use `docker-compose.ollama.yml` override. Provider host: `http://ollama:11434`.
- **Mode C (Host Ollama):** Provider host: `http://host.docker.internal:11434`. Linux requires `extra_hosts: ["host.docker.internal:host-gateway"]`.
- **Mode D (Bare metal):** Provider host: `http://localhost:11434` is correct.

**Critical:** `localhost` inside Docker containers refers to the container itself, NOT the host. Using `http://localhost:11434` from Docker will silently fail at LLM call time. `AINEWS_RUNNING_IN_DOCKER=1` env var is set in Dockerfile and compose services. `ProductionConfig.validate()` emits a warning when Ollama uses localhost inside Docker (see `_validate_docker_ollama_host()` in `config.py`).

### Health Check Property Name
The `HealthResult` model at `services/health.py:27-33` has two properties:
- `is_healthy`: Returns `True` for both `"ok"` and `"degraded"` statuses
- `is_fully_healthy`: Returns `True` only for `"ok"` status

Use `is_healthy` for general health checks, `is_fully_healthy` when degraded status should be treated as unhealthy.

### Celery Timezone
Celery uses UTC (`CELERY_TIMEZONE = "UTC"` in `config.py:102`). The `NewsletterConfig.timezone` setting is display-only for newsletter rendering. All beat schedule times are in UTC.

### SQLite Only (No PostgreSQL)
The codebase uses SQLite with WAL mode only. There is no PostgreSQL configuration, driver, or connection string anywhere. Do not reference PostgreSQL in documentation.

### Operator CLI Architecture
The `ainews_cli` package is Flask-free and imports only from `ainews_config`. All commands work outside the repository directory. The CLI uses Typer with `typer.Typer(no_args_is_help=True)`. Configuration loading uses `resolve_paths()` → `load_all_configs()` → `validate_cross_file()`. Secret values are redacted in output by default; `--show-secrets` is not available in Release 1. The `config set` and `config unset` commands use `ConfigTransaction` for atomic file replacement with rollback. Exit codes are defined in `ainews_cli/exit_codes.py`. See `docs/cli-reference.md` for the full command reference.

### Installer Architecture
The installer at `scripts/install.sh` is a thin, channel-aware shell script that downloads immutable release artifacts from GitHub. It:
- Detects platform (OS + CPU architecture)
- Resolves the target version via GitHub API (stable/prerelease/main channels)
- Downloads artifact tarball + SHA256SUMS
- Verifies SHA-256 checksum before extraction
- Extracts to a staging directory with path traversal rejection
- Atomically installs to canonical paths
- Writes `install-metadata.json` consumed by `ainews_config.paths`
- Delegates setup to `ainews onboard` and lifecycle to `ainews start`

The installer contains NO application configuration policy. It acquires and installs; all setup is delegated to the CLI.

Installer options: `--channel`, `--version`, `--commit`, `--user`/`--system`, `--prefix`, `--non-interactive`, `--bootstrap`, `--start`, `--download-only`, `--dry-run`, `--yes`.

Canonical paths:
- User: `~/.local/share/ainews/app/`, `~/.config/ainews/`, `~/.local/state/ainews/`
- System: `/opt/ainews/`, `/etc/ainews/`, `/var/lib/ainews/`, `/var/log/ainews/`

### Update Architecture
The update system at `ainews_cli/update/` provides safe, channel-aware in-place updates:
- **State machine:** `UpdatePhase` enum tracks operation lifecycle: idle → checking → planned → downloading → verified → backed_up → staged → migrating → activated → validating → complete (or failed/rolled_back)
- **GitHub client:** `ainews_cli/update/github.py` replicates installer's version resolution and artifact download logic in Python using `urllib.request`. Supports `AINEWS_GITHUB_TOKEN` and proxy env vars. Reports artifact size via HEAD request.
- **Update engine:** `ainews_cli/update/engine.py` orchestrates the full pipeline: check → plan → download → verify checksum → create pre-update backup → extract to staging → stop services → activate → run migrations → start services → health check → auto-rollback on failure
- **Migration integration:** Detects both config schema migrations (`ainews_config.migrations`) and Alembic database migrations (`ainews_cli.migrations`). Runs migration preflight checks (lock detection, version validation), executes migrations, and validates post-migration state (config parseability, DB integrity).
- **Disk space preflight:** Checks available disk space before download and before applying. Fails early if insufficient space is detected.
- **Staging cleanup:** Removes stale `.staging-*` directories before downloading new artifacts.
- **Locking:** Exclusive `fcntl.flock` on `state_dir/update.lock` prevents concurrent update/uninstall/restore operations
- **State persistence:** `UpdateOperation` saved to `state_dir/update-state.json` for interrupted operation recovery
- **Pre-update backup:** Full backup via `ainews_config.backup.create_backup()` before any migration, verified before proceeding. Optional `force_backup` override allows proceeding when backup fails.
- **Rollback:** Automatic on failure; explicit via `ainews update rollback` within 30-day retention window. Restores previous app version from staging backup or pre-update backup. Emits manual recovery instructions when automatic rollback fails.
- **Health validation:** Runs lifecycle health check and optional doctor/smoke test after update. Health or doctor failures trigger automatic rollback.
- **Version comparison:** Uses `packaging.version.Version` when available, falls back to string comparison

Commands: `ainews update check`, `ainews update plan`, `ainews update apply`, `ainews update rollback`, `ainews update status`

### Channel Management
Channel commands at `ainews_cli/channel/` manage the release channel:
- `ainews channel show` — displays current channel, version, commit, installed-at from `install-metadata.json`
- `ainews channel set <channel>` — validates channel (stable/prerelease/main), requires confirmation for risky channels (prerelease/main), writes metadata atomically
- `--apply` flag triggers immediate update check after channel change
- `--version` flag pins to a specific version, preventing channel resolution
- Switching channels clears any existing version pin unless `--version` is also specified

### Uninstall Architecture
The uninstall command at `ainews_cli/uninstall/` removes application files while preserving operator-owned state:
- **Default behavior:** Removes only app files (binaries, code), preserves config, data, backups, and state
- **`--remove-app-only`:** Removes only application files
- **`--purge`:** Removes everything including config, data, and backups (requires `--yes` in non-interactive mode). Prompts for a final backup before deleting mutable state.
- **Path ownership validation:** Each target path must be under an approved root (`~/.local/share/ainews`, `~/.config/ainews`, `/opt/ainews`, etc.)
- **Safety checks:** Refuses without install metadata, rejects unsafe paths (root, home, empty, unresolved variables)
- **Service lifecycle:** Stops services via lifecycle driver before removal
- **Dry-run support:** Shows deletion plan without executing

Commands: `ainews uninstall`, `ainews uninstall --remove-app-only`, `ainews uninstall --purge --yes`, `ainews uninstall --dry-run`

### Service Management Architecture

The service management subsystem at `ainews_cli/service/` provides systemd unit rendering, installation, and logrotate integration for installed ainews deployments.

**Package structure:**
- `models.py` — Typed dataclasses: `ServiceUnitSpec`, `LogrotateRuleSpec`, `RenderedUnit`, `RenderedLogrotateRule`, `ValidationResult`, `InstalledUnitRecord`
- `systemd.py` — systemd unit file rendering engine with `render_unit()` and builder functions for web, celery-worker, celery-beat, and docker-compose profiles
- `logrotate.py` — logrotate rule rendering engine with `render_logrotate_rule()` and `build_logrotate_rule()`
- `state.py` — Installation state tracking (persisted to `service-state.json` in config dir)
- `validation.py` — Path validation, conflict detection, and comprehensive unit spec validation
- `commands.py` — CLI commands: `ainews service {render,install,validate,status,restart,remove}`
- `logrotate_commands.py` — CLI commands: `ainews logrotate {configure-rotation,validate-rotation,remove-rotation}`

**Service topology:**
- Docker Compose project managed as a unit (`docker compose up/down`)
- Bare-metal web process (Granian ASGI via `python run.py`)
- Bare-metal Celery worker
- Optional Celery beat scheduler
- Redis remains external or Compose-managed

**systemd hardening defaults:**
- `NoNewPrivileges=true`
- `PrivateTmp=true`
- `ProtectSystem=strict`
- `ProtectHome=true`
- `UMask=0027`
- `CapabilityBoundingSet=` (empty = drop all capabilities)
- `RestrictNamespaces=true`
- `RestrictRealtime=true`
- `RestrictSUIDSGID=true`
- `MemoryDenyWriteExecute=true`
- `LockPersonality=true`
- `SystemCallArchitectures=native`
- `PrivateDevices=true`
- `ProtectKernelTunables=true`
- `ProtectKernelModules=true`
- `ProtectControlGroups=true`
- `ProtectClock=true`
- `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX`
- Bounded restart policy (on-failure, 5s delay, 5 burst in 60s)

**Installation lifecycle:**
1. Render to staging directory
2. Validate (model checks, path checks, executable checks, conflict detection, systemd-analyze verify)
3. Show diff and impact analysis
4. Require confirmation
5. Write atomically with correct permissions (0644)
6. Record installed unit paths and content hashes in state
7. Run daemon-reload
8. Optionally enable/start only when requested
9. Run post-install health checks
10. Automatic rollback on failure

**State tracking:** Installed units are tracked in `service-state.json` with SHA-256 content hashes. Modified units are detected on removal and require explicit confirmation. Installation uses flock-based locking to prevent concurrent modifications.

**Logrotate:** Rules are generated only for file-backed logs (not journald or Docker logs). Default: daily rotation, 10 rotations, compression with delay, 0640 permissions.

**Exit codes:** `SERVICE_ERROR = 12` added to `ainews_cli/exit_codes.py`.

**Tests:** `tests/test_service.py` (100+ tests), `tests/test_logrotate.py` (46 tests), `tests/test_cli_service.py` (34 tests).

### Release Workflow Architecture
The release workflow at `.github/workflows/release.yml` builds platform-specific release artifacts and creates GitHub Releases:
- **Trigger:** Tag pushes matching `v*` (also supports `workflow_dispatch` for dry runs)
- **Gate:** Full test suite (lint, typecheck, pytest) must pass before builds start
- **Build matrix:** `linux-x86_64` (ubuntu-22.04 for glibc 2.35), `linux-aarch64`, `macos-x86_64`, `macos-aarch64`
- **Artifact contents:** Application source + `.venv/` + Docker Compose manifests + migrations + themes + wrapper `ainews` script
- **Safety validation:** Rejects absolute paths and `..` traversal entries in tarballs
- **Checksums:** Per-platform `SHA256SUMS` merged into a single file
- **Release:** `softprops/action-gh-release@v2` with auto-generated notes; `-rc`/`-beta`/`-alpha` tags marked as prerelease
- **Artifact naming:** `ainews-{version}-{platform}.tar.gz` (matches installer's `resolve_artifact_url()`)

### Installer CI Architecture
The clean-host CI workflow at `.github/workflows/installer-smoke.yml` validates the installer as a supported operational path:
- **Build job:** Builds a test tarball from the repo for deterministic testing (no GitHub API required)
- **Linux x86_64:** Full install to canonical user paths, metadata verification, ainews version, config check, doctor --production
- **Linux aarch64:** Native ARM runner (`ubuntu-24.04-arm`), builds own artifact on ARM for architecture-correct testing
- **macOS arm64:** Cross-platform canonical path validation
- **Full lifecycle:** Install → Docker Compose build → start services → wait for /health → verify health response → stop → verify no orphans
- **Deferred prerequisite:** Tests installation without Docker, verifies metadata distinguishes installed/configured/running states
- **Docker unavailable:** Verifies graceful degradation when Docker daemon is missing

The workflow builds a local tarball to avoid GitHub API dependency in CI. The installer's GitHub API resolution is tested by the existing shell tests (`tests/test_install.sh`).

### Artifact Validation
The artifact validation script at `scripts/validate_artifact.sh` pre-publishes release assets:
- Expected top-level structure (files and directories)
- Executable CLI entry point with correct shebang
- Compose files, migrations, themes, static assets present
- No repository secrets, caches, test databases, `.env`, or developer state
- No absolute paths or escaping links in archive
- SHA-256 checksum verification against SHA256SUMS
- Version metadata cross-check with pyproject.toml (when `--tag` provided)

### Installer Tests
Shell tests at `tests/test_install.sh` cover:
- Argument parsing (all flags, missing values, unknown flags)
- Platform detection and architecture normalization
- Path computation (user, system, prefix modes)
- Checksum verification helpers
- Metadata writing (valid JSON, correct fields, permissions)
- Input validation (empty, absolute, traversal, newlines)
- Fault injection (corrupted archives, traversal, symlinks, device nodes, checksum mismatches, unwritable directories)
- 137 tests — run with `bash tests/test_install.sh`

End-to-end installer tests at `tests/installer_e2e.sh` cover:
- Post-install canonical directory creation
- Metadata written with correct schema and no secrets
- Archive safety (traversal, absolute paths, symlinks, corruption, truncation)
- Checksum mismatch detection
- Unwritable directory handling
- Lifecycle exit codes
- Onboarding failure preserves installation state
- Startup timeout handling
- Metadata write failure handling
- Config preservation on rerun (Docker becomes available)
- 28 tests — run with `bash tests/installer_e2e.sh`

JSON contract tests at `tests/test_cli_json_contracts.py` cover:
- `ainews version --json` schema and no-secrets check
- `ainews config path` text output and no-secrets check
- `ainews config check` status/exit-code consistency
- `ainews doctor` schema_version, checks, counts, outcome
- `ainews status --json` output contract
- Exit code consistency across commands
- Additive evolution policy (extra fields accepted)
- 24 tests — run with `pytest tests/test_cli_json_contracts.py -v`

### Doctor Package Architecture
The `ainews_cli/doctor/` package provides system diagnostics. It is structured as:
- `model.py`: `CheckStatus` enum (PASS/WARN/FAIL/SKIP), `CheckResult`, `DoctorReport` with aggregate counts (`passed_count`, `warn_count`, `failed_count`, `skipped_count`). `CheckResult.passed` property is backwards-compatible (PASS or SKIP → True).
- `runner.py`: `run_doctor()` orchestrator with `--quick`, `--production`, `--network` flags controlling check tiers.
- `rendering.py`: Human-readable output with symbols (✅ WARN ⚠️ FAIL ❌ SKIP ⏭️).
- `checks/`: Individual check modules — `installation`, `configuration`, `runtime`, `providers`, `sources`, `docker`, `network`.

**Source connectivity:** The `_extract_primary_url()` helper in `checks/sources.py` correctly extracts URLs from adapter-specific config fields (`feed_url` for RSS, `list_url` for API, `listing_url` for Web) instead of a non-existent top-level `url`. Safe source probing uses `safe_fetch_url()` from `services/safe_fetch.py` — the same SSRF-protected client used in production. The `probe_source()` function applies tight limits (3s connect, 5s read, 10s total, 4KB max bytes) and maps exceptions to stable reason codes (`ssrf_blocked`, `timeout`, `connection_failed`, `dns_failure`, `content_type_rejected`, `http_error`). Probe results include latency and per-source details in JSON output.

**Docker diagnostics (non-invasive):** Default doctor does not run `docker run --rm alpine:3.19 nslookup`. Instead it checks Docker daemon status via `docker info` and inspects existing running containers via `docker compose ps`. DNS resolution (`nslookup`) only runs inside existing containers when `--network` is passed.

**Exit behavior:** `ainews doctor` exits 0 when no FAIL results exist, exits 1 when any check has FAIL status. JSON output includes `passed_count`, `warn_count`, `failed_count`, `skipped_count` fields.

**Doctor JSON contract:** `ainews doctor --json` outputs a versioned schema (`schema_version: 1`) with `command`, `mode` (quick/production/network flags), `outcome` (passed/failed), `counts` (pass/warn/fail/skip), and `checks` array. Each check includes `name`, `status`, `message`, optional `reason_code`, optional `remediation`, and optional `duration_ms`.

### Onboarding Architecture
The `ainews onboard` command implements a 16-stage state machine (`OnboardingService`) with resume-from-failure support. State is persisted to `onboarding-state.json` in the config directory. Stages are executed sequentially with `run_stage()` returning `StageResult` objects. The `resume()` method picks up from the last incomplete stage. Deployment, pipeline, and source profiles (`ainews_cli/profiles.py`) provide preset configurations. Bootstrap YAML files (`ainews_cli/schema.py`) enable unattended setup with cross-field validation and secret detection.

### Backup, Restore, and Migration Architecture

**Location:** `ainews_config/backup.py` (core library, Flask-free), `ainews_cli/backup_commands.py` (CLI commands)

**Backup format:** Versioned directory containing:
- `manifest.json` — schema version, backup ID, application version, config schema version, database schema version, sections with SHA-256 checksums
- `config.tar` — tarball of all config files (.env, providers.yaml, pipeline.yaml, sources.yaml, topics.yaml). When `--include-logs` is used, log files are included under `logs/` prefix.
- `database.sqlite` — consistent SQLite snapshot via backup API
- `install_metadata.json` — installation metadata

**Backup directory layout:**
```
backup_dir/
  2026-07-15T041500Z-1.4.0/
    manifest.json
    config.tar
    database.sqlite
    install_metadata.json
  pins.json  # {"pinned": ["backup_id1", ...]}
  restore-records/
    restore-*.json
```

**Backup creation:** Acquires flock on `state_dir/backup.lock`, validates config files, uses SQLite backup API for consistent snapshot, stages in temp dir, computes checksums, atomically publishes. Permissions: 0o700 for dirs, 0o600 for files. Cleans up staging directories on failure.

**Backup verification:** Non-mutating. Validates manifest schema, section presence/checksums/paths, SQLite integrity (`PRAGMA integrity_check`), config tarball parseability, cross-file validation (pipeline stages must reference defined providers), version compatibility (same major version). Returns stable reason codes: `backup_not_found`, `manifest_missing`, `manifest_corrupt`, `manifest_invalid`, `schema_too_new`, `version_incompatible`, `section_missing`, `unsafe_path`, `file_missing`, `size_mismatch`, `checksum_mismatch`, `db_corrupt`, `config_tar_corrupt`, `config_parse_error`.

**Retention/pruning:** Default 10 backups, 90 days max age. Optional `max_total_bytes` limit. Respects pinned backups. Never deletes the only verified backup. Oldest-first selection. Supports `--dry-run`. Reports `total_bytes_pruned`.

**Restore:** Creates automatic pre-restore safety backup. Supports `--config-only`, `--data-only`, `--dry-run`, `--no-lifecycle`. Acquires restore lock. Stages files, validates, atomically replaces. Writes restore record. Integrates with lifecycle driver for service stop/start. Runs post-restore health check. Rolls back to safety backup on health check failure.

**Restore plan fields:** `RestorePlan` includes `secrets_impact` (identifies .env files with secrets), `restart_actions` (post-restore steps), and `permissions_impact` (files set to 0o600).

**Lifecycle integration:** Restore accepts optional `LifecycleOperations` protocol with `stop_services()`, `start_services()`, `check_health()`. When provided, services are stopped before restore and started after. Health check failure triggers automatic rollback.

**Rollback:** On restore failure or health check failure, `_rollback_restore()` restores from the safety backup. Uses `restore_backup_inner()` (no lock acquisition, no safety backup) to avoid deadlocks.

**Migration framework:** `Migration` protocol with `id`, `from_version`, `to_version`, `reversible`, `preflight()`, `apply()`, `rollback()`. `BaseMigration` abstract class. Deterministic ordering, idempotency, downgrade refusal. `plan_migrations()` and `execute_migration_plan()` functions.

**CLI commands:**
```bash
ainews backup create [--include-logs] [--tag TAG]
ainews backup list
ainews backup show BACKUP_ID
ainews backup verify BACKUP_ID
ainews backup prune [--max-count N] [--max-age-days N] [--max-total-bytes N] [--dry-run]
ainews restore BACKUP_ID [--config-only] [--data-only] [--dry-run] [--no-lifecycle] [-y]
ainews migrations status
ainews migrations plan
ainews migrations apply [--dry-run] [-y]
```

**Exit codes:** `BACKUP_ERROR = 9` added to `ainews_cli/exit_codes.py`. `UPDATE_ERROR = 10` and `UNINSTALL_ERROR = 11` added for update and uninstall operations. `SERVICE_ERROR = 12` added for service management operations.

**Key types:** `BackupManifest`, `BackupSection`, `VerifyResult`, `RestorePlan`, `PruneResult`, `MigrationReport`, `MigrationStatusDetail`, `MigrationPlanDetail`, `MigrationApplyResult`, `LifecycleOperations` (protocol).

**Tests:** `tests/test_backup_restore.py` — 98 tests covering creation, verification, listing, pinning, pruning (count, age, total bytes), restore (full/config-only/data-only), health check rollback, lifecycle integration, WAL snapshot consistency, concurrent locking, incomplete backup cleanup, secret-free output, cross-file validation, include-logs, version compatibility, migration framework, manifest serialization, and edge cases.

### Provider Adapter Architecture
Provider management uses a pluggable adapter pattern (`ainews_cli/providers/`). Each adapter implements the `ProviderSetupAdapter` protocol with `fields()`, `probe()`, `discover_models()`, and `remediation()`. The registry (`ainews_cli/providers/registry.py`) maps type IDs to adapter classes. Built-in adapters: `ollama`, `openai`, `anthropic`, `gemini`, `eggpool`, `generic`. Adapters are independent of the Flask runtime and can be tested in isolation.

### Lifecycle Driver Architecture
Service lifecycle uses a `LifecycleDriver` protocol (`ainews_cli/lifecycle/driver.py`) with `DockerComposeDriver` and `BareMetalDriver` implementations. Commands (`ainews_cli/lifecycle/commands.py`) register as top-level CLI commands (start, stop, restart, status, logs, health, smoke). The start command integrates with `doctor` checks and `migrations` for prerequisites.

### Configuration Engine Architecture
The `ainews_config` package provides the shared configuration model used by both the CLI and (eventually) the Flask/Celery runtime. Key modules: `paths.py` (5-level path precedence chain), `fields.py` (typed field registry with 80+ operator-facing keys), `loader.py` (dotenv/YAML parsing with provenance tracking), `validation.py` (cross-file semantic checks), `transaction.py` (flock-based atomic writes with rollback). The package has zero Flask dependencies.

### MetricsCollector Method Names
The `MetricsCollector` in `services/metrics.py` uses these method names:
- `counter_inc(name, value=1, labels=None)` — NOT `increment()`
- `gauge_set(name, value, labels=None)` — NOT `set_gauge()`
- `histogram_observe(name, value, labels=None)` — NOT `observe()`
- `get_metrics()` — returns dict of all metrics
- `get_prometheus()` — returns Prometheus exposition format

### ModelLimiter Interface
The `ModelLimiter` in `services/limiter.py` is provider/model-aware:
- `acquire(provider_id, model, max_concurrent, timeout=300)` — NOT `acquire(slots=1, timeout=30)`
- `release(provider_id, model, timeout=300)`
- `get_active(provider_id, model)`
- `cleanup_stale_slots()`
- Uses Redis DB 15 for storage (NOT DB 0 or DB 2)

### Redis DB Allocation
- DB 0: Celery broker (from `CELERY_BROKER_URL` env var)
- DB 1: Config cache (in `services/config_cache.py`)
- DB 15: Flask-Limiter storage (derived from broker URL)

### CircuitBreaker Interface
The `CircuitBreaker` in `services/circuit_breaker.py`:
- Constructor requires `name` param: `__init__(self, name: str, failure_threshold=5, ...)`
- Method is `can_execute()` — NOT `is_open()`
- Factory function: `get_breaker(name, failure_threshold=5, ...)`
- Decorator: `circuit_protected(breaker_name, fallback=None)`

### Health Check Function
The health check function in `services/health.py`:
- Function name: `run_health_checks(include_celery=True, detailed=False)` — NOT `check_health()`
- `HealthResult` has fields: `status: str`, `checks: dict[str, Any]`, `version: dict[str, str] | None`

### APIAdapter Specific Notes
The `APIAdapter` in `adapters/api.py` has pagination support via `PaginationConfig`:
- `next_link` type: extracts next URL from JSON response via JSONPath selector
- `query_param` type: increments page/offset query parameter
- `none` type: disables pagination
- Respects `max_pages` limit (default 3) and `max_items` limit across all pages

APIAdapter only supports Bearer token authentication. No API key header support (e.g., `X-Api-Key`) is implemented.

APIAdapter uses these configuration fields (NOT `item_path`):
- `list_url`: URL to fetch items from
- `list_method`: `"json_array"` or `"json_object_items"`
- `list_items_path`: JSONPath to items array (optional)

### Search Provider Notes
The search providers are:
- `services/search/duckduckgo.py`: DuckDuckGo provider (default/enabled)
- `services/search/google.py`: Google provider (disabled, requires API key)
- `services/search/searxng.py`: SearxNG provider (disabled, self-hosted)
- `services/search/hybrid.py`: Hybrid provider (FTS5 + vector similarity) - ENABLED
- `services/search/sqlite_fts.py`: SQLite FTS provider (internal article search)

DeepSeek is NOT a search provider - it only appears as a regex pattern (`r"\bdeepseek\b"`) in `services/trend_detector.py` for detecting AI topic trends and in `adapters/base.py` for URL sanitization. Do not add DeepSeek to search provider documentation without implementing `services/search/deepseek.py`.

The search provider configuration in `providers.yaml` uses the key `search_providers:` (plural), NOT `search:`. Google env vars are `GOOGLE_API_KEY` and `GOOGLE_CSE_ID` (not `GOOGLE_SEARCH_API_KEY`/`GOOGLE_SEARCH_CX`).

## Shared Context

Agents should use the nested `AGENTS.override.md` files in subdirectories for more specific instructions related to those modules:

- `services/AGENTS.override.md` - Services layer conventions
- `adapters/AGENTS.override.md` - Adapters layer conventions
- `tasks/AGENTS.override.md` - Celery task conventions
- `schemas/AGENTS.override.md` - Schema conventions
- `services/llm/AGENTS.override.md` - LLM provider conventions
- `services/search/AGENTS.override.md` - Search provider conventions
- `routes/AGENTS.override.md` - Route conventions
- `routes/admin/AGENTS.override.md` - Admin route conventions
- `tests/AGENTS.override.md` - Testing conventions
- `templates/AGENTS.override.md` - Template conventions
- `static/AGENTS.override.md` - Static file conventions

## Known Intentional Layering Violations

The following are documented as intentional and should NOT be "fixed":
- `services/crawling.py` imports from `adapters.base` via `TYPE_CHECKING` block for type hints only
- `services/subagent/tools.py` imports directly from `models` and `extensions` - this is a known layering issue
- `schemas/common.py` intentionally imports from `services.config_cache` (documented with comment)
- `tasks/crawl.py` imports directly from `adapters.base` - documented in AGENTS.md

## Key Files

| File | Purpose |
|------|---------|
| `run.py` | WSGI/ASGI app entry point |
| `app.py` | Flask app factory |
| `config.py` | Flask config classes, Celery beat schedule, ProductionConfig.validate() |
| `extensions.py` | Flask extensions (db, redis, limiter) |
| `models/` | SQLAlchemy models package (article, source, newsletter, pipeline, context, etc.) |
| `constants.py` | Constants including `PipelineStatus` enum, `DEFAULT_LLM_TIMEOUT_SECONDS` |
| `tests/test_production_config.py` | 56 tests for ProductionConfig validation, fail-closed provider checks |
| `tests/test_smoke_production_config.py` | Production config validation smoke tests (Layer 1) |
| `tests/test_smoke_migrations.py` | Database migration smoke tests — real `flask db upgrade` via subprocess, verifies Alembic migration chain and table schemas (Layer 2) |
| `tests/test_smoke_celery.py` | Celery app import/config smoke tests (Layer 3) |
| `tests/test_docs_env_consistency.py` | Docs/env variable consistency smoke tests (Layer 7) |
| `scripts/ci_compose_smoke.sh` | Docker Compose boot smoke test script (Layer 6) — wired into CI as `compose-smoke` job |
| `scripts/install.sh` | Channel-aware release installer with checksum verification |
| `tests/fixtures/providers.ci.yaml` | Minimal valid Ollama provider config for CI image smoke and production app-factory tests |
| `scripts/wait_for_health.sh` | Reusable health check poller for CI scripts |
| `schemas/tasks.py` | Pydantic schemas for Celery task input validation |
| `services/prompts.py` | `esc_xml_text()`, `esc_xml_attr()` for LLM prompt escaping |
| `services/url.py` | URL validation (SSRF prevention), DNS cache |
| `services/safe_fetch.py` | Safe HTTP fetch client with SSRF protection, manual redirects, streaming byte limits, content-type allowlist |
| `tests/test_safe_fetch.py` | Safe fetch SSRF, redirect, byte-limit, content-type, timeout tests |
| `tests/test_url_security.py` | URL parser edge cases: credentials, host confusion, IPv6, encoded hosts |
| `tests/test_content_extractor_safe_fetch.py` | Content extractor ↔ safe fetch integration tests |
| `services/cache.py` | ResponseCache (L1 in-memory + L2 Redis) with LRU eviction and stampede protection |
| `services/limiter.py` | ModelLimiter (Redis-based rate limiting) |
| `services/config_utils.py` | `get_config_with_default()` for Celery-safe config |
| `services/config_cache.py` | Config cache with mtime-based invalidation |
| `services/config_unified.py` | Unified config loading + validation |
| `services/pipeline_monitor.py` | Redis minute-bucket stage metrics |
| `services/health.py` | Health check with degradation |
| `services/logging_utils.py` | PipelineLogger, `log_pipeline_event()`, `log_article_event()` |
| `services/api_tokens.py` | `generate_api_token()`, `hash_api_token_secret()`, `verify_api_token_secret()`, `parse_api_token()` |
| `services/article_validation.py` | `ValidationError(ValueError)`, `validate_final_article()` |
| `routes/admin/__init__.py` | Admin blueprint, login lockout |
| `routes/admin/api/` | Admin API endpoints (health, config, pipeline, articles, webhooks, search) |
| `routes/admin/dashboard.py` | Dashboard with serialized cache (plain dicts, not model instances) |
| `routes/public/feeds.py` | Public feed routes, RSS generation, search with analytics logging |
| `routes/decorators.py` | `commit()` helper, `commit_or_rollback()` context manager, `@require_auth` decorator |
| `routes/themes.py` | Theme CSS delivery route (public, no auth) |
| `scripts/validate_themes.py` | Theme validation CLI (bundled/directory/file modes) |
| `routes/admin/api/theme_diagnostics.py` | Admin theme diagnostics endpoint |
| `docs/theme-authoring.md` | Theme authoring guide for operators and contributors |
| `docs/theme-troubleshooting.md` | Theme troubleshooting guide with diagnostic codes |
| `docs/theme-preferences.md` | Reader-facing theme preference help |
| `docs/theme-provenance.md` | Theme source provenance and license documentation |
| `templates/partials/theme_selector.html` | Accessible theme selector UI (Phase 4) |
| `tests/test_theme_preferences.py` | Phase 4 preference system tests |
| `tasks/newsletter.py` | Newsletter generation and email delivery |
| `tasks/extract.py` | Article extraction from crawled content |
| `tasks/retry.py` | `retry_stuck` task, dead-letter handling |
| `tasks/cleanup.py` | Log cleanup, trend memory consolidation |
| `services/pipeline_degradation.py` | `post_finalize_article()`, `degrade_stage()`, `_finalize()` |
| `adapters/api.py` | API source adapter with error logging in `_fetch_item` |
| `ainews_config/` | Configuration engine: path resolver, field registry, loader, validator, transactional writer |
| `ainews_cli/` | Operator CLI: version, onboard, providers (list/add/test/models/set-default/assign/remove), start/stop/restart/status/logs/health/smoke, config (path/show/check/get/set/unset/diff/rollback), doctor |
| `ainews_cli/onboard.py` | Onboarding state machine, stage definitions, orchestration service |
| `ainews_config/backup.py` | Backup, restore, and migration framework (Flask-free) |
| `ainews_cli/backup_commands.py` | CLI commands for backup, restore, migrations |
| `tests/test_backup_restore.py` | 98 tests for backup/restore/migration system |
| `ainews_cli/profiles.py` | Deployment, pipeline, and source profile definitions |
| `ainews_cli/schema.py` | Declarative bootstrap YAML schema and validation |
| `ainews_cli/secrets.py` | Secret generation, password hashing, admin setup |
| `ainews_cli/migrations.py` | Database migration detection and execution |
| `ainews_cli/providers/` | Provider adapter protocol, built-in adapters (Ollama, OpenAI, Anthropic, Gemini, EggPool, generic), CLI commands |
| `ainews_cli/lifecycle/` | Lifecycle driver abstraction, Docker Compose and bare metal drivers, CLI commands |
| `docs/cli-reference.md` | CLI command reference documentation |
| `docs/configuration-contract.md` | Machine-oriented configuration inventory |
| `docs/backup-restore.md` | Backup, restore, and migration documentation (disaster recovery, compatibility matrix) |
| `ainews_cli/service/` | Service management: systemd units, logrotate, state tracking |
| `ainews_cli/service/commands.py` | Service CLI commands (render, install, validate, status, restart, remove) |
| `ainews_cli/service/logrotate_commands.py` | Logrotate CLI commands (configure-rotation, validate-rotation, remove-rotation) |
| `tests/test_service.py` | Service models, systemd rendering, state tracking tests |
| `tests/test_logrotate.py` | Logrotate rendering tests |
| `tests/test_cli_service.py` | CLI service command tests |

## CI Gates

### Required Checks for Protected `main`

The following CI jobs must pass before merge. These are configured as required status checks in GitHub branch protection (see `docs/release_checklist.md`):

| Job | Purpose |
|-----|---------|
| `lint-and-test` | ruff lint + mypy type-check + pytest with coverage |
| `pip-audit` | Dependency vulnerability scan |
| `trivy` | Filesystem vulnerability scan |
| `docker-build` | Image build + testing/prod app-factory smoke |
| `smoke-tests` | Production config, Celery import, migration, docs/env consistency |
| `compose-smoke` | Full Docker Compose boot + `/health` endpoint |
| `gitleaks` | Secret scanning |
| `theme-browser-smoke` | Playwright/Chromium browser tests for theme subsystem |
| `installer-smoke` | Clean-host installer validation (Linux x86_64, aarch64, macOS arm64, deferred prerequisite, full lifecycle) |

### Concurrency

CI uses `concurrency.group = ${{ github.workflow }}-${{ github.ref }}` with `cancel-in-progress: true` to save runner minutes on rapid pushes.

### Determinism Audit

All Python smoke tests are fully deterministic — no network, DNS, LLM, or external service dependencies. `compose-smoke` boots a real Docker Compose stack (inherently timing-sensitive but acceptable for integration testing).

### Local Release Validation

Run `scripts/validate_release.sh` to replicate CI gates locally. Agents should run the appropriate mode before claiming release readiness:

- `--fast` — ruff + targeted smoke tests (pre-push quick check, no mypy)
- `--full` (default) — lint + mypy + tests + smoke + Docker build + Compose smoke (release-equivalent)
- `--security` — pip-audit + gitleaks + trivy

**Agents MUST NOT claim release readiness without `--full` mode passing.** The full checklist is in `docs/release_checklist.md`.

The script generates throwaway `.env.ci` secrets, uses `COMPOSE_PROJECT_NAME=ainews-validation` for Docker isolation, and cleans up on exit.

## Security Architecture

### Route Auth
- **`authenticate_request()`** in `routes/decorators.py` — standalone helper returning `None` on success or a Flask response tuple on failure. Used by both `require_auth` decorator and blueprint `before_request` hooks.
- **`require_auth` decorator** — must be placed AFTER `@blueprint.route(...)` (innermost). Wrong order means Flask registers the unwrapped function.
- **Route classification test** — `tests/test_admin_route_auth.py:test_all_admin_routes_classified` fails if any `/admin`, `/api/v1`, or `/api-tokens` route is added without auth classification.

### CSRF
Three layers: Flask-WTF `CSRFProtect` (app-wide, exempts API blueprints), `@validate_csrf_json` (session-auth JSON endpoints), `@csrf_for_session_auth` (skips CSRF for verified bearer tokens). Bearer tokens bypass CSRF intentionally.

### 2FA
8 backup codes stored as JSON. `session.clear()` on all login paths (no `regenerate_id()` in Flask 3.x).

### Webhook Security
MultiFernet key rotation, HMAC signing with timestamps, SSRF protection on all webhook URLs.

## Key Constant Locations

- `CELERY_TASK_MAX_RETRIES`: `constants.py:6` (default: 3, configurable via env var)
- `MAX_STAGE_RETRIES`: `constants.py:9` (value: 3)
- `MAX_STAGE_FAILURES`: `constants.py:10` (value: 3)
- `MAX_TOTAL_RETRIES`: `constants.py:11` (value: 10)
- `PIPELINE_TIMEOUT_SECONDS`: `constants.py:14` (value: 3600)
- `DEFAULT_LLM_TIMEOUT_SECONDS`: `constants.py:17` (value: 120.0)
