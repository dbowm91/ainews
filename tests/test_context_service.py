"""Tests for the context service."""

from unittest.mock import patch

import pytest
from sqlalchemy.exc import SQLAlchemyError


class TestTopicNoteCrud:
    """Test topic note CRUD operations."""

    def test_create_topic_note(self, app):
        """Creating a topic note should persist it."""
        with app.app_context():
            from services.context_service import create_topic_note

            note = create_topic_note(
                topic="artificial-intelligence",
                note="AI is transforming many industries",
                source="test-source",
            )

            assert note.id is not None
            assert note.topic == "artificial-intelligence"
            assert note.note == "AI is transforming many industries"
            assert note.source == "test-source"

    def test_get_topic_note(self, app):
        """Getting a topic note by topic and source."""
        with app.app_context():
            from services.context_service import create_topic_note, get_topic_note

            created = create_topic_note(
                topic="machine-learning", note="ML note", source="src"
            )

            retrieved = get_topic_note("machine-learning", "src")
            assert retrieved is not None
            assert retrieved.id == created.id
            assert retrieved.note == "ML note"

    def test_get_topic_note_not_found(self, app):
        """Getting a non-existent topic note returns None."""
        with app.app_context():
            from services.context_service import get_topic_note

            result = get_topic_note("non-existent-topic", "non-existent-source")
            assert result is None

    def test_get_all_topic_notes(self, app):
        """Getting all notes for a topic."""
        with app.app_context():
            from services.context_service import create_topic_note, get_all_topic_notes

            create_topic_note("python", note="Note 1", source="src1")
            create_topic_note("python", note="Note 2", source="src2")

            notes = get_all_topic_notes("python")
            assert len(notes) == 2

    def test_update_topic_note(self, app):
        """Updating an existing topic note."""
        with app.app_context():
            from services.context_service import create_topic_note, update_topic_note

            create_topic_note("rust", note="Original note", source="src")
            updated = update_topic_note("rust", note="Updated note", source="src")

            assert updated is not None
            assert updated.note == "Updated note"

    def test_delete_topic_note(self, app):
        """Deleting a topic note."""
        with app.app_context():
            from services.context_service import (
                create_topic_note,
                delete_topic_note,
                get_topic_note,
            )

            create_topic_note("go", note="To be deleted", source="src")
            result = delete_topic_note("go", "src")

            assert result is True
            assert get_topic_note("go", "src") is None

    def test_delete_topic_note_not_found(self, app):
        """Deleting a non-existent topic note returns False."""
        with app.app_context():
            from services.context_service import delete_topic_note

            result = delete_topic_note("non-existent", "src")
            assert result is False

    def test_create_topic_note_rollback_on_commit_failure(self, app):
        """Creating a topic note should rollback on commit failure."""
        with app.app_context():
            from extensions import db
            from services.context_service import create_topic_note

            with patch.object(
                db.session, "commit", side_effect=SQLAlchemyError("commit failed")
            ):
                with patch.object(db.session, "rollback") as mock_rollback:
                    with pytest.raises(SQLAlchemyError):
                        create_topic_note(
                            "rollback-test", note="should fail", source="src"
                        )
                    mock_rollback.assert_called_once()

    def test_update_topic_note_rollback_on_commit_failure(self, app):
        """Updating a topic note should rollback on commit failure."""
        with app.app_context():
            from extensions import db
            from services.context_service import create_topic_note, update_topic_note

            note = create_topic_note("rollback-update", note="original", source="src")

            with patch.object(
                db.session, "commit", side_effect=SQLAlchemyError("commit failed")
            ):
                with patch.object(db.session, "rollback") as mock_rollback:
                    with pytest.raises(SQLAlchemyError):
                        update_topic_note(
                            "rollback-update", note="updated", source="src"
                        )
                    mock_rollback.assert_called_once()

            db.session.rollback()
            db.session.commit()
            retrieved = db.session.get(type(note), note.id)
            assert retrieved.note == "original"

    def test_delete_topic_note_rollback_on_commit_failure(self, app):
        """Deleting a topic note should rollback on commit failure."""
        with app.app_context():
            from extensions import db
            from services.context_service import create_topic_note, delete_topic_note

            note = create_topic_note(
                "rollback-delete", note="to be deleted", source="src"
            )
            note_id = note.id

            with patch.object(
                db.session, "commit", side_effect=SQLAlchemyError("commit failed")
            ):
                with patch.object(db.session, "rollback") as mock_rollback:
                    with pytest.raises(SQLAlchemyError):
                        delete_topic_note("rollback-delete", "src")
                    mock_rollback.assert_called_once()

            db.session.rollback()
            db.session.commit()
            retrieved = db.session.get(type(note), note_id)
            assert retrieved is not None


class TestGetTopicNotesForTopics:
    """Test get_topic_notes_for_topics function."""

    def test_empty_topics(self, app):
        """Empty topics list returns empty dict."""
        with app.app_context():
            from services.context_service import get_topic_notes_for_topics

            result = get_topic_notes_for_topics([])
            assert result == {}

    def test_get_notes_for_multiple_topics(self, app):
        """Getting notes for multiple topics."""
        with app.app_context():
            from services.context_service import (
                create_topic_note,
                get_topic_notes_for_topics,
            )

            create_topic_note("ai", note="AI note 1", source="src1")
            create_topic_note("ai", note="AI note 2", source="src2")
            create_topic_note("ml", note="ML note", source="src")

            result = get_topic_notes_for_topics(["ai", "ml"])

            assert "ai" in result
            assert len(result["ai"]) == 2
            assert "ml" in result
            assert len(result["ml"]) == 1


class TestGetRelatedArticlesForEdit:
    """Test get_related_articles_for_edit function."""

    def test_empty_topics(self, app):
        """Empty topics returns empty list."""
        with app.app_context():
            from services.context_service import get_related_articles_for_edit

            result = get_related_articles_for_edit([], exclude_id=1)
            assert result == []

    def test_get_related_articles(self, app, create_article, create_source):
        """Getting related articles for topics."""
        with app.app_context():
            source1 = create_source(source_key="test-source-ai", name="AI Source")
            source2 = create_source(source_key="test-source-ml", name="ML Source")
            source3 = create_source(
                source_key="test-source-sports", name="Sports Source"
            )

            create_article(
                source=source1,
                original_title="AI News Article",
                category="artificial-intelligence",
            )

            create_article(
                source=source2,
                original_title="ML Article",
                category="machine-learning",
            )

            create_article(
                source=source3,
                original_title="Unrelated Article",
                category="sports",
            )

            from services.context_service import get_related_articles_for_edit

            result = get_related_articles_for_edit(
                ["artificial-intelligence", "machine-learning"],
                exclude_id=999,
                limit=5,
            )

            assert len(result) >= 2
