# Architecture Review Plan

This document outlines the review plan for architecture documentation modules.

## Modules to Review

| Module | Document | Assigned Subagent | Output Plan File |
|--------|----------|-------------------|------------------|
| Models | `models.md` | `models-reviewer` | `plans/models_review.md` |
| Adapters | `adapters.md` | `adapters-reviewer` | `plans/adapters_review.md` |
| Services | `services.md` | `services-reviewer` | `plans/services_review.md` |
| Schemas | `schemas.md` | `schemas-reviewer` | `plans/schemas_review.md` |
| Utils | `utils.md` | `utils-reviewer` | `plans/utils_review.md` |
| Pipeline | `pipeline.md` | `pipeline-reviewer` | `plans/pipeline_review.md` |
| Tasks | `tasks.md` | `tasks-reviewer` | `plans/tasks_review.md` |
| Routes | `routes.md` | `routes-reviewer` | `plans/routes_review.md` |
| Subagent | `subagent.md` | `subagent-reviewer` | `plans/subagent_review.md` |

## Review Methodology

For each module, subagents will:

1. **Read Architecture Document**: Read the module's `.md` file in `architecture/`
2. **Verify Claims Against Code**: Cross-reference claims with actual implementation in the codebase
3. **Identify Improvements**: Document specific improvements (API consistency, error handling, performance, security)
4. **Find Bugs**: Document bugs, edge cases, race conditions, or layer violations
5. **Write Improvement Plan**: Output structured findings to `plans/<module>_review.md`

## Subagent Instructions

Each subagent should produce a plan with these sections:

```markdown
# <Module> Review Plan

## Verified Claims
- List claims from architecture doc that are confirmed by code

## Discrepancies
- List claims that don't match implementation

## Improvement Recommendations
1. [Priority] Description of improvement
2. [Priority] Description of improvement

## Bugs Found
1. Bug description with location
2. Bug description with location

## Layer Violations
- Any clean layering violations (adapters importing services, etc.)
```

## Module Review Details

### 1. Models (`models.md`)
- **Focus**: Verify model relationships, field names, indexes, security implementation
- **Key Files**: `models/article.py`, `models/source.py`, `models/newsletter.py`, `models/pipeline.py`, `models/context.py`, `models/auth.py`
- **Known Issues from AGENTS.md**: `TrendMemory.embedding` is Text not vector; `Source.adapter_config` documented but never implemented; `Source.type` is actually `source_type`; `Source.last_fetch_at` is actually `last_crawled`; `Article.finalized_at` doesn't exist - use `published_at`; `TrendMemory.observation` is actually `signal`
- **Output**: `plans/models_review.md`

### 2. Adapters (`adapters.md`)
- **Focus**: Verify adapter pattern, SSRF protection, error handling, registry mechanism
- **Key Files**: `adapters/base.py`, `adapters/rss.py`, `adapters/api.py`, `adapters/web.py`, `adapters/session.py`
- **Known Issues from AGENTS.md**: URL validation duplication between `utils/url.py` and `services/url.py`; SSRFSafeRedirectHandler redirect counter bug (fixed but verify); trafilatura ImportError handling
- **Output**: `plans/adapters_review.md`

### 3. Services (`services.md`)
- **Focus**: Verify clean layering (no adapter imports), LLM provider system, circuit breaker, rate limiter
- **Key Files**: `services/*.py` (excluding subagent/)
- **Known Issues from AGENTS.md**: Rate limiter must release slots in `finally` block; `provider_id` vs `rc.provider` model mismatch (fixed but verify)
- **Output**: `plans/services_review.md`

### 4. Schemas (`schemas.md`)
- **Focus**: Verify Pydantic models match documented field names, StageConfig stub note
- **Key Files**: `schemas/pipeline.py`, `schemas/llm_responses.py`, `schemas/source.py`
- **Output**: `plans/schemas_review.md`

### 5. Utils (`utils.md`)
- **Focus**: Verify pure functions, minimal dependencies, SSRF protection in utils/url.py
- **Key Files**: `utils/*.py`
- **Known Issues from AGENTS.md**: `utils/url.py` has global mutable state (`_dns_cache`, `_dns_cache_lock`, `_dns_executor`) despite docstring claims of pure functions
- **Output**: `plans/utils_review.md`

### 6. Pipeline (`pipeline.md`)
- **Focus**: Verify stage transitions, degradation behavior, monitoring, failure handling
- **Key Files**: `services/newsletter_pipeline.py`, pipeline stages in `tasks/`
- **Known Issues from AGENTS.md**: `VALID_TRANSITIONS` missing `selecting` and `selected` statuses (fixed but verify); Newsletter `idempotency_key` bug (fixed but verify)
- **Output**: `plans/pipeline_review.md`

### 7. Tasks (`tasks.md`)
- **Focus**: Verify Celery tasks, stage transitions, run_stage helper, rate limiting
- **Key Files**: `tasks/*.py`
- **Output**: `plans/tasks_review.md`

### 8. Routes (`routes.md`)
- **Focus**: Verify endpoints, security (TOTP, session binding, CSRF), rate limiting
- **Key Files**: `routes/admin/`, `routes/public/`
- **Known Issues from AGENTS.md**: `api_tokens_bp` auth redirect bug (fixed but verify)
- **Output**: `plans/routes_review.md`

### 9. Subagent (`subagent.md`)
- **Focus**: Verify tool registry, chain system, middleware, runner implementation
- **Key Files**: `services/subagent/*.py`
- **Known Issues from AGENTS.md**: Subagent is at `services/subagent/` not top-level `subagent/`
- **Output**: `plans/subagent_review.md`

## Execution

Subagents will be launched in parallel for each module. Each subagent will:
1. Read the architecture document for their module
2. Explore the corresponding code files
3. Verify claims against implementation
4. Document discrepancies, bugs, and improvement recommendations
5. Write the improvement plan to the designated output file

## Verification

After all subagents complete, review the plans in `plans/` directory and aggregate findings into a summary.