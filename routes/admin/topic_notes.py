"""Admin routes for topic notes CRUD."""
import logging

from flask import flash, redirect, render_template, request, url_for

from extensions import db
from routes.admin import admin_bp, require_auth
from services.audit import log_admin_action
from services.cache import get_response_cache
from services.context_service import (
    create_topic_note,
    delete_topic_note,
    get_topic_note,
)

logger = logging.getLogger(__name__)


@admin_bp.route("/topic-notes")
@admin_bp.route("/topic-notes/")
@require_auth
def topic_notes_list():
    topic = request.args.get("topic", "")
    source = request.args.get("source", "")

    from models import TopicNote

    notes: list
    if topic or source:
        query = TopicNote.query
        if topic:
            query = query.filter(TopicNote.topic == topic)
        if source:
            query = query.filter(TopicNote.source == source)
        notes = query.order_by(TopicNote.updated_at.desc()).limit(100).all()
    else:
        notes = TopicNote.query.order_by(TopicNote.updated_at.desc()).limit(100).all()

    if request.headers.get("HX-Request"):
        return render_template(
            "admin/partials/topic_notes_table.html",
            notes=notes,
            topic=topic,
            source=source,
        )
    return render_template(
        "admin/topic_notes.html",
        notes=notes,
        topic=topic,
        source=source,
    )


@admin_bp.route("/topic-notes/create", methods=["POST"])
@require_auth
def topic_notes_create():
    topic = request.form.get("topic", "").strip()
    note = request.form.get("note", "").strip()
    source = request.form.get("source", "").strip() or None

    if not topic or not note:
        flash("Topic and note are required", "error")
        return redirect(url_for("admin.topic_notes_list"))

    if len(topic) > 64:
        flash("Topic too long (max 64 characters)", "error")
        return redirect(url_for("admin.topic_notes_list"))
    if len(note) > 4096:
        flash("Note too long (max 4096 characters)", "error")
        return redirect(url_for("admin.topic_notes_list"))

    existing = get_topic_note(topic, source)
    if existing:
        flash("A note for this topic/source already exists. Use edit instead.", "error")
        return redirect(url_for("admin.topic_notes_list"))

    try:
        create_topic_note(topic, note, source)
        log_admin_action(
            "topic_note_create",
            target_type="topic_note",
            target_id=0,
            details={"topic": topic, "source": source},
            category="config",
        )
        flash("Topic note created", "success")
        try:
            cache = get_response_cache()
            cache.invalidate_prefix("topic_note")
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to invalidate topic_note cache: %s", e)
    except Exception as e:  # noqa: BLE001
        flash(f"Error creating note: {e}", "error")

    return redirect(url_for("admin.topic_notes_list"))


@admin_bp.route("/topic-notes/edit", methods=["POST"])
@require_auth
def topic_notes_edit():
    topic = request.form.get("topic", "").strip()
    note = request.form.get("note", "").strip()
    source = request.form.get("source", "").strip() or None
    original_topic = request.form.get("original_topic", "").strip()
    original_source = request.form.get("original_source", "").strip() or None

    if not topic or not note:
        flash("Topic and note are required", "error")
        return redirect(url_for("admin.topic_notes_list"))

    if len(topic) > 64:
        flash("Topic too long (max 64 characters)", "error")
        return redirect(url_for("admin.topic_notes_list"))
    if len(note) > 4096:
        flash("Note too long (max 4096 characters)", "error")
        return redirect(url_for("admin.topic_notes_list"))

    try:
        existing = get_topic_note(original_topic, original_source)
        if existing:
            existing.topic = topic
            existing.note = note
            existing.source = source
            db.session.commit()
            log_admin_action(
                "topic_note_edit",
                target_type="topic_note",
                target_id=existing.id,
                details={"topic": topic, "source": source},
                category="config",
            )
            flash("Topic note updated", "success")
        else:
            create_topic_note(topic, note, source)
            log_admin_action(
                "topic_note_create",
                target_type="topic_note",
                target_id=0,
                details={"topic": topic, "source": source},
                category="config",
            )
            flash("Topic note created", "success")
        try:
            cache = get_response_cache()
            cache.invalidate_prefix("topic_note")
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to invalidate topic_note cache: %s", e)
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        flash(f"Error updating note: {e}", "error")

    return redirect(url_for("admin.topic_notes_list"))


@admin_bp.route("/topic-notes/delete", methods=["POST"])
@require_auth
def topic_notes_delete():
    topic = request.form.get("topic", "").strip()
    source = request.form.get("source", "").strip() or None

    try:
        if delete_topic_note(topic, source):
            log_admin_action(
                "topic_note_delete",
                target_type="topic_note",
                target_id=0,
                details={"topic": topic, "source": source},
                category="config",
            )
            flash("Topic note deleted", "success")
            try:
                cache = get_response_cache()
                cache.invalidate_prefix("topic_note")
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to invalidate topic_note cache: %s", e)
        else:
            flash("Note not found", "error")
    except Exception as e:  # noqa: BLE001
        flash(f"Error deleting note: {e}", "error")

    return redirect(url_for("admin.topic_notes_list"))


@admin_bp.route("/topic-notes/row/<topic>")
@require_auth
def topic_notes_row(topic):
    source = request.args.get("source", "")
    note = get_topic_note(topic, source or None)
    if not note:
        return "<tr><td colspan='4'>Not found</td></tr>"
    return render_template("admin/partials/topic_note_row.html", note=note)
