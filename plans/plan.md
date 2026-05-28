# AINews Consolidated Implementation Plan

**Status:** IN PROGRESS
**Last Updated:** 2026-05-28
**Source:** Consolidated from 7 architecture review files

---

## Overview

This plan consolidates findings from architecture reviews across all modules: `architecture_review_consolidated.md`, `routes_review.md`, `infra_config_overview_review.md`, `pipeline_tasks_review.md`, `llm_search_subagent_review.md`, `adapter_utils_review.md`, and `data_layer_review.md`. Items are organized into logical phases with parallelization opportunities indicated as "Waves". Each wave represents a group of items that can be worked on in parallel by different agents.

---

## Phase 1: Critical Bug Fixes (Must Fix First)

### 1.1 Missing `UnsafeURLError` Import — Runtime Crash
- **Priority:** HIGH
- **File:** `routes/admin/sources.py:59`
- **Issue:** `except UnsafeURLError as e:` is used but `UnsafeURLError` is never imported. This will raise `NameError` at runtime when `validate_url_safe()` raises for invalid URLs.
- **Fix:** Add `from utils.url import UnsafeURLError` to imports, or use `ValueError` (since `UnsafeURLError` is a subclass of `ValueError`).
- **Verification:** Read `routes/admin/sources.py` lines 1-11 (imports) and line 59 (usage).

### 1.2 `generate_daily_newsletters` Missing `@shared_task` Decorator
- **Priority:** HIGH
- **File:** `tasks/newsletter.py:476`
- **Issue:** `def generate_daily_newsletters(self, ...)` has no `@shared_task` decorator, so it's not registered as a Celery task. The function takes `self` suggesting it's in a Task class but it's standalone.
- **Fix:** Add `@shared_task` decorator to register it properly.
- **Verification:** Read `tasks/newsletter.py:470-490` to confirm decorator placement.

### 1.3 `validate_url_safe()` Exception Type Mismatch
- **Priority:** HIGH
- **File:** `utils/url.py:245-264`
- **Issue:** Function raises `ValueError` for empty URL, unsupported scheme, or missing hostname. `UnsafeURLError` is only raised for DNS/blocked-IP failures. But the docstring claims `UnsafeURLError` for all cases. Callers that only catch `UnsafeURLError` will miss `ValueError` exceptions.
- **Fix:** Either (a) make all invalid URL cases raise `UnsafeURLError`, or (b) fix the docstring to accurately document the two exception types.
- **Verification:** Read `utils/url.py:245-264` and check callers.

### 1.4 `ErrorHandlingMiddleware` Behavior Mismatch
- **Priority:** MEDIUM
- **File:** `services/subagent/middleware.py:64-80`
- **Issue:** Documentation says it catches errors and returns error dict. Actual implementation re-raises exceptions after logging.
- **Fix:** Update documentation to match actual behavior (re-raises after logging).
- **Verification:** Read `services/subagent/middleware.py:64-80`.

### 1.5 `ModelLimiter` Uses Wrong MetricsCollector Method
- **Priority:** HIGH
- **File:** `services/limiter.py:122-126`
- **Issue:** Calls `get_metrics().increment(...)` but the actual method on MetricsCollector is `counter_inc()`. This will raise `AttributeError` at runtime when slot leak detection triggers.
- **Fix:** Change `get_metrics().increment(...)` to `get_metrics().counter_inc(...)`.
- **Verification:** Read `services/limiter.py:122-126` and `services/metrics.py`.

---

## Phase 2: Documentation Corrections — Function Signatures

### 2.1 LLM Provider Functions

#### 2.1.1 `get_provider_for_role()` Return Type
- **File:** `services/llm/__init__.py`
- **Doc says:** Returns `BaseLLMProvider`
- **Actual:** Returns `Tuple[BaseLLMProvider, str, int, str]` — `(provider, model, max_tokens, provider_id)`
- **Fix:** Update all documentation to show 4-tuple return type.

#### 2.1.2 `get_provider_chain()` Return Type
- **File:** `services/llm/__init__.py`
- **Doc says:** Returns `list[str]`
- **Actual:** Returns a generator yielding `(provider, model, max_tokens, provider_id)` tuples
- **Fix:** Update documentation to show generator of tuples.

