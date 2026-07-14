# ainews Configuration and Operator CLI — Corrective Verification Pass

## Status

Implementation handoff plan for closing Releases 1 and 2 before installer work begins.

This plan assumes the current `main` branch already contains:

- the `ainews_config` package;
- the `ainews_cli` package and console entry point;
- transactional configuration writes and rollback snapshots;
- interactive and declarative onboarding;
- provider adapters and provider CLI commands;
- Docker Compose and bare-metal lifecycle drivers;
- expanded `doctor`, health, status, and smoke commands;
- the Release 1 and Release 2 test suites and documentation.

Do not rebuild those systems. This pass is narrowly corrective: fix known diagnostic defects, make status semantics reliable, verify the complete operator path under realistic conditions, clean misleading test artifacts, and produce explicit closure evidence.

## Objective

At completion, Releases 1 and 2 should be defensibly closed with the following properties:

1. `ainews doctor` accurately distinguishes pass, warning, failure, and skipped checks.
2. Source connectivity checks understand the real `sources.yaml` schema and use production-safe network primitives.
3. Routine diagnostics do not pull images, mutate host state, or perform unexpectedly expensive network work.
4. Configuration transactions, onboarding resume behavior, secret handling, provider setup, and lifecycle commands are exercised end to end.
5. The repository contains a release closure record mapping every Release 1 and Release 2 acceptance criterion to implementation and test evidence.
6. Release 3 installer work can begin without carrying known correctness ambiguity from the underlying CLI.

## Non-goals

- implementing `scripts/install.sh`;
- release artifact or channel management;
- update or uninstall workflows;
- backup and restore beyond transaction rollback validation;
- source/topic CRUD expansion;
- systemd deployment;
- broad redesign of the configuration model;
- replacing the provider adapter architecture;
- rewriting all large CLI modules solely to reduce line count.

Structural extraction is included only where it materially improves correctness, testability, or reviewability of the corrective work.

---

## Workstream 1 — Establish a reproducible baseline

### Tasks

Before modifying behavior, capture the current baseline for the Release 1 and Release 2 surfaces.

Run and record:

```bash
uv sync --all-extras
uv run ruff check .
uv run mypy .
uv run pytest \
  tests/test_config_fields.py \
  tests/test_config_paths.py \
  tests/test_config_loader.py \
  tests/test_config_validation.py \
  tests/test_config_transaction.py \
  tests/test_config_parity.py \
  tests/test_cli.py \
  tests/test_cli_doctor.py \
  tests/test_cli_doctor_expanded.py \
  tests/test_cli_onboard.py \
  tests/test_cli_providers.py \
  tests/test_cli_lifecycle.py \
  tests/test_cli_release2_completion.py \
  tests/test_lifecycle.py \
  tests/test_migrations.py
```

Then run the full suite using the repository’s normal CI invocation.

Record:

- Python version;
- platform and architecture;
- Docker and Compose versions where available;
- exact command lines;
- passed, failed, skipped, and xfailed counts;
- wall-clock duration;
- any network-dependent tests;
- any environmental assumptions.

### Required output

Create or update:

```text
docs/config-cli-release-closure.md
```

with a baseline section. Do not mark the releases closed yet.

### Acceptance criteria

- The targeted Release 1/2 test subset passes or every failure is classified before corrective implementation begins.
- The full suite result is recorded.
- No claimed test count exists only in a commit message; closure evidence is committed to the repository.

---

## Workstream 2 — Correct doctor result semantics

### Problem

The current doctor implementation can report checks as successful when they were skipped or could not be executed. This makes both human and JSON output unreliable for automation.

### Required model

Introduce an explicit result status enum or equivalent stable literal model:

```text
pass
warn
fail
skip
```

A check result should include at least:

```python
CheckResult(
    name: str,
    status: CheckStatus,
    message: str,
    remediation: str | None,
    blocking: bool,
    details: dict[str, object] | None,
    duration_ms: float | None,
)
```

Compatibility properties such as `passed` may remain temporarily if existing callers require them, but they must be derived from `status`, not independently assigned.

### Policy

Use the following semantics:

- `pass`: the check ran and verified the expected condition;
- `warn`: the check ran and found a degraded or optional problem;
- `fail`: the check ran or was required to run and found a blocking problem;
- `skip`: the check was intentionally not applicable or could not run because an optional prerequisite was absent.

A caught exception must not automatically become `pass`.

Classify checks by operating mode:

