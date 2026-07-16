# Backup, Restore, and Migrations

This document covers the backup/restore system, migration framework, and disaster recovery procedures.

## Backup Contents

Each backup contains:

| Section | Contents | Required |
|---------|----------|----------|
| `config` | `.env`, `providers.yaml`, `pipeline.yaml`, `sources.yaml`, `topics.yaml` (tarball) | Yes |
| `database` | SQLite database via online backup API | No |
| `install_metadata` | Installation metadata JSON | No |

When `--include-logs` is used, log files from the `logs/` directory are added to the config tarball.

### What is NOT backed up

- Immutable application artifacts
- Caches that can be regenerated
- Temporary files
- Live sockets/PIDs
- `.agents/skills/` directory (symlinks, not tracked by git)

## Backup Format

Backups are stored as versioned directories:

```
backups/
  2026-07-15T041500Z-1.4.0/
    manifest.json
    config.tar
    database.sqlite
    install_metadata.json
  pins.json
  restore-records/
    restore-*.json
```

### Manifest schema

```json
{
  "schema_version": 1,
  "backup_id": "2026-07-15T041500Z-1.4.0",
  "created_at": "2026-07-15T04:15:00+00:00",
  "application_version": "1.4.0",
  "config_schema_version": "82",
  "database_schema_version": "036",
  "source_install": {"channel": "stable", "commit": "abc123"},
  "sections": [
    {"name": "config", "path": "config.tar", "sha256": "...", "size": 1234},
    {"name": "database", "path": "database.sqlite", "sha256": "...", "size": 5678},
    {"name": "install_metadata", "path": "install_metadata.json", "sha256": "...", "size": 128}
  ],
  "pinned": false,
  "tag": null,
  "total_size": 7030
}
```

## Permissions

- Backup directories: `0o700`
- Backup files: `0o600`
- Pins file: `0o600`
- Restore records: `0o600`

## Retention and Pruning

Default retention policy:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--max-count` | 10 | Maximum number of backups to keep |
| `--max-age-days` | 90 | Maximum age in days |
| `--max-total-bytes` | None | Maximum total bytes (optional) |

### Pruning behavior

- Pinned backups are never pruned
- The last verified backup is never pruned (even if age/count limits say otherwise)
- Age-based pruning runs first, then count-based, then size-based
- Dry-run mode shows what would be pruned without deleting

## Verification

`ainews backup verify` checks:

1. **Manifest schema** — valid JSON with required fields
2. **Section presence** — all expected sections exist
3. **File integrity** — sizes and SHA-256 checksums match
4. **Archive safety** — no path traversal (`../`) in tar members
5. **SQLite integrity** — `PRAGMA integrity_check` passes
6. **YAML parseability** — config files parse without errors
7. **Cross-file validation** — pipeline stages reference defined providers
8. **Version compatibility** — same major version as current installation

### Verification reason codes

| Code | Meaning |
|------|---------|
| `backup_not_found` | Backup directory does not exist |
| `manifest_missing` | `manifest.json` not found |
| `manifest_corrupt` | Cannot parse manifest JSON |
| `manifest_invalid` | Missing required manifest fields |
| `schema_too_new` | Backup schema version exceeds supported version |
| `version_incompatible` | Major version mismatch |
| `section_missing` | Expected section not in manifest |
| `unsafe_path` | Path traversal detected in section path or tar member |
| `file_missing` | Section file not found on disk |
| `size_mismatch` | File size differs from manifest |
| `checksum_mismatch` | SHA-256 hash differs from manifest |
| `db_corrupt` | SQLite integrity check failed |
| `config_tar_corrupt` | Cannot read config tarball |
| `config_parse_error` | YAML parse error or invalid config reference |

## Restore

### Restore modes

| Mode | Sections restored | Description |
|------|-------------------|-------------|
| Full | config, database, install_metadata | Restores everything |
| `--config-only` | config only | Restores `.env` and YAML files |
| `--data-only` | database, install_metadata | Restores database and metadata |

### Restore flow

1. **Verify backup** — ensure backup is valid
2. **Stop services** — via lifecycle driver (Docker Compose or bare metal)
3. **Create safety backup** — captures current state before restore
4. **Acquire restore lock** — prevents concurrent restores
5. **Stage files** — extract to temporary directory
6. **Apply restore** — atomic writes to config, database, metadata
7. **Record restore** — write restore record with timestamp
8. **Health check** — verify services are healthy post-restore
9. **Start services** — restart via lifecycle driver
10. **Rollback on failure** — if health check fails, restore safety backup

### Rollback

If the post-restore health check fails:

1. Services are stopped
2. The safety backup (created in step 3) is restored
3. Services are restarted
4. A `RestoreError` is raised with code `HEALTH_CHECK_FAILED`

### Restore plan output

The `--dry-run` mode shows:

- Sections to restore
- Current vs backup versions
- Required migrations
- Paths affected
- Services to stop
- Secrets impact (`.env` files contain secrets)
- Permissions impact (files set to `0o600`)
- Post-restore actions

## Secrets and Security

- `.env` files contain secrets (`SECRET_KEY`, `ADMIN_PASSWORD`, etc.)
- Backup files are created with `0o600` permissions (owner read/write only)
- Backup directories are created with `0o700` permissions
- JSON output never includes secret values (only metadata about sections)
- Manifest files contain only section names, paths, checksums, and sizes

## Disaster Recovery

### From a backup

```bash
# 1. List available backups
ainews backup list

