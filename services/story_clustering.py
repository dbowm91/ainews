"""Conservative local clustering of cross-feed leads into one story candidate."""

from __future__ import annotations

from typing import cast

import hashlib
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

_STOP = frozenset({
    "a", "an", "and", "the", "to", "for", "of", "in", "on", "by", "as", "with",
    "is", "are", "was", "were", "will", "new", "says", "said", "report", "reports",
})
_EVENTS = {
    "release": {"launch", "launches", "launched", "release", "releases", "released", "unveil", "unveils", "unveiled"},
    "update": {"update", "updates", "updated", "upgrade", "upgrades", "upgraded"},
    "benchmark": {"benchmark", "benchmarks", "score", "scores", "outperforms"},
    "security": {"vulnerability", "breach", "attack", "exploit", "cve", "patch", "patched"},
    "policy": {"law", "rule", "regulation", "court", "lawsuit", "ban", "banned"},
    "research": {"study", "paper", "research", "finds", "found"},
    "correction": {"correction", "correct", "corrects", "corrected", "retraction", "retracted"},
}


def event_fingerprint(title: str) -> tuple[str, str, set[str]]:
    words = re.findall(r"[a-z0-9][a-z0-9.+#_-]*", (title or "").casefold())
    event_type = "other"
    for kind, verbs in _EVENTS.items():
        if any(word in verbs for word in words):
            event_type = kind
            break
    signature_words = sorted({word for word in words if word not in _STOP and len(word) > 1})
    entities = {word for word in signature_words if any(char.isdigit() for char in word)}
    # Company/product names and versions retain capitalization signals from title.
    for token in re.findall(r"\b[A-Z][A-Za-z0-9.+#_-]{1,}\b", title or ""):
        entities.add(token.casefold())
    signature = f"{event_type}:" + " ".join(signature_words[:30])
    return signature, event_type, entities


def _score(incoming: str, incoming_event: str, incoming_entities: set[str], existing: str) -> float:
    _, event_type, existing_entities = event_fingerprint(existing)
    if incoming_event != event_type:
        return 0.0
    left = {word for word in re.findall(r"[a-z0-9][a-z0-9.+#_-]*", incoming.casefold()) if word not in _STOP}
    right = {word for word in re.findall(r"[a-z0-9][a-z0-9.+#_-]*", existing.casefold()) if word not in _STOP}
    if not left or not right:
        return 0.0
    jaccard = len(left & right) / len(left | right)
    entity_overlap = (
        len(incoming_entities & existing_entities) / max(1, len(incoming_entities | existing_entities))
        if incoming_entities
        else 1.0
    )
    if incoming_entities and entity_overlap < 0.5:
        return 0.0
    return min(1.0, jaccard * 0.75 + entity_overlap * 0.25)


