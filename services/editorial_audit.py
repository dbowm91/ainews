"""Deterministic checks on the exact edited public article artifact."""

from __future__ import annotations

import json
import re

_TOKEN = re.compile(r"[\w'-]+", re.UNICODE)
_NUMBER = re.compile(r"(?<!\w)\d[\d,.]*(?:%|x)?", re.IGNORECASE)
_QUOTED = re.compile(r'["“](.{5,500}?)["”]')


def _words(text: str) -> list[str]:
    return [word.casefold() for word in _TOKEN.findall(text)]


def _longest_shared_run(left: list[str], right: list[str]) -> int:
    previous = [0] * (len(right) + 1)
    longest = 0
    for token in left:
        current = [0]
        for index, candidate in enumerate(right, start=1):
            value = previous[index - 1] + 1 if token == candidate else 0
            current.append(value)
            longest = max(longest, value)
        previous = current
    return longest


def audit_final_artifact(article) -> dict:
    """Return reproducible findings; any finding prevents autonomous release."""
    from services.url import normalize_url

    try:
        final = json.loads(article.final_article or "")
    except (json.JSONDecodeError, TypeError):
        return {"passed": False, "findings": ["FINAL_ARTICLE_INVALID"]}
    row = getattr(article, "editorial_dossier", None)
    if row is None or row.status != "verified":
        return {"passed": False, "findings": ["EVIDENCE_DOSSIER_UNVERIFIED"]}
    payload = row.payload or {}
    sources = {
        source.get("evidence_source_id"): source
        for source in payload.get("sources", [])
        if isinstance(source, dict) and source.get("retrieval_status") == "retrieved"
    }
    allowed_urls = set()
    for source in sources.values():
        try:
            allowed_urls.add(normalize_url(source.get("url") or ""))
        except (ValueError, TypeError):
            continue
    findings: list[dict] = []
    for citation in final.get("citations", []):
        try:
            citation_url = normalize_url(citation.get("url") or "")
        except (ValueError, TypeError):
            citation_url = ""
        if not citation_url or citation_url not in allowed_urls:
            findings.append({"code": "CITATION_NOT_IN_DOSSIER", "url": (citation.get("url") or "")[:300]})

    fields = ["headline", "tldr", "why_it_matters", "body", "what_to_watch"]
    text = "\n".join(
        [str(final.get(field) or "") for field in fields]
        + [str(point) for point in (final.get("key_points") or [])]
    )
    verified_text = " ".join(
        [claim.get("claim", "") for claim in payload.get("claims", [])]
        + [link.get("span", "") for claim in payload.get("claims", [])
           for link in claim.get("supports", []) + claim.get("contradicts", [])]
    )
    for number in set(_NUMBER.findall(text)):
        if number not in verified_text:
            findings.append({"code": "UNSUPPORTED_NUMBER", "value": number})

    evidence_texts = [source.get("excerpt", "") for source in sources.values()]
    for quote in _QUOTED.findall(text):
        if not any(quote in excerpt for excerpt in evidence_texts):
            findings.append({"code": "QUOTE_NOT_VERBATIM", "excerpt": quote[:160]})

    # Exact long phrase overlap is a high-risk copying signal, not a legal
    # threshold. Quoted spans are removed before comparison.
    prose = _QUOTED.sub(" ", text)
    article_words = _words(prose)
    longest = max((_longest_shared_run(article_words, _words(source_text)) for source_text in evidence_texts), default=0)
    if longest >= 12:
        findings.append({"code": "LONG_VERBATIM_OVERLAP", "token_run": longest})

    return {"passed": not findings, "findings": findings, "longest_shared_run": longest}
