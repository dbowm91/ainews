# Architecture Documentation Review Plan

**Created:** 2026-05-31
**Status:** COMPLETE
**Purpose:** Systematic review of all architecture documents to verify claims against code, identify bugs and improvements, and prune stale content.

---

## Scope

Review all 15 architecture documents (excluding this file):

| Document | Module(s) | Output Plan |
|----------|-----------|-------------|
| `overview.md` | System-wide | `plans/review_overview.md` |
| `pipeline.md` | `tasks/`, `services/` | `plans/review_pipeline.md` |
| `services.md` | `services/` | `plans/review_services.md` |
| `utils.md` | `utils/` | `plans/review_utils.md` |
| `subagent.md` | `services/subagent/` | `plans/review_subagent.md` |
| `routes.md` | `routes/` | `plans/review_routes.md` |
| `schemas.md` | `schemas/` | `plans/review_schemas.md` |
| `models.md` | `models/` | `plans/review_models.md` |
| `search-providers.md` | `services/search/` | `plans/review_search_providers.md` |
| `adapters.md` | `adapters/` | `plans/review_adapters.md` |
| `tasks.md` | `tasks/` | `plans/review_tasks.md` |
| `infrastructure.md` | `extensions.py`, `services/` | `plans/review_infrastructure.md` |
| `config.md` | `config.py`, YAML configs | `plans/review_config.md` |
| `prompts.md` | `prompts/`, `services/prompts.py` | `plans/review_prompts.md` |
| `llm-providers.md` | `services/llm/` | `plans/review_llm_providers.md` |

---

## Review Methodology

For each document, the reviewing subagent MUST execute all four phases:

### Phase 1: Verify Claims Against Code

Confirm every factual claim in the architecture document matches the actual codebase:

- **File paths**: Every referenced file exists at the stated path
- **Class/function names**: Every referenced class, function, method, and constant exists with the stated name
- **Signatures**: Every function signature (parameters, types, defaults) matches the code
- **Field definitions**: Every model field, schema field, and config field matches name, type, default, and constraints
- **Relationships**: Every foreign key, association table, and backref is accurate
- **Constants**: Every constant name and value matches `constants.py` and other source files
- **Scheduled tasks**: Every beat task name, schedule, and task function path is correct
- **Enum values**: Every `PipelineStatus` value and valid transition matches `constants.py:VALID_TRANSITIONS`
- **Imports**: Every referenced import path is correct

For each claim, mark as:
- **VERIFIED**: Confirmed correct
- **INCORRECT**: Does not match code (provide file:line of actual code)
- **UNVERIFIABLE**: Cannot determine from available code (note why)

### Phase 2: Interrogate for Bugs and Improvements

Analyze the documented architecture for:

**Potential Bugs:**
- Race conditions in documented patterns (e.g., lock acquisition, shared state)
- Resource leaks (unclosed connections, unreleased locks, missing finally blocks)
- Missing error handling paths
- Incorrect assumptions about execution context (e.g., Flask app context in Celery tasks)
- Security gaps in documented patterns (e.g., missing SSRF checks, timing attacks)
- Incomplete cleanup paths (e.g., stale limiter slots, orphaned cache entries)

**Improvement Opportunities:**
- Performance: unnecessary LLM calls, missing caching, suboptimal query patterns
- Security: defense-in-depth gaps, missing input validation
- Maintainability: overly complex patterns, duplicated logic, unclear abstractions
- Testability: hard-to-test patterns, missing seam points
- Reliability: single points of failure, missing fallbacks
- Observability: missing metrics, insufficient logging, blind spots

**Layering Violations:**
- Check every import against the layering rules in `overview.md`
- Flag any unmarked layering violations (known intentional violations are documented in AGENTS.md)
- Verify TYPE_CHECKING imports are correctly used where noted

### Phase 3: Identify Stale Content

Detect documentation that is outdated or no longer accurate:

