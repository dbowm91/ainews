# Architecture Review Plan

This document outlines the plan for reviewing the architecture documents in the `architecture/` directory. Each module will be reviewed by a subagent that will verify claims against the codebase and produce an improvement plan in the `plans/` directory.

## Modules to Review

| # | Module | Architecture Doc | Output Plan |
|---|--------|-----------------|-------------|
| 1 | Overview | `architecture/overview.md` | `plans/review_00_overview.md` |
| 2 | Models | `architecture/models.md` | `plans/review_05_models.md` |
| 3 | Services | `architecture/services.md` | `plans/review_02_services.md` |
| 4 | Adapters | `architecture/adapters.md` | `plans/review_04_adapters.md` |
| 5 | Schemas | `architecture/schemas.md` | `plans/review_08_schemas.md` |
| 6 | Routes | `architecture/routes.md` | `plans/review_06_routes.md` |
| 7 | Tasks | `architecture/tasks.md` | `plans/review_07_tasks.md` |
| 8 | Pipeline | `architecture/pipeline.md` | `plans/review_01_pipeline.md` |
| 9 | Subagent | `architecture/subagent.md` | `plans/review_03_subagent.md` |
| 10 | Utils | `architecture/utils.md` | `plans/review_09_utils.md` |

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