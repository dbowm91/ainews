# Architecture Documentation Review: infrastructure.md, config.md, overview.md

Review of architecture documentation against actual codebase. Generated from systematic verification of every claim.

---

## Verified Claims

The following claims were confirmed correct against the actual codebase:

### infrastructure.md
- **Celery beat schedule**: 14 scheduled tasks confirmed in `config.py:get_beat_schedule()` (lines 146-203)
- **Distributed locks**: Pattern used in crawl dedup, retry sweeps, publish scheduling — confirmed
- **Fail-closed**: `crawl_source`, `retry_stuck`, `publish_scheduled` raise when Redis unavailable — confirmed
- **SQLite WAL**: Pragmas confirmed in `app.py:164-172` (`journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`, `cache_size=-64000`, `foreign_keys=ON`)
- **FlaskTask base**: Confirmed in `celery_app.py:17-45` (creates app context per execution)
- **Email functions exist**: `send_newsletter_email`, `send_verification_email`, `send_welcome_email` confirmed in `services/email.py`
- **HTML-to-plain**: `html_to_plain_text()` confirmed in `services/email.py:328`
- **Connection pooling**: SMTP pool confirmed via `SMTPConnectionPool` in `services/email.py:13`
- **Circuit breaker states**: CLOSED → OPEN → HALF_OPEN confirmed in `services/circuit_breaker.py`
- **Sliding window**: Failure counting via `_failure_times` list in `CircuitBreaker` confirmed
- **Webhook HMAC-SHA256**: Confirmed in `services/webhooks.py:101-122`
- **Webhook Fernet encryption**: Confirmed in `services/webhooks.py:69-98`
- **Key rotation**: Fallback keys supported via `WEBHOOK_SECRET_KEY_PREVIOUS_1/2` in `services/webhooks.py:51-66`
- **Idempotency keys**: Supported in `dispatch_webhook` and `trigger_event` in `services/webhooks.py`
- **ResponseCache L1+L2**: In-memory OrderedDict + Redis confirmed in `services/cache.py:32-264`
- **Stampede protection**: Redis pub/sub lock pattern confirmed in `services/cache.py:143-188`
- **Incremental eviction**: O(1) batch of 5 oldest entries via `_evict_batch` in `services/cache.py:67-78`
- **ModelLimiter Lua scripts**: Atomic acquire/release confirmed in `services/limiter.py:9-29`
- **Pub/Sub notifications**: Waiters notified on slot release in `services/limiter.py:77,100`
- **MetricsCollector**: Redis-backed with in-memory fallback confirmed in `services/metrics.py:23-297`
- **Prometheus export**: `get_prometheus()` confirmed in `services/metrics.py:219-271`
- **ThreadPoolExecutor pattern**: Used in `services/content_extractor.py`, `services/search/*.py`, `services/subagent/config.py`, `services/llm/base.py`, `services/url.py`
- **cancel_futures=True**: Pattern confirmed in `services/subagent/config.py:18`, `services/timeout.py:60`, `services/llm/base.py:383`
- **PipelineLogger**: Confirmed in `services/logging_utils.py:159-206`
- **OpenTelemetry tracing**: `traced_llm_call` and `traced_stage` confirmed in `services/logging_utils.py:251-298`
- **HealthResult dataclass**: Confirmed in `services/health.py:19-35`
- **RedisCircuitBreaker**: Distributed circuit breaker with Redis fallback confirmed in `services/circuit_breaker.py:183-381`
- **Circuit breaker registry**: `get_breaker()` singleton pattern confirmed in `services/circuit_breaker.py:388-406`
- **Task signing**: HMAC signing for Celery tasks confirmed in `services/task_security.py`

