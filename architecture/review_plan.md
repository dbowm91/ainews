# Architecture Documentation Review Plan

**Created:** 2026-05-29
**Status:** PHASE_3_IN_PROGRESS
**Purpose:** Systematic review of architecture documents to verify claims against code, identify bugs and improvements, and prune stale content.

**Phase 3 Work Items (from consolidated review):**
- HIGH: Fix config.md YAML structure errors (providers.yaml list-based, search_providers key)
- HIGH: Fix infrastructure.md CELERY_RESULT_BACKEND env var name
- MEDIUM: Fix tasks.md stale _degrade_and_advance reference
- MEDIUM: Fix services/url.py config documentation in utils.md
- MEDIUM: Add missing environment variables to config.md
- MEDIUM: Add missing schema documentation to schemas.md
- MEDIUM: Add missing endpoints to routes.md
- MEDIUM: Document services/url.py vs utils/url.py relationship
- LOW: Various clarifications across documents

---

## Scope

Review all 14 architecture documents (excluding this file):

| Document | Module | Output Plan |
|----------|--------|-------------|
| `adapters.md` | `adapters/` | `plans/review_adapters.md` |
| `config.md` | `config.py`, YAML configs | `plans/review_config.md` |
| `infrastructure.md` | Redis, SQLite, Celery, email, health | `plans/review_infrastructure.md` |
| `llm-providers.md` | `services/llm/` | `plans/review_llm_providers.md` |
| `models.md` | `models/` | `plans/review_models.md` |
| `overview.md` | System-wide | `plans/review_overview.md` |
| `pipeline.md` | `tasks/pipeline.py`, newsletter | `plans/review_pipeline.md` |
| `prompts.md` | `prompts/`, `services/prompts.py` | `plans/review_prompts.md` |
| `routes.md` | `routes/` | `plans/review_routes.md` |
| `schemas.md` | `schemas/` | `plans/review_schemas.md` |
| `search-providers.md` | `services/search/` | `plans/review_search_providers.md` |
| `services.md` | `services/` | `plans/review_services.md` |
| `subagent.md` | `services/subagent/` | `plans/review_subagent.md` |
| `tasks.md` | `tasks/` | `plans/review_tasks.md` |
| `utils.md` | `utils/` | `plans/review_utils.md` |

---

## Review Methodology

For each document, the reviewing subagent must:

### Phase 1: Verify Claims Against Code
- Confirm every file path, class, function, and field referenced in the document exists in the codebase
- Verify every signature, default value, and type matches the documented claim
- Check every relationship (foreign keys, associations, enums) is accurate
- Validate every scheduled task name, schedule, and beat entry

### Phase 2: Interrogate for Bugs and Improvements
- Identify potential bugs: race conditions, resource leaks, missing error handling, incorrect assumptions
- Identify improvement opportunities: performance, security, maintainability, testability
- Flag violations of documented layering rules (unless marked as intentional)
- Note discrepancies between architecture docs and AGENTS.md

### Phase 3: Identify Stale Content
- Documented items that no longer exist in code
- Behaviors superseded by newer implementations
- Outdated version references or deprecated patterns
- Cross-reference with `plans/plan.md` to avoid re-flagging resolved issues

### Phase 4: Write Improvement Plan
Write findings to `plans/review_{module}.md` with sections:
- **Verified Claims**: Confirmed correct items
- **Incorrect Claims**: Wrong documentation (file:line references)
- **Bugs Found**: Potential bugs with severity (HIGH/MEDIUM/LOW)
- **Improvement Opportunities**: Suggested enhancements
- **Stale Content**: Items to prune or update
- **Priority**: For each finding

---

## Subagent Assignments

### Subagent 1: Data Layer
**Documents:** `models.md`, `schemas.md`
**Output:** `plans/review_models.md`, `plans/review_schemas.md`

Checklist for `models.md`:
- [ ] All model classes exist in `models/` package
- [ ] All field names, types, defaults match code
- [ ] All relationships (FKs, association tables) verified
- [ ] Article model field count (30+)
- [ ] PipelineStatus enum matches `constants.py`
- [ ] TrendMemory field names (`signal`, `embedding` as Text)
- [ ] AdminUser 2FA backup_codes as JSON
- [ ] Source model field names (`source_type`, `last_crawled`)
- [ ] Newsletter association tables exist

