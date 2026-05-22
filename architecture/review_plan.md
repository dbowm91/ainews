# Architecture Review Plan

**Status:** IN_PROGRESS
**Created:** 2026-05-22
**Purpose:** Comprehensive review of all architecture documents with verification against actual codebase

## Modules to Review

| # | Module | Document | Output Plan | Subagent |
|---|--------|----------|-------------|----------|
| 1 | Adapters | `architecture/adapters.md` | `plans/adapters_review.md` | subagent-adapters |
| 2 | Models | `architecture/models.md` | `plans/models_review.md` | subagent-models |
| 3 | Overview | `architecture/overview.md` | `plans/overview_review.md` | subagent-overview |
| 4 | Pipeline | `architecture/pipeline.md` | `plans/pipeline_review.md` | subagent-pipeline |
| 5 | Routes | `architecture/routes.md` | `plans/routes_review.md` | subagent-routes |
| 6 | Schemas | `architecture/schemas.md` | `plans/schemas_review.md` | subagent-schemas |
| 7 | Services | `architecture/services.md` | `plans/services_review.md` | subagent-services |
| 8 | Subagent | `architecture/subagent.md` | `plans/subagent_review.md` | subagent-subagent |
| 9 | Tasks | `architecture/tasks.md` | `plans/tasks_review.md` | subagent-tasks |
| 10 | Utils | `architecture/utils.md` | `plans/utils_review.md` | subagent-utils |

**Excluded:** `architecture/review_plan.md` (this document)

## Review Methodology

Each subagent will:

1. **Read** the architecture document at `architecture/<MODULE>.md`
2. **Verify claims** by:
   - Locating actual implementation files referenced
   - Comparing documented patterns against actual code
   - Checking file inventories match reality
   - Verifying function signatures, class definitions, behavior
3. **Identify bugs and issues**:
   - Layering violations (adapters importing from services, etc.)
   - Deprecated patterns vs documented patterns
   - Missing implementations
   - Security concerns (SSRF, XSS, etc.)
   - Performance concerns
4. **Interrogate code for improvements**:
   - Code quality issues
   - Missing error handling
   - Race conditions
   - API design improvements
5. **Write improvement plan** to `plans/<MODULE>_review.md` with:
   - Summary of verified claims
   - Discrepancies and issues found
   - Specific bugs (with file:line references)
   - Recommendations with priority (CRIT/HIGH/MED/LOW)

## Subagent Instructions

Launch 10 parallel subagents using the `general` subagent_type with this prompt for each:

```
Review the architecture document at `architecture/<MODULE>.md` and verify all claims against the actual codebase.

Your assigned module: <MODULE>

Tasks:
1. Read `architecture/<MODULE>.md` thoroughly
2. For each claim, pattern, and file inventory in the document:
   - Locate the actual code in the codebase
   - Verify the claim is accurate
   - Note any discrepancies
3. Check for:
   - Layering violations
   - Deprecated patterns vs documented
   - Missing implementations
   - Security issues
   - Performance concerns
   - Bugs in implementation
4. Write a detailed improvement plan to `plans/<MODULE>_review.md` with:
   - Summary of verified claims
   - Discrepancies and issues
   - Specific bugs (file:line)
   - Recommendations (CRIT/HIGH/MED/LOW)

Report back only the path to your written plan when complete.
```

## Module Focus Areas

### Adapters
- RSSAdapter, APIAdapter, WebAdapter implementations
- Config field naming (config vs adapter_config)
- Pagination and filter implementations
- SSRF protection in session handling

### Models
- Source, Article, Tag, Newsletter, PipelineLog models
- Field naming accuracy (type vs source_type, last_fetch_at vs last_crawled)
- Relationship definitions and indexes
- PipelineStatus state machine

### Overview
- Project structure accuracy
- Layer boundaries
- Directory structure

### Pipeline
- Stage transitions (select→research→write→edit)
- Quality gates routing to review
- Rate limiter slot management
- Provider fallback chain

### Routes
- Blueprint registration and URL prefixes
- Admin API at /api/v1/
- Public vs admin separation

### Schemas
- RSSConfig, APIConfig, WebConfig schemas
- PaginationConfig implementation
- SourceConfig validation

### Services
- Service layer not importing from adapters
- LLM provider fallback chain
- Subagent orchestration

### Subagent
- ToolDefinition dataclass fields
- run_subagent_with_tools implementation
- _finalize_subagent_result

### Tasks
- Celery task definitions
- Rate limiter usage
- Stage task routing

### Utils
- URL validation (SSRF protection)
- dns_cache behavior
- Helper function purity

## Execution

Run all 10 subagents in parallel (independent modules). Cross-module references noted but not blocking.

## Output

Each plan file at `plans/<MODULE>_review.md` used to:
1. Fix critical bugs
2. Update documentation
3. Add missing tests
4. Address layering violations