- **Dead references**: Documented files, classes, or functions that no longer exist
- **Behavioral drift**: Documented behavior that contradicts current implementation
- **Schema mismatches**: Documented fields, types, or defaults that don't match code
- **Removed features**: Documented features that were removed or replaced
- **Version drift**: References to outdated library versions or patterns
- **Superseded patterns**: Old approaches replaced by newer implementations
- **Contradictions**: Two architecture documents making conflicting claims about the same thing
- **Cross-reference failures**: Links between documents that point to wrong locations

### Phase 4: Write Improvement Plan

Write findings to `plans/review_{module}.md` with this structure:

```markdown
# Review: {Document Name}

**Reviewed:** {date}
**Source:** `architecture/{document}.md`
**Reviewer:** Subagent {N}
**Status:** COMPLETE

---

## Verified Claims

List all claims confirmed correct. Group by category (models, functions, etc.).
Only include items where code was actually checked and confirmed.

## Incorrect Claims

| Line(s) | Claim | Actual Code | Severity |
|---------|-------|-------------|----------|
| ... | ... | file.py:line -- actual value | HIGH/MEDIUM/LOW |

## Bugs Found

| # | Description | Location | Severity | Evidence |
|---|-------------|----------|----------|----------|
| 1 | ... | file.py:line | HIGH | ... |

Severity: HIGH = likely production impact, MEDIUM = correctness/reliability concern, LOW = edge case/minor

## Improvement Opportunities

| # | Description | Category | Priority |
|---|-------------|----------|----------|
| 1 | ... | performance/security/maintainability | P1/P2/P3 |

## Stale Content

| Line(s) | Content | Reason | Action |
|---------|---------|--------|--------|
| ... | ... | file no longer exists / behavior changed / etc. | remove / update / rewrite |

## Summary

- Verified: N claims
- Incorrect: N claims
- Bugs: N (HIGH: N, MEDIUM: N, LOW: N)
- Improvements: N
- Stale items: N
```

---

## Subagent Assignments

### Subagent 1: Data Layer
**Documents:** `models.md`, `schemas.md`
**Output:** `plans/review_models.md`, `plans/review_schemas.md`

**models.md Checklist:**
- [ ] All model classes exist in `models/` package (`Article`, `Source`, `Newsletter`, `Subscriber`, `PipelineRun`, `PipelineLog`, `ArticleVersion`, `TopicNote`, `TrendMemory`, `AdminUser`, `ApiToken`, `Webhook`, `WebhookEvent`, `Tag`, `SearchQuery`, `AuditLog`, `QualityReport`, `ShareConfig`, `ArticleMetric`)
- [ ] Article model: all 30+ fields verified (name, type, default, nullable, index)
- [ ] Article model: `pipeline_status` default and valid values
- [ ] Source model: field names match (`source_type` not `type`, `last_crawled` not `last_fetch_at`)
- [ ] TrendMemory model: `signal` (not `observation`), `embedding` as `db.Text` (not vector type)
- [ ] AdminUser model: `backup_codes` as JSON, no `ip_binding`/`user_agent_hash` fields
- [ ] Newsletter association tables: `newsletter_articles` and `newsletter_subscribers` exist with correct columns
- [ ] `article_tags` association table exists
- [ ] QualityReport model: all fields, composite indexes, relationships
- [ ] PipelineStatus enum values in `constants.py`
- [ ] VALID_TRANSITIONS map in `constants.py`
- [ ] Index definitions match actual model indexes
- [ ] Relationship definitions (backrefs, lazy loading, cascade)

