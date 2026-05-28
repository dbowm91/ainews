# AINews Consolidated Implementation Plan

**Status:** COMPLETED
**Last Updated:** 2026-05-28
**Source:** Consolidated from 7 architecture review files

---

## Overview

This plan consolidates findings from architecture reviews across all modules. Items are organized into logical phases with parallelization opportunities indicated as "Waves". Each wave represents a group of items that can be worked on in parallel by different agents.

**IMPORTANT:** This plan is primarily a documentation accuracy fix. Most items correct mismatches between documentation files and actual code. The bugs in Phase 1 are the only runtime code changes.

**Target files:** The architecture docs live in `architecture/` directory. The bugs in Phase 1 require code changes in the source files listed.

---

## Phase 1: Critical Bug Fixes (Must Fix First)

**These are real runtime bugs. Each must be verified with a test or manual verification after fixing.**

### 1.1 Missing `UnsafeURLError` Import — Runtime Crash
- **Priority:** HIGH
- **File:** `routes/admin/sources.py:59`
- **Issue:** `except UnsafeURLError as e:` is used but `UnsafeURLError` is never imported. This will raise `NameError` at runtime when `validate_url_safe()` raises for invalid URLs.
- **Fix:** Add `from utils.url import UnsafeURLError` to imports at top of file.
- **Verification:** Add a test that calls the route handler with an invalid URL and confirms no `NameError` is raised (the `ValueError`/`UnsafeURLError` should be caught properly).

### 1.2 `generate_daily_newsletters` Missing `@shared_task` Decorator
- **Priority:** HIGH
- **File:** `tasks/newsletter.py:476`
- **Issue:** `def generate_daily_newsletters(self, ...)` has no `@shared_task` decorator, so it's not registered as a Celery task. The function takes `self` suggesting it's in a Task class but it's standalone.
- **Fix:** Add `@shared_task(bind=True, ...)` decorator consistent with other tasks in the file.
- **Verification:** Verify `generate_daily_newsletters` appears in `celery_app.control.inspect().registered()` after fix.

### 1.3 `validate_url_safe()` Exception Type Mismatch
- **Priority:** HIGH
- **File:** `utils/url.py:245-264`
- **Issue:** Function raises `ValueError` for empty URL, unsupported scheme, or missing hostname. `UnsafeURLError` is only raised for DNS/blocked-IP failures. But the docstring claims `UnsafeURLError` for all cases. Callers that only catch `UnsafeURLError` will miss `ValueError` exceptions.
- **Fix:** Either (a) make all invalid URL cases raise `UnsafeURLError` (preferred for consistent API), or (b) fix the docstring to accurately document the two exception types. If choosing (b), also update all callers in `adapters/web.py:55`, `adapters/rss.py`, etc. to catch `ValueError` as well.
- **Verification:** Test each exception path: empty URL, unsupported scheme (e.g., `ftp://`), no hostname, DNS failure, blocked IP.

### 1.4 `ErrorHandlingMiddleware` Behavior Mismatch
- **Priority:** MEDIUM
- **File:** `services/subagent/middleware.py:64-80`
- **Issue:** Documentation says it catches errors and returns error dict. Actual implementation re-raises exceptions after logging.
- **Fix:** Update documentation to match actual behavior (re-raises after logging). No code change needed.
- **Verification:** Read the middleware code and confirm documentation matches.

### 1.5 `ModelLimiter` Uses Wrong MetricsCollector Method
- **Priority:** HIGH
- **File:** `services/limiter.py:122-126`
- **Issue:** Calls `get_metrics().increment(...)` but the actual method on MetricsCollector is `counter_inc()`. This will raise `AttributeError` at runtime when slot leak detection triggers.
- **Fix:** Change `get_metrics().increment(...)` to `get_metrics().counter_inc(...)`.
- **Verification:** Add a test that triggers the slot leak detection code path and confirms no `AttributeError`.

---

## Phase 2: Documentation Corrections — Function Signatures

**All items in this phase are documentation-only fixes. They correct mismatches between architecture docs and actual code.**

### 2.1 LLM Provider Functions

#### 2.1.1 `get_provider_for_role()` Return Type
- **File:** `services/llm/__init__.py:45`
- **Doc says:** Returns `BaseLLMProvider`
- **Actual:** `def get_provider_for_role(role: str) -> Tuple[BaseLLMProvider, str, int, str]:` — returns `(provider, model, max_tokens, provider_id)`
- **Fix:** Update architecture doc return type to show 4-tuple.

