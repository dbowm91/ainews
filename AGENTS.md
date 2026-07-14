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

## Project Structure

*   `app.py`: Application factory and configuration.
*   `models/`: Database models package (SQLAlchemy). Contains `source.py`, `article.py`, `tag.py`, `newsletter.py`, `pipeline.py`, etc.
*   `services/`: Business logic, LLM interaction, third-party service wrappers.
*   `adapters/`: Infrastructure-specific code (RSS, Web, API). Should NOT import from `services/`.
*   `tasks/`: Celery tasks for the newsletter pipeline.
*   `routes/`: Flask blueprints for public and admin interfaces.
*   `schemas/`: Pydantic models for validation and serialization.
*   `utils/`: Pure helper functions with minimal dependencies (e.g., `utils/url.py` for URL normalization).

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
- **Selector UI:** `templates/partials/theme_selector.html` — accessible popover with search, grouped options (system/built-in/custom), keyboard navigation, mobile bottom-sheet. Replaces `theme_toggle.html` in base templates.
- **Cross-tab sync:** `storage` event listener on the v2 key. Validates incoming preferences, avoids write-back loops, falls back on unknown IDs.
- **Metadata endpoint:** `GET /api/v1/themes/metadata` returns same JSON as context processor, `Cache-Control: public, max-age=60`. No auth required.

### Theme Validation CLI
`scripts/validate_themes.py` validates themes using production helpers. Modes: `--bundled` (all packaged), `--directory DIR` (scan custom), `--file FILE` (single). Flags: `--strict` (warnings fail), `--format json` (machine-readable), `--print-css` (emit CSS). Integrated into `scripts/validate_release.sh`.

### Theme Admin Diagnostics
`GET /api/v1/themes/diagnostics` (admin-authenticated) returns registry health, per-theme validity, aggregate diagnostic counts, `built_at` (real ISO timestamp of registry construction), and `overrides_bundled` per theme. Does not expose absolute paths, TOML content, or generated CSS. Uses `Cache-Control: no-store`.

### Theme Contrast Policy
`classify_contrast_findings()` checks 14 WCAG contrast pairings. `classify_accessibility_findings()` checks category badges (3:1) and status colors (4.5:1). Critical primary text < 4.5 raises `ThemeContrastError`. All other failures are warnings.

### Theme Diagnostic Codes
Stable codes in `THEME_DIAGNOSTIC_CODES` dict in `services/themes/errors.py`. Use these in CLI output, logs, tests, and admin diagnostics. `get_diagnostic_description(code)` returns human-readable description.

### Theme Comprehensive Validation (Phase 6)
- **Validation matrix**: `docs/theme-validation.md` defines the complete validation matrix with 11 theme representatives, 34 page families, 5 viewports, 16 state dimensions, and 57 risk-weighted matrix cells.
- **Lifecycle regression**: `tests/test_theme_lifecycle.py` (33 tests) validates dual-stylesheet ownership, standalone page support, CSS route integration, and metadata integrity.
- **Preference validation**: `tests/test_theme_preference_validation.py` (38 tests) validates preference parsing, legacy migration, HTMX/navigation, selector state, and cross-tab sync contracts.
- **Failure recovery**: `tests/test_theme_failure_recovery.py` (58 tests) validates registry build failures, external directory pathologies, route-level failures, and recovery assertions.
- **CI integration**: `theme-validation` job in `.github/workflows/ci.yml` runs validation CLI and theme-specific tests.
- **Total theme test count**: 568+ tests across 13 test files.

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

### Celery Beat Schedule
Key scheduled tasks:
- `run-all-sources`: Every 30 minutes (crawl_interval)
- `generate-newsletters`: Daily at newsletters_hour (default 8 AM ET)
- `backfill-embeddings`: Daily at 2 AM
- `cleanup-old-logs`: Daily at cleanup_logs_hour (default 3 AM)
- `publish-scheduled-articles`: Every 5 minutes (publish_interval)
- `retry-stuck`: Every 60 minutes
- `consolidate-trend-memory`: Daily at 3:30 AM
- `purge-trend-memory`: Daily at 3:45 AM
- `cleanup-old-versions`: Daily at 3:45 AM
- `cleanup-expired-verifications`: Every 15 minutes
- `cleanup-stale-limiter-slots`: Every 5 minutes
- `retry-failed-newsletter-deliveries`: Every 2 hours
- `recalculate-impact-scores`: Daily at 4 AM
- `cleanup-inactive-subscribers`: Daily at 1 AM

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