#### 2.1.3 `cost_tracker.py` Function Names
- **File:** `services/cost_tracker.py`
- **Doc says:** `record_usage()`, `get_usage_summary()`
- **Actual:** `_load_rates()` (private), `get_cost_summary()` (public), `_parse_metric_key()` (private)
- **Fix:** Update documentation to use correct function names.

#### 2.1.4 `_retry_with_backoff` Signature
- **File:** `services/llm/`
- **Doc says:** Named params `max_retries`, `base_delay`, `max_delay`
- **Actual:** Positional `model` arg with class constants for defaults
- **Fix:** Update documentation to match actual signature.

### 2.2 Search Provider Functions

#### 2.2.1 `SearxNGProvider` Class Name
- **File:** `services/search/searxng.py:59`
- **Doc says:** `SearxNGProvider`
- **Actual:** `SearXNGSearchProvider`
- **Fix:** Update all references to correct class name.

#### 2.2.2 `HybridSearchProvider` Base Class
- **File:** `services/search/hybrid.py`
- **Doc says:** Extends `BaseSearchProvider`
- **Actual:** Extends `SearchProvider`
- **Fix:** Update base class reference.

#### 2.2.3 `get_article_search_provider()` Return Type
- **File:** `services/search/`
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
- **Actual:** `_search_web`
- **Fix:** Update function name reference.

### 2.3 Adapter Functions

#### 2.3.1 `BaseSourceAdapter.__init__` Signature
- **File:** `adapters/base.py:41`
- **Doc says:** Constructor omitted
- **Actual:** Takes `source_config: SourceConfig`
- **Fix:** Add constructor documentation.

#### 2.3.2 `fetch()` Return Type
- **File:** `adapters/base.py:51`
- **Doc says:** `list[dict]`
- **Actual:** `list[Any]`
- **Fix:** Update return type.

#### 2.3.3 `parse_item()` Signature
- **File:** `adapters/base.py:54`
- **Doc says:** Param name `item`
- **Actual:** Param name `raw`, return type `Optional[RawItem]`
- **Fix:** Update parameter name and return type.

#### 2.3.4 `SSRFSafeRedirectHandler` Method Name
- **File:** `adapters/session.py:37`
- **Doc says:** `redirect_request`
- **Actual:** `__call__`
- **Fix:** Update method name in documentation.

### 2.4 Infrastructure Functions

#### 2.4.1 `get_redis()` Signature
- **File:** `extensions.py:68`
- **Doc says:** `get_redis(db: int = 0)`
- **Actual:** `get_redis()` — no parameters
- **Fix:** Remove `db` parameter from documentation.

#### 2.4.2 Redis DB Allocation Table
- **Doc says:** DB 0 = general cache, DB 1 = rate limiter, DB 2 = config cache
- **Actual:** DB 0 = Celery broker, DB 15 = Flask-Limiter storage, DB 1 = config cache (in `services/config_cache.py`)
- **Fix:** Update Redis DB allocation documentation.

#### 2.4.3 SQLite Pragma Function Name
- **File:** `app.py:164`
- **Doc says:** `_configure_sqlite_pragmas`
- **Actual:** `set_sqlite_pragma`
- **Fix:** Update function name reference.

#### 2.4.4 `HealthResult` Field Types
- **File:** `services/health.py:19-35`
- **Doc says:** `checks: dict[str, bool]`, `details: dict[str, str]`
- **Actual:** `checks: dict[str, Any]`, `version: dict[str, str] | None`
- **Fix:** Update field types.

#### 2.4.5 Health Check Function Name
- **File:** `services/health.py:121`
- **Doc says:** `check_health()`
- **Actual:** `run_health_checks(include_celery=True, detailed=False)`
- **Fix:** Update function name and signature.

#### 2.4.6 `ModelLimiter.acquire()` Signature
- **File:** `services/limiter.py:39-45`
- **Doc says:** `acquire(slots=1, timeout=30)`
- **Actual:** `acquire(provider_id: str, model: str, max_concurrent: int, timeout: int = 300)`
- **Fix:** Update signature documentation.

#### 2.4.7 `MetricsCollector` Method Names
- **File:** `services/metrics.py`
- **Doc says:** `increment()`, `gauge()`, `histogram()`, `export_prometheus()`
- **Actual:** `counter_inc()`, `gauge_set()`, `histogram_observe()`, `get_prometheus()`
- **Fix:** Update all method name references.

