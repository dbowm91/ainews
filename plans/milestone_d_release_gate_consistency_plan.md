# Milestone D Release Gate Consistency Plan

## Purpose

This plan closes the remaining release-gate consistency issues found after the Milestone C/D implementation pass. The repo is now close to release-candidate shape: safe-fetch transport is thread-safe and IP-pinned, local release validation exists, CI gates are stronger, release/security docs exist, and mypy is now configured with scoped legacy ignores.

The remaining work is a focused cleanup pass: align the mypy policy across CI/docs/scripts, confirm safe-fetch HTTPS/SNI coverage or document its tested boundary, harden the local release script to match CI semantics, and capture real validation evidence before claiming release readiness.

## Current state summary

Implemented since the Milestone D plan set:

- CI has inline required-check documentation and workflow concurrency.
- `lint-and-test` runs ruff, full pytest+coverage, and mypy as a normal blocking step.
- Docker build, production image smoke, smoke-tests, compose-smoke, pip-audit, Trivy, and gitleaks remain in CI.
- `scripts/validate_release.sh` provides `--full`, `--fast`, `--security`, and `--with-mypy` modes.
- Makefile exposes `validate-release` and `validate-release-fast`.
- `docs/release_checklist.md` and `docs/security_triage.md` exist.
- Safe-fetch polish landed: non-default Host header ports, hop-local session cleanup in `finally`, proxy env ignoring, selected IP tracking, and thread-safe urllib3 pinned transport.
- `pyproject.toml` now has mypy configuration with broad ignores for known noisy legacy modules.

## Remaining issues

### 1. Mypy policy mismatch

CI currently treats mypy as blocking inside `lint-and-test`, but release docs and local validation script still describe mypy as advisory/optional.

Examples to clean up:

- `docs/release_checklist.md` states mypy is advisory and optional.
- Required CI gate table omits mypy as an effective required check, even though workflow comments list it and `lint-and-test` runs it without `|| true`.
- `scripts/validate_release.sh --with-mypy` says advisory and non-blocking, while CI blocks on mypy.

Desired policy:

- Either mypy is blocking everywhere, or it is advisory everywhere.
- Given current CI behavior, prefer making mypy blocking in release validation too.
- If full-repo mypy is too broad, change CI to a scoped required mypy command and document that exact scope.

### 2. Local validation script should mirror CI

`validate_release.sh --full` should run the same required gate semantics as CI. If CI blocks on mypy, local full validation should either:

- run mypy by default and fail on errors, or
- explicitly state that CI has an additional required mypy gate and `--full` is not release-complete without `--with-mypy`.

Prefer: run mypy by default in `--full`, make `--with-mypy` unnecessary or convert it to a compatibility alias.

### 3. Safe-fetch HTTPS/SNI behavior needs evidence or boundary docs

The safe-fetch transport has `PinnedHTTPSConnection`, but HTTPS/SNI/certificate behavior is subtle. Before release-readiness claims, add tests or precise docs describing what is verified.

Preferred:

- Add a local TLS fixture or targeted urllib3-level test verifying the TCP connection uses the pinned IP while original hostname is retained for TLS/SNI/cert hostname verification.

Acceptable if TLS fixture is too heavy:

- Document the tested behavior and keep a follow-up item saying full HTTPS local-certificate coverage remains deferred.
- Do not overclaim beyond tests.

### 4. Release docs should distinguish “required CI job” from “required step inside a job”

`mypy` is currently a step inside `lint-and-test`, not a separate job. Docs should not call it a required status check unless it is split into its own job.

Options:

- Keep it inside `lint-and-test` and document it as a required step of that required job.
- Split into a separate `mypy` job if branch protection should show it independently.

Prefer splitting only if branch-protection clarity is worth an extra job.

### 5. Validation evidence still missing

Do not claim release readiness until there is actual evidence from:

- GitHub CI run status, or
- local validation output from `bash scripts/validate_release.sh --full`, plus targeted safe-fetch tests.

This plan should ensure docs/agents state that code inspection alone is insufficient.

## Workstream 1: Align mypy policy

### Step 1: Decide policy

Recommended policy:

- `lint-and-test` remains required.
- `lint-and-test` includes blocking mypy.
- `scripts/validate_release.sh --full` runs blocking mypy by default.
- `--fast` may skip mypy for speed.
- `--security` skips mypy because it is not a security scan mode.

### Step 2: Update CI comments

In `.github/workflows/ci.yml`:

- Remove `mypy` from the required job list if it remains a step under `lint-and-test`.
- Under `lint-and-test`, comment that it includes ruff, pytest+coverage, and mypy.
- If a separate `mypy` job is created, keep `mypy` in the required job list.