**schemas.md Checklist:**
- [ ] All Pydantic models exist in `schemas/` package
- [ ] `PipelineRootConfig` structure matches `pipeline.yaml` actual structure
- [ ] `RoleConfig` fields and defaults (provider required, model required, temperature, concurrency, timeout)
- [ ] `SubagentConfig` has NO top-level `enabled` field (only on `SubagentStageConfig`)
- [ ] `StageConfig` is a stub (only `tools` field)
- [ ] `SubagentStageConfig` fields (max_iterations ge=1 le=20)
- [ ] `SourceConfig` validator logic (`validate_adapter_config`)
- [ ] `RSSConfig`, `APIConfig`, `WebConfig` fields
- [ ] `TopicMatchConfig` and `MatchMode`
- [ ] LLM response schemas: `SelectionResult`, `ResearchBrief`, `CondensedArticle`, `ExecutiveSummary`, `NewsletterBrief`
- [ ] `NewsletterBrief` does NOT have `preamble`, `footer`, or `articles` fields
- [ ] Task validation schemas: `SelectArticleTask`, `ProcessItemTask`, `GenerateNewsletterTask`, `SendEmailTask`
- [ ] `ProcessItemTask.validate_source_type` validator
- [ ] `ProviderDef` in `common.py`
- [ ] Intentional layer violation documented in `common.py`

### Subagent 2: Adapter & Utils Layer
**Documents:** `adapters.md`, `utils.md`
**Output:** `plans/review_adapters.md`, `plans/review_utils.md`

**adapters.md Checklist:**
- [ ] `BaseSourceAdapter` abstract methods: `fetch()`, `parse_item()`, `fetch_and_parse()`, `match_topics()`
- [ ] `@register_adapter` decorator and `SOURCE_ADAPTERS` registry
- [ ] `get_adapter_class()` function
- [ ] `_classify_topics()` module-level function
- [ ] `RSSAdapter`: feedparser usage, malformed feed fallback
- [ ] `APIAdapter`: `list_url`, `list_items_path`, `fields`, `pagination`, `filters` operations
- [ ] `APIAdapter`: auth header injection (Bearer token only, NOT API key headers)
- [ ] `APIAdapter`: `PaginationConfig` types (`next_link`, `query_param`, `none`)
- [ ] `WebAdapter`: CSS selector configuration, `base_url` with `urljoin()`
- [ ] `SSRFSafeRedirectHandler.__call__` signature: `(self, request, response, **kwargs)`
- [ ] Session ownership: RSS=own session, API/Web=shared global session
- [ ] `APIAdapter.close()` and `WebAdapter.close()` are no-ops
- [ ] `RSSAdapter.close()` closes its own session
- [ ] WebAdapter `request_delay` applies per-article, not per-page
- [ ] Error handling: adapters don't update `Source.consecutive_failures/successes`

**utils.md Checklist:**
- [ ] All 6 files exist: `url.py`, `text.py`, `datetime.py`, `hash.py`, `html.py`, `security.py`
- [ ] `validate_url_safe()` behavior: DNS resolution, `_dns_cache`, `_dns_executor`, `_TTLCache`
- [ ] `UnsafeURLError` inherits from `ValueError`
- [ ] `normalize_url()` strips 14 TRACKING_PARAMS
- [ ] `normalize_title()` fuzzy matching
- [ ] `clear_dns_cache()` function exists
- [ ] `esc_xml_text()`, `esc_xml_attr()` in `text.py`
- [ ] `escape_prompt_data()` recursive dict escaping
- [ ] `truncate()` word-boundary truncation (vs `BaseSourceAdapter._truncate()` simple slicing)
- [ ] `parse_date()` naive datetime UTC handling
- [ ] `format_date()` / `time_ago()` alias relationship
- [ ] `generate_token()` / `constant_time_compare()` in `security.py`
- [ ] `extract_text()` trafilatura fallback in `html.py`
- [ ] `__all__` exports in `url.py` (6 items)
- [ ] Empty `__init__.py` intentional design
- [ ] `services/url.py` duplication documented: re-exports from `utils/url.py`, own `validate_url_safe()` with config support
- [ ] `services/url.py` uses `get_config_with_default()` for `DNS_CACHE_TTL` and `DNS_CACHE_MAX`

### Subagent 3: LLM & Search Layer
**Documents:** `llm-providers.md`, `search-providers.md`, `subagent.md`
**Output:** `plans/review_llm_providers.md`, `plans/review_search_providers.md`, `plans/review_subagent.md`

