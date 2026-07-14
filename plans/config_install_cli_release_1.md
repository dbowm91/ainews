# ainews Configuration and Operator CLI — Release 1 Detailed Plan

## Release objective

Release 1 creates the configuration and CLI substrate required by onboarding, provider management, lifecycle commands, and the installer. It must not attempt to deliver a polished first-run wizard. Its job is to establish one authoritative configuration model and prove that configuration can be inspected and changed safely from outside the repository checkout.

## User-visible result

```bash
ainews version
ainews config path
ainews config show
ainews config check
ainews config get pipeline.writer.model
ainews config set pipeline.writer.model qwen3:8b
ainews config unset smtp.password
ainews config diff
ainews config rollback
ainews doctor
```

## Non-goals

- one-shot installer;
- provider account wizard;
- start/stop lifecycle management;
- source and topic administration;
- live configuration reload;
- replacement of YAML or dotenv with a database;
- broad configuration redesign unrelated to operator ergonomics.

## Phase 1.1 — Repository configuration inventory

### Tasks

1. Enumerate every environment variable read by application, Celery, scripts, Compose files, tests, and documentation.
2. Enumerate all fields in `providers.yaml`, `pipeline.yaml`, `sources.yaml`, and `topics.yaml`.
3. Record loaders, defaults, caches, and startup validators for each surface.
4. Identify cross-file references:
   - default provider to provider ID;
   - pipeline role provider to provider ID;
   - pipeline role model to provider/model availability;
   - source topic references to topic IDs;
   - theme defaults to registry IDs;
   - process-level environment variables consumed by Flask and Celery.
5. Classify each value as secret, sensitive, public, generated, derived, or deprecated.
6. Record whether changes require Flask restart, Celery restart, scheduler restart, or no runtime action.
7. Identify duplicate or divergent parsing code, especially in `config.py`, `services/config_unified.py`, schema loaders, scripts, and tests.

### Deliverable

Create `docs/configuration-contract.md` containing a machine-oriented table with:

```text
canonical key
physical destination
serialized path or environment variable
Python type
required profiles
default source
secret classification
restart impact
validator
consumers
deprecation status
```

### Acceptance criteria

- No currently supported production setting is omitted.
- Every direct `os.environ` or dotenv access is either represented or explicitly classified as internal/development-only.
- Cross-file dependencies are documented before the validator refactor begins.

## Phase 1.2 — Canonical path resolver

### Tasks

Implement a pure-Python path model that does not require Flask initialization.

Required resolved paths:

- application/install directory;
- config directory;
- data directory;
- state directory;
- backup directory;
- `.env`;
- `providers.yaml`;
- `pipeline.yaml`;
- `sources.yaml`;
- `topics.yaml`;
- SQLite database path when locally managed;
- install metadata path;
- transaction lock and staging paths.

Required precedence:

```text
explicit command option
→ environment override
→ install metadata
→ platform canonical location
→ repository-local compatibility location in development mode
```

Implement immutable models such as `ResolvedPaths` and `PathProvenance`. Do not scatter `Path.cwd()` or repository-root assumptions through command code.

### Compatibility behavior

Repository-local files remain supported for development. Production commands should emit a migration warning when they are using repository-local compatibility paths without recorded install metadata.

### Tests

- explicit path wins;
- environment override wins over metadata;
- metadata wins over platform default;
- development compatibility fallback;
- paths containing spaces;
- symlinked install directory;
- missing directories;
- commands invoked from unrelated working directories;
- user and system installation layouts.

### Acceptance criteria

`ainews config path` can later be implemented entirely from this resolver without importing Flask.

## Phase 1.3 — Configuration field registry

### Tasks

Create a typed field registry covering operator-supported keys. Each entry should expose:

- canonical key;
- destination file;
- nested serialization path;
- type parser;
- nullable and required status;
- default information;
- secret classification;
- restart impact;
- validation hooks;
- human description;
- aliases and deprecated names.

Avoid trying to expose every low-level internal value through `config set` immediately. Fields may be marked read-only or advanced.

Example:

```python
ConfigField(
    key="newsletter.timezone",
    destination=ConfigFile.PIPELINE,
    path=("newsletter", "timezone"),
    parser=parse_timezone,
    secret=False,
    restart_impact={RuntimeComponent.WEB, RuntimeComponent.WORKER},
)
```

