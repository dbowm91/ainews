# ainews Configuration and Operator CLI — Release 4B Backup, Restore, and Migrations

## Objective

Establish the recovery foundation required before updates are allowed. Add versioned backups with manifests and integrity verification, selective and full restore, compatibility checks, and explicit schema migration hooks for configuration and application data.

## Command surface

```bash
ainews backup create
ainews backup list
ainews backup show BACKUP_ID
ainews backup verify BACKUP_ID
ainews backup prune
ainews restore BACKUP_ID
ainews restore BACKUP_ID --config-only
ainews restore BACKUP_ID --data-only
ainews migrations status
ainews migrations plan
ainews migrations apply
```

## Workstream 1 — Backup scope and manifest

Define a versioned backup format containing independently identifiable sections:

- configuration files;
- install metadata and schema metadata;
- application database;
- selected mutable application data;
- operational metadata required for restore;
- optional logs only when explicitly requested.

Do not include:

- immutable application artifacts by default;
- caches that can be regenerated;
- temporary files;
- live sockets/PIDs;
- plaintext secrets outside their existing protected config files.

Example manifest fields:

```json
{
  "schema_version": 1,
  "backup_id": "2026-07-15T041500Z-1.4.0",
  "created_at": "...",
  "application_version": "1.4.0",
  "config_schema_version": "1.0.0",
  "database_schema_version": "...",
  "source_install": {"channel": "stable", "commit": "..."},
  "sections": [
    {"name": "config", "path": "config.tar", "sha256": "...", "size": 1234},
    {"name": "database", "path": "database.sqlite", "sha256": "...", "size": 5678}
  ]
}
```

## Workstream 2 — Consistent snapshot creation

Backups must be internally consistent.

Requirements:

- acquire an application-level backup lock;
- coordinate with configuration transactions;
- use SQLite online backup API or an equivalent consistent database snapshot, not a raw copy of an active WAL database;
- capture config only after successful parse and validation unless an explicit recovery mode is used;
- flush or record pending migration/update state;
- stage backup contents in a private temporary directory;
- calculate section checksums before finalization;
- atomically publish the completed backup directory/archive;
- write restrictive permissions;
- clean incomplete backups or mark them as incomplete and non-restorable.

Define bounded behavior when workers are active. Prefer online-safe snapshotting; otherwise perform a controlled quiesce through lifecycle abstractions.

## Workstream 3 — Backup verification

`ainews backup verify` must validate:

- manifest schema;
- expected section presence;
- file sizes and SHA-256 values;
- safe archive paths and link targets;
- SQLite integrity checks;
- YAML/dotenv parseability;
- configuration cross-file validation;
- application/config/database version compatibility;
- secret-file permissions after extraction to a temporary validation root.

Verification must not modify live state.

Return stable reason codes for malformed manifest, checksum mismatch, incompatible version, database corruption, unsafe archive member, and invalid configuration.

## Workstream 4 — Retention and pruning

Support policy-driven pruning:

- maximum count;
- maximum age;
- optional maximum total bytes;
- preserve named/pinned backups;
- never delete the only verified backup before a destructive operation;
- dry-run preview;
- deterministic oldest-first selection;
- audit record of deleted backup IDs.

Default retention should be conservative and documented.

## Workstream 5 — Restore planning

Before writing, build a restore plan showing:

- sections to restore;
- current versus backup application and schema versions;
- required migrations or downgrades;
- paths affected;
- services that must stop or quiesce;
- secrets and permissions impact;
- estimated restart actions;
- whether rollback is possible.

`--dry-run` must generate the complete plan without modifying live state.

Refuse unsupported cross-version restores rather than guessing.

## Workstream 6 — Transactional restore

Restore must:

1. verify the backup;
2. acquire restore/config/update locks;
3. stop or quiesce affected services through lifecycle drivers;
4. create an automatic pre-restore safety backup unless explicitly impossible;
5. stage restored files outside live paths;
6. validate staged config and database;
7. atomically replace configuration where possible;
8. replace database/data using a documented rollback strategy;
9. apply required forward migrations only when supported;
10. restore permissions and ownership;
11. start services and run health/smoke checks;
12. roll back on failed validation or health checks;
13. write a restore record.

Partial restores must preserve consistency. For example, config-only restore must reject references incompatible with the live provider/database state.

## Workstream 7 — Migration framework

Create explicit versioned migration interfaces for:

- configuration schema;
- install metadata schema;
- backup manifest schema readers;
- database schema integration with the existing migration mechanism.

Recommended contract:

```python
class Migration(Protocol):
    id: str
    from_version: str
    to_version: str
    reversible: bool

    def preflight(self, context) -> MigrationReport: ...
    def apply(self, staging_root, context) -> MigrationReport: ...
    def rollback(self, staging_root, context) -> MigrationReport: ...
```

Requirements:

- deterministic ordering;
- idempotency or explicit already-applied detection;
- checksummed migration identity;
- no network dependency;
- redacted logs;
- preflight before mutation;
- migration plan output;
- documented minimum supported source version;
- downgrade refusal unless a tested reverse migration exists.

## Workstream 8 — Tests

Add real-filesystem and SQLite integration tests for:

- active WAL database snapshot consistency;
- config mutation concurrent with backup locking;
- checksum mismatch;
- corrupted SQLite database;
- incomplete backup publication;
- retention and pinned backups;
- restore dry-run;
- config-only and full restore;
- failed health check rollback;
- interrupted restore recovery;
- permission restoration;
- migration ordering and idempotency;
- unsupported downgrade refusal;
- secret-free logs and JSON.

Maintain fixtures for at least the current schema and one prior supported schema.

## Documentation

Document:

- exact backup contents;
- secret implications and permissions;
- retention defaults;
- restore compatibility matrix;
- disaster-recovery steps;
- manual offline verification;
- migration support window;
- recovery from interrupted restore.

## Acceptance criteria

- backups use consistent database snapshots and validated config;
- every backup has a versioned manifest and per-section checksums;
- verification is non-mutating and catches corruption/unsafe paths;
- restore provides a complete dry-run plan;
- full restore automatically creates a safety backup when possible;
- failed post-restore validation or health checks roll back;
- migrations are explicit, ordered, tested, and compatibility-aware;
- backup/restore JSON output is stable and secret-free;
- updates remain blocked until these acceptance criteria are met.
