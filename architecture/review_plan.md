# Architecture Review Plan

**Status:** COMPLETED
**Created:** 2026-05-21

This plan orchestrates a comprehensive review of all architecture documents in the `architecture/` directory. Each module is assigned to a subagent that will verify claims against the actual codebase and produce an improvement plan stored in the `plans/` directory.

## Modules to Review

| # | Module | Document | Output Plan | Assigned Subagent |
|---|--------|----------|-------------|-------------------|
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

## Review Methodology

Each subagent will perform the following tasks for their assigned module:

1. **Read the architecture document** thoroughly
2. **Verify claims in code** by:
   - Locating actual implementation files referenced in the document
   - Comparing documented patterns against actual code
   - Checking that file inventories match reality
   - Verifying function signatures, class definitions, and behavior
3. **Identify bugs and issues**:
   - Layering violations (adapters importing from services, etc.)
   - Deprecated patterns that don't match documentation
   - Missing implementations that are documented
   - Security concerns or SSRF protection gaps
   - Performance concerns
4. **Interrogate code for improvements**:
   - Code quality issues
   - Missing error handling
   - Potential bugs or race conditions
   - API design improvements
5. **Write improvement plan** to `plans/<module>_review.md` with:
   - Summary of verified claims
   - List of discrepancies and issues found
   - Specific bugs identified (with file:line references)
   - Improvement recommendations with priority (CRIT/HIGH/MED/LOW)

## Subagent Prompt Template

```
Review the architecture document at `architecture/<MODULE>.md` and verify all claims against the actual codebase.

Your assigned module: <MODULE>

Tasks:
1. Read `architecture/<MODULE>.md` thoroughly
2. For each claim, pattern, and file inventory item in the document:
   - Locate the actual code in the codebase
   - Verify the claim is accurate
   - Note any discrepancies
3. Check for:
   - Layering violations (adapters importing from services, etc.)
   - Deprecated patterns vs documented patterns
   - Missing implementations
   - Security issues
   - Performance concerns
   - Bugs in implementation
4. Write a detailed improvement plan to `plans/<MODULE>_review.md` with:
   - Summary of verified claims
   - List of discrepancies and issues found
   - Specific bugs identified (with file:line references)
   - Improvement recommendations with priority levels

Report back only the path to your written plan when complete.
```

## Module-Specific Focus Areas

### Adapters (adapters.md)
- Verify RSSAdapter, APIAdapter, WebAdapter implementations
- Check config field naming (config vs adapter_config)
- Verify pagination and filter implementations
- Check SSRF protection in session handling

### Models (models.md)
- Verify Source, Article, Tag, Newsletter, PipelineLog models
- Check field naming (type vs source_type, last_fetch_at vs last_crawled)
- Verify relationship definitions and indexes
- Check PipelineStatus state machine

### Overview (overview.md)
- Verify overall project structure
- Check layer boundaries are respected
- Verify directory structure matches documented layout

### Pipeline (pipeline.md)
- Verify stage transitions (select→research→write→edit)
- Check quality gates routing to review status
- Verify rate limiter slot management
- Check provider fallback chain behavior

### Routes (routes.md)
- Verify blueprint registration and URL prefixes
- Check admin API endpoints at /api/v1/
- Verify public vs admin route separation

### Schemas (schemas.md)
- Verify RSSConfig, APIConfig, WebConfig schemas
- Check PaginationConfig implementation
- Verify SourceConfig validation logic

### Services (services.md)
- Check service layer doesn't import from adapters
- Verify LLM provider fallback chain
- Check subagent orchestration

### Subagent (subagent.md)
- Verify ToolDefinition dataclass fields
- Check run_subagent_with_tools implementation
- Verify _finalize_subagent_result exists and is called

### Tasks (tasks.md)
- Verify Celery task definitions
- Check rate limiter usage patterns
- Verify stage task routing

### Utils (utils.md)
- Verify URL validation (SSRF protection)
- Check dns_cache behavior
- Verify helper functions are pure

## Execution

Subagents may run in parallel since they review independent modules. Cross-module references should be noted but each subagent focuses on their assigned module only.

## Output Files

Each subagent writes their improvement plan to `plans/<module>_review.md`. These files will be used to:
1. Fix critical bugs identified
2. Update documentation to match reality
3. Add missing tests
4. Address layering violations