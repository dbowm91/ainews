from typing import Any
from urllib.parse import urlparse

from billiard.exceptions import SoftTimeLimitExceeded
from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy.exc import SQLAlchemyError
from constants import CELERY_TASK_MAX_RETRIES

logger = get_task_logger(__name__)


def _extract_content_if_needed(url: str, text_content: str | None, min_content_length: int) -> tuple[str, Any]:
    """Extract content from URL if needed.

    Returns tuple of (extracted_text, extraction_result).
    """
    from services.content_extractor import extract_article

    extraction = None
    extracted_text = text_content or ""

    if url and (not text_content or len(text_content) < min_content_length):
        try:
            extraction = extract_article(url)
            if extraction and extraction.text and len(extraction.text) >= min_content_length:
                extracted_text = extraction.text
        except (ConnectionError, TimeoutError, ValueError, Exception) as exc:  # noqa: BLE001 - trafilatura raises diverse exceptions
            logger.warning("Extraction failed for %s: %s", url, exc)

    return extracted_text, extraction


def _find_duplicate_article(url: str, title: str):
    """Check for existing article by normalized URL or title.

    Returns the existing Article or None.
    """
    from models import Article
    from services.article import _escape_like_pattern
    from services.url import normalize_title, normalize_url

    # URL-based dedup: query by domain to narrow candidates, then normalize in Python
    if url:
        normalized = normalize_url(url)
        if normalized:
            parsed = urlparse(normalized)
            domain = parsed.netloc

            if domain:
                # Only load articles from the same domain — avoids full table scan
                escaped_domain = _escape_like_pattern(domain)
                candidates = (
                    Article.query.filter(
                        Article.original_url.ilike(f"%{escaped_domain}%", escape="\\"),
                    )
                    .limit(20)
                    .all()
                )
                for cand in candidates:
                    if (
                        cand.original_url
                        and normalize_url(cand.original_url) == normalized
                    ):
                        return cand

    # Title-based dedup: normalize both sides consistently
    if title:
        normalized_title = normalize_title(title)
        if normalized_title:
            # Use LIKE with the normalized title to handle internal whitespace differences.
            # We fetch candidates and verify in Python for exact match.
            escaped = _escape_like_pattern(normalized_title)
            like_pattern = escaped.replace(" ", "%")
            candidates = (
                Article.query.filter(
                    Article.original_title.ilike(f"%{like_pattern}%", escape="\\"),
                )
                .limit(20)
                .all()
            )
            for cand in candidates:
                if normalize_title(cand.original_title) == normalized_title:
                    return cand

    return None


def _create_article_record(
    validated,
    source,
    extracted_text: str,
    extraction,
    run_id: int | None = None,
):
    """Create and persist article record with citations.

    Returns the created Article.
    """
    from datetime import datetime, timezone

    from extensions import db
    from models import Article, Citation, encode_short_url

    try:
        pub_date = (
            datetime.fromisoformat(validated.published_at)
            if validated.published_at
            else datetime.now(timezone.utc)
        )
        if pub_date.tzinfo is not None:
            pub_date = pub_date.replace(tzinfo=None)
    except (ValueError, TypeError):
        pub_date = datetime.now(timezone.utc)

    article = Article(
        source_id=source.id,
        external_id=validated.external_id,
        original_url=validated.url,
        original_title=validated.title,
        original_author=validated.author,
        original_published_at=pub_date,
        extracted_text=extracted_text,
        pipeline_status="pending",
        pipeline_started_at=datetime.now(timezone.utc),
        crawled_at=datetime.now(timezone.utc),
        category=validated.topics[0] if validated.topics else "other",
        topics=validated.topics,
        raw_metadata=validated.raw_metadata or {},
        extraction_status=(
            extraction.status.value
            if extraction
            else ("no_url" if not validated.url else "fallback")
        ),
    )
    db.session.add(article)
    db.session.flush()

    article.short_id = encode_short_url(article.id)
    db.session.flush()

    if validated.url:
        db.session.add(
            Citation(
                article_id=article.id,
                url=validated.url,
                title=validated.title,
                author=validated.author,
                position=1,
            ),
        )

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return article


def _dispatch_after_extraction(article_id: int, run_id: int | None = None) -> None:
    """Log extraction and dispatch to next pipeline stage."""
    from extensions import db
    from models import Article
    from tasks.pipeline import _dispatch_next, _log_pipeline

    article = db.session.get(Article, article_id)
    if not article:
        logger.error("Article %s not found for dispatch", article_id)
        return

    topic = article.topics[0] if article.topics else "?"
    title_trunc = (article.original_title or "")[:60]

    if run_id:
        _log_pipeline(
            run_id,
            "extract",
            "info",
            "Extracted [%s]: %s",
            topic,
            title_trunc,
            article_id=article.id,
        )
    logger.info("Extracted [%s]: %s", topic, title_trunc)

    try:
        _dispatch_next(article_id, run_id=run_id, next_status="pending")
    except Exception as e:
        article.last_error = "Failed to dispatch to pipeline"
        db.session.rollback()
        logger.error("Failed to dispatch select_article for article %s: %s", article_id, e)
        raise


