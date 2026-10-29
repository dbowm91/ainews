import logging

from flask import jsonify, redirect, render_template, request, url_for
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from constants import PER_PAGE_ADMIN_ARTICLES, PipelineStatus
from routes.admin import admin_bp, require_auth
from routes.decorators import validate_csrf_token
from services.cache import get_response_cache
from services.audit import log_admin_action

logger = logging.getLogger(__name__)


@admin_bp.route("/review")
@require_auth
def review_queue():
    from models import Article
    from services.pagination import paginate_query

    page = max(1, request.args.get("page", 1, type=int))
    per_page = PER_PAGE_ADMIN_ARTICLES

    q = (
        Article.query.options(
            joinedload(Article.source),
            joinedload(Article.tags),
            joinedload(Article.metrics),
        )
        .filter_by(pipeline_status=PipelineStatus.REVIEW)
        .order_by(Article.impact_score.desc())
    )
    total_review = q.count()
    articles, has_next, next_page = paginate_query(q, page, per_page)

    from services.article import parse_articles

    parse_articles(articles)

    if request.headers.get("HX-Request"):
        return render_template(
            "admin/partials/review_table.html",
            articles=articles,
            has_next=has_next,
            next_page=next_page,
            page=page,
            per_page=per_page,
            total_count=total_review,
        )
    return render_template(
        "admin/review.html",
        articles=articles,
        has_next=has_next,
        next_page=next_page,
        page=page,
        per_page=per_page,
        total_count=total_review,
        total_review=total_review,
    )


@admin_bp.route("/review/<int:article_id>/approve", methods=["POST"])
@validate_csrf_token
@require_auth
def approve_article(article_id):
    from extensions import db
    from models import Article

    from services.auto_review import approve_article as publish

    article = db.get_or_404(Article, article_id)
    if article.pipeline_status != PipelineStatus.REVIEW:
        return jsonify({"error": "Article is not in review"}), 400

    try:
        # The same primitive the auto-approver uses, so a human-approved
        # article and an auto-approved one end up in the same state.
        publish(article, reason="admin")
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Failed to approve article %s", article_id)
        return jsonify({"error": "Failed to approve article"}), 500

    if request.headers.get("HX-Request"):
        return "", 200
    return redirect(url_for("admin.review_queue"))


@admin_bp.route("/review/<int:article_id>/reject", methods=["POST"])
@validate_csrf_token
@require_auth
def reject_article(article_id):
    from extensions import db
    from models import Article

    article = db.get_or_404(Article, article_id)
    if article.pipeline_status != PipelineStatus.REVIEW:
        return jsonify({"error": "Article is not in review"}), 400

    article.pipeline_status = PipelineStatus.SKIPPED
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Failed to reject article %s", article_id)
        return jsonify({"error": "Failed to reject article"}), 500

    log_admin_action(
        "article_reject",
        target_type="article",
        target_id=article.id,
        details={"original_title": article.original_title, "pipeline_status": article.pipeline_status},
        category="article",
    )

    try:
        cache = get_response_cache()
        cache.invalidate_prefix("pub:index")
        cache.invalidate_prefix("pub:topic")
        cache.invalidate_prefix("pub:rss_feed")
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to invalidate article cache: %s", e)

    logger.info(
        "Rejected article %s: %s", article_id, (article.original_title or "")[:50],
    )

    if request.headers.get("HX-Request"):
        return "", 200
    return redirect(url_for("admin.review_queue"))
