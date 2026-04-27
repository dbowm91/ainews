import logging
import redis.exceptions
from flask import render_template
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from routes.admin import admin_bp, require_auth

logger = logging.getLogger(__name__)

_DASHBOARD_CACHE_TTL = 300


def _get_dashboard_cache_key() -> str:
    return "dashboard:stats:v2"


@admin_bp.route("/dead-letters")
@require_auth
def dead_letters() -> str:
    from models import Article
    from constants import PipelineStatus
    from flask import request

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
                ]
            )
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
                ]
            )
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
    from models import Article, Source, PipelineRun
    from extensions import db
    from services.llm import get_provider_info
    from services.pipeline_monitor import get_all_stages_stats
    from services.subscribers import get_subscriber_stats

    pipeline_stats = dict(
        db.session.query(Article.pipeline_status, func.count(Article.id))
        .group_by(Article.pipeline_status)
        .all()
    )

    sources = Source.query.all()
    source_count = Source.query.count()

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

    total_subs, subs_by_type, _ = get_subscriber_stats(db)

    recent_runs = (
        PipelineRun.query.order_by(PipelineRun.started_at.desc()).limit(5).all()
    )

    running_count = PipelineRun.query.filter_by(status="running").count()

    pipeline_health = None
    try:
        from extensions import get_redis
        redis_client = get_redis()
        redis_client.ping()
        pipeline_health = get_all_stages_stats(minutes=15)
    except Exception as e:
        logger.warning("Failed to get pipeline health stats: %s", e)

    return {
        "pipeline_stats": pipeline_stats,
        "sources": [{"id": s.id, "name": s.name, "active": s.active} for s in sources],
        "article_counts": article_counts,
        "recent": [
            {
                "id": a.id,
                "title": a.original_title,
                "pipeline_status": a.pipeline_status,
                "source_name": a.source.name if a.source else None,
            }
            for a in recent
        ],
        "llm_info": llm_info,
        "total_subs": total_subs,
        "subs_by_type": subs_by_type,
        "recent_runs": [
            {
                "id": r.id,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "error_message": r.error_message,
            }
            for r in recent_runs
        ],
        "running_count": running_count,
        "pipeline_health": pipeline_health,
        "source_count": source_count,
    }


@admin_bp.route("/")
@require_auth
def dashboard() -> str:
    from extensions import get_redis
    from services.cache import get_response_cache

    redis_ok = False
    try:
        redis_client = get_redis()
        redis_client.ping()
        redis_ok = True

        cache = get_response_cache()
        cached = cache.get_or_set(
            _get_dashboard_cache_key(),
            _compute_dashboard_stats,
            _DASHBOARD_CACHE_TTL,
        )
    except redis.exceptions.RedisError:
        cached = None
    except Exception as e:
        logger.warning("Dashboard cache failed: %s", e)
        cached = None

    if cached:
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
