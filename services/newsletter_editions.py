"""Deterministic edition selection, immutable snapshots and public DTOs."""
from __future__ import annotations

import html
import json
import re
from collections import Counter
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from flask import current_app

from extensions import db
from models import Article, NewsletterEdition, NewsletterEditionItem, NewsletterProfile
from services.publication import published_article_filters

MAX_EDITION_ITEMS = 20


def ensure_profile(key: str, *, title: str | None = None) -> NewsletterProfile:
    profile = cast(NewsletterProfile | None, db.session.scalar(select(NewsletterProfile).where(NewsletterProfile.key == key)))
    if profile:
        return profile
    profile = NewsletterProfile(key=key, scope="unified" if key == "main" else "category", category=None if key == "main" else key,
                                enabled=False, email_enabled=False, title=title or ("AInews" if key == "main" else key))
    db.session.add(profile)
    db.session.flush()
    return profile


def _editorial_text(article: Article) -> tuple[str, str, str]:
    try:
        parsed = json.loads(article.final_article or "{}")
    except (TypeError, json.JSONDecodeError):
        parsed = {}
    headline = str(parsed.get("headline") or article.original_title or "Untitled")[:512]
    why_raw = re.sub(r"\s+", " ", str(parsed.get("why_it_matters") or parsed.get("tldr") or article.summary or "")).strip()
    why_match = re.match(r"(.{1,240}?[.!?])(?:\s|$)", why_raw)
    why = (why_match.group(1) if why_match else why_raw[:240].rsplit(" ", 1)[0]).strip()
    body = html.unescape(re.sub(r"<[^>]+>", " ", str(parsed.get("body") or "")))
    paragraph = re.sub(r"\s+", " ", body).strip()
    sentence = re.match(r"(.{40,500}?[.!?])(?:\s|$)", paragraph)
    if sentence:
        paragraph = sentence.group(1)
    else:
        fallback = re.sub(r"\s+", " ", str(parsed.get("tldr") or article.summary or "")).strip()
        fallback_sentence = re.match(r"(.{40,500}?[.!?])(?:\s|$)", fallback)
        paragraph = fallback_sentence.group(1) if fallback_sentence else ""
    return headline, why, paragraph


