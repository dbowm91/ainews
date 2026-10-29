"""Conservative, deterministic triggers for optional editorial subagents."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from services.url import normalize_title, normalize_url

_GAP_MARKERS = re.compile(
    r"\b(correction|corrected|retraction|retracted|disputed|disputes|"
    r"contradict|contradicts|conflicting|uncertain|low confidence|"
    r"revised|updated after|later clarified|according to different)\b",
    re.IGNORECASE,
)


def prepare_web_evidence(results: list[dict], *, limit: int = 8, per_domain: int = 2) -> list[dict]:
    """Deduplicate canonical URLs and cap repeated publishers deterministically."""
    output: list[dict] = []
    seen_urls: set[str] = set()
    domain_counts: dict[str, int] = {}
    for result in results:
        url = str(result.get("url") or "").strip()
        try:
            canonical = normalize_url(url) if url else ""
        except ValueError:
            canonical = ""
        if canonical and canonical in seen_urls:
            continue
        try:
            host = (urlsplit(canonical or url).hostname or "").casefold()
        except ValueError:
            host = ""
        domain = host.removeprefix("www.")
        if domain and domain_counts.get(domain, 0) >= per_domain:
            continue
        if canonical:
            seen_urls.add(canonical)
        if domain:
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        output.append({
            "title": str(result.get("title") or "")[:300],
            "url": url[:2048],
            "snippet": str(result.get("snippet") or "")[:1000],
            "source_kind": "search_snippet",
        })
        if len(output) >= max(1, limit):
            break
    return output


def should_synthesize_web_results(article, results: list[dict]) -> bool:
    """Only spend an extra call on heterogeneous, conflicting, or complex evidence."""
    if not results:
        return False
    domains = set()
    for result in results:
        try:
            domain = (urlsplit(str(result.get("url") or "")).hostname or "").casefold().removeprefix("www.")
        except ValueError:
            domain = ""
        if domain:
            domains.add(domain)
    combined = " ".join([
        str(getattr(article, "original_title", "") or ""),
        str(getattr(article, "extracted_text", "") or "")[:12000],
        *(str(result.get("snippet") or "") for result in results),
    ])
    if _GAP_MARKERS.search(combined):
        return True
    if len(results) >= 3 and len(domains) >= 2:
        return True
    return len(results) >= 4 and len(str(getattr(article, "extracted_text", "") or "")) >= 6000


def should_contextualize_editor(article, related_articles: list, topic_notes: dict, memory: str) -> bool:
    """Detect explicit gaps or unusually rich context that merits an extra pass."""
    brief = str(getattr(article, "research_brief", "") or "")
    draft = str(getattr(article, "draft_article", "") or "")
    if _GAP_MARKERS.search(f"{brief}\n{draft}"):
        return True
    if any(notes for notes in topic_notes.values()):
        return True  # Manual notes represent explicit editorial policy.
    if len(related_articles) >= 3 or len(memory) > 1800:
        return True
    return False


def selector_prefilter_reason(article, candidates: list[dict]) -> str | None:
    """Reject only invalid-empty items or exact duplicates already published."""
    if not (str(getattr(article, "original_title", "") or "").strip() or str(getattr(article, "extracted_text", "") or "").strip()):
        return "invalid_empty_article"
    article_url = normalize_url(str(getattr(article, "original_url", "") or ""))
    article_title = normalize_title(str(getattr(article, "original_title", "") or ""))
    for candidate in candidates:
        if candidate.get("id") == getattr(article, "id", None) or candidate.get("pipeline_status") != "done":
            continue
        candidate_url = normalize_url(str(candidate.get("url") or ""))
        candidate_title = normalize_title(str(candidate.get("title") or ""))
        if (article_url and candidate_url == article_url) or (article_title and candidate_title == article_title):
            return "exact_published_duplicate"
    return None
