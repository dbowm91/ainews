from __future__ import annotations

import re
import math
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import MemoryEvidence, MemoryItem, MemoryLineage, MemoryScope

_TOKEN_RE = re.compile(r"[\w-]{2,}", re.UNICODE)


def normalize_category(category: str | None) -> str:
    """Resolve known category display names to stable topic keys."""
    if not category or not category.strip():
        return "uncategorized"
    from schemas.topic import normalize_topic

    return normalize_topic(unicodedata.normalize("NFKC", category).strip()) or "uncategorized"


def tokenize(text: str) -> list[str]:
    return list(dict.fromkeys(token.casefold() for token in _TOKEN_RE.findall(unicodedata.normalize("NFKC", text))[:64]))


@dataclass(frozen=True)
class MemoryRecord:
    id: int
    owner_category: str
    item_type: str
    text: str
    importance: int
    status: str
    confidence: str | None
    qualifier: str | None
    valid_as_of: datetime | None
    source_article_ids: tuple[int, ...]
    evidence_count: int
    source_domains: tuple[str, ...]
    shared: bool
    score: float
    score_reasons: tuple[str, ...]


def _candidate_ids(query: str, category_id: str, scope: str, historical: bool, limit: int) -> list[tuple[int, bool]]:
    now = datetime.now(timezone.utc)
    active_statuses = ("active", "synthesized", "superseded", "archived") if historical else ("active",)
    conditions = [MemoryItem.status.in_(active_statuses)]
    if not historical:
        conditions.append(or_(MemoryItem.expires_at.is_(None), MemoryItem.expires_at > now))
    query_tokens = tokenize(query)
    shared_ids = select(MemoryScope.memory_id).where(
        MemoryScope.scope_type == "shared", MemoryScope.scope_id == "global"
    )
    fts_matches: set[int] | None = None
    if query_tokens:
        fts_query = " OR ".join(f'"{token.replace(chr(34), "")}"' for token in query_tokens[:12])
        try:
            scope_terms: list[str] = []
            params: dict[str, object] = {
                "query": fts_query,
                "limit": max(limit * 8, 64),
                "category": category_id,
                "now": now,
            }
            if scope in ("own", "combined"):
                scope_terms.append("m.owner_category = :category")
            if scope in ("shared", "combined"):
                scope_terms.append(
                    "EXISTS (SELECT 1 FROM memory_scopes s "
                    "WHERE s.memory_id = m.id AND s.scope_type = 'shared' "
                    "AND s.scope_id = 'global')"
                )
            status_clause = "m.status IN ('active')"
            if historical:
                status_clause = "m.status IN ('active','synthesized','superseded','archived')"
            expiry_clause = "" if historical else " AND (m.expires_at IS NULL OR m.expires_at > :now)"
            scoped_sql = " OR ".join(scope_terms) or "0"
            matches = db.session.execute(
                db.text(
                    "SELECT f.rowid FROM memory_items_fts AS f "
                    "JOIN memory_items AS m ON m.id = f.rowid "
                    "WHERE memory_items_fts MATCH :query "
                    f"AND ({scoped_sql}) AND {status_clause}{expiry_clause} "
                    "ORDER BY rank LIMIT :limit"
                ),
                params,
            ).scalars().all()
            fts_matches = {int(value) for value in matches}
        except SQLAlchemyError:
            db.session.rollback()

    lexical_filter = []
    if query_tokens and not fts_matches:
        lexical_filter = [or_(*(MemoryItem.text.ilike(f"%{token}%") for token in query_tokens[:12]))]
    if fts_matches:
        lexical_filter = [MemoryItem.id.in_(fts_matches)]

    pairs: list[tuple[int, bool]] = []
    if scope in ("own", "combined"):
        stmt = select(MemoryItem.id).where(
            MemoryItem.owner_category == category_id, *conditions, *lexical_filter
        ).order_by(MemoryItem.importance.desc(), MemoryItem.created_at.desc(), MemoryItem.id).limit(limit)
        pairs.extend((int(value), False) for value in db.session.execute(stmt).scalars().all())
    if scope in ("shared", "combined"):
        stmt = select(MemoryItem.id).where(
            MemoryItem.id.in_(shared_ids), *conditions, *lexical_filter
        ).order_by(MemoryItem.importance.desc(), MemoryItem.created_at.desc(), MemoryItem.id).limit(limit)
        pairs.extend((int(value), True) for value in db.session.execute(stmt).scalars().all())
    # An item can be both category-owned and shared. For its owner, return it
    # once as a local record; other categories receive the shared reference.
    unique: dict[int, bool] = {}
    for item_id, shared in pairs:
        if item_id not in unique or (not shared and unique[item_id]):
            unique[item_id] = shared
    return list(unique.items())


