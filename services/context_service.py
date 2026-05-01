from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import TopicNote

logger = logging.getLogger(__name__)


def get_topic_note(topic: str, source: Optional[str] = None) -> Optional[TopicNote]:
    query = TopicNote.query.filter(TopicNote.topic == topic)
    if source:
        query = query.filter(TopicNote.source == source)
    return query.first()


def get_all_topic_notes(topic: str) -> list[TopicNote]:
    return TopicNote.query.filter(TopicNote.topic == topic).all()


def create_topic_note(topic: str, note: str, source: Optional[str] = None) -> TopicNote:
    topic_note = TopicNote(topic=topic, note=note, source=source)
    db.session.add(topic_note)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return topic_note


def update_topic_note(
    topic: str, note: str, source: Optional[str] = None,
) -> Optional[TopicNote]:
    topic_note = get_topic_note(topic, source)
    if topic_note:
        topic_note.note = note
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise
    return topic_note


def delete_topic_note(topic: str, source: Optional[str] = None) -> bool:
    topic_note = get_topic_note(topic, source)
    if topic_note:
        db.session.delete(topic_note)
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise
        return True
    return False


def get_topic_notes_for_topics(topics: list[str]) -> dict[str, list[str]]:
    if not topics:
        return {}
    notes_by_topic = {}
    topic_notes = TopicNote.query.filter(TopicNote.topic.in_(topics)).all()
    for tn in topic_notes:
        if tn.topic not in notes_by_topic:
            notes_by_topic[tn.topic] = []
        notes_by_topic[tn.topic].append(tn.note)
    return notes_by_topic


def get_related_articles_for_edit(
    topics: list[str], exclude_id: int, limit: int = 5,
) -> list[dict]:
    if not topics:
        return []
    from services.related import find_related_articles_dicts

    return find_related_articles_dicts(topics, exclude_id, limit=limit)