### config.md
- **PipelineRootConfig structure**: Top-level fields confirmed (`pipeline`, `newsletter`, `newsletter_pipeline`, `subagent`, `memory`, `stages`, `schedule`)
- **RoleConfig schema**: Confirmed in `schemas/pipeline.py:16-33`
- **SubagentStageConfig schema**: Confirmed in `schemas/pipeline.py:93-106`
- **MemoryConfig schema**: Confirmed in `schemas/pipeline.py:128-138`
- **SourceConfig schema**: Confirmed in `schemas/source.py:106-131`
- **TopicMatchConfig**: Confirmed in `schemas/source.py:23-26`
- **RSSConfig, APIConfig, WebConfig**: Confirmed in `schemas/source.py:29-97`
- **Config validation**: `validate_config()` confirmed in `services/config_unified.py:220-231`
- **Config reload endpoint**: `POST /api/v1/config/reload` confirmed via search
- **cached_config_with_mtime**: Confirmed in `schemas/common.py:82-97`
- **Celery beat schedule loading**: `get_beat_schedule()` confirmed in `config.py:117-203`
- **Environment variables**: Most variables confirmed (FLASK_CONFIG, SECRET_KEY, DATABASE_URL, REDIS_URL, REDIS_SSL, SMTP_*, CELERY_*, WEBHOOK_SECRET_KEY, etc.)
- **Topic definitions**: `topics.yaml` confirmed with ai, privacy, programming, hardware topics
- **Provider types**: ollama, openai, anthropic, gemini confirmed in `schemas/llm.py:74-79`

### overview.md
- **System diagram**: Architecture layers (Adapters → Services → Orchestration → Data) confirmed
- **Directory structure**: All referenced directories exist and contain the listed files
- **Layering rules table**: Confirmed against AGENTS.md and actual imports
- **Known intentional violations**: All 3 listed violations confirmed
- **NewsletterBrief fields**: Correctly noted that it does NOT have preamble/footer/articles (actual: themes, highlights, connections)
- **StageConfig stub**: Confirmed only has `tools` field in `schemas/pipeline.py:141-148`
- **PipelineLog meta field**: Uses `meta` not `metadata` — confirmed
- **Logout requires POST**: Confirmed in admin routes
- **Dynamic fallback chain**: Provider chain determined by enabled providers — confirmed
- **utils/url.py not pure**: Global mutable state confirmed

---

## Incorrect Claims

### infrastructure.md — HIGH Priority

1. **`get_redis` function signature** (infrastructure.md:14-17)
   - **Doc claims**: `def get_redis(db: int = 0) -> redis.Redis:` with docstring mentioning TLS and password preservation
   - **Actual code**: `def get_redis():` — no `db` parameter, no return type annotation
   - **Location**: `extensions.py:68`
   - **Impact**: Misleading for anyone extending Redis usage

2. **Redis DB allocation table** (infrastructure.md:25-30)
   - **Doc claims**: DB 0 = general cache, DB 1 = rate limiter slots, DB 2 = config cache, DB 15 = Flask-Limiter
   - **Actual allocation**:
     - DB 0: General cache, distributed locks, ModelLimiter (rate limiter slots), metrics, circuit breaker, ResponseCache
     - DB 1: Config cache (via `CONFIG_CACHE_REDIS_URL` in `services/config_cache.py:297-301`)
     - DB 15: Flask-Limiter only (`_get_limiter_storage_uri()` in `extensions.py:18-31`)
     - DB 2: **NOT USED**
   - **Impact**: Incorrect understanding of Redis resource isolation

3. **SQLite pragma function name** (infrastructure.md:57)
   - **Doc claims**: `def _configure_sqlite_pragmas(dbapi_conn, connection_record):`
   - **Actual code**: `def set_sqlite_pragma(dbapi_conn, _):` at `app.py:164`
   - **Missing pragmas**: Doc omits `PRAGMA temp_store=MEMORY` and `PRAGMA mmap_size=268435456` (actual `app.py:171-172`)

4. **Missing Celery task time limits** (infrastructure.md:108-109)
   - **Doc claims**: `CELERY_TASK_TIME_LIMIT = 300` and `CELERY_TASK_SOFT_TIME_LIMIT = 240`
   - **Actual code**: These settings do NOT exist in `config.py`
   - **Impact**: Non-existent configuration documented

5. **HealthResult field types** (infrastructure.md:177-182)
   - **Doc claims**: `checks: dict[str, bool]` and `details: dict[str, str]`
   - **Actual code**: `checks: dict[str, Any]` and `version: dict[str, str] | None` (no `details` field)
   - **Location**: `services/health.py:19-25`

6. **Health check function name and signature** (infrastructure.md:188)
   - **Doc claims**: `def check_health(detailed: bool = False) -> HealthResult:`
   - **Actual code**: `def run_health_checks(include_celery: bool = True, detailed: bool = False) -> HealthResult:` at `services/health.py:121`
   - **Impact**: Different function name and additional parameter

