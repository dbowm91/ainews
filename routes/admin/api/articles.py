import logging
from datetime import datetime, timezone

from flask import jsonify, request, Response
from sqlalchemy.exc import SQLAlchemyError
from routes.admin import admin_bp, require_auth
from routes.decorators import validate_csrf_json
from constants import PipelineStatus, VALID_PIPELINE_STATUSES
from services.task_security import get_signed_kwargs

logger = logging.getLogger(__name__)


def _bulk_set_category(articles, data, db) -> tuple[Response, int] | Response:
    from schemas.topic import load_topics
    from services.audit import log_admin_action

    new_category = data.get("category", "").strip()
    if not new_category:
        return jsonify({"error": "category is required"}), 400
    topics = load_topics().topics
    if new_category not in topics:
        return jsonify({"error": f"Unknown category: {new_category}"}), 400
    try:
        for article in articles:
            article.category = new_category
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Failed to update articles"}), 500
    try:
        log_admin_action(
            "article_bulk_set_category",
            target_type="article",
            details={
                "count": len(articles),
                "ids": [a.id for a in articles],
                "category": new_category,
            },
        )
    except Exception:
        logger.warning("Audit logging failed for article_bulk_set_category")
    return jsonify(
        {"message": f"Updated {len(articles)} articles to category '{new_category}'"}
    )


def _bulk_reprocess(articles, db) -> tuple[Response, int] | Response:
    from tasks.select import select_article
    from services.audit import log_admin_action

    for article in articles:
        article.pipeline_status = PipelineStatus.PENDING
        article.pipeline_started_at = datetime.now(timezone.utc)
        article.retry_count = 0
        article.total_retries = 0
        article.last_error = None
        article.selector_result = None
        article.research_brief = None
        article.draft_article = None
        article.final_article = None

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Failed to reset articles for reprocessing"}), 500

    dispatched = 0
    failed_ids = []
    for article in articles:
        try:
            signed_kwargs = get_signed_kwargs("select_article", (article.id,), {})
            select_article.apply_async(args=(article.id,), kwargs=signed_kwargs)
            dispatched += 1
        except Exception as e:
            logger.warning(
                "Failed to dispatch reprocess for article %s: %s", article.id, e
            )
            failed_ids.append(article.id)

    if failed_ids:
        try:
            log_admin_action(
                "article_bulk_reprocess",
                target_type="article",
                details={
                    "count": len(articles),
                    "dispatched": dispatched,
                    "failed_ids": failed_ids,
                },
            )
        except Exception:
            logger.warning("Audit logging failed for article_bulk_reprocess")
        return jsonify(
            {
                "message": f"Partial success: {dispatched} dispatched, {len(failed_ids)} failed",
                "dispatched": dispatched,
                "failed_article_ids": failed_ids,
            }
        ), 207

    try:
        log_admin_action(
            "article_bulk_reprocess",
            target_type="article",
            details={
                "count": len(articles),
                "dispatched": dispatched,
            },
        )
    except Exception:
        logger.warning("Audit logging failed for article_bulk_reprocess")
    return jsonify(
        {"message": f"Reprocessing {len(articles)} articles ({dispatched} dispatched)"}
    )


def _bulk_add_tags(articles, data, db) -> tuple[Response, int] | Response:
    from tasks.pipeline import _assign_tags
    from tasks.edit import clear_tag_cache
    from services.audit import log_admin_action

    tag_names = data.get("tags", [])
    if not tag_names or not isinstance(tag_names, list):
        return jsonify({"error": "tags must be a non-empty list"}), 400
    if len(tag_names) > 10:
        return jsonify({"error": "Maximum 10 tags per bulk operation"}), 400

    try:
        _assign_tags(articles, tag_names, db)
        db.session.commit()
    except Exception as e:
        logger.warning("Bulk add tags failed: %s", e)
        db.session.rollback()
        return jsonify({"error": "Failed to add tags"}), 500

    clear_tag_cache()
    try:
        log_admin_action(
            "article_bulk_add_tags",
            target_type="article",
            details={
                "count": len(articles),
                "ids": [a.id for a in articles],
                "tags": tag_names,
            },
        )
    except Exception:
        logger.warning("Audit logging failed for article_bulk_add_tags")
    return jsonify(
        {"message": f"Added {min(len(tag_names), 10)} tags to {len(articles)} articles"}
    )


@admin_bp.route("/api/articles/bulk", methods=["POST"])
@require_auth
@validate_csrf_json
def bulk_article_operations() -> tuple[Response, int] | Response:
    """Bulk operations on articles: delete, change status, change category, reprocess, add tags."""
    from models import Article
    from extensions import db

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    article_ids = data.get("article_ids", [])
    action = data.get("action", "")

    if not article_ids or not isinstance(article_ids, list):
        return jsonify({"error": "article_ids must be a non-empty list"}), 400
    if len(article_ids) > 500:
        return jsonify({"error": "Maximum 500 articles per bulk operation"}), 400

    articles = Article.query.filter(Article.id.in_(article_ids)).all()
    if not articles:
        return jsonify({"error": "No articles found"}), 404

    if action == "delete":
        try:
            for article in articles:
                db.session.delete(article)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            return jsonify({"error": "Failed to delete articles"}), 500
        try:
            from services.cache import get_response_cache
            from services.audit import log_admin_action

            cache = get_response_cache()
            for article in articles:
                cache.invalidate(f"article_detail:{article.id}")
            cache.invalidate_prefix("articles:list")
            log_admin_action(
                "article_bulk_delete",
                target_type="article",
                details={"count": len(articles), "ids": article_ids},
            )
        except Exception:
            logger.warning("Cache invalidation or audit logging failed")
        return jsonify({"message": f"Deleted {len(articles)} articles"})

    elif action == "set_status":
        new_status = data.get("status", "")
        if new_status not in VALID_PIPELINE_STATUSES:
            return jsonify(
                {
                    "error": f"Invalid status. Must be one of: {', '.join(sorted(VALID_PIPELINE_STATUSES))}"
                }
            ), 400
        try:
            for article in articles:
                article.pipeline_status = new_status
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            return jsonify({"error": "Failed to update articles"}), 500
        try:
            from services.audit import log_admin_action

            log_admin_action(
                "article_bulk_set_status",
                target_type="article",
                details={
                    "count": len(articles),
                    "ids": article_ids,
                    "status": new_status,
                },
            )
        except Exception:
            logger.warning("Audit logging failed for article_bulk_set_status")
        return jsonify(
            {"message": f"Updated {len(articles)} articles to '{new_status}'"}
        )

    elif action == "set_category":
        return _bulk_set_category(articles, data, db)

    elif action == "reprocess":
        return _bulk_reprocess(articles, db)

    elif action == "add_tags":
        return _bulk_add_tags(articles, data, db)

    else:
        return jsonify(
            {
                "error": "Invalid action. Must be one of: delete, set_status, set_category, reprocess, add_tags"
            }
        ), 400
