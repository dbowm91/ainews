"""Bounded editor repair feedback for unsupported final statements."""

from tasks.edit import _final_claim_repair_context


def test_repair_feedback_contains_only_unverified_final_statements():
    context = _final_claim_repair_context({
        "claims": [
            {"claim": "body: unsupported synthetic claim", "status": "unverified"},
            {"claim": "body: verified synthetic claim", "status": "primary_supported"},
        ],
    })

    assert context == ["Unverified final statement: body: unsupported synthetic claim"]


def test_repair_feedback_is_bounded():
    assert _final_claim_repair_context({"claims": [
        {"claim": f"claim {index}", "status": "unverified"}
        for index in range(25)
    ]}) is None
    assert _final_claim_repair_context({"claims": [
        {"claim": "x" * 500, "status": "unverified"}
        for _ in range(9)
    ]}) is None


def test_repair_feedback_includes_deterministic_audit_categories():
    context = _final_claim_repair_context(
        {"status": "verified", "claims": []},
        {"findings": [
            {"code": "UNSUPPORTED_NUMBER", "value": "123"},
            {"code": "LONG_VERBATIM_OVERLAP", "token_run": 12},
        ]},
    )

    assert context is not None
    assert any("numbers" in issue for issue in context)
    assert any("original language" in issue for issue in context)
