---
name: architecture_review
description: "Architecture review workflow — verifying architecture documents against actual code, identifying bugs and documentation discrepancies, and fixing issues found. Triggers: architecture review, review_plan.md, plans/*_review.md, architecture document verification."
---

## Overview

The architecture review process verifies that architecture documents accurately describe the actual codebase. Each module is reviewed independently and findings are documented.

## Review Workflow

### 1. Review Plan Structure

Each module has:
- **Architecture document**: `architecture/<module>.md`
- **Review output**: `plans/<module>_review.md`

### 2. Review Methodology

For each module, verify:
1. **File inventory** — Do all documented files exist?
2. **Function signatures** — Do documented signatures match actual code?
3. **Class schemas** — Do documented schemas match actual implementations?
4. **Layering** — Are layering rules (adapters→services) properly followed?
5. **Bugs** — Are there actual code bugs vs documentation issues?

### 3. Categorizing Issues

| Severity | Description | Action |
|----------|-------------|--------|
| CRIT | Critical bug causing runtime failure | Fix code immediately |
| HIGH | Significant bug affecting functionality | Fix code |
| MED | Medium priority issue | Fix if straightforward |
| LOW | Minor issue or documentation fix | Fix if easy, otherwise document |

### 4. Common Issue Types

#### Layering Violations
- Adapters importing from services (violates architecture)
- Services importing from adapters without TYPE_CHECKING

#### Documentation Discrepancies
- Documented field names don't match actual schema
- Documented function signatures differ from implementation
- Missing files in inventory
- Extra files not documented
- YAML examples use wrong field names or structure
- Abstract vs concrete method misclassification
- Incomplete function signatures (missing parameters)
- Wrong return type documentation

#### Security Issues
- SSRF protection gaps
- Authentication/authorization missing
- Input validation missing

### 5. Verification Checklist

- [ ] File inventory matches directory contents
- [ ] All class definitions match documented schemas
- [ ] Function signatures match actual code
- [ ] Layering rules are followed (adapters → utils only)
- [ ] No blind `except Exception` blocks
- [ ] Rate limiter properly released in finally blocks
- [ ] JSON imports present where needed

### 6. Writing Review Findings

Each review output should include:
1. **Summary** — Overview of findings
2. **Verified Claims** — What matched
3. **Discrepancies** — What differed
4. **Bugs** — Specific issues with file:line references
5. **Recommendations** — Actionable fixes

### 7. Code Fix Priority

When fixing bugs found during review:
1. **CRIT bugs** — Fix immediately, test, commit
2. **Documentation fixes** — Batch together for single commit
3. **MED issues** — Fix if straightforward, defer complex ones

### 8. Common Fix Patterns

#### Limiter Slot Leak
```python
# Before (buggy):
limiter.release(provider_id, model, timeout)
# After (fixed):
limiter.release(provider_id or rc.provider, model or rc.model, timeout)
```

#### Chain Step Validation
```python
# Before (buggy):
for i, step_config in enumerate(steps):
    task_type = step_config.task_type  # AttributeError if dict
# After (fixed):
for i, step_config in enumerate(steps):
    if not isinstance(step_config, SubagentChainStep):
        step_config = SubagentChainStep.model_validate(step_config)
    task_type = step_config.task_type
```

#### Middleware Clone Fix
```python
# Before (buggy - mutates cached ToolDefinition):
wrapped_fn = apply_middleware(copy.deepcopy(tool.fn), middleware_chain)
tool.fn = wrapped_fn  # Mutates cached object!
# After (fixed - creates new ToolDefinition):
wrapped_fn = apply_middleware(copy.deepcopy(tool.fn), middleware_chain)
tools[i] = ToolDefinition(
    name=tool.name,
    description=tool.description,
    parameters=tool.parameters,
    required=tool.required,
    fn=wrapped_fn,
)
```

#### Missing Import
```python
# If json.JSONDecodeError is used but json not imported:
import json  # Add at top of file
```

#### Shared Session Close Bug (CRIT)
```python
# Before (buggy - APIAdapter/WebAdapter close global session):
def close(self):
    self._session.close()  # Closes the SHARED global session!

# After (fixed - no-op since they share the global session):
def close(self):
    pass  # Don't close the shared global session!

# Note: RSSAdapter creates its own session, so its close() correctly closes:
# def close(self):
#     self._session.close()  # Its own session, not shared
```

#### Config Cache Without mtime (CRIT)
```python
# Before (buggy - cached_config doesn't invalidate on file change):
from schemas.common import cached_config  # No mtime tracking
load_search_config():
    return cached_config(key="search_config", loader_fn=loader_fn)

# After (fixed - use cached_config_with_mtime):
from schemas.common import cached_config_with_mtime
load_search_config():
    config_path = BASE_DIR / "providers.yaml"
    return cached_config_with_mtime(
        key="search_config",
        loader_fn=loader_fn,
        config_path=config_path,
    )
```

### 9. Commit Messages

Use prefix `Fix <area>:` for review fixes:
- `Fix subagent: Add chain step validation`
- `Fix services: Fix limiter slot leak using rc.provider fallback`
- `Fix documentation: Update adapters.md to reflect actual field names`

### 10. Wave-Based Implementation Approach

When multiple issues are found across modules, use a wave-based approach to avoid conflicts:

| Wave | Focus | Branch Pattern |
|------|-------|----------------|
| Wave A | CRIT bugs | `wave-a-crit-fixes` |
| Wave B | HIGH issues | `wave-b-high-fixes` |
| Wave C | MED issues | `wave-c-med-fixes` |
| Wave D | LOW issues | `wave-d-low-fixes` |

**Critical rules**:
- One wave per branch, sequential implementation
- Verify each fix on its branch before proceeding
- Create separate branches for AGENTS.md/skill updates
- Never run parallel agents on the same branch

### 11. Related Files

- `architecture/review_plan.md` — Master review plan
- `plans/review_*.md` — Individual module review outputs (15 files)
- `plans/architecture_review_consolidated.md` — Consolidated findings across all modules
- `plans/architecture_pruning_log.md` — Log of stale content fixes applied
- `AGENTS.md` — Contains "Design Notes for Future Agents" section
- `.opencode/skills/` — Specialized skills for subdirectories

### 12. Review Statistics (from 2026-05-31 review)

| Metric | Count |
|--------|-------|
| Documents reviewed | 15 |
| Total verified claims | 863 |
| Total incorrect claims | 41 (2H, 10M, 29L) |
| Total bugs | 22 (2H, 8M, 12L) |
| Total improvements | 82 |
| Total stale items | 17 |
| Cross-document contradictions | 3 |
| Recommended pruning actions | 25 |

**Key patterns discovered:**
- `models.md` has most incorrect claims (6) due to missing `index=True`/`nullable=` attributes
- `infrastructure.md` has most LOW bugs (3) from undocumented ThreadPoolExecutors
- `tasks.md` has most MEDIUM bugs (2) from incomplete stage transitions and missing `max_retries`
- 3 documents (utils, config, overview) have 0 incorrect claims — highly accurate