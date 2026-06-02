from unittest.mock import MagicMock, patch

from services.researcher import build_research_prompt, get_researcher_system_prompt
from services.writer import build_writer_prompt, get_writer_system_prompt


def _make_pipeline_mock(role_system_prompt="yaml-prompt", experiments=None):
    """Create mock modules for schemas.pipeline and services.prompts."""
    mock_rc = MagicMock(system_prompt=role_system_prompt)
    mock_config = MagicMock(experiments=experiments or {})

    mock_pipeline = MagicMock()
    mock_pipeline.get_role_config = MagicMock(return_value=mock_rc)
    mock_pipeline.load_pipeline_config = MagicMock(return_value=mock_config)

    mock_prompts = MagicMock()
    mock_prompts.get_system_prompt = MagicMock()

    return mock_pipeline, mock_prompts


class TestGetWriterSystemPrompt:
    """Tests for get_writer_system_prompt."""

    def test_returns_default_when_no_article(self):
        mock_pipeline, mock_prompts = _make_pipeline_mock()
        mock_prompts.get_system_prompt.return_value = "default-prompt"
        with patch.dict("sys.modules", {
            "schemas.pipeline": mock_pipeline,
            "services.prompts": mock_prompts,
        }):
            result = get_writer_system_prompt()
        assert result == "default-prompt"
        mock_prompts.get_system_prompt.assert_called_once_with("writer", "yaml-prompt")

    def test_returns_variant_when_experiment_enabled(self):
        mock_pipeline, mock_prompts = _make_pipeline_mock(experiments={
            "enabled": True,
            "prompt_variants": {"writer": {"group_a": "variant-prompt"}},
        })
        mock_prompts.get_system_prompt.return_value = "variant-prompt"
        article = MagicMock(experiment_group="group_a")
        with patch.dict("sys.modules", {
            "schemas.pipeline": mock_pipeline,
            "services.prompts": mock_prompts,
        }):
            result = get_writer_system_prompt(article)
        assert result == "variant-prompt"
        mock_prompts.get_system_prompt.assert_called_once_with("writer", "variant-prompt")

    def test_returns_default_when_experiments_disabled(self):
        mock_pipeline, mock_prompts = _make_pipeline_mock(experiments={
            "enabled": False,
            "prompt_variants": {"writer": {"group_a": "variant-prompt"}},
        })
        mock_prompts.get_system_prompt.return_value = "default-prompt"
        article = MagicMock(experiment_group="group_a")
        with patch.dict("sys.modules", {
            "schemas.pipeline": mock_pipeline,
            "services.prompts": mock_prompts,
        }):
            result = get_writer_system_prompt(article)
        assert result == "default-prompt"
        mock_prompts.get_system_prompt.assert_called_once_with("writer", "yaml-prompt")

    def test_returns_default_when_article_has_no_experiment_group(self):
        mock_pipeline, mock_prompts = _make_pipeline_mock(experiments={
            "enabled": True,
            "prompt_variants": {"writer": {"group_a": "variant-prompt"}},
        })
        mock_prompts.get_system_prompt.return_value = "default-prompt"
        article = MagicMock(experiment_group=None)
        with patch.dict("sys.modules", {
            "schemas.pipeline": mock_pipeline,
            "services.prompts": mock_prompts,
        }):
            result = get_writer_system_prompt(article)
        assert result == "default-prompt"
        mock_prompts.get_system_prompt.assert_called_once_with("writer", "yaml-prompt")

    def test_returns_variant_when_experiment_group_not_in_variants(self):
        mock_pipeline, mock_prompts = _make_pipeline_mock(experiments={
            "enabled": True,
            "prompt_variants": {"writer": {"group_a": "variant-prompt"}},
        })
        mock_prompts.get_system_prompt.return_value = "default-prompt"
        article = MagicMock(experiment_group="group_b")
        with patch.dict("sys.modules", {
            "schemas.pipeline": mock_pipeline,
            "services.prompts": mock_prompts,
        }):
            result = get_writer_system_prompt(article)
        assert result == "default-prompt"
        mock_prompts.get_system_prompt.assert_called_once_with("writer", "yaml-prompt")

    def test_returns_default_when_article_lacks_experiment_group_attr(self):
        mock_pipeline, mock_prompts = _make_pipeline_mock()
        mock_prompts.get_system_prompt.return_value = "default-prompt"
        with patch.dict("sys.modules", {
            "schemas.pipeline": mock_pipeline,
            "services.prompts": mock_prompts,
        }):
            result = get_writer_system_prompt(article="not-an-article")
        assert result == "default-prompt"