### Required initial namespaces

- `server.*`;
- `database.*`;
- `redis.*`;
- `admin.*`;
- `smtp.*`;
- `providers.*` for inspectable common fields;
- `pipeline.*` and `newsletter.*`;
- `safe_fetch.*`;
- `themes.*`.

Source and topic object mutation can remain deferred, but their files must still be loaded and validated.

### Acceptance criteria

- Registry keys are unique.
- Aliases resolve deterministically.
- Secret fields are explicitly marked.
- Generated documentation can be produced from registry metadata.

## Phase 1.4 — Shared configuration loader and effective model

### Tasks

Create a configuration library independent of CLI rendering and Flask request context.

The loader must:

1. resolve paths;
2. parse dotenv without silently discarding malformed lines;
3. parse all YAML surfaces;
4. resolve supported environment references;
5. validate individual Pydantic models;
6. construct an effective configuration view;
7. retain per-value provenance;
8. produce redacted and unredacted internal representations;
9. report all independent errors in one pass where safe.

Suggested result model:

```python
EffectiveConfiguration(
    paths=resolved_paths,
    environment=...,
    providers=...,
    pipeline=...,
    sources=...,
    topics=...,
    provenance=...,
    diagnostics=...,
)
```

### Error taxonomy

Define structured errors for:

- missing file;
- malformed dotenv;
- malformed YAML;
- schema violation;
- missing secret reference;
- invalid cross-file reference;
- unsafe file permissions;
- unsupported schema version;
- deprecated field;
- production-policy violation.

Each diagnostic should include severity, code, file, canonical key when known, message, and remediation.

### Compatibility

Preserve current application defaults unless the existing behavior is unsafe or internally inconsistent. Any intentional semantic correction must be isolated and documented rather than hidden in the refactor.

## Phase 1.5 — Cross-file semantic validator

### Required validations

- configured default provider exists and is enabled;
- every pipeline role references an existing enabled provider;
- provider credential references resolve where required;
- duplicate provider IDs are rejected;
- source IDs are unique;
- topic IDs are unique;
- source topic references exist;
- pipeline concurrency, token, timeout, and schedule values satisfy current schema bounds;
- newsletter timezone is valid;
- production database and Redis settings are present;
- Redis broker and result backend configuration is coherent;
- required production secrets meet length and placeholder policies;
- admin password is a supported hash, not plaintext;
- theme configuration remains compatible with the existing theme registry contract;
- unsafe-fetch limits remain within supported ranges.

Separate offline validation from external probes. `config check` must not require provider, SMTP, or Redis connectivity.

### Acceptance criteria

Application startup and CLI validation call the same semantic validator.

## Phase 1.6 — Transactional configuration writer

### Tasks

Implement a transaction abstraction supporting one or more changed files.

Required sequence:

1. acquire an exclusive configuration lock;
2. snapshot source file metadata and content hashes;
3. create staging copies in the same filesystem where possible;
4. apply typed mutations;
5. serialize files;
6. reload staged files through the canonical loader;
7. validate the complete staged configuration;
8. generate a redacted diff;
9. fsync temporary files where supported;
10. atomically replace changed files;
11. write a bounded rollback snapshot and manifest;
12. release the lock.

### Serialization requirements

- Preserve YAML ordering and comments where feasible using a round-trip parser.
- Preserve unrelated dotenv entries and comments.
- Use stable newline and encoding behavior.
- Never write secrets with broad permissions.
- Never overwrite a file changed externally after the transaction began; detect content-hash mismatch and abort.

### Failure tests

- validation failure;
- serialization failure;
- permission error;
- disk-full simulation where feasible;
- failure after one temporary file is written;
- external concurrent modification;
- stale lock recovery;
- interrupted rollback creation.

### Acceptance criteria

Any failed transaction leaves original configuration files byte-for-byte unchanged.

## Phase 1.7 — CLI package and command framework

### Tasks

Add to `pyproject.toml`:

```toml
[project.scripts]
ainews = "ainews_cli.main:app"
```

Implement `ainews_cli` with:

- global context;
- global path overrides;
- `--verbose`, `--quiet`, `--no-color`, and `--json`;
- version output;
- stable exit codes;
- human and JSON renderers;
- exception-to-result mapping;
- no Flask initialization at import time.

### Required commands

#### `ainews version`