- default doctor: offline and low-impact checks plus bounded local runtime checks;
- `--network`: provider, SMTP, source, and external connectivity checks;
- `--production`: strict policy checks where warnings may become failures;
- optional `--deep`: explicitly expensive or container-assisted checks, if retained.

### Exit behavior

Define and test:

- exit 0 when there are no blocking failures;
- warning-only and skipped checks remain exit 0 unless strict production policy says otherwise;
- blocking failures return the documented doctor/configuration failure code;
- JSON includes counts for each status;
- human summary includes `PASS`, `WARN`, `FAIL`, and `SKIP` separately.

### Tests

Add tests covering:

- optional prerequisite absent → `skip`;
- network timeout → `warn` or `fail` according to check policy, never `pass`;
- production-required check unavailable → `fail`;
- warning-only report exit behavior;
- mixed report aggregation;
- stable JSON serialization;
- backwards compatibility where public fields are retained.

### Acceptance criteria

- No doctor check uses `passed=True` merely to indicate “not checked.”
- Human and JSON outputs distinguish verified health from skipped verification.
- Exit behavior is deterministic and documented.

---

## Workstream 3 — Repair source schema interpretation

### Problem

The current source-connectivity doctor logic treats `config.sources` as though it were a top-level list and expects a direct `url` field. The actual source configuration is schema-driven and commonly uses a root mapping plus adapter-specific URLs under `config`, such as `feed_url`, `list_url`, or another typed field.

### Tasks

Use the existing source configuration loader and Pydantic models rather than manually interpreting arbitrary dictionaries.

Create a reusable source inspection function that returns typed probe targets, for example:

```python
SourceProbeTarget(
    source_id: str,
    source_type: str,
    enabled: bool,
    primary_url: str | None,
    adapter_config: object,
)
```

The extraction logic must support every source type currently supported by the runtime. At minimum inspect the adapters and schemas for:

- RSS/feed sources;
- generic API sources;
- listing/web sources;
- any repository, social, or custom adapters presently registered.

Do not invent a universal URL when a source type does not have one. Such sources should be marked unsupported or skipped with a clear reason.

### Reuse

Place the target extraction close to the source schema or adapter registry so future source CLI commands can reuse it. Avoid burying schema interpretation inside `doctor.py`.

### Tests

Create fixtures representative of real `sources.yaml` structures and verify:

- root mapping is parsed correctly;
- enabled and disabled sources are distinguished;
- RSS `feed_url` is found;
- API `list_url` is found;
- web/listing target is found;
- missing optional URL produces `skip`, not “no sources configured”;
- malformed source configuration is surfaced as a configuration failure;
- source count and sampled count are reported accurately.

### Acceptance criteria

- A valid non-empty `sources.yaml` cannot be misreported as empty because of container shape.
- Probe targets derive from typed schema/adapter knowledge.
- Unsupported source types are explicit in output.

---

## Workstream 4 — Use production-safe source probes

### Problem

The current source doctor check uses direct `requests.head(..., allow_redirects=True)`, bypassing the application’s safe-fetch, redirect, DNS, and SSRF policy. `HEAD` also creates false negatives for feeds and sites that only support `GET` correctly.

### Tasks

Identify the canonical safe network primitive already used by source adapters. Reuse it rather than creating a separate HTTP client policy.

The diagnostic probe should:

- run URL validation through the production SSRF/safe-fetch layer;
- enforce bounded connect and total timeouts;
- enforce bounded redirects through the same redirect validator;
- cap response body bytes;
- avoid downloading full feed or page bodies;
- prefer a small streaming `GET` or adapter-native health probe rather than assuming `HEAD` support;
- identify DNS, policy rejection, TLS, timeout, HTTP status, and parse failures separately;
- avoid logging credentials or sensitive query parameters;
- sample a bounded number of sources by default;
- provide an explicit `--all-sources` or deep mode if exhaustive probing is useful.

Where an adapter already exposes a non-mutating validation or fetch method, use that method with a diagnostic budget.

### Result taxonomy

Source results should distinguish:

```text
reachable
http_error
timeout
dns_error
tls_error
policy_rejected
parse_error
unsupported
skipped
```

Map these to doctor `pass`, `warn`, `fail`, or `skip` based on whether the source is enabled and whether the command is in production-strict mode.

### Tests

Use mocked DNS/HTTP boundaries or a local test server. Do not rely on public internet services.

Required cases:

