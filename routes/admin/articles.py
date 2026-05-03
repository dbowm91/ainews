import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import redis.exceptions
from flask import flash, g, jsonify, redirect, render_template, request, url_for
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from constants import PER_PAGE_ADMIN_ARTICLES, PipelineStatus
from routes.admin import admin_bp, require_auth
from routes.decorators import validate_csrf_json
from services.audit import log_admin_action
from services.article import _escape_like_pattern
from services.task_security import get_signed_kwargs
from services.utils import get_admin_categories as _admin_categories

logger = logging.getLogger(__name__)

MAX_HEADLINE_LENGTH = 500
MAX_TLDR_LENGTH = 300
MAX_BODY_LENGTH = 50000
MAX_WHY_IT_MATTERS_LENGTH = 1000
MAX_WHAT_TO_WATCH_LENGTH = 500
MAX_KEY_POINTS_LENGTH = 2000
MAX_TAGS_LENGTH = 500


def _sanitize_field(value: str, max_length: int) -> str:
    """Truncate a string to max_length characters."""
    if not isinstance(value, str):
        return ""
    return value[:max_length]


_REPROCESS_STAGES = {
    "select": {
        "status": PipelineStatus.PENDING,
        "fields": [
            "selector_result",
            "research_brief",
            "draft_article",
            "final_article",
            "original_ai_article",
        ],
        "task": "select_article",
    },
    "research": {
        "status": PipelineStatus.RESEARCHING,
        "fields": [
            "research_brief",
            "draft_article",
            "final_article",
            "original_ai_article",
        ],
        "task": "research_article",
    },
    "write": {
        "status": PipelineStatus.WRITING,
        "fields": ["draft_article", "final_article", "original_ai_article"],
        "task": "write_article",
    },
}


def _query_looks_like_url(query: str) -> bool:
    """Check if the query string looks like a URL."""
    if not query:
        return False
    if query.startswith("http://") or query.startswith("https://"):
        return True
    parsed = urlparse(query)
    return bool(parsed.scheme and parsed.netloc)


def _apply_numeric_filter(q, field, value_str, operator=">="):
    """Apply a numeric filter to the query if value_str is valid."""
    if not value_str:
        return q
    try:
        value = int(value_str)
        if operator == ">=":
            return q.filter(field >= value)
        elif operator == "<=":
            return q.filter(field <= value)
    except ValueError:
        pass
    return q


def _apply_tag_filter(q, tag_slug):
    """Apply tag filter to query if tag exists."""
    from models import Tag

    if not tag_slug:
        return q
    tag = Tag.query.filter_by(slug=tag_slug).first()
    if tag:
        return q.filter(Article.tags.any(Tag.id == tag.id))
    return q


def _build_articles_query(query, status, category, source_id, date_from, date_to, impact_min, impact_max, tag_slug):
    """Build the SQLAlchemy query for articles with all filters applied."""
    from models import Article

    q = Article.query.options(
        joinedload(Article.source),
        joinedload(Article.tags),
    ).order_by(Article.created_at.desc())

    if query:
        escaped_query = _escape_like_pattern(query)
        if _query_looks_like_url(query):
            q = q.filter(Article.original_url.ilike(f"%{escaped_query}%", escape="\\"))
        else:
            q = q.filter(Article.original_title.ilike(f"%{escaped_query}%", escape="\\"))

    if status:
        q = q.filter_by(pipeline_status=status)
    if category:
        q = q.filter_by(category=category)
    if source_id:
        try:
            q = q.filter_by(source_id=int(source_id))
        except ValueError:
            pass

    date_errors = []
    if date_from:
        dt_from, err = _parse_date_filter(date_from, "date_from")
        if err:
            date_errors.append(err)
        elif dt_from:
            q = q.filter(Article.created_at >= dt_from)
    if date_to:
        dt_to, err = _parse_date_filter(date_to, "date_to")
        if err:
            date_errors.append(err)
        elif dt_to:
            q = q.filter(Article.created_at <= dt_to)

    q = _apply_numeric_filter(q, Article.impact_score, impact_min, ">=")
    q = _apply_numeric_filter(q, Article.impact_score, impact_max, "<=")
    q = _apply_tag_filter(q, tag_slug)

    return q, date_errors


