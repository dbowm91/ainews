from datetime import datetime, timezone
from urllib.parse import urlparse

from celery import shared_task
from celery.utils.log import get_task_logger
from billiard.exceptions import SoftTimeLimitExceeded

from constants import truncate_for_log

logger = get_task_logger(__name__)


def _find_duplicate_article(url: str, title: str):
    """Check for existing article by normalized URL or title.

    Returns the existing Article or None.
    """
    from models import Article
    from services.url import normalize_url, normalize_title
    from services.article import _escape_like_pattern

    # URL-based dedup: query by domain to narrow candidates, then normalize in Python
    if url:
        normalized = normalize_url(url)
        if normalized:
            parsed = urlparse(normalized)
            domain = parsed.netloc

            if domain:
                # Only load articles from the same domain — avoids full table scan
                escaped_domain = _escape_like_pattern(domain)
                candidates = Article.query.filter(
                    Article.original_url.ilike(f"%{escaped_domain}%", escape="\\"),
                ).all()
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


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=300,
    time_limit=360,
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
    from services.content_extractor import extract_article
    from models import Article, Citation, encode_short_url
    from extensions import db
    from tasks.pipeline import _log_pipeline
    from services.config_unified import MIN_CONTENT_LENGTH

    if min_content_length is None:
        min_content_length = MIN_CONTENT_LENGTH

    extraction = None
    extracted_text = text_content or title

    if url and (not text_content or len(text_content) < min_content_length):
        try:
            extraction = extract_article(url)
            if (
                extraction
                and extraction.text
                and len(extraction.text) >= MIN_CONTENT_LENGTH
            ):
                extracted_text = extraction.text
        except Exception as exc:
            logger.warning("Extraction failed for %s: %s", url, exc)
            if run_id:
                _log_pipeline(
                    run_id,
                    "extract",
                    "warning",
                    "Extraction failed for %s: %s",
                    title[:60],
                    exc,
                )

    # Cross-source dedup check
    try:
        duplicate = _find_duplicate_article(url, title)
    except Exception as exc:
        logger.warning("Dedup check failed for %s: %s", truncate_for_log(title), exc)
        duplicate = None
    if duplicate:
        logger.info(
            "Duplicate found for [%s]: existing article %s",
            truncate_for_log(title),
            duplicate.id,
        )
        if run_id:
            _log_pipeline(
                run_id,
                "extract",
                "info",
                "Duplicate skipped: %s (existing: %s)",
                title[:60],
                duplicate.id,
                article_id=duplicate.id,
            )
        # Add this source as a citation to the existing article if URL differs
        if url and url != duplicate.original_url:
            try:
                existing_cite = Citation.query.filter_by(
                    article_id=duplicate.id, url=url
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
                        )
                    )
                    db.session.commit()
                    logger.info(
                        "Added citation to article %s from %s", duplicate.id, url[:60]
                    )
            except Exception as exc:
                db.session.rollback()
                logger.warning(
                    "Failed to add citation for duplicate %s: %s", duplicate.id, exc
                )
        return {"article_id": duplicate.id, "duplicate": True}

    try:
        from services.crawling import get_or_create_source

        source = get_or_create_source(
            source_key=source_key,
            name=source_name,
            source_type=source_type,
            url=url or "",
        )

        try:
            pub_date = (
                datetime.fromisoformat(published_at)
                if published_at
                else datetime.now(timezone.utc)
            )
        except (ValueError, TypeError):
            pub_date = datetime.now(timezone.utc)

        article = Article(
            source_id=source.id,
            external_id=external_id,
            original_url=url,
            original_title=title,
            original_author=author,
            original_published_at=pub_date,
            extracted_text=extracted_text,
            pipeline_status="pending",
            category=topics[0] if topics else "other",
            topics=topics,
            raw_metadata=raw_metadata or {},
            extraction_status=(
                extraction.status.value
                if extraction
                else ("no_url" if not url else "fallback")
            ),
        )
        db.session.add(article)
        db.session.flush()

        # Generate short URL id
        article.short_id = encode_short_url(article.id)
        db.session.flush()

        if url:
            db.session.add(
                Citation(
                    article_id=article.id,
                    url=url,
                    title=title,
                    author=author,
                    position=1,
                )
            )

        db.session.commit()
    except SoftTimeLimitExceeded:
        db.session.rollback()
        logger.error("process_item exceeded soft time limit for %s", external_id)
        raise
    except Exception as exc:
        db.session.rollback()
        logger.error("DB operation failed for %s: %s", external_id, exc)
        if run_id:
            _log_pipeline(run_id, "extract", "error", "%s: %s", external_id, exc)
        raise

    if run_id:
        _log_pipeline(
            run_id,
            "extract",
            "info",
            "Extracted [%s]: %s",
            topics[0] if topics else "?",
            title[:60],
            article_id=article.id,
        )
    logger.info("Extracted [%s]: %s", topics[0] if topics else "?", title[:60])

    from tasks.select import select_article

    try:
        select_article.delay(article.id, run_id=run_id)
    except Exception:
        article.pipeline_status = "failed"
        article.last_error = "Failed to dispatch to pipeline"
        db.session.commit()
        logger.error("Failed to dispatch select_article for article %s", article.id)

    return {"article_id": article.id}