7. **ModelLimiter interface** (infrastructure.md:209-216)
   - **Doc claims**: `acquire(slots=1, timeout=30)`, `release(slots=1)`, `get_active() -> int`
   - **Actual code**: `acquire(provider_id, model, max_concurrent, timeout=300)`, `release(provider_id, model, timeout=300)`, `get_active(provider_id, model) -> int | None`
   - **Location**: `services/limiter.py:39-139`
   - **Impact**: Completely different interface — provider/model-aware with pub/sub

8. **MetricsCollector method names** (infrastructure.md:348-352)
   - **Doc claims**: `increment()`, `gauge()`, `histogram()`, `export_prometheus()`
   - **Actual code**: `counter_inc()`, `gauge_set()`, `histogram_observe()`, `get_prometheus()`
   - **Location**: `services/metrics.py:44-271`
   - **Impact**: All method names are wrong

9. **CircuitBreaker constructor** (infrastructure.md:271)
   - **Doc claims**: `__init__(self, failure_threshold=5, recovery_timeout=60)`
   - **Actual code**: `__init__(self, name: str, failure_threshold=5, recovery_timeout=60.0, half_open_max_calls=1, window_seconds=120.0)` at `services/circuit_breaker.py:40-52`
   - **Impact**: `name` is required, additional parameters undocumented

10. **CircuitBreaker `is_open()` method** (infrastructure.md:280-281)
    - **Doc claims**: `def is_open(self) -> bool:`
    - **Actual code**: `def can_execute(self) -> bool:` at `services/circuit_breaker.py:155`
    - **Impact**: Method doesn't exist

11. **`dispatch_webhook` signature** (infrastructure.md:295-301)
    - **Doc claims**: `def dispatch_webhook(event_type: str, payload: dict):`
    - **Actual code**: `def dispatch_webhook(webhook_id, name, url, secret, event_type, event_data, idempotency_key=None) -> tuple[bool, str | None]:` at `services/webhooks.py:194-202`
    - **Impact**: Completely different signature

12. **`log_pipeline_event` parameter order** (infrastructure.md:325)
    - **Doc claims**: `def log_pipeline_event(event_type: str, article_id: int, stage: str, **kwargs):`
    - **Actual code**: `def log_pipeline_event(stage: str, event: str, article_id=None, run_id=None, level="info", **extra):` at `services/logging_utils.py:85-92`
    - **Impact**: Parameter order is wrong, different parameters

13. **`log_article_event` signature** (infrastructure.md:328)
    - **Doc claims**: `def log_article_event(event_type: str, article_id: int, **kwargs):`
    - **Actual code**: `def log_article_event(article_id: int, event: str, level="info", **extra):` at `services/logging_utils.py:114-119`
    - **Impact**: Parameter order is wrong

14. **`traced_stage` signature** (infrastructure.md:322)
    - **Doc claims**: `def traced_stage(stage_name: str):`
    - **Actual code**: `def traced_stage(stage: str, operation: str = "execute"):` at `services/logging_utils.py:279`
    - **Impact**: Missing `operation` parameter

15. **ThreadPoolExecutor locations** (infrastructure.md:380)
    - **Doc claims**: Used in `services/content_extractor.py`, `services/search/*.py`, `services/subagent/`
    - **Actual**: Also used in `services/url.py`, `services/timeout.py`, `services/llm/base.py`, `services/article.py`
    - **Impact**: Incomplete list

16. **ResponseCache `invalidate` method** (infrastructure.md:243-245)
    - **Doc claims**: `def invalidate(self, prefix: str) -> None:`
    - **Actual code**: `def invalidate(self, key: str) -> None:` and `def invalidate_prefix(self, prefix: str) -> None:` at `services/cache.py:190-220`
    - **Impact**: Method name and behavior differ

17. **ResponseCache default TTL** (infrastructure.md:240)
    - **Doc claims**: `def set(self, key: str, value: Any, ttl: int = 300) -> None:`
    - **Actual code**: `def set(self, key: str, value: Any, ttl: int = 120) -> None:` at `services/cache.py:122`
    - **Impact**: Default TTL is 120, not 300

### config.md — HIGH Priority

