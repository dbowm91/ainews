# Architecture Documentation Review Plan

**Created:** 2026-05-29
**Status:** PENDING
**Purpose:** Systematic review of all architecture documents (except this file) to verify claims in code, interrogate for bugs/improvements, and prune stale content.

---

## Scope

Review all 15 architecture documents (excluding `review_plan.md`):

| # | Document | Module(s) | Output File |
|---|----------|-----------|-------------|
| 1 | `adapters.md` | `adapters/` | `plans/review_adapters.md` |
| 2 | `config.md` | `config.py`, YAML files, `schemas/` | `plans/review_config.md` |
| 3 | `infrastructure.md` | Redis, SQLite, Celery, email, health, rate limiting, caching | `plans/review_infrastructure.md` |
| 4 | `llm-providers.md` | `services/llm/` | `plans/review_llm_providers.md` |
| 5 | `models.md` | `models/` | `plans/review_models.md` |
| 6 | `overview.md` | System-wide bird's-eye view | `plans/review_overview.md` |
| 7 | `pipeline.md` | Article pipeline stages, newsletter generation | `plans/review_pipeline.md` |
| 8 | `prompts.md` | `prompts/`, `services/prompts.py` | `plans/review_prompts.md` |
| 9 | `routes.md` | `routes/` (public, admin, API) | `plans/review_routes.md` |
| 10 | `schemas.md` | `schemas/` | `plans/review_schemas.md` |
| 11 | `search-providers.md` | `services/search/` | `plans/review_search_providers.md` |
| 12 | `services.md` | `services/` (business logic) | `plans/review_services.md` |
| 13 | `subagent.md` | `services/subagent/` | `plans/review_subagent.md` |
| 14 | `tasks.md` | `tasks/` | `plans/review_tasks.md` |
| 15 | `utils.md` | `utils/` | `plans/review_utils.md` |

---

## Review Methodology

Each subagent review must:

### 1. Verify Claims in Code
- For every file path referenced, confirm the file exists and contains the claimed code
- For every function/class signature, verify it matches the actual implementation
- For every field/model/constant, confirm it exists with the documented type and default
- For every relationship, verify the foreign key/association table exists
- For every scheduled task, confirm the task name, schedule, and beat schedule entry

### 2. Interrogate for Bugs and Improvements
- Identify potential bugs: race conditions, resource leaks, missing error handling, incorrect assumptions
- Identify improvement opportunities: performance, security, maintainability, testability
- Check for inconsistencies between documents (e.g., overview.md vs module-specific doc)
- Check for inconsistencies between documentation and AGENTS.md
- Flag any code patterns that violate the documented layering rules (unless marked as intentional)

### 3. Check for Stale Content
- Verify that all referenced files, classes, and functions still exist
- Check if any documented behaviors have been superseded by newer implementations
- Look for outdated version references, deprecated patterns, or removed features
- Cross-reference with `plans/plan.md` to see if previously identified issues were resolved or regressed

### 4. Write Improvement Plan
Each subagent must write its findings to `plans/review_{module_name}.md` with:
- **Verified Claims**: What was confirmed correct
- **Incorrect Claims**: What is wrong in the documentation (with file:line references to actual code)
- **Bugs Found**: Potential bugs discovered during review
- **Improvement Opportunities**: Suggested enhancements
- **Stale Content**: Items that should be pruned or updated
- **Priority**: HIGH / MEDIUM / LOW for each finding

---

## Subagent Review Assignments

### Subagent 1: Data Layer Review
**Documents:** `models.md`, `schemas.md`
**Output:** `plans/review_models.md` and `plans/review_schemas.md`