#### 2.1.2 `get_provider_chain()` Return Type
- **File:** `services/llm/__init__.py:57-97`
- **Doc says:** Returns `list[str]`
- **Actual:** Returns a generator yielding `(provider, model, max_tokens, provider_id)` tuples. Filters out providers with open circuits.
- **Fix:** Update documentation to show generator of tuples.

#### 2.1.3 `cost_tracker.py` Function Names
- **File:** `services/cost_tracker.py`
- **Doc says:** `record_usage()`, `get_usage_summary()`
- **Actual:** `_load_rates()` (private, line 63), `get_cost_summary()` (public, line 77), `_parse_metric_key()` (private). There is no `record_usage()` function — cost data comes from MetricsCollector counters.
- **Fix:** Update documentation to use correct function names and explain that cost data is derived from metrics counters.

#### 2.1.4 `_retry_with_backoff` Signature
- **File:** `services/llm/base.py:131-137`
- **Doc says:** Named params `max_retries`, `base_delay`, `max_delay`
- **Actual:** `_retry_with_backoff(self, func, model, *args, **kwargs)` — positional `model` arg with class constants for defaults (`RETRY_MAX_ATTEMPTS=3`, `RETRY_BASE_DELAY=1.0`, `RETRY_MAX_DELAY=30.0`)
- **Fix:** Update documentation to match actual signature and note that retry params are class constants.

### 2.2 Search Provider Functions

#### 2.2.1 `SearxNGProvider` Class Name
- **File:** `services/search/searxng.py:59`
- **Doc says:** `SearxNGProvider`
- **Actual:** `class SearXNGSearchProvider(BaseSearchProvider):`
- **Fix:** Update all references to correct class name.

#### 2.2.2 `HybridSearchProvider` Base Class
- **File:** `services/search/hybrid.py:78`
- **Doc says:** Extends `BaseSearchProvider`
- **Actual:** `class HybridSearchProvider(SearchProvider):` — `SearchProvider` is the DB search ABC (at `services/search/base.py:43`), distinct from `BaseSearchProvider` (the web search ABC at line 18)
- **Fix:** Update base class reference to `SearchProvider`.

#### 2.2.3 `get_article_search_provider()` Return Type
- **File:** `services/search/__init__.py:56`
- **Doc says:** Returns `BaseSearchProvider`
- **Actual:** Returns `SearchProvider`
- **Fix:** Update return type reference.

#### 2.2.4 `SearchResult` Missing `score` Field
- **File:** `services/search/base.py:10-15`
- **Doc says:** Has `score: float = 0.0`
- **Actual:** Only has `title`, `url`, `snippet`, `source` — no `score` field
- **Fix:** Remove `score` field from documentation.

#### 2.2.5 `_context_tool_search_web` → `_search_web`
- **File:** `services/subagent/tools.py:165`
- **Doc says:** `_context_tool_search_web`
- **Actual:** `def _search_web(query: str, max_results: int = 5) -> str:`
- **Fix:** Update function name reference.

### 2.3 Adapter Functions

#### 2.3.1 `BaseSourceAdapter.__init__` Signature
- **File:** `adapters/base.py:41-48`
- **Doc says:** Constructor omitted
- **Actual:** `def __init__(self, source_config: SourceConfig):` — takes SourceConfig, validates config via `self.config_class` if present
- **Fix:** Add constructor documentation showing SourceConfig parameter.

#### 2.3.2 `fetch()` Return Type
- **File:** `adapters/base.py:51`
- **Doc says:** `list[dict]`
- **Actual:** `def fetch(self) -> list[Any]: ...`
- **Fix:** Update return type.

#### 2.3.3 `parse_item()` Signature
- **File:** `adapters/base.py:54`
- **Doc says:** Param name `item`, return `RawItem`
- **Actual:** `def parse_item(self, raw: Any) -> Optional[RawItem]: ...`
- **Fix:** Update parameter name and return type.

#### 2.3.4 `SSRFSafeRedirectHandler` Method Name
- **File:** `adapters/session.py:37`
- **Doc says:** `redirect_request`
- **Actual:** `def __call__(self, request, response, **kwargs):` — the class is callable, not using `redirect_request`
- **Fix:** Update method name in documentation to `__call__`.

### 2.4 Infrastructure Functions

#### 2.4.1 `get_redis()` Signature
- **File:** `extensions.py:68`
- **Doc says:** `get_redis(db: int = 0)`
- **Actual:** `def get_redis():` — no parameters, returns Redis client connected to default DB
- **Fix:** Remove `db` parameter from documentation.

