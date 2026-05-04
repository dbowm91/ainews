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