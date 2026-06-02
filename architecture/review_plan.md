# Architecture Review Plan

This document outlines a systematic review of the architecture documentation and the underlying codebase to verify claims, identify bugs, and discover improvement opportunities.

## Scope

Review all discrete architecture modules in `architecture/` **except** `review_plan.md` (this file). Each module will be reviewed in depth by a dedicated subagent.

## Modules to Review

| # | Module | Architecture Doc | Primary Code Location |
|---|--------|------------------|----------------------|
| 1 | Models | `architecture/models.md` | `models/` |
| 2 | Schemas | `architecture/schemas.md` | `schemas/` |
| 3 | Adapters | `architecture/adapters.md` | `adapters/` |
| 4 | Services | `architecture/services.md` | `services/` |
| 5 | Tasks | `architecture/tasks.md` | `tasks/` |
| 6 | Routes | `architecture/routes.md` | `routes/` |
| 7 | Utils | `architecture/utils.md` | `utils/` |
| 8 | Pipeline | `architecture/pipeline.md` | `tasks/`, `services/pipeline_degradation.py` |
| 9 | Subagent | `architecture/subagent.md` | `services/subagent/` |
| 10 | LLM Providers | `architecture/llm-providers.md` | `services/llm/` |
| 11 | Search Providers | `architecture/search-providers.md` | `services/search/` |
| 12 | Prompts | `architecture/prompts.md` | `prompts/`, `services/prompts.py` |
| 13 | Config | `architecture/config.md` | YAML configs, `config.py`, `schemas/` |
| 14 | Infrastructure | `architecture/infrastructure.md` | `extensions.py`, `services/` |

## Review Methodology

For each module, the reviewing subagent must:

1. **Read the architecture document** fully
2. **Read the corresponding source code files** to understand actual implementation
3. **Verify claims** made in the architecture document against the code:
   - Function signatures, class definitions, constant values
   - File paths and directory structure
   - Behavioral descriptions and flow control
   - Configuration formats and default values
4. **Identify discrepancies** between documentation and implementation
5. **Interrogate code for bugs** including:
   - Error handling gaps
   - Race conditions
   - Resource leaks (Redis slots, connections, file handles)
   - Edge cases not covered
   - Security vulnerabilities
6. **Identify improvement opportunities**:
   - Performance optimizations
   - Code duplication that could be consolidated
   - Missing abstractions or layering violations
   - Incomplete error recovery paths
7. **Write findings** to `plans/<module>_review.md`

## Subagent Assignments

Each subagent will receive a detailed prompt with:
- The specific architecture document to review
- Key claims to verify against code
- Specific code locations to examine
- Output format requirements

### Subagent 1: Models Review
**Files**: `architecture/models.md`
**Code**: `models/article.py`, `models/source.py`, `models/newsletter.py`, `models/pipeline.py`, `models/context.py`, `models/auth.py`, `models/webhook.py`, `models/tag.py`, `models/search.py`, `models/audit.py`, `models/quality.py`, `models/share.py`
**Output**: `plans/models_review.md`

### Subagent 2: Schemas Review
**Files**: `architecture/schemas.md`
**Code**: `schemas/pipeline.py`, `schemas/source.py`, `schemas/llm.py`, `schemas/llm_responses.py`, `schemas/tasks.py`, `schemas/topic.py`, `schemas/webhook.py`, `schemas/item.py`, `schemas/admin.py`, `schemas/search.py`, `schemas/common.py`
**Output**: `plans/schemas_review.md`

### Subagent 3: Adapters Review
**Files**: `architecture/adapters.md`
**Code**: `adapters/base.py`, `adapters/rss.py`, `adapters/api.py`, `adapters/web.py`, `adapters/session.py`
**Output**: `plans/adapters_review.md`

### Subagent 4: Services Review
**Files**: `architecture/services.md`
**Code**: `services/` (excluding subagent, llm, search which are separate)
**Output**: `plans/services_review.md`

### Subagent 5: Tasks Review
**Files**: `architecture/tasks.md`
**Code**: `tasks/crawl.py`, `tasks/extract.py`, `tasks/select.py`, `tasks/research.py`, `tasks/write.py`, `tasks/edit.py`, `tasks/newsletter.py`, `tasks/retry.py`, `tasks/cleanup.py`, `tasks/scheduler.py`, `tasks/embeddings.py`, `tasks/pipeline.py`
**Output**: `plans/tasks_review.md`

### Subagent 6: Routes Review
**Files**: `architecture/routes.md`
**Code**: `routes/admin/`, `routes/admin/api/`, `routes/public/`, `routes/decorators.py`
**Output**: `plans/routes_review.md`

### Subagent 7: Utils Review
**Files**: `architecture/utils.md`
**Code**: `utils/url.py`, `utils/text.py`, `utils/datetime.py`, `utils/hash.py`, `utils/html.py`, `utils/security.py`
**Output**: `plans/utils_review.md`

### Subagent 8: Pipeline Review
**Files**: `architecture/pipeline.md`
**Code**: `tasks/select.py`, `tasks/research.py`, `tasks/write.py`, `tasks/edit.py`, `services/pipeline_degradation.py`, `services/pipeline_failure.py`, `constants.py`
**Output**: `plans/pipeline_review.md`

### Subagent 9: Subagent Review
**Files**: `architecture/subagent.md`
**Code**: `services/subagent/runner.py`, `services/subagent/tools.py`, `services/subagent/registry.py`, `services/subagent/middleware.py`, `services/subagent/chain.py`, `services/subagent/conditions.py`
**Output**: `plans/subagent_review.md`

