# Subagent Branch Management

Conventions for managing subagent work and parallel development in this codebase.

## Branch Management Rules

1. **Separate Branches:** Each subagent task should use a dedicated branch to avoid merge conflicts
2. **Branch Naming:** `feat/description` where description is concise
3. **Merge Strategy:** Use `git merge --no-ff` to preserve task branch history when merging into integration branches

## Verification

Before merging subagent work:
- Run linter: `.venv/bin/ruff check . --exclude .venv`
- Run tests: `.venv/bin/python -m pytest tests/ -x -q`
- Review diff for unintended changes
- Ensure only task-related files are modified

## Lessons Learned (2026-05-05)

### Test Infrastructure Issues
Some tests fail due to **MagicMock objects being JSON serialized** - this is a test infrastructure issue, not a code bug. When `_dispatch_next` is imported from `services.pipeline_utils` but called from `tasks.pipeline`, the mock patch target matters:

```python
# WRONG - patches where function is defined, not where it's used
patch("services.pipeline_degradation._dispatch_next")

# CORRECT - patches where function is looked up at runtime
patch("tasks.pipeline._dispatch_next")  # if tasks.pipeline imports it
# or
patch("services.pipeline_utils._dispatch_next")  # if that's where it's used
```

### Layer Violations
- `adapters/` should NOT import from `services/`
- Utils should contain pure helper functions with no external dependencies
- RawItem dataclass moved to `schemas/item.py` as Pydantic model

### Pre-existing Test Failures
Before starting a new wave, always check if tests were already failing:
```bash
git stash
.venv/bin/python -m pytest tests/ -x -q  # see if tests pass without your changes
git stash pop
```