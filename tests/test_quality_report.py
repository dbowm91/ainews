"""Tests for services/quality_report.py - Persisted quality reporting service."""

import json

from services.quality_report import (
    QualityFinding,
    QualityReportResult,
    _check_direct_quotes,
    _check_unsupported_claims,
    _parse_final_article,
    _verify_citations,
    article_passes_quality,
    build_quality_report,
    persist_quality_report,
)


class TestParseFinalArticle:
    """Tests for _parse_final_article function."""

    def test_valid_article_returns_parsed(self, app):
        """Returns parsed dict for valid final_article JSON."""
        with app.app_context():
            article_data = '{"headline": "Test", "tldr": "Summary", "body": "Content."}'
            parsed, findings = _parse_final_article(article_data)
            assert parsed is not None
            assert parsed["headline"] == "Test"
            assert len(findings) == 0

    def test_invalid_json_returns_error_finding(self, app):
        """Returns schema_error finding for invalid JSON."""
        with app.app_context():
            parsed, findings = _parse_final_article("not valid json")
            assert parsed is None
            assert len(findings) == 1
            assert findings[0].code == "schema_error"
            assert findings[0].severity == "error"

    def test_empty_string_returns_error_finding(self, app):
        """Returns error finding for empty final_article."""
        with app.app_context():
            parsed, findings = _parse_final_article("")
            assert parsed is None
            assert any(f.code == "schema_error" for f in findings)

    def test_missing_required_fields_returns_error_finding(self, app):
        """Returns schema errors for missing required fields."""
        with app.app_context():
            parsed, findings = _parse_final_article('{"headline": "Test"}')
            assert len(findings) > 0
            assert any("Required field" in f.message for f in findings)


class TestVerifyCitations:
    """Tests for _verify_citations function."""

    def test_citation_url_in_research_brief_passes(self, app):
        """Citation with URL in research_brief.external_sources passes."""
        with app.app_context():
            parsed = {
                "citations": [{"title": "Source", "url": "https://example.com/news"}],
                "body": "Some content",
            }
            research_brief = {
                "external_sources": [
                    {"title": "Source", "url": "https://example.com/news", "snippet": "..."}
                ],
                "key_claims": [],
                "direct_quotes": [],
            }
            findings = _verify_citations(parsed, research_brief, None, [])
            assert len(findings) == 0

    def test_citation_url_in_original_url_passes(self, app):
        """Citation with URL matching article original_url passes."""
        with app.app_context():
            parsed = {
                "citations": [{"title": "Original", "url": "https://example.com/article"}],
                "body": "Some content",
            }
            findings = _verify_citations(parsed, None, "https://example.com/article", [])
            assert len(findings) == 0

    def test_citation_url_in_existing_citations_passes(self, app):
        """Citation with URL in existing Citation rows passes."""
        with app.app_context():
            parsed = {
                "citations": [{"title": "Ref", "url": "https://example.com/ref"}],
                "body": "Some content",
            }
            existing = [{"url": "https://example.com/ref"}]
            findings = _verify_citations(parsed, None, None, existing)
            assert len(findings) == 0

    def test_unknown_citation_url_creates_warning(self, app):
        """Citation URL not in research/original/citations creates warning."""
        with app.app_context():
            parsed = {
                "citations": [{"title": "Unknown", "url": "https://unknown.com/article"}],
                "body": "Some content",
            }
            findings = _verify_citations(parsed, None, None, [])
            assert len(findings) == 1
            assert findings[0].code == "unknown_citation_url"
            assert findings[0].severity == "warning"

    def test_citation_without_url_creates_warning(self, app):
        """Citation without URL creates missing_citation warning."""
        with app.app_context():
            parsed = {
                "citations": [{"title": "No URL"}],
                "body": "Some content",
            }
            findings = _verify_citations(parsed, None, None, [])
            assert len(findings) == 1
            assert findings[0].code == "missing_citation"


