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

### 8. Example Fix Patterns

#### Missing Function
```python
# If _finalize_subagent_result is called but not defined:
# Add the function following similar patterns in the same file
```

#### Limiter Slot Leak
```python
# Before (buggy):
limiter.release(provider_id, model, timeout)
# After (fixed):
limiter.release(provider_id or rc.provider, model or rc.model, timeout)
```

#### Missing Import
```python
# If json.JSONDecodeError is used but json not imported:
import json  # Add at top of file
```

### 9. Related Files

- `architecture/review_plan.md` — Master review plan
- `plans/*_review.md` — Individual module review outputs
- `AGENTS.md` — Contains "Design Notes for Future Agents" section
- `.opencode/skills/` — Specialized skills for subdirectories

### 10. Commit Messages

Use prefix `Fix <area>:` for review fixes:
- `Fix subagent CRIT-1: Add missing _finalize_subagent_result function`
- `Fix services HIGH: Fix limiter slot leak using rc.provider fallback`
- `Fix documentation: Update adapters.md to reflect actual field names`
