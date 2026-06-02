"""Persisted quality reporting service for editorial quality verification.

Provides deterministic quality checks for citation verification, claim verification,
and direct quote validation against research briefs and sources.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field as dc_field
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError as PydanticValidationError

from schemas.llm_responses import ResearchBrief
from services.article_validation import validate_final_article
from services.quality import QualityScore, lightweight_quality_signals

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from models.article import Article
    from models.quality import QualityReport


@dataclass
class QualityFinding:
    """A single quality finding from verification checks."""

    severity: str  # error|warning|info
    code: str  # unsupported_claim|missing_citation|unknown_citation_url|quote_mismatch|stale_date|unsafe_content|schema_error
    message: str
    field: str  # body|citations|key_points|headline|research_brief
    evidence: dict[str, Any] = dc_field(default_factory=dict)


@dataclass
class QualityReportResult:
    """Result of building a quality report before persistence."""

    overall_score: float
    groundedness: float
    coherence: float
    completeness: float
    safety: float
    citation_score: float
    claim_score: float
    passed: bool
    needsreview: bool
    findings: list[QualityFinding]
    meta: dict[str, Any]


def _parse_final_article(final_article: str | None) -> tuple[dict | None, list[QualityFinding]]:
    """Parse final_article JSON and check for schema errors.

    Returns parsed dict and any schema findings.
    """
    findings = []
    if not final_article:
        findings.append(
            QualityFinding(
                severity="error",
                code="schema_error",
                message="final_article is empty",
                field="body",
                evidence={},
            )
        )
        return None, findings

    is_valid, errors = validate_final_article(final_article)
    if not is_valid:
        for err in errors:
            findings.append(
                QualityFinding(
                    severity="error",
                    code="schema_error",
                    message=err,
                    field="body",
                    evidence={"error": err},
                )
            )
        try:
            parsed = json.loads(final_article)
        except json.JSONDecodeError:
            parsed = None
        return parsed, findings

    try:
        parsed = json.loads(final_article)
        return parsed, findings
    except json.JSONDecodeError as e:
        findings.append(
            QualityFinding(
                severity="error",
                code="schema_error",
                message=f"final_article is not valid JSON: {e}",
                field="body",
                evidence={"error": str(e)},
            )
        )
        return None, findings


def _parse_research_brief(research_brief: str | None) -> tuple[ResearchBrief | None, list[QualityFinding]]:
    """Parse research_brief JSON as ResearchBrief.

    Returns parsed ResearchBrief and any parse findings.
    """
    findings: list[QualityFinding] = []
    if not research_brief:
        return None, findings

    try:
        parsed = json.loads(research_brief)
        rb = ResearchBrief(**parsed)
        return rb, findings
    except (json.JSONDecodeError, PydanticValidationError) as e:
        findings.append(
            QualityFinding(
                severity="warning",
                code="research_brief_parse_error",
                message=f"Could not parse research_brief: {e}",
                field="research_brief",
                evidence={"error": str(e)},
            )
        )
        return None, findings


def _build_known_url_set(
    research_brief: ResearchBrief | dict | None,
    original_url: str | None,
    existing_citations: list[dict],
) -> set[str]:
    """Build set of all known/valid URL strings from research and citations."""
    known_urls: set[str] = set()

    if original_url:
        known_urls.add(original_url)

    if research_brief:
        if isinstance(research_brief, dict):
            for src in research_brief.get("external_sources", []):
                url = src.get("url") if isinstance(src, dict) else getattr(src, "url", None)
                if url:
                    known_urls.add(url)
            for claim in research_brief.get("key_claims", []):
                source = claim.get("source") if isinstance(claim, dict) else getattr(claim, "source", None)
                if source and source.startswith("http"):
                    known_urls.add(source)
            for quote in research_brief.get("direct_quotes", []):
                source_url = quote.get("source_url") if isinstance(quote, dict) else getattr(quote, "source_url", None)
                if source_url:
                    known_urls.add(source_url)
        else:
            for src in research_brief.external_sources:
                if src.url:
                    known_urls.add(src.url)
            for claim in research_brief.key_claims:
                if claim.source and claim.source.startswith("http"):
                    known_urls.add(claim.source)
            for quote in research_brief.direct_quotes:
                if quote.source_url:
                    known_urls.add(quote.source_url)

    for citation in existing_citations:
        url = citation.get("url") or citation.get("url")
        if url:
            known_urls.add(url)

    return known_urls


def _normalize_url(url: str) -> str:
    """Normalize URL for comparison by stripping trailing slashes."""
    if not url:
        return url
    url = url.strip()
    while url.endswith("/"):
        url = url[:-1]
    return url


def _verify_citations(
    parsed_article: dict,
    research_brief: ResearchBrief | dict | None,
    original_url: str | None,
    existing_citations: list[dict],
) -> list[QualityFinding]:
    """Verify that all citations in final article are from known sources.

    Citations must appear in research_brief.external_sources, key_claims.source,
    original_url, or existing Citation rows.
    """
    findings = []
    citations = parsed_article.get("citations", [])
    known_urls = _build_known_url_set(research_brief, original_url, existing_citations)

    normalized_known = {_normalize_url(u) for u in known_urls}

    for i, cit in enumerate(citations):
        url = cit.get("url", "").strip() if isinstance(cit, dict) else ""
        if not url:
            findings.append(
                QualityFinding(
                    severity="warning",
                    code="missing_citation",
                    message=f"Citation at index {i} has no URL",
                    field="citations",
                    evidence={"index": i, "citation": cit},
                )
            )
            continue

        normalized_url = _normalize_url(url)
        if normalized_url not in normalized_known:
            findings.append(
                QualityFinding(
                    severity="warning",
                    code="unknown_citation_url",
                    message=f"Citation URL not found in research sources or citations: {url}",
                    field="citations",
                    evidence={"url": url, "index": i},
                )
            )

    return findings


def _extract_text_fields(parsed_article: dict) -> str:
    """Extract all text fields from article for claim checking."""
    fields = []
    for key in ["body", "tldr", "why_it_matters", "what_to_watch"]:
        val = parsed_article.get(key, "")
        if isinstance(val, str):
            fields.append(val)
    for kp in parsed_article.get("key_points", []):
        if isinstance(kp, str):
            fields.append(kp)
    return " ".join(fields)


def _claim_overlaps_source(claim_text: str, source_text: str) -> bool:
    """Check if claim text shares meaningful overlap with source text.

    Uses conservative word overlap: at least 3 non-stopwords must appear in source.
    """
    stopwords = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "this", "that", "these", "those",
        "as", "from", "into", "through", "during", "before", "after",
    }
    claim_words = {w.lower() for w in re.findall(r"\b\w+\b", claim_text) if len(w) > 3}
    claim_keywords = claim_words - stopwords
    if not claim_keywords:
        return True

    source_lower = source_text.lower()
    overlap = sum(1 for w in claim_keywords if w in source_lower)
    return overlap >= 3


def _check_unsupported_claims(
    article_text: str,
    research_brief: ResearchBrief | None,
) -> list[QualityFinding]:
    """Check for numeric/date/entity claims without supporting source overlap.

    Uses conservative approach: flags claims with numbers, dates, or specific entities
    that don't appear to be supported by key claims or source text.
    """
    findings = []

    date_pattern = re.compile(
        r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b",
        re.IGNORECASE,
    )
    number_pattern = re.compile(
        r"\b\d+\.?\d*\s*(?:percent|%|million|billion|trillion|thousand|kg|lbs|years?|months?|days?|hours?|minutes?|seconds?|users?|customers?|companies?|dollars?|eur|gbps?|mbps?|nm|ghz|kw|wh)\b",
        re.IGNORECASE,
    )
    entity_pattern = re.compile(
        r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b",
    )

    source_text = ""
    if research_brief:
        for claim in research_brief.key_claims:
            source_text += claim.claim + " " + claim.source + " "
        for src in research_brief.external_sources:
            source_text += src.title + " " + src.snippet + " "
        for quote in research_brief.direct_quotes:
            source_text += quote.quote + " "

    sentences = re.split(r"[.!?]+", article_text)
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 20:
            continue

        has_date = bool(date_pattern.search(sent))
        has_number = bool(number_pattern.search(sent))
        has_entity = bool(entity_pattern.search(sent))

        if has_date or has_number or has_entity:
            if source_text and not _claim_overlaps_source(sent, source_text):
                claim_type = []
                if has_date:
                    claim_type.append("date")
                if has_number:
                    claim_type.append("numeric")
                if has_entity:
                    claim_type.append("entity")

                findings.append(
                    QualityFinding(
                        severity="warning",
                        code="unsupported_claim",
                        message=f"Claim appears unsupported by key claims or sources: {sent[:100]}",
                        field="body",
                        evidence={
                            "claim": sent[:200],
                            "claim_types": claim_type,
                        },
                    )
                )

    return findings


def _check_direct_quotes(
    parsed_article: dict,
    research_brief: ResearchBrief | None,
) -> list[QualityFinding]:
    """Verify that quoted text in article appears in ResearchBrief.direct_quotes.

    Looks for text enclosed in double quotes in article body and checks if they
    appear in the research brief's direct quotes.
    """
    findings: list[QualityFinding] = []
    if not research_brief:
        return findings

    direct_quote_texts = {q.quote.lower() for q in research_brief.direct_quotes}

    body = parsed_article.get("body", "")
    if not body or not isinstance(body, str):
        return findings

    quoted_matches = re.findall(r'"([^"]{20,})"', body)
    for quote in quoted_matches:
        quote_lower = quote.lower().strip()
        if quote_lower and not any(
            quote_lower in dq or dq in quote_lower for dq in direct_quote_texts
        ):
            findings.append(
                QualityFinding(
                    severity="warning",
                    code="quote_mismatch",
                    message=f"Direct quote not found in research brief direct quotes: {quote[:80]}",
                    field="body",
                    evidence={"quote": quote[:100]},
                )
            )

    return findings


def _compute_scores(
    quality_signals: QualityScore,
    citation_findings: list[QualityFinding],
    claim_findings: list[QualityFinding],
) -> tuple[float, float]:
    """Compute citation and claim scores from findings.

    citation_score: 1.0 minus ratio of citation warnings to total citations
    claim_score: 1.0 minus ratio of claim warnings to total key claims
    """
    citation_errors = sum(1 for f in citation_findings if f.severity == "error")
    citation_warnings = sum(1 for f in citation_findings if f.severity == "warning")

    citation_penalty = (citation_errors * 0.3 + citation_warnings * 0.1)
    citation_score = max(0.0, 1.0 - citation_penalty)

    claim_warnings = sum(1 for f in claim_findings if f.severity == "warning")
    claim_penalty = claim_warnings * 0.1
    claim_score = max(0.0, 1.0 - claim_penalty)

    return citation_score, claim_score


def _should_fail_or_review(
    findings: list[QualityFinding],
    citation_score: float,
    claim_score: float,
    safety: float,
    overall_score: float = 1.0,
) -> tuple[bool, bool]:
    """Determine if article should fail quality or just needs review.

    Fails (passed=False) on:
    - Any error-level finding
    - overall_score below 0.5
    - citation_score below 0.3
    - claim_score below 0.3
    - safety below 0.3

    Needs review (needs_review=True) on:
    - citation_score below 0.6
    - claim_score below 0.6
    - Any warning finding
    """
    has_error = any(f.severity == "error" for f in findings)
    if has_error:
        return True, True

    if overall_score < 0.5:
        return True, True

    if citation_score < 0.3 or claim_score < 0.3 or safety < 0.3:
        return True, True

    needs_review = (
        citation_score < 0.6
        or claim_score < 0.6
        or any(f.severity == "warning" for f in findings)
    )

    return False, needs_review


def build_quality_report(article: "Article") -> QualityReportResult:
    """Build a quality report for an article with full citation and claim verification.

    Args:
        article: Article model instance with final_article, research_brief,
                 original_url, and citations.

    Returns:
        QualityReportResult with scores, findings, and pass/review flags.
    """
    findings: list[QualityFinding] = []

    parsed_article, schema_findings = _parse_final_article(article.final_article)
    findings.extend(schema_findings)

    research_brief, rb_findings = _parse_research_brief(article.research_brief)
    findings.extend(rb_findings)

    if parsed_article is None:
        return QualityReportResult(
            overall_score=0.0,
            groundedness=0.0,
            coherence=0.0,
            completeness=0.0,
            safety=0.0,
            citation_score=0.0,
            claim_score=0.0,
            passed=False,
            needsreview=True,
            findings=findings,
            meta={},
        )

    existing_citations = [
        {"url": c.url}
        for c in article.citations  # type: ignore[attr-defined]
        if hasattr(c, "url")
    ]

    citation_findings = _verify_citations(
        parsed_article,
        research_brief,
        article.original_url,
        existing_citations,
    )
    findings.extend(citation_findings)

    article_text = _extract_text_fields(parsed_article)
    claim_findings = _check_unsupported_claims(article_text, research_brief)
    findings.extend(claim_findings)

    quote_findings = _check_direct_quotes(parsed_article, research_brief)
    findings.extend(quote_findings)

    quality_signals = lightweight_quality_signals(article_text)
    citation_score, claim_score = _compute_scores(
        quality_signals, citation_findings, claim_findings,
    )

    overall_score = (
        quality_signals.overall * 0.4
        + citation_score * 0.3
        + claim_score * 0.3
    )

    should_fail, needs_review = _should_fail_or_review(
        findings, citation_score, claim_score, quality_signals.safety,
        overall_score,
    )
    passed = not should_fail

    meta = {
        "citation_findings_count": len(citation_findings),
        "claim_findings_count": len(claim_findings),
        "quote_findings_count": len(quote_findings),
        "schema_findings_count": len(schema_findings),
    }

    return QualityReportResult(
        overall_score=round(overall_score, 3),
        groundedness=round(quality_signals.groundedness, 3),
        coherence=round(quality_signals.coherence, 3),
        completeness=round(quality_signals.completeness, 3),
        safety=round(quality_signals.safety, 3),
        citation_score=round(citation_score, 3),
        claim_score=round(claim_score, 3),
        passed=passed,
        needsreview=needs_review,
        findings=findings,
        meta=meta,
    )


def persist_quality_report(
    article: "Article",
    result: QualityReportResult,
    stage: str = "edit",
) -> "QualityReport":
    """Persist a quality report result to the database.

    Args:
        article: Article model instance.
        result: QualityReportResult from build_quality_report.
        stage: Pipeline stage name (default "edit").

    Returns:
        Persisted QualityReport model instance.
    """
    from extensions import db
    from models.quality import QualityReport

    latest_version = None
    if article.versions and hasattr(article, "versions"):
        try:
            latest_version = (
                article.versions.order_by(db.column("version_number").desc())
                .first()
            )
        except (AttributeError, TypeError):
            pass

    findings_dicts = [
        {
            "severity": f.severity,
            "code": f.code,
            "message": f.message,
            "field": f.field,
            "evidence": f.evidence,
        }
        for f in result.findings
    ]

    report = QualityReport(
        article_id=article.id,
        article_version_id=latest_version.id if latest_version else None,
        stage=stage,
        overall_score=result.overall_score,
        groundedness=result.groundedness,
        coherence=result.coherence,
        completeness=result.completeness,
        safety=result.safety,
        citation_score=result.citation_score,
        claim_score=result.claim_score,
        passed=result.passed,
        needs_review=result.needsreview,
        findings=findings_dicts,
        meta=result.meta,
    )

    db.session.add(report)
    db.session.commit()

    return report


@dataclass
class QualityThresholds:
    """Quality thresholds for determining pass/fail."""

    min_overall: float = 0.5
    min_citation: float = 0.3
    min_claim: float = 0.3
    min_safety: float = 0.5


def article_passes_quality(
    result: QualityReportResult,
    thresholds: QualityThresholds | None = None,
) -> bool:
    """Check if a quality report result passes configured thresholds.

    Args:
        result: QualityReportResult from build_quality_report.
        thresholds: Optional QualityThresholds instance. Uses defaults if None.

    Returns:
        True if article passes all thresholds. Defaults are conservative fail-open.
    """
    if thresholds is None:
        thresholds = QualityThresholds()

    if result.overall_score < thresholds.min_overall:
        return False
    if result.citation_score < thresholds.min_citation:
        return False
    if result.claim_score < thresholds.min_claim:
        return False
    if result.safety < thresholds.min_safety:
        return False

    error_findings = [f for f in result.findings if f.severity == "error"]
    if error_findings:
        return False

    return True