**Review checklist for `models.md`:**
- [ ] Verify every model class exists in `models/` package
- [ ] Verify every field name, type, and default value
- [ ] Verify every relationship (foreign keys, association tables)
- [ ] Verify every index name and column list
- [ ] Check Article model has 30+ fields as claimed
- [ ] Verify PipelineStatus enum values match `constants.py`
- [ ] Check TrendMemory field names (`signal` not `observation`, `embedding` as Text)
- [ ] Verify AdminUser 2FA fields exist (backup_codes as JSON)
- [ ] Check Source model field names (`source_type` not `type`, `last_crawled` not `last_fetch_at`)
- [ ] Look for missing models or fields not documented

**Review checklist for `schemas.md`:**
- [ ] Verify every Pydantic model class exists in `schemas/`
- [ ] Verify field names, types, validators, and defaults
- [ ] Check PipelineRootConfig structure matches `pipeline.yaml`
- [ ] Verify RoleConfig fields and defaults
- [ ] Check SubagentConfig has no `enabled` field (only SubagentStageConfig does)
- [ ] Verify SourceConfig validator logic
- [ ] Check all LLM response schemas (SelectionResult, ResearchBrief, CondensedArticle, etc.)
- [ ] Verify task validation schemas match actual task signatures
- [ ] Look for schemas in code not documented here

### Subagent 2: Adapter & Utils Review
**Documents:** `adapters.md`, `utils.md`
**Output:** `plans/review_adapters.md` and `plans/review_utils.md`

**Review checklist for `adapters.md`:**
- [ ] Verify BaseSourceAdapter abstract methods
- [ ] Verify @register_adapter decorator exists and works
- [ ] Check RSSAdapter implements fetch/parse_item correctly
- [ ] Check APIAdapter config fields match `schemas/source.py` (list_url, list_items_path, fields, etc.)
- [ ] Verify filter operations (equals, min, exists, contains) are implemented
- [ ] Check WebAdapter CSS selector configuration
- [ ] Verify SSRFSafeRedirectHandler signature and behavior
- [ ] Confirm session ownership table (RSS=own, API/Web=shared)
- [ ] Verify close() is no-op for APIAdapter and WebAdapter
- [ ] Check error handling patterns match claims
- [ ] Look for adapter features not documented

**Review checklist for `utils.md`:**
- [ ] Verify every function exists in `utils/`
- [ ] Check function signatures match actual code
- [ ] Verify `validate_url_safe()` behavior and DNS cache
- [ ] Check TRACKING_PARAMS set has 14 entries as claimed
- [ ] Verify `UnsafeURLError` inherits from `ValueError`
- [ ] Check `escape_prompt_data()` exists and works
- [ ] Look for utility functions in code not documented
- [ ] Verify the `services/url.py` duplication is intentional

### Subagent 3: LLM & Search Review
**Documents:** `llm-providers.md`, `search-providers.md`, `subagent.md`
**Output:** `plans/review_llm_providers.md`, `plans/review_search_providers.md`, and `plans/review_subagent.md`

**Review checklist for `llm-providers.md`:**
- [ ] Verify BaseLLMProvider abstract methods and signatures
- [ ] Check ToolDefinition dataclass fields (no `cached` field)
- [ ] Verify provider implementations exist (openai.py, anthropic.py, gemini.py, ollama.py)
- [ ] Check provider registry in `services/llm/__init__.py`
- [ ] Verify get_provider_for_role() and get_provider_chain() functions
- [ ] Check circuit breaker integration
- [ ] Verify error classification types in `services/llm/errors.py`
- [ ] Check DEFAULT_LLM_TIMEOUT_SECONDS constant exists
- [ ] Look for LLM features not documented

**Review checklist for `search-providers.md`:**
- [ ] Verify all search provider files exist in `services/search/`
- [ ] Check DuckDuckGo provider is default/enabled
- [ ] Verify Hybrid provider (FTS5 + vector) is enabled
- [ ] Confirm Google and SearxNG are disabled
- [ ] Check SearchResult dataclass fields
- [ ] Verify provider registry in `services/search/__init__.py`
- [ ] Confirm DeepSeek is NOT a search provider
- [ ] Look for search features not documented

