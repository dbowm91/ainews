"""Tests for subagent tool registry and built-in tools."""

from unittest.mock import MagicMock, patch

from services.search.evidence import SearchOutcome, SearchStatus


class TestToolRegistry:
    """Test tool registry functions."""

    def test_register_tool(self):
        from services.subagent import _TOOL_REGISTRY, register_tool, ToolDefinition

        _TOOL_REGISTRY.clear()
        tool = ToolDefinition(name="test_tool", description="test", parameters={}, fn=lambda: None)
        register_tool(tool)
        assert "test_tool" in _TOOL_REGISTRY
        assert _TOOL_REGISTRY["test_tool"] == tool

    def test_get_registered_tools(self):
        from services.subagent import _TOOL_REGISTRY, get_registered_tools, register_tool, ToolDefinition

        _TOOL_REGISTRY.clear()
        tool1 = ToolDefinition(name="t1", description="t1", parameters={}, fn=lambda: None)
        tool2 = ToolDefinition(name="t2", description="t2", parameters={}, fn=lambda: None)
        register_tool(tool1)
        register_tool(tool2)
        tools = get_registered_tools()
        assert len(tools) == 2
        assert any(t.name == "t1" for t in tools)
        assert any(t.name == "t2" for t in tools)

    def test_initialize_tool_registry_no_filter(self, app):
        with app.app_context():
            from services.subagent import initialize_tool_registry, _TOOL_REGISTRY

            _TOOL_REGISTRY.clear()
            tools = initialize_tool_registry()
            assert len(tools) > 0
            tool_names = [t.name for t in tools]
            assert "get_topic_note" in tool_names
            assert "web_search" in tool_names

    def test_initialize_tool_registry_with_tool_names(self, app):
        with app.app_context():
            from services.subagent import initialize_tool_registry, _TOOL_REGISTRY

            _TOOL_REGISTRY.clear()
            tools = initialize_tool_registry(tool_names=["web_search"])
            assert len(tools) == 1
            assert tools[0].name == "web_search"

    def test_initialize_tool_registry_with_selector(self, app):
        with app.app_context():
            from services.subagent import initialize_tool_registry, _TOOL_REGISTRY

            class MockSelector:
                def select_tools(self, all_tools, context):
                    return [t for t in all_tools if t.name == "get_topic_note"]

            _TOOL_REGISTRY.clear()
            selector = MockSelector()
            tools = initialize_tool_registry(selector=selector)
            assert len(tools) == 1
            assert tools[0].name == "get_topic_note"

    def test_initialize_tool_registry_with_context(self, app):
        with app.app_context():
            from services.subagent import initialize_tool_registry, _TOOL_REGISTRY

            class MockSelector:
                def select_tools(self, all_tools, context):
                    assert context == {"key": "value"}
                    return all_tools

            _TOOL_REGISTRY.clear()
            selector = MockSelector()
            tools = initialize_tool_registry(selector=selector, context={"key": "value"})
            assert len(tools) > 0


