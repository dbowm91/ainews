import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import Response, request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from pydantic import ValidationError

from constants import VALID_PIPELINE_STATUSES, VALID_TRANSITIONS, PipelineStatus
from routes import limit_content_length
from routes.admin import admin_api_bp, require_auth
from routes.admin.api.utils import api_response
from routes.decorators import csrf_for_session_auth
from schemas.admin import ArticleIdsParams, BulkArticleRequest
from services.task_security import get_signed_kwargs

logger = logging.getLogger(__name__)


def _query_looks_like_url(q_str):
    if not q_str:
        return False
    if q_str.startswith("http://") or q_str.startswith("https://"):
        return True
    parsed = urlparse(q_str)
    return bool(parsed.scheme and parsed.netloc)


def _parse_article_ids_params(request):
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
        return params, None
    except ValidationError as e:
        return None, api_response(error=str(e), status=400)


def _parse_date(date_str):
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _apply_source_filter(q, source_id):
    try:
        return q.filter_by(source_id=int(source_id))
    except ValueError:
        return q


def _apply_impact_filter(q, impact_val, op):
    from models import Article
    try:
        val = int(impact_val)
        if op == 'ge':
            return q.filter(Article.impact_score >= val)
        elif op == 'le':
            return q.filter(Article.impact_score <= val)
    except ValueError:
        return q


def _apply_tag_filter(q, tag_slug):
    from models import Article, Tag
    tag = Tag.query.filter_by(slug=tag_slug).first()
    if tag:
        return q.filter(Article.tags.any(Tag.id == tag.id))
    return q


def _apply_query_filter(q, query):
    from models import Article
    from services.article import _escape_like_pattern
    try:
        from services.search import get_article_search_provider
        provider = get_article_search_provider()
        fts_results = provider.search_admin(query, url_search=_query_looks_like_url(query))
    except (ImportError, AttributeError, SQLAlchemyError):
        logger.debug("FTS5 search unavailable, falling back to ILIKE")
        fts_results = None

    if fts_results is not None:
        return q.filter(Article.id.in_(fts_results))
    elif _query_looks_like_url(query):
        escaped = _escape_like_pattern(query)
        return q.filter(Article.original_url.ilike(f"%{escaped}%", escape="\\"))
    else:
        escaped = _escape_like_pattern(query)
        return q.filter(Article.original_title.ilike(f"%{escaped}%", escape="\\"))


def _build_article_ids_query(params):
    from models import Article

    q = Article.query.options(joinedload(Article.source), joinedload(Article.tags))

    query = params.q
    status = params.status or ""
    category = params.category or ""
    source_id = params.source_id
    date_from = params.date_from
    date_to = params.date_to
    impact_min = params.impact_min
    impact_max = params.impact_max
    tag_slug = params.tag or ""

    if query:
        q = _apply_query_filter(q, query)
    if status:
        q = q.filter_by(pipeline_status=status)
    if category:
        q = q.filter_by(category=category)
    if source_id is not None:
        q = _apply_source_filter(q, source_id)
    if date_from:
        dt = _parse_date(date_from)
        if dt:
            q = q.filter(Article.created_at >= dt)
        else:
            logger.warning("Invalid date_from filter: %s", date_from)
    if date_to:
        dt = _parse_date(date_to)
        if dt:
            q = q.filter(Article.created_at <= dt)
        else:
            logger.warning("Invalid date_to filter: %s", date_to)
    if impact_min is not None:
        q = _apply_impact_filter(q, impact_min, 'ge')
    if impact_max is not None:
        q = _apply_impact_filter(q, impact_max, 'le')
    if tag_slug:
        q = _apply_tag_filter(q, tag_slug)

    return q


@admin_api_bp.route("/articles/ids", methods=["GET"])
@require_auth
def get_article_ids():
    """Return article IDs matching the current filter params for bulk selection.

    Query params: q, status, category, source_id, date_from, date_to, impact_min, impact_max, tag
    Returns: {"ids": [1, 2, 3], "count": 3}
    """
    from models import Article

    params, error = _parse_article_ids_params(request)
    if error:
        return error

    q = _build_article_ids_query(params)
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
    counts = dict(results)
    return api_response(data={"counts": counts, "total": sum(counts.values())})


def _bulk_set_category(articles, validated, db) -> tuple[Response, int] | Response:
    from models import Article
    from schemas.topic import load_topics
    from services.audit import log_admin_action

    new_category = (validated.category or "").strip()
    if not new_category:
        return api_response(error="category is required", status=400)
    topics = load_topics().topics
    if new_category not in topics:
        return api_response(error=f"Unknown category: {new_category}", status=400)
    try:
        from sqlalchemy import update

        from services.cache import get_response_cache

        cache = get_response_cache()
        article_ids = [a.id for a in articles]
        stmt = update(Article).where(Article.id.in_(article_ids)).values(category=new_category)
        db.session.execute(stmt)
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
    except Exception:  # noqa: BLE001 fail-closed for audit logging
        logger.warning("Audit logging failed for article_bulk_set_category")
    return api_response(meta={"message": f"Updated {len(articles)} articles to category '{new_category}'"})