#### 2.4.2 Redis DB Allocation Table
- **Doc says:** DB 0 = general cache, DB 1 = rate limiter, DB 2 = config cache
- **Actual:**
  - DB 0: Celery broker (from `CELERY_BROKER_URL`, default `redis://localhost:6379/0`)
  - DB 1: Config cache (via `CONFIG_CACHE_REDIS_URL` in `services/config_cache.py:280-281`)
  - DB 15: Flask-Limiter storage only (`_get_limiter_storage_uri()` in `extensions.py:18-31`)
  - DB 2: NOT USED
- **Fix:** Update Redis DB allocation documentation.

#### 2.4.3 SQLite Pragma Function Name
- **File:** `app.py:164`
- **Doc says:** `_configure_sqlite_pragmas`
- **Actual:** `def set_sqlite_pragma(dbapi_conn, _):`
- **Also:** Doc omits `PRAGMA temp_store=MEMORY` (line 171) and `PRAGMA mmap_size=268435456` (line 172)
- **Fix:** Update function name and document all pragmas.

#### 2.4.4 `HealthResult` Field Types
- **File:** `services/health.py:19-25`
- **Doc says:** `checks: dict[str, bool]`, `details: dict[str, str]`
- **Actual:** `checks: dict[str, Any]`, `version: dict[str, str] | None = None` (no `details` field)
- **Fix:** Update field types.

#### 2.4.5 Health Check Function Name
- **File:** `services/health.py:121`
- **Doc says:** `check_health()`
- **Actual:** `def run_health_checks(include_celery: bool = True, detailed: bool = False) -> HealthResult:`
- **Fix:** Update function name and signature.

#### 2.4.6 `ModelLimiter.acquire()` Signature
- **File:** `services/limiter.py:39-45`
- **Doc says:** `acquire(slots=1, timeout=30)`
- **Actual:** `def acquire(self, provider_id: str, model: str, max_concurrent: int, timeout: int = 300):`
- **Fix:** Update signature documentation.

#### 2.4.7 `MetricsCollector` Method Names
- **File:** `services/metrics.py`
- **Doc says:** `increment()`, `gauge()`, `histogram()`, `export_prometheus()`
- **Actual:** `counter_inc()` (line 44), `gauge_set()` (line 60), `histogram_observe()` (line 77), `get_prometheus()` (line 219)
- **Fix:** Update all method name references.

#### 2.4.8 `CircuitBreaker` Constructor and Methods
- **File:** `services/circuit_breaker.py`
- **Doc says:** `__init__(self, failure_threshold=5, ...)`, `is_open()` method
- **Actual:** `__init__(self, name: str, failure_threshold=5, recovery_timeout=60.0, half_open_max_calls=1, window_seconds=120.0)`, method is `can_execute()` (line 155)
- **Fix:** Update constructor (add required `name` param) and method name.

#### 2.4.9 `dispatch_webhook` Signature
- **File:** `services/webhooks.py:194-202`
- **Doc says:** `dispatch_webhook(event_type, payload)`
- **Actual:** `def dispatch_webhook(webhook_id: int, name: str, url: str, secret: str, event_type: str, event_data: dict[str, Any], idempotency_key: str | None = None) -> tuple[bool, str | None]:` — 7 parameters
- **Fix:** Update signature documentation.

#### 2.4.10 `log_pipeline_event` / `log_article_event` Parameter Order
- **File:** `services/logging_utils.py`
- **Doc says:** `(event_type, article_id, stage, **kwargs)`
- **Actual:** `log_pipeline_event(stage: str, event: str, article_id=None, run_id=None, level="info", **extra)` and `log_article_event(article_id: int, event: str, level="info", **extra)`
- **Fix:** Update parameter order documentation.

#### 2.4.11 `ResponseCache` Default TTL
- **File:** `services/cache.py:49`
- **Doc says:** 300 seconds
- **Actual:** `self._ttl = 120` — 120 seconds
- **Fix:** Update default TTL.

#### 2.4.12 `RoleConfig` Defaults
- **File:** `schemas/pipeline.py:16-33`
- **Doc says:** `provider: "ollama-local"`, `temperature: 0.5`
- **Actual:** `provider: str = Field(..., min_length=1)` (required, no default), `temperature: float = Field(default=0.0, ge=0.0, le=2.0)`
- **Fix:** Update defaults (provider is required, temperature is 0.0).

#### 2.4.13 `SubagentStageConfig` Defaults
- **File:** `schemas/pipeline.py:94,99`
- **Doc says:** `enabled: True`, `timeout_seconds: 60`
- **Actual:** `enabled: bool = False`, `timeout_seconds: int = Field(default=120, ge=10, le=600)`
- **Fix:** Update defaults.

