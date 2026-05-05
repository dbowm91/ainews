"""Tests for subagent response models."""



class TestSubagentResponse:
    """Test SubagentResponse model."""

    def test_subagent_response_defaults(self):
        from schemas.llm_responses import SubagentResponse

        resp = SubagentResponse(synthesis="test synthesis")
        assert resp.synthesis == "test synthesis"
        assert resp.used_fallback is False
        assert resp.fallback_stages == []


class TestResearchSynthesisResponse:
    """Test ResearchSynthesisResponse model."""

    def test_research_synthesis_response(self):
        from schemas.llm_responses import ResearchSynthesisResponse

        resp = ResearchSynthesisResponse(synthesis="web synthesis content")
        assert resp.synthesis == "web synthesis content"


class TestEditContextualizationResponse:
    """Test EditContextualizationResponse model."""

    def test_edit_contextualization_response(self):
        from schemas.llm_responses import EditContextualizationResponse

        resp = EditContextualizationResponse(synthesis="context notes")
        assert resp.synthesis == "context notes"