# ainews Configuration and Operator CLI — Release 2 Detailed Plan

## Release objective

Release 2 turns the Release 1 configuration substrate into a complete first-run and day-two operator workflow. It introduces interactive and declarative onboarding, provider management, model discovery, pipeline assignment, and lifecycle commands for the current Docker Compose deployment.

Release 2 assumes the following are already complete:

- canonical path resolution;
- shared typed configuration loading;
- cross-file semantic validation;
- field registry and secret classification;
- transactional multi-file writes and rollback snapshots;
- packaged `ainews` CLI;
- stable human and JSON output contracts.

Do not duplicate those mechanisms in onboarding or provider commands.

## User-visible result

```bash
ainews onboard
ainews onboard --non-interactive --config-file bootstrap.yaml --start

ainews providers list
ainews providers add
ainews providers test
ainews providers models eggpool
ainews providers set-default eggpool
ainews providers assign eggpool auto selector researcher writer editor

ainews start
ainews stop
ainews restart
ainews status
ainews logs
ainews health
ainews smoke
```

## Non-goals

- release artifact installer and channel management;
- automatic system package installation;
- update and uninstall;
- backup and restore beyond Release 1 transaction snapshots;
- full source/topic CRUD;
- systemd installation;
- multi-node deployment;
- live reload of arbitrary configuration.

## Phase 2.1 — Onboarding domain model and state machine

### Tasks

Create an onboarding service independent of prompt rendering. Model onboarding as explicit stages with typed inputs and outputs.

Recommended stages:

```text
resolve_paths
→ select_deployment_profile
→ initialize_directories
→ configure_admin
→ generate_application_secrets
→ configure_database_and_redis
→ configure_provider
→ select_models
→ select_pipeline_profile
→ select_source_profile
→ configure_optional_newsletter
→ validate_staged_configuration
→ apply_database_migrations
→ optionally_start
→ verify_health
→ write_completion_record
```

Each stage must declare:

- required inputs;
- generated outputs;
- whether it is repeatable;
- whether it changes secrets;
- whether it requires Docker or network access;
- rollback behavior;
- resume marker.

### State persistence

Store non-secret onboarding progress in the state directory. Do not store plaintext passwords, API keys, or generated secret values in resume metadata.

Resume records should include:

- schema version;
- installation/config paths;
- completed stages;
- selected profiles;
- pending stage;
- last failure code and remediation;
- configuration transaction or staging identifier.

### Idempotency requirements

- Re-running onboarding on a completed installation defaults to reconfiguration mode.
- Existing secrets are preserved unless a rotate option is selected.
- Existing provider definitions are preserved unless explicitly replaced.
- Existing custom YAML fields are not discarded.
- `--reset` requires explicit confirmation or a non-interactive force flag.

## Phase 2.2 — Deployment profiles

### Required profiles

#### `docker-local`

- bind public entry point to localhost;
- use Compose-managed service names for Redis;
- use repository or installed Compose manifests;
- allow local/demo defaults where safe;
- print Docker-specific Ollama and EggPool endpoint guidance.

#### `docker-lan`

- bind to a configurable LAN interface or all interfaces;
- require explicit allowed origin/site URL handling;
- require strong admin credentials and generated secrets;
- warn about absent TLS or outer authentication.

#### `reverse-proxy`

- application remains behind an operator-managed proxy;
- collect public site URL and trusted proxy/origin values;
- avoid pretending to configure nginx, Caddy, firewall, or TLS automatically;
- print required proxy headers and health endpoints.

#### `bare-metal`

- support existing `uv`-based development/operator path;
- detect Python, `uv`, and Redis;
- do not attempt broad cross-platform service management in Release 2;
- provide start commands or a limited foreground driver.

#### `custom`

- expose advanced values while retaining validation.

### Profile implementation

Profiles should be typed overlays applied through the Release 1 transaction engine. They must not be separate permanent configuration formats. The resulting files remain ordinary supported `.env` and YAML.

### Tests

- profile overlay produces expected values;
- applying a profile twice is idempotent;
- custom operator values are not overwritten without confirmation;
- production profiles reject placeholder or weak secrets;
- profile transition reports affected components and restart impact.

## Phase 2.3 — Secret and administrator setup

### Required generated values

- Flask/session `SECRET_KEY`;
- `CELERY_TASK_SECRET`;
- administrator password hash;
- any additional application signing or encryption values classified by Release 1.

Use `secrets.token_hex()` or equivalent CSPRNG primitives. Use the application's supported password hashing implementation directly rather than shelling out to `scripts/hash_password.py`.

### Input handling

Interactive password entry must:

- disable echo;
- require confirmation;
- reject blank and known placeholder values;
- enforce a documented minimum policy;
- avoid retaining plaintext after hashing.