def _bulk_reprocess(articles, db) -> tuple[Response, int] | Response:
    from models import Article
    from services.audit import log_admin_action
    from services.cache import get_response_cache
    from tasks.select import select_article

    cache = get_response_cache()

    try:
        from sqlalchemy import update

        article_ids = [a.id for a in articles]
        now = datetime.now(timezone.utc)
        stmt = (
            update(Article)
            .where(Article.id.in_(article_ids))
            .values(
                pipeline_status=PipelineStatus.PENDING,
                pipeline_started_at=now,
                retry_count=0,
                total_retries=0,
                last_error=None,
                selector_result=None,
                research_brief=None,
                draft_article=None,
                final_article=None,
            )
        )
        db.session.execute(stmt)
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
        except Exception as e:  # noqa: BLE001 non-critical task dispatch
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
        except Exception:  # noqa: BLE001 fail-closed for audit logging
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
    except Exception:  # noqa: BLE001 fail-closed for audit logging
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
    except SQLAlchemyError as e:
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
    except Exception:  # noqa: BLE001 fail-closed for audit logging
        logger.warning("Audit logging failed for article_bulk_add_tags")
    return api_response(
        meta={"message": f"Added {min(len(tag_names), 10)} tags to {len(articles)} articles"},
    )


def _bulk_delete(articles, article_ids, db) -> tuple[Response, int] | Response:
    from models import Article
    from sqlalchemy import delete

    try:
        stmt = delete(Article).where(Article.id.in_(article_ids))
        db.session.execute(stmt)
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
    except Exception:  # noqa: BLE001 fail-closed for cache/audit
        logger.warning("Cache invalidation or audit logging failed")
    return api_response(meta={"message": f"Deleted {len(articles)} articles"})


def _bulk_set_status(articles, validated, article_ids, db) -> tuple[Response, int] | Response:
    from models import Article
    from sqlalchemy import update

    new_status = validated.status or ""
    if new_status not in VALID_PIPELINE_STATUSES:
        return api_response(
            error=f"Invalid status. Must be one of: {', '.join(sorted(VALID_PIPELINE_STATUSES))}",
            status=400,
        )

    for article in articles:
        current_status = article.pipeline_status
        valid_next = VALID_TRANSITIONS.get(current_status, frozenset())
        if new_status not in valid_next:
            return api_response(
                error=f"Invalid transition from '{current_status}' to '{new_status}'. "
                f"Valid transitions from '{current_status}': {', '.join(sorted(valid_next)) if valid_next else 'none'}",
                status=400,
            )
    try:
        stmt = update(Article).where(Article.id.in_(article_ids)).values(pipeline_status=new_status)
        db.session.execute(stmt)
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
    except Exception:  # noqa: BLE001 fail-closed for cache/audit
        logger.warning("Cache invalidation or audit logging failed")
    return api_response(
        meta={"message": f"Updated {len(articles)} articles to '{new_status}'"},
    )


def _hx_trigger(
    result: tuple[Response, int] | Response, event: str = "articles-bulk-updated"
) -> tuple[Response, int] | Response:
    """Annotate a JSON api_response with HTMX trigger headers for table refresh."""
    if not request.headers.get("HX-Request") or not isinstance(result, tuple):
        return result
    if len(result) != 2:
        return result
    resp, status_code = result
    try:
        resp.headers["HX-Trigger"] = event
        resp.headers["HX-Reswap"] = "none"
    except (AttributeError, TypeError):
        return result
    return resp, status_code


@admin_api_bp.route("/articles/bulk", methods=["POST"])
@require_auth
@csrf_for_session_auth
@limit_content_length(32768)
def bulk_article_operations() -> tuple[Response, int] | Response:
    """Bulk operations on articles: delete, change status, change category, reprocess, add tags."""
    from extensions import db
    from models import Article

    data = request.get_json(silent=True)
    if data is None:
        # Allow form-encoded HTMX submissions for the bulk-action UI.
        data = request.form.to_dict()
    if not data:
        return api_response(error="Invalid request body", status=400)

    # HTMX submissions encode article_ids as repeated fields or comma-separated.
    if "article_ids" in data and isinstance(data["article_ids"], str):
        raw = data["article_ids"]
        if "," in raw:
            data["article_ids"] = [int(x) for x in raw.split(",") if x.strip()]
        else:
            try:
                data["article_ids"] = [int(raw)]
            except (TypeError, ValueError):
                data["article_ids"] = []

    try:
        validated = BulkArticleRequest(**data)
    except ValidationError as e:
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
        .options(joinedload(Article.source), joinedload(Article.tags))  # type: ignore[arg-type]
        .all()
    )
    if not articles:
        return api_response(error="No articles found", status=404)

    actions = {
        "delete": lambda: _bulk_delete(articles, article_ids, db),
        "set_status": lambda: _bulk_set_status(articles, validated, article_ids, db),
        "set_category": lambda: _bulk_set_category(articles, validated, db),
        "reprocess": lambda: _bulk_reprocess(articles, db),
        "add_tags": lambda: _bulk_add_tags(articles, validated, db),
    }
    if action not in actions:
        return api_response(
            error="Invalid action. Must be one of: delete, set_status, set_category, reprocess, add_tags",
            status=400,
        )

    result = actions[action]()
    return _hx_trigger(result)