def _handle_duplicate(
    duplicate,
    article_id: int,
    url: str,
    title: str,
    author,
    run_id: int | None = None,
    validated=None,
) -> dict | None:
    """Handle duplicate article by adding citation if needed.

    Returns dict if handled (returns duplicate info), None if not a duplicate.
    """
    from constants import truncate_for_log
    from extensions import db
    from models import Citation
    from tasks.pipeline import _log_pipeline

    if not duplicate:
        return None

    logger.info(
        "Duplicate found for [%s]: existing article %s",
        truncate_for_log(validated.title if validated else title),
        duplicate.id,
    )
    if run_id:
        _log_pipeline(
            run_id,
            "extract",
            "info",
            "Duplicate skipped: %s (existing: %s)",
            (validated.title[:60] if validated else title[:60]),
            duplicate.id,
            article_id=duplicate.id,
        )
    if url and url != duplicate.original_url:
        try:
            existing_cite = Citation.query.filter_by(
                article_id=duplicate.id, url=url,
            ).first()
            if not existing_cite:
                max_pos = (
                    db.session.query(db.func.max(Citation.position))
                    .filter_by(article_id=duplicate.id)
                    .scalar()
                    or 0
                )
                db.session.add(
                    Citation(
                        article_id=duplicate.id,
                        url=url,
                        title=title,
                        author=author,
                        position=max_pos + 1,
                    ),
                )
                db.session.commit()
                logger.info(
                    "Added citation to article %s from %s", duplicate.id, url[:60],
                )
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.warning(
                "Failed to add citation for duplicate %s: %s", duplicate.id, exc,
            )
    return {"article_id": duplicate.id, "duplicate": True}


@shared_task(
    bind=True,
    acks_late=True,
    task_reject_on_worker_lost=True,
    max_retries=CELERY_TASK_MAX_RETRIES,
    default_retry_delay=30,
    soft_time_limit=300,
    time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def process_item(
    self,
    source_key,
    source_name,
    source_type,
    external_id,
    title,
    url,
    author,
    published_at,
    text_content,
    raw_score,
    raw_metadata,
    topics,
    min_content_length=None,
    run_id=None,
):
    from constants import truncate_for_log
    from extensions import db
    from services.config_unified import MIN_CONTENT_LENGTH
    from services.crawling import get_or_create_source
    from tasks.pipeline import _log_pipeline

    try:
        from schemas.tasks import ProcessItemTask
        validated = ProcessItemTask(
            source_key=source_key,
            source_name=source_name,
            source_type=source_type,
            external_id=external_id,
            title=title,
            url=url,
            author=author,
            published_at=published_at,
            text_content=text_content,
            raw_score=raw_score,
            raw_metadata=raw_metadata,
            topics=topics,
            min_content_length=min_content_length,
            run_id=run_id,
        )
    except Exception as e:
        logger.warning("Invalid process_item input: %s", e)
        raise TypeError(f"Invalid process_item input: {e}") from e

    if validated.min_content_length is None:
        min_content_length = MIN_CONTENT_LENGTH
    else:
        min_content_length = validated.min_content_length

    extracted_text, extraction = _extract_content_if_needed(
        validated.url,
        validated.text_content or validated.title,
        min_content_length,
    )

    if run_id and extraction is None and validated.url:
        _log_pipeline(
            run_id,
            "extract",
            "warning",
            "Extraction failed for %s",
            validated.title[:60],
        )

    duplicate = None
    try:
        duplicate = _find_duplicate_article(validated.url, validated.title)
    except SQLAlchemyError as exc:
        logger.warning("Dedup check failed for %s: %s", truncate_for_log(validated.title), exc)
        try:
            from services.metrics import get_metrics
            get_metrics().increment("pipeline.dedup_check_failed", tags={"source": source_key})
        except Exception as e:  # noqa: BLE001 - metrics failure is non-critical
            logger.debug("Failed to increment dedup_check_failed metric: %s", e)

    if duplicate:
        result = _handle_duplicate(
            duplicate,
            duplicate.id,
            validated.url,
            validated.title,
            validated.author,
            run_id,
            validated,
        )
        if result:
            return result

    source = get_or_create_source(
        source_key=validated.source_key,
        name=validated.source_name,
        source_type=validated.source_type,
        url=validated.url or "",
    )

    try:
        article = _create_article_record(
            validated,
            source,
            extracted_text,
            extraction,
            run_id,
        )
    except SoftTimeLimitExceeded:
        db.session.rollback()
        logger.error("process_item exceeded soft time limit for %s", validated.external_id)
        raise
    except Exception as exc:
        db.session.rollback()
        logger.error("DB operation failed for %s: %s", validated.external_id, exc)
        if run_id:
            _log_pipeline(run_id, "extract", "error", "%s: %s", validated.external_id, exc)
        raise

    _dispatch_after_extraction(article.id, run_id)

    return {"article_id": article.id}