**llm-providers.md Checklist:**
- [ ] `BaseLLMProvider` abstract methods: `chat()`, `chat_streaming()`, `chat_structured()`, `chat_with_tools()`, `_create_client()`, `_chat_with_schema()`, `_call_api_with_tools()`, `_extract_text_and_tool_calls()`, `_format_tool_result()`
- [ ] `ToolDefinition` dataclass: fields are `name`, `description`, `parameters`, `required`, `fn` -- NO `cached` field
- [ ] `LLMResponse` and `ToolCall` types
- [ ] Provider implementations: `OpenAIProvider`, `AnthropicProvider`, `GeminiProvider`, `OllamaProvider`
- [ ] `services/llm/__init__.py`: `get_provider_for_role()`, `get_provider_chain()`
- [ ] `get_provider_chain()` is dynamic (from `providers.yaml` config order, not hardcoded)
- [ ] Circuit breaker integration: `CircuitOpenError` imported from `services/circuit_breaker.py`
- [ ] Error classification in `services/llm/errors.py`: `AuthError`, `RateLimitError`, `ProviderServerError`, `ProviderTimeoutError`
- [ ] `DEFAULT_LLM_TIMEOUT_SECONDS = 120.0` in `constants.py`
- [ ] `record_provider_success()` accepts `stage` parameter
- [ ] Cost tracking via `services/cost_tracker.py`
- [ ] `_retry_with_backoff()` retry logic: retries RateLimitError, ProviderTimeoutError, ProviderServerError; does NOT retry AuthError
- [ ] `json_utils.py` JSON extraction helpers
- [ ] Provider count: 14 providers in `providers.yaml` (not 16 as some docs claim)

**search-providers.md Checklist:**
- [ ] All 7 files exist in `services/search/`
- [ ] DuckDuckGo is default/enabled, `duckduckgo_search` library
- [ ] Hybrid provider (FTS5 + vector) is enabled for article search
- [ ] Google disabled, requires `GOOGLE_API_KEY` and `GOOGLE_CSE_ID`
- [ ] SearxNG disabled, self-hosted
- [ ] `SearchResult` dataclass: `title`, `url`, `snippet`, `source`
- [ ] Provider registry in `services/search/__init__.py`
- [ ] `search_web()` and `get_search_provider()` functions
- [ ] `get_article_search_provider()` for internal search
- [ ] DeepSeek is NOT a search provider (only regex in `trend_detector.py`)
- [ ] `providers.yaml` uses `search_providers:` key (plural, not `search:`)
- [ ] `sqlite_fts.py` for internal FTS5 article search
- [ ] `session.py` shared crawl session for web scraping
- [ ] Integration with subagent tools (`web_search`, `search_articles`)

**subagent.md Checklist:**
- [ ] All 10 files exist in `services/subagent/`
- [ ] Tool registry: `_TOOL_REGISTRY` in `registry.py`
- [ ] 14 tools total (12 context + 2 search), NOT 9
- [ ] Tool list: `get_topic_note`, `context_notes`, `related_articles`, `get_trend_memory`, `get_article_by_id`, `search_articles`, `get_source_health`, `get_topic_gap_report`, `get_source_performance`, `get_quality_report`, `find_dedupe_candidates`, `estimate_stage_cost`, `web_search`, `get_search_provider`
- [ ] `run_subagent()` signature: `(task_type, stage, prompt_data, response_model, article_id=None)`
- [ ] `run_subagent_with_tools()` signature includes `tools` parameter
- [ ] `SubagentResponse` schema: `synthesis`, `used_fallback`, `fallback_stages`
- [ ] `ToolCall` and `ToolResult` schemas
- [ ] Chain system: `SubagentChainStep`, `SubagentChainConfig` in `schemas/pipeline.py`
- [ ] Chains use `provider.chat()` directly (no tool calling in chains)
- [ ] Middleware chain: `LoggingMiddleware` -> `TimingMiddleware` -> `ErrorHandlingMiddleware` (applied in reverse)
- [ ] `ErrorHandlingMiddleware` re-raises exceptions (does NOT return error dicts)
- [ ] `copy.deepcopy()` for tool definitions prevents middleware compounding
- [ ] `max_iterations` default: 5 (ge=1, le=20)
- [ ] Self-correction mechanism: retries on structured output validation failure
- [ ] Prompt templates in `prompt_templates.py`
- [ ] Conditions AST-based evaluation in `conditions.py`
- [ ] `_format_subagent_prompt()` in `utils.py`
- [ ] Config from `pipeline.yaml` under `subagent` section