- safe public URL succeeds;
- private/reserved target is rejected;
- redirect to private target is rejected;
- excessive redirects fail;
- `HEAD`-rejecting but `GET`-working source succeeds;
- oversized body is capped;
- timeout is classified;
- HTTP 403/404 is classified;
- malformed feed or payload is classified when parse validation is requested;
- credentials and query secrets are redacted from output.

### Acceptance criteria

- No source diagnostic uses a raw unrestricted `requests` call.
- Doctor and production source fetching share the same URL-safety policy.
- Network tests are hermetic.

---

## Workstream 5 — Make Docker diagnostics non-invasive

### Problem

Routine doctor execution currently may invoke:

```bash
docker run --rm alpine:3.19 nslookup host.docker.internal
```

This can pull an image, alter local Docker state, require registry access, and add significant latency.

### Tasks

Replace the default behavior with layered, non-mutating checks:

1. inspect whether Docker and Compose are installed;
2. inspect the resolved Compose file and relevant `extra_hosts`, networks, and service endpoints;
3. inspect running application containers when available;
4. execute DNS checks inside an already-running project container when safe;
5. only create a disposable diagnostic container in an explicit deep mode;
6. never pull an image implicitly.

If deep mode uses a diagnostic image:

- require the image to exist locally or require explicit `--allow-pull`;
- document the mutation and network impact;
- bound execution time;
- use the project network where relevant;
- clean up deterministically.

### Output policy

Distinguish:

- Docker absent and not required by selected profile → `skip`;
- Docker absent but required → `fail`;
- Compose config lacks required host mapping → `warn` or `fail` based on provider endpoint/profile;
- DNS could not be verified because no container is running → `skip` or `warn`, not `pass`;
- DNS verified inside running container → `pass`.

### Tests

Mock subprocess execution and verify:

- default doctor never invokes `docker pull` or an image-creating `docker run`;
- no running container produces a non-pass status;
- running service container path is used when available;
- deep mode requires explicit opt-in;
- timeouts and Docker daemon errors are classified correctly;
- commands are argument arrays, not shell strings.

### Acceptance criteria

- Default `ainews doctor` is observational and does not create or download Docker artifacts.
- Docker DNS output is semantically accurate.

---

## Workstream 6 — Validate onboarding secret and resume safety

### Objective

Verify the security correction that removed generated secrets from persisted onboarding state and confirm that interrupted onboarding remains resumable.

### Tests

Add integration tests that perform the following:

1. initialize onboarding with temporary config and state directories;
2. generate application secrets and an administrator password hash;
3. force a failure after the transaction has staged or committed selected files;
4. inspect every onboarding state/resume file directly;
5. assert plaintext administrator passwords, API keys, generated `SECRET_KEY`, and generated `CELERY_TASK_SECRET` are absent;
6. assert secret values are present only in the intended protected configuration destination;
7. assert file permissions are restrictive where supported;
8. resume onboarding using references or existing configuration rather than persisted plaintext;
9. complete onboarding successfully;
10. verify state cleanup or completion-record behavior.

Also test explicit rotation paths:

- administrator password only;
- application secrets only;
- all supported secrets;
- dry-run rotation;
- validation failure during rotation;
- rollback after failed rotation;
- impact and restart warnings.

### Acceptance criteria

- Serialized onboarding state contains no plaintext generated secret material.
- Resume remains functional after the security change.
- Rotation is transactional and redacted.

---

## Workstream 7 — End-to-end configuration transaction verification

### Scenarios

Create integration tests using real temporary files rather than only mocked writers.

#### Scenario A — Valid multi-file update

```text
load .env and YAML files
→ change provider credential reference
→ add provider
→ assign pipeline role
→ validate staged complete configuration
→ commit atomically
→ reload through runtime loader
```

Verify:

- all destination files are correct;
- comments and ordering are retained where supported;
- unrelated fields are preserved;
- redacted diff contains no secret values;
- rollback manifest contains integrity metadata;
- runtime loader sees the new values.

#### Scenario B — Invalid cross-file update

```text
remove referenced provider
→ leave pipeline role pointing to it
→ validation fails
→ no target file changes
```

Verify byte-for-byte preservation.

#### Scenario C — Mid-commit failure

Inject a failure during replacement of one file in a multi-file transaction.

Verify:

- original state is restored;
- no temporary file is treated as authoritative;
- lock cleanup is correct;
- rollback snapshot remains usable;
- subsequent transaction succeeds.

#### Scenario D — Stale lock handling

Verify:

- active lock is respected;
- stale lock is detected using the documented policy;
- stale lock recovery is logged and safe;
- concurrent writers cannot both commit.

#### Scenario E — Rollback retention