#### 2.4.14 `SubagentStageConfig` Missing Fields
- **File:** `schemas/pipeline.py:93-106`
- **Doc says:** 4 fields (`enabled`, `tools`, `max_retries`, `timeout_seconds`)
- **Actual:** 12 fields including `provider`, `model`, `max_tokens`, `temperature`, `system_prompt`, `max_retries`, `retry_delay`, `task_template`, `tools`, `max_iterations`
- **Fix:** Document all fields.

#### 2.4.15 `NewsletterConfig` Field Names
- **File:** `schemas/pipeline.py:52-58`
- **Doc says:** `daily_send_time`
- **Actual:** `send_time: str = "08:00"` (not `daily_send_time`). No `enable_topic_newsletters` or `batch_size` fields. Has `prep_minutes` instead.
- **Fix:** Update field names.

#### 2.4.16 `cached_config_with_mtime` Signature
- **File:** `schemas/common.py:82-97`
- **Doc says:** 2-param: `(key, loader_fn)`
- **Actual:** `def cached_config_with_mtime(key: str, loader_fn: Callable[[], T], config_path: Path, ttl: int = 300) -> T:` — 4 parameters
- **Fix:** Update signature.

#### 2.4.17 `traced_stage` Signature
- **File:** `services/logging_utils.py:279`
- **Doc says:** `(stage_name)`
- **Actual:** `def traced_stage(stage: str, operation: str = "execute"):`
- **Fix:** Update signature.

### 2.5 Prompt Functions

#### 2.5.1 `get_system_prompt()` Signature
- **File:** `services/prompts.py:95-112`
- **Doc says:** `get_system_prompt(stage)`
- **Actual:** `def get_system_prompt(role: str, yaml_prompt: str | None) -> str:` — `yaml_prompt` is required (not optional)
- **Fix:** Update signature.

#### 2.5.2 `load_prompt_file()` Signature
- **File:** `services/prompts.py:85-92`
- **Doc says:** `load_prompt_file(filename) -> str`
- **Actual:** `def load_prompt_file(name: str) -> str | None:` — returns `None` when file not found
- **Fix:** Update return type to show Optional.

#### 2.5.3 `count_tokens()` Default
- **File:** `services/prompts.py:34`
- **Doc says:** `model="gpt-4"`
- **Actual:** `model: str | None = None`
- **Fix:** Update default value.

#### 2.5.4 Truncation Function Parameter Names
- **File:** `services/prompts.py:115,157`
- **Doc says:** `max_tokens`
- **Actual:** `max_chars` (e.g., `sliding_window_truncate(text: str, max_chars: int = 8000, ...)`)
- **Fix:** Update parameter names.

#### 2.5.5 `smart_truncate_context()` Return Type
- **File:** `services/prompts.py:316-325`
- **Doc says:** Returns `str`
- **Actual:** `def smart_truncate_context(text: str, max_chars: int = 8000, ...) -> tuple[str, bool]:`
- **Fix:** Update return type.

#### 2.5.6 `summarize_context()` Signature
- **File:** `services/prompts.py:257`
- **Doc says:** Simplified signature
- **Actual:** `def summarize_context(text: str, llm_provider=None, max_tokens: int = 512, temperature: float = 0.0) -> str:`
- **Fix:** Update signature with all parameters.

### 2.6 Task Functions

#### 2.6.1 Task Signatures Missing `run_id` Parameter
- **Files:** `tasks/select.py:59`, `tasks/research.py:267`, `tasks/write.py:48`, `tasks/edit.py:396`
- **Issue:** All stage task functions have `run_id=None` parameter that's not documented
- **Fix:** Add `run_id` to all task function signatures in documentation.

---

## Phase 3: Schema & Model Documentation Corrections

### 3.1 Article Model

#### 3.1.1 `created_at`/`updated_at` Usage
- **Status:** ALREADY CORRECT — Uses `datetime.now(timezone.utc)` not deprecated `datetime.utcnow`

#### 3.1.2 Missing Relationships
- **File:** `models/article.py:56-63`
- **Issue:** `tags`, `metrics`, `citations` relationships not documented
- **Fix:** Document all relationships: `citations` → Citation (one-to-many), `tags` → Tag (many-to-many via article_tags), `metrics` → ArticleMetric (one-to-one)

#### 3.1.3 `source_id` Foreign Key
- **Status:** ALREADY CORRECT — Has `ondelete="CASCADE"`

### 3.2 Source Model

#### 3.2.1 `name` Field
- **Status:** ALREADY CORRECT — Has `nullable=False, index=True`

#### 3.2.2 `active` Index
- **Status:** ALREADY CORRECT — Documented in models.md

