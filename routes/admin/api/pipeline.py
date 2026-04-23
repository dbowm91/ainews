import logging

from flask import jsonify, request, Response
from routes.admin import admin_bp, require_auth
from constants import PipelineStatus

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

    days = request.args.get("days", 7, type=int)
    days = max(1, min(days, 30))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    articles = (
        Article.query.filter(
            Article.published_at.isnot(None),
            Article.published_at >= cutoff,
        )
        .order_by(Article.published_at.desc())
        .all()
    )

    total_count = len(articles)
    if total_count == 0:
        return jsonify(
            {
                "period_days": days,
                "article_count": 0,
                "sla": {
                    "crawl_to_select_avg": None,
                    "crawl_to_select_p50": None,
                    "crawl_to_select_p95": None,
                    "select_to_publish_avg": None,
                    "select_to_publish_p50": None,
                    "select_to_publish_p95": None,
                    "crawl_to_publish_avg": None,
                    "crawl_to_publish_p50": None,
                    "crawl_to_publish_p95": None,
                },
                "histogram": get_metrics().get_metrics().get("histograms", {}).get(
                    "pipeline_sla_seconds", {}
                ),
            }
        )

    crawl_to_select = []
    select_to_publish = []
    crawl_to_publish = []

    for a in articles:
        if a.crawled_at and a.selected_at:
            delta = (a.selected_at - a.crawled_at).total_seconds()
            if delta >= 0:
                crawl_to_select.append(delta)
        if a.selected_at and a.published_at:
            delta = (a.published_at - a.selected_at).total_seconds()
            if delta >= 0:
                select_to_publish.append(delta)
        if a.crawled_at and a.published_at:
            delta = (a.published_at - a.crawled_at).total_seconds()
            if delta >= 0:
                crawl_to_publish.append(delta)

    sorted_c2s = sorted(crawl_to_select) if crawl_to_select else []
    sorted_s2p = sorted(select_to_publish) if select_to_publish else []
    sorted_c2p = sorted(crawl_to_publish) if crawl_to_publish else []

    def _stats(sorted_data):
        n = len(sorted_data)
        return {
            "avg": round(sum(sorted_data) / n, 1),
            "p50": round(sorted_data[n // 2], 1),
            "p95": round(sorted_data[int(n * 0.95)], 1),
        }

    c2s_stats = _stats(sorted_c2s)
    s2p_stats = _stats(sorted_s2p)
    c2p_stats = _stats(sorted_c2p)

    return jsonify(
        {
            "period_days": days,
            "article_count": total_count,
            "sla": {
                "crawl_to_select_avg": c2s_stats["avg"],
                "crawl_to_select_p50": c2s_stats["p50"],
                "crawl_to_select_p95": c2s_stats["p95"],
                "select_to_publish_avg": s2p_stats["avg"],
                "select_to_publish_p50": s2p_stats["p50"],
                "select_to_publish_p95": s2p_stats["p95"],
                "crawl_to_publish_avg": c2p_stats["avg"],
                "crawl_to_publish_p50": c2p_stats["p50"],
                "crawl_to_publish_p95": c2p_stats["p95"],
            },
            "histogram": get_metrics().get_metrics().get("histograms", {}).get(
                "pipeline_sla_seconds", {}
            ),
        }
    )
