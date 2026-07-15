# ainews Configuration and Operator CLI — Release 3C Clean-Host CI and Documentation

## Objective

Prove that the Release 3 installer is a supported operational path rather than a repository-local convenience. Add clean-host installation, onboarding, startup, diagnostics, and failure-path CI; stabilize the installer-facing documentation; and produce an auditable Release 3 closure record.

## Workstream 1 — Clean-host test matrix

Create CI jobs for at least:

- Ubuntu LTS x86_64 user installation;
- Ubuntu LTS arm64 through a native runner or supported emulation strategy;
- macOS arm64 when runner availability and dependencies permit;
- stable-style versioned artifact installation;
- main-channel exact-commit installation.

The primary Linux job must start from a runner without a repository checkout in the final installation directory. The test may check out the repo only to build or host fixtures; the installed application must operate from canonical paths.

## Workstream 2 — Full supported-path scenario

Exercise the documented path:

```text
fresh host
-> run installer
-> verify checksum and metadata
-> invoke `ainews version`
-> run non-interactive onboarding from bootstrap fixture
-> run `ainews config check`
-> run `ainews doctor --production`
-> start services
-> wait for bounded readiness
-> run health and smoke checks
-> inspect status
-> stop services
```

Assertions:

- commands run outside the repository;
- config/data/state are in canonical paths;
- generated secrets are not printed or persisted in onboarding state;
- dashboard and health endpoints are reported correctly;
- lifecycle exit codes are stable;
- shutdown leaves no orphaned project containers or processes.

Use deterministic local provider/source fixtures. Do not require public AI API credentials.

## Workstream 3 — Deferred prerequisite scenario

Test a host without usable Docker:

- installer succeeds when `--start` is not requested;
- install metadata is written;
- onboarding can be deferred or can complete for a non-Docker profile;
- output clearly distinguishes installed, configured, and running states;
- rerunning after Docker becomes available resumes without replacing config or secrets.

Also test Docker present but daemon unavailable, Compose missing, and insufficient permissions.

## Workstream 4 — Installer fault injection

Build fixture-driven tests for:

- unavailable release API;
- rate-limited API response;
- missing platform asset;
- checksum manifest missing;
- malformed checksum manifest;
- checksum mismatch;
- interrupted download;
- truncated archive;
- traversal/symlink escape archive;
- extraction failure;
- disk-full or unwritable staging directory;
- metadata write failure;
- onboarding failure after successful installation;
- startup timeout after successful onboarding.

For every case, verify:

- no unverified payload is executed;
- previous installations remain usable;
- temporary files are cleaned or identified for remediation;
- config/data/state are preserved;
- output includes a stable error category and resume command where applicable.

## Workstream 5 — CI artifact validation

Before publishing a release asset, CI must inspect the archive and verify:

- expected top-level structure;
- executable CLI entry point;
- Compose files and templates present;
- migrations present;
- static assets and packaged Halloy themes present;
- version metadata matches the tag/commit;
- no repository secrets, local caches, test databases, `.env`, or developer state included;
- no absolute paths or escaping links;
- artifact can be installed and invoked on a clean runner.

Publish the validation report as a CI artifact or release evidence file.

## Workstream 6 — JSON contract tests

Snapshot and schema-test installer-adjacent CLI JSON:

- `ainews version --json`;
- `ainews config path --json`;
- `ainews config check --json`;
- `ainews doctor --production --network --json`;
- `ainews status --json`;
- onboarding non-interactive result JSON if supported.

Requirements:

- explicit schema versions;
- deterministic field names and types;
- no secrets;
- additive evolution policy documented;
- exit status consistent with reported outcome;
- timestamps normalized or ignored in snapshots.

## Workstream 7 — README and installation documentation

Only after clean-host CI passes, replace the primary README setup path with:

```bash
curl -fsSL https://raw.githubusercontent.com/dbowm91/ainews/main/scripts/install.sh | bash
ainews onboard
ainews start
```

Document:

- stable versus prerelease versus main channels;
- user versus system installs;
- supported OS/architecture matrix;
- canonical paths;
- non-interactive bootstrap;
- Docker-absent deferred setup;
- integrity verification behavior;
- proxy/firewall considerations;
- uninstall/update commands as future Release 4 work, without implying they already exist;
- manual repository workflow as an advanced/development path.

Add a troubleshooting table mapping installer error categories to remediation.

## Workstream 8 — Release closure record

Create `docs/config-cli-release-3-closure.md` containing:

- final commit and release tag;
- artifact names and checksums;
- supported platform matrix;
- CI run links or identifiers;
- test counts and commands;
- safe-probe evidence;
- clean-host scenario results;
- fault-injection scenario results;
- known limitations;
- rollback/recovery instructions;
- explicit acceptance-criterion audit.

Update the roadmap to mark Release 3 complete only when every required gate has evidence.

## Acceptance criteria

- at least one clean Linux job installs, onboards, starts, validates, and stops ainews from canonical paths;
- the test does not rely on developer-local state or public provider credentials;
- corrupted and malicious artifacts fail closed;
- missing Docker supports a clean deferred-install outcome;
- JSON contracts are schema-tested and secret-free;
- release assets pass content and provenance validation;
- README primary instructions exactly match an exercised CI path;
- manual development installation remains documented;
- Release 3 closure evidence is committed and reviewable.
