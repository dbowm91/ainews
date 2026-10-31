"""Public immutable newsletter edition archive."""
from flask import abort, current_app, render_template, request
from sqlalchemy import select

from extensions import db
from models import NewsletterEdition
from routes.public import public_bp
from services.newsletter_editions import get_public_edition, serialize_edition


def _enabled():
    if not current_app.config.get("NEWSLETTER_ARCHIVE_ENABLED", False):
        abort(404)


@public_bp.route("/newsletters")
def newsletter_archive():
    _enabled()
    page = max(request.args.get("page", 1, type=int), 1)
    profile = request.args.get("profile", "").strip()
    q = select(NewsletterEdition).where(NewsletterEdition.status == "published", NewsletterEdition.published_at.is_not(None))
    if profile:
        q = q.where(NewsletterEdition.profile_key == profile)
    rows = db.session.scalars(q.order_by(NewsletterEdition.published_at.desc(), NewsletterEdition.id.desc()).offset((page - 1) * 20).limit(21)).all()
    return render_template("newsletters/archive.html", editions=rows[:20], has_more=len(rows) > 20, page=page, profile=profile)


@public_bp.route("/newsletters/category/<category>")
def newsletter_category_archive(category: str):
    _enabled()
    return newsletter_archive_filtered(category)


def newsletter_archive_filtered(category: str):
    page = max(request.args.get("page", 1, type=int), 1)
    rows = db.session.scalars(select(NewsletterEdition).where(NewsletterEdition.status == "published", NewsletterEdition.published_at.is_not(None), NewsletterEdition.profile_key == category)
        .order_by(NewsletterEdition.published_at.desc(), NewsletterEdition.id.desc()).offset((page - 1) * 20).limit(21)).all()
    return render_template("newsletters/archive.html", editions=rows[:20], has_more=len(rows) > 20, page=page, profile=category)


@public_bp.route("/newsletters/<public_id>")
def newsletter_detail(public_id: str):
    _enabled()
    edition = get_public_edition(public_id)
    if edition is None:
        abort(404)
    return render_template("newsletters/detail.html", edition=edition, dto=serialize_edition(edition))
