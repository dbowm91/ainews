"""Admin routes for topic notes CRUD."""

from flask import flash, redirect, render_template, request, url_for

from extensions import db
from routes.admin import admin_bp, require_auth
from services.context_service import (
    create_topic_note,
    delete_topic_note,
    get_all_topic_notes,
    get_topic_note,
)


@admin_bp.route("/topic-notes")
@admin_bp.route("/topic-notes/")
@require_auth
def topic_notes_list():
    topic = request.args.get("topic", "")
    source = request.args.get("source", "")

    if topic:
        notes = get_all_topic_notes(topic)
    else:
        from models import TopicNote

        notes = TopicNote.query.order_by(TopicNote.updated_at.desc()).limit(100).all()

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
        flash("Topic note created", "success")
    except Exception as e:
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
            flash("Topic note updated", "success")
        else:
            create_topic_note(topic, note, source)
            flash("Topic note created", "success")
    except Exception as e:
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
            flash("Topic note deleted", "success")
        else:
            flash("Note not found", "error")
    except Exception as e:
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
