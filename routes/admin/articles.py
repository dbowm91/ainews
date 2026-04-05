import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse
from flask import flash, render_template, request, redirect, url_for, jsonify
from sqlalchemy.exc import SQLAlchemyError
from routes.admin import admin_bp, require_auth
from services.utils import get_admin_categories as _admin_categories
from services.article import _escape_like_pattern
from constants import PER_PAGE_ADMIN_ARTICLES, PipelineStatus

logger = logging.getLogger(__name__)

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


@admin_bp.route("/articles")
@require_auth
def articles():
    from models import Article, Source, Tag
    from services.utils import paginate_query
    from datetime import datetime, timezone

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

    q = Article.query.order_by(Article.created_at.desc())

    if query:
        if _query_looks_like_url(query):
            escaped_query = _escape_like_pattern(query)
            q = q.filter(Article.original_url.ilike(f"%{escaped_query}%", escape="\\"))
        else:
            escaped_query = _escape_like_pattern(query)
            q = q.filter(
                Article.original_title.ilike(f"%{escaped_query}%", escape="\\")
            )
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
        try:
            dt_from = datetime.fromisoformat(date_from)
            if dt_from.tzinfo is None:
                dt_from = dt_from.replace(tzinfo=timezone.utc)
            q = q.filter(Article.created_at >= dt_from)
        except ValueError:
            logger.warning("Invalid date_from filter: %s", date_from)
            date_errors.append(f"Invalid start date: {date_from}")
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            if dt_to.tzinfo is None:
                dt_to = dt_to.replace(tzinfo=timezone.utc)
            q = q.filter(Article.created_at <= dt_to)
        except ValueError:
            logger.warning("Invalid date_to filter: %s", date_to)
            date_errors.append(f"Invalid end date: {date_to}")
    if impact_min:
        try:
            q = q.filter(Article.impact_score >= int(impact_min))
        except ValueError:
            pass
    if impact_max:
        try:
            q = q.filter(Article.impact_score <= int(impact_max))
        except ValueError:
            pass
    if tag_slug:
        tag = Tag.query.filter_by(slug=tag_slug).first()
        if tag:
            q = q.filter(Article.tags.any(Tag.id == tag.id))

    per_page = PER_PAGE_ADMIN_ARTICLES
    total_count = q.count()
    articles, has_next, next_page = paginate_query(q, page, per_page)

    # Get sources for filter dropdown
    sources = Source.query.order_by(Source.name).all()

    for err in date_errors:
        flash(err, "warning")

    if request.headers.get("HX-Request"):
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
            categories=_admin_categories(),
            sources=sources,
        )

    categories = _admin_categories()
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


