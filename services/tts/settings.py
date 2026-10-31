"""Versioned database backed TTS policy with default-off configuration fallback."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import TTSSettings


def get_settings() -> TTSSettings | None:
    try:
        return db.session.get(TTSSettings, 1)
    except SQLAlchemyError:
        db.session.rollback()
        return None


def value(name: str, fallback: Any) -> Any:
    row = get_settings()
    return getattr(row, name) if row is not None else fallback


def save_settings(values: dict[str, Any]) -> TTSSettings:
    row = db.session.get(TTSSettings, 1)
    if row is None:
        row = TTSSettings(id=1)
        db.session.add(row)
    speech_affecting = {"backend", "model", "checkpoint_revision", "instruction", "cfg_scale", "opus_bitrate",
                        "max_minutes", "max_chars", "pronunciation_aliases"}
    changed = any(getattr(row, key) != val for key, val in values.items() if key in speech_affecting and hasattr(row, key))
    for key, val in values.items():
        if hasattr(row, key):
            setattr(row, key, val)
    if changed:
        row.profile_revision = int(row.profile_revision or 0) + 1
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.commit()
    from services.publication import invalidate_publication_cache
    invalidate_publication_cache()
    return row