def _parse_date_filter(date_str, field_name):
    """Parse a date string and return datetime with UTC timezone.

    Returns tuple of (datetime or None, error_message or None).
    """
    from datetime import datetime, timezone

    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt, None
    except ValueError:
        logger.warning("Invalid %s filter: %s", field_name, date_str)
        return None, f"Invalid {field_name.replace('_', ' ')}: {date_str}"


def _render_articles_response(articles, has_next, next_page, page, total_count,
                               query, status, category, source_id, date_from, date_to,
                               impact_min, impact_max, tag_slug, sources, is_htmx=False):
    """Render the appropriate template for the articles page."""
    from models import Tag

    categories = _admin_categories()

    if is_htmx:
        return render_template(
            "admin/partials/articles_table.html",
            articles=articles,
            has_next=has_next,
            next_page=next_page,
            page=page,
            total_count=total_count,
            query=query,
            status=status,
            category=category,
            source_id=source_id,
            date_from=date_from,
            date_to=date_to,
            impact_min=impact_min,
            impact_max=impact_max,
            tag_slug=tag_slug,
            categories=categories,
            sources=sources,
        )

    all_tags = Tag.query.order_by(Tag.name).all()

    return render_template(
        "admin/articles.html",
        articles=articles,
        has_next=has_next,
        next_page=next_page,
        page=page,
        total_count=total_count,
        query=query,
        status=status,
        category=category,
        source_id=source_id,
        date_from=date_from,
        date_to=date_to,
        impact_min=impact_min,
        impact_max=impact_max,
        tag_slug=tag_slug,
        categories=categories,
        sources=sources,
        all_tags=all_tags,
    )


@admin_bp.route("/articles")
@require_auth
def articles():
    from models import Source
    from services.pagination import paginate_query

    page = max(1, request.args.get("page", 1, type=int))
    query = request.args.get("q", "", type=str).strip()
    status = request.args.get("status", "", type=str).strip()
    category = request.args.get("category", "", type=str).strip()
    source_id = request.args.get("source_id", "", type=str).strip()
    date_from = request.args.get("date_from", "", type=str).strip()
    date_to = request.args.get("date_to", "", type=str).strip()
    impact_min = request.args.get("impact_min", "", type=str).strip()
    impact_max = request.args.get("impact_max", "", type=str).strip()
    tag_slug = request.args.get("tag", "", type=str).strip()

    q, date_errors = _build_articles_query(
        query, status, category, source_id, date_from, date_to, impact_min, impact_max, tag_slug,
    )

    per_page = PER_PAGE_ADMIN_ARTICLES
    total_count = q.count()
    articles, has_next, next_page = paginate_query(q, page, per_page)

    # Get sources for filter dropdown
    sources = Source.query.order_by(Source.name).all()

    for err in date_errors:
        flash(err, "warning")

    is_htmx = bool(request.headers.get("HX-Request"))
    return _render_articles_response(
        articles, has_next, next_page, page, total_count,
        query, status, category, source_id, date_from, date_to,
        impact_min, impact_max, tag_slug, sources, is_htmx,
    )


def _parse_final_article(article):
    """Parse the final_article JSON from an article.

    Returns tuple of (parsed_dict, original_dict_or_none).
    """
    if not article.final_article:
        return {}, None
    try:
        fa = json.loads(article.final_article)
        return fa, fa
    except (json.JSONDecodeError, TypeError):
        return {}, None