def acquire_admission_guard() -> tuple[object | None, str | None]:
    """Serialize short cluster admission checks; Redis outage disables merging safely."""
    try:
        from extensions import get_redis

        client = get_redis()
        token = hashlib.sha256(f"{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()
        if client.set("ainews:story_cluster_admission", token, nx=True, ex=45):
            return client, token
    except Exception:  # noqa: BLE001 - clustering is optional; failure keeps leads separate
        return None, None
    return None, None


def release_admission_guard(guard: tuple[object | None, str | None]) -> None:
    client, token = guard
    if client is None or token is None:
        return
    try:
        from services.redis_utils import release_lock

        release_lock(client, "ainews:story_cluster_admission", token)
    except Exception:  # noqa: BLE001 - short expiry is the recovery path
        return


def attach_matching_lead(
    *, title: str, source_id: int, external_id: str | None, url: str | None,
    published_at: datetime | None,
) -> int | None:
    """Attach a high-confidence same-event lead and return the canonical article ID."""
    from extensions import db
    from models import Article, EditorialDossier, StoryCluster, StoryLead
    from services.metrics import get_metrics

    signature, event_type, entities = event_fingerprint(title)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    published_at = published_at or now
    if published_at.tzinfo:
        published_at = published_at.astimezone(timezone.utc).replace(tzinfo=None)
    start = published_at - timedelta(hours=48)
    candidates = db.session.execute(
        select(Article, StoryCluster)
        .outerjoin(StoryCluster, StoryCluster.canonical_article_id == Article.id)
        .where(Article.created_at >= start)
        .order_by(Article.created_at.desc())
        .limit(150)
    ).all()
    normalized_candidates = []
    for article, cluster in candidates:
        if cluster is None:
            prior_signature, prior_type, _ = event_fingerprint(article.original_title or "")
            prior_time = article.original_published_at or article.created_at or now
            if prior_time.tzinfo:
                prior_time = prior_time.astimezone(timezone.utc).replace(tzinfo=None)
            cluster = StoryCluster(
                canonical_article_id=article.id,
                event_signature=prior_signature,
                event_type=prior_type,
                event_at=prior_time,
                status="active",
            )
            db.session.add(cluster)
            db.session.flush()
            db.session.add(StoryLead(
                cluster_id=cluster.id,
                source_id=article.source_id,
                external_id=article.external_id,
                url=article.original_url,
                title=(article.original_title or "")[:512],
                published_at=prior_time,
                match_score=1.0,
                decision_reason="legacy_backfill",
            ))
        if cluster.status == "active" and cluster.event_at and cluster.event_at >= start:
            normalized_candidates.append((article, cluster))
    scored = [
        (_score(title, event_type, entities, article.original_title or ""), article, cluster)
        for article, cluster in normalized_candidates
        if article.pipeline_status not in {"skipped", "failed"}
    ]
    scored.sort(key=lambda candidate: candidate[0], reverse=True)
    if not scored or scored[0][0] < 0.82:
        # Record an ambiguous high-overlap candidate only as a metric; it is
        # intentionally kept separate until a human or stronger signal acts.
        if scored and scored[0][0] >= 0.55:
            _metric(get_metrics(), "story_cluster_ambiguous")
        return None

    score, article, cluster = scored[0]
    exists = StoryLead.query.filter_by(source_id=source_id, external_id=external_id).one_or_none()
    if exists:
        return cast(int | None, cluster.canonical_article_id)
    db.session.add(StoryLead(
        cluster_id=cluster.id,
        source_id=source_id,
        external_id=external_id,
        url=url,
        title=title[:512],
        published_at=published_at,
        match_score=score,
        decision_reason="high_confidence_event_match",
    ))
    if article.pipeline_status != "done":
        dossier = EditorialDossier.query.filter_by(article_id=article.id).one_or_none()
        if dossier:
            dossier.status = "stale"
            article.last_error = "Editorial hold: a new discovery lead requires evidence re-evaluation"
    db.session.commit()
    _metric(get_metrics(), "story_cluster_lead_merged")
    _metric(get_metrics(), "story_cluster_duplicate_prevented")
    return cast(int | None, cluster.canonical_article_id)


def register_canonical_lead(article, source_id: int, external_id: str | None,
                            url: str | None, published_at: datetime | None) -> None:
    """Create the initial cluster and immutable lead provenance for a new article."""
    from extensions import db
    from models import StoryCluster, StoryLead
    from services.metrics import get_metrics

    signature, event_type, _ = event_fingerprint(article.original_title or "")
    event_at = published_at or article.original_published_at or article.created_at
    if event_at and event_at.tzinfo:
        event_at = event_at.astimezone(timezone.utc).replace(tzinfo=None)
    cluster = StoryCluster(
        canonical_article_id=article.id,
        event_signature=signature,
        event_type=event_type,
        event_at=event_at,
        status="active",
    )
    db.session.add(cluster)
    db.session.flush()
    db.session.add(StoryLead(
        cluster_id=cluster.id,
        source_id=source_id,
        external_id=external_id,
        url=url,
        title=(article.original_title or "")[:512],
        published_at=event_at,
        match_score=1.0,
        decision_reason="canonical_lead",
    ))
    db.session.commit()
    _metric(get_metrics(), "story_cluster_created")


def _metric(metrics, name: str) -> None:
    try:
        metrics.counter_inc(name, labels={})
    except Exception:  # noqa: BLE001 - telemetry never changes story admission
        return