#### 2.4.8 `CircuitBreaker` Constructor and Methods
- **File:** `services/circuit_breaker.py`
- **Doc says:** `__init__(self, failure_threshold=5, ...)`, `is_open()` method
- **Actual:** Requires `name` param: `__init__(self, name: str, failure_threshold=5, ...)`, method is `can_execute()` not `is_open()`
- **Fix:** Update constructor and method name.

#### 2.4.9 `dispatch_webhook` Signature
- **File:** `services/webhooks.py:194-202`
- **Doc says:** `dispatch_webhook(event_type, payload)`
- **Actual:** 7 parameters: `(webhook_id, name, url, secret, event_type, event_data, idempotency_key=None)`
- **Fix:** Update signature documentation.

#### 2.4.10 `log_pipeline_event` / `log_article_event` Parameter Order
- **File:** `services/logging_utils.py`
- **Doc says:** `(event_type, article_id, stage, **kwargs)`
- **Actual:** `log_pipeline_event(stage, event, article_id=None, run_id=None, level="info", **extra)` and `log_article_event(article_id, event, level="info", **extra)`
- **Fix:** Update parameter order documentation.

#### 2.4.11 `ResponseCache` Default TTL
- **File:** `services/cache.py:49`
- **Doc says:** 300 seconds
- **Actual:** 120 seconds
- **Fix:** Update default TTL.

#### 2.4.12 `RoleConfig` Defaults
- **File:** `schemas/pipeline.py`
- **Doc says:** `provider: "ollama-local"`, `temperature: 0.5`
- **Actual:** `provider: Field(...)` (required, no default), `temperature: 0.0`
- **Fix:** Update defaults.

#### 2.4.13 `SubagentStageConfig` Defaults
- **File:** `schemas/pipeline.py:94,99`
- **Doc says:** `enabled: True`, `timeout_seconds: 60`
- **Actual:** `enabled: False`, `timeout_seconds: 120`
- **Fix:** Update defaults.

#### 2.4.14 `SubagentStageConfig` Missing Fields
- **File:** `schemas/pipeline.py:93-105`
- **Doc says:** 4 fields
- **Actual:** 12 fields including `provider`, `model`, `max_tokens`, `temperature`, `system_prompt`, `max_retries`, `retry_delay`, `task_template`, `tools`, `max_iterations`
- **Fix:** Document all fields.

#### 2.4.15 `NewsletterConfig` Field Names
- **File:** `schemas/pipeline.py:54`
- **Doc says:** `daily_send_time`
- **Actual:** `send_time: str = "08:00"`
- **Fix:** Update field name.

#### 2.4.16 `cached_config_with_mtime` Signature
- **File:** `services/config_cache.py`
- **Doc says:** 2-param: `(key, loader_fn)`
- **Actual:** 4-param: `(key, loader_fn, config_path, ttl)`
- **Fix:** Update signature.

#### 2.4.17 `traced_stage` Signature
- **Doc says:** `(stage_name)`
- **Actual:** `(stage, operation="execute")`
- **Fix:** Update signature.

### 2.5 Prompt Functions

#### 2.5.1 `get_system_prompt()` Signature
- **File:** `services/prompts.py`
- **Doc says:** `get_system_prompt(stage)`
- **Actual:** `get_system_prompt(role, yaml_prompt)` — yaml_prompt is required
- **Fix:** Update signature.

#### 2.5.2 `load_prompt_file()` Signature
- **File:** `services/prompts.py`
- **Doc says:** `load_prompt_file(filename) -> str`
- **Actual:** `load_prompt_file(name) -> str | None`
- **Fix:** Update return type to show Optional.

#### 2.5.3 `count_tokens()` Default
- **File:** `services/prompts.py`
- **Doc says:** `model="gpt-4"`
- **Actual:** `model=None`
- **Fix:** Update default value.

#### 2.5.4 Truncation Function Parameter Names
- **File:** `services/prompts.py`
- **Doc says:** `max_tokens`
- **Actual:** `max_chars`
- **Fix:** Update parameter names.

#### 2.5.5 `smart_truncate_context()` Return Type
- **File:** `services/prompts.py`
- **Doc says:** Returns `str`
- **Actual:** Returns `tuple[str, bool]`
- **Fix:** Update return type.

#### 2.5.6 `summarize_context()` Signature
- **File:** `services/prompts.py`
- **Doc says:** Simplified signature
- **Actual:** Has `text`, `llm_provider`, `temperature` params
- **Fix:** Update signature.

### 2.6 Task Functions