Show package version, commit where available, configuration schema version, and install channel metadata.

#### `ainews config path`

Show every resolved path and provenance. Include existence and writability status without creating files.

#### `ainews config show`

Show effective values and provenance. Secrets are redacted. A dangerous `--show-secrets` option should not be introduced in Release 1 unless there is a concrete operational requirement and explicit confirmation mechanism.

#### `ainews config check`

Run offline syntax, schema, semantic, permission, and production-policy checks. Support `--production` and `--json`.

#### `ainews config get KEY`

Return a typed value with secrets redacted or reported as configured/unconfigured.

#### `ainews config set KEY VALUE`

Parse through the registry, stage the change, validate, display impact, and commit. Support `--dry-run`.

#### `ainews config set-secret KEY --stdin`

Read sensitive values from standard input or a hidden prompt. Do not recommend plaintext command arguments.

#### `ainews config unset KEY`

Remove an optional override or restore default behavior. Reject removal of required values unless explicitly operating on an incomplete staging configuration.

#### `ainews config diff`

Compare effective configuration with packaged defaults or a named rollback snapshot. Redact secrets.

#### `ainews config rollback`

List and restore bounded transaction snapshots through the same validation and transaction machinery.

## Phase 1.8 — Initial doctor command

Release 1 doctor is offline/host-focused. It should check:

- package and schema versions;
- resolved paths;
- directory existence and permissions;
- configuration validity;
- secret file permissions;
- Docker and Compose availability;
- Python and `uv` availability for bare-metal development;
- configured port availability when services are stopped;
- database directory writability;
- obvious placeholder values.

Network and runtime health checks are deferred to Release 2.

## Phase 1.9 — Runtime integration

### Tasks

Migrate Flask and Celery startup to the shared loader incrementally.

Required constraints:

- no request-context dependency;
- no change to current public configuration semantics without an explicit migration note;
- cache invalidation remains correct;
- test fixtures can inject isolated resolved paths;
- startup failures use structured diagnostics and still produce readable logs.

Retire or reduce duplicate functions in `services/config_unified.py` only after all consumers have moved. Keep compatibility wrappers temporarily when needed, with deprecation comments and tests.

### Acceptance criteria

- `config check` and application startup agree on valid/invalid fixtures.
- Flask and Celery resolve the same files.
- Existing release validation remains green.

## Phase 1.10 — Documentation and tests

### Documentation

Add or update:

- `docs/configuration-contract.md`;
- `docs/cli-reference.md` for Release 1 commands;
- `docs/configuration.md` with canonical path and precedence sections;
- `docs/troubleshooting.md` for structured configuration errors;
- README note describing the new CLI as available but not yet the complete installer path.

### Required test groups

- field registry tests;
- path resolution tests;
- effective configuration fixtures;
- cross-file validation fixtures;
- transaction and rollback tests;
- CLI command tests through Typer's test runner;
- JSON output snapshots or schema assertions;
- secret redaction tests across output, logs, exceptions, and diffs;
- runtime/CLI validator parity tests;
- commands invoked outside repository root.

## Suggested commit sequence

1. `docs(config): inventory configuration contract and path policy`
2. `feat(config): add canonical path resolver and field registry`
3. `feat(config): add shared loader, provenance, and diagnostics`
4. `feat(config): add cross-file semantic validation`
5. `feat(config): add transactional writer and rollback snapshots`
6. `feat(cli): add ainews entry point and output contracts`
7. `feat(cli): add configuration inspection and mutation commands`
8. `feat(cli): add offline doctor checks`
9. `refactor(config): migrate Flask and Celery to shared loader`
10. `test(config): add parity, redaction, and failure-path coverage`
11. `docs(cli): document Release 1 operator commands`

Commits may be split further, but configuration engine and CLI presentation changes should remain reviewable independently.

## Release 1 completion gate

Release 1 is complete only when:

- `ainews` installs as a console command through the Python package;
- all commands work outside the repository directory;
- `config check` and runtime startup share validation code;
- all supported settings have path, type, provenance, secret, and restart metadata;
- `config set` and `unset` are transactional;
- failed writes preserve original files;
- secret values are absent from standard output, JSON, logs, and diffs;
- rollback snapshots can be listed and restored;
- existing Docker and developer setup paths remain functional;
- Ruff, Mypy, unit tests, configuration integration tests, and release-fast validation pass.