Non-interactive bootstrap must accept password and API key references through environment variable names or file/stdin references, not embedded plaintext by default.

Example:

```yaml
admin:
  username: admin
  password_env: AINEWS_BOOTSTRAP_ADMIN_PASSWORD
```

### Rotation options

Support explicit options such as:

```text
--rotate-admin-password
--rotate-application-secrets
--rotate-all-secrets
```

Rotation must report impact. Rotation of secrets used for existing sessions, encrypted records, webhooks, or signed tasks must be blocked or carefully migrated if compatibility cannot be preserved.

## Phase 2.4 — Declarative bootstrap schema

### Schema

Define a versioned Pydantic model, for example:

```yaml
version: 1

deployment:
  profile: docker-local
  port: 5000
  site_url: http://localhost:5000

admin:
  username: admin
  password_env: AINEWS_BOOTSTRAP_ADMIN_PASSWORD

provider:
  type: eggpool
  id: eggpool
  base_url: http://eggpool:11300/v1
  api_key_env: EGGPOOL_API_KEY
  default_model: auto

pipeline:
  profile: balanced

sources:
  profile: ai-general

newsletter:
  enabled: false

start: true
```

### Required behavior

- Reject unknown schema versions.
- Reject embedded sensitive fields unless an explicit opt-in policy exists.
- Resolve environment references at execution time.
- Validate all required inputs before mutating the installation.
- Support `--dry-run` with redacted planned changes.
- Provide deterministic non-interactive failures with stable exit codes.

### Commands

```bash
ainews onboard --config-file bootstrap.yaml
ainews onboard --non-interactive --config-file bootstrap.yaml
ainews onboard --dry-run --config-file bootstrap.yaml
```

## Phase 2.5 — Pipeline and source profiles

### Pipeline profiles

#### `lightweight-local`

- local-provider-oriented defaults;
- conservative concurrency;
- smaller output limits;
- bounded research and writing timeouts;
- minimal optional subagent work where appropriate.

#### `balanced`

- current production-like defaults;
- moderate concurrency and token limits;
- all core stages enabled.

#### `quality`

- larger research/writer budgets;
- quality-oriented model assignment prompts;
- explicit warning about increased latency and cost.

#### `low-cost`

- smaller model assignments where selected provider supports them;
- lower concurrency and token ceilings;
- no claim of exact cost savings without current authoritative pricing.

#### `custom`

- preserve current values and prompt for individual stage assignments.

### Source profiles

- `minimal`;
- `ai-general`;
- `ai-security`;
- `comprehensive`;
- `existing-defaults`;
- `custom`.

Profiles should use repository-owned templates with schema versioning. Applying a profile should produce a redacted diff and preserve operator-added sources unless replacement is explicitly requested.

## Phase 2.6 — Provider adapter protocol

### Interface

Define a provider onboarding adapter with methods equivalent to:

```python
class ProviderSetupAdapter(Protocol):
    type_id: str
    display_name: str

    def fields(self) -> list[ProviderInputField]: ...
    def normalize_endpoint(self, context, values) -> ProviderEndpoint: ...
    def build_definition(self, values) -> ProviderDefinition: ...
    def probe(self, definition, credentials) -> ProviderProbeResult: ...
    def discover_models(self, definition, credentials) -> ModelDiscoveryResult: ...
    def remediation(self, error) -> list[str]: ...
```

Adapters must separate configuration generation from network calls so dry-run and offline validation remain possible.

### Shared requirements

- bounded connect/read/total timeouts;
- sanitized errors;
- no authorization header logging;
- model discovery result limits and normalization;
- clear distinction between authentication failure, endpoint failure, unsupported discovery, and empty catalog;
- Docker-context endpoint diagnostics;
- deterministic test doubles.

## Phase 2.7 — Built-in provider adapters

### Ollama

- default endpoint outside Docker: `http://localhost:11434`;
- detect Docker deployment and recommend/normalize `host.docker.internal` where supported;
- optionally support a Compose-managed Ollama service name;
- probe version/tags endpoint;
- discover installed models;
- clearly report when no models are pulled.

### OpenAI

- default official base URL;
- hidden API key input;
- authentication probe with minimal side effects;
- model discovery with normalization and configurable exposure filtering.

### Anthropic

- official base URL and credential handling;
- probe using supported low-cost metadata or minimal request behavior;
- model discovery may use a maintained catalog if upstream discovery is unavailable, but must identify catalog provenance and age.

### Google Gemini

- API key handling;
- model listing where supported;
- normalize model IDs used by current adapter code.

### Generic OpenAI-compatible

- base URL prompt;
- optional API key;
- `/v1/models` discovery with configurable path fallback;
- compatibility warning that model listing does not prove chat/tool/schema support.

