#!/bin/bash
# Query analysis script — runs EXPLAIN ANALYZE on slow or problematic queries
#
# Usage:
#   scripts/query_analysis.sh          # Run common query patterns
#   scripts/query_analysis.sh custom  # Run custom SQL
#   scripts/query_analysis.sh article ID  # Analyze queries for specific article
#
# This helps identify missing indexes and query performance issues.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

DATABASE_URL="${DATABASE_URL:-${DB_URL:-ainews.db}}"

echo "=== Query Analysis for ainews ==="
echo "Database: $DATABASE_URL"
echo ""

if [[ "$1" == "custom" ]]; then
    echo "Enter SQL query to analyze (CTRL+C to exit):"
    read -r QUERY
    echo ""
    echo "EXPLAIN QUERY PLAN $QUERY;"
    echo "---"
    sqlite3 "$DATABASE_URL" "EXPLAIN QUERY PLAN $QUERY"
    echo ""
    echo "EXPLAIN ANALYZE $QUERY;"
    echo "---"
    sqlite3 "$DATABASE_URL" "EXPLAIN ANALYZE $QUERY"
    exit 0
fi

if [[ -n "$1" ]]; then
    ARTICLE_ID="$1"
    echo "=== Queries for Article ID: $ARTICLE_ID ==="
    echo ""
    echo "--- Article lookup ---"
    sqlite3 "$DATABASE_URL" "EXPLAIN QUERY PLAN SELECT * FROM articles WHERE id = $ARTICLE_ID;"
    echo ""
    echo "--- Article with source ---"
    sqlite3 "$DATABASE_URL" "EXPLAIN QUERY PLAN SELECT a.*, s.name as source_name FROM articles a JOIN sources s ON a.source_id = s.id WHERE a.id = $ARTICLE_ID;"
    echo ""
    echo "--- Article with tags ---"
    sqlite3 "$DATABASE_URL" "EXPLAIN QUERY PLAN SELECT a.*, GROUP_CONCAT(t.name) as tags FROM articles a LEFT JOIN article_tags at ON a.id = at.article_id LEFT JOIN tags t ON at.tag_id = t.id WHERE a.id = $ARTICLE_ID GROUP BY a.id;"
    exit 0
fi

echo "=== Common Query Patterns ==="
echo ""

echo "--- Article by ID ---"
sqlite3 "$DATABASE_URL" "EXPLAIN QUERY PLAN SELECT * FROM articles WHERE id = 1;"
echo ""

echo "--- Article by short_id ---"
sqlite3 "$DATABASE_URL" "EXPLAIN QUERY PLAN SELECT * FROM articles WHERE short_id = 'abc123';"
echo ""

echo "--- Articles by status ---"
sqlite3 "$DATABASE_URL" "EXPLAIN QUERY PLAN SELECT * FROM articles WHERE pipeline_status = 'pending' ORDER BY created_at DESC LIMIT 20;"
echo ""

echo "--- Articles by source ---"
sqlite3 "$DATABASE_URL" "EXPLAIN QUERY PLAN SELECT * FROM articles WHERE source_id = 1 ORDER BY created_at DESC LIMIT 20;"
echo ""

echo "--- Articles by category ---"
sqlite3 "$DATABASE_URL" "EXPLAIN QUERY PLAN SELECT * FROM articles WHERE category = 'ai' AND pipeline_status = 'done' ORDER BY published_at DESC LIMIT 20;"
echo ""

echo "--- Recent PipelineRuns ---"
sqlite3 "$DATABASE_URL" "EXPLAIN QUERY PLAN SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 10;"
echo ""

echo "--- Recent Subscribers ---"
sqlite3 "$DATABASE_URL" "EXPLAIN QUERY PLAN SELECT * FROM subscribers ORDER BY subscribed_at DESC LIMIT 20;"
echo ""

echo "--- Recent AuditLogs ---"
sqlite3 "$DATABASE_URL" "EXPLAIN QUERY PLAN SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 20;"
echo ""

echo "=== Full-text search ==="
sqlite3 "$DATABASE_URL" "EXPLAIN QUERY PLAN SELECT id, snippet(articles_fts, 2, '<b>', '</b>', '...', 64) FROM articles_fts WHERE articles_fts MATCH 'ai AND neural' ORDER BY rank LIMIT 20;"
echo ""

echo "=== Done ==="
echo ""
echo "To analyze a specific article: $0 article <id>"
echo "To run custom SQL: $0 custom"