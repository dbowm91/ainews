# Architecture Review Plan

**Status:** IN PROGRESS
**Created:** 2026-05-22
**Purpose:** Comprehensive review of all architecture documents with verification against actual codebase

## Modules to Review

| # | Module | Document | Output Plan |
|---|--------|----------|-------------|
| 1 | Adapters | `architecture/adapters.md` | `plans/adapters_review.md` |
| 2 | Models | `architecture/models.md` | `plans/models_review.md` |
| 3 | Overview | `architecture/overview.md` | `plans/overview_review.md` |
| 4 | Pipeline | `architecture/pipeline.md` | `plans/pipeline_review.md` |
| 5 | Routes | `architecture/routes.md` | `plans/routes_review.md` |
| 6 | Schemas | `architecture/schemas.md` | `plans/schemas_review.md` |
| 7 | Services | `architecture/services.md` | `plans/services_review.md` |
| 8 | Subagent | `architecture/subagent.md` | `plans/subagent_review.md` |
| 9 | Tasks | `architecture/tasks.md` | `plans/tasks_review.md` |
| 10 | Utils | `architecture/utils.md` | `plans/utils_review.md` |

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

## Subagent Execution

Launch 10 parallel subagents using the `general` subagent_type:

### Adapters Review
```
Review the architecture document at `architecture/adapters.md` and verify all claims against the actual codebase.

Your assigned module: Adapters

Tasks:
1. Read `architecture/adapters.md` thoroughly
2. For each claim, pattern, and file inventory in the document:
   - Locate the actual code in the codebase
   - Verify the claim is accurate
   - Note any discrepancies
3. Check for:
   - Layering violations
   - Deprecated patterns vs documented
   - Missing implementations
   - Security issues (SSRF, etc.)
   - Performance concerns
   - Bugs in implementation
4. Write a detailed improvement plan to `plans/adapters_review.md` with:
   - Summary of verified claims
   - Discrepancies and issues
   - Specific bugs (file:line)
   - Recommendations (CRIT/HIGH/MED/LOW)

Focus areas:
- RSSAdapter, APIAdapter, WebAdapter implementations
- Config field naming (config vs adapter_config)
- Pagination and filter implementations
- SSRF protection in session handling
- APIAdapter item_url handling

Report back only the path to your written plan when complete.
```

### Models Review
```
Review the architecture document at `architecture/models.md` and verify all claims against the actual codebase.

Your assigned module: Models

Tasks:
1. Read `architecture/models.md` thoroughly
2. For each claim, pattern, and file inventory in the document:
   - Locate the actual code in the codebase
   - Verify the claim is accurate
   - Note any discrepancies
3. Check for:
   - Layering violations
   - Deprecated patterns vs documented
   - Missing implementations
   - Security concerns
   - Performance concerns
   - Bugs in implementation
4. Write a detailed improvement plan to `plans/models_review.md` with:
   - Summary of verified claims
   - Discrepancies and issues
   - Specific bugs (file:line)
   - Recommendations (CRIT/HIGH/MED/LOW)

Focus areas:
- Source, Article, Tag, Newsletter, PipelineLog models
- Field naming accuracy (type vs source_type, last_fetch_at vs last_crawled)
- Relationship definitions and indexes
- PipelineStatus state machine
- TrendMemory model details

Report back only the path to your written plan when complete.
```

### Overview Review
```
Review the architecture document at `architecture/overview.md` and verify all claims against the actual codebase.

Your assigned module: Overview

Tasks:
1. Read `architecture/overview.md` thoroughly
2. For each claim, pattern, and file inventory in the document:
   - Locate the actual code in the codebase
   - Verify the claim is accurate
   - Note any discrepancies
3. Check for:
   - Layering violations
   - Deprecated patterns vs documented
   - Missing implementations
   - Security concerns
   - Performance concerns
   - Bugs in implementation
4. Write a detailed improvement plan to `plans/overview_review.md` with:
   - Summary of verified claims
   - Discrepancies and issues
   - Specific bugs (file:line)
   - Recommendations (CRIT/HIGH/MED/LOW)

Focus areas:
- Project structure accuracy
- Layer boundaries
- Directory structure
- utils/url.py purity assumptions

Report back only the path to your written plan when complete.
```

### Pipeline Review
```
Review the architecture document at `architecture/pipeline.md` and verify all claims against the actual codebase.

Your assigned module: Pipeline

Tasks:
1. Read `architecture/pipeline.md` thoroughly
2. For each claim, pattern, and file inventory in the document:
   - Locate the actual code in the codebase
   - Verify the claim is accurate
   - Note any discrepancies
3. Check for:
   - Layering violations
   - Deprecated patterns vs documented
   - Missing implementations
   - Security concerns
   - Performance concerns
   - Bugs in implementation
4. Write a detailed improvement plan to `plans/pipeline_review.md` with:
   - Summary of verified claims
   - Discrepancies and issues
   - Specific bugs (file:line)
   - Recommendations (CRIT/HIGH/MED/LOW)

Focus areas:
- Stage transitions (select→research→write→edit)
- Quality gates routing to review
- Rate limiter slot management
- Provider fallback chain behavior
- _run_stage_core implementation

Report back only the path to your written plan when complete.
```

### Routes Review
```
Review the architecture document at `architecture/routes.md` and verify all claims against the actual codebase.

Your assigned module: Routes

Tasks:
1. Read `architecture/routes.md` thoroughly
2. For each claim, pattern, and file inventory in the document:
   - Locate the actual code in the codebase
   - Verify the claim is accurate
   - Note any discrepancies
3. Check for:
   - Layering violations
   - Deprecated patterns vs documented
   - Missing implementations
   - Security concerns
   - Performance concerns
   - Bugs in implementation
4. Write a detailed improvement plan to `plans/routes_review.md` with:
   - Summary of verified claims
   - Discrepancies and issues
   - Specific bugs (file:line)
   - Recommendations (CRIT/HIGH/MED/LOW)

Focus areas:
- Blueprint registration and URL prefixes
- Admin API at /api/v1/
- Public vs admin separation
- API token authentication

Report back only the path to your written plan when complete.
```

