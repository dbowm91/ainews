import logging

from flask import current_app, g, jsonify, render_template, request
from sqlalchemy.orm import joinedload

from constants import PER_PAGE_NEWSLETTERS
from extensions import db
from routes.admin import admin_bp, require_auth
from routes.decorators import validate_csrf_json
from services.task_security import get_signed_kwargs

logger = logging.getLogger(__name__)

# Allowed HTML tags and attributes for newsletter content.
_NEWSLETTER_TAGS = {
    "a",
    "p",
    "br",
    "strong",
    "em",
    "b",
    "i",
    "u",
    "ul",
    "ol",
    "li",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "blockquote",
    "img",
    "table",
    "tr",
    "td",
    "th",
    "thead",
    "tbody",
    "div",
    "span",
    "hr",
    "pre",
    "code",
}
_NEWSLETTER_ATTRS = {
    "a": {"href", "title"},
    "img": {"src", "alt", "width", "height"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}


def _sanitize_newsletter_html(html: str) -> str:
    """Remove dangerous tags and attributes from newsletter HTML before serving."""
    import nh3

    if not html:
        return html
    return nh3.clean(
        html,
        tags=_NEWSLETTER_TAGS,
        attributes=_NEWSLETTER_ATTRS,
        url_schemes={"http", "https", "mailto"},
    )


@admin_bp.route("/newsletters")
@require_auth
def newsletters():
    from models import Newsletter
    from services.utils import paginate_query

    page = max(1, request.args.get("page", 1, type=int))
    per_page = PER_PAGE_NEWSLETTERS
    q = Newsletter.query.order_by(Newsletter.generated_at.desc())
    newsletters, has_next, next_page = paginate_query(q, page, per_page)

    return render_template(
        "admin/newsletters.html",
        newsletters=newsletters,
        has_next=has_next,
        next_page=next_page,
        page=page,
    )


@admin_bp.route("/newsletters/<int:newsletter_id>")
@require_auth
def view_newsletter(newsletter_id):
    from models import Newsletter

    nl = db.get_or_404(Newsletter, newsletter_id)
    safe_html = _sanitize_newsletter_html(nl.html_content or "")
    return safe_html, 200, {"Content-Type": "text/html"}


@admin_bp.route("/newsletters/generate", methods=["POST"])
@require_auth
@validate_csrf_json
def trigger_newsletter():
    from tasks.newsletter import generate_daily_newsletters

    try:
        request_id = getattr(g, "request_id", None)
        headers = {"request_id": request_id} if request_id else None
        signed_kwargs = get_signed_kwargs("generate_daily_newsletters", (), {})
        result = generate_daily_newsletters.apply_async(kwargs=signed_kwargs, headers=headers)
        return jsonify(
            {"message": "Newsletter generation started", "task_id": result.id}
        ), 202
    except Exception:
        current_app.logger.exception("Failed to trigger newsletter")
        return jsonify({"error": "Failed to start newsletter generation"}), 503


@admin_bp.route("/newsletters/dry-run", methods=["POST"])
@require_auth
@validate_csrf_json
def newsletter_dry_run():
    from tasks.newsletter import generate_daily_newsletters

    test_email = request.form.get("test_email", "").strip().lower()
    from services.utils import is_valid_email

    is_htmx = request.headers.get("HX-Request")

    if not is_valid_email(test_email):
        if is_htmx:
            return (
                '<span class="health-dot red"></span> <span class="form-hint">Invalid email address</span>',
                400,
            )
        return jsonify({"error": "Invalid email address"}), 400

    try:
        request_id = getattr(g, "request_id", None)
        headers = {"request_id": request_id} if request_id else None
        kwargs = {"dry_run_email": test_email}
        signed_kwargs = get_signed_kwargs("generate_daily_newsletters", (), kwargs)
        result = generate_daily_newsletters.apply_async(
            kwargs=signed_kwargs, headers=headers
        )
        msg = f"Dry run started — will send to {test_email}"
        if is_htmx:
            return (
                f'<span class="health-dot green"></span> <span class="form-hint">{msg}</span>',
                202,
            )
        return jsonify({"message": msg, "task_id": result.id}), 202
    except Exception:
        current_app.logger.exception("Failed to trigger newsletter dry run")
        if is_htmx:
            return (
                '<span class="health-dot red"></span> <span class="form-hint">Failed to start dry run</span>',
                503,
            )
        return jsonify({"error": "Failed to start dry run"}), 503


@admin_bp.route("/api/newsletters/stats", methods=["GET"])
@require_auth
def newsletters_stats():
    """Return newsletter delivery statistics."""
    from sqlalchemy import case, func

    from models import Newsletter

    stats = db.session.query(
        func.count(Newsletter.id).label("total"),
        func.sum(Newsletter.recipients).label("total_recipients"),
        func.sum(Newsletter.delivered_count).label("total_delivered"),
        func.sum(case((Newsletter.error_message.isnot(None), 1), else_=0)).label("total_errors"),
    ).one()

    recent = (
        Newsletter.query
        .order_by(Newsletter.generated_at.desc())
        .limit(30)
        .all()
    )

    return jsonify({
        "total_newsletters": stats.total or 0,
        "total_recipients": stats.total_recipients or 0,
        "total_delivered": stats.total_delivered or 0,
        "total_with_errors": stats.total_errors or 0,
        "recent": [
            {
                "id": nl.id,
                "newsletter_type": nl.newsletter_type,
                "subject": nl.subject,
                "article_count": nl.article_count,
                "recipients": nl.recipients,
                "delivered_count": nl.delivered_count,
                "error_message": nl.error_message,
                "generated_at": nl.generated_at.isoformat() if nl.generated_at else None,
                "sent_at": nl.sent_at.isoformat() if nl.sent_at else None,
            }
            for nl in recent
        ],
    })


@admin_bp.route("/api/newsletter/preview", methods=["POST"])
@require_auth
@validate_csrf_json
def newsletter_preview():
    """Generate newsletter HTML preview without sending emails."""
    from datetime import datetime, timedelta, timezone

    from constants import PipelineStatus
    from models import Article
    from services.newsletter import generate_main_newsletter
    from services.newsletter_pipeline import generate_executive_summary

    site_url = request.form.get("site_url", "").strip()
    if not site_url:
        site_url = request.host_url.rstrip("/")

    # Get recent articles
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    articles = (
        Article.query.filter(
            Article.pipeline_status == PipelineStatus.DONE,
            Article.impact_score > 0,
            Article.created_at >= cutoff,
        )
        .options(joinedload(Article.source), joinedload(Article.tags))
        .order_by(Article.impact_score.desc())
        .limit(20)
        .all()
    )

    if not articles:
        return jsonify({"error": "No articles available for preview"}), 400

    try:
        result = generate_executive_summary(articles, topic_key="main")
        exec_summary = result["summary"]
    except Exception as e:
        logger.exception("Preview exec summary failed")
        exec_summary = f"(Summary generation failed: {e})"

    try:
        html, subject, count = generate_main_newsletter(
            site_url=site_url,
            max_articles=20,
            executive_summary=exec_summary,
        )
    except Exception as e:
        logger.exception("Preview HTML generation failed")
        return jsonify({"error": f"Failed to generate preview: {e}"}), 500

    safe_html = _sanitize_newsletter_html(html)
    return jsonify(
        {
            "subject": subject,
            "article_count": count,
            "html": safe_html,
        }
    )