### 3.3 Subscriber Model

#### 3.3.1 Unique Constraint
- **File:** `models/newsletter.py:78-80`
- **Issue:** Unique constraint on `(email, newsletter_type)` undocumented
- **Fix:** Add constraint documentation: `db.UniqueConstraint("email", "newsletter_type", name="uq_email_newsletter")`

### 3.4 AdminUser Model

#### 3.4.1 `username` Index
- **Status:** ALREADY CORRECT — `username` is indexed with `index=True`

### 3.5 Newsletter Model

#### 3.5.1 `newsletter_articles` Association Table
- **File:** `models/newsletter.py:8-13`
- **Issue:** Association table columns not fully documented
- **Actual columns:** `newsletter_id`, `article_id`, `position` (nullable=False, default=0), `created_at`
- **Fix:** Document all association table columns.

### 3.6 TopicNote Model
- **Issue:** Missing complete documentation
- **Fix:** Add TopicNote model with 5 fields (`id`, `topic`, `note`, `source`, `created_at`, `updated_at`) and unique constraint on `(topic, source)` at `models/context.py:21`.

### 3.7 TrendMemory Model

#### 3.7.1 Field Order
- **Issue:** Documentation has incorrect field order
- **Fix:** Correct field order to: `topic, signal, importance, source_article_id, expires_at, last_consolidated_at, created_at, last_accessed_at, embedding`

### 3.8 PipelineStatus Transitions
- **File:** `constants.py:52-64`
- **Issue:** Simplified diagram missing SELECTING, SELECTED, FAILED states
- **Actual transitions from `VALID_TRANSITIONS`:**
  - PENDING → SELECTING, RESEARCHING, REVIEW
  - SELECTING → SELECTED, FAILED
  - SELECTED → RESEARCHING, FAILED
  - RESEARCHING → WRITING, FAILED
  - W → EDITING, FAILED
  - WRITTEN → EDITING, FAILED
  - EDITING → REVIEW, DONE, FAILED
  - REVIEW → DONE, FAILED
  - DONE → (terminal)
  - SKIPPED → (terminal)
  - FAILED → PENDING
- **Fix:** Update transitions diagram to match `VALID_TRANSITIONS` in `constants.py`.

### 3.9 Schema Corrections

#### 3.9.1 `SelectArticleInput` → `SelectArticleTask`
- **File:** `schemas/tasks.py:33`
- **Issue:** `SelectArticleInput` doesn't exist. Class is `SelectArticleTask`.
- **Fix:** Update all references.

#### 3.9.2 `NewsletterPipelineConfig` Fields
- **File:** `schemas/pipeline.py:60-90`
- **Issue:** Documentation shows required fields, but all have `default_factory=lambda: RoleConfig(...)`
- **Fix:** Update to show optional fields with defaults.

#### 3.9.3 `SubagentConfig` `enabled` Field
- **File:** `schemas/pipeline.py:121-125`
- **Status:** ALREADY CORRECT — `enabled` is on `SubagentStageConfig`, not `SubagentConfig`

#### 3.9.4 Missing Schema Documentation
- **Issue:** Several schemas not documented
- **Fix:** Document: `ProviderDef` (in `schemas/common.py:23-29`), `SubagentResponse`, `ResearchSynthesisResponse`, `EditContextualizationResponse`, `ToolCall`, `ToolResult`, `ToolCallingResponse` (all in `schemas/llm_responses.py`)

---

## Phase 4: Route Documentation Corrections

### 4.1 Trigger-Crawl Route Path
- **File:** `routes/admin/pipelines.py:84`
- **Doc says:** `/admin/pipelines/trigger-crawl`
- **Actual:** Route is `@admin_bp.route("/trigger-crawl")` which resolves to `/admin/trigger-crawl`
- **Fix:** Update route path.

### 4.2 Semantic Search Endpoint Path
- **File:** `routes/admin/trend_memory.py:117`
- **Doc says:** `/api/trend-memory/semantic-search`
- **Actual:** Route is `@admin_bp.route("/api/trend-memory/semantic-search")` which resolves to `/admin/api/trend-memory/semantic-search`
- **Fix:** Update endpoint path to include `/admin` prefix.

### 4.3 Session Key for User Agent
- **File:** `routes/decorators.py:44`
- **Doc says:** `session['ua']`
- **Actual:** `stored_user_agent = session.get("user_agent")`
- **Fix:** Update key name.