def select_articles(profile_key: str, *, limit: int = MAX_EDITION_ITEMS, now: datetime | None = None) -> list[Article]:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    profile = cast(NewsletterProfile | None, db.session.scalar(select(NewsletterProfile).where(NewsletterProfile.key == profile_key)))
    min_impact = profile.min_impact if profile else 0
    cutoff = now - timedelta(hours=36)
    last_published = db.session.scalar(select(func.max(NewsletterEdition.published_at)).where(
        NewsletterEdition.profile_key == profile_key, NewsletterEdition.status == "published"))
    if last_published is not None:
        cutoff = max(cutoff, last_published.replace(tzinfo=None) if last_published.tzinfo else last_published)
    q = Article.query.filter(*published_article_filters(Article),
                             Article.published_at.is_not(None), Article.published_at >= cutoff,
                             Article.impact_score >= min_impact)
    if profile_key != "main":
        q = q.filter(Article.category == profile_key)
    prior: list[int | None] = list(db.session.scalars(select(NewsletterEditionItem.article_id).join(NewsletterEdition)
        .where(NewsletterEdition.profile_key == profile_key, NewsletterEdition.published_at >= cutoff,
               NewsletterEditionItem.article_id.is_not(None))).all())
    if prior:
        q = q.filter(~Article.id.in_(prior))
    candidates = q.order_by(Article.impact_score.desc(), Article.published_at.desc(), Article.public_id.asc()).limit(200).all()
    # Greedy MMR-style reranking: impact remains dominant, while similar titles
    # and repeated categories are softly penalized. Every input and tie-break is stable.
    unique: list[Article] = []
    seen_urls: set[str] = set()
    for article in candidates:
        from utils.url import normalize_url
        url = normalize_url(article.original_url or "") or ""
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        unique.append(article)
    selected: list[Article] = []
    title_sets: list[set[str]] = []
    category_counts: Counter[str] = Counter()
    while unique and len(selected) < min(max(limit, 1), MAX_EDITION_ITEMS):
        ranked = []
        impact_values = sorted({float(article.impact_score or 0) for article in unique})
        impact_rank = {value: index / max(len(impact_values) - 1, 1) for index, value in enumerate(impact_values)}
        for article in unique:
            title = set(re.findall(r"[a-z0-9]+", (article.original_title or "").lower()))
            similarity = max((len(title & old) / max(len(title | old), 1) for old in title_sets), default=0.0)
            category = article.category or ""
            category_penalty = 0.25 if profile_key == "main" and category_counts[category] >= max(1, len(selected) // 3) else 0.0
            score = impact_rank[float(article.impact_score or 0)] - similarity * 0.35 - category_penalty
            ranked.append((score, article.id, article, title))
        _, _, winner, words = max(ranked, key=lambda item: (item[0], item[1]))
        selected.append(winner)
        title_sets.append(words)
        category_counts[winner.category or ""] += 1
        unique.remove(winner)
    return selected


def create_edition(profile_key: str, articles: list[Article] | None = None, *, occurrence_key: str | None = None,
                   subject: str | None = None, summary: str = "", publish: bool = True,
                   send_email: bool = False) -> NewsletterEdition | None:
    """Persist exactly the selected ordered set. Unique occurrence makes retries safe."""
    profile = ensure_profile(profile_key)
    occurrence_key = occurrence_key or f"manual:{secrets.token_urlsafe(18)}"
    existing = cast(NewsletterEdition | None, db.session.scalar(select(NewsletterEdition).where(NewsletterEdition.occurrence_key == occurrence_key)))
    if existing:
        return existing
    selected: list[Article] = articles if articles is not None else select_articles(profile_key, limit=profile.max_articles)
    selected = [a for a in selected[:MAX_EDITION_ITEMS]
                if a.publicly_visible and a.pipeline_status == "done" and a.final_article and a.final_article.strip()]
    if not selected:
        return None  # deterministic no-edition result for empty windows
    edition = NewsletterEdition(profile_id=profile.id, profile_key=profile_key, occurrence_key=occurrence_key,
        profile_title=profile.title, policy_revision=profile.policy_revision,
        email_requested=send_email,
        status="published" if publish else "ready", subject=(subject or f"{profile.title}: edition")[:256],
        summary=summary, published_at=datetime.now(timezone.utc).replace(tzinfo=None) if publish else None)
    db.session.add(edition)
    try:
        db.session.flush()
        for position, article in enumerate(selected):
            headline, why, paragraph = _editorial_text(article)
            edition.items.append(NewsletterEditionItem(article_id=article.id, article_public_id=article.public_id,
                position=position, headline=headline, why_it_matters=why, paragraph=paragraph,
                canonical_url=f"{str(current_app.config.get('SITE_URL') or 'http://localhost:5000').rstrip('/')}/article/{article.public_id}", category=article.category,
                source_name=(article.source.name[:256] if article.source and article.source.name else None),
                source_url=(article.source.url[:2048] if article.source and article.source.url else None),
                citations=[{"url": c.url, "title": c.title, "author": c.author} for c in sorted(cast(list[Any], article.citations), key=lambda c: c.position) if c.url]))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = cast(NewsletterEdition | None, db.session.scalar(select(NewsletterEdition).where(NewsletterEdition.occurrence_key == occurrence_key)))
        if existing:
            return existing
        raise
    if publish:
        try:
            from services.tts.jobs import ensure_narration_job_for_published
            ensure_narration_job_for_published(edition, kind="edition")
        except Exception:  # noqa: BLE001 - optional TTS must not block edition publication
            import logging
            logging.getLogger(__name__).warning("Could not create narration job for edition %s", edition.id, exc_info=True)
    return edition


def serialize_edition(edition: NewsletterEdition) -> dict[str, Any]:
    site_url = str(current_app.config.get("SITE_URL") or "http://localhost:5000").rstrip("/")
    payload = {"public_id": edition.public_id, "profile": edition.profile_key, "profile_title": edition.profile_title,
        "policy_revision": edition.policy_revision, "status": edition.status,
        "subject": edition.subject, "summary": edition.summary or "", "published_at": edition.published_at.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z") if edition.published_at else None,
        "canonical_url": f"{site_url}/newsletters/{edition.public_id}", "items": [
            {"position": item.position, "article_public_id": item.article_public_id, "headline": item.headline,
             "why_it_matters": item.why_it_matters, "paragraph": item.paragraph, "canonical_url": item.canonical_url,
             "category": item.category, "source": {"name": item.source_name, "url": item.source_url} if item.source_name or item.source_url else None,
             "citations": item.citations} for item in cast(list[NewsletterEditionItem], edition.items)]}
    try:
        from services.tts.jobs import ready_audio_url
        audio_url = ready_audio_url(edition, kind="edition")
        if audio_url:
            payload["audio"] = {"url": audio_url, "codec": "opus"}
    except Exception:  # noqa: BLE001 - optional audio metadata must not break edition reads
        pass
    return payload


def get_public_edition(public_id: str) -> NewsletterEdition | None:
    return cast(NewsletterEdition | None, db.session.scalar(select(NewsletterEdition).where(NewsletterEdition.public_id == public_id,
        NewsletterEdition.status == "published", NewsletterEdition.published_at.is_not(None))))