### Subagent 10: LLM Providers Review
**Files**: `architecture/llm-providers.md`
**Code**: `services/llm/base.py`, `services/llm/openai.py`, `services/llm/anthropic.py`, `services/llm/gemini.py`, `services/llm/ollama.py`, `services/llm/errors.py`, `services/llm/json_utils.py`, `services/circuit_breaker.py`
**Output**: `plans/llm_providers_review.md`

### Subagent 11: Search Providers Review
**Files**: `architecture/search-providers.md`
**Code**: `services/search/base.py`, `services/search/duckduckgo.py`, `services/search/google.py`, `services/search/searxng.py`, `services/search/hybrid.py`, `services/search/sqlite_fts.py`, `services/search/__init__.py`
**Output**: `plans/search_providers_review.md`

### Subagent 12: Prompts Review
**Files**: `architecture/prompts.md`
**Code**: `prompts/*.txt`, `services/prompts.py`, `services/researcher.py`, `services/writer.py`, `services/editor.py`, `services/subagent/prompt_templates.py`
**Output**: `plans/prompts_review.md`

### Subagent 13: Config Review
**Files**: `architecture/config.md`
**Code**: `config.py`, `pipeline.yaml`, `providers.yaml`, `sources.yaml`, `topics.yaml`, `schemas/pipeline.py`, `schemas/source.py`, `schemas/llm.py`, `schemas/topic.py`, `services/config_cache.py`, `services/config_unified.py`
**Output**: `plans/config_review.md`

### Subagent 14: Infrastructure Review
**Files**: `architecture/infrastructure.md`
**Code**: `extensions.py`, `celery_app.py`, `services/limiter.py`, `services/cache.py`, `services/health.py`, `services/metrics.py`, `services/email.py`, `services/webhooks.py`, `services/logging_utils.py`
**Output**: `plans/infrastructure_review.md`

## Stale Item Detection

After all subagent reviews complete, a final pass will identify stale items:

### Detection Criteria

An architecture document or section is considered **stale** if:

1. **Referenced files don't exist** - File paths in the doc no longer exist in the codebase
2. **Feature flags contradict code** - Doc says something is "disabled" or "not implemented" but code shows it exists
3. **Outdated function signatures** - Doc shows parameters or return types that don't match current code
4. **Deprecated modules** - Code has modules not documented, or docs reference modules removed from code
5. **Inconsistent naming** - Doc uses different names than what exists in code (e.g., old field names, old function names)
6. **Orphaned documentation** - Doc sections covering features that have been completely removed from code

### Stale Item Categories

| Category | Action |
|----------|--------|
| Outdated claim | Update the claim in the architecture doc |
| Missing documentation | Document the new feature (create new doc or section) |
| Deprecated feature | Remove the stale documentation section |
| Renamed/moved module | Update references throughout architecture docs |
| Fully obsolete | Delete the stale file from architecture/ |

### Known Items to Check

Based on AGENTS.md warnings, the following should be verified:

1. **NewsletterBrief schema** - Doc claims it has `preamble`, `footer`, `articles` fields but these are noted as NOT implemented
2. **StageConfig** - Documented as a stub with only `tools` field - verify this is still true
3. **Subagent tool count** - Doc says 14 tools (not 9 as older docs claim)
4. **ToolDefinition** - Doc says it does NOT have a `cached` field
5. **Rate limiter pattern** - Verify `provider_id or rc.provider` fallback pattern is used correctly
6. **utils/url.py purity** - Verify the doc's warning about global mutable state is accurate
7. **Layering violations** - Verify the documented intentional violations are still accurate
8. **Redis DB allocation** - Verify DB 0, 1, 15 assignments match code

## Output Files

Each subagent will write their findings to:

```
plans/
├── models_review.md
├── schemas_review.md
├── adapters_review.md
├── services_review.md
├── tasks_review.md
├── routes_review.md
├── utils_review.md
├── pipeline_review.md
├── subagent_review.md
├── llm_providers_review.md
├── search_providers_review.md
├── prompts_review.md
├── config_review.md
└── infrastructure_review.md
```

### Review Output Format

Each `plans/<module>_review.md` should contain:

```markdown
# <Module> Review

## Summary
Brief description of what was reviewed and overall health assessment.

## Verified Claims
List of claims from the architecture doc that were confirmed accurate.

## Discrepancies Found
- [ ] Claim: "<exact quote from doc>"
  - Reality: "<what the code actually does>"
  - Severity: Critical/Major/Minor
  - Suggested fix: "<how to resolve>"

## Bugs Identified
- **Bug 1**: Description
  - Location: `file:line`
  - Impact: <what goes wrong>
  - Suggested fix: <how to fix>

## Improvement Opportunities
- **Improvement 1**: Description
  - Location: `file:line`
  - Benefit: <what improvement this provides>

## Stale Items Found
Any outdated documentation or obsolete references found in this module's arch doc.

## Recommendations
Priority-ordered list of actions for this module.
```

## Execution Order

1. Launch all 14 subagents in parallel (they work independently)
2. Wait for all subagents to complete
3. Aggregate stale items from all review reports
4. Create consolidated stale items report
5. Update architecture directory (prune outdated docs, update stale claims)
6. Write final review summary

## Commit

After all reviews and updates are complete, commit the changes to `main` branch with message:

```
docs: complete architecture review - verify claims and identify improvements

- Add plans/ directory with per-module review reports
- Update stale architecture documentation
- Document verified claims and discrepancies found
- Identify bug fixes and improvement opportunities
```