#!/usr/bin/env bash
# Verify a SQLite backup file is valid.
# Usage: verify_backup.sh <backup_file>
set -euo pipefail

BACKUP_FILE="${1:-}"

if [[ -z "$BACKUP_FILE" ]]; then
    echo "Usage: $0 <backup_file>"
    exit 1
fi

if [[ ! -s "$BACKUP_FILE" ]]; then
    echo "FAIL: Backup file is empty or missing: $BACKUP_FILE"
    exit 1
fi

# Decompress if gzipped, otherwise use file directly
if [[ "$BACKUP_FILE" == *.gz ]]; then
    DB_CHECK=$(mktemp)
    trap "rm -f '$DB_CHECK'" EXIT
    gunzip -c "$BACKUP_FILE" > "$DB_CHECK"
else
    DB_CHECK="$BACKUP_FILE"
fi

# SQLite integrity check
if ! sqlite3 "$DB_CHECK" "PRAGMA integrity_check;" | grep -q "^ok$"; then
    echo "FAIL: SQLite integrity check failed for $BACKUP_FILE"
    exit 1
fi

# Check required tables exist
REQUIRED_TABLES=(
    "articles"
    "sources"
    "tags"
    "subscribers"
    "newsletters"
    "article_metrics"
    "share_configs"
    "pipeline_runs"
    "pipeline_logs"
    "article_versions"
    "topic_notes"
    "trend_memory"
    "webhooks"
    "webhook_events"
    "audit_logs"
    "search_queries"
    "citations"
)
for table in "${REQUIRED_TABLES[@]}"; do
    count=$(sqlite3 "$DB_CHECK" "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='$table';")
    if [[ "$count" != "1" ]]; then
        echo "FAIL: Required table '$table' not found in backup"
        exit 1
    fi
done

echo "OK: Backup verified - $(du -h "$BACKUP_FILE" | cut -f1), all tables present"
exit 0
