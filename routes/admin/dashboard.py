import logging

import redis.exceptions
from flask import render_template
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from routes.admin import admin_bp, require_auth

logger = logging.getLogger(__name__)


@admin_bp.route("/dead-letters")
@require_auth
def dead_letters() -> str:
    from flask import request

    from constants import PipelineStatus
    from models import Article

    failed_page = max(1, request.args.get("failed_page", 1, type=int))
    stuck_page = max(1, request.args.get("stuck_page", 1, type=int))
    per_page = 20

    failed_count = (
        Article.query.filter_by(pipeline_status=PipelineStatus.FAILED).count()
    )
    failed_total_pages = (failed_count + per_page - 1) // per_page

    dead_letter_articles = (
        Article.query.filter_by(pipeline_status=PipelineStatus.FAILED)
        .options(joinedload(Article.source))
        .order_by(Article.updated_at.desc())
        .offset((failed_page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    stuck_count = (
        Article.query.filter(
            Article.pipeline_status.in_(
                [
                    PipelineStatus.RESEARCHING,
                    PipelineStatus.WRITING,
                    PipelineStatus.EDITING,
                    PipelineStatus.PENDING,
                ],
            ),
        )
        .count()
    )
    stuck_total_pages = (stuck_count + per_page - 1) // per_page

    stuck_articles = (
        Article.query.filter(
            Article.pipeline_status.in_(
                [
                    PipelineStatus.RESEARCHING,
                    PipelineStatus.WRITING,
                    PipelineStatus.EDITING,
                    PipelineStatus.PENDING,
                ],
            ),
        )
        .options(joinedload(Article.source))
        .order_by(Article.updated_at.asc())
        .offset((stuck_page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return render_template(
        "admin/dead_letters.html",
        dead_letter_articles=dead_letter_articles,
        stuck_articles=stuck_articles,
        failed_count=failed_count,
        stuck_count=stuck_count,
        failed_page=failed_page,
        stuck_page=stuck_page,
        failed_total_pages=failed_total_pages,
        stuck_total_pages=stuck_total_pages,
        per_page=per_page,
    )


def _compute_dashboard_stats():
    from extensions import db
    from models import Article, PipelineRun, Source
    from services.cache import get_response_cache
    from services.llm import get_provider_info
    from services.pipeline_monitor import get_all_stages_stats
    from services.subscribers import get_subscriber_stats

    cache = get_response_cache()
    cache_key = "admin:dashboard:stats"
    cached = cache.get(cache_key)
    if cached:
        return cached

    pipeline_stats = dict(
        db.session.query(Article.pipeline_status, func.count(Article.id))
        .group_by(Article.pipeline_status)
        .all(),
    )

    sources_with_counts = (
        db.session.query(Source.id, Source.name, Source.active, func.count(Article.id))
        .outerjoin(Article, Article.source_id == Source.id)
        .group_by(Source.id, Source.name, Source.active)
        .all()
    )
    source_count = len(sources_with_counts)
    sources_query = [(s[0], s[1], s[2]) for s in sources_with_counts]
    article_counts = {s[0]: s[3] for s in sources_with_counts}

    recent = (
        db.session.query(Article.id, Article.original_title, Article.pipeline_status, Source.name)
        .outerjoin(Source, Article.source_id == Source.id)
        .order_by(Article.created_at.desc())
        .limit(15)
        .all()
    )

    try:
        llm_info = get_provider_info()
    except Exception as e:
        logger.warning("Provider info failed: %s", e)
        llm_info = {"status": "error", "error": str(e)}

    total_subs, subs_by_type, _ = get_subscriber_stats(db)

    recent_runs_with_running = (
        db.session.query(
            PipelineRun.id,
            PipelineRun.status,
            PipelineRun.started_at,
            PipelineRun.finished_at,
            PipelineRun.error_message,
        )
        .order_by(PipelineRun.started_at.desc())
        .limit(5)
        .all()
    )
    recent_runs = recent_runs_with_running
    running_count = sum(1 for r in recent_runs_with_running if r[1] == "running")
    if running_count == 0:
        running_count = PipelineRun.query.filter_by(status="running").count()

    pipeline_health = None
    try:
        from extensions import get_redis
        redis_client = get_redis()
        redis_client.ping()
        pipeline_health = get_all_stages_stats(minutes=15)
    except Exception as e:
        logger.warning("Failed to get pipeline health stats: %s", e)

    stats = {
        "pipeline_stats": pipeline_stats,
        "sources": [{"id": s[0], "name": s[1], "active": s[2]} for s in sources_query],
        "article_counts": article_counts,
        "recent": [
            {
                "id": a[0],
                "title": a[1],
                "pipeline_status": a[2],
                "source_name": a[3],
            }
            for a in recent
        ],
        "llm_info": llm_info,
        "total_subs": total_subs,
        "subs_by_type": subs_by_type,
        "recent_runs": [
            {
                "id": r[0],
                "status": r[1],
                "started_at": r[2].isoformat() if r[2] else None,
                "finished_at": r[3].isoformat() if r[3] else None,
                "error_message": r[4],
            }
            for r in recent_runs
        ],
        "running_count": running_count,
        "pipeline_health": pipeline_health,
        "source_count": source_count,
    }
    cache.set(cache_key, stats, 60)
    return stats


@admin_bp.route("/")
@require_auth
def dashboard() -> str:
    from extensions import get_redis

    redis_ok = False
    try:
        redis_client = get_redis()
        redis_client.ping()
        redis_ok = True
    except redis.exceptions.RedisError:
        pass
    except Exception as e:
        logger.warning("Redis check failed: %s", e)

    cached = _compute_dashboard_stats()

    return render_template(
        "admin/dashboard.html",
        pipeline_stats=cached["pipeline_stats"],
        sources=cached["sources"],
        article_counts=cached["article_counts"],
        recent=cached["recent"],
        llm_info=cached["llm_info"],
        redis_ok=redis_ok,
        total_subs=cached["total_subs"],
        subs_by_type=cached["subs_by_type"],
        recent_runs=cached["recent_runs"],
        running_count=cached["running_count"],
        pipeline_health=cached.get("pipeline_health"),
        source_count=cached.get("source_count"),
    )