class TestBuildWriterPrompt:
    """Tests for build_writer_prompt."""

    def test_returns_xml_wrapped_input_data(self):
        result = build_writer_prompt(
            title="Test Title",
            topics=["ai", "llm"],
            research_brief="Some brief",
        )
        assert result.startswith("<input_data>")
        assert "</input_data>" in result
        assert "<topics>ai, llm</topics>" in result
        assert "<original_title>Test Title</original_title>" in result
        assert "<research_brief>" in result
        assert "</research_brief>" in result

    def test_includes_trend_memory_when_provided(self):
        result = build_writer_prompt(
            title="T",
            topics=["ai"],
            research_brief="brief",
            trend_memory="trend info here",
        )
        assert "<editor_memory>" in result
        assert "trend info here" in result
        assert "</editor_memory>" in result

    def test_omits_trend_memory_when_empty(self):
        result = build_writer_prompt(
            title="T",
            topics=["ai"],
            research_brief="brief",
            trend_memory="",
        )
        assert "<editor_memory>" not in result

    def test_escapes_xml_special_chars(self):
        result = build_writer_prompt(
            title="A <B> & C",
            topics=["t"],
            research_brief="x < y & z > w",
        )
        assert "A &lt;B&gt; &amp; C" in result
        assert "x &lt; y &amp; z &gt; w" in result

    def test_includes_correct_max_key_points(self):
        result = build_writer_prompt(
            title="T",
            topics=["ai"],
            research_brief="brief",
            max_key_points=10,
        )
        assert "Limit key_points to 10 items" in result

    def test_defaults_to_five_key_points(self):
        result = build_writer_prompt(
            title="T",
            topics=["ai"],
            research_brief="brief",
        )
        assert "Limit key_points to 5 items" in result

    def test_includes_instruction_text(self):
        result = build_writer_prompt(
            title="T",
            topics=["ai"],
            research_brief="brief",
        )
        assert "why_it_matters" in result
        assert "what_to_watch" in result
        assert "citations" in result


class TestGetResearcherSystemPrompt:
    """Tests for get_researcher_system_prompt."""

    def test_returns_system_prompt(self):
        mock_pipeline, mock_prompts = _make_pipeline_mock()
        mock_prompts.get_system_prompt.return_value = "researcher-prompt"
        with patch.dict("sys.modules", {
            "schemas.pipeline": mock_pipeline,
            "services.prompts": mock_prompts,
        }):
            result = get_researcher_system_prompt()
        assert result == "researcher-prompt"
        mock_prompts.get_system_prompt.assert_called_once_with("researcher", "yaml-prompt")