### 4.4 Missing Admin Routes
- **Issue:** Several routes not documented
- **Fix:** Add documentation for:
  - `/admin/sources/add` [POST] — `routes/admin/sources.py:39`
  - `/admin/trend-memory` [GET] — `routes/admin/trend_memory.py:16`
  - `/admin/trend-memory/delete/<id>` [POST] — `routes/admin/trend_memory.py:53`
  - `/admin/trend-memory/delete-expired` [POST] — `routes/admin/trend_memory.py:85`
  - `/admin/api/trend-memory/semantic-search` [GET] — `routes/admin/trend_memory.py:117`

### 4.5 Rate Limiting Claim
- **Doc says:** "Admin routes have stricter rate limits"
- **Actual:** Only `/admin/login` and `/admin/verify-2fa` have explicit `@limiter.limit("10 per minute")` decorators. All other admin routes rely on the global default limit.
- **Fix:** Correct documentation.

### 4.6 `api_tokens_bp` Registration
- **File:** `app.py:197`
- **Doc says:** Registered with `url_prefix="/api-tokens"`
- **Actual:** `app.register_blueprint(api_tokens_bp)` — no `url_prefix`. Routes include the full `/api-tokens` path.
- **Fix:** Update registration documentation.

### 4.7 Logout Method
- **File:** `routes/admin/auth.py:188`
- **Status:** ALREADY CORRECT — Requires POST method only

---

## Phase 5: Adapter & Utils Documentation

### 5.1 Missing Adapter Methods
- **Issue:** Several methods not documented in architecture docs
- **Fix:** Document: `match_topics(item) -> RawItem` (`adapters/base.py:81`), `get_adapter_class(source_type) -> type` (`adapters/base.py:31`), `_classify_topics(title, text) -> list[str]` (`adapters/base.py:109`), `_get_match_text(item) -> str` (`adapters/base.py:90`), `_hash_ext_id(url, title) -> str` (`adapters/base.py:97`), `__enter__`/`__exit__` context manager (`adapters/base.py:71-75`)

### 5.2 `services/url.py` Relationship with `utils/url.py`
- **Issue:** Duplication description oversimplified
- **Actual:** `services/url.py` re-exports `TRACKING_PARAMS`, `normalize_title`, and `normalize_url` from `utils/url.py` (line 15). Only `UnsafeURLError`, `_resolve_and_check`, and `validate_url_safe` are truly duplicated with config support.
- **Fix:** Clarify the relationship.

### 5.3 `WebConfig.base_url` Field
- **Issue:** Not documented
- **Fix:** Add field documentation — `base_url` is used in `adapters/web.py:160,166` for URL resolution.

### 5.4 `validate_url_safe()` Exception Documentation
- **Status:** Must be fixed (see 1.3 above)

### 5.5 `UnsafeURLError` Inherits from `ValueError`
- **Status:** ALREADY CORRECT — Documented correctly

---

## Phase 6: Service Documentation

### 6.1 Config Cache Architecture
- **File:** `services/config_cache.py`
- **Issue:** Two-tier cache (L1 memory + L2 Redis) not documented
- **Fix:** Document L1 (in-memory, 500 entries max) + L2 (Redis, DB 1) architecture.

### 6.2 Health Check Function
- **Status:** Must be fixed (see 2.4.5 above)

### 6.3 Provider Count
- **Doc says:** 16 providers
- **Actual:** 14 providers defined in `providers.yaml`, 1 enabled (ollama-local)
- **Fix:** Update count.

### 6.4 `DeepSeek` NOT a Search Provider
- **Status:** ALREADY CORRECT — DeepSeek is only a regex pattern in `services/trend_detector.py`

### 6.5 Email Function Signatures
- **File:** `services/email.py:185-191`
- **Issue:** `send_verification_email` has additional `unsubscribe_url: str` and optional `site_name: str = "ainews//"` params not documented
- **Fix:** Update signature documentation.

---

## Phase 7: Pipeline & Subagent Documentation

### 7.1 Middleware Chain Order
- **Status:** ALREADY CORRECT — Documented as Logging → Timing → ErrorHandling

### 7.2 Self-Correction Behavior
- **Status:** ALREADY CORRECT — Documented in subagent.md

### 7.3 Tool Timeout Behavior
- **Status:** ALREADY CORRECT — Documented that it applies to entire LLM call

### 7.4 Pipeline Timeout
- **File:** `constants.py:14`
- **Status:** EXISTS — `PIPELINE_TIMEOUT_SECONDS = safe_int("PIPELINE_TIMEOUT_SECONDS", 3600)`
- **Issue:** Auto-dead-letter behavior not documented
- **Fix:** Document pipeline timeout (default 3600s) and auto-dead-letter behavior in `tasks/pipeline.py:316-331`.