### Subagent 4: Pipeline & Tasks Layer
**Documents:** `pipeline.md`, `tasks.md`, `prompts.md`
**Output:** `plans/review_pipeline.md`, `plans/review_tasks.md`, `plans/review_prompts.md`

**pipeline.md Checklist:**
- [ ] Pipeline status values match `constants.py:PipelineStatus`
- [ ] Valid transitions match `constants.py:VALID_TRANSITIONS`
- [ ] Stage descriptions (select, research, write, edit)
- [ ] Select stage: scoring 1-10, `min_score` threshold, low confidence -> review
- [ ] Research stage: web search + subagent, degenerate brief -> review
- [ ] Write stage: Smart Brevity format, validation (body < 500 chars, empty key_points, empty citations)
- [ ] Edit stage: subagent contextualization, tag assignment, quality report
- [ ] Finalize: `published_at`, `pipeline_status="done"`, webhooks, trend memory
- [ ] Newsletter generation: 3-stage LLM (reader -> writer -> editor)
- [ ] Newsletter lock: Redis-based, idempotency key, 10-minute TTL
- [ ] Scheduled tasks table: 14 tasks with correct names and schedules
- [ ] Pipeline timeout: `PIPELINE_TIMEOUT_SECONDS` default 3600
- [ ] `VALID_PIPELINE_STATUSES` frozen set (excludes transient `selecting`, `selected`, `written`)
- [ ] `MAX_CONSECUTIVE_FAILURES` default 10
- [ ] Shadow quality assessments: `lightweight_quality_signals()`
- [ ] A/B experiment distribution: 70% control, 15% variant_a, 15% variant_b
- [ ] Degradation behavior table per stage
- [ ] Retry limits: per-stage 3, total 10
- [ ] Selector `retry_max=20` (hardcoded in `tasks/select.py:202`)
- [ ] Circuit breaker states and transitions
- [ ] Fallback chain is dynamic
- [ ] `AuthError` handling: immediate failure, no retry/fallback

**tasks.md Checklist:**
- [ ] All task files exist in `tasks/`
- [ ] Task functions exist: `run_all_sources`, `aggregate_crawl_results`, `process_item`, `select_article`, `research_article`, `write_article`, `edit_article`, `generate_daily_newsletters`, `publish_scheduled_articles`, `retry_stuck`, `backfill_embeddings`, `dispatch_webhook_task`, `cleanup_inactive_subscribers`
- [ ] Cleanup tasks: `cleanup_old_pipeline_logs`, `cleanup_expired_verifications`, `cleanup_stale_limiter_slots`, `consolidate_trend_memory`, `recalculate_impact_scores`, `purge_trend_memory`, `cleanup_old_article_versions`
- [ ] `run_stage()` signature: `(stage, article_id, work_fn, task_self, run_id=None, skip_next="finalize", retry_countdown=30, retry_max=15)`
- [ ] `max_retries=CELERY_TASK_MAX_RETRIES` on pipeline tasks
- [ ] Quality gate conditions per stage
- [ ] Degradation path: `degrade_stage()` in `services/pipeline_degradation.py`
- [ ] `_degrade_and_advance` alias in `tasks/retry.py`
- [ ] Beat schedule matches `config.py:get_beat_schedule()`

