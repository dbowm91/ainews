# ainews Configuration and Operator CLI — Release 5 Closure and Hardening Plan

## Status

Final implementation and verification handoff for closing the configuration, installer, operator CLI, backup/update, and service-management roadmap.

This plan assumes Releases 1 through 4 are already implemented on `main`, including:

- the shared `ainews_config` engine;
- transactional configuration mutation and rollback;
- onboarding, provider management, and lifecycle commands;
- safe source diagnostics;
- release artifacts, checksum verification, and clean-host installer workflows;
- source, topic, pipeline, and OPML administration;
- backup, verification, restore, and schema migration support;
- update, channel, rollback, and uninstall commands;
- systemd service and logrotate generation;
- the existing unit, integration, installer, and JSON contract tests.

Do not expand product scope in this pass. Release 5 is a closure pass: consolidate evidence, validate real host behavior, close security and maintainability risks, stabilize public contracts, and produce a defensible release-candidate record.

## Objective

At completion, the full configuration/install/operator roadmap should be closed with all of the following properties:

1. A clean supported host can install, onboard, start, diagnose, update, roll back, stop, uninstall, and reinstall ainews through documented commands.
2. Supported upgrade paths from the oldest maintained installation format are tested end to end.
3. Backup and restore are proven against real configuration and SQLite state, including interrupted operations and corruption cases.
4. Generated systemd units and logrotate rules are validated by real system tools in an isolated Linux environment.
5. Installer, update, restore, and service-management operations preserve the previous working state on failure.
6. Human and JSON CLI contracts are stable, versioned, secret-free, and covered by snapshot/schema tests.
7. The largest implementation modules have clear ownership boundaries and no avoidable correctness-critical monoliths.
8. Release 1–4 acceptance evidence is consolidated into one authoritative closure matrix.
9. A specific release-candidate commit and its CI evidence are recorded and reproducible.
10. Remaining limitations are explicit and do not contradict the supported installation or operating model.

## Non-goals

- native Windows installation outside WSL;
- multi-node or clustered deployment;
- Kubernetes packaging;
- replacing SQLite with another database;
- application-serving frameworks outside the current deployment model;
- adding new providers, source types, content features, or UI capabilities;
- broad rewrites solely to reduce line count;
- replacing systemd with a cross-platform service abstraction;
- implementing automatic privileged host hardening beyond generated service definitions.

---

## Workstream 1 — Establish and pin the release-candidate baseline

### Tasks

Select one commit as the Release 5 candidate before beginning corrective changes. Record:

- full commit SHA;
- Python and `uv` versions;
- supported operating systems and architectures;
- Docker and Compose versions used by CI;
- minimum supported prior ainews version;
- full test inventory and current pass/fail counts;
- known pre-existing failures or environment-dependent skips.

Run the existing repository checks using the same commands CI is expected to run:

```bash
uv sync --all-extras
uv run ruff check .
uv run mypy .
uv run pytest
bash tests/test_install.sh
bash tests/installer_e2e.sh
bash scripts/validate_artifact.sh <artifact> <version>
```

Create `docs/config-cli-release-5-baseline.md` containing exact commands and results. Do not record approximate test counts.

### Acceptance criteria

- [ ] One exact commit SHA is designated as the baseline.
- [ ] Every baseline command is recorded with its exit status.
- [ ] All failing or skipped tests have an owner and disposition.
- [ ] No Release 5 work begins from an unrecorded or moving baseline.
- [ ] Test counts in documentation match actual collection output.

---

## Workstream 2 — Consolidated Release 1–4 closure matrix

### Tasks

Create `docs/config-cli-roadmap-closure.md` as the authoritative acceptance matrix for Releases 1–4.

For every requirement in:

- `plans/config_install_cli_release_1.md`;
- `plans/config_install_cli_release_2.md`;
- `plans/config_install_cli_release_3*.md`;
- `plans/config_install_cli_release_4*.md`;

record:

| Field | Required content |
|---|---|
| Requirement | Exact requirement or concise normalized statement |
| Status | complete / accepted limitation / deferred / failed |
| Implementation | Repository path and primary symbol or command |
| Unit evidence | Test file and test name or test class |
| Integration evidence | Real-filesystem, fake-service, or system-level test |
| Failure-path evidence | Explicit rollback, interruption, or invalid-input test |
| Documentation | User-facing document or generated reference |
| Notes | Compatibility or operational qualification |