@admin_bp.route("/articles/<int:article_id>/edit", methods=["GET", "POST"])
@require_auth
def edit_article(article_id):
    from models import Article
    from extensions import db

    article = db.get_or_404(Article, article_id)

    if request.method == "POST":
        from constants import (
            VALID_PIPELINE_STATUSES,
            IMPACT_SCORE_MIN,
            IMPACT_SCORE_MAX,
        )

        # Parse final_article JSON and update fields
        fa = {}
        if article.final_article:
            try:
                fa = json.loads(article.final_article)
            except (json.JSONDecodeError, TypeError):
                fa = {}
        original_fa = dict(fa)  # snapshot before overwriting

        fa["headline"] = request.form.get("headline", "").strip()
        fa["tldr"] = request.form.get("tldr", "").strip()
        fa["why_it_matters"] = request.form.get("why_it_matters", "").strip()
        fa["body"] = request.form.get("body", "").strip()
        fa["what_to_watch"] = request.form.get("what_to_watch", "").strip()

        key_points_raw = request.form.get("key_points", "").strip()
        if key_points_raw:
            fa["key_points"] = [
                kp.strip() for kp in key_points_raw.split("\n") if kp.strip()
            ]
        else:
            fa["key_points"] = []

        tags_raw = request.form.get("tags", "").strip()
        if tags_raw:
            fa["tags"] = [t.strip().lower() for t in tags_raw.split(",") if t.strip()]
        else:
            fa["tags"] = []

        # Preserve structured fields not editable in the form
        for preserve_key in ("citations", "original_attribution"):
            if original_fa.get(preserve_key):
                fa[preserve_key] = original_fa[preserve_key]

        # Create version snapshot of OLD content before overwriting
        from services.article import create_article_version

        create_article_version(article, change_reason="admin_edit", changed_by="admin")

        article.final_article = json.dumps(fa)

        # Validate category
        new_category = request.form.get("category", article.category).strip()
        valid_categories = set(_admin_categories())
        if new_category in valid_categories:
            article.category = new_category

        # Validate pipeline_status
        new_status = request.form.get(
            "pipeline_status", article.pipeline_status
        ).strip()
        if new_status in VALID_PIPELINE_STATUSES:
            article.pipeline_status = new_status

        # Validate impact_score
        impact_raw = request.form.get("impact_score", "")
        if impact_raw.strip():
            try:
                article.impact_score = max(
                    IMPACT_SCORE_MIN, min(IMPACT_SCORE_MAX, int(impact_raw))
                )
            except ValueError:
                pass

        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            logger.exception("Failed to save article %s", article_id)
            return render_template(
                "admin/article_edit.html",
                article=article,
                fa=fa,
                categories=_admin_categories(),
                error="Failed to save changes. Please try again.",
            ), 500

        try:
            from services.cache import get_response_cache

            cache = get_response_cache()
            cache.invalidate_prefix("index")
            cache.invalidate_prefix("topic")
            cache.invalidate_prefix("rss")
        except Exception:
            pass

        return redirect(url_for("admin.articles"))

    # Parse current final_article for form
    fa = {}
    if article.final_article:
        try:
            fa = json.loads(article.final_article)
        except (json.JSONDecodeError, TypeError):
            pass

    return render_template(
        "admin/article_edit.html",
        article=article,
        fa=fa,
        categories=_admin_categories(),
    )


@admin_bp.route("/articles/<int:article_id>/original")
@require_auth
def view_original_article(article_id):
    from models import Article
    from extensions import db

    article = db.get_or_404(Article, article_id)

    if not article.original_ai_article:
        return jsonify({"error": "No original AI version available"}), 404

    return article.original_ai_article, 200, {"Content-Type": "application/json"}


@admin_bp.route("/articles/<int:article_id>/versions")
@require_auth
def article_versions(article_id):
    from models import Article
    from extensions import db
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
    "/articles/<int:article_id>/versions/<int:version_id>/rollback", methods=["POST"]
)
@require_auth
def rollback_article(article_id, version_id):
    from models import Article, ArticleVersion
    from extensions import db
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
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception(
            "Failed to rollback article %s to version %s", article_id, version_id
        )
        return jsonify({"error": "Rollback failed"}), 500

    logger.info(
        "Rolled back article %s to version %s", article_id, version.version_number
    )
    return redirect(url_for("admin.article_versions", article_id=article_id))


@admin_bp.route("/articles/<int:article_id>/delete", methods=["POST"])
@require_auth
def delete_article(article_id):
    from models import Article
    from extensions import db

    article = db.get_or_404(Article, article_id)

    try:
        db.session.delete(article)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Failed to delete article %s", article_id)
        return jsonify({"error": "Failed to delete article"}), 500

    if request.headers.get("HX-Request"):
        return "", 200
    return redirect(url_for("admin.articles"))


@admin_bp.route("/articles/<int:article_id>/reprocess", methods=["POST"])
@require_auth
def reprocess_article(article_id):
    from models import Article
    from extensions import db
    from tasks import select_article, research_article, write_article

    stage = request.form.get("from_stage", "select")
    if stage not in _REPROCESS_STAGES:
        return jsonify(
            {
                "error": f"Invalid stage. Must be one of: {', '.join(sorted(_REPROCESS_STAGES))}"
            }
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
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Failed to reprocess article %s (%s stage)", article_id, stage)
        return jsonify({"error": "Failed to reprocess article"}), 500

    _TASKS = {
        "select_article": select_article,
        "research_article": research_article,
        "write_article": write_article,
    }
    _TASKS[cfg["task"]].delay(article.id)

    return redirect(url_for("admin.articles"))
