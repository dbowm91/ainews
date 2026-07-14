# ainews Configuration, Installation, and Operator CLI Roadmap

## Status

Planning document for implementation handoff. This roadmap defines the path from the current repository-oriented setup to a supported operator experience centered on an `ainews` CLI, transactional configuration management, guided onboarding, and a one-shot installer.

## Problem statement

The application is operationally mature, but installation and first-run configuration still require operators to coordinate `.env`, `providers.yaml`, `pipeline.yaml`, `sources.yaml`, and `topics.yaml` manually. Required secrets are generated through separate commands, provider credentials and model assignments span multiple files, and lifecycle operations remain split between Docker Compose, shell scripts, Flask utilities, and documentation.

The project should retain ordinary inspectable configuration files, but expose a single supported control plane for creating, validating, changing, migrating, and operating them.

## Target operator experience

Interactive installation:

```bash
curl -fsSL https://raw.githubusercontent.com/dbowm91/ainews/main/scripts/install.sh | bash
ainews onboard
ainews start
```

Automated installation:

```bash
ainews onboard \
  --non-interactive \
  --config-file ./bootstrap.yaml \
  --start
```

Routine administration:

```bash
ainews config check
ainews providers add
ainews providers test
ainews status
ainews doctor
ainews backup
```

## Architectural principles

1. Configuration remains ordinary YAML and dotenv data. The CLI is a control plane, not an opaque replacement store.
2. Flask, Celery, the CLI, onboarding, doctor checks, and release validation must use one shared configuration engine.
3. All multi-file mutations are staged, validated as a unit, and committed atomically.
4. Secrets are classified centrally, redacted by default, entered through secure prompts or standard input, and written with restrictive permissions.
5. Interactive and non-interactive workflows must have feature parity.
6. The installer performs acquisition and bootstrap only; application configuration logic belongs in Python CLI code.
7. Commands must work outside the repository checkout through deterministic canonical path resolution.
8. Existing repository-local development workflows remain supported during migration.

## Scope

The roadmap covers:

- canonical configuration and data paths;
- shared typed configuration loading and validation;
- a packaged `ainews` command;
- configuration inspection and transactional mutation;
- interactive and declarative onboarding;
- provider management, including Ollama and EggPool;
- lifecycle, health, logs, and deployment diagnostics;
- a one-shot release installer;
- update, uninstall, backup, and restore;
- source, topic, and pipeline administration;
- service-manager integration;
- documentation and end-to-end release validation.

It does not introduce multi-node deployment, replace all configuration with a database, or make the shell installer responsible for application policy.

## Release sequence

### Release 1 — Configuration and CLI foundation

Release 1 establishes the internal contract on which every later workflow depends.

Primary outcomes:

- inventory every configuration key and cross-file dependency;
- define canonical paths and precedence;
- consolidate parsing, validation, provenance, redaction, and transactional writes;
- add the `ainews` console entry point;
- implement `config path`, `config show`, `config check`, `config get/set/unset`, `config diff`, `config rollback`, and the initial offline `doctor` checks;
- migrate Flask and Celery loading to the shared configuration library without changing runtime semantics.

Release 1 must be completed before implementing onboarding or the installer. Otherwise, setup policy will be duplicated in command handlers and shell scripts.

Detailed handoff: `plans/config_install_cli_release_1.md`.

### Release 2 — Onboarding, providers, and lifecycle

Release 2 makes the configuration foundation useful to operators.

Primary outcomes:

- interactive and declarative onboarding;
- deployment, pipeline, and source profiles;
- secure admin credential and application secret generation;
- provider adapters for Ollama, OpenAI, Anthropic, Gemini, generic OpenAI-compatible APIs, and EggPool;
- model discovery and pipeline assignment;
- Docker-aware host endpoint normalization;
- lifecycle commands for start, stop, restart, status, logs, health, and smoke validation;
- bounded readiness checks and migration integration.

Detailed handoff: `plans/config_install_cli_release_2.md`.

### Release 3 — Installer and production diagnostics

Release 3 packages the proven CLI workflow into the supported installation path.

Work includes:

- `scripts/install.sh` with stable, prerelease, and main channels;
- immutable release artifacts and SHA-256 verification;
- canonical directory creation and install metadata;
- resumable setup when Docker is unavailable;
- `ainews doctor --production`, `--network`, and stable JSON output;
- installer CI on clean Linux environments;
- README quick-start replacement.

The installer must call `ainews onboard`; it must not reimplement onboarding in shell.

### Release 4 — Full operator lifecycle

Release 4 completes common administration:

- source, topic, and pipeline commands;
- OPML import/export;
- backup, verification, and restore;
- update channels and staged upgrades;
- uninstall with data preservation by default;
- systemd and logrotate generation;
- configuration schema migration hooks.

### Release 5 — Closure and release hardening

