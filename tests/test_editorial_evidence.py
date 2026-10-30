"""Synthetic, copyright-safe regression cases for evidence handling."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.editorial_evidence import (
    build_research_queries,
    retrieve_search_candidates,
)


def test_query_plan_is_bounded_and_diverse():
    queries = build_research_queries("Acme launches Nova 3 AI model", ["ai"])

    assert 1 <= len(queries) <= 4
    assert len(set(queries)) == len(queries)
    assert len({query.rsplit(" ", 1)[-1] for query in queries}) > 1
    assert all(query != "Acme launches Nova 3 AI model" for query in queries)


def test_identical_syndicated_content_collapses_to_one_evidence_family(monkeypatch):
    from services.content_extractor import ExtractionResult, ExtractionStatus
    from services import content_extractor

    story = (
        "A synthetic public bulletin describes a newly announced system and its release date. "
        "The bulletin states that the service becomes available next month to all users. "
    ) * 4
    monkeypatch.setattr(
        content_extractor,
        "extract_article",
        lambda url: ExtractionResult(url, story, "Synthetic bulletin", None, ExtractionStatus.SUCCESS),
    )
    leads = [
        SimpleNamespace(url="https://one.example/story", title="One", snippet="lead"),
        SimpleNamespace(url="https://two.example/story", title="Two", snippet="lead"),
    ]

    sources = retrieve_search_candidates(leads)

    assert len(sources) == 2
    assert sources[0].source_family == sources[1].source_family
    assert sources[1].source_family_confidence == "content_lineage_inferred"
    assert sources[0].retrieval_status == "retrieved"


def test_short_lived_document_cache_avoids_second_fetch(app, monkeypatch):
    from datetime import datetime, timezone

    from extensions import db
    from models import EvidenceDocumentCache
    from services import content_extractor

    with app.app_context():
        source = EvidenceDocumentCache(
            canonical_url="https://cache.example/report",
            final_url="https://cache.example/report",
            title="Cached report",
            publisher="cache.example",
            source_type="secondary_reporting",
            retrieval_status="retrieved",
            excerpt="The cached excerpt contains a synthetic verified fact.",
            content_digest="a" * 64,
            acquired_at=datetime.now(timezone.utc),
        )
        db.session.add(source)
        db.session.flush()
        monkeypatch.setattr(content_extractor, "extract_article", lambda *_: pytest.fail("cache miss"))

        results = retrieve_search_candidates([
            SimpleNamespace(url="https://cache.example/report", title="Search title", snippet="lead")
        ])

        assert results[0].retrieval_status == "retrieved"
        assert results[0].excerpt.startswith("The cached excerpt")
        assert results[0].evidence_source_id.startswith("ev_")


def _create_dossier(article, sources, db):
    from models import EditorialDossier

    row = EditorialDossier(
        article_id=article.id,
        revision=1,
        policy_version="evidence-first-v1",
        status="collecting",
        payload={"sources": sources, "claims": []},
        content_digest="d" * 64,
    )
    db.session.add(row)
    db.session.flush()
    return row


def test_claim_support_requires_valid_server_minted_handles_and_spans(app, create_article):
    from extensions import db
    from services.editorial_evidence import verify_claims

    with app.app_context():
        article = create_article(pipeline_status="researching")
        _create_dossier(article, [
            {"evidence_source_id": "ev_one", "retrieval_status": "retrieved", "source_type": "secondary_reporting", "source_family": "newsroom:reuters", "source_family_confidence": "registry", "excerpt": "Acme announced Nova 3 on Tuesday."},
            {"evidence_source_id": "ev_two", "retrieval_status": "retrieved", "source_type": "secondary_reporting", "source_family": "newsroom:associated_press", "source_family_confidence": "registry", "excerpt": "Acme announced Nova 3 on Tuesday."},
        ], db)
        provider = MagicMock()
        provider.chat_structured.return_value = SimpleNamespace(assessments=[SimpleNamespace(
            claim_index=0,
            decision="supported",
            evidence=[
                {"evidence_source_id": "ev_one", "span": "Acme announced Nova 3 on Tuesday."},
                {"evidence_source_id": "ev_two", "span": "Acme announced Nova 3 on Tuesday."},
            ],
            rationale="The passages agree.",
        )])

        verified = verify_claims(article, ["Acme announced Nova 3 on Tuesday."], provider, "test-model")
        assert verified["status"] == "verified"
        assert verified["claims"][0]["independent_origin_count"] == 2

        provider.chat_structured.return_value = SimpleNamespace(assessments=[SimpleNamespace(
            claim_index=0,
            decision="supported",
            evidence=[{"evidence_source_id": "model_forged", "span": "Acme announced Nova 3 on Tuesday."}],
            rationale="Claimed support.",
        )])
        rejected = verify_claims(article, ["Acme announced Nova 3 on Tuesday."], provider, "test-model")
        assert rejected["status"] == "unverified"
        assert rejected["claims"][0]["supports"] == []


@pytest.mark.parametrize(
    "source_type,expected",
    [("primary_document", "primary_supported"), ("secondary_reporting", "single_source")],
)
def test_one_source_only_counts_as_primary_with_primary_document(app, create_article, source_type, expected):
    from extensions import db
    from services.editorial_evidence import verify_claims

    with app.app_context():
        article = create_article(pipeline_status="researching")
        _create_dossier(article, [{
            "evidence_source_id": "ev_one", "retrieval_status": "retrieved",
            "source_type": source_type, "source_family": "publisher:one.example",
            "source_family_confidence": "inferred", "excerpt": "The notice states version 3.2 is available.",
        }], db)
        provider = MagicMock()
        provider.chat_structured.return_value = SimpleNamespace(assessments=[SimpleNamespace(
            claim_index=0, decision="supported",
            evidence=[{"evidence_source_id": "ev_one", "span": "The notice states version 3.2 is available."}],
            rationale="The excerpt directly states the version.",
        )])

        result = verify_claims(article, ["The notice states version 3.2 is available."], provider, "test-model")

        assert result["claims"][0]["status"] == expected
        assert (result["status"] == "verified") is (expected == "primary_supported")