#### 2.6.1 Task Signatures Missing `run_id` Parameter
- **Files:** `tasks/select.py`, `tasks/research.py`, `tasks/write.py`, `tasks/edit.py`
- **Issue:** All stage task functions have `run_id` parameter that's not documented
- **Fix:** Add `run_id` to all task function signatures.

---

## Phase 3: Schema & Model Documentation Corrections

### 3.1 Article Model

#### 3.1.1 `created_at`/`updated_at` Usage
- **Status:** ALREADY CORRECT — Uses `datetime.now(timezone.utc)` not deprecated `datetime.utcnow`

#### 3.1.2 Missing Relationships
- **File:** `models/article.py:56-63`
- **Issue:** `tags`, `metrics`, `citations` relationships not documented
- **Fix:** Document all relationships: `citations` → Citation, `tags` → Tag (many-to-many), `metrics` → ArticleMetric (one-to-one)

#### 3.1.3 `source_id` Foreign Key
- **Status:** ALREADY CORRECT — Has `ondelete="CASCADE"`

### 3.2 Source Model

#### 3.2.1 `name` Field
- **Status:** ALREADY CORRECT — Has `nullable=False, index=True`

#### 3.2.2 `active` Index
- **Status:** ALREADY CORRECT — Documented in models.md

### 3.3 Subscriber Model

#### 3.3.1 Unique Constraint
- **File:** `models/newsletter.py`
- **Issue:** Unique constraint on `(email, newsletter_type)` undocumented
- **Fix:** Add constraint documentation.

### 3.4 AdminUser Model

#### 3.4.1 `username` Index
- **Status:** ALREADY CORRECT — `username` is indexed

### 3.5 Newsletter Model

#### 3.5.1 `newsletter_articles` Association Table
- **File:** `models/newsletter.py:8-13`
- **Issue:** Association table columns not fully documented
- **Actual columns:** `newsletter_id`, `article_id`, `position` (nullable=False, default=0), `created_at`
- **Fix:** Document all association table columns.

### 3.6 TopicNote Model
- **Issue:** Missing complete documentation
- **Fix:** Add TopicNote model with 5 fields and unique constraint.

### 3.7 TrendMemory Model

#### 3.7.1 Field Order
- **Issue:** Documentation has incorrect field order
- **Fix:** Correct field order to match actual model.

### 3.8 PipelineStatus Transitions
- **File:** `constants.py:52-64`
- **Issue:** Simplified diagram missing SELECTING, SELECTED, FAILED states
- **Actual transitions:**
  - PENDING → SELECTING, RESEARCHING, REVIEW
  - SELECTING → SELECTED, FAILED
  - SELECTED → RESEARCHING, FAILED
  - RESEARCHING → WRITING, FAILED
  - WRITING → EDITING, FAILED
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
- **File:** `schemas/pipeline.py`
- **Issue:** Documentation shows required fields, but all have `default_factory`
- **Fix:** Update to show optional fields with defaults.

#### 3.9.3 `SubagentConfig` `enabled` Field
- **File:** `schemas/pipeline.py:121-125`
- **Status:** ALREADY CORRECT — `enabled` is on `SubagentStageConfig`, not `SubagentConfig`

#### 3.9.4 Missing Schema Documentation
- **Issue:** Several schemas not documented
- **Fix:** Document: `ProviderDef`, `SubagentResponse`, `ResearchSynthesisResponse`, `EditContextualizationResponse`, `ToolCall`, `ToolResult`, `ToolCallingResponse`

---

## Phase 4: Route Documentation Corrections

### 4.1 Trigger-Crawl Route Path
- **File:** `routes/admin/pipelines.py:84`
- **Doc says:** `/admin/pipelines/trigger-crawl`
- **Actual:** `/admin/trigger-crawl`
- **Fix:** Update route path.

### 4.2 Semantic Search Endpoint Path
- **File:** `routes/admin/trend_memory.py:117`
- **Doc says:** `/api/trend-memory/semantic-search`
- **Actual:** `/admin/api/trend-memory/semantic-search`
- **Fix:** Update endpoint path.

### 4.3 Session Key for User Agent
- **File:** `routes/decorators.py:44`
- **Doc says:** `session['ua']`
- **Actual:** `session['user_agent']`
- **Fix:** Update key name.

### 4.4 Missing Admin Routes
- **Issue:** Several routes not documented
- **Fix:** Add documentation for: `/admin/sources/add`, `/admin/trend-memory` (CRUD), `/admin/api/trend-memory/semantic-search`

