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


def test_claim_verification_batches_large_ledgers(app, create_article):
    from extensions import db
    from services.editorial_evidence import verify_claims

    with app.app_context():
        article = create_article(pipeline_status="researching")
        _create_dossier(article, [{
            "evidence_source_id": "ev_one",
            "retrieval_status": "retrieved",
            "source_type": "primary_document",
            "source_family": "publisher:one.example",
            "source_family_confidence": "registry",
            "excerpt": "The notice says the release is available.",
        }], db)
        provider = MagicMock()

        def assess_batch(**kwargs):
            user_prompt = kwargs["messages"][0]["content"]
            batch_size = user_prompt.count("<claim index=")
            return SimpleNamespace(assessments=[SimpleNamespace(
                claim_index=index,
                decision="supported",
                evidence=[{
                    "evidence_source_id": "ev_one",
                    "span": "The notice says the release is available.",
                }],
                rationale="Exact source span.",
            ) for index in range(batch_size)])

        provider.chat_structured.side_effect = assess_batch
        result = verify_claims(
            article,
            [f"The release claim {index} is supported." for index in range(7)],
            provider,
            "test-model",
        )

        assert provider.chat_structured.call_count == 3
        assert result["status"] == "verified"
        assert len(result["claims"]) == 7


def test_research_can_drop_unsupported_candidate_claims_but_strict_audit_cannot(
    app, create_article, monkeypatch,
):
    from extensions import db
    from services.editorial_evidence import verify_claims

    monkeypatch.setattr(
        "schemas.pipeline.load_pipeline_config",
        lambda: SimpleNamespace(evidence=SimpleNamespace(allow_single_source_attributed=True)),
    )
    with app.app_context():
        article = create_article(pipeline_status="researching")
        _create_dossier(article, [{
            "evidence_source_id": "ev_one",
            "retrieval_status": "retrieved",
            "source_type": "secondary_reporting",
            "source_family": "newsroom:one",
            "source_family_confidence": "registry",
            "excerpt": "The notice states the release is available.",
        }], db)
        provider = MagicMock()
        provider.chat_structured.return_value = SimpleNamespace(assessments=[
            SimpleNamespace(
                claim_index=0, decision="supported",
                evidence=[{"evidence_source_id": "ev_one", "span": "The notice states the release is available."}],
                rationale="Exact source span.",
            ),
            SimpleNamespace(claim_index=1, decision="unclear", evidence=[], rationale="No support."),
        ])

        candidates = ["The release is available.", "A second claim lacks support."]
        partial = verify_claims(article, candidates, provider, "test-model", allow_partial=True)
        assert partial["status"] == "verified"
        assert partial["claims"][0]["is_material"] is True
        assert partial["claims"][1]["is_material"] is False

        strict = verify_claims(article, candidates, provider, "test-model")
        assert strict["status"] == "unverified"
        assert all(claim["is_material"] for claim in strict["claims"])


def test_final_claim_audit_does_not_replace_research_ledger(app, create_article):
    from extensions import db
    from services.editorial_evidence import audit_final_claims

    with app.app_context():
        article = create_article(pipeline_status="editing")
        dossier = _create_dossier(article, [{
            "evidence_source_id": "ev_one",
            "retrieval_status": "retrieved",
            "source_type": "primary_document",
            "source_family": "publisher:one.example",
            "source_family_confidence": "registry",
            "excerpt": "The notice confirms the release is available.",
        }], db)
        dossier.status = "verified"
        research_claim = {
            "claim_id": "research-claim",
            "claim": "The release is available.",
            "status": "primary_supported",
            "supports": [{
                "evidence_source_id": "ev_one",
                "span": "The notice confirms the release is available.",
            }],
            "is_material": True,
            "publish_allowed": True,
        }
        dossier.payload = {"sources": dossier.payload["sources"], "claims": [research_claim], "revision": 1}
        article.final_article = (
            '{"headline":"Release update","tldr":"It is available now.",'
            '"why_it_matters":"","body":"It is available now.",'
            '"key_points":[],"what_to_watch":"","citations":[],"original_attribution":'
            '{"source":"Notice"},"tags":[]}'
        )
        provider = MagicMock()
        provider.chat_structured.return_value = SimpleNamespace(assessments=[SimpleNamespace(
            claim_index=0,
            decision="supported",
            evidence=[{
                "evidence_source_id": "ev_one",
                "span": "The notice confirms the release is available.",
            }],
            rationale="Exact span.",
        )])

        result = audit_final_claims(article, provider, "test-model")

        assert result["status"] == "verified"
        assert result["statement_count"] == 1
        assert dossier.status == "verified"
        assert dossier.payload["claims"][0]["claim_id"] == "research-claim"


@pytest.mark.parametrize(
    "source_type,expected",
    [("primary_document", "primary_supported"), ("secondary_reporting", "single_source")],
)
def test_one_source_only_counts_as_primary_with_primary_document(
    app, create_article, source_type, expected, monkeypatch,
):
    monkeypatch.setattr(
        "schemas.pipeline.load_pipeline_config",
        lambda: SimpleNamespace(
            evidence=SimpleNamespace(allow_single_source_attributed=False),
        ),
    )
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


def test_single_secondary_source_is_publishable_only_with_explicit_personal_policy(
    app, create_article, monkeypatch,
):
    from types import SimpleNamespace

    from extensions import db
    from services.editorial_evidence import build_verified_packet, verify_claims

    with app.app_context():
        article = create_article(pipeline_status="researching")
        _create_dossier(article, [{
            "evidence_source_id": "ev_one",
            "retrieval_status": "retrieved",
            "source_type": "secondary_reporting",
            "source_family": "newsroom:one",
            "source_family_confidence": "registry",
            "title": "Test report",
            "url": "https://news.example.test/report",
            "publisher": "news.example.test",
            "excerpt": "Acme announced Nova 3 on Tuesday.",
        }], db)
        monkeypatch.setattr(
            "schemas.pipeline.load_pipeline_config",
            lambda: SimpleNamespace(
                evidence=SimpleNamespace(allow_single_source_attributed=True),
            ),
        )
        provider = MagicMock()
        provider.chat_structured.return_value = SimpleNamespace(assessments=[SimpleNamespace(
            claim_index=0,
            decision="supported",
            evidence=[{
                "evidence_source_id": "ev_one",
                "span": "Acme announced Nova 3 on Tuesday.",
            }],
            rationale="The exact excerpt states the claim.",
        )])

        result = verify_claims(
            article, ["Acme announced Nova 3 on Tuesday."], provider, "test-model",
        )

        assert result["status"] == "verified"
        claim = result["claims"][0]
        assert claim["status"] == "single_source_supported"
        assert claim["publish_allowed"] is True
        packet = build_verified_packet(article)
        assert packet["claims"][0]["status"] == "single_source_supported"
        assert packet["sources"][0]["url"] == "https://news.example.test/report"


def test_supported_claim_requires_a_nonempty_typed_evidence_span():
    from pydantic import ValidationError

    from schemas.llm_responses import ClaimEvidenceAssessment

    with pytest.raises(ValidationError):
        ClaimEvidenceAssessment(
            claim_index=0, decision="supported", evidence=[], rationale="",
        )

    with pytest.raises(ValidationError):
        ClaimEvidenceAssessment(
            claim_index=0,
            decision="supported",
            evidence=[{"source": "ev_1", "quote": "an unrecognized shape"}],
            rationale="",
        )