class TestBuiltInTools:
    """Test built-in tool functions."""

    def test_get_topic_note_success(self, app):
        with app.app_context():
            from services.subagent import initialize_tool_registry, _TOOL_REGISTRY

            _TOOL_REGISTRY.clear()
            tools = initialize_tool_registry(tool_names=["get_topic_note"])
            assert len(tools) == 1
            tool = tools[0]
            assert tool.name == "get_topic_note"

            with patch("services.context_service.get_topic_note") as mock_get_note:
                mock_note = MagicMock()
                mock_note.note = "test note content"
                mock_get_note.return_value = mock_note

                with patch("services.cache.get_response_cache") as mock_cache:
                    mock_cache_instance = MagicMock()
                    mock_cache_instance.get_or_set.return_value = "test note content"
                    mock_cache.return_value = mock_cache_instance

                    result = tool.fn(topic="test_topic", source="test_source")
                    assert result == "test note content"

    def test_get_topic_note_not_found(self, app):
        with app.app_context():
            from services.subagent import initialize_tool_registry, _TOOL_REGISTRY

            _TOOL_REGISTRY.clear()
            tools = initialize_tool_registry(tool_names=["get_topic_note"])
            tool = tools[0]

            with patch("services.context_service.get_topic_note") as mock_get_note:
                mock_get_note.return_value = None

                with patch("services.cache.get_response_cache") as mock_cache:
                    mock_cache_instance = MagicMock()
                    mock_cache_instance.get_or_set.return_value = "No note found for this topic."
                    mock_cache.return_value = mock_cache_instance

                    result = tool.fn(topic="test_topic")
                    assert result == "No note found for this topic."

    def test_search_web_success(self, app):
        with app.app_context():
            from services.subagent import initialize_tool_registry, _TOOL_REGISTRY

            _TOOL_REGISTRY.clear()
            tools = initialize_tool_registry(tool_names=["web_search"])
            assert len(tools) == 1
            tool = tools[0]
            assert tool.name == "web_search"

            with patch("services.search.search_web_detailed") as mock_search:
                mock_result = MagicMock()
                mock_result.title = "Test Result"
                mock_result.snippet = "Test snippet content"
                mock_result.url = "https://example.org/article?a=1&b=2"
                mock_result.metadata = {"source_id": "source-7"}
                mock_search.return_value = SearchOutcome([mock_result], SearchStatus.OK)

                result = tool.fn(query="test query", max_results=1)
                assert "[source-7] Test Result" in result
                assert "URL: https://example.org/article?a=1&amp;b=2" in result
                assert "Snippet (external_untrusted): Test snippet content" in result

    def test_search_web_no_results(self, app):
        with app.app_context():
            from services.subagent import initialize_tool_registry, _TOOL_REGISTRY

            _TOOL_REGISTRY.clear()
            tools = initialize_tool_registry(tool_names=["web_search"])
            tool = tools[0]

            with patch("services.search.search_web_detailed") as mock_search:
                mock_search.return_value = SearchOutcome([], SearchStatus.EMPTY)
                result = tool.fn(query="test query")
                assert result == "No search results found."

    def test_search_web_error(self, app):
        with app.app_context():
            from services.subagent import initialize_tool_registry, _TOOL_REGISTRY

            _TOOL_REGISTRY.clear()
            tools = initialize_tool_registry(tool_names=["web_search"])
            tool = tools[0]

            with patch("services.search.search_web_detailed") as mock_search:
                mock_search.side_effect = ConnectionError("connection failed")
                result = tool.fn(query="test query")
                assert "Error performing web search" in result

    def test_get_topic_note_sql_error(self, app):
        with app.app_context():
            from sqlalchemy.exc import SQLAlchemyError
            from services.subagent import initialize_tool_registry, _TOOL_REGISTRY

            _TOOL_REGISTRY.clear()
            tools = initialize_tool_registry(tool_names=["get_topic_note"])
            tool = tools[0]

            with patch("services.context_service.get_topic_note") as mock_get_note:
                mock_get_note.side_effect = SQLAlchemyError("db error")

                with patch("services.cache.get_response_cache") as mock_cache:
                    mock_cache_instance = MagicMock()
                    mock_cache_instance.get_or_set.return_value = "Error retrieving topic note: SQLAlchemyError"
                    mock_cache.return_value = mock_cache_instance

                    result = tool.fn(topic="test_topic")
                    assert "Error retrieving topic note" in result

    def test_get_topic_note_unexpected_error(self, app):
        with app.app_context():
            from services.subagent import initialize_tool_registry, _TOOL_REGISTRY

            _TOOL_REGISTRY.clear()
            tools = initialize_tool_registry(tool_names=["get_topic_note"])
            tool = tools[0]

            with patch("services.context_service.get_topic_note") as mock_get_note:
                mock_get_note.side_effect = Exception("unexpected")

                with patch("services.cache.get_response_cache") as mock_cache:
                    mock_cache_instance = MagicMock()
                    mock_cache_instance.get_or_set.return_value = "Error retrieving topic note: Exception"
                    mock_cache.return_value = mock_cache_instance

                    result = tool.fn(topic="test_topic")
                    assert "Error retrieving topic note" in result

    def test_search_web_timeout_error(self, app):
        with app.app_context():
            from services.subagent import initialize_tool_registry, _TOOL_REGISTRY

            _TOOL_REGISTRY.clear()
            tools = initialize_tool_registry(tool_names=["web_search"])
            tool = tools[0]

            with patch("services.search.search_web_detailed") as mock_search:
                mock_search.side_effect = TimeoutError("timeout")
                result = tool.fn(query="test query")
                assert "Error performing web search" in result

    def test_search_web_value_error(self, app):
        with app.app_context():
            from services.subagent import initialize_tool_registry, _TOOL_REGISTRY

            _TOOL_REGISTRY.clear()
            tools = initialize_tool_registry(tool_names=["web_search"])
            tool = tools[0]

            with patch("services.search.search_web_detailed") as mock_search:
                mock_search.side_effect = ValueError("invalid query")
                result = tool.fn(query="test query")
                assert "Error performing web search" in result


