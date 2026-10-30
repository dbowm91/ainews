from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from extensions import db
from models import MemoryCategorySummary, MemoryItem
from services.memory.repository import MemoryRecord, memory_search, normalize_category
from services.metrics import get_metrics
from utils.text import esc_xml_attr, esc_xml_text


@dataclass(frozen=True)
class ContextPack:
    category_id: str
    stage: str
    memory_ids: tuple[int, ...]
    records: tuple[MemoryRecord, ...]
    rendered: str
    tokens_estimate: int
    truncated: bool
    cache_version: str


def _tokens(text: str) -> int:
    return math.ceil(len(text) / 3)


def fit_context_text(text: str, token_budget: int) -> str:
    """Fit plain context by whole lines using the deterministic token estimator."""
    budget = max(0, int(token_budget))
    if budget == 0:
        return ""
    selected: list[str] = []
    for line in text.splitlines():
        candidate = "\n".join([*selected, line])
        if _tokens(candidate) > budget:
            continue
        selected.append(line)
    return "\n".join(selected)


def memory_context(
    category_id: str,
    article_id: int | None,
    token_budget: int,
    stage: str,
    query: str = "",
) -> ContextPack:
    started = time.perf_counter()
    category = normalize_category(category_id)
    budget = max(0, min(int(token_budget), 2400))
    stage = stage if stage in {"research", "edit", "deep"} else "edit"
    from schemas.pipeline import load_pipeline_config

    memory_config = load_pipeline_config().memory
    if budget == 0:
        return ContextPack(category, stage, (), (), "", 0, False, "memory-v1-empty")

    summary = db.session.get(MemoryCategorySummary, category)
    summary_text = summary.content if summary else ""
    current_synthesis = db.session.get(MemoryItem, summary.current_memory_id) if summary and summary.current_memory_id else None
    records = memory_search(
        query or category,
        category_id=category,
        scope="combined",
        limit=min(20, memory_config.max_records_per_context + memory_config.max_shared_records_per_context),
        historical=False,
        exclude_article_id=article_id,
    )
    # The summary is the canonical rendering of its current synthesis. Do not
    # spend the context budget repeating that same synthesis as a record.
    records = [
        record for record in records
        if record.id != (summary.current_memory_id if summary else None)
    ]
    metrics = get_metrics()
    metrics.gauge_set("memory.candidates", len(records), labels={"stage": stage, "mode": "fts5_lexical"})
    local = [record for record in records if not record.shared][:memory_config.max_records_per_context]
    shared = [record for record in records if record.shared][:memory_config.max_shared_records_per_context]
    selected = local + shared

    def render(chosen: list[MemoryRecord], include_summary: bool) -> str:
        blocks = ["<editorial_memory_context>"]
        if include_summary and summary_text:
            evidence_ids = ",".join(str(value) for value in (summary.evidence_ids or [])[:8]) if summary else ""
            as_of = current_synthesis.valid_as_of.date().isoformat() if current_synthesis and current_synthesis.valid_as_of else "date unknown"
            qualifier = esc_xml_attr(current_synthesis.qualifier or "qualified historical synthesis") if current_synthesis else "qualified historical synthesis"
            blocks.append(
                f'<category_summary revision="{summary.revision if summary else 0}" '
                f'current_memory_id="{summary.current_memory_id if summary and summary.current_memory_id else "unknown"}" '
                f'evidence_memory_ids="{evidence_ids}" as_of="{as_of}" qualifier="{qualifier}">'
                + esc_xml_text(summary_text[:1000])
                + "</category_summary>"
            )
        for record in chosen:
            scope = "shared" if record.shared else "category"
            provenance = ",".join(str(value) for value in record.source_article_ids[:4]) or "unknown"
            qualifier = esc_xml_attr(record.qualifier or "historical observation")
            date = record.valid_as_of.date().isoformat() if record.valid_as_of else "date unknown"
            text = esc_xml_text(record.text[:1200])
            blocks.append(
                f'<memory id="{record.id}" scope="{scope}" as_of="{date}" evidence="{provenance}" qualifier="{qualifier}">{text}</memory>'
            )
        blocks.append("</editorial_memory_context>")
        return "\n".join(blocks) if chosen or (include_summary and summary_text) else ""

    include_summary = bool(summary_text)
    rendered = render(selected, include_summary)
    truncated = False
    while selected and _tokens(rendered) > budget:
        selected.pop()
        truncated = True
        rendered = render(selected, include_summary)
    if _tokens(rendered) > budget and include_summary:
        include_summary = False
        truncated = True
        rendered = render(selected, include_summary)
    if _tokens(rendered) > budget or not rendered:
        rendered = ""
        selected = []
    metrics.gauge_set("memory.selected", len(selected), labels={"stage": stage})
    metrics.gauge_set("memory.tokens_estimate", _tokens(rendered), labels={"stage": stage})
    metrics.counter_inc("memory.retrieval_calls", labels={"stage": stage, "mode": "fts5_lexical"})
    if selected:
        metrics.counter_inc("memory.category_hits", labels={"category": category, "stage": stage})
    if truncated:
        metrics.counter_inc("memory.context_truncated", labels={"stage": stage})
    metrics.histogram_observe("memory.context_build_seconds", time.perf_counter() - started, labels={"stage": stage})
    if not records:
        metrics.counter_inc("memory.retrieval_miss", labels={"stage": stage, "reason": "no_relevant_candidates"})
    elif not selected:
        metrics.counter_inc("memory.retrieval_miss", labels={"stage": stage, "reason": "budget_empty"})
    now = datetime.now(timezone.utc)
    for record in selected:
        if record.valid_as_of:
            value = record.valid_as_of.replace(tzinfo=timezone.utc) if record.valid_as_of.tzinfo is None else record.valid_as_of
            metrics.histogram_observe("memory.age_days", max(0.0, (now - value).total_seconds() / 86400), labels={"stage": stage})
    digest = hashlib.sha256(json.dumps({
        "category": category,
        "stage": stage,
        "budget": budget,
        "summary_revision": summary.revision if summary else 0,
        "ids": [record.id for record in selected],
    }, sort_keys=True).encode()).hexdigest()[:16]
    return ContextPack(
        category_id=category,
        stage=stage,
        memory_ids=tuple(record.id for record in selected),
        records=tuple(selected),
        rendered=rendered,
        tokens_estimate=_tokens(rendered),
        truncated=truncated,
        cache_version=digest,
    )