### 4.5 Rate Limiting Claim
- **Doc says:** "Admin routes have stricter rate limits"
- **Actual:** Only login/verify-2fa have explicit rate limits
- **Fix:** Correct documentation.

### 4.6 `api_tokens_bp` Registration
- **File:** `app.py:197`
- **Doc says:** Registered with `url_prefix="/api-tokens"`
- **Actual:** Registered without `url_prefix` — routes include full path
- **Fix:** Update registration documentation.

### 4.7 Logout Method
- **File:** `routes/admin/auth.py:188`
- **Status:** ALREADY CORRECT — Requires POST method only

---

## Phase 5: Adapter & Utils Documentation

### 5.1 Missing Adapter Methods
- **Issue:** Several methods not documented
- **Fix:** Document: `match_topics`, `get_adapter_class`, `_classify_topics`, `_get_match_text`, `_hash_ext_id`, `__enter__`, `__exit__`

### 5.2 `_classify_topics` Function
- **Issue:** Not documented
- **Fix:** Add documentation.

### 5.3 `get_adapter_class` Function
- **Issue:** Not documented
- **Fix:** Add documentation.

### 5.4 `services/url.py` Relationship with `utils/url.py`
- **Issue:** Duplication description oversimplified
- **Fix:** Clarify that `services/url.py` has config support while `utils/url.py` is for adapters.

### 5.5 `WebConfig.base_url` Field
- **Issue:** Not documented
- **Fix:** Add field documentation.

### 5.6 `validate_url_safe()` Exception Documentation
- **Status:** Must be fixed (see 1.3 above)

### 5.7 `UnsafeURLError` Inherits from `ValueError`
- **Status:** ALREADY CORRECT — Documented correctly

---

## Phase 6: Service Documentation

### 6.1 Config Cache Architecture
- **File:** `services/config_cache.py`
- **Issue:** Two-tier cache (L1 memory + L2 Redis) not documented
- **Fix:** Document L1 (in-memory, 500 entries max) + L2 (Redis) architecture.

### 6.2 Health Check Function
- **Status:** Must be fixed (see 2.4.5 above)

### 6.3 Provider Count
- **Doc says:** 16 providers
- **Actual:** 14 providers defined, 1 enabled (ollama-local)
- **Fix:** Update count.

### 6.4 `DeepSeek` NOT a Search Provider
- **Status:** ALREADY CORRECT — DeepSeek is only a regex pattern in trend_detector.py

### 6.5 Email Function Signatures
- **File:** `services/email.py:185-191`
- **Issue:** `send_verification_email` has additional `unsubscribe_url` and `site_name` params
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
- **File:** `config.py:64-66`
- **Status:** EXISTS — `PIPELINE_TIMEOUT_SECONDS = safe_int("PIPELINE_TIMEOUT_SECONDS", 3600)`
- **Issue:** Auto-dead-letter behavior not documented
- **Fix:** Document pipeline timeout (default 3600s) and auto-dead-letter behavior.

### 7.5 `VALID_PIPELINE_STATUSES` Incompleteness
- **File:** `constants.py`
- **Issue:** Excludes SELECTING, SELECTED, WRITTEN, FAILED states
- **Fix:** Document full set of valid statuses.

### 7.6 `MAX_CONSECUTIVE_FAILURES` Config
- **File:** `config.py:67`
- **Status:** EXISTS — `MAX_CONSECUTIVE_FAILURES = safe_int("MAX_CONSECUTIVE_FAILURES", 10)`
- **Issue:** Not documented
- **Fix:** Document default of 10, configurable via environment variable.

### 7.7 Newsletter Lock Mechanism
- **Issue:** Redis-based lock not documented
- **Fix:** Add documentation.

### 7.8 Shadow Quality Assessments
- **Issue:** `lightweight_quality_signals()` not documented
- **Fix:** Add documentation.

### 7.9 A/B Experiment Distribution
- **Issue:** 70/15/15 split not documented
- **Fix:** Add documentation.

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
| Item | Description | Files to Modify |
|------|-------------|-----------------|
| 1.1 | Fix missing `UnsafeURLError` import | `routes/admin/sources.py` |
| 1.2 | Add `@shared_task` decorator | `tasks/newsletter.py` |
| 1.3 | Fix `validate_url_safe()` exception docs | `utils/url.py` |
| 1.4 | Fix `ErrorHandlingMiddleware` docs | Documentation only |
| 1.5 | Fix `MetricsCollector` method call | `services/limiter.py` |

