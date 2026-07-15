# ainews Configuration and Operator CLI — Release 4 Detailed Plan

## Release objective

Release 4 completes routine day-two administration after the supported installer path is proven. It adds source, topic, and pipeline administration; OPML interoperability; backup, verification, restore, and schema migration; update and uninstall workflows; and service-manager/log-rotation integration.

Release 4 must preserve the architecture established in Releases 1–3:

- all configuration changes use the shared loader, validator, field registry, and transaction engine;
- backup and restore precede update;
- updates install immutable verified artifacts;
- uninstall preserves operator data by default;
- service definitions are generated from resolved canonical paths and validated before installation.

## User-visible result

```bash
ainews sources list
ainews sources add
ainews sources test
ainews sources import-opml subscriptions.opml
ainews sources export-opml subscriptions.opml

ainews topics list
ainews topics add "AI Safety"
ainews pipeline show
ainews pipeline assign writer openai:gpt-5

ainews backup create
ainews backup verify latest
ainews restore latest

ainews update check
ainews update apply
ainews uninstall

ainews service install --systemd
ainews service status
ainews service remove
```

## Release plan index

1. `plans/config_install_cli_release_4a_content_admin_and_opml.md`
   - source/topic/pipeline CRUD;
   - validation, probes, import/export, and restart-impact reporting.
2. `plans/config_install_cli_release_4b_backup_restore_and_migrations.md`
   - versioned backup manifests;
   - verification and restore;
   - schema migration hooks and rollback foundations.
3. `plans/config_install_cli_release_4c_update_and_uninstall.md`
   - channel-aware update checks and staged verified upgrades;
   - automatic pre-update backup and rollback;
   - conservative uninstall behavior.
4. `plans/config_install_cli_release_4d_service_manager_and_logrotate.md`
   - systemd unit generation and lifecycle integration;
   - logrotate generation;
   - validation and security hardening.

## Ordering constraints

The implementation order is mandatory:

```text
content administration
-> backup create/verify
-> restore
-> schema migrations
-> update check/apply/rollback
-> uninstall
-> systemd/logrotate integration
```

Update must not land before tested backup and restore. Service installation should target the final installed paths and lifecycle commands, not duplicate startup policy.

## Shared command requirements

Every mutating command must support:

- human-readable output;
- `--json` output with schema version;
- `--dry-run` where meaningful;
- redacted diff or impact summary;
- stable exit codes;
- transactional writes;
- non-interactive operation;
- explicit confirmation for destructive behavior;
- `--yes` or equivalent for automation;
- operation outside the repository checkout.

## Security requirements

- do not serialize provider credentials into OPML or ordinary exports;
- backup files containing secrets must use restrictive permissions;
- update artifacts require checksum verification and reuse Release 3 acquisition logic;
- restore must validate archive members and manifests before writing;
- uninstall must not delete data/config/backups without a separate explicit purge option;
- generated service units must not expose secrets on command lines or in world-readable environment files;
- migration scripts must be versioned, deterministic, and rollback-aware.

## Data ownership model

Classify paths as:

### Immutable application

- installed application artifacts;
- packaged defaults;
- templates and Compose manifests.

### Mutable configuration

- `.env`;
- providers, pipeline, sources, and topics YAML;
- install metadata and schema metadata.

### Mutable data

- database;
- generated reports/content;
- queues or local state where applicable.

### Operational state

- onboarding state;
- transaction manifests;
- PID/status files;
- update staging state;
- service installation records.

### Backups

- versioned archives/manifests;
- verification metadata;
- restore records.

All Release 4 commands must respect this classification.

## Test strategy

Release 4 requires:

- unit tests for command parsing and models;
- real-filesystem integration tests for mutations and restore;
- fixture-driven OPML tests;
- migration fixtures from prior schema versions;
- local artifact/update fixture servers;
- interrupted update and rollback tests;
- uninstall preservation tests;
- generated systemd/logrotate golden tests;
- clean-host service installation tests where CI permits.

## Release gates

Release 4 is complete only when:

- sources, topics, and pipeline can be administered without manual YAML editing;
- OPML import/export is idempotent and does not expose secrets;
- backups are versioned, verifiable, and restorable;
- restore can recover configuration and data after an interrupted mutation;
- schema migrations are explicit and tested from supported prior versions;
- updates perform verified staged installation with automatic pre-update backup;
- failed health validation rolls back to the previous application version and compatible data/config state;
- uninstall preserves config/data/backups by default;
- systemd and logrotate files are generated from canonical paths and pass validation;
- all command JSON contracts are tested;
- `docs/config-cli-release-4-closure.md` maps every gate to evidence.