**prompts.md Checklist:**
- [ ] 7 prompt template files exist in `prompts/`
- [ ] `get_system_prompt()` in `services/prompts.py`
- [ ] `load_prompt_file()` returns None if not found
- [ ] Override mechanism: YAML `system_prompt` takes priority over `.txt` file
- [ ] Context truncation: `count_tokens()`, `sliding_window_truncate()`, `importance_weighted_truncate()`, `smart_truncate_context()`, `summarize_context()`
- [ ] Prompt escaping: `esc_xml_text()`, `esc_xml_attr()` in `utils/text.py`
- [ ] `escape_prompt_data()` recursive dict escaping
- [ ] Subagent task templates in `services/subagent/prompt_templates.py`
- [ ] Template resolution order: YAML task_template -> fallback templates
- [ ] A/B experiment prompts in `pipeline.yaml` `experiments.prompt_variants`

### Subagent 5: Infrastructure & Config Layer
**Documents:** `infrastructure.md`, `config.md`, `overview.md`
**Output:** `plans/review_infrastructure.md`, `plans/review_config.md`, `plans/review_overview.md`

**infrastructure.md Checklist:**
- [ ] Redis DB allocation: 0=broker, 1=config cache, 15=limiter
- [ ] SQLite WAL pragmas in `app.py`: journal_mode=WAL, synchronous=NORMAL, busy_timeout=5000, cache_size=-64000, foreign_keys=ON, temp_store=MEMORY, mmap_size=268435456
- [ ] Celery task configuration: `FlaskTask` base, `CELERY_TIMEZONE = "UTC"`
- [ ] Email: `SMTPConnectionPool`, `send_newsletter_email()`, `send_verification_email()`, `send_welcome_email()`
- [ ] Health checks: `HealthResult` dataclass, `run_health_checks()` signature
- [ ] Rate limiter: `ModelLimiter` interface (`acquire(provider_id, model, max_concurrent)`, not `acquire(slots=1)`)
- [ ] ResponseCache: L1 in-memory LRU + L2 Redis, stampede protection
- [ ] ConfigCache: L1 memory + L2 Redis DB 1, mtime-based invalidation
- [ ] Circuit breaker: `CircuitBreaker(name, failure_threshold=5)`, `can_execute()` method
- [ ] Webhook dispatch: HMAC-SHA256, Fernet encryption, retry
- [ ] Metrics: `MetricsCollector` methods (`counter_inc`, `gauge_set`, `histogram_observe`)
- [ ] ThreadPoolExecutor pattern: bounded pools, `shutdown(wait=False, cancel_futures=True)`
- [ ] Structured logging: `log_pipeline_event()`, `log_article_event()`, `traced_llm_call()`
- [ ] OpenTelemetry tracing availability
- [ ] URL validation layering: `utils/url.py` for adapters, `services/url.py` for services

**config.md Checklist:**
- [ ] 5 config files: `pipeline.yaml`, `providers.yaml`, `sources.yaml`, `topics.yaml`, `config.py`
- [ ] `PipelineRootConfig` top-level keys match `pipeline.yaml` actual structure
- [ ] `RoleConfig` fields and defaults
- [ ] `SubagentStageConfig` fields
- [ ] `ReviewConfig` with `auto_publish_threshold`
- [ ] `MemoryConfig` fields
- [ ] `providers.yaml` structure: list-based with `providers:` key
- [ ] `search_providers:` section (plural)
- [ ] Environment variables table completeness
- [ ] Config loading functions: `load_pipeline_config()`, `load_sources()`, `load_providers_config()`
- [ ] Config caching: `cached_config_with_mtime()` in `schemas/common.py`
- [ ] Celery-safe config: `get_config_with_default()` in `services/config_utils.py`
- [ ] Beat schedule: `get_beat_schedule()` in `config.py`
- [ ] `validate_config()` in `services/config_unified.py`

**overview.md Checklist:**
- [ ] System diagram accuracy (layers, components)
- [ ] Directory structure matches actual codebase
- [ ] Layering rules table correct
- [ ] Data flow summaries accurate (ingestion, extraction, pipeline, newsletter)
- [ ] Security architecture table: all features and locations
- [ ] Resilience patterns table: all patterns and implementations
- [ ] External integrations: LLM providers count and statuses
- [ ] Search providers count and statuses
- [ ] Entry points table
- [ ] Celery Beat schedule table (14 tasks)
- [ ] Redis DB allocation table
- [ ] Deep-dive links all resolve to existing documents
- [ ] Known architecture notes accuracy
- [ ] Module index descriptions match actual modules