Accepted limitations require a rationale and must not invalidate the primary supported workflow.

### Acceptance criteria

- [ ] Every Release 1–4 plan item appears exactly once in the matrix.
- [ ] No item is marked complete using only a commit message as evidence.
- [ ] Every mutation or lifecycle feature has at least one failure-path test.
- [ ] Every public command has user-facing documentation.
- [ ] Any deferred item is either moved to a named future roadmap or explicitly removed from scope.
- [ ] The matrix contains no ambiguous labels such as “mostly complete.”

---

## Workstream 3 — Clean-host full lifecycle validation

### Required scenarios

Run clean-host validation in isolated environments for at least:

- Linux x86_64;
- Linux ARM64;
- macOS ARM64 for installer and non-systemd CLI paths;
- a Linux environment with systemd as PID 1 for service-manager validation.

The Linux full-lifecycle scenario must execute:

```text
clean host
→ install from release artifact through documented installer command
→ verify checksum and install metadata
→ run non-interactive onboarding from a bootstrap file
→ configure a deterministic local provider or fake provider
→ run config check and doctor
→ start deployment
→ verify application health and worker health
→ create backup and verify it
→ mutate configuration
→ restore backup and verify original state
→ update to a staged newer fixture release
→ verify migrations and health
→ roll back to previous release
→ verify health and configuration
→ stop deployment
→ uninstall without purge
→ verify config/data preservation
→ reinstall
→ verify preserved installation resumes correctly
→ uninstall with purge in an isolated test root
```

Do not use the developer checkout as the installed application path.

### Acceptance criteria

- [ ] Full lifecycle passes on Linux x86_64.
- [ ] Installer, onboarding, config validation, and health pass on Linux ARM64.
- [ ] macOS installer and CLI paths pass for supported non-systemd features.
- [ ] Every scenario installs into canonical or isolated equivalent paths.
- [ ] Default uninstall preserves configuration and data.
- [ ] Purge removes only owned paths inside the isolated test root.
- [ ] Reinstall after non-purge uninstall preserves and reuses valid state.
- [ ] CI stores logs and evidence artifacts for every scenario.

---

## Workstream 4 — Prior-version upgrade and rollback fixtures

### Tasks

Define the minimum supported prior version and provide immutable fixtures representing:

- install metadata;
- configuration files;
- backup manifest format;
- database schema and representative SQLite data;
- service state if applicable;
- provider and pipeline assignments.

At minimum, preserve the existing `0.9.0 → 1.0.0` fixture path and add a fixture representing the immediately previous release format.

Test:

1. update planning;
2. compatibility checks;
3. pre-update backup;
4. staged artifact verification;
5. migration execution before activation;
6. activation;
7. post-update health;
8. rollback after an injected post-activation failure;
9. rollback after migration failure;
10. manual recovery instructions if automatic rollback also fails.

Fixtures must be generated or checked into a deterministic test path and must not depend on network access.

### Acceptance criteria

- [ ] The oldest supported version upgrades successfully to the release candidate.
- [ ] The immediately previous version upgrades successfully.
- [ ] Migration selection identifies every required step in order.
- [ ] A failed migration leaves the old release active and usable.
- [ ] A failed post-activation health check restores the prior release.
- [ ] Configuration and database state are byte-for-byte or semantically restored as specified.
- [ ] Rollback failure produces exact, tested manual recovery instructions.
- [ ] Unsupported versions fail before mutation with a stable reason code.

---

## Workstream 5 — Backup, restore, corruption, and interruption validation

### Required tests

Exercise real filesystem and SQLite behavior for:

- consistent SQLite snapshot while the database is open;
- configuration archive creation;
- secret-bearing file permission preservation;
- manifest checksum verification;
- missing section detection;
- corrupted tar member;
- corrupted SQLite backup;
- manifest tampering;
- restore dry-run;
- config-only restore;
- data-only restore;
- full restore;
- pre-restore safety backup;
- restore interruption before activation;
- restore interruption during activation;
- crash recovery marker handling;
- idempotent resume or rollback;
- pruning by count, age, total size, and pinned status.

Use explicit fault-injection hooks or controlled monkeypatch points rather than timing-dependent process kills wherever possible.

### Acceptance criteria