Checklist for `schemas.md`:
- [ ] All Pydantic models exist in `schemas/`
- [ ] Field names, types, validators match code
- [ ] PipelineRootConfig matches `pipeline.yaml`
- [ ] RoleConfig fields and defaults
- [ ] SubagentConfig has NO top-level `enabled` (only SubagentStageConfig)
- [ ] SourceConfig validator logic
- [ ] LLM response schemas (SelectionResult, ResearchBrief, etc.)
- [ ] Task validation schemas match task signatures

### Subagent 2: Adapter & Utils Layer
**Documents:** `adapters.md`, `utils.md`
**Output:** `plans/review_adapters.md`, `plans/review_utils.md`

Checklist for `adapters.md`:
- [ ] BaseSourceAdapter abstract methods
- [ ] @register_adapter decorator
- [ ] RSSAdapter fetch/parse_item
- [ ] APIAdapter config fields (list_url, list_items_path, fields, pagination)
- [ ] Filter operations (equals, min, exists, contains)
- [ ] WebAdapter CSS selector configuration
- [ ] SSRFSafeRedirectHandler signature
- [ ] Session ownership (RSS=own, API/Web=shared)
- [ ] APIAdapter/WebAdapter close() is no-op

Checklist for `utils.md`:
- [ ] All functions exist in `utils/`
- [ ] Function signatures match code
- [ ] validate_url_safe() behavior and DNS cache
- [ ] TRACKING_PARAMS set size (14 entries)
- [ ] UnsafeURLError inherits from ValueError
- [ ] escape_prompt_data() exists
- [ ] services/url.py duplication documented as intentional

### Subagent 3: LLM & Search Layer
**Documents:** `llm-providers.md`, `search-providers.md`, `subagent.md`
**Output:** `plans/review_llm_providers.md`, `plans/review_search_providers.md`, `plans/review_subagent.md`

Checklist for `llm-providers.md`:
- [ ] BaseLLMProvider abstract methods and signatures
- [ ] ToolDefinition dataclass fields (NO `cached` field)
- [ ] Provider implementations (openai, anthropic, gemini, ollama)
- [ ] Provider registry in `services/llm/__init__.py`
- [ ] get_provider_for_role() and get_provider_chain()
- [ ] Circuit breaker integration
- [ ] Error classification in `services/llm/errors.py`
- [ ] DEFAULT_LLM_TIMEOUT_SECONDS constant

Checklist for `search-providers.md`:
- [ ] All search provider files in `services/search/`
- [ ] DuckDuckGo is default/enabled
- [ ] Hybrid provider (FTS5 + vector) is enabled
- [ ] Google and SearxNG are disabled
- [ ] SearchResult dataclass fields
- [ ] Provider registry
- [ ] DeepSeek is NOT a search provider (only a regex pattern)

Checklist for `subagent.md`:
- [ ] Tool registry in `services/subagent/registry.py`
- [ ] 14 tools (12 context + 2 search), NOT 9
- [ ] Runner functions (run_subagent, run_subagent_with_tools)
- [ ] Chain implementation
- [ ] Middleware classes (Logging, Timing, ErrorHandling)
- [ ] Middleware chain order (applied in reverse)
- [ ] Prompt templates
- [ ] Conditions AST-based evaluation

### Subagent 4: Pipeline & Tasks Layer
**Documents:** `pipeline.md`, `tasks.md`, `prompts.md`
**Output:** `plans/review_pipeline.md`, `plans/review_tasks.md`, `plans/review_prompts.md`

Checklist for `pipeline.md`:
- [ ] Pipeline status values match `constants.py`
- [ ] Status transition flow
- [ ] Stage thresholds and scoring
- [ ] Newsletter generation (3-stage LLM)
- [ ] Scheduled tasks table (14 tasks)
- [ ] Degradation behavior
- [ ] Retry limits (per-stage: 3, total: 10)
- [ ] Selector retry_max=20
- [ ] Circuit breaker claims

Checklist for `tasks.md`:
- [ ] All task functions exist in `tasks/`
- [ ] Task signatures match code
- [ ] run_stage() signature and behavior
- [ ] Quality gate conditions per stage
- [ ] Degradation path
- [ ] Beat schedule matches `config.py:get_beat_schedule()`

