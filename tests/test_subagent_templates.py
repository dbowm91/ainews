"""Tests for subagent templates and prompt handling."""




class TestSubagentTemplates:
    """Test subagent task templates."""

    def test_research_synthesis_template(self):
        from services.subagent import _SUBAGENT_TASK_TEMPLATES

        template = _SUBAGENT_TASK_TEMPLATES["research_synthesis"]
        assert "source_article" in template
        assert "web_results" in template
        assert "Synthesize" in template

    def test_edit_contextualization_template(self):
        from services.subagent import _SUBAGENT_TASK_TEMPLATES

        template = _SUBAGENT_TASK_TEMPLATES["edit_contextualization"]
        assert "draft_article" in template
        assert "research_brief" in template
        assert "topic_notes" in template

    def test_get_task_template_falls_back_to_hardcoded(self, app):
        """When no task_template is set, falls back to hardcoded templates."""
        with app.app_context():
            from schemas.pipeline import SubagentStageConfig
            from services.subagent import _get_task_template

            config = SubagentStageConfig(enabled=True)
            template = _get_task_template("research_synthesis", config)
            assert "source_article" in template
            assert "web_results" in template

    def test_get_task_template_loads_from_file(self, app, tmp_path):
        """When task_template is set and file exists, loads from file."""
        with app.app_context():
            from schemas.pipeline import BASE_DIR, SubagentStageConfig
            from services.subagent import _get_task_template

            prompt_file = BASE_DIR / "prompts" / "test_template.txt"
            prompt_file.parent.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text("CUSTOM TEMPLATE CONTENT")

            try:
                config = SubagentStageConfig(
                    enabled=True,
                    task_template="prompts/test_template.txt",
                )
                template = _get_task_template("research_synthesis", config)
                assert template == "CUSTOM TEMPLATE CONTENT"
            finally:
                prompt_file.unlink(missing_ok=True)

    def test_get_task_template_falls_back_when_file_missing(self, app):
        """When task_template is set but file doesn't exist, falls back to hardcoded."""
        with app.app_context():
            from schemas.pipeline import SubagentStageConfig
            from services.subagent import _get_task_template

            config = SubagentStageConfig(
                enabled=True,
                task_template="nonexistent/prompt.txt",
            )
            template = _get_task_template("research_synthesis", config)
            assert "source_article" in template


class TestEscapePromptData:
    """Tests for _escape_prompt_data function."""

    def test_escapes_simple_strings(self):
        from services.subagent import _escape_prompt_data

        data = {"title": "<script>alert('xss')</script>", "body": "normal text"}
        result = _escape_prompt_data(data)
        assert result["title"] == "&lt;script&gt;alert('xss')&lt;/script&gt;"
        assert result["body"] == "normal text"

    def test_escapes_nested_dicts(self):
        from services.subagent import _escape_prompt_data

        data = {
            "outer": {
                "inner": "<img src=x onerror=alert(1)>",
                "safe": "normal",
            }
        }
        result = _escape_prompt_data(data)
        assert result["outer"]["inner"] == "&lt;img src=x onerror=alert(1)&gt;"
        assert result["outer"]["safe"] == "normal"

    def test_escapes_lists(self):
        from services.subagent import _escape_prompt_data

        data = {"items": ["<b>bold</b>", "normal", "<i>italic</i>"]}
        result = _escape_prompt_data(data)
        assert result["items"][0] == "&lt;b&gt;bold&lt;/b&gt;"
        assert result["items"][1] == "normal"
        assert result["items"][2] == "&lt;i&gt;italic&lt;/i&gt;"

    def test_preserves_non_string_values(self):
        from services.subagent import _escape_prompt_data

        data = {"count": 42, "enabled": True, "ratio": 3.14, "none_val": None}
        result = _escape_prompt_data(data)
        assert result["count"] == 42
        assert result["enabled"] is True
        assert result["ratio"] == 3.14
        assert result["none_val"] is None

    def test_handles_empty_strings(self):
        from services.subagent import _escape_prompt_data

        data = {"empty": "", "title": "no special chars"}
        result = _escape_prompt_data(data)
        assert result["empty"] == ""
        assert result["title"] == "no special chars"

    def test_escapes_xml_special_chars(self):
        from services.subagent import _escape_prompt_data

        data = {"xml": "<tag attr=\"value\">content & more</tag>"}
        result = _escape_prompt_data(data)
        assert "&lt;tag" in result["xml"]
        assert "attr=\"value\"" in result["xml"]
        assert "&amp; more" in result["xml"]


class TestLoadPromptTemplate:
    """Test _load_prompt_template function."""

    def test_load_existing_file(self, tmp_path):
        from services.subagent import _load_prompt_template, BASE_DIR
        import os

        test_file = BASE_DIR / "test_prompt.txt"
        test_file.write_text("test content")
        try:
            result = _load_prompt_template("test_prompt.txt")
            assert result == "test content"
        finally:
            os.remove(test_file)

    def test_load_nonexistent_file(self):
        from services.subagent import _load_prompt_template

        result = _load_prompt_template("nonexistent/file.txt")
        assert result is None