### Wave 2: Function Signature Corrections (Parallel — 3 Subagents)
**Subagent A — LLM & Search:**
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

**Subagent B — Adapters & Utils:**
| Item | Description |
|------|-------------|
| 2.3.1 | Fix `BaseSourceAdapter.__init__` signature |
| 2.3.2 | Fix `fetch()` return type |
| 2.3.3 | Fix `parse_item()` signature |
| 2.3.4 | Fix `SSRFSafeRedirectHandler` method name |
| 5.1-5.5 | Document missing adapter methods |

**Subagent C — Infrastructure:**
| Item | Description |
|------|-------------|
| 2.4.1-2.4.17 | Fix all infrastructure function signatures |

### Wave 3: Schema & Model Corrections (Parallel — 2 Subagents)
**Subagent D — Models:**
| Item | Description |
|------|-------------|
| 3.1-3.8 | Fix all model documentation issues |

**Subagent E — Schemas:**
| Item | Description |
|------|-------------|
| 3.9.1-3.9.4 | Fix all schema documentation issues |

### Wave 4: Route & Service Documentation (Parallel — 2 Subagents)
**Subagent F — Routes:**
| Item | Description |
|------|-------------|
| 4.1-4.7 | Fix all route documentation issues |

**Subagent G — Services:**
| Item | Description |
|------|-------------|
| 6.1-6.5 | Fix all service documentation issues |

### Wave 5: Pipeline & Low Priority (Parallel — 2 Subagents)
**Subagent H — Pipeline:**
| Item | Description |
|------|-------------|
| 7.1-7.10 | Fix all pipeline documentation issues |

**Subagent I — Low Priority:**
| Item | Description |
|------|-------------|
| 8.1-8.6 | Fix all low priority items |

---

## Verification Checklist

Before marking items complete, verify:
- [ ] `routes/admin/sources.py` imports `UnsafeURLError`
- [ ] `tasks/newsletter.py` has `@shared_task` on `generate_daily_newsletters`
- [ ] `validate_url_safe()` documentation matches actual exception behavior
- [ ] All function signatures match actual code
- [ ] All return types match actual implementations
- [ ] All default values match actual defaults
- [ ] All class names match actual class names
- [ ] All route paths match actual route definitions
- [ ] All field names match actual schema fields
- [ ] All method names match actual method names
- [ ] Provider count updated (14 total, 1 enabled)
- [ ] Redis DB allocation corrected (DB 0 = broker, DB 15 = limiter, DB 1 = config cache)

---

## Notes

- **APIAdapter/WebAdapter close() Design:** These adapters intentionally have no-op `close()` because they share the global session. RSSAdapter owns its own session and closes it properly. This is BY DESIGN.
- **utils/url.py and services/url.py Duplication:** Intentional for layering — `utils/url.py` is for adapters, `services/url.py` is for services with config support.
- **DeepSeek is NOT a search provider:** DeepSeek is only a regex pattern in `services/trend_detector.py` and `adapters/base.py`. Do NOT list it as a search provider.
- **SubagentConfig has no top-level `enabled` field:** The `enabled` field is on `SubagentStageConfig`, not `SubagentConfig`.
- **Task name is `retry_stuck`:** The Celery task defined at `tasks/retry.py:78` is named `retry_stuck`. The beat schedule key may be different (`retry-stuck-articles`).
- **Config cache is two-tier:** L1 (in-memory, 500 entries) + L2 (Redis, DB 1).
- **Limiter uses Redis DB 15:** Not DB 0 or DB 2 as some docs claim.

---

## Implementation Order Recommendation

1. **First (Wave 1):** Fix critical bugs — these affect runtime correctness
2. **Second (Wave 2):** Fix function signatures — these affect developer understanding
3. **Third (Wave 3):** Fix schema and model docs — these affect data model understanding
4. **Fourth (Wave 4):** Fix route and service docs — these affect API understanding
5. **Fifth (Wave 5):** Fix pipeline and low priority — these affect advanced understanding

---

*Plan consolidated: 2026-05-28*
*Source files: architecture_review_consolidated.md, routes_review.md, infra_config_overview_review.md, pipeline_tasks_review.md, llm_search_subagent_review.md, adapter_utils_review.md, data_layer_review.md*