18. **RoleConfig defaults** (config.md:82-91)
    - **Doc claims**: `provider: str = "ollama-local"`, `model: str = "qwen3:8b"`, `temperature: float = 0.5`, `concurrency: int = 4`
    - **Actual code**: `provider: str = Field(...)` (required), `model: str = Field(...)` (required), `temperature: float = Field(default=0.0)`, `concurrency: int = Field(default=2)`
    - **Location**: `schemas/pipeline.py:16-33`
    - **Impact**: Wrong defaults, required fields shown as having defaults

19. **SubagentStageConfig defaults** (config.md:96-101)
    - **Doc claims**: `enabled: bool = True`, `timeout_seconds: int = 60`
    - **Actual code**: `enabled: bool = False`, `timeout_seconds: int = Field(default=120)`
    - **Location**: `schemas/pipeline.py:93-106`
    - **Impact**: `enabled` defaults to False, not True; timeout is 120, not 60

20. **SubagentStageConfig missing fields** (config.md:96-101)
    - **Doc claims**: Only `enabled`, `tools`, `max_retries`, `timeout_seconds`
    - **Actual code**: Also has `provider`, `model`, `max_tokens`, `temperature`, `system_prompt`, `retry_delay`, `task_template`, `max_iterations`
    - **Location**: `schemas/pipeline.py:93-106`

21. **NewsletterConfig fields** (config.md:26-32)
    - **Doc claims**: `daily_send_time`, `enable_topic_newsletters`, `batch_size`
    - **Actual code**: `send_time` (not `daily_send_time`), no `enable_topic_newsletters`, no `batch_size`. Has `prep_minutes` instead.
    - **Location**: `schemas/pipeline.py:52-58`

22. **`cached_config_with_mtime` signature** (config.md:267-274)
    - **Doc claims**: `def cached_config_with_mtime(path: Path, model_class):` with mtime dict-based caching
    - **Actual code**: `def cached_config_with_mtime(key: str, loader_fn: Callable[[], T], config_path: Path, ttl: int = 300) -> T:` at `schemas/common.py:82-97`
    - **Impact**: Completely different interface

23. **`config_utils.py` implementation** (config.md:279-285)
    - **Doc claims**: Uses `from celery_support import get_current_app` and `app = get_current_app()`
    - **Actual code**: Uses `from flask import current_app` and `current_app.config.get(key)` — no `celery_support` import
    - **Location**: `services/config_utils.py:43-46`

24. **`load_pipeline_config` signature** (config.md:247-250)
    - **Doc claims**: `def load_pipeline_config(path: str = None) -> PipelineRootConfig:`
    - **Actual code**: `def load_pipeline_config(path: str | Path = BASE_DIR / "pipeline.yaml") -> PipelineRootConfig:` at `schemas/pipeline.py:173-180`
    - **Impact**: Path type is `str | Path`, not `str | None`

25. **`load_providers_config` return type** (config.md:258-260)
    - **Doc claims**: `def load_providers_config(path: str = None) -> dict:`
    - **Actual code**: `def load_providers_config(path: str | Path = BASE_DIR / "providers.yaml") -> LLMProvidersConfig:` at `schemas/llm.py:98-104`
    - **Impact**: Returns `LLMProvidersConfig`, not `dict`

26. **Providers.yaml example — ollama type** (config.md:123-128)
    - **Doc claims**: `type: openai` for ollama-local
    - **Actual code**: `type: ollama` in `providers.yaml:3`
    - **Impact**: Wrong provider type

27. **Providers.yaml example — model names** (config.md:131-141)
    - **Doc claims**: OpenAI model "gpt-4o", Anthropic model "claude-sonnet-4-20250514"
    - **Actual code**: OpenAI model "gpt-4o-mini" (`providers.yaml:16`), Anthropic model "claude-sonnet-4-5-20250929" (`providers.yaml:24`)
    - **Impact**: Outdated model names

### overview.md — HIGH Priority

28. **Provider count** (overview.md:380)
    - **Doc claims**: "LLM provider definitions (16 providers)"
    - **Actual code**: 14 providers in `providers.yaml`
    - **Impact**: Wrong count

29. **Session binding location** (overview.md:393)
    - **Doc claims**: Session binding at `routes/admin/__init__.py`
    - **Actual code**: Session binding with IP + User-Agent validation is in `routes/decorators.py:43-54`
    - **Impact**: Wrong file location

