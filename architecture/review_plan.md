# Architecture Review Plan

This document outlines the plan for reviewing the architecture documents in the `architecture/` directory. Each module will be reviewed by a subagent that will verify claims against the codebase and produce an improvement plan in the `plans/` directory.

## Modules to Review

| # | Module | Architecture Doc | Output Plan | Status |
|---|--------|-----------------|-------------|--------|
| 1 | Overview | `architecture/overview.md` | `plans/review_00_overview.md` | COMPLETED |
| 2 | Models | `architecture/models.md` | `plans/review_05_models.md` | COMPLETED |
| 3 | Services | `architecture/services.md` | `plans/review_02_services.md` | COMPLETED |
| 4 | Adapters | `architecture/adapters.md` | `plans/review_04_adapters.md` | COMPLETED |
| 5 | Schemas | `architecture/schemas.md` | `plans/review_08_schemas.md` | COMPLETED |
| 6 | Routes | `architecture/routes.md` | `plans/review_06_routes.md` | COMPLETED |
| 7 | Tasks | `architecture/tasks.md` | `plans/review_07_tasks.md` | COMPLETED |
| 8 | Pipeline | `architecture/pipeline.md` | `plans/review_01_pipeline.md` | COMPLETED |
| 9 | Subagent | `architecture/subagent.md` | `plans/review_03_subagent.md` | COMPLETED |
| 10 | Utils | `architecture/utils.md` | `plans/review_09_utils.md` | COMPLETED |

## Review Process

For each module, the subagent will:

1. **Read the architecture document** to understand the intended design
2. **Verify claims** by checking if the code implements what the docs claim
3. **Identify discrepancies** between documentation and implementation
4. **Find bugs and issues** in the implementation
5. **Propose improvements** based on best practices and the codebase conventions

## Subagent Instructions

Each subagent should:

- Read the designated architecture document fully
- Search the codebase for the relevant module code
- Compare documentation claims against actual implementation
- Check for:
  - Missing functionality described in docs
  - undocumented functionality in code
  - Bug-prone patterns or edge cases
  - Violations of the architecture principles (e.g., adapters importing from services)
  - Security concerns (fail-closed, proper validation)
  - Performance issues (caching, async patterns)
- Write a detailed improvement plan to the designated output path in `plans/`

## Execution

Run all subagent reviews in parallel for efficiency. Each subagent operates independently and writes its output to the plans directory.

## Review Summary (2026-05-08)

### Bugs Found

| Bug | Location | Severity | Fix |
|-----|----------|----------|-----|
| Missing `import random` | `adapters/web.py:2` | Critical | Added import |

### Documentation Fixes Applied

| Doc | Fixes Applied |
|-----|---------------|
| `overview.md` | Fixed subagent location (services/subagent/), added all 14 LLM providers |
| `adapters.md` | Fixed SSRFSafeRedirectHandler inheritance, clarified javascript:/data: blocking |
| `pipeline.md` | Fixed editor/researcher max_tokens, added complete selector config, clarified dynamic fallback chain |
| `subagent.md` | Fixed run_subagent_with_tools signature, replaced non-existent Chain classes, fixed usage example |
| `routes.md` | Removed /api/v1 prefix (endpoints at root), added missing endpoints, added /share note |
| `tasks.md` | Added all 14 Celery Beat tasks with accurate schedules |
| `utils.md` | Fixed format_date (relative time), validate_url_safe (str return, raises UnsafeURLError) |
| `schemas.md` | Fixed PipelineRootConfig, ResearchBrief, CondensedArticle, NewsletterBrief, task schemas |

### Key Findings

1. **Subagent location**: `services/subagent/` not top-level `subagent/`
2. **API endpoints**: Root-level (`/articles`) not prefixed (`/api/v1/articles`)
3. **StageConfig**: Only has `tools` field, actual config in `RoleConfig`/`SubagentStageConfig`
4. **ResearchBrief**: Much more complex structure with nested models not simple fields
5. **ExecutiveSummary**: Only has `summary` field, not the 6 documented fields
6. **Celery Beat**: 14 tasks exist, only 5 were documented