### Subagent 6: Routes Layer
**Documents:** `routes.md`
**Output:** `plans/review_routes.md`

**routes.md Checklist:**
- [ ] All route files exist in `routes/`
- [ ] Blueprint names: `public_bp`, `admin_bp`, `admin_api_bp`, `api_tokens_bp`
- [ ] URL prefixes: `/` (public), `/admin` (admin), `/api/v1` (admin API), no prefix (api_tokens)
- [ ] Admin routes table: all endpoints with correct HTTP methods
- [ ] `/admin/logout` is POST only (not GET)
- [ ] Admin API endpoints table: all endpoints with methods
- [ ] API token routes: `/api-tokens/`, `/api-tokens/<id>` (no url_prefix)
- [ ] Public routes: feeds, subscribe, links, health
- [ ] `@require_auth` decorator
- [ ] Session hijacking protection: IP + User-Agent binding
- [ ] CSRF protection: `@validate_csrf_json` for JSON endpoints
- [ ] Rate limiting on admin routes (10/min login, 60/min default)
- [ ] Template structure matches `templates/` directory
- [ ] Social sharing: client-side JavaScript, NOT server endpoint
- [ ] Newsletter endpoints: stats, preview
- [ ] Trend memory semantic search endpoint
- [ ] Alerting, source intelligence, topic gap, quality, replay API endpoints
- [ ] `api_tokens_bp` registered WITHOUT url_prefix in `app.py`

### Subagent 7: Services Layer
**Documents:** `services.md`
**Output:** `plans/review_services.md`

**services.md Checklist:**
- [ ] All service modules listed in file inventory exist
- [ ] `BaseLLMProvider` inherits from `BaseProvider` (from `services/provider_base.py`)
- [ ] `BaseProvider` provides `provider_id` and `config` fields
- [ ] `ModelLimiter` interface: `acquire(provider_id, model, max_concurrent)`, `release(provider_id, model)`, `get_active(provider_id, model)`
- [ ] `SMTPConnectionPool`: `__init__(pool_size=5)`, `get_connection()`, `return_connection()`, `close_all()`, `_is_healthy()`, `_compute_cfg_hash()`
- [ ] Global `_smtp_pool` singleton via `_get_smtp_pool()`
- [ ] `send_newsletter_email()`, `send_verification_email()`, `send_welcome_email()` signatures
- [ ] Trend memory: module-level functions (`propose_trend_memory()`, `get_memory_for_topics()`, `consolidate_all_topics()`, `purge_expired()`)
- [ ] `content_extractor.py`: trafilatura primary, readability fallback, raw HTML final fallback
- [ ] Search provider files match `services/search/` directory
- [ ] Known layering exceptions documented correctly
- [ ] `services/crawling.py` TYPE_CHECKING import from `adapters.base`
- [ ] `services/subagent/tools.py` direct imports from `models` and `extensions`
- [ ] `schemas/common.py` imports from `services.config_cache`
- [ ] `tasks/crawl.py` imports from `adapters.base`
- [ ] Circuit breaker: `get_breaker(name, failure_threshold=5)`, `circuit_protected` decorator
- [ ] `MetricsCollector` methods: `counter_inc()`, `gauge_set()`, `histogram_observe()`
- [ ] `run_health_checks()` -- NOT `check_health()`
- [ ] `PipelineLogger` and `log_pipeline_event()`, `log_article_event()` in `logging_utils.py`
- [ ] `ValidationError(ValueError)` in `article_validation.py`
- [ ] `validate_final_article()` function
- [ ] Cost tracker: `get_cost_summary()` reads from `MetricsCollector`

---

## Stale Content Pruning

After ALL subagent reviews complete:

### Phase A: Aggregate Findings