def memory_search(  # noqa: C901 - bounded filtering, ranking and diversity are one auditable pass
    query: str,
    *,
    category_id: str,
    scope: str = "combined",
    limit: int = 8,
    historical: bool = False,
) -> list[MemoryRecord]:
    if len(query) > 512:
        raise ValueError("query must be at most 512 characters")
    if scope not in {"own", "shared", "combined"}:
        raise ValueError("scope must be own, shared or combined")
    limit = max(0, min(int(limit), 20))
    if limit == 0:
        return []
    category = normalize_category(category_id)
    pairs = _candidate_ids(query, category, scope, historical, max(limit * 4, 16))
    if not pairs:
        return []
    ids = [item_id for item_id, _ in pairs]
    items = db.session.execute(select(MemoryItem).where(MemoryItem.id.in_(ids))).scalars().all()
    shared_by_id = dict(pairs)
    query_tokens = set(tokenize(query))
    now = datetime.now(timezone.utc)
    evidence_rows = db.session.execute(
        select(MemoryEvidence.memory_id, MemoryEvidence.source_article_id, MemoryEvidence.source_url).where(
            MemoryEvidence.memory_id.in_(ids), MemoryEvidence.source_article_id.is_not(None)
        ).order_by(MemoryEvidence.id).limit(max(1, len(ids) * 8))
    ).all()
    evidence: dict[int, list[int]] = {}
    domains: dict[int, list[str]] = {}
    for memory_id, article_id, source_url in evidence_rows:
        evidence.setdefault(memory_id, []).append(article_id)
        try:
            host = (urlsplit(source_url).hostname or "").casefold().removeprefix("www.") if source_url else ""
        except ValueError:
            host = ""
        if host:
            domains.setdefault(memory_id, []).append(host)
    by_id = {item.id: item for item in items}
    records: list[MemoryRecord] = []
    for item_id, shared in pairs:
        item = by_id.get(item_id)
        if item is None:
            continue
        expires_at = item.expires_at
        if not historical and expires_at and (expires_at.replace(tzinfo=timezone.utc) if expires_at.tzinfo is None else expires_at) <= now:
            continue
        text_tokens = set(tokenize(item.text))
        overlap = len(query_tokens & text_tokens) / max(len(query_tokens), 1)
        if query_tokens and overlap < 0.15:
            continue
        last_evidence = item.last_evidence_at or item.created_at
        if last_evidence and last_evidence.tzinfo is None:
            last_evidence = last_evidence.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (now - last_evidence).total_seconds() / 86400) if last_evidence else 3650.0
        freshness = 1 / (1 + age_days / 90)
        confidence_score = {"high": 0.2, "medium": 0.1, "qualified": 0.1, "low": 0.0}.get(item.confidence, 0.0)
        evidence_count = len(evidence.get(item.id, []))
        evidence_score = min(0.3, math.log1p(evidence_count) * 0.1)
        reasons = [
            f"lexical_overlap={overlap:.2f}",
            f"freshness={freshness:.2f}",
            f"evidence_count={evidence_count}",
            f"importance={item.importance}",
        ]
        if item.valid_as_of:
            reasons.append("valid_as_of_present")
        score = overlap * 4 + freshness * 0.5 + confidence_score + evidence_score + item.importance * 0.1
        records.append(MemoryRecord(
            id=item.id,
            owner_category=item.owner_category,
            item_type=item.item_type,
            text=item.text,
            importance=item.importance,
            status=item.status,
            confidence=item.confidence,
            qualifier=item.qualifier,
            valid_as_of=item.valid_as_of,
            source_article_ids=tuple(dict.fromkeys(evidence.get(item.id, []))),
            evidence_count=evidence_count,
            source_domains=tuple(dict.fromkeys(domains.get(item.id, []))),
            shared=shared,
            score=score,
            score_reasons=tuple(reasons),
        ))
    records.sort(key=lambda record: (-record.score, -record.importance, record.id))
    selected: list[MemoryRecord] = []
    domains_seen: dict[str, int] = {}
    deferred: list[MemoryRecord] = []
    for record in records:
        if record.source_domains and any(domains_seen.get(domain, 0) >= 2 for domain in record.source_domains):
            deferred.append(record)
            continue
        selected.append(record)
        for domain in record.source_domains:
            domains_seen[domain] = domains_seen.get(domain, 0) + 1
        if len(selected) == limit:
            break
    if len(selected) < limit:
        selected.extend(deferred[: limit - len(selected)])
    return selected


def memory_get(
    ids: list[int], *, category_id: str, allow_shared: bool = True, historical: bool = False,
) -> list[dict]:
    ids = list(dict.fromkeys(int(value) for value in ids))[:20]
    if not ids:
        return []
    category = normalize_category(category_id)
    shared_ids = set()
    if allow_shared:
        shared_ids = set(db.session.execute(select(MemoryScope.memory_id).where(
            MemoryScope.memory_id.in_(ids), MemoryScope.scope_type == "shared", MemoryScope.scope_id == "global"
        )).scalars().all())
    status_filter = (
        MemoryItem.status.in_(("active", "synthesized", "superseded", "archived"))
        if historical
        else MemoryItem.status == "active"
    )
    items = db.session.execute(select(MemoryItem).where(
        MemoryItem.id.in_(ids),
        status_filter,
        or_(MemoryItem.owner_category == category, MemoryItem.id.in_(shared_ids)),
    )).scalars().all()
    output = []
    now = datetime.now(timezone.utc)
    for item in items:
        expires_at = item.expires_at
        if not historical and expires_at and (
            expires_at.replace(tzinfo=timezone.utc) if expires_at.tzinfo is None else expires_at
        ) <= now:
            continue
        evidence = db.session.execute(select(MemoryEvidence).where(
            MemoryEvidence.memory_id == item.id
        ).order_by(MemoryEvidence.id).limit(20)).scalars().all()
        lineage = db.session.execute(select(MemoryLineage).where(or_(
            MemoryLineage.source_memory_id == item.id, MemoryLineage.target_memory_id == item.id
        )).order_by(MemoryLineage.id).limit(20)).scalars().all()
        output.append({
            "id": item.id,
            "owner_category": item.owner_category,
            "item_type": item.item_type,
            "text": item.text[:2000],
            "status": item.status,
            "importance": item.importance,
            "confidence": item.confidence,
            "qualifier": item.qualifier,
            "valid_as_of": item.valid_as_of.isoformat() if item.valid_as_of else None,
            "shared": item.id in shared_ids,
            "evidence": [{"article_id": e.source_article_id, "url": e.source_url, "claim_id": e.claim_id, "relation": e.relation} for e in evidence],
            "lineage": [{"source_id": e.source_memory_id, "target_id": e.target_memory_id, "relation": e.relation} for e in lineage],
        })
    return output