Create more than the configured retention limit and verify deterministic pruning without deleting the active or newest required snapshot.

### Acceptance criteria

- Transaction claims are supported by real filesystem integration tests.
- Runtime/configuration parity is demonstrated after committed changes.

---

## Workstream 8 — Provider and lifecycle end-to-end verification

### Provider tests

Use local fake HTTP servers implementing minimal provider surfaces instead of public APIs.

Cover:

- generic OpenAI-compatible authentication probe;
- `/v1/models` discovery;
- EggPool model discovery and health behavior;
- Ollama model discovery;
- authentication rejection;
- malformed model response;
- timeout;
- Docker hostname warning;
- provider addition diff and transaction commit;
- failed probe leaves configuration unchanged;
- `--skip-probe` emits an explicit warning;
- setting default validates pipeline references;
- removing or changing a referenced provider is blocked or requires reassignment.

Secrets must remain redacted in all human and JSON outputs.

### Lifecycle tests

Use a controlled fake Compose executable or hermetic fixture to verify command construction and state transitions for:

- start with readiness wait;
- start with `--no-wait`;
- migration failure before startup;
- partial service health;
- Celery worker unavailable;
- status with pending migrations;
- status with provider summary;
- log tail/follow/timestamps/raw passthrough;
- stop and restart;
- smoke failure classification;
- command execution outside repository root.

Where CI supports Docker, add one real Compose smoke workflow using the repository services or a minimal dedicated test compose file.

### Acceptance criteria

- Provider management is transactionally verified against local deterministic services.
- Lifecycle command options reach the driver correctly.
- At least one real containerized smoke path is documented or CI-enforced where infrastructure allows.

---

## Workstream 9 — Clean misleading or weak test artifacts

### Tasks

Review:

```text
tests/test_onboarding.py
tests/test_provider_adapters.py
```

If these are intentionally empty placeholders, remove them or add a module docstring explaining why collection is intentionally empty. Prefer deletion when the real coverage exists in other test modules.

Audit the new Release 1 and Release 2 tests for:

- assertions that only check imports or object existence;
- mocks placed above the actual boundary under test;
- tests that duplicate implementation details without validating behavior;
- network tests that depend on public services;
- filesystem tests that never write real files;
- skipped tests lacking a tracked reason;
- unstable time-based assertions;
- secret redaction assertions that only inspect one output surface.

Add test markers if useful:

```text
unit
integration
network
docker
slow
```

Do not inflate closure evidence with empty modules or trivial assertion counts.

### Acceptance criteria

- No unexplained empty test files remain.
- The release closure record reports meaningful suites and scenarios, not only raw test totals.

---

## Workstream 10 — Targeted module decomposition

### Scope

Decompose only modules directly touched by the corrective work or whose current size prevents isolated testing.

Priority candidates:

```text
ainews_cli/doctor.py
ainews_cli/onboard.py
ainews_cli/main.py
```

### Recommended doctor structure

```text
ainews_cli/doctor/
  __init__.py
  model.py
  runner.py
  installation.py
  configuration.py
  runtime.py
  providers.py
  sources.py
  docker.py
  rendering.py
```

The doctor check registry should make each check independently invokable and declare:

- name;
- category;
- required modes;
- blocking policy;
- network or mutation characteristics;
- timeout budget.

### Recommended onboarding extraction

Only extract if needed for the new safety tests:

```text
ainews_cli/onboarding/
  state.py
  stages.py
  secrets.py
  declarative.py
  runner.py
  summary.py
```

### CLI root

Move command implementations out of `ainews_cli/main.py` where practical. The root should register command groups and global options, not own most domain logic.

### Constraints

- preserve public CLI command names and option behavior;
- avoid simultaneous broad refactoring of configuration loader/validation internals;
- keep commits separable from correctness fixes where possible;
- require parity tests before and after extraction.

### Acceptance criteria

- Corrective logic is independently testable.
- No user-visible CLI regression is introduced.
- Structural changes remain bounded and justified by the pass.

---

## Workstream 11 — Documentation and operator contract correction

### Tasks

Update documentation to reflect actual behavior after the corrective changes:

- `docs/cli-reference.md`;
- `docs/troubleshooting.md`;
- `docs/onboarding.md`;
- `docs/providers-cli.md`;
- `docs/deployment.md`;
- `docs/automation.md` where bootstrap/resume behavior changes;
- README quick-start language if it implies the future one-shot installer is already available.

Document:

- doctor statuses and exit behavior;
- which checks run by default, `--network`, `--production`, and deep mode;
- source sampling behavior;
- safe-fetch and SSRF policy reuse;
- whether Docker checks can mutate state;
- how onboarding state protects secrets;
- exact resume behavior;
- release boundaries: Releases 1 and 2 complete, installer deferred to Release 3.

### Acceptance criteria

- Documentation does not claim an installer exists before Release 3.
- Every documented doctor mode matches implemented behavior.
- Examples avoid plaintext credentials in command history or bootstrap files.

---

## Workstream 12 — Closure evidence and roadmap reconciliation

### Closure document

Complete `docs/config-cli-release-closure.md` with the following sections:

1. implementation commit range;
2. Release 1 acceptance-criterion matrix;
3. Release 2 acceptance-criterion matrix;
4. corrective findings and resolutions;
5. test command evidence;
6. end-to-end scenario results;
7. supported platforms exercised;
8. known limitations;
9. deferred Release 3 installer scope;
10. rollback guidance.

For each acceptance criterion, use one of:

```text
PASS
PASS WITH DOCUMENTED LIMITATION
DEFERRED TO RELEASE 3
FAIL
```

Every `PASS` must cite implementation files and tests or recorded manual evidence.

### Roadmap updates

Update:

```text
plans/config_install_cli_roadmap.md
plans/config_install_cli_release_1.md
plans/config_install_cli_release_2.md
```

Mark them historical/completed only after the closure matrix passes. Do not delete the plans.

Update `AGENTS.md` with:

- current command architecture;
- doctor status model;
- safe source probing contract;
- onboarding state security rules;
- remaining Release 3 priority.

### Acceptance criteria

- Future agents can determine exactly what is complete without inferring from commit messages.
- No Release 1 or Release 2 requirement is silently dropped.

---

## Required CI gates

Add or extend CI to run:

```bash
uv run ruff check .
uv run mypy .
uv run pytest tests/test_config_*.py tests/test_cli*.py tests/test_lifecycle.py tests/test_migrations.py
```

Add dedicated jobs or markers for:

- transaction filesystem integration;
- onboarding interruption/resume security;
- local fake provider integration;
- source safe-fetch policy;
- Docker Compose smoke where supported.

CI must not depend on public provider APIs or secrets.

The Docker job should record a clear skip when Docker is unavailable rather than silently passing without execution.

---

## Suggested implementation sequence

Execute in this order:

```text
1. Baseline evidence
2. Doctor status model
3. Source schema extraction
4. Safe source probes
5. Non-invasive Docker checks
6. Onboarding secret/resume tests
7. Transaction integration tests
8. Provider and lifecycle integration tests
9. Empty/weak test cleanup
10. Targeted module extraction
11. Documentation correction
12. Closure matrix and roadmap reconciliation
```

Do not begin with broad module refactoring. Correct semantics first, then extract stable responsibilities.

---

## Commit strategy

Prefer reviewable commits such as:

```text
fix(cli): add explicit doctor pass warn fail skip semantics
fix(cli): use typed safe source connectivity probes
fix(cli): make Docker diagnostics non-invasive
 test(cli): verify onboarding secret-safe resume and rotation
 test(config): add filesystem transaction integration coverage
 test(cli): add provider and lifecycle end-to-end fixtures
refactor(cli): split doctor checks into focused modules
 docs(cli): add Release 1 and 2 closure evidence
```

Avoid one monolithic commit combining behavior changes, structural moves, and documentation.

---

## Final completion criteria

This corrective pass is complete only when all of the following are true:

1. Doctor output distinguishes pass, warning, failure, and skipped checks.
2. No skipped or exception-suppressed check is represented as verified healthy.
3. Source diagnostics correctly parse real source configuration structures.
4. Source probes reuse the production URL-safety and redirect policy.
5. Default Docker diagnostics do not pull images or create containers.
6. Onboarding resume state is proven free of plaintext generated secrets.
7. Secret rotation is transactionally tested and redacted.
8. Multi-file transaction atomicity and rollback are verified using real temporary files.
9. Provider management is tested against deterministic local fake services.
10. Lifecycle option passthrough and failure classification are verified.
11. No unexplained empty test modules remain.
12. Targeted CLI decomposition preserves public behavior.
13. Targeted and full test suites pass with committed evidence.
14. Release 1 and Release 2 acceptance matrices contain no unresolved failures.
15. The roadmap explicitly identifies Release 3 installer work as the next phase.

Until these conditions are met, do not mark the configuration/install CLI roadmap ready to advance into installer implementation.