**Review checklist for `subagent.md`:**
- [ ] Verify tool registry in `services/subagent/registry.py`
- [ ] Check all 9 built-in tools exist and are registered
- [ ] Verify runner.py functions (run_subagent, run_subagent_with_tools)
- [ ] Check chain.py implementation
- [ ] Verify middleware classes (Logging, Timing, ErrorHandling)
- [ ] Check middleware chain order (applied in reverse)
- [ ] Verify prompt_templates.py exists
- [ ] Check conditions.py AST-based evaluation
- [ ] Look for subagent features not documented

### Subagent 4: Pipeline & Tasks Review
**Documents:** `pipeline.md`, `tasks.md`, `prompts.md`
**Output:** `plans/review_pipeline.md`, `plans/review_tasks.md`, and `plans/review_prompts.md`

**Review checklist for `pipeline.md`:**
- [ ] Verify pipeline status values match `constants.py`
- [ ] Check status transition flow is accurate
- [ ] Verify stage thresholds and scoring behavior
- [ ] Check newsletter generation flow (3-stage LLM)
- [ ] Verify scheduled tasks table (14 tasks)
- [ ] Check degradation behavior table
- [ ] Verify retry limits (per-stage: 3, total: 10)
- [ ] Check selector retry_max=20 claim
- [ ] Verify circuit breaker claims
- [ ] Look for pipeline behaviors not documented

**Review checklist for `tasks.md`:**
- [ ] Verify every task function exists in `tasks/`
- [ ] Check task signatures match actual code
- [ ] Verify run_stage() signature and behavior
- [ ] Check quality gate conditions per stage
- [ ] Verify degradation path documentation
- [ ] Check beat schedule matches `config.py:get_beat_schedule()`
- [ ] Look for task features not documented

**Review checklist for `prompts.md`:**
- [ ] Verify all 7 prompt template files exist in `prompts/`
- [ ] Check get_system_prompt() and load_prompt_file() functions
- [ ] Verify override mechanism works
- [ ] Check context truncation functions exist
- [ ] Verify prompt escaping functions exist
- [ ] Look for prompt features not documented

### Subagent 5: Infrastructure & Config Review
**Documents:** `infrastructure.md`, `config.md`, `overview.md`
**Output:** `plans/review_infrastructure.md`, `plans/review_config.md`, and `plans/review_overview.md`

**Review checklist for `infrastructure.md`:**
- [ ] Verify Redis DB allocation (0, 1, 2, 15)
- [ ] Check SQLite WAL pragmas in `app.py`
- [ ] Verify Celery task configuration
- [ ] Check email delivery functions exist
- [ ] Verify health check implementation
- [ ] Check rate limiter (ModelLimiter) interface
- [ ] Verify ResponseCache (L1 + L2) implementation
- [ ] Check circuit breaker implementation
- [ ] Verify webhook dispatch security features
- [ ] Check metrics collector interface
- [ ] Verify ThreadPoolExecutor pattern usage
- [ ] Look for infrastructure features not documented

**Review checklist for `config.md`:**
- [ ] Verify PipelineRootConfig structure
- [ ] Check all YAML file purposes and schemas
- [ ] Verify environment variables table
- [ ] Check config loading and caching patterns
- [ ] Verify Celery beat schedule loading
- [ ] Look for config features not documented

**Review checklist for `overview.md`:**
- [ ] Verify system diagram accuracy
- [ ] Check directory structure matches actual codebase
- [ ] Verify layering rules table
- [ ] Check data flow summaries
- [ ] Verify security architecture table
- [ ] Check external integrations list
- [ ] Verify entry points table
- [ ] Cross-reference all deep-dive links
- [ ] Look for overview claims contradicted by module docs

### Subagent 6: Routes Review
**Documents:** `routes.md`
**Output:** `plans/review_routes.md`

