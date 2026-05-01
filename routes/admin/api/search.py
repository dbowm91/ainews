import logging

from routes.admin import admin_api_bp, require_auth
from routes.admin.api.utils import api_response

logger = logging.getLogger(__name__)


@admin_api_bp.route("/search/analytics")
@require_auth
def search_analytics():
    """Return top queries and zero-result queries."""
    from sqlalchemy import func

    from models import SearchQuery

    top_queries = (
        SearchQuery.query.with_entities(
            SearchQuery.__table__.c.query.label("query"),
            func.count(SearchQuery.id).label("search_count"),
            func.sum(SearchQuery.results_count).label("total_results"),
        )
        .group_by(SearchQuery.__table__.c.query)
        .order_by(func.count(SearchQuery.id).desc())
        .limit(20)
        .all()
    )

    zero_result_queries = (
        SearchQuery.query.filter(SearchQuery.results_count == 0)
        .with_entities(
            SearchQuery.__table__.c.query.label("query"),
            SearchQuery.created_at.label("last_searched"),
        )
        .order_by(SearchQuery.created_at.desc())
        .limit(50)
        .all()
    )

    return api_response(
        data={
            "top_queries": [
                {
                    "query": row.query,
                    "search_count": row.search_count,
                    "total_results": row.total_results or 0,
                }
                for row in top_queries
            ],
            "zero_result_queries": [
                {"query": row.query, "last_searched": row.last_searched.isoformat() if row.last_searched else None}
                for row in zero_result_queries
            ],
        },
    )