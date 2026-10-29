from types import SimpleNamespace

from schemas.llm_responses import KeyClaim, ResearchBrief
from schemas.pipeline import PipelineOptimizationConfig, PipelineRootConfig
from services.pipeline_optimizations import (
    prepare_web_evidence,
    selector_prefilter_reason,
    should_contextualize_editor,
    should_synthesize_web_results,
)
from services.trend_memory import _deterministic_candidates


def _article(*, title="Routine release", body="A product release provides a small update.", brief=""):
    return SimpleNamespace(
        original_title=title,
        extracted_text=body,
        draft_article=body,
        research_brief=brief,
    )


def test_web_evidence_deduplicates_urls_and_limits_publisher_redundancy():
    results = prepare_web_evidence([
        {"title": "A", "url": "https://www.example.com/story?utm_source=x", "snippet": "one"},
        {"title": "A duplicate", "url": "https://example.com/story", "snippet": "same"},
        {"title": "B", "url": "https://example.com/second", "snippet": "two"},
        {"title": "C", "url": "https://example.com/third", "snippet": "three"},
        {"title": "D", "url": "https://other.example/news", "snippet": "four"},
    ])
    assert [result["title"] for result in results] == ["A", "B", "D"]
    assert all(result["source_kind"] == "search_snippet" for result in results)


def test_selector_prefilter_rejects_only_provable_duplicates_or_empty_artifacts():
    article = SimpleNamespace(
        id=3,
        original_title="AI model release",
        original_url="https://example.com/story?utm_source=mail",
        extracted_text="The article content is available.",
    )
    assert selector_prefilter_reason(article, [
        {"id": 1, "title": "A related AI model release", "url": "https://other.example/story", "pipeline_status": "done"},
    ]) is None
    assert selector_prefilter_reason(article, [
        {"id": 1, "title": "Different title", "url": "https://example.com/story", "pipeline_status": "done"},
    ]) == "exact_published_duplicate"
    assert selector_prefilter_reason(
        SimpleNamespace(id=4, original_title="", original_url="", extracted_text=""), [],
    ) == "invalid_empty_article"


def test_conditional_research_synthesis_only_triggers_on_complexity_or_disagreement():
    article = _article()
    routine = [{"url": "https://one.example/a", "snippet": "Routine release"}]
    assert should_synthesize_web_results(article, routine) is False

    heterogeneous = [
        {"url": "https://one.example/a", "snippet": "Report one"},
        {"url": "https://two.example/b", "snippet": "Report two"},
        {"url": "https://three.example/c", "snippet": "Report three"},
    ]
    assert should_synthesize_web_results(article, heterogeneous) is True
    conflicting = [{"url": "https://one.example/a", "snippet": "A correction disputes earlier figures"}]
    assert should_synthesize_web_results(article, conflicting) is True


def test_conditional_edit_contextualization_preserves_manual_policy_trigger():
    article = _article()
    assert should_contextualize_editor(article, [], {}, "") is False
    assert should_contextualize_editor(article, [], {"ai": ["Do not treat forecasts as results."]}, "") is True
    assert should_contextualize_editor(
        _article(brief='{"confidence": "low", "claim": "uncertain"}'), [], {}, "",
    ) is True


def test_deterministic_memory_candidates_require_confidence_source_and_topic():
    brief = ResearchBrief(
        source_summary="A research summary.",
        key_claims=[
            KeyClaim(
                claim="OpenAI released a new model with a published context window of one million tokens.",
                source="source_article",
                confidence="high",
            ),
            KeyClaim(
                claim="Researchers may later release a different model with a much larger context window.",
                source="source_article",
                confidence="low",
            ),
            KeyClaim(
                claim="A high confidence claim without any source attribution should not enter memory.",
                source="unattributed",
                confidence="high",
            ),
        ],
        newsworthiness="A significant model release.",
        impact_score=90,
    )
    final_article = (
        '{"headline":"OpenAI model release","body":"OpenAI released a new model with a published '
        'context window of one million tokens."}'
    )
    candidates = _deterministic_candidates(
        brief, {"ai": "ai"}, "https://example.com/story", final_article,
    )
    assert len(candidates) == 1
    assert candidates[0].topic == "ai"
    assert candidates[0].importance == 2
    assert candidates[0].evidence_confidence == "high"


def test_pipeline_optimization_switches_default_off_and_call_caps_validate():
    config = PipelineOptimizationConfig()
    assert not config.selector_prefilter_enabled
    assert not config.conditional_research_synthesis_enabled
    assert not config.conditional_edit_contextualization_enabled
    assert not config.memory_candidate_reuse_enabled
    assert not config.optional_llm_call_caps_enabled
    assert PipelineOptimizationConfig(
        optional_llm_call_caps_enabled=True,
        max_optional_llm_calls_per_article_per_day=2,
        max_optional_llm_calls_per_day=30,
    )
    assert PipelineRootConfig.model_construct(optimizations=config).optimizations is config


def test_optional_call_budget_denies_atomic_reservation_at_cap():
    from unittest.mock import patch

    from services.optional_llm_budget import reserve_optional_llm_call

    calls = []

    class FakeRedis:
        def register_script(self, script):
            assert "INCR" in script

            def reserve(*, keys, args):
                calls.append((keys, args))
                return 0

            return reserve

    configured = PipelineRootConfig.model_construct(
        optimizations=PipelineOptimizationConfig(
            optional_llm_call_caps_enabled=True,
            max_optional_llm_calls_per_article_per_day=2,
            max_optional_llm_calls_per_day=10,
        )
    )
    with patch("schemas.pipeline.load_pipeline_config", return_value=configured):
        with patch("extensions.get_redis", return_value=FakeRedis()):
            with patch("services.optional_llm_budget._record_decision"):
                assert reserve_optional_llm_call(42, "research_synthesis") is False
    assert len(calls) == 1
    assert calls[0][1] == [2, 10, 172800]


def test_memory_proposal_reuses_structured_claim_without_provider_call(app, create_article):
    from unittest.mock import patch

    from extensions import db
    from schemas.pipeline import MemoryConfig
    from services.trend_memory import propose_trend_memory

    brief = ResearchBrief(
        source_summary="A research summary.",
        key_claims=[KeyClaim(
            claim="A company released a new AI model with a documented one million token context window.",
            source="source_article",
            confidence="high",
        )],
        newsworthiness="A significant model release.",
        impact_score=90,
    )
    config = PipelineRootConfig.model_construct(
        memory=MemoryConfig(),
        optimizations=PipelineOptimizationConfig(memory_candidate_reuse_enabled=True),
    )
    with app.app_context():
        article = create_article(
            pipeline_status="done",
            category="ai",
            topics=["ai"],
            final_article=(
                '{"headline":"AI model release","body":"A company released a new AI model with a '
                'documented one million token context window."}'
            ),
            research_brief=brief.model_dump_json(),
        )
        db.session.commit()
        with patch("schemas.pipeline.load_pipeline_config", return_value=config):
            with patch("services.trend_memory._save_memory_entries", return_value=1) as save:
                with patch("services.trend_memory._call_llm_for_memory", side_effect=AssertionError("extra call")):
                    response = propose_trend_memory(article)
        assert "Reused 1" in response.synthesis
        assert save.call_args.args[0][0].signal == brief.key_claims[0].claim