### 7.5 `VALID_PIPELINE_STATUSES` Incompleteness
- **File:** `constants.py:97-108`
- **Issue:** Excludes SELECTING, SELECTED, WRITTEN, FAILED states
- **Fix:** Document full set of valid statuses and explain the intent (used for validation, excludes transient states).

### 7.6 `MAX_CONSECUTIVE_FAILURES` Config
- **File:** `config.py:67`
- **Status:** EXISTS — `MAX_CONSECUTIVE_FAILURES = safe_int("MAX_CONSECUTIVE_FAILURES", 10)`
- **Issue:** Not documented
- **Fix:** Document default of 10, configurable via environment variable.

### 7.7 Newsletter Lock Mechanism
- **Issue:** Redis-based lock not documented
- **Fix:** Add documentation for `_check_newsletter_lock` in `tasks/newsletter.py:366-409`.

### 7.8 Shadow Quality Assessments
- **Issue:** `lightweight_quality_signals()` not documented
- **Fix:** Add documentation for shadow quality assessment in `tasks/research.py:181-201`, `tasks/write.py:106-125`, `tasks/edit.py:340-364`.

### 7.9 A/B Experiment Distribution
- **Issue:** 70/15/15 split not documented
- **Fix:** Add documentation for `_assign_experiment_group()` in `tasks/select.py:19-43` with distribution percentages.

### 7.10 `_search_web` Function
- **Status:** Must be fixed (see 2.2.5 above)

---

## Phase 8: Low Priority Items

### 8.1 `TRACKING_PARAMS` Documentation
- **Status:** ALREADY CORRECT — 14 params documented

### 8.2 `format_date()` Singular Forms
- **Status:** ALREADY CORRECT — Uses correct singular forms

### 8.3 `parse_date()` Fallback
- **Status:** ALREADY CORRECT — Documented fallback to `email.utils`

### 8.4 Configuration Examples
- **Issue:** Add comprehensive example with all fields
- **Fix:** Add configuration example referencing `pipeline.yaml`.

### 8.5 Circuit Breaker Section
- **Status:** ALREADY CORRECT — Section is complete in pipeline.md

### 8.6 RSSAdapter Redirect Handler
- **Status:** ALREADY CORRECT — Functionality works, deferred as low priority

---

## Implementation Waves (Parallelization Opportunities)

### Wave 1: Critical Bug Fixes (Sequential — Must Complete First)
**These are runtime code changes that affect correctness. Complete before any documentation work.**

| Item | Description | Files to Modify | Subagent? |
|------|-------------|-----------------|-----------|
| 1.1 | Fix missing `UnsafeURLError` import | `routes/admin/sources.py` | No — single import line |
| 1.2 | Add `@shared_task` decorator | `tasks/newsletter.py` | No — single decorator |
| 1.3 | Fix `validate_url_safe()` exception behavior | `utils/url.py` + callers in `adapters/` | No — careful, affects multiple files |
| 1.4 | Fix `ErrorHandlingMiddleware` docs | Architecture docs only | No — doc-only |
| 1.5 | Fix `MetricsCollector` method call | `services/limiter.py` | No — single method name |

### Wave 2: Function Signature Corrections (Parallel — 3 Subagents)
**All documentation-only fixes. No runtime code changes.**

**Subagent A — LLM & Search (files: `architecture/llm-providers.md`, `architecture/search-providers.md`, `architecture/subagent.md`):**
| Item | Description |
|------|-------------|
| 2.1.1 | Fix `get_provider_for_role()` return type |
| 2.1.2 | Fix `get_provider_chain()` return type |
| 2.1.3 | Fix `cost_tracker.py` function names |
| 2.1.4 | Fix `_retry_with_backoff` signature |
| 2.2.1 | Fix `SearxNGProvider` → `SearXNGSearchProvider` |
| 2.2.2 | Fix `HybridSearchProvider` base class |
| 2.2.3 | Fix `get_article_search_provider()` return type |
| 2.2.4 | Remove `SearchResult.score` field |
| 2.2.5 | Fix `_context_tool_search_web` → `_search_web` |

**Subagent B — Adapters & Utils (files: `architecture/adapters.md`, `architecture/utils.md`):**
| Item | Description |
|------|-------------|
| 2.3.1 | Fix `BaseSourceAdapter.__init__` signature |
| 2.3.2 | Fix `fetch()` return type |
| 2.3.3 | Fix `parse_item()` signature |
| 2.3.4 | Fix `SSRFSafeRedirectHandler` method name |
| 5.1-5.3 | Document missing adapter methods and `WebConfig.base_url` |

