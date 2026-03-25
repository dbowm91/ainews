from flask import render_template, request
from datetime import datetime, timezone, timedelta
from sqlalchemy import func
from routes.admin import admin_bp, require_auth


@admin_bp.route("/metrics")
@require_auth
def metrics():
    from models import Article, ArticleMetric, Subscriber
    from extensions import db

    # Date range
    days = request.args.get("days", 30, type=int)
    days = max(1, min(days, 365))  # Clamp to 1-365
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
        .join(ArticleMetric, Article.id == ArticleMetric.article_id)
        .filter(
            ArticleMetric.page_loads > 0,
            ArticleMetric.updated_at >= cutoff,
        )
        .order_by(ArticleMetric.page_loads.desc())
        .limit(10)
        .all()
    )

    # Top articles by share clicks
    top_by_shares = (
        db.session.query(Article, ArticleMetric.share_button_clicks)
        .join(ArticleMetric, Article.id == ArticleMetric.article_id)
        .filter(
            ArticleMetric.share_button_clicks > 0,
            ArticleMetric.updated_at >= cutoff,
        )
        .order_by(ArticleMetric.share_button_clicks.desc())
        .limit(10)
        .all()
    )

    # Top articles by share link views
    top_by_link_views = (
        db.session.query(Article, ArticleMetric.share_link_views)
        .join(ArticleMetric, Article.id == ArticleMetric.article_id)
        .filter(
            ArticleMetric.share_link_views > 0,
            ArticleMetric.updated_at >= cutoff,
        )
        .order_by(ArticleMetric.share_link_views.desc())
        .limit(10)
        .all()
    )

    # Subscriber metrics
    total_subs = Subscriber.query.filter_by(active=True).count()
    subs_by_type = dict(
        db.session.query(Subscriber.newsletter_type, func.count(Subscriber.id))
        .filter_by(active=True)
        .group_by(Subscriber.newsletter_type)
        .all()
    )
    inactive_subs = Subscriber.query.filter_by(active=False).count()

    return render_template(
        "admin/metrics.html",
        totals=totals,
        top_by_views=top_by_views,
        top_by_shares=top_by_shares,
        top_by_link_views=top_by_link_views,
        days=days,
        total_subs=total_subs,
        subs_by_type=subs_by_type,
        inactive_subs=inactive_subs,
    )