- [ ] Verification never mutates the backup or active installation.
- [ ] Corruption is detected before active files are replaced.
- [ ] Failed restore leaves the pre-restore state usable.
- [ ] Secret files retain restrictive permissions after restore.
- [ ] SQLite integrity checks pass after successful restore.
- [ ] Safety backups are created before destructive restore operations.
- [ ] Resume and rollback behavior is deterministic after interruption.
- [ ] Pruning never removes pinned backups.
- [ ] Count and total-size caps are both enforced on newly created backups.

---

## Workstream 6 — Real systemd validation

### Environment

Use an isolated Linux VM or container environment where systemd is PID 1. Validate both:

- user-scoped units;
- system-scoped units using controlled privilege escalation inside the isolated environment.

### Tasks

For each supported deployment profile:

1. render units;
2. validate paths and executable existence;
3. run `systemd-analyze verify` against generated units;
4. install units;
5. run `daemon-reload`;
6. enable/start when requested;
7. inspect active state;
8. verify restart behavior;
9. verify environment file permissions;
10. modify an installed unit and verify content-hash conflict protection;
11. inject a start failure and verify automatic rollback;
12. remove units and verify only owned files are deleted.

Inspect generated units for expected hardening directives and confirm that hardening does not block required application behavior.

### Acceptance criteria

- [ ] `systemd-analyze verify` reports no errors for every generated unit.
- [ ] User-scoped units install and run without root.
- [ ] System-scoped units install and run only through the explicit privileged path.
- [ ] Web, worker, beat, and Compose units reach expected active states.
- [ ] Restart limits and failure behavior match the documented policy.
- [ ] Environment secrets are referenced through files and never embedded in `ExecStart`.
- [ ] Modified unit files are not silently overwritten or removed.
- [ ] Failed installation rolls back files and service state.
- [ ] Generated hardening settings do not prevent required network, filesystem, or process behavior.

---

## Workstream 7 — Real logrotate validation

### Tasks

In an isolated Linux environment with logrotate installed:

- render rules for file-backed logs;
- run `logrotate --debug` or equivalent parser validation;
- run a forced rotation against temporary logs;
- verify ownership, mode, compression, delay-compress, retention count, and create behavior;
- verify duplicate rule detection;
- verify path traversal and newline rejection;
- verify journald-managed and Docker-managed logs are skipped with explicit status;
- verify removal respects ownership and modified-rule detection.

### Acceptance criteria

- [ ] Every generated rule is accepted by the real logrotate parser.
- [ ] Forced rotation produces the documented file layout and permissions.
- [ ] Journald and Docker log modes do not generate inappropriate file rules.
- [ ] Duplicate rules are rejected before installation.
- [ ] Unsafe paths are rejected before rendering or writing.
- [ ] Modified rules are preserved unless the operator explicitly forces removal.
- [ ] Installation and removal are idempotent.

---

## Workstream 8 — Installer and update fault injection

### Required fault classes

Installer:

- checksum mismatch;
- missing checksum entry;
- missing platform artifact;
- API rate limit;
- interrupted download;
- truncated archive;
- path traversal;
- absolute archive member;
- symlink escape;
- unwritable install destination;
- metadata write failure;
- onboarding failure;
- startup timeout;
- repeated installation over an existing working install.

Update:

- malicious or invalid install metadata paths;
- release metadata with unsupported URL scheme;
- checksum mismatch;
- artifact extraction failure;
- lock contention;
- backup failure;
- migration failure;
- activation failure;
- post-activation health failure;
- rollback failure;
- process interruption at every persisted update state.

### Acceptance criteria

- [ ] No failed installer or update case destroys the last known good installation.
- [ ] All temporary staging paths are either cleaned or recoverable.
- [ ] Existing configuration is preserved on installer rerun.
- [ ] Update lock contention returns a stable nonzero exit code and does not mutate state.
- [ ] Every persisted state can resume or roll back deterministically.
- [ ] Errors contain remediation but no secrets or authorization headers.
- [ ] Network failures are bounded by explicit timeouts.
- [ ] Unsupported URL schemes and unsafe paths are rejected before network or filesystem mutation.

---

## Workstream 9 — Security review

### Review scope

Perform a focused review of:

- installer shell behavior;
- artifact and checksum trust model;
- GitHub release/API parsing;
- archive extraction;
- canonical path and ownership validation;
- secret entry, storage, display, logs, JSON, exceptions, backups, and restore;
- provider credentials and upstream error handling;
- source safe-fetch behavior;
- update metadata and state files;
- systemd units and environment files;
- logrotate rules;
- uninstall and purge path deletion;
- temporary files and file modes;
- privilege boundaries.

