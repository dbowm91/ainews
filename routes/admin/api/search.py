import logging

from flask import request

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


@admin_api_bp.route("/search/articles", methods=["GET"])
@require_auth
def search_articles():
    """Search articles with optional hybrid mode for admin.

    Query params:
        q: Search query string (required)
        mode: Search mode - "fts" or "hybrid" (default "fts")
        category: Optional category filter
        page: Page number (default 1)
        per_page: Results per page (default 20, max 100)

    Returns: SearchPage with items, total, page, per_page, vector_available
    """
    from services.search.hybrid import search_articles

    query = request.args.get("q", "", type=str).strip()
    if not query:
        return api_response(error="q parameter is required", status=400)

    mode = request.args.get("mode", "fts", type=str).strip()
    if mode not in ("fts", "hybrid"):
        return api_response(error="mode must be 'fts' or 'hybrid'", status=400)

    category = request.args.get("category", "", type=str).strip() or None
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("per_page", 20, type=int)))

    try:
        results = search_articles(
            query,
            mode=mode,
            category=category,
            page=page,
            per_page=per_page,
        )
        return api_response(
            data={
                "items": [
                    {
                        "id": item.id,
                        "fts_rank": item.fts_rank,
                        "vector_score": item.vector_score,
                        "combined_score": item.combined_score,
                    }
                    for item in results.items
                ],
                "total": results.total,
                "page": results.page,
                "per_page": results.per_page,
                "vector_available": results.vector_available,
            }
        )
    except Exception as e:  # noqa: BLE001 - search failure returns error response
        logger.warning("Admin article search failed: %s", e)
        return api_response(error="Search failed", status=500)