Checklist for `prompts.md`:
- [ ] 7 prompt template files in `prompts/`
- [ ] get_system_prompt() and load_prompt_file()
- [ ] Override mechanism
- [ ] Context truncation functions
- [ ] Prompt escaping functions (esc_xml_text, esc_xml_attr)

### Subagent 5: Infrastructure & Config Layer
**Documents:** `infrastructure.md`, `config.md`, `overview.md`
**Output:** `plans/review_infrastructure.md`, `plans/review_config.md`, `plans/review_overview.md`

Checklist for `infrastructure.md`:
- [ ] Redis DB allocation (0=broker, 1=config cache, 15=limiter)
- [ ] SQLite WAL pragmas in `app.py`
- [ ] Celery task configuration
- [ ] Email delivery functions
- [ ] Health check implementation
- [ ] Rate limiter (ModelLimiter) interface
- [ ] ResponseCache (L1 + L2) implementation
- [ ] Circuit breaker implementation
- [ ] Webhook dispatch security
- [ ] Metrics collector interface
- [ ] ThreadPoolExecutor pattern

Checklist for `config.md`:
- [ ] PipelineRootConfig structure
- [ ] YAML file purposes and schemas
- [ ] Environment variables table
- [ ] Config loading and caching
- [ ] Celery beat schedule loading

Checklist for `overview.md`:
- [ ] System diagram accuracy
- [ ] Directory structure matches codebase
- [ ] Layering rules table
- [ ] Data flow summaries
- [ ] Security architecture
- [ ] External integrations list
- [ ] Entry points table
- [ ] Cross-reference deep-dive links

### Subagent 6: Routes Layer
**Documents:** `routes.md`
**Output:** `plans/review_routes.md`

Checklist:
- [ ] All route files exist in `routes/`
- [ ] Blueprint registration (public_bp, admin_bp, admin_api_bp)
- [ ] URL prefixes (/admin, /api/v1)
- [ ] Admin routes table (all endpoints)
- [ ] API endpoints table (all endpoints)
- [ ] HTTP methods per endpoint
- [ ] Authentication methods
- [ ] Template structure
- [ ] Session hijacking protection
- [ ] CSRF protection
- [ ] Rate limiting on admin routes

### Subagent 7: Services Layer
**Documents:** `services.md`
**Output:** `plans/review_services.md`

Checklist:
- [ ] All service modules exist in `services/`
- [ ] Service function signatures match code
- [ ] config_cache.py and config_unified.py patterns
- [ ] circuit_breaker.py interface (name param, can_execute(), get_breaker())
- [ ] limiter.py ModelLimiter interface (provider/model-aware)
- [ ] cache.py ResponseCache implementation
- [ ] metrics.py MetricsCollector methods (counter_inc, gauge_set, histogram_observe)
- [ ] health.py run_health_checks() signature
- [ ] logging_utils.py PipelineLogger and log functions
- [ ] article_validation.py ValidationError

---

## Stale Content Pruning

After all subagent reviews complete:

1. **Aggregate** findings from all `plans/review_*.md` files
2. **Identify** stale claims confirmed incorrect or outdated
3. **Create** pruning list of specific sections to remove or rewrite
4. **Cross-reference** with `plans/plan.md` to avoid re-flagging resolved items
5. **Update** architecture documents to remove stale content
6. **Delete** any architecture documents fully superseded

### Stale Content Indicators
- Documented file/class/function no longer exists
- Documented behavior contradicts implementation
- Documented field/type/default doesn't match code
- Documented feature was removed or replaced
- Documented pattern contradicts AGENTS.md

---

## Execution

~~**Phase 1:** Launch 7 subagents in parallel, each reviewing their assigned documents and writing to `plans/review_*.md`~~ ✅ DONE

~~**Phase 2:** Read all `plans/review_*.md` outputs. Consolidate into `plans/architecture_review_consolidated.md`~~ ✅ DONE

~~**Phase 3:** Apply stale content pruning to architecture documents~~ ✅ DONE

**Phase 4:** Run `ruff check . --exclude .venv` to verify no syntax errors (SKIPPED - ruff not available)

**Phase 5:** Commit all changes to `main`

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

- Work only in `/home/sugarwookie/projects/ainews`
- Do NOT specify direct code changes; this is a review plan only
- Improvement plans go into `plans/` directory
- All linting must pass before commit
- Commit only when all reviews and pruning complete