class TestCheckUnsupportedClaims:
    """Tests for _check_unsupported_claims function."""

    def test_claim_with_matching_key_claim_passes(self, app):
        """Numeric/date claim with overlapping key claim source does not flag."""
        with app.app_context():
            from schemas.llm_responses import ResearchBrief, KeyClaim, ExternalSource

            rb = ResearchBrief(
                source_summary="Test",
                key_claims=[
                    KeyClaim(
                        claim="Company announced 50 percent revenue growth in Q4.",
                        source="https://example.com/pr",
                        confidence="high",
                    )
                ],
                direct_quotes=[],
                external_sources=[
                    ExternalSource(
                        title="PR", url="https://example.com/pr", snippet="50 percent revenue growth"
                    )
                ],
                related_articles=[],
                context_notes="",
                newsworthiness="",
                impact_score=50,
            )
            text = "Company announced 50 percent revenue growth in Q4."
            findings = _check_unsupported_claims(text, rb)
            assert len(findings) == 0

    def test_numeric_claim_without_source_creates_finding(self, app):
        """Numeric claim without overlapping key claim creates warning."""
        with app.app_context():
            from schemas.llm_responses import ResearchBrief, KeyClaim

            rb = ResearchBrief(
                source_summary="Test",
                key_claims=[
                    KeyClaim(
                        claim="Different claim about something else.",
                        source="https://example.com/other",
                        confidence="high",
                    )
                ],
                direct_quotes=[],
                external_sources=[],
                related_articles=[],
                context_notes="",
                newsworthiness="",
                impact_score=50,
            )
            text = "Company X has grown to 10 million users as of January 2024."
            findings = _check_unsupported_claims(text, rb)
            numeric_findings = [f for f in findings if "numeric" in f.evidence.get("claim_types", [])]
            assert len(numeric_findings) == 1
            assert numeric_findings[0].code == "unsupported_claim"


class TestCheckDirectQuotes:
    """Tests for _check_direct_quotes function."""

    def test_quote_in_direct_quotes_passes(self, app):
        """Quote text matching direct_quotes does not flag."""
        with app.app_context():
            from schemas.llm_responses import ResearchBrief, DirectQuote

            rb = ResearchBrief(
                source_summary="Test",
                key_claims=[],
                direct_quotes=[
                    DirectQuote(
                        quote="This is a direct quote from the CEO.",
                        attribution="CEO Jane Smith",
                        source_url="https://example.com/ceo",
                    )
                ],
                external_sources=[],
                related_articles=[],
                context_notes="",
                newsworthiness="",
                impact_score=50,
            )
            parsed = {"body": 'The CEO said "This is a direct quote from the CEO."'}
            findings = _check_direct_quotes(parsed, rb)
            assert len(findings) == 0

    def test_quote_not_in_direct_quotes_creates_finding(self, app):
        """Quote text not in direct_quotes creates warning."""
        with app.app_context():
            from schemas.llm_responses import ResearchBrief, DirectQuote

            rb = ResearchBrief(
                source_summary="Test",
                key_claims=[],
                direct_quotes=[
                    DirectQuote(
                        quote="Different quote entirely.",
                        attribution="Someone",
                        source_url="https://example.com/quote",
                    )
                ],
                external_sources=[],
                related_articles=[],
                context_notes="",
                newsworthiness="",
                impact_score=50,
            )
            parsed = {"body": 'The CEO said "This is not in the research brief."'}
            findings = _check_direct_quotes(parsed, rb)
            assert len(findings) == 1
            assert findings[0].code == "quote_mismatch"

    def test_no_direct_quotes_no_findings(self, app):
        """Article without quotes returns no findings."""
        with app.app_context():
            parsed = {"body": "This is regular content without quotes."}
            findings = _check_direct_quotes(parsed, None)
            assert len(findings) == 0