### EggPool

Treat EggPool as a first-class OpenAI-compatible integration.

Required behavior:

- prompt for endpoint and API key if configured;
- probe liveness/readiness endpoints where available;
- query `/v1/models`;
- support `auto` or explicit model assignment according to current ainews provider schema;
- warn when `localhost` points to the ainews container rather than the EggPool host;
- provide common endpoint presets for same-Compose-network, host service, and LAN service deployments;
- preserve the distinction between EggPool account/provider health and ainews's single upstream provider definition.

## Phase 2.8 — Provider commands

### `ainews providers list`

Show provider ID, type, endpoint, enabled status, credential configured status, default status, pipeline roles, and last probe summary. Never show credentials.

### `ainews providers add`

Interactive or flag-driven adapter flow. Required sequence:

```text
collect values
→ normalize endpoint
→ securely collect/store credential reference
→ stage provider definition
→ optionally probe
→ discover models
→ optionally assign pipeline roles
→ validate complete configuration
→ show redacted diff
→ commit transaction
```

Default behavior should require a successful probe when the network is available. Provide `--skip-probe` for intentionally offline setup with an explicit warning.

### `ainews providers test [ID]`

Run bounded provider and model checks. Support `--json`. Results should include endpoint resolution, authentication, model discovery status, latency, and remediation.

### `ainews providers models ID`

List discovered or configured models and indicate discovery provenance and timestamp.

### `ainews providers set-default ID`

Update default-provider references transactionally and validate affected pipeline settings.

### `ainews providers assign ID MODEL [ROLES...]`

Assign provider/model pairs to one or more pipeline roles. Reject unknown roles and report restart impact.

### `ainews providers remove ID`

Block removal while the provider is referenced. Support explicit reassignment to another provider in the same transaction.

## Phase 2.9 — Interactive onboarding UI

### Prompt behavior

- Use clear defaults derived from detected environment.
- Show one conceptual decision at a time.
- Do not ask operators for every low-level pipeline value.
- Mark optional sections clearly.
- Allow backtracking before commit where the prompt framework supports it.
- Display a final redacted summary and require confirmation before applying.

### Final summary

On successful completion, print:

- dashboard URL;
- admin username;
- deployment profile;
- provider and selected models;
- configuration and data paths;
- service status;
- health result;
- next commands: status, logs, doctor, provider test.

Do not print passwords or API keys.

### Failure behavior

- Preserve staging state for resumable failures where safe.
- Print exact resume command.
- Distinguish configuration, prerequisite, connectivity, migration, startup, and health failures.
- Never claim completion if startup or readiness verification failed.

## Phase 2.10 — Lifecycle driver abstraction

### Interface

Define a driver abstraction for:

```python
start()
stop()
restart()
status()
logs()
health()
smoke()
```

Implement `DockerComposeDriver` as the fully supported Release 2 production driver. A limited `BareMetalDriver` may support foreground development commands but should not pretend to manage durable services.

### Compose resolution

The driver must use resolved install paths and explicit Compose project naming. It must not depend on current working directory.

It should know whether production overlays are required and validate the rendered Compose configuration before startup.

## Phase 2.11 — Lifecycle commands

### `ainews start`

Required sequence:

1. load and validate configuration;
2. run relevant doctor prerequisites;
3. validate Compose configuration;
4. run database migrations unless disabled;
5. start services;
6. wait for bounded liveness and readiness;
7. check Celery worker availability;
8. print dashboard URL and degraded warnings.

Support:

```text
--skip-doctor
--skip-migrations
--no-wait
--timeout SECONDS
--json
```

Skipping safety checks must be explicit and visible.

### `ainews stop`

Stop only the resolved ainews deployment. Do not remove volumes by default.

### `ainews restart`

Perform a full restart. Do not label it as configuration reload. Validate configuration before stopping the healthy deployment so a broken edit does not unnecessarily take the service down.

### `ainews status`

Combine:

- Compose service state;
- liveness and readiness;
- database accessibility;
- Redis connectivity;
- Celery worker status;
- pending migration status;
- configured provider summary;
- URL and port information.

### `ainews logs`

Support service selection, tail count, follow/no-follow, timestamps, and raw passthrough where needed.

### `ainews health`

Probe public and admin health endpoints with bounded timeouts. Distinguish authentication-required endpoints from failure.

### `ainews smoke`

Run a post-deploy smoke sequence equivalent to the existing release smoke expectations without rebuilding or destructively resetting the installation unless explicitly requested.

## Phase 2.12 — Runtime/network doctor expansion

Add checks for:

