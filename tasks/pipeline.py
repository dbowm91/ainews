"""Shared pipeline helpers used across stage modules."""

import json

from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

MAX_STAGE_RETRIES = 3

_STAGE_STATUS_MAP = {
    "pending": "select",
    "researching": "research",
    "writing": "write",
    "editing": "edit",
}


def _build_fallback_article(article) -> str:
    """Build a minimal article JSON when pipeline stages fail or are skipped."""
    return json.dumps(
        {
            "headline": article.original_title or "Untitled",
            "tldr": (article.extracted_text or "")[:200],
            "why_it_matters": "",
            "body": article.extracted_text or article.original_title or "",
            "key_points": [],
            "what_to_watch": "",
            "citations": [],
            "original_attribution": {
                "source": article.original_url or "",
                "author": article.original_author or "",
            },
            "tags": [],
        }
    )


def _log_pipeline(run_id, stage, level, message, article_id=None):
    """Create a PipelineLog entry without committing outer transactions."""
    from models import PipelineLog
    from extensions import db

    savepoint = db.session.begin_nested()
    try:
        log = PipelineLog(
            run_id=run_id,
            article_id=article_id,
            stage=stage,
            level=level,
            message=message,
        )
        db.session.add(log)
        savepoint.commit()
    except Exception as e:
        savepoint.rollback()
        logger.error(f"Failed to write pipeline log: {e}")


def _degrade_and_advance(article, failed_stage: str, run_id=None):
    """Advance article to next stage with degraded quality on persistent failure."""
    from extensions import db

    # Normalize: accept both action names ("write") and status names ("writing")
    failed_stage = _STAGE_STATUS_MAP.get(failed_stage, failed_stage)

    logger.warning(
        f"Degrading article {article.id} from stage '{failed_stage}' (retry_count={article.retry_count})"
    )

    if failed_stage == "select":
        article.selector_result = {
            "selected": True,
            "score": 6,
            "reason": "auto-selected after failure",
        }
        article.pipeline_status = "researching"
        article.retry_count = 0
        article.last_error = None
        db.session.commit()
        if run_id:
            _log_pipeline(
                run_id,
                "select",
                "warning",
                f"Degraded: auto-selected {article.original_title[:50]}",
                article_id=article.id,
            )
        from tasks.research import research_article

        research_article.delay(article.id, run_id=run_id)

    elif failed_stage == "research":
        article.research_brief = json.dumps(
            {
                "source_summary": (
                    article.extracted_text or article.original_title or ""
                )[:500],
                "key_claims": [],
                "direct_quotes": [],
                "external_sources": [],
                "related_articles": [],
                "context_notes": "Research stage failed; using source text only.",
                "newsworthiness": "Auto-generated after research failure.",
                "impact_score": 30,
            }
        )
        article.impact_score = 30
        article.pipeline_status = "writing"
        article.retry_count = 0
        article.last_error = None
        db.session.commit()
        if run_id:
            _log_pipeline(
                run_id,
                "research",
                "warning",
                f"Degraded: skipped research for {article.original_title[:50]}",
                article_id=article.id,
            )
        from tasks.write import write_article

        write_article.delay(article.id, run_id=run_id)

    elif failed_stage == "write":
        article.draft_article = _build_fallback_article(article)
        article.pipeline_status = "editing"
        article.retry_count = 0
        article.last_error = None
        db.session.commit()
        if run_id:
            _log_pipeline(
                run_id,
                "write",
                "warning",
                f"Degraded: minimal draft for {article.original_title[:50]}",
                article_id=article.id,
            )
        from tasks.edit import edit_article

        edit_article.delay(article.id, run_id=run_id)

    elif failed_stage == "edit":
        fallback = article.draft_article or _build_fallback_article(article)
        article.final_article = fallback
        article.original_ai_article = fallback
        article.retry_count = 0
        article.last_error = None

        # Route to review if enabled, otherwise mark as done
        from schemas.pipeline import load_pipeline_config

        review_cfg = load_pipeline_config().pipeline.review
        if review_cfg.enabled:
            threshold = review_cfg.auto_publish_threshold
            if threshold is None or (article.impact_score or 0) < threshold:
                article.pipeline_status = "review"
                db.session.commit()
                if run_id:
                    _log_pipeline(
                        run_id,
                        "edit",
                        "warning",
                        f"Degraded to review: {article.original_title[:50]}",
                        article_id=article.id,
                    )
                return

        article.pipeline_status = "done"
        db.session.commit()
        if run_id:
            _log_pipeline(
                run_id,
                "edit",
                "warning",
                f"Degraded: used draft as final for {article.original_title[:50]}",
                article_id=article.id,
            )
        logger.warning(f"Article {article.id} finalized with degraded content")

    else:
        logger.error(
            f"Unknown stage '{failed_stage}' for degradation of article {article.id}"
        )