class TestBuildQualityReport:
    """Tests for build_quality_report function."""

    def test_valid_article_with_matching_citation_passes(self, app, create_article):
        """Valid article with citation in research passes quality."""
        with app.app_context():
            article = create_article(
                final_article=json.dumps({
                    "headline": "Test Article",
                    "tldr": "Test summary",
                    "body": "Content about AI.",
                    "key_points": ["Point 1"],
                    "what_to_watch": "Future developments.",
                    "citations": [
                        {"title": "Source", "url": "https://example.com/source", "type": "article"}
                    ],
                    "original_attribution": {
                        "source": "Original Source",
                        "url": "https://example.com/article",
                        "author": "Author Name",
                    },
                }),
                research_brief=json.dumps({
                    "source_summary": "Test summary",
                    "key_claims": [
                        {"claim": "AI is growing", "source": "https://example.com/article", "confidence": "high"}
                    ],
                    "direct_quotes": [],
                    "external_sources": [
                        {"title": "Source", "url": "https://example.com/source", "snippet": "Content"}
                    ],
                    "related_articles": [],
                    "context_notes": "",
                    "newsworthiness": "Significant",
                    "impact_score": 50,
                }),
            )
            result = build_quality_report(article)
            assert result.passed is True
            assert result.citation_score > 0
            assert len(result.findings) == 0

    def test_invalid_final_article_json_creates_schema_finding(self, app, create_article):
        """Invalid JSON in final_article creates schema_error finding."""
        with app.app_context():
            article = create_article(
                final_article="not valid json",
                research_brief=json.dumps({
                    "source_summary": "Test",
                    "key_claims": [],
                    "direct_quotes": [],
                    "external_sources": [],
                    "related_articles": [],
                    "context_notes": "",
                    "newsworthiness": "Test",
                    "impact_score": 50,
                }),
            )
            result = build_quality_report(article)
            assert any(f.code == "schema_error" for f in result.findings)

    def test_unknown_citation_url_creates_finding_and_lowers_score(self, app, create_article):
        """Citation URL not in research creates warning and lowers citation_score."""
        with app.app_context():
            article = create_article(
                final_article=json.dumps({
                    "headline": "Test",
                    "tldr": "Summary",
                    "body": "Content.",
                    "citations": [
                        {"title": "Unknown", "url": "https://unknown.com/fake"}
                    ],
                    "original_attribution": {
                        "source": "Test",
                        "url": "https://example.com/original",
                    },
                }),
                research_brief=json.dumps({
                    "source_summary": "Test",
                    "key_claims": [
                        {"claim": "Claim", "source": "https://example.com/original", "confidence": "high"}
                    ],
                    "direct_quotes": [],
                    "external_sources": [],
                    "related_articles": [],
                    "context_notes": "",
                    "newsworthiness": "Test",
                    "impact_score": 50,
                }),
            )
            result = build_quality_report(article)
            citation_warnings = [f for f in result.findings if f.code == "unknown_citation_url"]
            assert len(citation_warnings) == 1
            assert result.citation_score < 1.0


class TestPersistQualityReport:
    """Tests for persist_quality_report function."""

    def test_persists_quality_report_to_db(self, app, create_article):
        """persist_quality_report saves report to database."""
        with app.app_context():
            from models import QualityReport

            article = create_article(
                final_article=json.dumps({
                    "headline": "Test",
                    "tldr": "Summary",
                    "body": "Content",
                    "citations": [],
                    "original_attribution": {"source": "Test"},
                }),
            )
            result = build_quality_report(article)
            report = persist_quality_report(article, result)

            assert report.id is not None
            assert report.article_id == article.id
            assert report.passed == result.passed
            assert report.overall_score == result.overall_score

            db_report = QualityReport.query.get(report.id)
            assert db_report is not None
            assert db_report.passed == result.passed


class TestArticlePassesQuality:
    """Tests for article_passes_quality function."""

    def test_returns_true_for_passing_result(self, app):
        """Returns True when all thresholds pass and no error findings."""
        with app.app_context():
            result = QualityReportResult(
                overall_score=0.8,
                groundedness=0.7,
                coherence=0.7,
                completeness=0.7,
                safety=0.9,
                citation_score=0.8,
                claim_score=0.8,
                passed=True,
                needsreview=False,
                findings=[],
                meta={},
            )
            assert article_passes_quality(result) is True

    def test_returns_false_for_error_finding(self, app):
        """Returns False when there are error-level findings."""
        with app.app_context():
            result = QualityReportResult(
                overall_score=0.8,
                groundedness=0.7,
                coherence=0.7,
                completeness=0.7,
                safety=0.9,
                citation_score=0.8,
                claim_score=0.8,
                passed=False,
                needsreview=True,
                findings=[
                    QualityFinding(
                        severity="error",
                        code="unknown_citation_url",
                        message="Test",
                        field="citations",
                        evidence={},
                    )
                ],
                meta={},
            )
            assert article_passes_quality(result) is False

    def test_respects_custom_thresholds(self, app):
        """Respects custom QualityThresholds settings."""
        with app.app_context():
            from services.quality_report import QualityThresholds

            result = QualityReportResult(
                overall_score=0.6,
                groundedness=0.5,
                coherence=0.5,
                completeness=0.5,
                safety=0.8,
                citation_score=0.5,
                claim_score=0.5,
                passed=True,
                needsreview=False,
                findings=[],
                meta={},
            )
            thresholds = QualityThresholds(min_overall=0.7)
            assert article_passes_quality(result, thresholds) is False
