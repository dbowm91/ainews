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


def _selector_score(selector_result) -> float | None:
    """Extract the selector's score from a raw ``selector_result`` value.

    ``Article.selector_result`` is a JSON column that is NULL for articles the
    selector never scored (anything rejected before selection). When present
    it is a mapping with a ``score`` key. Defensive parsing keeps a malformed
    value from breaking the whole dashboard.
    """
    if not isinstance(selector_result, dict):
        return None
    score = selector_result.get("score")
    if score is None:
        return None
    try:
        return float(score)
    except (TypeError, ValueError):
        return None


def _safe_summary(builder, label: str) -> dict:
    """Build a summary payload, degrading to an empty one on failure.

    The audit and memory panels are additions to the dashboard, not the
    dashboard itself. If one of them cannot be read the page still has to
    render.
    """
    try:
        return builder()
    except Exception as e:  # noqa: BLE001
        logger.warning("Dashboard %s summary failed: %s", label, e)
        return {}


def _audit_payload() -> dict:
    """Return the pipeline audit summary as a JSON-safe payload.

    The dashboard stats blob is stored in the response cache as JSON, so
    every value in it has to survive ``json.dumps``. Timestamps are
    formatted here rather than handed to the template as datetimes.
    """
    from services.pipeline_audit import dashboard_summary

    summary = dashboard_summary()

    def _event(event) -> dict:  # type: ignore[no-untyped-def]
        return {
            "id": event.id,
            "article_id": event.article_id,
            "stage": event.stage,
            "level": event.level,
            "message": event.message,
            "error": event.error,
            "created_at": event.created_at.strftime("%b %d %H:%M:%S") if event.created_at else "",
        }

    return {
        "total_events": summary.total_events,
        "error_count": summary.error_count,
        "warning_count": summary.warning_count,
        "articles_touched": summary.articles_touched,
        "recent_events": [_event(e) for e in summary.recent_events],
        "recent_errors": [_event(e) for e in summary.recent_errors],
        "stage_summaries": [
            {
                "stage": s.stage,
                "label": s.label,
                "total": s.total,
                "warnings": s.warnings,
                "errors": s.errors,
            }
            for s in summary.stage_summaries
        ],
    }


def _memory_payload() -> dict:
    """Return the trend-memory summary as a JSON-safe payload."""
    from services.trend_memory import memory_summary

    summary = memory_summary()

    return {
        "total": summary.total,
        "high": summary.high,
        "medium": summary.medium,
        "low": summary.low,
        "expired": summary.expired,
        "topics": [
            {"topic": t.topic, "count": t.count, "high": t.high}
            for t in summary.topics
        ],
        "recent": [
            {
                "id": int(m.id),
                "topic": m.topic,
                "signal": (m.signal or "")[:140],
                "importance": int(m.importance or 0),
                "created_at": m.created_at.strftime("%b %d %H:%M") if m.created_at else "",
            }
            for m in summary.recent
        ],
    }


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

    # The recent-articles table renders title, topic, status, selection score,
    # impact and creation time. Every one of those columns has to be selected
    # here: the template reads them off the row, so a column that is not in
    # the SELECT list renders as an empty cell rather than raising.
    recent = (
        db.session.query(
            Article.id,
            Article.original_title,
            Article.category,
            Article.pipeline_status,
            Article.selector_result,
            Article.impact_score,
            Article.created_at,
            Source.name,
        )
        .outerjoin(Source, Article.source_id == Source.id)
        .order_by(Article.created_at.desc())
        .limit(15)
        .all()
    )

    try:
        llm_info = get_provider_info()
    except Exception as e:  # noqa: BLE001
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
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to get pipeline health stats: %s", e)

    stats = {
        "pipeline_stats": pipeline_stats,
        "sources": [{"id": s[0], "name": s[1], "active": s[2]} for s in sources_query],
        "article_counts": article_counts,
        "recent": [
            {
                "id": a[0],
                "original_title": a[1],
                "category": a[2],
                "pipeline_status": a[3],
                "selector_score": _selector_score(a[4]),
                "impact_score": a[5],
                # The dashboard stats blob is stored in the response cache as
                # JSON, which cannot carry a datetime. Format it here.
                "created_at": a[6].strftime("%b %d %H:%M") if a[6] else "",
                "source_name": a[7],
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
        "audit": _safe_summary(_audit_payload, "audit"),
        "memory": _safe_summary(_memory_payload, "memory"),
    }
    cache.set(cache_key, stats, 180)
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
    except Exception as e:  # noqa: BLE001
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
        audit=cached.get("audit") or {},
        memory=cached.get("memory") or {},
    )