def _process_edit_form(article, form_data, original_fa):
    """Process the edit form data and update the article's final_article.

    Returns the updated final_article dict.
    """
    from constants import (
        IMPACT_SCORE_MAX,
        IMPACT_SCORE_MIN,
        VALID_PIPELINE_STATUSES,
    )

    fa = dict(original_fa) if original_fa else {}

    fa["headline"] = _sanitize_field(form_data.get("headline", "").strip(), MAX_HEADLINE_LENGTH)
    fa["tldr"] = _sanitize_field(form_data.get("tldr", "").strip(), MAX_TLDR_LENGTH)
    fa["why_it_matters"] = _sanitize_field(form_data.get("why_it_matters", "").strip(), MAX_WHY_IT_MATTERS_LENGTH)
    fa["body"] = _sanitize_field(form_data.get("body", "").strip(), MAX_BODY_LENGTH)
    fa["what_to_watch"] = _sanitize_field(form_data.get("what_to_watch", "").strip(), MAX_WHAT_TO_WATCH_LENGTH)

    key_points_raw = _sanitize_field(form_data.get("key_points", "").strip(), MAX_KEY_POINTS_LENGTH)
    if key_points_raw:
        fa["key_points"] = [
            kp.strip() for kp in key_points_raw.split("\n") if kp.strip()
        ]
    else:
        fa["key_points"] = []

    tags_raw = _sanitize_field(form_data.get("tags", "").strip(), MAX_TAGS_LENGTH)
    if tags_raw:
        fa["tags"] = [t.strip().lower() for t in tags_raw.split(",") if t.strip()]
    else:
        fa["tags"] = []

    # Preserve structured fields not editable in the form
    for preserve_key in ("citations", "original_attribution"):
        if original_fa.get(preserve_key):
            fa[preserve_key] = original_fa[preserve_key]

    # Validate category
    new_category = form_data.get("category", article.category).strip()
    valid_categories = set(_admin_categories())
    if new_category in valid_categories:
        article.category = new_category

    # Validate pipeline_status
    new_status = form_data.get(
        "pipeline_status", article.pipeline_status,
    ).strip()
    if new_status in VALID_PIPELINE_STATUSES:
        article.pipeline_status = new_status

    # Validate impact_score
    impact_raw = form_data.get("impact_score", "")
    if impact_raw.strip():
        try:
            article.impact_score = max(
                IMPACT_SCORE_MIN, min(IMPACT_SCORE_MAX, int(impact_raw)),
            )
        except ValueError:
            pass

    return fa, new_category, new_status


def _invalidate_article_caches(article_id):
    """Invalidate response caches for an article."""
    try:
        from services.cache import get_response_cache

        cache = get_response_cache()
        cache.invalidate_prefix("pub:index")
        cache.invalidate_prefix("pub:topic")
        cache.invalidate_prefix("pub:rss_feed")
        cache.invalidate(f"pub:article_detail:{article_id}")
    except Exception as e:
        logger.warning("Failed to invalidate article cache: %s", e)


def _save_article_edit(article, fa, new_category, new_status):
    """Save the edited article and log the action.

    Returns (success, error_response).
    """
    from extensions import db

    try:
        db.session.commit()
        log_admin_action(
            "article_edit",
            target_type="article",
            target_id=article.id,
            details={
                "original_title": article.original_title,
                "category": new_category,
                "pipeline_status": new_status,
            },
            category="article",
        )
        return True, None
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Failed to save article %s", article.id)
        return False, render_template(
            "admin/article_edit.html",
            article=article,
            fa=fa,
            categories=_admin_categories(),
            error="Failed to save changes. Please try again.",
        ), 500


@admin_bp.route("/articles/<int:article_id>/edit", methods=["GET", "POST"])
@require_auth
@validate_csrf_json
def edit_article(article_id):
    from extensions import db
    from models import Article

    article = db.get_or_404(Article, article_id)

    if request.method == "POST":
        # Parse final_article JSON and update fields
        fa, original_fa = _parse_final_article(article)

        # Create version snapshot of OLD content before overwriting
        from services.article import create_article_version

        create_article_version(article, change_reason="admin_edit", changed_by="admin")

        fa, new_category, new_status = _process_edit_form(article, request.form, original_fa or {})

        article.final_article = json.dumps(fa)

        success, error_response = _save_article_edit(article, fa, new_category, new_status)
        if not success:
            return error_response

        _invalidate_article_caches(article.id)

        return redirect(url_for("admin.articles"))

    # Parse current final_article for form
    fa, _ = _parse_final_article(article)

    return render_template(
        "admin/article_edit.html",
        article=article,
        fa=fa,
        categories=_admin_categories(),
    )


@admin_bp.route("/articles/<int:article_id>/original")
@require_auth
def view_original_article(article_id):
    from extensions import db
    from models import Article

    article = db.get_or_404(Article, article_id)

    if not article.original_ai_article:
        return jsonify({"error": "No original AI version available"}), 404

    return article.original_ai_article, 200, {"Content-Type": "application/json"}


