import logging
from datetime import datetime, timezone

from flask import Response, request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from constants import VALID_PIPELINE_STATUSES, VALID_TRANSITIONS, PipelineStatus
from routes import limit_content_length
from routes.admin import admin_api_bp, require_auth
from routes.admin.api.utils import api_response
from routes.decorators import validate_csrf_json
from schemas.admin import ArticleIdsParams, BulkArticleRequest
from services.task_security import get_signed_kwargs

logger = logging.getLogger(__name__)


def _escape_fts5_string(query: str) -> str:
    """Escape double quotes for FTS5 queries by doubling them."""
    return query.replace('"', '""')


@admin_api_bp.route("/articles/ids", methods=["GET"])
@require_auth
def get_article_ids():
    """Return article IDs matching the current filter params for bulk selection.

    Query params: q, status, category, source_id, date_from, date_to, impact_min, impact_max, tag
    Returns: {"ids": [1, 2, 3], "count": 3}
    """
    from urllib.parse import urlparse

    from models import Article, Tag
    from services.article import _escape_like_pattern

    try:
        params = ArticleIdsParams(
            q=request.args.get("q", "", type=str).strip(),
            status=request.args.get("status", "", type=str).strip() or None,
            category=request.args.get("category", "", type=str).strip() or None,
            source_id=request.args.get("source_id", type=int),
            date_from=request.args.get("date_from", "", type=str).strip() or None,
            date_to=request.args.get("date_to", "", type=str).strip() or None,
            impact_min=request.args.get("impact_min", type=int),
            impact_max=request.args.get("impact_max", type=int),
            tag=request.args.get("tag", "", type=str).strip() or None,
        )
    except Exception as e:
        return api_response(error=str(e), status=400)

    query = params.q
    status = params.status or ""
    category = params.category or ""
    source_id = str(params.source_id) if params.source_id is not None else ""
    date_from = params.date_from or ""
    date_to = params.date_to or ""
    impact_min = str(params.impact_min) if params.impact_min is not None else ""
    impact_max = str(params.impact_max) if params.impact_max is not None else ""
    tag_slug = params.tag or ""

    def _query_looks_like_url(q_str):
        if not q_str:
            return False
        if q_str.startswith("http://") or q_str.startswith("https://"):
            return True
        parsed = urlparse(q_str)
        return bool(parsed.scheme and parsed.netloc)

    q = Article.query.options(joinedload(Article.source), joinedload(Article.tags))

    if query:
        # Try FTS5 search first, fall back to ILIKE if FTS5 unavailable
        fts_results = None
        try:
            from sqlalchemy import text

            from extensions import db

            # Build FTS5 query - escape special chars
            safe_query = (
                query.replace('"', "'")
                .replace("*", "")
                .replace(":", " ")
                .replace("(", " ")
                .replace(")", " ")
                .replace("-", " ")
                .replace("+", " ")
            )
            words = [w.strip() for w in safe_query.split() if w.strip()]
            if words:
                fts_query = " AND ".join(f'"{w}"' for w in words)
                if _query_looks_like_url(query):
                    fts_query = f'original_url:"{_escape_fts5_string(query)}"'
                sql = text(
                    "SELECT rowid FROM articles_admin_fts WHERE articles_admin_fts MATCH :q",
                )
                result = db.session.execute(sql, {"q": fts_query}).fetchall()
                fts_results = [row[0] for row in result]
        except Exception:
            logger.debug("FTS5 search unavailable, falling back to ILIKE")

        if fts_results is not None:
            q = q.filter(Article.id.in_(fts_results))
        elif _query_looks_like_url(query):
            escaped = _escape_like_pattern(query)
            q = q.filter(Article.original_url.ilike(f"%{escaped}%", escape="\\"))
        else:
            escaped = _escape_like_pattern(query)
            q = q.filter(Article.original_title.ilike(f"%{escaped}%", escape="\\"))
    if status:
        q = q.filter_by(pipeline_status=status)
    if category:
        q = q.filter_by(category=category)
    if source_id:
        try:
            q = q.filter_by(source_id=int(source_id))
        except ValueError:
            pass
    if date_from:
        try:
            dt = datetime.fromisoformat(date_from)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            q = q.filter(Article.created_at >= dt)
        except ValueError:
            logger.warning("Invalid date_from filter: %s", date_from)
    if date_to:
        try:
            dt = datetime.fromisoformat(date_to)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            q = q.filter(Article.created_at <= dt)
        except ValueError:
            logger.warning("Invalid date_to filter: %s", date_to)
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

    ids = [row.id for row in q.with_entities(Article.id).limit(1000).all()]
    return api_response(data={"ids": ids, "count": len(ids)})