### Schemas Review
```
Review the architecture document at `architecture/schemas.md` and verify all claims against the actual codebase.

Your assigned module: Schemas

Tasks:
1. Read `architecture/schemas.md` thoroughly
2. For each claim, pattern, and file inventory in the document:
   - Locate the actual code in the codebase
   - Verify the claim is accurate
   - Note any discrepancies
3. Check for:
   - Layering violations
   - Deprecated patterns vs documented
   - Missing implementations
   - Security concerns
   - Performance concerns
   - Bugs in implementation
4. Write a detailed improvement plan to `plans/schemas_review.md` with:
   - Summary of verified claims
   - Discrepancies and issues
   - Specific bugs (file:line)
   - Recommendations (CRIT/HIGH/MED/LOW)

Focus areas:
- RSSConfig, APIConfig, WebConfig schemas
- PaginationConfig implementation
- SourceConfig validation
- SearchConfig documentation

Report back only the path to your written plan when complete.
```

### Services Review
```
Review the architecture document at `architecture/services.md` and verify all claims against the actual codebase.

Your assigned module: Services

Tasks:
1. Read `architecture/services.md` thoroughly
2. For each claim, pattern, and file inventory in the document:
   - Locate the actual code in the codebase
   - Verify the claim is accurate
   - Note any discrepancies
3. Check for:
   - Layering violations
   - Deprecated patterns vs documented
   - Missing implementations
   - Security concerns
   - Performance concerns
   - Bugs in implementation
4. Write a detailed improvement plan to `plans/services_review.md` with:
   - Summary of verified claims
   - Discrepancies and issues
   - Specific bugs (file:line)
   - Recommendations (CRIT/HIGH/MED/LOW)

Focus areas:
- Service layer not importing from adapters
- LLM provider fallback chain
- Subagent orchestration
- Search provider inventory

Report back only the path to your written plan when complete.
```

### Subagent Review
```
Review the architecture document at `architecture/subagent.md` and verify all claims against the actual codebase.

Your assigned module: Subagent

Tasks:
1. Read `architecture/subagent.md` thoroughly
2. For each claim, pattern, and file inventory in the document:
   - Locate the actual code in the codebase
   - Verify the claim is accurate
   - Note any discrepancies
3. Check for:
   - Layering violations
   - Deprecated patterns vs documented
   - Missing implementations
   - Security concerns
   - Performance concerns
   - Bugs in implementation
4. Write a detailed improvement plan to `plans/subagent_review.md` with:
   - Summary of verified claims
   - Discrepancies and issues
   - Specific bugs (file:line)
   - Recommendations (CRIT/HIGH/MED/LOW)

Focus areas:
- ToolDefinition dataclass fields
- run_subagent_with_tools implementation
- _finalize_subagent_result
- Chain execution with tools

Report back only the path to your written plan when complete.
```

### Tasks Review
```
Review the architecture document at `architecture/tasks.md` and verify all claims against the actual codebase.

Your assigned module: Tasks

Tasks:
1. Read `architecture/tasks.md` thoroughly
2. For each claim, pattern, and file inventory in the document:
   - Locate the actual code in the codebase
   - Verify the claim is accurate
   - Note any discrepancies
3. Check for:
   - Layering violations
   - Deprecated patterns vs documented
   - Missing implementations
   - Security concerns
   - Performance concerns
   - Bugs in implementation
4. Write a detailed improvement plan to `plans/tasks_review.md` with:
   - Summary of verified claims
   - Discrepancies and issues
   - Specific bugs (file:line)
   - Recommendations (CRIT/HIGH/MED/LOW)

Focus areas:
- Celery task definitions
- Rate limiter usage
- Stage task routing
- Celery Beat schedule accuracy

Report back only the path to your written plan when complete.
```

### Utils Review
```
Review the architecture document at `architecture/utils.md` and verify all claims against the actual codebase.

Your assigned module: Utils

Tasks:
1. Read `architecture/utils.md` thoroughly
2. For each claim, pattern, and file inventory in the document:
   - Locate the actual code in the codebase
   - Verify the claim is accurate
   - Note any discrepancies
3. Check for:
   - Layering violations
   - Deprecated patterns vs documented
   - Missing implementations
   - Security concerns
   - Performance concerns
   - Bugs in implementation
4. Write a detailed improvement plan to `plans/utils_review.md` with:
   - Summary of verified claims
   - Discrepancies and issues
   - Specific bugs (file:line)
   - Recommendations (CRIT/HIGH/MED/LOW)

Focus areas:
- URL validation (SSRF protection)
- dns_cache behavior (mutable state)
- Helper function purity assumptions
- sanitize_html XSS protection

Report back only the path to your written plan when complete.
```

## Execution Order

1. Write this plan to `architecture/review_plan.md`
2. Launch all 10 subagents in parallel (independent modules)
3. Each subagent writes its improvement plan to `plans/<MODULE>_review.md`
4.汇总结果

## Output Files

All review plans will be written to the `plans/` directory:
- `plans/adapters_review.md`
- `plans/models_review.md`
- `plans/overview_review.md`
- `plans/pipeline_review.md`
- `plans/routes_review.md`
- `plans/schemas_review.md`
- `plans/services_review.md`
- `plans/subagent_review.md`
- `plans/tasks_review.md`
- `plans/utils_review.md`