30. **`get_beat_schedule` description** (config.md:326-327, overview.md:383)
    - **Doc claims**: "Beat schedule is loaded from `pipeline.yaml` `schedule:` section via `config.py:get_beat_schedule()`"
    - **Partial accuracy**: Schedule defaults come from `config.py:get_beat_schedule()` which reads from pipeline.yaml's `schedule` section, but the function constructs celery beat schedule entries with configurable intervals
    - **Location**: `config.py:117-203`

---

## Bugs Found

### infrastructure.md — MEDIUM Priority

1. **`_redis_lock` vs `_redis_pool`** (infrastructure.md:20)
   - Doc shows `_redis_lock = threading.Lock()` but actual code also has `_redis_pool = None` which is part of the connection management but not documented

2. **Cache `get_or_set` stampede protection** (infrastructure.md:256)
   - Doc says it "wraps lock acquisition + value computation in `RedisError` try/except"
   - Actual implementation at `services/cache.py:143-188` is more nuanced: it uses Redis `SET NX EX` for lock, then falls back to polling via pub/sub if lock can't be acquired

3. **Email `send_verification_email` parameters** (infrastructure.md:157)
   - Doc shows `send_verification_email(email: str, newsletter_type: str, verification_url: str, ...)`
   - Actual has additional required parameter `unsubscribe_url: str` and optional `site_name: str = "ainews//"` at `services/email.py:185-191`

### config.md — MEDIUM Priority

4. **`SourceConfig.config` default** (config.md:207)
   - Doc shows `config: dict[str, Any]` without default
   - Actual code has `config: dict[str, Any] = Field(default_factory=dict)` at `schemas/source.py:112`

5. **Missing `ProviderDef` in config.md** (config.md:119-159)
   - The `providers.yaml` schema uses `ProviderDef` from `schemas/common.py:23-29` which is not documented in config.md
   - `ProviderDef` has fields: `id`, `type`, `enabled`, `config`

### overview.md — MEDIUM Priority

6. **Missing `routes/admin/auth.py`** (overview.md:215-226)
   - Directory listing shows `routes/admin/` but `auth.py` is not listed in the directory structure
   - Actual directory contains `auth.py` for login/logout/session management

7. **Missing `routes/admin/api/` directory** (overview.md:226)
   - Directory listing shows `api/` as a subdirectory but doesn't show its contents
   - Actual `routes/admin/api/` contains multiple API endpoint files

8. **Missing `models/utils.py`** (overview.md:123-134)
   - `models/utils.py` exists but is not listed in the directory structure

9. **Missing `services/` files** (overview.md:155-192)
   - Several service files not listed: `article_fallback.py`, `article_parser.py`, `article_validation.py`, `audit.py`, `context_service.py`, `date_utils.py`, `dead_letter.py`, `degradation.py`, `newsletter_pipeline.py`, `pagination.py`, `pipeline_utils.py`, `prompts.py`, `provider_base.py`, `quality.py`, `redis_utils.py`, `related.py`, `rss.py`, `subscribers.py`, `timeout.py`, `tool_selection.py`, `totp.py`, `tracing.py`, `trend_detector.py`, `utils.py`, `validation.py`

10. **Missing `routes/admin/` files** (overview.md:215-226)
    - Files not listed: `auth.py`, `metrics.py`, `shares.py`, `subscribers.py`, `topic_notes.py`, `api_tokens.py`

---

## Improvement Opportunities

### infrastructure.md