class TestGetAllToolsCached:
    """Test _get_all_tools_cached function."""

    def test_returns_tuple_of_tools(self, app):
        with app.app_context():
            from services.subagent import _get_all_tools_cached

            tools = _get_all_tools_cached()
            assert isinstance(tools, tuple)
            assert len(tools) > 0

    def test_returns_same_object_on_multiple_calls(self, app):
        with app.app_context():
            from services.subagent import _get_all_tools_cached

            tools1 = _get_all_tools_cached()
            tools2 = _get_all_tools_cached()
            assert tools1 is tools2


class TestBuiltInToolsExtended:
    """Test additional built-in tools that were previously untested."""

    def test_get_topic_notes_for_topics_success(self, app):
        with app.app_context():
            from services.subagent import _build_context_tools
            tools = _build_context_tools()
            tool = next((t for t in tools if t.name == "context_notes"), None)
            assert tool is not None

            with patch("services.context_service.get_topic_notes_for_topics") as mock_get:
                mock_get.return_value = {"AI": ["note1", "note2"], "ML": ["note3"]}
                result = tool.fn(topics=["AI", "ML"])
                assert "Topic: AI" in result
                assert "note1" in result
                assert "Topic: ML" in result

    def test_get_topic_notes_for_topics_empty(self, app):
        with app.app_context():
            from services.subagent import _build_context_tools
            tools = _build_context_tools()
            tool = next((t for t in tools if t.name == "context_notes"), None)

            with patch("services.context_service.get_topic_notes_for_topics") as mock_get:
                mock_get.return_value = {}
                result = tool.fn(topics=["Nonexistent"])
                assert "No topic notes found" in result

    def test_get_related_articles_success(self, app):
        with app.app_context():
            from services.subagent import _build_context_tools
            tools = _build_context_tools()
            tool = next((t for t in tools if t.name == "related_articles"), None)
            assert tool is not None

            with patch("services.context_service.get_related_articles_for_edit") as mock_get:
                mock_get.return_value = [
                    {"title": "Article 1", "summary_snippet": "Summary 1"},
                    {"title": "Article 2", "summary_snippet": "Summary 2"},
                ]
                result = tool.fn(topics=["AI"], exclude_id=5, limit=2)
                assert "Article 1" in result
                assert "Summary 1" in result

    def test_get_related_articles_empty(self, app):
        with app.app_context():
            from services.subagent import _build_context_tools
            tools = _build_context_tools()
            tool = next((t for t in tools if t.name == "related_articles"), None)

            with patch("services.context_service.get_related_articles_for_edit") as mock_get:
                mock_get.return_value = []
                result = tool.fn(topics=["AI"], exclude_id=5)
                assert "No related articles found" in result

    def test_get_trend_memory_success(self, app):
        with app.app_context():
            from services.subagent import _build_context_tools
            tools = _build_context_tools()
            tool = next((t for t in tools if t.name == "get_trend_memory"), None)
            assert tool is not None

            with patch("services.trend_memory.get_memory_for_topics") as mock_get:
                mock_entry = MagicMock()
                mock_entry.topic = "AI"
                mock_entry.importance = 2
                mock_entry.signal = "AI is hot"
                mock_get.return_value = [mock_entry]
                result = tool.fn(topics=["AI"], min_importance=1)
                assert "AI is hot" in result

    def test_get_trend_memory_empty(self, app):
        with app.app_context():
            from services.subagent import _build_context_tools
            tools = _build_context_tools()
            tool = next((t for t in tools if t.name == "get_trend_memory"), None)

            with patch("services.trend_memory.get_memory_for_topics") as mock_get:
                mock_get.return_value = []
                result = tool.fn(topics=["Nonexistent"])
                assert "No trend memory found" in result

    def test_get_article_by_id_success(self, app):
        with app.app_context():
            from services.subagent import _build_context_tools
            tools = _build_context_tools()
            tool = next((t for t in tools if t.name == "get_article_by_id"), None)
            assert tool is not None

            mock_article = MagicMock()
            mock_article.id = 123
            mock_article.title = "Test Article"
            mock_article.pipeline_status = "done"
            mock_article.impact_score = 50
            mock_article.created_at.isoformat.return_value = "2024-01-01T00:00:00"

            with patch("extensions.db") as mock_db:
                mock_db.session.get.return_value = mock_article
                result = tool.fn(article_id=123)
                import json
                data = json.loads(result)
                assert data["id"] == 123
                assert data["title"] == "Test Article"

    def test_get_article_by_id_not_found(self, app):
        with app.app_context():
            from services.subagent import _build_context_tools
            tools = _build_context_tools()
            tool = next((t for t in tools if t.name == "get_article_by_id"), None)

            with patch("extensions.db") as mock_db:
                mock_db.session.get.return_value = None
                result = tool.fn(article_id=999)
                assert "not found" in result

    def test_search_articles_success(self, app):
        with app.app_context():
            from services.subagent import _build_context_tools
            tools = _build_context_tools()
            tool = next((t for t in tools if t.name == "search_articles"), None)
            assert tool is not None

            mock_article = MagicMock()
            mock_article.id = 1
            mock_article.original_title = "AI Breakthrough"

            with patch("models.Article") as mock_article_cls:
                mock_article_cls.query.filter.return_value.limit.return_value.all.return_value = [mock_article]
                result = tool.fn(query="AI", limit=5)
                import json
                data = json.loads(result)
                assert len(data) == 1
                assert data[0]["title"] == "AI Breakthrough"

    def test_search_articles_empty(self, app):
        with app.app_context():
            from services.subagent import _build_context_tools
            tools = _build_context_tools()
            tool = next((t for t in tools if t.name == "search_articles"), None)

            with patch("models.Article") as mock_article_cls:
                mock_article_cls.query.filter.return_value.limit.return_value.all.return_value = []
                result = tool.fn(query="Nonexistent")
                assert "error" in result.lower() or "[]" in result

    def test_get_source_health_success(self, app):
        with app.app_context():
            from services.subagent import _build_context_tools
            tools = _build_context_tools()
            tool = next((t for t in tools if t.name == "get_source_health"), None)
            assert tool is not None

            mock_source = MagicMock()
            mock_source.id = 1
            mock_source.name = "Test Source"
            mock_source.disabled_at = None
            mock_source.consecutive_failures = 0

            with patch("extensions.db") as mock_db:
                mock_db.session.query.return_value.all.return_value = [mock_source]
                result = tool.fn()
                import json
                data = json.loads(result)
                assert len(data) == 1
                assert data[0]["name"] == "Test Source"

    def test_get_search_provider_success(self, app):
        with app.app_context():
            from services.subagent import _build_search_tools
            tools = _build_search_tools()
            tool = next((t for t in tools if t.name == "get_search_provider"), None)
            assert tool is not None

            with patch("services.search.get_search_provider") as mock_get:
                mock_prov = MagicMock()
                mock_prov.provider_id = "searxng"
                mock_get.return_value = mock_prov
                result = tool.fn()
                assert "searxng" in result