Release 5 is the verification and documentation closure pass:

- clean-host install/onboard/start test;
- previous-version upgrade and rollback fixtures;
- interrupted mutation and restore tests;
- shell installer fault injection;
- JSON schema stability tests;
- security review of secret handling and service definitions;
- generated CLI and configuration references;
- full migration guide for repository-local installs.

## Cross-release architecture

### Proposed package boundaries

```text
ainews_config/
  fields.py
  paths.py
  dotenv.py
  yaml_io.py
  models.py
  loader.py
  validation.py
  provenance.py
  transaction.py
  migration.py

ainews_cli/
  main.py
  context.py
  output.py
  exit_codes.py
  commands/
    config.py
    doctor.py
    onboard.py
    providers.py
    lifecycle.py
    sources.py
    pipeline.py
    backup.py
    update.py
```

Names may be adjusted to fit current repository conventions, but configuration code must remain independent of Flask request context and CLI rendering.

### Canonical path model

User installation:

```text
~/.local/share/ainews/app/
~/.config/ainews/
~/.local/state/ainews/
~/.local/share/ainews/backups/
```

System installation:

```text
/opt/ainews/
/etc/ainews/
/var/lib/ainews/
/var/log/ainews/
/var/backups/ainews/
```

Required precedence:

```text
explicit CLI path
→ AINEWS_*_DIR environment override
→ recorded install metadata
→ platform canonical path
→ repository-local compatibility path in development mode only
```

`ainews config path` must report every resolved path and its provenance.

### Configuration field registry

Every supported key should have metadata equivalent to:

```python
ConfigField(
    key="pipeline.writer.model",
    destination="pipeline.yaml",
    path=("pipeline", "writer", "model"),
    value_type=str,
    secret=False,
    restart_required=True,
)
```

The registry drives typed mutation, validation, secret redaction, restart-impact reporting, generated documentation, and future schema migration.

### Transaction model

All mutations follow:

```text
acquire configuration lock
→ load current configuration set
→ create staging copy
→ apply requested changes
→ parse and validate all files
→ run optional external probes
→ produce redacted diff
→ atomically replace changed files
→ write bounded rollback snapshot
→ release lock
```

Failed validation or write operations must preserve the original files byte-for-byte.

### Output contract

The CLI should provide equivalent human and JSON results. JSON output must include a schema version, command, outcome, exit code, checks or changes, and redacted diagnostics. Secret values must never be serialized.

Recommended exit codes:

```text
0 success
1 general failure
2 invalid invocation
3 invalid configuration
4 missing prerequisite
5 connectivity failure
6 unhealthy deployment
7 degraded or partial success
```

## Major dependencies and ordering constraints

- The field inventory and path resolver precede all CLI mutation work.
- The shared loader and validator precede onboarding, provider commands, lifecycle preflight, and installer work.
- Transaction support precedes any command that writes multiple configuration files.
- Provider adapters precede a polished onboarding flow.
- Lifecycle commands precede the one-shot installer so that installation can delegate startup and readiness verification.
- Backup support must exist before staged upgrades are enabled.
- Documentation should be updated continuously, but the README should switch primary paths only after installer end-to-end tests pass.

## Security requirements

- Never accept plaintext passwords or long-lived API keys as recommended positional arguments.
- Use hidden prompts or `--stdin` for sensitive input.
- Redaction is metadata-driven, not based on key-name heuristics alone.
- Configuration exports exclude secrets by default.
- Secret-bearing backups use restrictive permissions and explicit warnings.
- Production validation rejects placeholder secrets and unsafe file permissions.
- Provider tests must not log request authorization headers or full upstream error bodies containing credentials.
- Install artifacts and updates require integrity verification.

## Testing strategy

Each release requires unit, integration, and failure-path coverage.

Required cross-cutting tests include:

- path precedence and operation outside the repository;
- malformed YAML and dotenv input;
- cross-file reference failures;
- transaction rollback after validation and I/O failures;
- concurrent mutation locking;
- secret redaction in human output, JSON, logs, exceptions, and diffs;
- idempotent onboarding and directory initialization;
- provider authentication and model-discovery failures;
- Docker host-network diagnostics;
- lifecycle partial-service failures;
- installer checksum and interrupted-extraction failures;
- upgrade and restore rollback.

## Completion criteria

This roadmap is complete when:

1. A supported host can install ainews through one documented command.
2. First-run setup does not require manual secret generation or coordinated edits across multiple files.
3. Ollama, EggPool, or a cloud provider can be configured through the CLI.
4. Runtime and CLI validation use the same code path.
5. All configuration writes are transactional and recoverable.
6. Lifecycle, diagnostics, backup, update, and uninstall are available through `ainews`.
7. Non-interactive setup is reproducible and tested.
8. The primary README workflow is exercised in CI from a clean environment.
9. Existing advanced manual workflows remain documented and functional.
