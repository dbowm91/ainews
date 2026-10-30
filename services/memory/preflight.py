"""Fail-fast schema checks for independently gated editor-memory features."""

from sqlalchemy import inspect

from extensions import db


REQUIRED_MEMORY_TABLES = frozenset({
    "memory_items",
    "memory_evidence",
    "memory_scopes",
    "memory_lineage",
    "memory_category_summaries",
    "memory_maintenance_state",
    "memory_synthesis_runs",
    "memory_synthesis_attempts",
})
REQUIRED_SYNTHESIS_TABLES = frozenset({"memory_synthesis_cursors"})
REQUIRED_MEMORY_COLUMNS = {
    "memory_items": frozenset({"review_status", "review_reason", "review_attempted_at", "review_count", "decision_metadata"}),
    "memory_category_summaries": frozenset({"current_memory_id"}),
}


def _inspector():
    """Reflect schema through the caller's session connection.

    ``inspect(db.engine)`` checks out a pooled connection whose close rolls
    back the caller's uncommitted transaction on StaticPool-backed SQLite
    databases — silently discarding pending writes (in tests this surfaces
    as ``StaleDataError`` on the next flush; in workers it would drop real
    stage output). Reflecting through the session's own connection keeps the
    inspection inside the caller's transaction.
    """
    return inspect(db.session.connection())


def ensure_memory_schema() -> None:
    """Raise an actionable error when an enabled V2 path lacks its migration."""
    present = set(_inspector().get_table_names())
    missing = sorted(REQUIRED_MEMORY_TABLES - present)
    missing_columns: list[str] = []
    for table, required in REQUIRED_MEMORY_COLUMNS.items():
        if table not in present:
            continue
        available = {column["name"] for column in _inspector().get_columns(table)}
        missing_columns.extend(f"{table}.{column}" for column in sorted(required - available))
    if missing or missing_columns:
        details = [*missing, *missing_columns]
        raise RuntimeError(
            "Editor memory V2 is enabled but its schema is not installed "
            f"(missing: {', '.join(details)}). Apply Alembic migrations through "
            "the current editor-memory revision before enabling V2 reads, tools, "
            "writes, maintenance, or synthesis."
        )


def ensure_synthesis_schema() -> None:
    """Require synthesis-only state without coupling retrieval to its cursor."""
    ensure_memory_schema()
    present = set(_inspector().get_table_names())
    missing = sorted(REQUIRED_SYNTHESIS_TABLES - present)
    if missing:
        raise RuntimeError(
            "Editor-memory synthesis is enabled but its schema is not installed "
            f"(missing: {', '.join(missing)}). Apply the current synthesis migration."
        )