def _handle_stage_failure(article, stage: str, exc, run_id=None):
    """Handle failure for a pipeline stage. Returns True if degraded, False if retrying."""
    from extensions import db

    article.retry_count = (article.retry_count or 0) + 1
    article.last_error = f"{stage}: {str(exc)[:500]}"

    if article.retry_count >= MAX_STAGE_RETRIES:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return False
        _degrade_and_advance(article, stage, run_id=run_id)
        return True
    else:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        return False


def _finalize(article_id: int):
    """Mark article as done when editor is skipped."""
    from models import Article
    from extensions import db

    try:
        article = Article.query.get(article_id)
        if article:
            final = article.draft_article or _build_fallback_article(article)
            article.final_article = final
            article.original_ai_article = final
            article.retry_count = 0
            article.last_error = None

            # Route to review if enabled, otherwise mark as done
            from schemas.pipeline import load_pipeline_config

            review_cfg = load_pipeline_config().pipeline.review
            if review_cfg.enabled:
                threshold = review_cfg.auto_publish_threshold
                if threshold is None or (article.impact_score or 0) < threshold:
                    article.pipeline_status = "review"
                    db.session.commit()
                    logger.info(f"Article {article_id} queued for review (finalize)")
                    return

            article.pipeline_status = "done"

            # Create version snapshot
            from services.article import create_article_version

            create_article_version(
                article,
                change_reason="pipeline_finalize",
                changed_by="pipeline:finalizer",
            )

            db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Finalize failed for article {article_id}: {e}")


def _assign_tags(article, tag_names: list[str], db):
    """Find or create tags and link them to the article.

    Batches queries to avoid N+1: one SELECT for existing tags, one flush
    for new tags, one SELECT for existing links, one INSERT for new links.
    """
    from models import Tag, slugify, article_tags

    if not tag_names:
        return

    # 1. Normalize names and compute slugs
    name_by_slug: dict[str, str] = {}
    for raw in tag_names[:10]:
        name = raw.strip().lower()
        if not name or len(name) > 64:
            continue
        slug = slugify(name)
        name_by_slug.setdefault(slug, name)

    if not name_by_slug:
        return

    slugs = list(name_by_slug.keys())

    # 2. Batch-fetch existing tags
    existing_tags = Tag.query.filter(Tag.slug.in_(slugs)).all()
    tag_by_slug = {t.slug: t for t in existing_tags}

    # 3. Create any missing tags
    for slug, name in name_by_slug.items():
        if slug not in tag_by_slug:
            tag = Tag(name=name, slug=slug)
            db.session.add(tag)
            tag_by_slug[slug] = tag
    db.session.flush()

    # 4. Batch-fetch existing article-tag links
    tag_ids = [t.id for t in tag_by_slug.values()]
    existing_links = set(
        r[0]
        for r in db.session.execute(
            article_tags.select()
            .where(
                (article_tags.c.article_id == article.id)
                & (article_tags.c.tag_id.in_(tag_ids))
            )
            .with_only_columns(article_tags.c.tag_id)
        ).all()
    )

    # 5. Insert missing links
    for tag in tag_by_slug.values():
        if tag.id not in existing_links:
            db.session.execute(
                article_tags.insert().values(article_id=article.id, tag_id=tag.id)
            )
