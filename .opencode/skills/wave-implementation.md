# Subagent Branch Management

> **Note:** The comprehensive improvement plan (plans/plan.md) has been completed as of 2026-05-04. This skill is retained for reference on branch management patterns.

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

## Historical: Wave-Based Implementation (Completed 2026-05-04)

The implementation plan used a wave structure:
- **Wave 1:** Security & Core Stability
- **Wave 2:** Pipeline Performance & Efficiency
- **Wave 3:** Quality & Maintainability (BLE001 lint fixes)
- **Wave 4:** Documentation & Observability

This structure has been superseded by the completed plan status.

(End of file - 28 lines)