import json
import logging
from flask import render_template, request, redirect, url_for, jsonify
from sqlalchemy.exc import SQLAlchemyError
from routes.admin import admin_bp, require_auth, _admin_categories
from services.article import _escape_like_pattern
from constants import PER_PAGE_ADMIN_ARTICLES

logger = logging.getLogger(__name__)


@admin_bp.route("/articles")
@require_auth
def articles():
    from models import Article
    from services.utils import paginate_query

    page = max(1, request.args.get("page", 1, type=int))
    query = request.args.get("q", "", type=str).strip()
    status = request.args.get("status", "", type=str).strip()
    category = request.args.get("category", "", type=str).strip()

    q = Article.query.order_by(Article.created_at.desc())

    if query:
        escaped_query = _escape_like_pattern(query)
        q = q.filter(Article.original_title.ilike(f"%{escaped_query}%", escape="\\"))
    if status:
        q = q.filter_by(pipeline_status=status)
    if category:
        q = q.filter_by(category=category)

    per_page = PER_PAGE_ADMIN_ARTICLES
    articles, has_next, next_page = paginate_query(q, page, per_page)

    if request.headers.get("HX-Request"):
        return render_template(
            "admin/partials/articles_table.html",
            articles=articles,
            has_next=has_next,
            next_page=next_page,
            page=page,
            query=query,
            status=status,
            category=category,
            categories=_admin_categories(),
        )

    categories = _admin_categories()

    return render_template(
        "admin/articles.html",
        articles=articles,
        has_next=has_next,
        next_page=next_page,
        page=page,
        query=query,
        status=status,
        category=category,
        categories=categories,
    )


@admin_bp.route("/articles/<int:article_id>/edit", methods=["GET", "POST"])
@require_auth
def edit_article(article_id):
    from models import Article
    from extensions import db

    article = Article.query.get_or_404(article_id)

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

    article = Article.query.get_or_404(article_id)

    if not article.original_ai_article:
        return jsonify({"message": "No original AI version available"}), 404

    return article.original_ai_article, 200, {"Content-Type": "application/json"}


@admin_bp.route("/articles/<int:article_id>/versions")
@require_auth
def article_versions(article_id):
    from models import Article
    from services.article import get_article_versions, parse_article_json

    article = Article.query.get_or_404(article_id)
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

    article = Article.query.get_or_404(article_id)
    version = ArticleVersion.query.get_or_404(version_id)

    if version.article_id != article_id:
        return jsonify({"message": "Version does not belong to this article"}), 400

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
        return jsonify({"message": "Rollback failed"}), 500

    logger.info(f"Rolled back article {article_id} to version {version.version_number}")
    return redirect(url_for("admin.article_versions", article_id=article_id))


@admin_bp.route("/articles/<int:article_id>/delete", methods=["POST"])
@require_auth
def delete_article(article_id):
    from models import Article, Citation, ArticleMetric, ArticleVersion, article_tags
    from extensions import db

    article = Article.query.get_or_404(article_id)

    try:
        Citation.query.filter_by(article_id=article_id).delete()
        ArticleMetric.query.filter_by(article_id=article_id).delete()
        ArticleVersion.query.filter_by(article_id=article_id).delete()
        db.session.execute(
            article_tags.delete().where(article_tags.c.article_id == article_id)
        )
        db.session.delete(article)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Failed to delete article %s", article_id)
        return jsonify({"message": "Failed to delete article"}), 500

    if request.headers.get("HX-Request"):
        return "", 200
    return redirect(url_for("admin.articles"))


@admin_bp.route("/articles/<int:article_id>/reprocess", methods=["POST"])
@require_auth
def reprocess_article(article_id):
    from models import Article
    from extensions import db
    from tasks import select_article

    valid_stages = {"select", "research", "write"}
    stage = request.form.get("from_stage", "select")
    if stage not in valid_stages:
        return jsonify(
            {
                "message": f"Invalid stage. Must be one of: {', '.join(sorted(valid_stages))}"
            }
        ), 400

    article = Article.query.get_or_404(article_id)

    if stage == "select":
        article.pipeline_status = "pending"
        article.selector_result = None
        article.research_brief = None
        article.draft_article = None
        article.final_article = None
        article.original_ai_article = None
        article.retry_count = 0
        article.total_retries = 0
        article.last_error = None
        db.session.commit()
        select_article.delay(article.id)
    elif stage == "research":
        from tasks import research_article

        article.pipeline_status = "researching"
        article.research_brief = None
        article.draft_article = None
        article.final_article = None
        article.original_ai_article = None
        article.retry_count = 0
        article.total_retries = 0
        article.last_error = None
        db.session.commit()
        research_article.delay(article.id)
    elif stage == "write":
        from tasks import write_article

        article.pipeline_status = "writing"
        article.draft_article = None
        article.final_article = None
        article.original_ai_article = None
        article.retry_count = 0
        article.total_retries = 0
        article.last_error = None
        db.session.commit()
        write_article.delay(article.id)

    return redirect(url_for("admin.articles"))
