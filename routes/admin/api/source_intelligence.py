import logging

from flask import Response, request

from routes.admin import admin_api_bp, require_auth
from routes.admin.api.utils import api_response

logger = logging.getLogger(__name__)


@admin_api_bp.route("/sources/performance", methods=["GET"])
@require_auth
def source_performance() -> tuple[Response, int]:
    """Get performance metrics for all sources within a time window."""
    days_param = request.args.get("days", "7")
    try:
        days = int(days_param)
        days = max(1, min(days, 90))
    except (ValueError, TypeError):
        days = 7

    limit_param = request.args.get("limit")
    limit = None
    if limit_param is not None:
        try:
            limit = int(limit_param)
            limit = max(1, min(limit, 100))
        except (ValueError, TypeError):
            pass

    from services.source_intelligence import get_source_performance

    try:
        results = get_source_performance(days=days, limit=limit)
        return api_response(
            data={
                "period_days": days,
                "sources": [
                    {
                        "source_key": s.source_key,
                        "name": s.name,
                        "active": s.active,
                        "health": s.health,
                        "articles_created": s.articles_created,
                        "selected": s.selected,
                        "published": s.published,
                        "review": s.review,
                        "skipped": s.skipped,
                        "failed": s.failed,
                        "selection_rate": s.selection_rate,
                        "publish_rate": s.publish_rate,
                        "avg_impact_score": s.avg_impact_score,
                        "p50_latency": s.p50_latency,
                        "p95_latency": s.p95_latency,
                        "last_success_at": s.last_success_at,
                        "last_error": s.last_error,
                        "topics": s.topics,
                        "recommendations": s.recommendations,
                    }
                    for s in results
                ],
                "meta": {
                    "days": days,
                    "limit": limit,
                    "count": len(results),
                },
            }
        )
    except (ValueError, KeyError, AttributeError, RuntimeError) as e:
        logger.error("source_performance failed: %s", e)
        return api_response(error=str(e), status=500)


@admin_api_bp.route("/topics/coverage", methods=["GET"])
@require_auth
def topic_coverage() -> tuple[Response, int]:
    """Get topic coverage distribution across sources."""
    days_param = request.args.get("days", "30")
    try:
        days = int(days_param)
        days = max(1, min(days, 90))
    except (ValueError, TypeError):
        days = 30

    from services.source_intelligence import get_topic_coverage

    try:
        coverage = get_topic_coverage(days=days)
        return api_response(
            data={
                "period_days": days,
                "topics": coverage,
                "meta": {
                    "days": days,
                    "topic_count": len(coverage),
                },
            }
        )
    except (ValueError, KeyError, AttributeError, RuntimeError) as e:
        logger.error("topic_coverage failed: %s", e)
        return api_response(error=str(e), status=500)


@admin_api_bp.route("/sources/recommendations", methods=["GET"])
@require_auth
def source_recommendations() -> tuple[Response, int]:
    """Get actionable recommendations for sources."""
    days_param = request.args.get("days", "30")
    try:
        days = int(days_param)
        days = max(1, min(days, 90))
    except (ValueError, TypeError):
        days = 30

    from services.source_intelligence import get_source_recommendations

    try:
        recommendations = get_source_recommendations(days=days)
        return api_response(
            data={
                "period_days": days,
                "recommendations": [
                    {
                        "source_key": r.source_key,
                        "name": r.name,
                        "recommendation": r.recommendation,
                        "reason": r.reason,
                        "severity": r.severity,
                    }
                    for r in recommendations
                ],
                "meta": {
                    "days": days,
                    "count": len(recommendations),
                },
            }
        )
    except (ValueError, KeyError, AttributeError, RuntimeError) as e:
        logger.error("source_recommendations failed: %s", e)
        return api_response(error=str(e), status=500)