Add automated tests for every confirmed issue. Document accepted residual risks.

### Mandatory invariants

- Secrets never appear in human output, JSON output, diffs, logs, exceptions, state files, or generated service commands.
- Artifact activation requires successful integrity verification.
- Archive extraction cannot escape staging.
- Delete operations require owned canonical paths.
- Provider and source probes use bounded, redacted network behavior.
- Privileged operations are explicit and minimized.

### Acceptance criteria

- [ ] A written security review exists at `docs/config-cli-security-review.md`.
- [ ] Every high or critical finding is fixed before closure.
- [ ] Medium findings are fixed or explicitly accepted with rationale.
- [ ] Secret-scanning tests cover every public JSON command.
- [ ] Shell scripts pass `shellcheck` with no unresolved high-confidence findings.
- [ ] Generated systemd units contain no inline secrets.
- [ ] Backup and restore permission tests cover secret-bearing files.
- [ ] Uninstall and purge cannot delete paths outside the recorded installation roots.

---

## Workstream 10 — Public JSON contract stabilization

### Tasks

Inventory every command supporting `--json`. Define a versioned schema or canonical fixture for each command family:

- version;
- config;
- doctor;
- providers;
- lifecycle/status/health;
- sources/topics/pipeline;
- backup/verify/restore;
- channel/update/rollback;
- uninstall;
- service/logrotate.

Standardize common envelope fields:

```json
{
  "schema_version": 1,
  "command": "...",
  "outcome": "success|warning|failure|skipped",
  "exit_code": 0,
  "data": {},
  "warnings": [],
  "errors": []
}
```

Existing stable contracts may retain compatible field placement, but deviations must be documented. Do not silently rename or remove fields during this pass.

### Acceptance criteria

- [ ] Every JSON-capable command has a schema or canonical snapshot test.
- [ ] Common envelope fields are present or an explicit compatibility exception is documented.
- [ ] Exit code and `outcome` agree for every tested result.
- [ ] Warning, failure, and skipped states are distinguishable.
- [ ] JSON output is valid with stdout containing no human-rendered text.
- [ ] No secret values or known secret patterns appear in serialized output.
- [ ] Schema changes require an explicit schema-version policy.

---

## Workstream 11 — Maintainability and module-boundary closure

### Priority modules

Review at minimum:

- `ainews_config/backup.py`;
- `ainews_cli/update/engine.py`;
- `ainews_cli/service/commands.py`;
- `ainews_cli/backup_commands.py`;
- `ainews_cli/sources/commands.py`;
- `ainews_cli/uninstall/commands.py`;
- `ainews_cli/service/logrotate_commands.py`.

Do not split files mechanically. Extract only when a module currently combines distinct correctness domains or makes isolated testing difficult.

Recommended backup boundaries:

```text
ainews_config/backup/
  models.py
  manifest.py
  create.py
  verify.py
  restore.py
  sqlite.py
  pruning.py
  recovery.py
```

Recommended update boundaries:

```text
ainews_cli/update/
  models.py
  resolution.py
  download.py
  staging.py
  migrations.py
  activation.py
  rollback.py
  recovery.py
  commands.py
```

Preserve public imports through compatibility re-exports where necessary.

### Acceptance criteria

- [ ] Each priority module has a documented responsibility assessment.
- [ ] Correctness-critical domain boundaries are separated where justified.
- [ ] No public CLI behavior changes as a side effect of decomposition.
- [ ] Existing imports continue to work or have explicit migration notes.
- [ ] Test coverage is redistributed to the extracted modules.
- [ ] Circular imports are not introduced.
- [ ] Ruff and mypy pass after refactoring.
- [ ] No new module exceeds the size of the monolith it replaces without documented justification.

---

## Workstream 12 — Generated documentation and migration guide

### Tasks

Generate or verify references for:

- CLI commands and options;
- configuration fields, types, destinations, secrecy, defaults, and restart impact;
- JSON schemas;
- bootstrap schema;
- backup manifest format;
- install metadata format;
- update state model;
- service and logrotate commands.

Create `docs/migrating-repository-install.md` for existing users running directly from a checkout. It must cover:

- detecting repository-local mode;
- backing up before migration;
- installing through the supported installer;
- importing or retaining existing `.env` and YAML files;
- canonical path precedence;
- validating providers and pipeline assignments;
- starting the installed deployment;
- rollback to repository-local operation;
- removal of obsolete files only after verification.

### Acceptance criteria

