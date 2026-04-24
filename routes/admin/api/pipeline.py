import logging

from flask import jsonify, request, Response
from routes.admin import admin_bp, require_auth
from constants import PipelineStatus
from extensions import db

logger = logging.getLogger(__name__)


@admin_bp.route("/api/pipeline/stats")
@require_auth
def pipeline_stats() -> Response:
    """Get pipeline stage success/failure statistics."""
    from services.pipeline_monitor import get_all_stages_stats
    from services.metrics import get_metrics

    minutes = request.args.get("minutes", 15, type=int)
    minutes = max(1, min(minutes, 120))

    stats = get_all_stages_stats(minutes)

    metrics = get_metrics().get_metrics()
    degradation_count = metrics.get("counters", {}).get("pipeline.degradation", 0)
    multi_stage_count = metrics.get("counters", {}).get(
        "pipeline.multi_stage_degradation", 0
    )
    total_stage_completions = sum(
        s.get("success", 0) + s.get("failure", 0)
        for s in stats.get("stages", {}).values()
    )
    degradation_rate = (
        round(degradation_count / total_stage_completions * 100, 2)
        if total_stage_completions > 0
        else 0.0
    )

    stats["degradation"] = {
        "total_degradations": degradation_count,
        "multi_stage_degradations": multi_stage_count,
        "rate_percent": degradation_rate,
    }
    return jsonify(stats)


@admin_bp.route("/api/pipeline/dead-letter/stats")
@require_auth
def dead_letter_stats() -> Response:
    """Get dead letter queue statistics."""
    from models import Article
    from constants import _get_stuck_threshold_minutes
    from datetime import datetime, timezone, timedelta

    threshold = _get_stuck_threshold_minutes()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=threshold)
    stuck = Article.query.filter(
        Article.pipeline_status.in_(
            [
                PipelineStatus.RESEARCHING,
                PipelineStatus.WRITING,
                PipelineStatus.EDITING,
                PipelineStatus.PENDING,
            ]
        ),
        Article.updated_at < cutoff,
    ).count()

    failed = Article.query.filter_by(pipeline_status=PipelineStatus.FAILED).count()

    from services.metrics import get_metrics

    metrics = get_metrics().get_metrics()
    gauge_val = metrics.get("gauges", {}).get("pipeline.stuck_articles", 0)

    return jsonify(
        {
            "stuck_articles": stuck,
            "failed_articles": failed,
            "gauge_stuck": gauge_val,
        }
    )


@admin_bp.route("/api/costs")
@require_auth
def cost_summary() -> Response:
    """Get LLM cost summary from token usage metrics."""
    from services.cost_tracker import get_cost_summary

    summary = get_cost_summary()
    return jsonify(
        {
            "total_tokens": summary.total_tokens,
            "total_cost_usd": summary.total_cost_usd,
            "total_calls": summary.total_calls,
            "models": [
                {
                    "provider": m.provider,
                    "model": m.model,
                    "total_tokens": m.total_tokens,
                    "estimated_cost_usd": m.estimated_cost_usd,
                    "call_count": m.call_count,
                }
                for m in summary.models
            ],
        }
    )


@admin_bp.route("/api/sources/health")
@require_auth
def sources_health() -> Response:
    """Get health status of all sources."""
    from models import Source

    sources = Source.query.order_by(Source.name).all()
    return jsonify(
        {
            "sources": [
                {
                    "id": s.id,
                    "source_key": s.source_key,
                    "name": s.name,
                    "active": s.active,
                    "consecutive_failures": s.consecutive_failures or 0,
                    "last_success_at": s.last_success_at.isoformat()
                    if s.last_success_at
                    else None,
                    "last_error": s.last_error,
                    "disabled_at": s.last_error.isoformat() if s.last_error else None,
                }
                for s in sources
            ]
        }
    )


@admin_bp.route("/api/pipeline/sla")
@require_auth
def pipeline_sla() -> Response:
    """Return SLA metrics for article processing."""
    from models import Article
    from datetime import datetime, timezone, timedelta
    from services.metrics import get_metrics
    from sqlalchemy import func

    days = request.args.get("days", 7, type=int)
    days = max(1, min(days, 30))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    def _compute_duration_stats(session, Article, cutoff, start_col, end_col, base_filters=None):
        if base_filters is None:
            base_filters = []

        duration_expr = (func.julianday(end_col) - func.julianday(start_col)) * 86400
        base_filters = base_filters + [start_col.isnot(None), end_col.isnot(None)]

        total = session.query(func.count()).filter(*base_filters).scalar()
        if total == 0:
            return {"avg": None, "p50": None, "p95": None}

        avg = session.query(func.avg(duration_expr)).filter(*base_filters).scalar()

        p50_subq = session.query(
            duration_expr.label('duration'),
            func.row_number().over(order_by=duration_expr).label('rn'),
        ).filter(*base_filters).subquery()

        p50_offset = (total // 2) + 1
        p95_offset = max(1, int(total * 0.95))

        p50 = session.query(p50_subq.c.duration).filter(p50_subq.c.rn == p50_offset).scalar()
        p95 = session.query(p50_subq.c.duration).filter(p50_subq.c.rn == p95_offset).scalar()

        return {
            "avg": round(avg, 1) if avg else None,
            "p50": round(p50, 1) if p50 else None,
            "p95": round(p95, 1) if p95 else None,
        }

    base_filters = [Article.published_at.isnot(None), Article.published_at >= cutoff]

    c2s = _compute_duration_stats(db.session, Article, cutoff, Article.crawled_at, Article.selected_at, base_filters)
    s2p = _compute_duration_stats(db.session, Article, cutoff, Article.selected_at, Article.published_at, base_filters)
    c2p = _compute_duration_stats(db.session, Article, cutoff, Article.crawled_at, Article.published_at, base_filters)

    total_count = db.session.query(func.count(Article.id)).filter(*base_filters).scalar() or 0

    return jsonify(
        {
            "period_days": days,
            "article_count": total_count,
            "sla": {
                "crawl_to_select_avg": c2s["avg"],
                "crawl_to_select_p50": c2s["p50"],
                "crawl_to_select_p95": c2s["p95"],
                "select_to_publish_avg": s2p["avg"],
                "select_to_publish_p50": s2p["p50"],
                "select_to_publish_p95": s2p["p95"],
                "crawl_to_publish_avg": c2p["avg"],
                "crawl_to_publish_p50": c2p["p50"],
                "crawl_to_publish_p95": c2p["p95"],
            },
            "histogram": get_metrics().get_metrics().get("histograms", {}).get(
                "pipeline_sla_seconds", {}
            ),
        }
    )
