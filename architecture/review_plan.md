# Architecture Review Plan

This document outlines the review plan for architecture documentation modules.

## Modules to Review

| Module | Document | Assigned Subagent | Output Plan File |
|--------|----------|-------------------|------------------|
| Overview | `overview.md` | - | - |
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
- **Known Issues**: `TrendMemory.embedding` is Text not vector; `Source.adapter_config` never implemented
- **Output**: `plans/models_review.md`

### 2. Adapters (`adapters.md`)
- **Focus**: Verify adapter pattern, SSRF protection, error handling, registry mechanism
- **Key Files**: `adapters/base.py`, `adapters/rss.py`, `adapters/api.py`, `adapters/web.py`, `adapters/session.py`
- **Output**: `plans/adapters_review.md`

### 3. Services (`services.md`)
- **Focus**: Verify clean layering (no adapter imports), LLM provider system, circuit breaker, rate limiter
- **Key Files**: `services/*.py` (excluding subagent/)
- **Output**: `plans/services_review.md`

### 4. Schemas (`schemas.md`)
- **Focus**: Verify Pydantic models match documented field names, StageConfig stub note
- **Key Files**: `schemas/pipeline.py`, `schemas/llm_responses.py`, `schemas/source.py`
- **Output**: `plans/schemas_review.md`

### 5. Utils (`utils.md`)
- **Focus**: Verify pure functions, minimal dependencies, SSRF protection in utils/url.py
- **Key Files**: `utils/*.py`
- **Output**: `plans/utils_review.md`

### 6. Pipeline (`pipeline.md`)
- **Focus**: Verify stage transitions, degradation behavior, monitoring, failure handling
- **Key Files**: `services/newsletter_pipeline.py`, pipeline stages in `tasks/`
- **Output**: `plans/pipeline_review.md`

### 7. Tasks (`tasks.md`)
- **Focus**: Verify Celery tasks, stage transitions, run_stage helper, rate limiting
- **Key Files**: `tasks/*.py`
- **Output**: `plans/tasks_review.md`

### 8. Routes (`routes.md`)
- **Focus**: Verify endpoints, security (TOTP, session binding, CSRF), rate limiting
- **Key Files**: `routes/admin/`, `routes/public/`
- **Output**: `plans/routes_review.md`

### 9. Subagent (`subagent.md`)
- **Focus**: Verify tool registry, chain system, middleware, runner implementation
- **Key Files**: `services/subagent/*.py`
- **Output**: `plans/subagent_review.md`

## Execution

Subagents will be launched in parallel after this plan is committed.
