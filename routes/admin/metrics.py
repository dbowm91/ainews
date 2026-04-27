from datetime import datetime, timedelta, timezone

from flask import render_template, request
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from routes.admin import admin_bp, require_auth


@admin_bp.route("/metrics")
@require_auth
def metrics():
    from extensions import db
    from models import Article, ArticleMetric

    # Date range
    days = request.args.get("days", 30, type=int)
    days = max(1, min(days, 365))

    limit = request.args.get("limit", 20, type=int)
    limit = max(10, min(limit, 100))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Total metrics
    totals = (
        db.session.query(
            func.coalesce(func.sum(ArticleMetric.page_loads), 0),
            func.coalesce(func.sum(ArticleMetric.share_button_clicks), 0),
            func.coalesce(func.sum(ArticleMetric.share_link_views), 0),
        )
        .filter(ArticleMetric.updated_at >= cutoff)
        .first()
    )

    # Top articles by page loads
    top_by_views = (
        db.session.query(Article, ArticleMetric.page_loads)
        .options(joinedload(Article.source))
        .join(ArticleMetric, Article.id == ArticleMetric.article_id)
        .filter(
            ArticleMetric.page_loads > 0,
            ArticleMetric.updated_at >= cutoff,
        )
        .order_by(ArticleMetric.page_loads.desc())
        .limit(limit)
        .all()
    )

    # Top articles by share clicks
    top_by_shares = (
        db.session.query(Article, ArticleMetric.share_button_clicks)
        .options(joinedload(Article.source))
        .join(ArticleMetric, Article.id == ArticleMetric.article_id)
        .filter(
            ArticleMetric.share_button_clicks > 0,
            ArticleMetric.updated_at >= cutoff,
        )
        .order_by(ArticleMetric.share_button_clicks.desc())
        .limit(limit)
        .all()
    )

    # Top articles by share link views
    top_by_link_views = (
        db.session.query(Article, ArticleMetric.share_link_views)
        .options(joinedload(Article.source))
        .join(ArticleMetric, Article.id == ArticleMetric.article_id)
        .filter(
            ArticleMetric.share_link_views > 0,
            ArticleMetric.updated_at >= cutoff,
        )
        .order_by(ArticleMetric.share_link_views.desc())
        .limit(limit)
        .all()
    )

    # Subscriber metrics
    from services.subscribers import get_subscriber_stats

    total_subs, subs_by_type, inactive_subs = get_subscriber_stats(db)

    return render_template(
        "admin/metrics.html",
        totals=totals,
        top_by_views=top_by_views,
        top_by_shares=top_by_shares,
        top_by_link_views=top_by_link_views,
        days=days,
        limit=limit,
        total_subs=total_subs,
        subs_by_type=subs_by_type,
        inactive_subs=inactive_subs,
    )