@admin_bp.route("/articles/<int:article_id>/versions")
@require_auth
def article_versions(article_id):
    from extensions import db
    from models import Article
    from services.article import get_article_versions, parse_article_json

    article = db.get_or_404(Article, article_id)
    parse_article_json(article)
    versions = get_article_versions(article_id)

    return render_template(
        "admin/article_versions.html",
        article=article,
        versions=versions,
    )


@admin_bp.route(
    "/articles/<int:article_id>/versions/<int:version_id>/rollback", methods=["POST"],
)
@require_auth
def rollback_article(article_id, version_id):
    from extensions import db
    from models import Article, ArticleVersion
    from services.article import create_article_version

    article = db.get_or_404(Article, article_id)
    version = db.get_or_404(ArticleVersion, version_id)

    if version.article_id != article_id:
        return jsonify({"error": "Version does not belong to this article"}), 400

    # Create a version snapshot of current state before rollback
    create_article_version(article, change_reason="pre_rollback", changed_by="admin")

    # Restore from version
    article.final_article = version.final_article
    article.original_ai_article = version.original_ai_article

    # Create version record for the rollback itself
    create_article_version(article, change_reason="rollback", changed_by="admin")

    try:
        db.session.commit()
        log_admin_action(
            "article_rollback",
            target_type="article",
            target_id=article_id,
            details={"version_id": version_id, "version_number": version.version_number},
            category="article",
        )
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception(
            "Failed to rollback article %s to version %s", article_id, version_id,
        )
        return jsonify({"error": "Rollback failed"}), 500

    logger.info(
        "Rolled back article %s to version %s", article_id, version.version_number,
    )
    return redirect(url_for("admin.article_versions", article_id=article_id))


@admin_bp.route("/articles/<int:article_id>/delete", methods=["POST"])
@require_auth
@validate_csrf_json
def delete_article(article_id):
    from extensions import db
    from models import Article

    article = db.get_or_404(Article, article_id)

    try:
        db.session.delete(article)
        db.session.commit()
        log_admin_action(
            "article_delete",
            target_type="article",
            target_id=article_id,
            details={"original_title": article.original_title},
            category="article",
        )
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Failed to delete article %s", article_id)
        return jsonify({"error": "Failed to delete article"}), 500

    if request.headers.get("HX-Request"):
        return "", 200
    return redirect(url_for("admin.articles"))


@admin_bp.route("/articles/<int:article_id>/reprocess", methods=["POST"])
@validate_csrf_json
@require_auth
def reprocess_article(article_id):
    from extensions import db
    from models import Article
    from tasks import research_article, select_article, write_article

    stage = request.form.get("from_stage", "select")
    if stage not in _REPROCESS_STAGES:
        return jsonify(
            {
                "error": f"Invalid stage. Must be one of: {', '.join(sorted(_REPROCESS_STAGES))}",
            },
        ), 400

    cfg = _REPROCESS_STAGES[stage]
    article = db.get_or_404(Article, article_id)

    article.pipeline_status = cfg["status"]
    article.pipeline_started_at = datetime.now(timezone.utc)
    for field in cfg["fields"]:
        setattr(article, field, None)
    article.retry_count = 0
    article.total_retries = 0
    article.last_error = None

    try:
        db.session.commit()
        log_admin_action(
            "article_reprocess",
            target_type="article",
            target_id=article_id,
            details={"stage": stage},
            category="pipeline",
        )
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Failed to reprocess article %s (%s stage)", article_id, stage)
        return jsonify({"error": "Failed to reprocess article"}), 500

    try:
        from extensions import get_redis
        redis_client = get_redis()
        pattern = f"ainews:article:stage_failures:{article_id}:*"
        for key in redis_client.scan_iter(match=pattern):
            redis_client.delete(key)
    except redis.exceptions.RedisError:
        logger.warning("Failed to clear stage failure keys for article %s", article_id)

    _TASKS = {
        "select_article": select_article,
        "research_article": research_article,
        "write_article": write_article,
    }
    request_id = getattr(g, "request_id", None)
    headers = {"request_id": request_id} if request_id else None
    task_name = cfg["task"]
    signed_kwargs = get_signed_kwargs(task_name, (article.id,), {})
    _TASKS[task_name].apply_async(args=(article.id,), kwargs=signed_kwargs, headers=headers)

    return redirect(url_for("admin.articles"))