class TestBuildResearchPrompt:
    """Tests for build_research_prompt."""

    def test_returns_source_article_xml(self):
        result = build_research_prompt(
            title="Art Title",
            extracted_text="body text",
            original_url="https://example.com",
            author="Jane",
            topics=["ai", "llm"],
            web_results=[],
            related_articles=[],
        )
        assert "<source_article>" in result
        assert "</source_article>" in result
        assert "<title>Art Title</title>" in result
        assert "<url>https://example.com</url>" in result
        assert "<author>Jane</author>" in result
        assert "<topics>ai, llm</topics>" in result
        assert "<body>" in result
        assert "</body>" in result

    def test_includes_topic_notes_when_provided(self):
        result = build_research_prompt(
            title="T",
            extracted_text="body",
            original_url="https://ex.com",
            author="A",
            topics=["t"],
            web_results=[],
            related_articles=[],
            topic_notes="notes here",
        )
        assert "<topic_notes>" in result
        assert "notes here" in result
        assert "</topic_notes>" in result

    def test_omits_topic_notes_when_empty(self):
        result = build_research_prompt(
            title="T",
            extracted_text="body",
            original_url="https://ex.com",
            author="A",
            topics=["t"],
            web_results=[],
            related_articles=[],
            topic_notes="",
        )
        assert "<topic_notes>" not in result

    def test_includes_trend_memory_when_provided(self):
        result = build_research_prompt(
            title="T",
            extracted_text="body",
            original_url="https://ex.com",
            author="A",
            topics=["t"],
            web_results=[],
            related_articles=[],
            trend_memory="trend data",
        )
        assert "<editor_memory>" in result
        assert "trend data" in result
        assert "</editor_memory>" in result

    def test_omits_trend_memory_when_empty(self):
        result = build_research_prompt(
            title="T",
            extracted_text="body",
            original_url="https://ex.com",
            author="A",
            topics=["t"],
            web_results=[],
            related_articles=[],
            trend_memory="",
        )
        assert "<editor_memory>" not in result

    def test_includes_web_synthesis_when_provided(self):
        result = build_research_prompt(
            title="T",
            extracted_text="body",
            original_url="https://ex.com",
            author="A",
            topics=["t"],
            web_results=[],
            related_articles=[],
            web_synthesis="synthesis text",
        )
        assert "<external_sources_synthesis>" in result
        assert "synthesis text" in result
        assert "</external_sources_synthesis>" in result

    def test_omits_web_synthesis_when_empty(self):
        result = build_research_prompt(
            title="T",
            extracted_text="body",
            original_url="https://ex.com",
            author="A",
            topics=["t"],
            web_results=[],
            related_articles=[],
            web_synthesis="",
        )
        assert "<external_sources_synthesis>" not in result

    def test_includes_external_sources_when_web_results_provided(self):
        web_results = [
            {"title": "Source 1", "url": "https://a.com", "snippet": "snippet one"},
            {"title": "Source 2", "url": "https://b.com", "snippet": "snippet two"},
        ]
        result = build_research_prompt(
            title="T",
            extracted_text="body",
            original_url="https://ex.com",
            author="A",
            topics=["t"],
            web_results=web_results,
            related_articles=[],
        )
        assert "<external_sources>" in result
        assert "</external_sources>" in result
        assert "<source index='1'>" in result
        assert "<source index='2'>" in result
        assert "<title>Source 1</title>" in result
        assert "<url>https://a.com</url>" in result
        assert "<snippet>snippet one</snippet>" in result

    def test_omits_external_sources_when_no_web_results(self):
        result = build_research_prompt(
            title="T",
            extracted_text="body",
            original_url="https://ex.com",
            author="A",
            topics=["t"],
            web_results=[],
            related_articles=[],
        )
        assert "<external_sources>" not in result

    def test_includes_related_articles_when_provided(self):
        related = [
            {"title": "Related 1", "category": "AI", "snippet": "rel snippet"},
        ]
        result = build_research_prompt(
            title="T",
            extracted_text="body",
            original_url="https://ex.com",
            author="A",
            topics=["t"],
            web_results=[],
            related_articles=related,
        )
        assert "<related_articles>" in result
        assert "</related_articles>" in result
        assert "<article index='1'>" in result
        assert "Related 1" in result
        assert "AI" in result

    def test_omits_related_articles_when_empty(self):
        result = build_research_prompt(
            title="T",
            extracted_text="body",
            original_url="https://ex.com",
            author="A",
            topics=["t"],
            web_results=[],
            related_articles=[],
        )
        assert "<related_articles>" not in result

    def test_truncates_extracted_text_to_max_text_length(self):
        long_text = "x" * 10000
        result = build_research_prompt(
            title="T",
            extracted_text=long_text,
            original_url="https://ex.com",
            author="A",
            topics=["t"],
            web_results=[],
            related_articles=[],
            max_text_length=500,
        )
        assert "x" * 500 in result
        assert "x" * 501 not in result

    def test_does_not_truncate_when_under_limit(self):
        short_text = "short text"
        result = build_research_prompt(
            title="T",
            extracted_text=short_text,
            original_url="https://ex.com",
            author="A",
            topics=["t"],
            web_results=[],
            related_articles=[],
            max_text_length=6000,
        )
        assert "short text" in result

    def test_escapes_xml_special_chars_in_all_fields(self):
        result = build_research_prompt(
            title="A <B> & C",
            extracted_text="body <tag> & stuff",
            original_url="https://ex.com?a=1&b=2",
            author="Smith & Jones",
            topics=["<topic>"],
            web_results=[{"title": "T<x>", "url": "https://a.com", "snippet": "s<y>&z"}],
            related_articles=[{"title": "R<a>", "category": "C&d", "snippet": "s<b>"}],
        )
        assert "A &lt;B&gt; &amp; C" in result
        assert "body &lt;tag&gt; &amp; stuff" in result
        assert "Smith &amp; Jones" in result
        assert "&lt;topic&gt;" in result
        assert "T&lt;x&gt;" in result
        assert "s&lt;y&gt;&amp;z" in result
        assert "R&lt;a&gt;" in result
        assert "C&amp;d" in result
        assert "s&lt;b&gt;" in result

    def test_web_snippet_truncated_to_300_chars(self):
        long_snippet = "s" * 500
        web_results = [{"title": "T", "url": "https://a.com", "snippet": long_snippet}]
        result = build_research_prompt(
            title="T",
            extracted_text="body",
            original_url="https://ex.com",
            author="A",
            topics=["t"],
            web_results=web_results,
            related_articles=[],
        )
        assert "s" * 300 in result
        assert "s" * 301 not in result

    def test_related_article_snippet_truncated_to_200_chars(self):
        long_snippet = "r" * 400
        related = [{"title": "R", "category": "C", "snippet": long_snippet}]
        result = build_research_prompt(
            title="T",
            extracted_text="body",
            original_url="https://ex.com",
            author="A",
            topics=["t"],
            web_results=[],
            related_articles=related,
        )
        assert "r" * 200 in result
        assert "r" * 201 not in result

    def test_includes_final_instructions(self):
        result = build_research_prompt(
            title="T",
            extracted_text="body",
            original_url="https://ex.com",
            author="A",
            topics=["t"],
            web_results=[],
            related_articles=[],
        )
        assert "Compile a comprehensive research brief" in result
        assert "Attribute all claims" in result

    def test_uses_newline_join(self):
        result = build_research_prompt(
            title="T",
            extracted_text="body",
            original_url="https://ex.com",
            author="A",
            topics=["t"],
            web_results=[],
            related_articles=[],
        )
        lines = result.split("\n")
        assert len(lines) > 1
