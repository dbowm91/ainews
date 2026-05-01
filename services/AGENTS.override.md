# Services Layer Conventions

Contextual conventions for agents working in the `services/` directory.

## Naming Conventions

- Avoid naming local variables `redis` to prevent shadowing the module import; use `redis_client` or `r`.

## Caching

- **Subagent Context Caching:** `_get_topic_note` and `_get_related_articles` use `ResponseCache` with 120s TTL.
- **Cache Invalidation Pattern:** Use `cache.invalidate_prefix()` for wildcard invalidation. Apply after admin mutations (source create/enable/disable, article approve/reject, topic note CRUD, trend memory delete).
- **Redis-Backed Stats:** Cache hit/miss stats stored in Redis with in-memory fallback via `record_hit()`, `record_miss()`, `get_stats()` in `ResponseCache`.
- **ResponseCache Incremental Eviction:** `cache.py` uses O(1) incremental eviction via `_evict_batch(batch=5)` checking oldest 5 entries (FIFO via `OrderedDict`) on each `get()`/`set()` call. Memory tuple format: `(expires_at, access_time, raw)` (3-tuple).
- **Related Articles Caching:** `find_related_articles_cached(article, limit=5)` in `related.py` with 600s TTL using key `pub:related:{article_id}`. 30-day date prefilter, configurable candidate limit via `RELATED_CANDIDATE_LIMIT` env var (default 50).
- **Redis max_connections Config:** Redis connection pool sizes configurable via `REDIS_MAX_CONNECTIONS` env var. Defaults to 100 for general Redis client (`extensions.py`), 20 for config cache (`services/config_cache.py`).

## URL Fetching & SSRF

All outbound HTTP requests must validate URLs against private IP ranges via `url.py:validate_url_safe()`. Catch `UnsafeURLError` to handle blocked URLs gracefully.

## LLM Prompt Building

All externally-sourced content MUST be XML-delimited and escaped.
- Use `prompts.py:esc_xml_text` for content inside tags.
- Use `prompts.py:esc_xml_attr` for content in attributes.
- Use `subagent.py:_escape_prompt_data` for recursive escaping of prompt context.

## Circuit Breaker

Per-Stage Circuit Breaker: Circuit breakers are keyed by `provider:model:stage` to prevent one stage's failures from blocking other stages. Redis-backed via `RedisCircuitBreaker` in `circuit_breaker.py` with in-memory fallback.

## Logging & Tracing

- **Structured Logging:** Use `get_pipeline_logger(task_id)` for task correlation.
- **OpenTelemetry:** Tracing integrated via `logging_utils.py:traced_stage`. Configure via `OTEL_EXPORTER_OTLP_ENDPOINT` environment variable. Real `OTLPSpanExporter` used when endpoint is set.
- **OTel Tracing for Subagents:** `traced_llm_call` wraps LLM invocations in `subagent.py:run_subagent()` and `run_subagent_with_tools()`.

## Metrics

- **Redis-Backed Metrics:** `metrics.py` stores counters/gauges/histograms in Redis with in-memory fallback.
- **Pipeline Throughput Counters:** `pipeline_monitor.py` provides throughput tracking with `record_throughput(stage, count=1)` and `get_throughput_stats(stage, minutes=15)`. Returns `total_items` and `items_per_minute`.
- **Pipeline Failure Tracking:** `pipeline_failure.py` fires `article.failed` webhook on pipeline failure. `pipeline_monitor.py:record_stage_result()` records failure reason counters (rate_limit, timeout, server_error, circuit_open) in Redis.

## Newsletter

- **SMTP Connection Pool:** `SMTPConnectionPool` class in `email.py` with configurable pool size (default 5) and connection health checks.
- **Newsletter Idempotency:** `tasks/newsletter.py` uses Redis key `idempotency:newsletter:{date}` to prevent duplicate generation, 2-day TTL after success.

## Quality Assessment

- **Quality Assessment Infrastructure:** `quality.py` with `QualityScore` dataclass, `QualityAssessor` protocol, `LLMQualityAssessor`, and `lightweight_quality_signals()`. This is a fully implemented but currently auxiliary system (to be documented and integrated into the main pipeline).
- **Stage-Aware Tool Selection:** `tool_selection.py` with `ToolSelector` protocol and `StageAwareToolSelector`.

## Subagent System

- **Core Functions:** `run_subagent()`, `run_subagent_with_tools()`, `run_subagent_chain()` in `subagent.py` for pipeline-specific agentic tasks
- **Tool Registry:** `initialize_tool_registry()` registers built-in tools. Add new tools via `_build_context_tools()` or new `_build_*_tools()` functions, then register in `initialize_tool_registry()`
- **Prompt Templates:** Defined in `_SUBAGENT_TASK_TEMPLATES` (code) or `pipeline.yaml:subagent.<stage>.tools` (config). Resolved at call time via `_get_task_template()`
- **Condition Evaluation:** `run_subagent_chain()` uses AST-based parsing (not `eval()`) for conditional steps, blocking dunder attribute access
- **Exception Handling:** Tool functions catch specific exceptions (`SQLAlchemyError`, `KeyError`, `AttributeError`) before falling back to bare `Exception`.
- **ThreadPoolExecutor Pattern:** Blocking I/O uses ThreadPoolExecutor to avoid blocking Celery workers. Applied in `content_extractor.py`, `search/searxng.py`, `search/google.py`, `search/duckduckgo.py`, `subagent.py`. Module-level singleton executor with `submit()` + `future.result(timeout=N)`.
- **Retry Logic Refactor:** Retry logic with exponential backoff + jitter has been refactored into the `_execute_with_retry()` helper in `subagent.py` to eliminate triple duplication.
- **ModelLimiter Stampede Protection:** `ModelLimiter` uses a Redis pub/sub pattern for stampede protection, ensuring only one worker attempts to refresh model quotas/limits while others wait for the result.
- **Thread Cancellation Limitation:** `future.cancel()` only requests cancellation - it doesn't guarantee thread termination. For robust cancellation, consider `ProcessPoolExecutor` or `executor.shutdown(wait=False)` with SIGTERM handling.