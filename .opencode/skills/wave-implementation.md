# Subagent Branch Management

## Rules
1. **Separate Branches:** Each subagent task MUST use a dedicated branch to avoid merge conflicts
2. **Branch Naming:** `feat/wX-Y-description` where X is wave number, Y is item ID
3. **Base Branch:** All task branches should be based on the main working branch (e.g., `feat/implement-remaining-plan-items`)
4. **Merge Strategy:** Use `git merge --no-ff` to preserve task branch history
5. **Conflict Resolution:** If conflicts arise, resolve in favor of the main working branch

## Example Workflow
```bash
# Create task branch
git checkout -b feat/w1-s1-fix-env-permissions

# Subagent completes work, commits

# Merge back
git checkout feat/implement-remaining-plan-items
git merge feat/w1-s1-fix-env-permissions --no-ff -m "Merge W1-S1: Fix .env permissions"
```

## Verification
Always verify subagent work before merging:
- Run linter and tests
- Review diff for unintended changes
- Ensure only task-related files are modified
