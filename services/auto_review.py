"""Auto-review mode: publish without waiting for a human.

The pipeline routes an article to the ``review`` queue whenever a quality gate
fails or an editor asks for a second look. That is the right default: a human
decides whether a shaky article goes out. It is the wrong default for a site
that wants fully autonomous generation, because the queue then fills up with
articles nobody is going to read and the site goes quiet.

Auto-review mode turns that around. When ``pipeline.review.auto_approve`` is
on, an article that reaches the review queue is approved and published
immediately, exactly as a human approver would have done.

Three things happen here, and they are deliberately separated:

``is_auto_approve_enabled``
    Reads the switch. Cheap, cached, and safe to call from a hot path.

``approve_article``
    The single approval primitive. It is what both the auto-approver and the
    admin panel's "approve" button call, so an auto-approved article and a
    human-approved one end up in exactly the same state.

``auto_approve_queued``
    Drains the queue. It is the safety net for articles that were already
    waiting when the switch was turned on, and it runs on the beat.

The decision of *whether* to auto-approve lives in one place, so the pipeline
stages cannot disagree about it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def is_auto_approve_enabled() -> bool:
    """True when articles that reach the review queue are published on sight."""
    try:
        from schemas.pipeline import load_pipeline_config

        return bool(load_pipeline_config().pipeline.review.auto_approve)
    except Exception as e:  # noqa: BLE001
        # A broken configuration must not silently switch a site into
        # publishing articles nobody reviewed. Failing closed here means the
        # articles wait for a human, which is the safe direction.
        logger.warning("Could not read the auto-approve setting: %s", e)
        return False


def _invalidate_public_cache(article) -> None:
    """Drop the cached pages that show a newly published article.

    The cache keys are namespaced by what they hold, and a new article can
    change every one of them: the index, the topic pages, the tag pages, the
    article page itself, the top-impact list, the feeds and the sitemap.
    Missing one leaves the article invisible on that page until the entry
    expires.
    """
    try:
        from services.cache import get_response_cache

        cache = get_response_cache()
        for prefix in (
            "pub:index",
            "pub:topic",
            "pub:tag",
            "pub:article_detail",
            "pub:top_impact",
            "pub:rss_feed",
            "pub:sitemap",
        ):
            cache.invalidate_prefix(prefix)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to invalidate the article cache: %s", e)


def approve_article(article, *, reason: str = "manual", published_at=None) -> bool:
    """Approve one article: mark it done and make it publicly visible.

    This is the same transition the admin panel performs when a person clicks
    "approve", so an auto-approved article is indistinguishable from a
    human-approved one.

    Returns True when the article was approved, False when it was not in the
    review queue and therefore needed no approval.
    """
    from constants import PipelineStatus

    if article.pipeline_status != PipelineStatus.REVIEW:
        return False

    publish_article(article, reason=reason, published_at=published_at)
    return True


def publish_article(article, *, reason: str = "manual", published_at=None) -> None:
    """Mark an article done and make it publicly visible.

    The caller decides whether the article *should* go out; this function only
    performs the transition. That split matters: the pipeline stages ask
    whether an article may be published, and the admin panel asks whether it
    may be approved, but they share the transition so the two can never drift
    apart.

    The caller commits. The post-finalize work runs before that commit, which
    is the order the normal publish path uses.
    """
    from constants import PipelineStatus

    article.pipeline_status = PipelineStatus.DONE
    article.publicly_visible = True
    article.retry_count = 0
    article.last_error = None
    article.scheduled_publish_at = None
    article.published_at = published_at or datetime.now(timezone.utc).replace(tzinfo=None)

    _invalidate_public_cache(article)
    _post_finalize(article)

    try:
        from services.audit import log_admin_action

        log_admin_action(
            "article_approve",
            target_type="article",
            target_id=article.id,
            details={
                "original_title": getattr(article, "original_title", ""),
                "approved_by": reason,
            },
            category="article",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to record the approval of article %s: %s", article.id, e)

    logger.info(
        "Article %s approved (%s): %s",
        article.id,
        reason,
        (getattr(article, "original_title", "") or "")[:50],
    )


def _post_finalize(article) -> None:
    """Run the work that follows a publication.

    Trend memory, the webhooks and the embedding are what a published
    article is *for*. An article that reaches the review queue and is then
    approved is still a published article, so it gets the same treatment as
    one that passed the editor without a second look.

    A failure here must not unpublish the article, so it is logged and
    swallowed.
    """
    try:
        from services.pipeline_degradation import post_finalize_article

        post_finalize_article(article)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "Post-finalize work failed for article %s, continuing: %s",
            getattr(article, "id", "?"),
            e,
        )


def route_to_review(article) -> bool:
    """Route an article to the review queue, or publish it outright.

    Returns True when the article is waiting in the queue for a human, and
    False when it is not in the queue -- because auto-review mode published it
    instead, or because it was already published.

    Every path that sends an article to review goes through here, so the
    pipeline stages cannot disagree about whether auto-review mode is on.
    """
    from constants import PipelineStatus

    # An article that is already published is not waiting for a review.
    # The editor can be re-dispatched onto an article that has already been
    # finalized, and routing that article to review again would either drag a
    # live article back out of the queue or -- in auto-review mode -- publish
    # it a second time and run the post-publication work twice.
    if article.pipeline_status == PipelineStatus.DONE:
        logger.info(
            "Article %s is already published, not routing to review",
            getattr(article, "id", "?"),
        )
        return False

    if is_auto_approve_enabled():
        publish_article(article, reason="auto_review")
        return False

    article.pipeline_status = PipelineStatus.REVIEW
    article.publicly_visible = False
    _invalidate_public_cache(article)
    return True


def auto_approve_queued(limit: int = 100) -> int:
    """Approve everything waiting in the review queue. Returns the count.

    This is the safety net. The pipeline normally approves an article the
    moment it routes it to review, but an article that was already waiting
    when the switch was turned on -- or one that was queued by a path that
    does not go through the pipeline -- would otherwise sit there for ever.
    """
    if not is_auto_approve_enabled():
        return 0

    from sqlalchemy.exc import SQLAlchemyError

    from constants import PipelineStatus
    from extensions import db
    from models import Article

    approved = 0
    try:
        queued = (
            Article.query.filter(Article.pipeline_status == PipelineStatus.REVIEW)
            .order_by(Article.updated_at.asc())
            .limit(limit)
            .all()
        )
    except SQLAlchemyError as e:
        logger.error("Could not read the review queue: %s", e)
        return 0

    for article in queued:
        try:
            if approve_article(article, reason="auto_review"):
                db.session.commit()
                approved += 1
        except SQLAlchemyError:
            db.session.rollback()
            logger.error("Failed to auto-approve article %s", article.id)
            continue

    if approved:
        logger.info("Auto-review mode published %s article(s)", approved)
    return approved