1. Read all `plans/review_*.md` files
2. Extract all **Stale Content** entries from each file
3. Cross-reference with `plans/plan.md` to avoid re-flagging resolved items
4. Build consolidated stale content list

### Phase B: Classify Stale Items

| Category | Action |
|----------|--------|
| **Dead reference** (file/class no longer exists) | Remove section or rewrite |
| **Behavioral drift** (implementation changed) | Update to match current code |
| **Schema mismatch** (field/type/default wrong) | Correct the documentation |
| **Removed feature** | Remove section entirely |
| **Contradiction** (conflicting docs) | Resolve and unify |
| **Version drift** | Update version references |

### Phase C: Apply Pruning

For each stale item:
1. Identify the specific architecture document and line range
2. Determine the correct current state from code
3. Rewrite the section to match current code (do NOT delete without replacement)
4. Verify the rewrite is accurate

### Phase D: Validate

1. Re-run subagent verification on pruned sections
2. Ensure no new contradictions introduced
3. Verify all cross-document links still resolve
4. Confirm AGENTS.md known issues are still accurately documented

---

## Execution Plan

### Step 1: Create Output Directory

```bash
mkdir -p plans
```

### Step 2: Launch 7 Subagents in Parallel

Each subagent reads its assigned architecture document(s), performs the 4-phase review, and writes output to `plans/review_{module}.md`.

**Subagent prompts must include:**
- The exact architecture document path(s) to review
- The specific checklist items to verify
- The output file path to write
- Instructions to work only in `/home/sugarwookie/projects/ainews`
- Instructions to NOT make direct code changes -- only write the improvement plan

### Step 3: Read All Subagent Outputs

After all 7 subagents complete, read all `plans/review_*.md` files.

### Step 4: Consolidate Findings

Write `plans/architecture_review_consolidated.md` with:
- Total claims verified/incorrect/Unverifiable
- Total bugs by severity
- Total improvements by priority
- Total stale items by action
- Cross-document contradictions
- Recommended pruning actions

### Step 5: Stale Content Pruning

Execute Phase A-D above on the architecture documents themselves.

### Step 6: Validate

Run `ruff check . --exclude .venv` to verify no syntax errors introduced.

### Step 7: Commit

Stage all changes and commit to `main`.

---

## Output Files

| Plan File | Subagent | Source Document(s) |
|-----------|----------|-------------------|
| `plans/review_adapters.md` | Subagent 2 | `adapters.md` |
| `plans/review_config.md` | Subagent 5 | `config.md` |
| `plans/review_infrastructure.md` | Subagent 5 | `infrastructure.md` |
| `plans/review_llm_providers.md` | Subagent 3 | `llm-providers.md` |
| `plans/review_models.md` | Subagent 1 | `models.md` |
| `plans/review_overview.md` | Subagent 5 | `overview.md` |
| `plans/review_pipeline.md` | Subagent 4 | `pipeline.md` |
| `plans/review_prompts.md` | Subagent 4 | `prompts.md` |
| `plans/review_routes.md` | Subagent 6 | `routes.md` |
| `plans/review_schemas.md` | Subagent 1 | `schemas.md` |
| `plans/review_search_providers.md` | Subagent 3 | `search-providers.md` |
| `plans/review_services.md` | Subagent 7 | `services.md` |
| `plans/review_subagent.md` | Subagent 3 | `subagent.md` |
| `plans/review_tasks.md` | Subagent 4 | `tasks.md` |
| `plans/review_utils.md` | Subagent 2 | `utils.md` |
| `plans/architecture_review_consolidated.md` | Orchestrator | All above |

---

## Constraints

- Work only in `/home/sugarwookie/projects/ainews` -- no external directories
- Do NOT specify direct code changes; this is a review plan only
- Improvement plans go into `plans/` directory
- All subagent outputs must be written before consolidation
- Stale content pruning must be validated against current code
- Commit only when all reviews and pruning are complete
- Architecture documents are the source of truth for this review (not AGENTS.md)