@admin_api_bp.route("/articles/counts-by-status", methods=["GET"])
@require_auth
def get_article_counts_by_status():
    """Return article counts grouped by pipeline status."""
    from extensions import db
    from models import Article
    from sqlalchemy import func

    results = (
        db.session.query(Article.pipeline_status, func.count(Article.id))
        .group_by(Article.pipeline_status)
        .all()
    )
    counts = {status: count for status, count in results}
    return api_response(data={"counts": counts, "total": sum(counts.values())})


def _bulk_set_category(articles, validated, db) -> tuple[Response, int] | Response:
    from schemas.topic import load_topics
    from services.audit import log_admin_action

    new_category = (validated.category or "").strip()
    if not new_category:
        return api_response(error="category is required", status=400)
    topics = load_topics().topics
    if new_category not in topics:
        return api_response(error=f"Unknown category: {new_category}", status=400)
    try:
        from services.cache import get_response_cache
        cache = get_response_cache()
        for article in articles:
            article.category = new_category
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return api_response(error="Failed to update articles", status=500)

    for article in articles:
        cache.invalidate(f"pub:article_detail:{article.id}")
    cache.invalidate_prefix("pub:index")
    cache.invalidate_prefix("pub:topic")
    cache.invalidate_prefix("articles:list")
    cache.invalidate_prefix("pub:related")
    try:
        log_admin_action(
            "article_bulk_set_category",
            target_type="article",
            category="article",
            details={
                "count": len(articles),
                "ids": [a.id for a in articles],
                "category": new_category,
            },
        )
    except Exception:
        logger.warning("Audit logging failed for article_bulk_set_category")
    return api_response(meta={"message": f"Updated {len(articles)} articles to category '{new_category}'"})


def _bulk_reprocess(articles, db) -> tuple[Response, int] | Response:
    from services.audit import log_admin_action
    from services.cache import get_response_cache
    from tasks.select import select_article

    cache = get_response_cache()

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
        return api_response(error="Failed to reset articles for reprocessing", status=500)

    try:
        import redis.exceptions

        from extensions import get_redis
        redis_client = get_redis()
        for article in articles:
            pattern = f"ainews:article:stage_failures:{article.id}:*"
            for key in redis_client.scan_iter(match=pattern):
                redis_client.delete(key)
    except redis.exceptions.RedisError:
        logger.warning("Failed to clear stage failure keys during reprocess")

    for article in articles:
        cache.invalidate(f"pub:article_detail:{article.id}")
    cache.invalidate_prefix("pub:index")
    cache.invalidate_prefix("pub:topic")
    cache.invalidate_prefix("articles:list")
    cache.invalidate_prefix("pub:related")

    dispatched = 0
    failed_ids = []
    for article in articles:
        try:
            signed_kwargs = get_signed_kwargs("select_article", (article.id,), {})
            select_article.apply_async(args=(article.id,), kwargs=signed_kwargs)
            dispatched += 1
        except Exception as e:
            logger.warning(
                "Failed to dispatch reprocess for article %s: %s", article.id, e,
            )
            failed_ids.append(article.id)

    if failed_ids:
        try:
            log_admin_action(
                "article_bulk_reprocess",
                target_type="article",
                category="pipeline",
                details={
                    "count": len(articles),
                    "dispatched": dispatched,
                    "failed_ids": failed_ids,
                },
            )
        except Exception:
            logger.warning("Audit logging failed for article_bulk_reprocess")
        return api_response(
            data={
                "message": f"Partial success: {dispatched} dispatched, {len(failed_ids)} failed",
                "dispatched": dispatched,
                "failed_article_ids": failed_ids,
            },
            status=207,
        )

    try:
        log_admin_action(
            "article_bulk_reprocess",
            target_type="article",
            category="pipeline",
            details={
                "count": len(articles),
                "dispatched": dispatched,
            },
        )
    except Exception:
        logger.warning("Audit logging failed for article_bulk_reprocess")
    return api_response(
        meta={"message": f"Reprocessing {len(articles)} articles ({dispatched} dispatched)"},
    )


