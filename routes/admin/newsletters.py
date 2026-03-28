import logging
from flask import render_template, request, jsonify, current_app
from routes.admin import admin_bp, require_auth
from constants import PER_PAGE_NEWSLETTERS

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
    )


@admin_bp.route("/newsletters/<int:newsletter_id>")
@require_auth
def view_newsletter(newsletter_id):
    from models import Newsletter

    nl = Newsletter.query.get_or_404(newsletter_id)
    safe_html = _sanitize_newsletter_html(nl.html_content or "")
    return safe_html, 200, {"Content-Type": "text/html"}


@admin_bp.route("/newsletters/generate", methods=["POST"])
@require_auth
def trigger_newsletter():
    from tasks.newsletter import generate_daily_newsletters

    try:
        result = generate_daily_newsletters.delay()
        return jsonify(
            {"message": "Newsletter generation started", "task_id": result.id}
        ), 202
    except Exception:
        current_app.logger.exception("Failed to trigger newsletter")
        return jsonify({"message": "Failed to start newsletter generation"}), 503


@admin_bp.route("/newsletters/dry-run", methods=["POST"])
@require_auth
def newsletter_dry_run():
    from tasks.newsletter import generate_daily_newsletters

    test_email = request.form.get("test_email", "").strip().lower()
    from services.utils import is_valid_email

    if not is_valid_email(test_email):
        return jsonify({"message": "Invalid email address"}), 400

    try:
        result = generate_daily_newsletters.delay(dry_run_email=test_email)
        return jsonify(
            {
                "message": f"Dry run started — will send to {test_email}",
                "task_id": result.id,
            }
        ), 202
    except Exception:
        current_app.logger.exception("Failed to trigger newsletter dry run")
        return jsonify({"message": "Failed to start dry run"}), 503


@admin_bp.route("/api/newsletter/preview", methods=["POST"])
@require_auth
def newsletter_preview():
    """Generate newsletter HTML preview without sending emails."""
    from models import Article
    from constants import PipelineStatus
    from datetime import datetime, timezone, timedelta
    from services.newsletter_pipeline import generate_executive_summary
    from services.newsletter import generate_main_newsletter

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
        .order_by(Article.impact_score.desc())
        .limit(20)
        .all()
    )

    if not articles:
        return jsonify({"message": "No articles available for preview"}), 400

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
        return jsonify({"message": f"Failed to generate preview: {e}"}), 500

    safe_html = _sanitize_newsletter_html(html)
    return jsonify(
        {
            "subject": subject,
            "article_count": count,
            "html": safe_html,
        }
    )