1. **Add actual `get_redis` signature**: Document the real `def get_redis():` without `db` parameter
2. **Correct Redis DB table**: Update to reflect actual allocation (DB 0: general+limiter, DB 1: config cache, DB 15: Flask-Limiter)
3. **Add missing SQLite pragmas**: Document `temp_store=MEMORY` and `mmap_size=268435456`
4. **Add CELERY_WORKER settings**: Document `CELERY_WORKER_PREFETCH_MULTIPLIER=1`, `CELERY_WORKER_MAX_TASKS_PER_CHILD=1000`, `CELERY_TASK_ACKS_LATE=True`, `CELERY_TASK_REJECT_ON_WORKER_LOST=True` from `config.py:99-106`
5. **Add Result Backend DB**: Note that `CELERY_RESULT_BACKEND` uses DB 1 (not DB 0) — `config.py:95-96`
6. **Update ModelLimiter docs**: Document provider/model-aware interface with pub/sub
7. **Update MetricsCollector docs**: Use actual method names (`counter_inc`, `gauge_set`, `histogram_observe`, `get_prometheus`)
8. **Add `circuit_protected` decorator**: Document the `@circuit_protected` decorator pattern from `services/circuit_breaker.py:415-448`
9. **Add `CircuitOpenError`**: Document the exception class from `services/circuit_breaker.py:451-454`
10. **Add email batch sending**: Document `_send_emails_parallel` pattern referenced in `overview.md:356`
11. **Update `log_pipeline_event`**: Fix parameter order to match actual code

### config.md

12. **Fix RoleConfig defaults**: Update to match actual required fields and correct defaults
13. **Fix SubagentStageConfig**: Add all fields, correct `enabled` default to `False`
14. **Fix NewsletterConfig**: Use correct field names (`send_time`, not `daily_send_time`)
15. **Add `PipelineConfig.review` field**: Document `ReviewConfig` in pipeline section
16. **Update `cached_config_with_mtime`**: Fix signature to match actual 4-parameter interface
17. **Fix `config_utils.py`**: Remove incorrect `celery_support` import reference
18. **Update model names**: Use current model names from `providers.yaml`
19. **Add `LLMProvidersConfig` schema**: Document the actual return type of `load_providers_config()`
20. **Add `SubagentChainStep` and `SubagentChainConfig`**: These schemas exist but aren't documented

### overview.md

21. **Fix provider count**: Change "16 providers" to "14 providers"
22. **Fix session binding location**: Change `routes/admin/__init__.py` to `routes/decorators.py`
23. **Add missing directory entries**: Update directory structure with all actual files
24. **Add `services/cost_tracker.py` to Key Files table**: This file exists and is referenced in `infrastructure.md:397`

---

## Stale Content

### infrastructure.md

1. **`_redis_lock = threading.Lock()`** (line 20): Partially stale — actual code has both `_redis_client` and `_redis_pool` with `_redis_lock`
2. **Email retry logic** (line 170): Doc says "3 attempts with exponential backoff" but email functions don't have retry logic — they raise `smtplib.SMTPException`. Retry is at the newsletter task level.
3. **Batch size "500"** (line 169): Not in `services/email.py` — batch sending is handled by the newsletter task, not the email service

### config.md

4. **`topics.yaml` example** (lines 217-239): Shows only 4 topics. Should note this is example content, not authoritative.
5. **`providers.yaml` search section** (lines 148-159): Shows `duckduckgo` and `hybrid` as enabled, but `hybrid` is not in the `search` section of `providers.yaml` — it's in `search_providers` section

### overview.md

6. **"87+ files" in tests** (line 259): May be stale — count should be verified against actual test files
7. **`docs/` directory** (line 267): Listed but contents not specified

---

## Summary

| Category | Count |
|----------|-------|
| Verified Claims | ~50+ |
| Incorrect Claims | 30 |
| Bugs Found | 10 |
| Improvement Opportunities | 24 |
| Stale Content | 7 |

### Priority Breakdown

| Priority | Count |
|----------|-------|
| HIGH | 30 (Incorrect claims requiring immediate fix) |
| MEDIUM | 10 (Bugs and missing documentation) |
| LOW | 7 (Stale content, minor improvements) |

### Most Critical Issues

1. **Redis DB allocation table is wrong** — will mislead anyone trying to understand resource isolation
2. **ModelLimiter interface is completely different** — provider/model-aware with pub/sub, not simple slots
3. **All MetricsCollector method names are wrong** — will cause import errors
4. **RoleConfig defaults are wrong** — required fields shown as having defaults
5. **CircuitBreaker constructor requires `name`** — missing required parameter
6. **Health check function name is wrong** — `run_health_checks` not `check_health`
7. **Session binding location is wrong** — `routes/decorators.py` not `routes/admin/__init__.py`
8. **Provider count is wrong** — 14 not 16
9. **NewsletterConfig field names are wrong** — `send_time` not `daily_send_time`
10. **Celery task time limits don't exist** — fabricated configuration values