- Redis connection and database selection;
- database open/write/migration state;
- Flask/ASGI liveness;
- readiness;
- Celery workers;
- provider authentication;
- selected model availability;
- SMTP connectivity when configured;
- representative source connectivity when requested;
- Docker DNS and host endpoint resolution;
- configured port conflicts;
- Compose service health.

Commands:

```bash
ainews doctor --quick
ainews doctor --production
ainews doctor --network
ainews doctor --json
```

Network checks must be opt-in or clearly identified because they may contact external providers.

## Phase 2.13 — Database migration integration

Use existing Flask-Migrate/Alembic infrastructure through a dedicated library function or controlled subprocess.

Requirements:

- detect pending migrations;
- support a dry-run/status mode;
- run before service readiness is declared;
- abort startup on migration failure;
- avoid concurrent migration execution through a lock;
- include migration state in `status` and `doctor`.

Release 2 does not need full data backup/restore, but startup should warn operators that major migration protection arrives in the later backup release.

## Phase 2.14 — Test strategy

### Onboarding tests

- fresh interactive Docker-local flow;
- scripted prompt flow;
- declarative non-interactive flow;
- missing bootstrap environment variables;
- dry-run with no writes;
- interruption and resume;
- reconfiguration without secret rotation;
- explicit reset;
- failed provider probe;
- failed migration;
- failed startup;
- readiness timeout;
- custom field preservation.

### Provider tests

For every adapter:

- field validation;
- endpoint normalization;
- credential redaction;
- success probe;
- authentication failure;
- timeout;
- malformed response;
- empty model catalog;
- model normalization;
- Docker localhost warning.

EggPool and Ollama require dedicated container-context tests.

### Lifecycle tests

- commands outside repository root;
- rendered Compose validation;
- start healthy stack;
- stop without volume deletion;
- restart validates before stopping;
- partial service failure;
- missing worker;
- Redis failure;
- migration failure;
- bounded readiness timeout;
- status human/JSON parity;
- log service selection.

### Security tests

- password/API key absent from onboarding state;
- secret absent from command output and exceptions;
- bootstrap embedded-secret rejection;
- authorization headers not logged;
- provider error body sanitization;
- restrictive file permissions after onboarding.

## Phase 2.15 — Documentation

Add or update:

- `docs/onboarding.md`;
- `docs/providers.md` with CLI-first examples;
- `docs/deployment.md` with lifecycle commands;
- `docs/automation.md` for bootstrap schema;
- `docs/troubleshooting.md` for provider and Compose networking;
- `docs/cli-reference.md`;
- README quick start showing `uv tool install` or current package installation followed by `ainews onboard`, while reserving the curl installer for Release 3.

Include explicit examples for:

- local Ollama outside Docker;
- Ollama in Compose;
- EggPool on the same Docker network;
- EggPool on a LAN host;
- OpenAI and Anthropic;
- reverse-proxy deployment;
- unattended setup.

## Suggested commit sequence

1. `feat(onboard): add onboarding state machine and bootstrap schema`
2. `feat(onboard): add deployment, pipeline, and source profiles`
3. `feat(onboard): add secure admin and secret setup`
4. `feat(providers): add provider setup protocol and common probes`
5. `feat(providers): add Ollama and OpenAI-compatible adapters`
6. `feat(providers): add OpenAI, Anthropic, and Gemini adapters`
7. `feat(providers): add first-class EggPool integration`
8. `feat(cli): add provider administration commands`
9. `feat(onboard): add interactive and non-interactive orchestration`
10. `feat(lifecycle): add Docker Compose driver`
11. `feat(cli): add start, stop, restart, status, and logs`
12. `feat(cli): add health, smoke, and network doctor checks`
13. `feat(db): integrate migration status and startup migration`
14. `test(cli): add onboarding, provider, and lifecycle failure coverage`
15. `docs(cli): document Release 2 first-run and operations workflows`

## Release 2 completion gate

Release 2 is complete only when:

- a fresh Docker installation can be configured without manual file editing;
- administrator credentials and required secrets are generated or securely supplied;
- interactive and declarative onboarding produce equivalent valid configuration;
- interrupted onboarding can resume without leaking secrets;
- Ollama, EggPool, and at least one direct cloud provider are configurable through the CLI;
- provider setup tests authentication before commit by default;
- model discovery and pipeline assignment are transactional;
- provider removal cannot leave dangling pipeline references;
- `start` validates configuration before changing runtime state;
- `restart` refuses broken configuration before stopping a healthy deployment;
- status reports web, Redis, database, Celery, migration, and provider state;
- all network operations are bounded and produce sanitized diagnostics;
- lifecycle commands work outside the repository checkout;
- existing manual Docker and bare-metal workflows remain functional;
- Ruff, Mypy, unit tests, integration tests, Docker smoke tests, and release validation pass.