def _bulk_add_tags(articles, validated, db) -> tuple[Response, int] | Response:
    from services.audit import log_admin_action
    from tasks.edit import clear_tag_cache
    from tasks.pipeline import _assign_tags

    tag_names = validated.tags or []
    if not tag_names or not isinstance(tag_names, list):
        return api_response(error="tags must be a non-empty list", status=400)

    try:
        from services.cache import get_response_cache
        cache = get_response_cache()
        _assign_tags(articles, tag_names, db)
        db.session.commit()
    except Exception as e:
        logger.warning("Bulk add tags failed: %s", e)
        db.session.rollback()
        return api_response(error="Failed to add tags", status=500)

    for article in articles:
        cache.invalidate(f"pub:article_detail:{article.id}")
    cache.invalidate_prefix("pub:index")
    cache.invalidate_prefix("pub:topic")
    cache.invalidate_prefix("articles:list")
    cache.invalidate_prefix("pub:related")

    clear_tag_cache()
    try:
        log_admin_action(
            "article_bulk_add_tags",
            target_type="article",
            category="article",
            details={
                "count": len(articles),
                "ids": [a.id for a in articles],
                "tags": tag_names,
            },
        )
    except Exception:
        logger.warning("Audit logging failed for article_bulk_add_tags")
    return api_response(
        meta={"message": f"Added {min(len(tag_names), 10)} tags to {len(articles)} articles"},
    )


@admin_api_bp.route("/articles/bulk", methods=["POST"])
@require_auth
@validate_csrf_json
@limit_content_length(32768)
def bulk_article_operations() -> tuple[Response, int] | Response:
    """Bulk operations on articles: delete, change status, change category, reprocess, add tags."""
    from extensions import db
    from models import Article

    data = request.get_json(silent=True)
    if not data:
        return api_response(error="Invalid JSON body", status=400)

    try:
        validated = BulkArticleRequest(**data)
    except Exception as e:
        return api_response(error=str(e), status=400)

    article_ids = validated.article_ids
    action = validated.action

    try:
        from services.validation import validate_bulk_ids
        article_ids = validate_bulk_ids(article_ids)
    except ValueError as e:
        return api_response(error=str(e), status=400)

    articles = (
        Article.query
        .filter(Article.id.in_(article_ids))
        .options(joinedload(Article.source), joinedload(Article.tags))
        .all()
    )
    if not articles:
        return api_response(error="No articles found", status=404)

    if action == "delete":
        try:
            for article in articles:
                db.session.delete(article)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            return api_response(error="Failed to delete articles", status=500)
        try:
            from services.audit import log_admin_action
            from services.cache import get_response_cache

            cache = get_response_cache()
            for article in articles:
                cache.invalidate(f"pub:article_detail:{article.id}")
            cache.invalidate_prefix("articles:list")
            cache.invalidate_prefix("pub:related")
            log_admin_action(
                "article_bulk_delete",
                target_type="article",
                category="article",
                details={"count": len(articles), "ids": article_ids},
            )
        except Exception:
            logger.warning("Cache invalidation or audit logging failed")
        return api_response(meta={"message": f"Deleted {len(articles)} articles"})

    elif action == "set_status":
        new_status = validated.status or ""
        if new_status not in VALID_PIPELINE_STATUSES:
            return api_response(
                error=f"Invalid status. Must be one of: {', '.join(sorted(VALID_PIPELINE_STATUSES))}",
                status=400,
            )

        try:
            for article in articles:
                current_status = article.pipeline_status
                valid_next = VALID_TRANSITIONS.get(current_status, frozenset())
                if new_status not in valid_next:
                    return api_response(
                        error=f"Invalid transition from '{current_status}' to '{new_status}'. "
                        f"Valid transitions from '{current_status}': {', '.join(sorted(valid_next)) if valid_next else 'none'}",
                        status=400,
                    )
                article.pipeline_status = new_status
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            return api_response(error="Failed to update articles", status=500)
        try:
            from services.audit import log_admin_action
            from services.cache import get_response_cache

            cache = get_response_cache()
            for article in articles:
                cache.invalidate(f"pub:article_detail:{article.id}")
            cache.invalidate_prefix("articles:list")
            cache.invalidate_prefix("pub:related")
            log_admin_action(
                "article_bulk_set_status",
                target_type="article",
                category="article",
                details={
                    "count": len(articles),
                    "ids": article_ids,
                    "status": new_status,
                },
            )
        except Exception:
            logger.warning("Cache invalidation or audit logging failed")
        return api_response(
            meta={"message": f"Updated {len(articles)} articles to '{new_status}'"},
        )

    elif action == "set_category":
        return _bulk_set_category(articles, validated, db)

    elif action == "reprocess":
        return _bulk_reprocess(articles, db)

    elif action == "add_tags":
        return _bulk_add_tags(articles, validated, db)

    else:
        return api_response(
            error="Invalid action. Must be one of: delete, set_status, set_category, reprocess, add_tags",
            status=400,
        )