**Subagent C — Infrastructure (files: `architecture/infrastructure.md`, `architecture/config.md`, `architecture/overview.md`):**
| Item | Description |
|------|-------------|
| 2.4.1-2.4.17 | Fix all infrastructure function signatures |

### Wave 3: Schema & Model Corrections (Parallel — 2 Subagents)
**All documentation-only fixes.**

**Subagent D — Models (files: `architecture/models.md`):**
| Item | Description |
|------|-------------|
| 3.1-3.8 | Fix all model documentation issues |

**Subagent E — Schemas (files: `architecture/schemas.md`):**
| Item | Description |
|------|-------------|
| 3.9.1-3.9.4 | Fix all schema documentation issues |

### Wave 4: Route & Service Documentation (Parallel — 2 Subagents)
**All documentation-only fixes.**

**Subagent F — Routes (files: `architecture/routes.md`):**
| Item | Description |
|------|-------------|
| 4.1-4.7 | Fix all route documentation issues |

**Subagent G — Services (files: `architecture/infrastructure.md`, `architecture/overview.md`):**
| Item | Description |
|------|-------------|
| 6.1-6.5 | Fix all service documentation issues |

### Wave 5: Pipeline & Low Priority (Parallel — 2 Subagents)
**All documentation-only fixes.**

**Subagent H — Pipeline (files: `architecture/pipeline.md`, `architecture/prompts.md`, `architecture/tasks.md`):**
| Item | Description |
|------|-------------|
| 2.5-2.6 | Fix prompt and task function signatures |
| 7.1-7.10 | Fix all pipeline documentation issues |

**Subagent I — Low Priority (various files):**
| Item | Description |
|------|-------------|
| 8.1-8.6 | Fix all low priority items |

---

## Verification Checklist

All items verified and complete:
- [x] `routes/admin/sources.py` imports `UnsafeURLError`
- [x] `tasks/newsletter.py` has `@shared_task` on `generate_daily_newsletters`
- [x] `validate_url_safe()` documentation matches actual exception behavior (now raises `UnsafeURLError` for all cases)
- [x] All function signatures match actual code (verified in Wave 2)
- [x] All return types match actual implementations (verified in Wave 2)
- [x] All default values match actual defaults (verified in Wave 2)
- [x] All class names match actual class names (verified in Wave 2)
- [x] All route paths match actual route definitions (verified in Wave 4)
- [x] All field names match actual schema fields (verified in Wave 3)
- [x] All method names match actual method names (verified in Wave 2)
- [x] Provider count updated (14 total, 1 enabled)
- [x] Redis DB allocation corrected (DB 0 = broker, DB 1 = config cache, DB 15 = limiter)
- [x] `ruff check . --exclude .venv` passes (2 pre-existing S311 warnings in adapters/web.py only)

---

## Notes

- **APIAdapter/WebAdapter close() Design:** These adapters intentionally have no-op `close()` because they share the global session. RSSAdapter owns its own session and closes it properly. This is BY DESIGN.
- **utils/url.py and services/url.py Duplication:** Intentional for layering — `utils/url.py` is for adapters, `services/url.py` is for services with config support. `services/url.py` re-exports `TRACKING_PARAMS`, `normalize_title`, `normalize_url` from `utils/url.py`.
- **DeepSeek is NOT a search provider:** DeepSeek is only a regex pattern in `services/trend_detector.py` and `adapters/base.py`. Do NOT list it as a search provider.
- **SubagentConfig has no top-level `enabled` field:** The `enabled` field is on `SubagentStageConfig`, not `SubagentConfig`.
- **Task name is `retry_stuck`:** The Celery task defined at `tasks/retry.py:78` is named `retry_stuck`. The beat schedule key may be different (`retry-stuck-articles`).
- **Config cache is two-tier:** L1 (in-memory, 500 entries) + L2 (Redis, DB 1).
- **Limiter uses Redis DB 15:** Not DB 0 or DB 2.
- **PipelineLog uses `meta` not `metadata`:** Due to SQLAlchemy reserved name restriction.

---

## Implementation Order Recommendation

1. **First (Wave 1):** Fix critical bugs — these affect runtime correctness
2. **Second (Wave 2):** Fix function signatures — these affect developer understanding
3. **Third (Wave 3):** Fix schema and model docs — these affect data model understanding
4. **Fourth (Wave 4):** Fix route and service docs — these affect API understanding
5. **Fifth (Wave 5):** Fix pipeline and low priority — these affect advanced understanding

---

*Plan consolidated: 2026-05-28*
*All claims verified against codebase on 2026-05-28*
*Implementation completed: 2026-05-28*
