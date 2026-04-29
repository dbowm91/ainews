#!/bin/bash
set -euo pipefail

# ainews Database Backup Script
# Usage: bash scripts/backup.sh
#
# Backs up the SQLite database with WAL checkpoint.
# Retains backups for 30 days by default.
#
# Add to cron for daily backups:
#   0 2 * * * /opt/ainews/scripts/backup.sh >> /var/log/ainews-backup.log 2>&1

APP_DIR="${APP_DIR:-/opt/ainews}"
DB_PATH="${DB_PATH:-$APP_DIR/instance/ainews.db}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="$BACKUP_DIR/ainews-$TIMESTAMP.db"

# Create backup directory if needed
mkdir -p "$BACKUP_DIR"

# Check database exists
if [ ! -f "$DB_PATH" ]; then
    echo "ERROR: Database not found at $DB_PATH"
    exit 1
fi

echo "$(date): Starting backup of $DB_PATH"

# Method 1: SQLite .backup command (preferred, handles WAL correctly)
if command -v sqlite3 &>/dev/null; then
    sqlite3 "$DB_PATH" ".backup $BACKUP_FILE"
    echo "$(date): SQLite backup completed: $BACKUP_FILE"
else
    echo "$(date): ERROR: sqlite3 is required for WAL checkpoint - backup cannot proceed"
    exit 1
fi

# Compress backup
if command -v gzip &>/dev/null; then
    gzip -f "$BACKUP_FILE"
    BACKUP_FILE="${BACKUP_FILE}.gz"
    echo "$(date): Compressed: $BACKUP_FILE"
fi

# Rotate old backups
DELETED=$(find "$BACKUP_DIR" -name "ainews-*.db.gz" -mtime +$RETENTION_DAYS | wc -l | tr -d ' ')
if [ "$DELETED" -gt 0 ]; then
    find "$BACKUP_DIR" -name "ainews-*.db.gz" -mtime +$RETENTION_DAYS -delete
    echo "$(date): Cleaned up $DELETED backups older than $RETENTION_DAYS days"
fi

# Verify backup
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
"$SCRIPT_DIR/verify_backup.sh" "$BACKUP_FILE"

# Show backup info
BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
TOTAL_BACKUPS=$(find "$BACKUP_DIR" -name "ainews-*.db*" | wc -l)
echo "$(date): Backup complete. Size: $BACKUP_SIZE. Total backups: $TOTAL_BACKUPS"