**Review checklist for `routes.md`:**
- [ ] Verify all route files exist in `routes/`
- [ ] Check blueprint registration (public_bp, admin_bp, admin_api_bp)
- [ ] Verify URL prefixes (/admin, /api/v1)
- [ ] Check admin routes table (all endpoints listed)
- [ ] Verify API endpoints table (all endpoints listed)
- [ ] Check HTTP methods for each endpoint
- [ ] Verify authentication methods per blueprint
- [ ] Check template structure
- [ ] Verify session hijacking protection claims
- [ ] Check CSRF protection
- [ ] Verify rate limiting on admin routes
- [ ] Look for routes not documented

### Subagent 7: Services Review
**Documents:** `services.md`
**Output:** `plans/review_services.md`

**Review checklist for `services.md`:**
- [ ] Verify every service module exists in `services/`
- [ ] Check service function signatures match actual code
- [ ] Verify config_cache.py and config_unified.py patterns
- [ ] Check circuit_breaker.py interface (name param, can_execute(), get_breaker())
- [ ] Verify limiter.py ModelLimiter interface (provider/model-aware)
- [ ] Check cache.py ResponseCache implementation
- [ ] Verify metrics.py MetricsCollector method names (counter_inc, gauge_set, histogram_observe)
- [ ] Check health.py run_health_checks() function signature
- [ ] Verify logging_utils.py PipelineLogger and log functions
- [ ] Look for service features not documented

---

## Stale Content Pruning Protocol

After all subagent reviews complete, the orchestrator must:

1. **Aggregate findings** from all `plans/review_*.md` files
2. **Identify stale claims** that are confirmed incorrect or outdated
3. **Create a pruning list** of specific documentation sections to remove or rewrite
4. **Cross-reference** with `plans/plan.md` to avoid re-fixing already-resolved items
5. **Update architecture documents** to remove stale content
6. **Delete or archive** any architecture documents that are fully superseded

### Stale Content Indicators
- Documented file/class/function no longer exists in codebase
- Documented behavior contradicts current implementation
- Documented field/type/default doesn't match actual code
- Documented feature was removed or replaced
- Documented pattern contradicts AGENTS.md conventions

---

## Execution Plan

### Phase 1: Parallel Subagent Reviews (7 subagents)
Launch all 7 subagents in parallel. Each writes findings to `plans/review_{module}.md`.

### Phase 2: Consolidation
Read all review output files. Merge into a single consolidated findings document at `plans/architecture_review_consolidated.md`.

### Phase 3: Stale Content Pruning
Remove or rewrite stale sections from architecture documents based on verified findings.

### Phase 4: Verification
Run linting (`ruff check . --exclude .venv`) to ensure no syntax errors introduced.

### Phase 5: Commit
Commit all changes to `main` branch.

---

## Output File Naming

Each subagent writes to `plans/` at the repo root:
- `plans/review_adapters.md` (Subagent 2)
- `plans/review_config.md` (Subagent 5)
- `plans/review_infrastructure.md` (Subagent 5)
- `plans/review_llm_providers.md` (Subagent 3)
- `plans/review_models.md` (Subagent 1)
- `plans/review_overview.md` (Subagent 5)
- `plans/review_pipeline.md` (Subagent 4)
- `plans/review_prompts.md` (Subagent 4)
- `plans/review_routes.md` (Subagent 6)
- `plans/review_schemas.md` (Subagent 1)
- `plans/review_search_providers.md` (Subagent 3)
- `plans/review_services.md` (Subagent 7)
- `plans/review_subagent.md` (Subagent 3)
- `plans/review_tasks.md` (Subagent 4)
- `plans/review_utils.md` (Subagent 2)

After consolidation, a final `plans/architecture_review_consolidated.md` summarizes all findings.

---

## Constraints

- Work only in the current working directory (`/home/sugarwookie/projects/ainews`)
- Do not modify code files unless a bug is confirmed
- Documentation improvements go into architecture docs directly
- Improvement plans go into `plans/` directory
- All changes must pass `ruff check . --exclude .venv`
- Commit only when all reviews are complete
