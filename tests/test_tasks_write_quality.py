"""Writer-stage quality gates should accept concise but usable drafts."""

from schemas.llm_responses import CitationItem, CondensedArticle, OriginalAttribution
from tasks.write import _canonicalize_verified_citations, _is_degenerate_write


def _draft(body: str) -> CondensedArticle:
    return CondensedArticle(
        headline="A useful local news reader",
        tldr="The tool keeps saved reading local.",
        body=body,
        key_points=["Feeds stay on device."],
        citations=[CitationItem(title="Notice", url="https://example.test/notice")],
        original_attribution=OriginalAttribution(source="Notice"),
    )


def test_writer_accepts_compact_draft_over_minimum_body_length():
    draft = _draft("x" * 320)

    assert _is_degenerate_write(draft) is False


def test_writer_rejects_draft_below_minimum_body_length():
    draft = _draft("x" * 319)

    assert _is_degenerate_write(draft) is True


def test_writer_canonicalizes_only_equivalent_verified_citation_urls():
    draft = _draft("x" * 420)
    draft.citations[0].url = "https://example.test/notice/?utm_source=feed"

    invalid = _canonicalize_verified_citations(
        draft, {"https://example.test/notice"},
    )

    assert invalid == []
    assert draft.citations[0].url == "https://example.test/notice"


def test_writer_rejects_citations_to_a_different_path_or_domain():
    draft = _draft("x" * 420)
    draft.citations[0].url = "https://other.example.test/notice"

    invalid = _canonicalize_verified_citations(
        draft, {"https://example.test/notice"},
    )

    assert len(invalid) == 1