@admin_api_bp.route("/articles/<int:article_id>/pipeline", methods=["POST"])
@require_auth
@csrf_for_session_auth
def trigger_article_pipeline(article_id: int) -> tuple[Response, int] | Response:
    """Trigger a pipeline stage for a specific article."""
    from models import Article

    from extensions import db

    article = db.get_or_404(Article, article_id)
    data = request.get_json(silent=True) or {}
    stage = data.get("stage")

    stage_to_task = {
        "select": ("tasks.select", "select_article"),
        "research": ("tasks.research", "research_article"),
        "write": ("tasks.write", "write_article"),
        "edit": ("tasks.edit", "edit_article"),
    }

    if stage and stage not in stage_to_task:
        return api_response(
            error=f"Invalid stage. Must be one of: {', '.join(stage_to_task.keys())}",
            status=400,
        )

    target_stage = stage or article.pipeline_status
    if target_stage not in stage_to_task:
        return api_response(
            error=f"Cannot trigger pipeline for article in status: {target_stage}",
            status=400,
        )

    module_path, task_name = stage_to_task[target_stage]
    task_fn = getattr(__import__(module_path, fromlist=[task_name]), task_name)

    from logging_config import get_request_id

    headers = {}
    request_id = get_request_id()
    if request_id:
        headers["request_id"] = request_id

    try:
        signed_kwargs = get_signed_kwargs(task_name, (article_id,), {"run_id": None})
    except Exception:  # noqa: BLE001 - use unsigned if security not configured
        signed_kwargs = {"article_id": article_id, "run_id": None}

    task_fn.apply_async(args=[article_id], kwargs=signed_kwargs, headers=headers)

    try:
        from services.audit import log_admin_action

        log_admin_action(
            "article_pipeline_trigger",
            target_type="article",
            target_id=article_id,
            details={"stage": target_stage},
            category="pipeline",
        )
    except Exception:  # noqa: BLE001 fail-closed for audit logging
        logger.warning("Audit logging failed for article_pipeline_trigger")

    return api_response(
        data={"article_id": article_id, "stage": target_stage, "status": "triggered"},
        meta={"message": f"Pipeline stage '{target_stage}' triggered"},
    )


@admin_api_bp.route("/articles/<int:article_id>", methods=["GET"])
@require_auth
def get_article(article_id: int) -> tuple[Response, int] | Response:
    """Get a single article by ID."""
    from models import Article

    from extensions import db

    article = db.get_or_404(Article, article_id)
    return api_response(
        data={
            "id": article.id,
            "title": article.title,
            "pipeline_status": article.pipeline_status,
            "source_id": article.source_id,
            "impact_score": article.impact_score,
            "created_at": article.created_at.isoformat() if article.created_at else None,
            "published_at": article.published_at.isoformat() if article.published_at else None,
            "final_article": article.final_article,
        }
    )


@admin_api_bp.route("/articles/<int:article_id>", methods=["PUT"])
@require_auth
@csrf_for_session_auth
def update_article(article_id: int) -> tuple[Response, int] | Response:
    """Update an article."""
    from models import Article

    from extensions import db

    article = db.get_or_404(Article, article_id)
    data = request.get_json(silent=True)
    if not data:
        return api_response(error="Invalid JSON body", status=400)

    if "title" in data:
        article.title = data["title"]
    if "impact_score" in data:
        article.impact_score = data["impact_score"]
    if "pipeline_status" in data:
        new_status = data["pipeline_status"]
        if new_status in VALID_PIPELINE_STATUSES:
            article.pipeline_status = new_status

    try:
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        return api_response(error=str(e), status=500)

    try:
        from services.audit import log_admin_action

        log_admin_action(
            "article_update",
            target_type="article",
            target_id=article_id,
            details={"title": article.title, "pipeline_status": article.pipeline_status},
            category="article",
        )
    except Exception:  # noqa: BLE001 fail-closed for audit logging
        logger.warning("Audit logging failed for article_update")

    return api_response(
        data={
            "id": article.id,
            "title": article.title,
            "pipeline_status": article.pipeline_status,
            "impact_score": article.impact_score,
        },
        meta={"message": "Article updated"},
    )


@admin_api_bp.route("/articles/<int:article_id>", methods=["DELETE"])
@require_auth
@csrf_for_session_auth
def delete_article(article_id: int) -> tuple[Response, int] | Response:
    """Delete an article."""
    from models import Article

    from extensions import db

    article = db.get_or_404(Article, article_id)
    db.session.delete(article)

    try:
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        return api_response(error=str(e), status=500)

    try:
        from services.audit import log_admin_action

        log_admin_action(
            "article_delete",
            target_type="article",
            target_id=article_id,
            details={},
            category="article",
        )
    except Exception:  # noqa: BLE001 fail-closed for audit logging
        logger.warning("Audit logging failed for article_delete")

    return api_response(meta={"message": "Article deleted"})
