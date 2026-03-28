import logging
from flask import render_template, request, redirect, url_for, jsonify
from sqlalchemy.exc import SQLAlchemyError
from routes.admin import admin_bp, require_auth
from constants import PER_PAGE_ADMIN_ARTICLES, PipelineStatus

logger = logging.getLogger(__name__)


@admin_bp.route("/review")
@require_auth
def review_queue():
    from models import Article
    from services.utils import paginate_query

    page = max(1, request.args.get("page", 1, type=int))
    per_page = PER_PAGE_ADMIN_ARTICLES

    q = Article.query.filter_by(pipeline_status=PipelineStatus.REVIEW).order_by(
        Article.impact_score.desc()
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
            total_review=total_review,
        )
    return render_template(
        "admin/review.html",
        articles=articles,
        has_next=has_next,
        next_page=next_page,
        page=page,
        total_review=total_review,
    )


@admin_bp.route("/review/<int:article_id>/approve", methods=["POST"])
@require_auth
def approve_article(article_id):
    from models import Article
    from extensions import db

    article = Article.query.get_or_404(article_id)
    if article.pipeline_status != PipelineStatus.REVIEW:
        return jsonify({"message": "Article is not in review"}), 400

    article.pipeline_status = PipelineStatus.DONE
    article.retry_count = 0
    article.last_error = None
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Failed to approve article %s", article_id)
        return jsonify({"message": "Failed to approve article"}), 500

    logger.info(f"Approved article {article_id}: {article.original_title[:50]}")

    if request.headers.get("HX-Request"):
        return "", 200
    return redirect(url_for("admin.review_queue"))


@admin_bp.route("/review/<int:article_id>/reject", methods=["POST"])
@require_auth
def reject_article(article_id):
    from models import Article
    from extensions import db

    article = Article.query.get_or_404(article_id)
    if article.pipeline_status != PipelineStatus.REVIEW:
        return jsonify({"message": "Article is not in review"}), 400

    article.pipeline_status = PipelineStatus.SKIPPED
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Failed to reject article %s", article_id)
        return jsonify({"message": "Failed to reject article"}), 500

    logger.info(f"Rejected article {article_id}: {article.original_title[:50]}")

    if request.headers.get("HX-Request"):
        return "", 200
    return redirect(url_for("admin.review_queue"))
