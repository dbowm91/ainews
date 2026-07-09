# Security Scanning and Vulnerability Triage Policy

This document defines how security scan findings are handled, when failures block release, how suppressions are recorded, and what additional scans are performed.

## Scanning Tools

| Tool | Scope | CI Job | Local Command |
|------|-------|--------|---------------|
| `pip-audit` | Python dependency CVEs | `pip-audit` | `uv run pip-audit` |
| Trivy | Filesystem + container image CVEs | `trivy` | `trivy fs .` |
| Gitleaks | Secret detection | `gitleaks` | `gitleaks detect --source . --no-git` |
| `pip-licenses` | Dependency license audit | Manual / release | `uv run pip-licenses --format=markdown` |

## Vulnerability Triage Policy

### Severity Classification

| Severity | Action | Blocks Release? |
|----------|--------|-----------------|
| **Critical** | Patch immediately. If reachable, blocks release until fixed or waived with documented justification. | Yes (unless waived) |
| **High** | Patch before release. If reachable, blocks release until fixed or waived with documented justification. | Yes (unless waived) |
| **Medium** | Triage required before release. Document decision (fix, defer, or suppress) with rationale. | No (but requires triage note) |
| **Low / Informational** | Can be deferred if not reachable. Track in backlog. | No |

### Reachability Assessment

A vulnerability is **reachable** if:
- The affected package is imported and its vulnerable code path is used in the application
- The vulnerability can be triggered by user input, network requests, or configuration
- No existing mitigation (e.g., input validation, SSRF protection) blocks the attack vector

A vulnerability is **not reachable** if:
- The affected package is a dev-only dependency not shipped in production
- The vulnerable code path is never executed (confirmed by code review)
- The vulnerability requires capabilities the application does not use

### Secret Leak Policy

Any secret leak finding (gitleaks or manual discovery) **blocks release** until:
1. The secret is removed from the codebase
2. The secret is rotated (credentials changed)
3. The incident is documented

No exceptions. No waivers.

## Suppression Policy

Suppressions are allowed only with documented rationale. Each suppression MUST include:

| Field | Required | Description |
|-------|----------|-------------|
| Vulnerability ID | Yes | CVE ID or advisory ID (e.g., `CVE-2024-12345`) |
| Affected package | Yes | Package name and version range |
| File / location | Yes | Where the dependency appears (e.g., `pyproject.toml`, `requirements.txt`) |
| Reason | Yes | Why the vulnerability does not apply or is accepted |
| Reachability | Yes | `reachable`, `not-reachable`, or `unassessed` |
| Expiration | Yes | Date or milestone when suppression must be re-evaluated |
| Author | Yes | Who approved the suppression |
| Date | Yes | When the suppression was created |

### Suppression Format

Suppressions are recorded in `SECURITY_SUPPRESSIONS.md` at the repository root:

```markdown
# Security Suppressions

| ID | CVE | Package | Reason | Reachable | Expires | Author | Date |
|----|-----|---------|--------|-----------|---------|--------|------|
| SUP-001 | CVE-2024-12345 | example-package<2.0 | Not reachable: vulnerability in CLI subcommand not used by application | not-reachable | 2026-12-01 | admin | 2026-07-09 |
```

### Suppression Rules

- No blanket ignore lists (e.g., `--ignore-all` is forbidden)
- Suppressions without expiration dates are not allowed
- Expired suppressions must be re-evaluated or removed before release
- Suppression changes require the same review as code changes

## Dependency Freshness

### Checking for Outdated Dependencies

```bash
# Using uv (preferred)
uv tree --outdated

# Using pip (fallback)
pip list --outdated --format=columns
```

### Policy

- Critical/high security updates must be applied within 7 days of advisory publication
- Regular updates should be reviewed monthly
- Major version upgrades require testing before merge
- Document any intentionally pinned versions in `pyproject.toml` comments

## License Review

### Command

```bash
# Generate license report
uv run pip-licenses --format=markdown

# Save for release records
uv run pip-licenses --format=markdown > docs/dependency_licenses.md
```

### Accepted Licenses

| License | Status | Notes |
|---------|--------|-------|
| MIT | Accepted | — |
| Apache-2.0 | Accepted | — |
| BSD-2-Clause | Accepted | — |
| BSD-3-Clause | Accepted | — |
| ISC | Accepted | — |
| MPL-2.0 | Accepted | File-level copyleft, compatible with MIT |
| LGPL-2.1+ | Review required | Library-level copyleft; acceptable for dynamically linked deps |
| GPL-2.0+ | Review required | Strong copyleft; requires legal review for SaaS distribution |
| AGPL-3.0 | Prohibited | Network copyleft triggers for SaaS |

### Policy

- All dependencies must have their license identified before public release
- Non-permissive licenses (LGPL, GPL, AGPL) require documented approval
- License review is a pre-release manual step (see `docs/release_checklist.md`)
- The license report is committed to `docs/dependency_licenses.md` and updated with each release

## Container Image Scanning

### Current Coverage

Trivy scans the filesystem in CI on every push/PR. This catches dependency CVEs in `pyproject.toml` and lock files.

### Image Scanning

Image scanning (`trivy image`) is **not** run on every PR due to build time constraints. Instead:

- Image scanning runs on `main` pushes and release candidates
- The `--security` mode in `scripts/validate_release.sh` includes filesystem scanning only
- To run image scanning locally:

```bash
docker build -t ainews-ci .
trivy image ainews-ci
```

### Policy

- Filesystem scan (every PR): Required check, blocks merge
- Image scan (main/release): Run manually or in release pipeline, blocks release if HIGH/CRITICAL found

## Secret Scanning

### CI Coverage

Gitleaks runs on every push and PR via the `gitleaks` CI job. Any finding blocks merge.

### Local Equivalent

```bash
# Full git history scan
gitleaks detect --source .

# Working directory only (no git history)
gitleaks detect --source . --no-git
```

If gitleaks is not installed locally, rely on CI. Install via:

```bash
# macOS
brew install gitleaks

# Linux (binary)
curl -sSL https://github.com/gitleaks/gitleaks/releases/latest/download/gitleaks_$(uname -s)_$(uname -m).tar.gz | tar xz -C /usr/local/bin
```

### .gitleaks.toml

The repository uses the default gitleaks configuration. If specific false positives arise, add targeted rules to `.gitleaks.toml` — never use `--no-rule` or blanket ignores.

## Release Validation

The `scripts/validate_release.sh --security` mode runs:

1. `pip-audit` — dependency CVE scan
2. `gitleaks detect --source . --verbose` — secret scan (if installed)
3. `trivy filesystem --severity HIGH,CRITICAL .` — filesystem CVE scan (if installed)

For full release validation, `--full` mode includes these plus lint, tests, smoke tests, and Docker build.

## Agent Guidelines

- **Never suppress scanner failures** without a documented rationale in `SECURITY_SUPPRESSIONS.md`
- **Never commit scanner output** containing secrets or sensitive data
- **Never use `--ignore-all`** or blanket suppression flags
- **Always check reachability** before deferring a vulnerability
- **Always set expiration dates** on suppressions
- **Update `docs/dependency_licenses.md`** when adding or changing dependencies
- **Run `--security` mode** before claiming release readiness
