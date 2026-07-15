# ainews Configuration and Operator CLI — Release 4D Service Manager and Logrotate

## Objective

Provide supported service-manager and log-rotation integration for installed ainews deployments. Generate systemd units and logrotate policy from canonical resolved paths, install them only through explicit operator action, and route service lifecycle through the existing `ainews` CLI rather than duplicating application startup logic.

## Command surface

```bash
ainews service render --systemd
ainews service install --systemd
ainews service validate
ainews service status
ainews service restart
ainews service remove

ainews logs configure-rotation
ainews logs validate-rotation
ainews logs remove-rotation
```

System-level operations must clearly distinguish user services from system services.

## Workstream 1 — Service deployment model

Define supported service topologies for the current application:

- Docker Compose project managed as a unit;
- bare-metal web process;
- bare-metal Celery worker;
- optional scheduler/beat process where applicable;
- Redis remains external or Compose-managed according to deployment profile.

Prefer units that invoke stable CLI lifecycle commands or narrowly scoped wrappers, for example:

```text
ExecStart=/usr/local/bin/ainews start --no-wait
ExecStop=/usr/local/bin/ainews stop
ExecReload=/usr/local/bin/ainews config check
```

Only use this pattern when command behavior is suitable for systemd supervision. If `ainews start` daemonizes or returns before the managed process is trackable, generate units for the actual foreground process or Compose integration instead. Document and test the supervision contract.

## Workstream 2 — Typed unit specification

Represent generated service definitions through typed models rather than string concatenation spread across commands.

Model:

- unit name and description;
- user/system scope;
- dependencies and ordering;
- working directory;
- executable and arguments;
- environment file path;
- restart policy;
- timeouts;
- hardening directives;
- log destination;
- install target;
- deployment profile compatibility.

Render templates deterministically and include a generator/version comment.

## Workstream 3 — Path and identity resolution

Use install metadata and canonical path resolution for:

- application root;
- CLI executable;
- config directory;
- environment file;
- data/state/log directories;
- Compose file and project name;
- service user/group.

Reject unresolved, relative, newline-containing, or unsafe paths. Do not trust arbitrary path values from mutable metadata without ownership and root-boundary validation.

For system services:

- require explicit root privilege only for installation/removal;
- do not run the application as root;
- require or create no users automatically unless a separate explicit policy is implemented;
- validate that the configured service identity can read config and write data/state/log paths.

For user services:

- install under the appropriate user systemd directory;
- use `systemctl --user`;
- document lingering/session requirements.

## Workstream 4 — systemd hardening

Apply defensible defaults compatible with application behavior:

- `NoNewPrivileges=true`;
- `PrivateTmp=true`;
- restrictive `UMask`;
- bounded restart policy and start-limit behavior;
- explicit `WorkingDirectory`;
- explicit writable paths;
- `ProtectSystem`/`ProtectHome` where compatible;
- capability bounding with no unnecessary capabilities;
- no secrets in `ExecStart` arguments;
- environment file permissions validated before install;
- network restrictions only when they do not break required provider/source access.

Every hardening directive must be tested against Docker and bare-metal profiles. Avoid cargo-cult directives that make the service unusable.

## Workstream 5 — Service rendering and validation

`ainews service render` should:

- produce files in a staging/output directory;
- show resolved paths and scope;
- support JSON metadata plus rendered text files;
- never install implicitly;
- support deterministic golden tests.

`ainews service validate` should run:

- internal model validation;
- path/permission checks;
- `systemd-analyze verify` when available;
- Compose configuration validation for Compose-backed units;
- environment file permission checks;
- executable existence checks;
- conflict detection with existing units.

A missing optional validator should be reported as `SKIP`, not pass.

## Workstream 6 — Installation, status, and removal

Installation sequence:

1. render to staging;
2. validate;
3. inspect existing units;
4. show diff and impact;
5. require confirmation;
6. write atomically with correct ownership/mode;
7. run daemon reload;
8. optionally enable/start only when requested;
9. run status and health checks;
10. record installed unit paths and hashes in state metadata.

Removal must:

- stop/disable only units recorded as owned by this installation;
- compare current file hashes and warn before deleting operator-modified units;
- run daemon reload;
- preserve application config/data;
- clean service state metadata transactionally.

`ainews service status/restart` should use the service manager when installed and fall back to the existing lifecycle driver otherwise, with clear reporting.

## Workstream 7 — Log ownership and destinations

Define logging behavior for each deployment profile:

- journald-only systemd services;
- file logs explicitly configured by the application;
- Docker logs managed by the container runtime;
- no duplicate rotation of journald or Docker-managed logs.

Do not generate logrotate rules for paths that are not actually used.

## Workstream 8 — Logrotate generation

For file-backed logs, generate rules with:

- explicit absolute paths;
- rotation frequency and size thresholds;
- retention count;
- compression and delayed compression;
- `missingok` and `notifempty` where appropriate;
- secure `create` mode/owner/group;
- no unsafe wildcards spanning unrelated files;
- postrotate action only when required and safe;
- deterministic generator comments and state metadata.

Support user-local rotation only if there is a tested mechanism; otherwise limit automatic installation to system logrotate and document user alternatives.

## Workstream 9 — Logrotate validation and ownership

Validate with `logrotate --debug` or equivalent when available. Detect:

- invalid syntax;
- inaccessible log paths;
- unsafe ownership or modes;
- duplicate/conflicting rules;
- rules for journald/Docker-only deployments;
- path traversal or newline injection.

Record installed file path and content hash. Removal must not delete an operator-modified rule without explicit confirmation.

## Workstream 10 — Tests

Add unit and integration tests for:

- deterministic unit rendering;
- user/system path resolution;
- unsafe path rejection;
- no secrets in rendered command lines;
- environment-file permission failures;
- hardening directives by profile;
- `systemd-analyze verify` result mapping;
- existing unit conflict and diff;
- install/enable/start sequence through fake `systemctl`;
- rollback after daemon-reload or start failure;
- modified-unit removal protection;
- journald versus file-log selection;
- deterministic logrotate rendering;
- logrotate validation result mapping;
- modified-rule removal protection;
- JSON and exit-code stability.

Where privileged CI is unavailable, use fake executables plus containerized validation. Add at least one real Linux service validation job when feasible.

## Documentation

Document:

- user versus system service installation;
- generated unit topology;
- service identity and permissions;
- hardening choices and limitations;
- interaction with Docker Compose;
- status/restart behavior;
- journald and file-log access;
- logrotate retention defaults;
- safe removal and modified-file handling;
- manual recovery after failed service installation.

## Acceptance criteria

- units are generated from typed models and canonical paths;
- service installation is explicit, staged, validated, and ownership-tracked;
- application processes do not run as root by default;
- secrets never appear in unit command lines or world-readable files;
- hardening directives are compatible with tested deployment profiles;
- service status/restart integrates with existing lifecycle abstractions;
- logrotate rules are generated only for real file-backed logs;
- modified units/rules are not silently overwritten or removed;
- generated files pass available native validators;
- tests cover failure rollback, permissions, conflicts, and deterministic output.
