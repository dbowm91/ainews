import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import jsonify, request

from extensions import db
from routes.admin import admin_api_bp, require_auth
from schemas.topic import load_topics

logger = logging.getLogger(__name__)


def _build_newsletter_type_list() -> list[str]:
    all_topics = list(load_topics().topics.keys())
    return ["main"] + all_topics


def _load_newsletters_in_window(cutoff: datetime) -> list:
    from models import Newsletter

    return (
        Newsletter.query.filter(Newsletter.generated_at >= cutoff)
        .order_by(Newsletter.generated_at.desc())
        .all()
    )


def _compute_sent_failed_counts(newsletters: list) -> tuple[int, int, dict[str, int], dict[str, int]]:

    sent_count = 0
    failed_count = 0
    sent_by_type: dict[str, int] = {}
    failed_by_type: dict[str, int] = {}

    for nl in newsletters:
        nt = nl.newsletter_type or "main"
        sent_by_type[nt] = sent_by_type.get(nt, 0)
        failed_by_type[nt] = failed_by_type.get(nt, 0)

        if nl.sent_at is not None:
            sent_count += 1
            sent_by_type[nt] += 1
        if nl.error_message is not None:
            failed_count += 1
            failed_by_type[nt] += 1

    return sent_count, failed_count, sent_by_type, failed_by_type


def _compute_retry_count(cutoff: datetime) -> int:
    from models import Newsletter
    from sqlalchemy import func

    return (
        db.session.query(func.count(Newsletter.id))
        .filter(
            Newsletter.generated_at >= cutoff,
            Newsletter.error_message.isnot(None),
            Newsletter.sent_at.isnot(None),
        )
        .scalar()
        or 0
    )


def _load_article_ids_for_newsletters(nl_ids: list[int]) -> dict[int, list[int]]:
    from models.newsletter import newsletter_articles

    if not nl_ids:
        return {}

    rows = (
        db.session.query(newsletter_articles.c.newsletter_id, newsletter_articles.c.article_id)
        .filter(newsletter_articles.c.newsletter_id.in_(nl_ids))
        .all()
    )
    result: dict[int, list[int]] = {}
    for nl_id, art_id in rows:
        if nl_id not in result:
            result[nl_id] = []
        result[nl_id].append(art_id)
    return result


def _load_click_totals(article_ids: list[int]) -> dict[int, int]:
    from models import ArticleMetric

    if not article_ids:
        return {}

    metrics = (
        db.session.query(ArticleMetric.article_id, ArticleMetric.newsletter_clicks)
        .filter(ArticleMetric.article_id.in_(article_ids))
        .all()
    )
    return {am.article_id: am.newsletter_clicks or 0 for am in metrics}


def _compute_click_count_by_type(
    newsletter_ids_by_type: dict[str, list[int]],
    article_ids_by_nl: dict[int, list[int]],
    click_totals: dict[int, int],
) -> dict[str, int]:
    click_through_by_type: dict[str, int] = {}
    for nt, nl_ids in newsletter_ids_by_type.items():
        total = 0
        for nl_id in nl_ids:
            for art_id in article_ids_by_nl.get(nl_id, []):
                total += click_totals.get(art_id, 0)
        click_through_by_type[nt] = total
    return click_through_by_type


def _load_top_clicked_articles(limit: int = 20) -> list[dict[str, Any]]:
    from models import Article, ArticleMetric

    rows = (
        db.session.query(Article, ArticleMetric.newsletter_clicks)
        .join(ArticleMetric, ArticleMetric.article_id == Article.id)
        .filter(ArticleMetric.newsletter_clicks > 0)
        .order_by(ArticleMetric.newsletter_clicks.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": article.id,
            "headline": article.original_title,
            "category": article.category,
            "newsletter_clicks": clicks,
        }
        for article, clicks in rows
    ]


def _load_subscriber_counts_by_type(all_types: list[str]) -> tuple[dict[str, int], dict[str, int]]:
    from models import Subscriber
    from sqlalchemy import func

    type_filter = Subscriber.newsletter_type.in_(all_types) if all_types else True

    active_query = (
        db.session.query(Subscriber.newsletter_type, func.count(Subscriber.id))
        .filter(
            Subscriber.deleted_at.is_(None),
            Subscriber.active.is_(True),
            Subscriber.confirmed_at.isnot(None),
            type_filter,
        )
        .group_by(Subscriber.newsletter_type)
        .all()
    )
    active_counts = dict(active_query)

    inactive_query = (
        db.session.query(Subscriber.newsletter_type, func.count(Subscriber.id))
        .filter(
            Subscriber.deleted_at.is_(None),
            Subscriber.active.is_(False),
            type_filter,
        )
        .group_by(Subscriber.newsletter_type)
        .all()
    )
    inactive_counts = dict(inactive_query)

    for nt in all_types:
        active_counts.setdefault(nt, 0)
        inactive_counts.setdefault(nt, 0)

    return active_counts, inactive_counts


@admin_api_bp.route("/newsletters/performance", methods=["GET"])
@require_auth
def newsletter_performance():
    """Return newsletter performance metrics for a given time window.

    Query params:
        days: Number of days to look back (default 30, max 365)

    Returns:
        - sent count, failed count, retry count, click count
        - top clicked articles
        - click-through by topic/newsletter type
        - subscriber count by newsletter type/topic preference
    """
    days = request.args.get("days", 30, type=int)
    days = max(1, min(days, 365))

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    all_newsletter_types = _build_newsletter_type_list()
    newsletters = _load_newsletters_in_window(cutoff)

    sent_count, failed_count, sent_by_type, failed_by_type = _compute_sent_failed_counts(newsletters)
    retry_count = _compute_retry_count(cutoff)

    newsletter_ids_by_type: dict[str, list[int]] = {t: [] for t in all_newsletter_types}
    for nl in newsletters:
        nt = nl.newsletter_type or "main"
        newsletter_ids_by_type[nt].append(nl.id)

    all_nl_ids = [nid for nids in newsletter_ids_by_type.values() for nid in nids]
    article_ids_by_nl = _load_article_ids_for_newsletters(all_nl_ids)

    all_article_ids = list(set(aid for aids in article_ids_by_nl.values() for aid in aids))
    click_totals = _load_click_totals(all_article_ids)

    click_count = sum(click_totals.values())
    click_through_by_type = _compute_click_count_by_type(
        newsletter_ids_by_type, article_ids_by_nl, click_totals
    )

    top_clicked = _load_top_clicked_articles(limit=20)
    active_counts, inactive_counts = _load_subscriber_counts_by_type(all_newsletter_types)

    return jsonify({
        "period_days": days,
        "generated_at": now.isoformat(),
        "summary": {
            "sent_count": sent_count,
            "failed_count": failed_count,
            "retry_count": retry_count,
            "click_count": click_count,
        },
        "by_newsletter_type": {
            nt: {
                "sent": sent_by_type.get(nt, 0),
                "failed": failed_by_type.get(nt, 0),
                "clicks": click_through_by_type.get(nt, 0),
            }
            for nt in all_newsletter_types
        },
        "top_clicked_articles": top_clicked,
        "subscriber_counts": {
            "active": active_counts,
            "inactive": inactive_counts,
            "total": {nt: active_counts.get(nt, 0) + inactive_counts.get(nt, 0) for nt in all_newsletter_types},
        },
    })