- [ ] Generated references are reproducible from repository code or schemas.
- [ ] CI detects stale generated documentation.
- [ ] Every operator-facing configuration field appears in the reference.
- [ ] Secret fields are clearly marked and never show real values.
- [ ] The migration guide is tested against a repository-local fixture.
- [ ] README Quick Start matches the clean-host CI path exactly.
- [ ] Manual/advanced workflows remain documented but are not presented as the primary installation path.

---

## Workstream 13 — Release-candidate CI and evidence retention

### Required CI gates

The release-candidate SHA must have successful runs for:

- lint;
- type checking;
- full Python tests;
- installer shell tests;
- installer E2E tests;
- JSON contract tests;
- artifact build and validation;
- Linux x86_64 clean-host lifecycle;
- Linux ARM64 installer/bootstrap validation;
- macOS ARM64 installer/CLI validation;
- systemd integration environment;
- logrotate integration environment;
- prior-version upgrade/rollback fixtures;
- security and secret-leak checks;
- generated-document freshness.

Upload evidence artifacts containing:

- test summaries;
- installer logs;
- artifact validation reports;
- systemd verification output;
- logrotate verification output;
- upgrade/rollback traces;
- JSON schema snapshots;
- closure matrix.

### Acceptance criteria

- [ ] One exact release-candidate SHA has all required gates green.
- [ ] Required gates are branch-protected or documented as release-blocking.
- [ ] Evidence artifacts are retained long enough for release review.
- [ ] Test results are not inferred solely from commit messages.
- [ ] Any platform-specific skip is documented and approved before release.
- [ ] Re-running the workflow from the same SHA produces equivalent results.

---

## Workstream 14 — Final closure record

### Deliverable

Create `docs/config-cli-release-5-closure.md` containing:

1. release-candidate SHA;
2. supported platforms and prerequisites;
3. final roadmap matrix status;
4. exact test and CI results;
5. clean-host lifecycle evidence;
6. upgrade and rollback evidence;
7. backup and restore evidence;
8. systemd and logrotate evidence;
9. security review disposition;
10. JSON contract version;
11. module decomposition summary;
12. known limitations;
13. rollback and emergency recovery procedure;
14. final go/no-go decision.

The record must distinguish:

- verified fact;
- test-environment limitation;
- accepted product limitation;
- deferred future enhancement.

### Acceptance criteria

- [ ] Every Release 5 workstream is marked pass or has an explicit blocking failure.
- [ ] No critical or high-severity known defect remains open.
- [ ] No roadmap requirement remains in an ambiguous state.
- [ ] Recovery instructions are tested, not merely documented.
- [ ] The final supported installation command is exercised by CI.
- [ ] The final go/no-go decision identifies the exact release-candidate SHA.

---

## Ordered execution sequence

Execute in this order:

1. Pin baseline and create the initial evidence record.
2. Build the Release 1–4 closure matrix.
3. Add missing clean-host and prior-version fixtures.
4. Complete backup/restore interruption and corruption tests.
5. Add real systemd and logrotate environments.
6. Expand installer/update fault injection.
7. Perform the security review and fix findings.
8. Stabilize JSON contracts.
9. Perform targeted module decomposition.
10. Generate references and migration documentation.
11. Run the release-candidate CI matrix.
12. Produce the final closure record.

Do not perform large refactors before the behavioral fixtures and closure matrix exist. Tests must first capture the current intended behavior.

## Final release gate

The roadmap is closed only when all of the following are true:

- [ ] Releases 1–4 have a complete evidence-backed closure matrix.
- [ ] The documented clean-host installation command succeeds in CI.
- [ ] Onboarding requires no manual coordinated edits or separate secret-generation scripts.
- [ ] Provider setup, lifecycle, diagnostics, content administration, backup, restore, update, rollback, service management, and uninstall are available through `ainews`.
- [ ] All configuration mutations are transactional and recoverable.
- [ ] The oldest supported installation upgrades and rolls back successfully.
- [ ] Installer and update integrity checks cannot be bypassed through normal supported paths.
- [ ] Real systemd and logrotate validation passes.
- [ ] Public JSON contracts are versioned and secret-free.
- [ ] Security review has no unresolved high or critical findings.
- [ ] The release-candidate SHA has all required CI gates green.
- [ ] Final documentation matches tested behavior.
- [ ] A signed-off Release 5 closure record exists.

Failure of any unchecked item blocks roadmap closure.