### Step 3: Update release checklist

In `docs/release_checklist.md`:

- Move mypy from optional/advisory into Python/test validation.
- Remove stale “allow-fail” language.
- Required CI gate table should list `lint-and-test` as covering ruff, pytest, coverage, and mypy unless mypy is split.
- Advisory table should not mention mypy if it is blocking.

### Step 4: Update agent and development docs

Update:

- `AGENTS.md`
- `.opencode/skills/testing/SKILL.md`
- `docs/development.md`

State:

- full release validation includes blocking mypy,
- fast validation may skip mypy,
- agents must not report release readiness if mypy is failing.

## Workstream 2: Align `scripts/validate_release.sh`

### Required changes

- In `--full` mode, run `uv run mypy . --exclude .venv` by default and fail on errors.
- Remove “advisory” wording for `--with-mypy`, or repurpose it as a no-op compatibility flag with a warning:

```bash
--with-mypy is now included in --full by default.
```

- In `--fast`, either skip mypy visibly or add `--fast --with-mypy` as an optional blocking check.
- Ensure final summary reports mypy failures as release-blocking in full mode.

### Caution

Current `run_step ... || true` pattern intentionally continues through all checks while recording failures. Preserve that behavior if desired, but ensure failures are accumulated and final exit code is non-zero. Do not let a failed mypy step be hidden.

## Workstream 3: HTTPS/SNI safe-fetch coverage

### Preferred test

Add a local TLS fixture with a test certificate:

- Server binds to loopback.
- Resolver/pinning fixture maps `example.test` to loopback for test transport only.
- Request URL uses `https://example.test:<port>/`.
- Safe fetch connects to pinned IP.
- Server records SNI if feasible.
- Client cert verification behavior is either tested with a test CA or intentionally disabled only in the test adapter path.

### Alternative focused unit test

If full local TLS is too costly, add tests at the `PinnedHTTPSConnection`/urllib3 layer:

- assert `_new_conn()` calls `urllib3.util.connection.create_connection((pinned_ip, port), ...)`,
- assert `host` remains original hostname,
- assert adapter Host header preserves hostname and non-default port.

### Documentation fallback

If no HTTPS runtime test is added, update `docs/security.md`:

- say HTTPS uses `PinnedHTTPSConnection` intended to preserve original hostname for TLS,
- identify exact tests that cover it,
- note any remaining local-certificate/SNI fixture limitation.

## Workstream 4: Re-audit direct network calls

Run and document:

```bash
rg "trafilatura\.fetch_url|requests\.get|httpx\.get|urlopen|urllib\.request" services adapters tasks routes
```

Acceptance:

- no unreviewed direct untrusted fetches,
- if results exist, each is either safe-fetch internals, trusted internal service, or refactored.

Add a note to `docs/release_checklist.md` saying the grep must be run locally because GitHub search does not replace local `rg` with exact regex semantics.

## Workstream 5: Capture validation evidence

Add a lightweight release validation evidence template, either in `docs/release_checklist.md` or a new `docs/release_validation_record.md` template.

Template fields:

- commit SHA,
- date/time,
- CI run URL/status,
- local command run,
- result summary,
- known waivers,
- release decision.

Do not commit actual transient validation logs unless useful and sanitized.

## Validation commands

Targeted policy/docs checks:

```bash
rg "mypy|allow-fail|advisory|optional" .github/workflows/ci.yml docs AGENTS.md .opencode/skills scripts/validate_release.sh
```

Safe-fetch checks:

```bash
uv run pytest tests/test_safe_fetch.py tests/test_url_security.py tests/test_content_extractor_safe_fetch.py -q
rg "trafilatura\.fetch_url|requests\.get|httpx\.get|urlopen|urllib\.request" services adapters tasks routes
```

Release validation:

```bash
bash scripts/validate_release.sh --fast
bash scripts/validate_release.sh --full
bash scripts/validate_release.sh --security
```

CI-equivalent core:

```bash
uv run ruff check . --exclude .venv
uv run pytest tests/ -q
uv run mypy . --exclude .venv
```

## Final acceptance criteria

This pass is complete when:

- CI, release checklist, development docs, agent guidance, and local validation script agree on mypy policy.
- Full local release validation includes every required CI gate that can run locally.
- Any remaining CI-only gates are explicitly labeled.
- HTTPS/SNI safe-fetch behavior is tested or accurately documented as a limitation.
- Direct network-call audit is documented in the release checklist.
- A validation evidence template exists.
- No docs claim release readiness can be inferred from inspection alone.

## Non-goals

This pass does not add new product features, change provider behavior, add browser rendering, implement crawler politeness, or complete marketing/public-announcement copy.
