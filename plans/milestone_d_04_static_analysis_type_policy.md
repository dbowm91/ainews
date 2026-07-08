# Milestone D.4: Static Analysis and Type-Checking Policy

## Objective

Move static analysis from best-effort to an explicit policy. The current CI runs mypy with `|| true`, which makes type checking advisory. This may be acceptable temporarily, but public release should have a clear path to enforce at least scoped type correctness for new and security-critical code.

## Current state

- Ruff is enforced.
- Mypy is run but allowed to fail.
- Some legacy areas have known type complexity.
- Recent security-critical code such as `services/safe_fetch.py`, config validation, and auth/token handling benefits from stricter checks.

## Required work

### 1. Inventory mypy failures

Run:

```bash
uv run mypy . --exclude .venv
```

Categorize failures:

- security-critical code,
- config/startup code,
- tests,
- legacy models/SQLAlchemy complexity,
- provider/adapter typing,
- false positives / missing stubs.

### 2. Choose enforcement strategy

Preferred incremental strategy:

- Keep global mypy advisory for now.
- Add strict or required type checks for selected packages/files:
  - `services/safe_fetch.py`
  - `services/url.py`
  - auth/token services and decorators,
  - config validation helpers,
  - schemas.

Possible commands:

```bash
uv run mypy services/safe_fetch.py services/url.py config.py routes/decorators.py services/api_tokens.py
```

Add this as a required CI step once it passes.

### 3. Add pyproject/mypy config sections

Use mypy overrides to handle SQLAlchemy/plugin complexity without masking security-critical code.

Examples:

```toml
[[tool.mypy.overrides]]
module = ["models.*"]
ignore_errors = true
```

Only use broad ignores as a temporary policy with comments.

### 4. Ruff rule review

Audit currently enabled/disabled Ruff rules. Consider enabling additional security/correctness-oriented rules if low-noise:

- bugbear rules,
- comprehensions/simplification rules,
- exception hygiene where not already handled,
- import hygiene.

Do not enable large noisy rule sets without a staged plan.

### 5. Type policy docs

Document:

- what type checks are required,
- what is advisory,
- how to add new code in typed areas,
- how to handle missing stubs,
- how agents should avoid weakening type checks.

Suggested location: `AGENTS.md` and `docs/development.md`.

## Acceptance criteria

- Mypy allow-fail status is explicitly documented.
- A scoped required type-check gate is added for security/config code, or a concrete cleanup plan exists with failing inventory.
- Broad ignores are documented and bounded.
- Agents are instructed not to add new untyped code to typed/security-critical modules.

## Validation commands

```bash
uv run ruff check .
uv run mypy services/safe_fetch.py services/url.py config.py routes/decorators.py services/api_tokens.py
uv run mypy . --exclude .venv || true
```

## Handoff cautions

- Do not remove mypy from CI merely because it is noisy.
- Do not convert all failures to `Any` to make checks pass.
- Do not add broad `ignore_errors = true` without documenting why and when it will be revisited.
