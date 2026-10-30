"""Final-field citation, quote, number and originality audit tests."""

from __future__ import annotations

import json
from types import SimpleNamespace

from services.editorial_audit import audit_final_artifact


def _article(body, *, citations=None, excerpt="Acme made the Nova 3 system available on Tuesday."):
    source = {
        "evidence_source_id": "ev_1",
        "retrieval_status": "retrieved",
        "url": "https://example.test/report",
        "excerpt": excerpt,
    }
    claim = {
        "claim": "Acme made Nova 3 available Tuesday.",
        "supports": [{"evidence_source_id": "ev_1", "span": "Acme made the Nova 3 system available on Tuesday."}],
        "contradicts": [],
    }
    final = {
        "headline": "Acme makes Nova 3 available",
        "tldr": "Nova 3 is available.",
        "why_it_matters": "The timing matters.",
        "body": body,
        "key_points": [],
        "what_to_watch": "Availability expands next.",
        "citations": citations or [{"url": "https://example.test/report", "title": "Report"}],
    }
    return SimpleNamespace(
        final_article=json.dumps(final),
        editorial_dossier=SimpleNamespace(
            status="verified",
            payload={"sources": [source], "claims": [claim]},
        ),
    )


def test_audits_all_final_fields_and_rejects_unsupported_number():
    article = _article("The rollout reaches 4.7 million users.")

    result = audit_final_artifact(article)

    assert result["passed"] is False
    assert any(item["code"] == "UNSUPPORTED_NUMBER" for item in result["findings"])


def test_rejects_fake_citation_and_nonverbatim_quote():
    article = _article(
        'The company said, "A wholly invented quotation appears here."',
        citations=[{"url": "https://fake.test/made-up", "title": "Fake"}],
    )

    result = audit_final_artifact(article)

    codes = {finding["code"] for finding in result["findings"]}
    assert "CITATION_NOT_IN_DOSSIER" in codes
    assert "QUOTE_NOT_VERBATIM" in codes


def test_flags_long_verbatim_overlap_but_not_short_shared_terms():
    sentence = "Acme made the Nova 3 system available on Tuesday after completing its staged rollout."
    copied = _article(sentence, excerpt=sentence)
    short = _article("Acme released Nova 3 on Tuesday.", excerpt=sentence)

    assert "LONG_VERBATIM_OVERLAP" in {f["code"] for f in audit_final_artifact(copied)["findings"]}
    assert "LONG_VERBATIM_OVERLAP" not in {f["code"] for f in audit_final_artifact(short)["findings"]}


def test_labeled_synthetic_overlap_corpus_has_no_observed_false_flags():
    corpus = [
        {
            "label": "copied",
            "body": "Acme made the Nova 3 system available on Tuesday after completing its staged rollout.",
            "source": "Acme made the Nova 3 system available on Tuesday after completing its staged rollout.",
        },
        {
            "label": "copied",
            "body": "The announcement comes after the company spent months preparing a staged rollout for all customers.",
            "source": "The announcement comes after the company spent months preparing a staged rollout for all customers.",
        },
        {
            "label": "clean",
            "body": "The vendor says the new release is available to customers this week.",
            "source": "Acme made the Nova 3 system available on Tuesday after completing its staged rollout.",
        },
        {
            "label": "clean",
            "body": "Nova 3 adds a 64-bit mode and supports Python 3.12 workloads.",
            "source": "The release notes list Nova 3, 64-bit mode, and Python 3.12 compatibility.",
        },
        {
            "label": "clean",
            "body": 'The notice says, "Available to all users starting Tuesday."',
            "source": "Available to all users starting Tuesday.",
        },
    ]
    true_positive = false_positive = 0
    for sample in corpus:
        result = audit_final_artifact(_article(sample["body"], excerpt=sample["source"]))
        flagged = "LONG_VERBATIM_OVERLAP" in {finding["code"] for finding in result["findings"]}
        if sample["label"] == "copied":
            true_positive += int(flagged)
            assert flagged
        else:
            false_positive += int(flagged)
            assert not flagged

    assert true_positive == 2
    assert false_positive == 0
