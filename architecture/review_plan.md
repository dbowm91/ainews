# Architecture Review Plan

This plan orchestrates a comprehensive review of all architecture documents in the `architecture/` directory. Each module is assigned to a subagent that will verify claims against the actual codebase and produce an improvement plan.

## Modules to Review

| # | Module | Document | Review Output |
|---|--------|----------|---------------|
| 1 | Adapters | `architecture/adapters.md` | `plans/adapters_review.md` |
| 2 | Overview | `architecture/overview.md` | `plans/overview_review.md` |
| 3 | Tasks | `architecture/tasks.md` | `plans/tasks_review.md` |
| 4 | Pipeline | `architecture/pipeline.md` | `plans/pipeline_review.md` |
| 5 | Utils | `architecture/utils.md` | `plans/utils_review.md` |
| 6 | Services | `architecture/services.md` | `plans/services_review.md` |
| 7 | Subagent | `architecture/subagent.md` | `plans/subagent_review.md` |
| 8 | Routes | `architecture/routes.md` | `plans/routes_review.md` |
| 9 | Schemas | `architecture/schemas.md` | `plans/schemas_review.md` |
| 10 | Models | `architecture/models.md` | `plans/models_review.md` |

## Review Methodology

Each subagent will:

1. **Read the architecture document** for their assigned module
2. **Verify claims in code** by:
   - Locating the actual implementation files
   - Comparing documented patterns against actual code
   - Checking that file inventories match reality
   - Verifying function signatures, class definitions, and behavior
3. **Identify bugs and issues**:
   - Layering violations (adapters importing from services, etc.)
   - Deprecated patterns that don't match documentation
   - Missing implementations that are documented
   - Security concerns or SSRF protection gaps
4. **Propose improvements**:
   - Code quality issues
   - Performance optimizations
   - Missing tests
   - Documentation corrections

## Subagent Prompts

Each subagent receives this base prompt, customized for their module:

```
Review the architecture document at `architecture/<module>.md` and verify all claims against the actual codebase.

Your specific module: <module>

Tasks:
1. Read `architecture/<module>.md` thoroughly
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
4. Write a detailed improvement plan to `plans/<module>_review.md` with:
   - Summary of verified claims
   - List of discrepancies and issues found
   - Specific bugs identified (with file:line references)
   - Improvement recommendations

Report back only the path to your written plan when complete.
```

## Execution Order

Subagents may run in parallel since they review independent modules. However, some modules reference each other (e.g., services.md references subagent.md, pipeline.md references tasks.md). Subagents should note cross-module references but focus on their assigned module.

## Output Files

Each subagent writes their improvement plan to `plans/<module>_review.md`. These files will contain:

- **Verified Claims**: What matched between documentation and code
- **Discrepancies**: What was documented but not found (or vice versa)
- **Bugs**: Specific issues with file:line references
- **Improvements**: Actionable recommendations

## Review Completion

After all subagents complete, aggregate findings will be used to:
1. Fix critical bugs identified
2. Update documentation to match reality
3. Add missing tests
4. Address layering violations