import json
import logging
import threading
import redis.exceptions
from flask import render_template
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from routes.admin import admin_bp, require_auth

logger = logging.getLogger(__name__)

_dashboard_cache = {}
_dashboard_cache_lock = threading.Lock()
_DASHBOARD_CACHE_TTL = 60


def _get_dashboard_cache_key() -> str:
    return "dashboard:stats:v2"


def _get_cached_stats(redis_client):
    try:
        cached = redis_client.get(_get_dashboard_cache_key())
        if cached:
            return json.loads(cached)
    except (redis.exceptions.RedisError, json.JSONDecodeError):
        pass
    return None


def _set_cached_stats(redis_client, data):
    try:
        redis_client.setex(
            _get_dashboard_cache_key(),
            _DASHBOARD_CACHE_TTL,
            json.dumps(data),
        )
    except redis.exceptions.RedisError:
        pass


@admin_bp.route("/")
@require_auth
def dashboard():
    from models import Article, Source, PipelineRun
    from extensions import db, get_redis
    from services.llm import get_provider_info

    redis_client = None
    try:
        redis_client = get_redis()
        redis_client.ping()
    except redis.exceptions.RedisError:
        redis_client = None

    if redis_client:
        cached = _get_cached_stats(redis_client)
        if cached:
            return render_template(
                "admin/dashboard.html",
                pipeline_stats=cached["pipeline_stats"],
                sources=cached["sources"],
                article_counts=cached["article_counts"],
                recent=cached["recent"],
                llm_info=cached["llm_info"],
                redis_ok=True,
                total_subs=cached["total_subs"],
                subs_by_type=cached["subs_by_type"],
                recent_runs=cached["recent_runs"],
                running_count=cached["running_count"],
            )

    pipeline_stats = dict(
        db.session.query(Article.pipeline_status, func.count(Article.id))
        .group_by(Article.pipeline_status)
        .all()
    )

    sources = Source.query.all()
    article_counts = dict(
        db.session.query(Article.source_id, func.count(Article.id))
        .group_by(Article.source_id)
        .all()
    )

    recent = (
        Article.query.options(joinedload(Article.source))
        .order_by(Article.created_at.desc())
        .limit(15)
        .all()
    )

    try:
        llm_info = get_provider_info()
    except Exception as e:
        logger.warning("Provider info failed: %s", e)
        llm_info = {"status": "error", "error": str(e)}

    redis_ok = redis_client is not None

    from services.subscribers import get_subscriber_stats

    total_subs, subs_by_type, _ = get_subscriber_stats(db)

    recent_runs = (
        PipelineRun.query.order_by(PipelineRun.started_at.desc()).limit(5).all()
    )

    running_count = PipelineRun.query.filter_by(status="running").count()

    if redis_client:
        cache_data = {
            "pipeline_stats": pipeline_stats,
            "sources": sources,
            "article_counts": article_counts,
            "recent": recent,
            "llm_info": llm_info,
            "total_subs": total_subs,
            "subs_by_type": subs_by_type,
            "recent_runs": recent_runs,
            "running_count": running_count,
        }
        _set_cached_stats(redis_client, cache_data)

    return render_template(
        "admin/dashboard.html",
        pipeline_stats=pipeline_stats,
        sources=sources,
        article_counts=article_counts,
        recent=recent,
        llm_info=llm_info,
        redis_ok=redis_ok,
        total_subs=total_subs,
        subs_by_type=subs_by_type,
        recent_runs=recent_runs,
        running_count=running_count,
    )
