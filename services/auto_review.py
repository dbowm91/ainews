"""Auto-review mode: publish without waiting for a human.

The pipeline routes an article to the ``review`` queue whenever a quality gate
fails or an editor asks for a second look. Eligible articles can be published
without waiting for a person. Editorial eligibility holds remain in review
until their evidence, audit, and quality requirements pass.

When ``pipeline.review.auto_approve`` is on, an eligible article is approved
and published without waiting for a human. The setting never overrides an
editorial eligibility hold.

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
logger = logging.getLogger(__name__)


def is_auto_approve_enabled() -> bool:
    """True when eligible articles can be published without human review."""
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

    return publish_article(article, reason=reason, published_at=published_at)


def publish_article(article, *, reason: str = "manual", published_at=None) -> bool:
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

    from services.editorial_eligibility import require_eligible

    verdict = require_eligible(article)
    if not verdict.eligible:
        article.last_error = "Cannot publish final content: " + ", ".join(verdict.reason_codes)
        logger.warning(
            "Article %s has no publishable final content: %s",
            getattr(article, "id", "?"),
            ", ".join(verdict.reason_codes),
        )
        return False

    article.pipeline_status = PipelineStatus.DONE
    article.publicly_visible = True
    article.retry_count = 0
    article.last_error = None
    article.scheduled_publish_at = None
    # post_finalize_article claims the publication timestamp atomically and
    # dispatches irreversible effects only for the winning transition.

    _invalidate_public_cache(article)
    finalized = (
        _post_finalize(article, published_at=published_at)
        if published_at is not None
        else _post_finalize(article)
    )
    if not finalized:
        try:
            from extensions import db

            db.session.refresh(article)
        except Exception:  # noqa: BLE001 - a concurrent winner may detach the row
            return False
        return article.pipeline_status == PipelineStatus.DONE and article.published_at is not None

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
    return True


def _post_finalize(article, *, published_at=None) -> bool:
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

        if published_at is None:
            return bool(post_finalize_article(article))
        return bool(post_finalize_article(article, published_at=published_at))
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "Post-finalize work failed for article %s, continuing: %s",
            getattr(article, "id", "?"),
            e,
        )
        return False


def route_to_review(article) -> bool:
    """Route an article to review, or publish it if eligible and auto-review is on.

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

    from services.editorial_eligibility import require_eligible

    verdict = require_eligible(article)
    if not verdict.eligible:
        article.last_error = "Cannot publish final content: " + ", ".join(verdict.reason_codes)
        article.pipeline_status = PipelineStatus.REVIEW
        return True

    if is_auto_approve_enabled():
        if publish_article(article, reason="auto_review"):
            return False
        article.pipeline_status = PipelineStatus.REVIEW
        return True

    article.pipeline_status = PipelineStatus.REVIEW
    article.publicly_visible = False
    _invalidate_public_cache(article)
    return True


def auto_approve_queued(limit: int = 100) -> int:
    """Publish queued articles with complete final content. Returns the count.

    This is the safety net. The pipeline normally publishes an article the
    moment it routes it to review, but an article that was already waiting
    when the switch was turned on -- or one that was queued by a path that
    does not go through the pipeline -- would otherwise sit there for ever.
    Articles without a valid final artifact remain queued.
    """
    if not is_auto_approve_enabled():
        return 0

    from sqlalchemy.exc import SQLAlchemyError

    from constants import PipelineStatus
    from extensions import db
    from models import Article

    approved = 0
    recovered = 0
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
            if not (article.final_article or "").strip():
                from services.editorial_eligibility import require_eligible

                require_eligible(article)
                if _resume_incomplete_review_article(article):
                    recovered += 1
                continue
            did_approve = approve_article(article, reason="auto_review")
            db.session.commit()
            if did_approve:
                approved += 1
        except SQLAlchemyError:
            db.session.rollback()
            logger.error("Failed to auto-approve article %s", article.id)
            continue

    if approved:
        logger.info("Auto-review mode published %s article(s)", approved)
    if recovered:
        logger.info("Auto-review mode resumed %s incomplete article(s)", recovered)
    return approved


def _resume_incomplete_review_article(article) -> bool:
    """Resume recoverable pre-publication work instead of parking it in review."""
    from constants import PipelineStatus
    from extensions import db

    metadata = dict(article.raw_metadata or {}) if isinstance(article.raw_metadata, dict) else {}
    attempts = int(metadata.get("incomplete_review_retries", 0) or 0)
    from services.pipeline_failure import _get_max_stage_retries

    maximum = _get_max_stage_retries()
    if attempts >= maximum:
        article.last_error = (
            f"Final article is still missing after {attempts} recovery attempts; "
            "manual retry is required"
        )
        db.session.commit()
        return False

    dossier = getattr(article, "editorial_dossier", None)
    dossier_verified = dossier is not None and dossier.status == "verified"
    if not dossier_verified:
        # A prior research attempt can leave a brief behind even when its
        # evidence ledger is unverified. Sending that article straight to
        # writing (or editing) only repeats the same missing-packet failure.
        # Re-run research so it can refresh retrieval and verify the ledger.
        if (article.extracted_text or "").strip():
            next_status = PipelineStatus.RESEARCHING
        else:
            article.last_error = (
                "Verified evidence dossier is unavailable and no extracted "
                "article text remains; manual retry is required"
            )
            db.session.commit()
            return False
    elif not (article.research_brief or "").strip():
        if (article.extracted_text or "").strip():
            next_status = PipelineStatus.RESEARCHING
        else:
            article.last_error = (
                "Final article is missing and no recoverable pipeline input remains"
            )
            db.session.commit()
            return False
    elif (article.draft_article or "").strip():
        next_status = PipelineStatus.EDITING
    else:
        next_status = PipelineStatus.WRITING

    attempts += 1
    metadata["incomplete_review_retries"] = attempts
    article.raw_metadata = metadata
    article.pipeline_status = next_status
    article.publicly_visible = False
    article.retry_count = attempts
    article.total_retries = (article.total_retries or 0) + 1
    article.last_error = (
        f"Retrying incomplete article at {next_status} (attempt {attempts}/{maximum})"
    )
    db.session.commit()

    from services.pipeline_utils import _dispatch_next

    _dispatch_next(article.id, next_status=next_status)
    logger.info(
        "Resuming incomplete article %s at %s (attempt %s/%s)",
        article.id,
        next_status,
        attempts,
        maximum,
    )
    return True
