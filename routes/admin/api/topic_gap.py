import logging

from flask import request

from routes.admin import admin_api_bp, require_auth
from routes.admin.api.utils import api_response
from services.topic_gap import get_topic_gap_report

logger = logging.getLogger(__name__)


@admin_api_bp.route("/topic-gap/reports", methods=["GET"])
@require_auth
def topic_gap_reports():
    topics_param = request.args.get("topics")
    topics = None
    if topics_param:
        topics = [t.strip() for t in topics_param.split(",") if t.strip()]

    days_param = request.args.get("days", "30")
    try:
        days = int(days_param)
        days = max(1, min(days, 365))
    except (ValueError, TypeError):
        days = 30

    try:
        reports = get_topic_gap_report(topics=topics, days=days)
        return api_response(
            data={
                "reports": [
                    {
                        "topic": r.topic,
                        "article_count_7d": r.article_count_7d,
                        "article_count_30d": r.article_count_30d,
                        "zero_result_queries": r.zero_result_queries,
                        "trend_memory_count": r.trend_memory_count,
                        "active_sources": r.active_sources,
                        "gap_score": r.gap_score,
                        "reason": r.reason,
                    }
                    for r in reports
                ],
                "meta": {
                    "topics": topics,
                    "days": days,
                    "count": len(reports),
                },
            }
        )
    except (ValueError, KeyError, AttributeError, RuntimeError) as e:
        logger.error("topic_gap_reports failed: %s", e)
        return api_response(error=str(e), status=500)