# 2. Verify the backup you want to restore
ainews backup verify <backup-id>

# 3. Preview the restore plan
ainews restore <backup-id> --dry-run

# 4. Restore (will create safety backup automatically)
ainews restore <backup-id>

# 5. Verify health
ainews health
```

### From a safety backup

If a restore failed and was rolled back, the safety backup is in the backups directory:

```bash
# List backups to find the safety backup
ainews backup list

# Restore from the safety backup
ainews restore pre-restore-<timestamp>-<version>
```

### Manual offline verification

To verify a backup without the CLI:

```bash
# 1. Check manifest exists and is valid JSON
cat backups/<backup-id>/manifest.json | python -m json.tool

# 2. Check config tarball
tar -tf backups/<backup-id>/config.tar

# 3. Check SQLite integrity
sqlite3 backups/<backup-id>/database.sqlite "PRAGMA integrity_check;"

# 4. Verify checksums (compare with manifest)
sha256sum backups/<backup-id>/config.tar
```

### Interrupted restore recovery

If a restore is interrupted (power failure, crash, etc.):

1. The staging directory (`.restore-staging-*`) will be cleaned up on the next restore attempt
2. The safety backup preserves the pre-restore state
3. The restore lock has a 600-second stale detection timeout
4. Config files that were partially written will be in an inconsistent state — restore from backup

## Migration Framework

### Migration protocol

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

### Migration rules

- **Deterministic ordering** — migrations are sorted by target version
- **Downgrade refusal** — downgrades are rejected unless a tested reverse migration exists
- **Preflight gating** — each migration must pass preflight before applying
- **Idempotent execution** — migrations should be safe to run multiple times
- **No network dependency** — migrations must work offline

### Migration status

```bash
# Check if migrations are needed
ainews migrations status

# Preview what would be applied
ainews migrations plan

# Apply pending migrations
ainews migrations apply
```

## Version Compatibility

| Backup version | Current version | Compatible? |
|----------------|-----------------|-------------|
| 1.4.0 | 1.5.0 | Yes (same major) |
| 1.4.0 | 2.0.0 | No (different major) |
| 1.4.0 | 1.4.1 | Yes (same minor) |

Cross-major-version restores are always rejected. Cross-minor-version restores are allowed but warn about potential incompatibilities.
