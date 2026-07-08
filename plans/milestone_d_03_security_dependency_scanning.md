# Milestone D.3: Security and Dependency Scanning Policy

## Objective

Make security/dependency scans actionable for public release. The repo already runs pip-audit, Trivy, and gitleaks. Milestone D should define how findings are handled, when failures block release, how suppressions are recorded, and what additional scans are worth adding.

## Current baseline

Existing CI coverage includes:

- `pip-audit` for Python dependencies,
- Trivy filesystem scan,
- gitleaks secret scanning,
- ruff/pytest gates,
- safe-fetch SSRF tests,
- production config fail-closed tests.

## Required work

### 1. Define vulnerability triage policy

Document severity policy:

- Critical/high reachable vulnerabilities block release unless explicitly waived.
- Medium vulnerabilities require triage note before release.
- Low/informational findings can be deferred if not reachable.
- Any secret leak finding blocks release until removed and rotated.

Add a `docs/security_triage.md` or section in `docs/security.md`.

### 2. Suppression policy

If scan suppressions are needed, require:

- vulnerability ID,
- affected package/file,
- reason for suppression,
- reachability assessment,
- expiration date or revisit milestone.

Avoid unstructured ignore lists.

### 3. Dependency freshness report

Add a lightweight check or documented command:

```bash
uv tree --outdated
```

or equivalent if supported. If not supported reliably, document manual dependency-review steps.

### 4. License review

For public release, add a dependency license review step. Options:

- `pip-licenses`,
- `pip-licenses --format=markdown`,
- manual review exported to docs.

Acceptance does not require zero non-permissive licenses unless the project policy says so, but it must identify them.

### 5. Container scan policy

Trivy currently scans filesystem. Decide whether to also scan the built image:

```bash
docker build -t ainews-ci .
trivy image ainews-ci
```

If image scanning is too slow for every PR, run it on `main` and release candidates.

### 6. Secret scanning local equivalent

Document local command for gitleaks, e.g.:

```bash
gitleaks detect --source . --no-git
```

If gitleaks is not expected locally, document CI-only behavior.

## Acceptance criteria

- Security scan failure policy is documented.
- Suppressions, if any, require reason and expiry.
- Dependency license review command or artifact exists.
- Container-image scan is either added or explicitly staged for release candidates.
- Agents know not to suppress scanner failures without documented rationale.

## Validation commands

```bash
uv run pip-audit
trivy fs .
docker build -t ainews-ci .
trivy image ainews-ci
gitleaks detect --source .
```

Adjust exact commands to installed tooling and CI environment.

## Handoff cautions

- Do not blanket-ignore scan failures.
- Do not commit scanner output containing secrets.
- Do not require network-dependent scanner DB updates in offline local validation without a fallback explanation.
