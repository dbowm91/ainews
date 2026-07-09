# PostgreSQL Migration Strategy

## Current State

The application uses SQLite in WAL (Write-Ahead Logging) mode for production. This is intentional for the current scale and deployment model.

## Rationale for SQLite

From `docs/architecture.md` and `AGENTS.md`:
- Workload is read-heavy with moderate write activity
- Single-server deployment (not clustered)
- SQLite WAL mode provides sufficient concurrency
- PostgreSQL adds operational overhead (maintenance, tuning, backups) with no benefit at current scale

## Migration Triggers

Consider PostgreSQL migration if:
1. **Concurrent write scaling**: Multiple application servers need shared DB access
2. **Connection pooling**: Need for advanced connection management
3. **JSONB queries**: Advanced querying of JSON fields (beyond SQLite's basic JSON1)
4. **Replication needs**: Read replicas for scaling read-heavy workloads
5. **Dataset size**: Database exceeds available RAM (SQLite performance degrades)

## Migration Path (When Needed)

### Phase 1: Preparation
1. Audit all SQLite-specific SQL (FTS5 queries, `insert or ignore`, etc.)
2. Create PostgreSQL-compatible equivalents
3. Update Alembic migration scripts to support both dialects
4. Add `DATABASE_URL` env var support (already exists in config)

### Phase 2: Dual Support
1. Implement `services/search/postgresql.py` as alternative SearchProvider
2. Add PostgreSQL-specific migrations
3. Test with `DATABASE_URL=postgresql://...`

### Phase 3: Migration
1. Set up PostgreSQL instance
2. Run `pgloader` or custom script to migrate data
3. Switch `DATABASE_URL` to PostgreSQL
4. Deprecate SQLite support

## Current Status

**No migration planned.** SQLite remains the recommended database for this application's current scale and deployment model.

The `services/search/` DAL (Database Abstraction Layer) provides the foundation for future PostgreSQL support if needed. The `SearchProvider` interface abstracts SQLite FTS5-specific logic, making it possible to add a PostgreSQL + pg_trgm or PostgreSQL + FTS implementation.

## References

- `services/search/base.py` - SearchProvider interface
- `services/search/sqlite_fts.py` - Current SQLite implementation
- `config.py` - `DATABASE_URL` support already exists
- `AGENTS.md` - Notes on intentional SQLite choice
