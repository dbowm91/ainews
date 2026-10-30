#!/usr/bin/env python3
"""Capture a redacted, read-only baseline for editor memory rollout planning."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from sqlalchemy import func, inspect, select  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402
from models import TrendMemory  # noqa: E402
from schemas.pipeline import load_pipeline_config  # noqa: E402


def main() -> int:
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        columns = {column["name"] for column in inspector.get_columns("trend_memory")}
        total = db.session.scalar(select(func.count(TrendMemory.id))) or 0
        high_unexpiring = db.session.scalar(select(func.count(TrendMemory.id)).where(
            TrendMemory.importance == 3, TrendMemory.expires_at.is_(None)
        )) or 0
        missing_embeddings = None
        if "embedding" in columns:
            missing_embeddings = db.session.scalar(select(func.count(TrendMemory.id)).where(
                (TrendMemory.embedding.is_(None)) | (TrendMemory.embedding == "")
            )) or 0
        by_topic = db.session.execute(select(
            TrendMemory.topic, func.count(TrendMemory.id)
        ).group_by(TrendMemory.topic).order_by(func.count(TrendMemory.id).desc(), TrendMemory.topic).limit(25)).all()
        duplicate_groups = db.session.execute(select(func.count()).select_from(
            select(func.lower(func.trim(TrendMemory.signal)).label("signal"))
            .group_by(func.lower(func.trim(TrendMemory.signal)))
            .having(func.count(TrendMemory.id) > 1)
            .subquery()
        )).scalar_one()
        fts5 = False
        if db.engine.dialect.name == "sqlite":
            try:
                db.session.execute(db.text("CREATE VIRTUAL TABLE temp.editor_memory_fts_probe USING fts5(text)"))
                db.session.execute(db.text("DROP TABLE temp.editor_memory_fts_probe"))
                fts5 = True
            except SQLAlchemyError:  # pragma: no cover - SQLite build dependent
                db.session.rollback()
        cfg = load_pipeline_config()
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False,
        ).stdout.strip()
        try:
            alembic_revision = db.session.execute(db.text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        except SQLAlchemyError:
            db.session.rollback()
            alembic_revision = None
        print(json.dumps({
            "git_sha": sha,
            "alembic_revision": alembic_revision,
            "database_dialect": db.engine.dialect.name,
            "sqlite_fts5": fts5,
            "trend_memory_rows": int(total),
            "high_without_expiry": int(high_unexpiring),
            "missing_embeddings": int(missing_embeddings) if missing_embeddings is not None else None,
            "embedding_column_present": "embedding" in columns,
            "duplicate_normalized_signal_groups": int(duplicate_groups),
            "top_topics": [{"topic": topic, "count": int(count)} for topic, count in by_topic],
            "last_accessed_at_column": "last_accessed_at" in columns,
            "configured_retrieval_budgets": {
                "research": cfg.memory.research_token_budget,
                "edit": cfg.memory.editor_token_budget,
                "deep": cfg.memory.deep_token_budget,
            },
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
