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


def ensure_memory_schema() -> None:
    """Raise an actionable error when an enabled V2 path lacks its migration."""
    present = set(inspect(db.engine).get_table_names())
    missing = sorted(REQUIRED_MEMORY_TABLES - present)
    missing_columns: list[str] = []
    for table, required in REQUIRED_MEMORY_COLUMNS.items():
        if table not in present:
            continue
        available = {column["name"] for column in inspect(db.engine).get_columns(table)}
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
    present = set(inspect(db.engine).get_table_names())
    missing = sorted(REQUIRED_SYNTHESIS_TABLES - present)
    if missing:
        raise RuntimeError(
            "Editor-memory synthesis is enabled but its schema is not installed "
            f"(missing: {', '.join(missing)}). Apply the current synthesis migration."
        )
