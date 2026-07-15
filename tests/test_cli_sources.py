from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from ainews_cli.main import app
from ainews_cli.sources.models import SourceDefinition, SourceTestResult
from ainews_cli.sources.opml import (
    export_opml,
    import_opml,
    _normalize_url,
    _strip_credentials,
    _generate_source_id,
)

# Ensure source adapters are registered (decorators run on import)
import ainews_cli.sources.adapters  # noqa: F401

runner = CliRunner()


@pytest.fixture(autouse=True)
def _fresh_ctx(tmp_path: Path) -> None:
    """Ensure each test gets a fresh CLIContext pointing at tmp_path."""
    from ainews_cli.main import _ctx as global_ctx

    global_ctx.config = None
    global_ctx.paths = None
    global_ctx._explicit_paths = {
        "env_file": tmp_path / ".env",
        "providers_file": tmp_path / "providers.yaml",
        "pipeline_file": tmp_path / "pipeline.yaml",
        "sources_file": tmp_path / "sources.yaml",
        "topics_file": tmp_path / "topics.yaml",
        "config_dir": tmp_path,
        "data_dir": tmp_path,
        "state_dir": tmp_path,
        "backup_dir": tmp_path,
    }
    yield
    global_ctx.config = None
    global_ctx.paths = None
    global_ctx._explicit_paths = {}


def _setup_base_files(tmp_path: Path) -> None:
    """Write minimal config files for CLI context."""
    (tmp_path / ".env").write_text("SECRET_KEY=test-secret\n")
    (tmp_path / "providers.yaml").write_text(
        yaml.dump(
            {
                "default_provider": "ollama-local",
                "providers": {
                    "ollama-local": {
                        "type": "ollama",
                        "enabled": True,
                        "config": {"base_url": "http://localhost:11434"},
                    }
                },
            }
        )
    )
    (tmp_path / "pipeline.yaml").write_text(yaml.dump({"pipeline": {}}))
    # Sources file must be a top-level list (loader expects list, not dict wrapper)
    (tmp_path / "sources.yaml").write_text("[]\n")
    (tmp_path / "topics.yaml").write_text("topics: {}\n")


def _write_sources(tmp_path: Path, sources_list: list[dict[str, Any]]) -> None:
    """Write a sources list to the sources.yaml file."""
    (tmp_path / "sources.yaml").write_text(yaml.dump(sources_list))


def _write_topics(tmp_path: Path, topics_dict: dict[str, Any]) -> None:
    """Write a topics dict to the topics.yaml file (wrapped in 'topics:' key)."""
    (tmp_path / "topics.yaml").write_text(yaml.dump({"topics": topics_dict}))


# ---------------------------------------------------------------------------
# Sources List
# ---------------------------------------------------------------------------
class TestSourcesList:
    def test_list_empty(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        result = runner.invoke(app, ["sources-list"], env={"HOME": str(tmp_path)})
        assert result.exit_code == 0
        assert "No sources" in result.output

    def test_list_with_sources(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        _write_sources(tmp_path, [
            {
                "id": "test_rss",
                "name": "Test RSS",
                "type": "rss",
                "enabled": True,
                "schedule_minutes": 30,
                "config": {"feed_url": "https://example.com/feed.xml"},
            }
        ])

        result = runner.invoke(app, ["sources-list"], env={"HOME": str(tmp_path)})
        assert result.exit_code == 0
        assert "test_rss" in result.output

    def test_list_json(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        _write_sources(tmp_path, [
            {
                "id": "test_rss",
                "name": "Test RSS",
                "type": "rss",
                "enabled": True,
                "schedule_minutes": 30,
                "config": {"feed_url": "https://example.com/feed.xml"},
            }
        ])

        result = runner.invoke(app, ["--json", "sources-list"], env={"HOME": str(tmp_path)})
        assert result.exit_code == 0
        assert "test_rss" in result.output


# ---------------------------------------------------------------------------
# Sources Show
# ---------------------------------------------------------------------------
class TestSourcesShow:
    def test_show_not_found(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        result = runner.invoke(app, ["sources-show", "nonexistent"], env={"HOME": str(tmp_path)})
        assert result.exit_code != 0

    def test_show_existing(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        _write_sources(tmp_path, [
            {
                "id": "test_rss",
                "name": "Test RSS",
                "type": "rss",
                "enabled": True,
                "schedule_minutes": 30,
                "config": {"feed_url": "https://example.com/feed.xml"},
            }
        ])

        result = runner.invoke(app, ["sources-show", "test_rss"], env={"HOME": str(tmp_path)})
        assert result.exit_code == 0
        assert "test_rss" in result.output


# ---------------------------------------------------------------------------
# Sources Enable / Disable
# ---------------------------------------------------------------------------
class TestSourcesEnableDisable:
    def test_enable_already_enabled(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        _write_sources(tmp_path, [
            {
                "id": "test_rss",
                "name": "Test RSS",
                "type": "rss",
                "enabled": True,
                "schedule_minutes": 30,
                "config": {"feed_url": "https://example.com/feed.xml"},
            }
        ])

        result = runner.invoke(app, ["sources-enable", "test_rss"], env={"HOME": str(tmp_path)})
        assert result.exit_code == 0
        assert "already enabled" in result.output

    def test_enable_disabled(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        _write_sources(tmp_path, [
            {
                "id": "test_rss",
                "name": "Test RSS",
                "type": "rss",
                "enabled": False,
                "schedule_minutes": 30,
                "config": {"feed_url": "https://example.com/feed.xml"},
            }
        ])

        result = runner.invoke(app, ["sources-enable", "test_rss"], env={"HOME": str(tmp_path)})
        assert result.exit_code == 0
        assert "enabled" in result.output.lower()

    def test_disable(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        _write_sources(tmp_path, [
            {
                "id": "test_rss",
                "name": "Test RSS",
                "type": "rss",
                "enabled": True,
                "schedule_minutes": 30,
                "config": {"feed_url": "https://example.com/feed.xml"},
            }
        ])

        result = runner.invoke(app, ["sources-disable", "test_rss"], env={"HOME": str(tmp_path)})
        assert result.exit_code == 0
        assert "disabled" in result.output.lower()

    def test_disable_already_disabled(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        _write_sources(tmp_path, [
            {
                "id": "test_rss",
                "name": "Test RSS",
                "type": "rss",
                "enabled": False,
                "schedule_minutes": 30,
                "config": {"feed_url": "https://example.com/feed.xml"},
            }
        ])

        result = runner.invoke(app, ["sources-disable", "test_rss"], env={"HOME": str(tmp_path)})
        assert result.exit_code == 0
        assert "already disabled" in result.output

    def test_enable_not_found(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        result = runner.invoke(app, ["sources-enable", "nonexistent"], env={"HOME": str(tmp_path)})
        assert result.exit_code != 0

    def test_disable_not_found(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        result = runner.invoke(app, ["sources-disable", "nonexistent"], env={"HOME": str(tmp_path)})
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Sources Remove
# ---------------------------------------------------------------------------
class TestSourcesRemove:
    def test_remove_not_found(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        result = runner.invoke(app, ["sources-remove", "nonexistent"], env={"HOME": str(tmp_path)})
        assert result.exit_code != 0

    def test_remove_with_force(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        _write_sources(tmp_path, [
            {
                "id": "test_rss",
                "name": "Test RSS",
                "type": "rss",
                "enabled": True,
                "schedule_minutes": 30,
                "config": {"feed_url": "https://example.com/feed.xml"},
            }
        ])

        result = runner.invoke(app, ["sources-remove", "test_rss", "--force"], env={"HOME": str(tmp_path)})
        assert result.exit_code == 0
        assert "removed" in result.output.lower()


# ---------------------------------------------------------------------------
# Sources Update
# ---------------------------------------------------------------------------
class TestSourcesUpdate:
    def test_update_not_found(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        result = runner.invoke(app, ["sources-update", "nonexistent", "--name", "New"], env={"HOME": str(tmp_path)})
        assert result.exit_code != 0

    def test_update_name(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        _write_sources(tmp_path, [
            {
                "id": "test_rss",
                "name": "Test RSS",
                "type": "rss",
                "enabled": True,
                "schedule_minutes": 30,
                "config": {"feed_url": "https://example.com/feed.xml"},
            }
        ])

        result = runner.invoke(
            app, ["sources-update", "test_rss", "--name", "Updated Name"], env={"HOME": str(tmp_path)}
        )
        assert result.exit_code == 0
        assert "updated" in result.output.lower()

    def test_update_schedule(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        _write_sources(tmp_path, [
            {
                "id": "test_rss",
                "name": "Test RSS",
                "type": "rss",
                "enabled": True,
                "schedule_minutes": 30,
                "config": {"feed_url": "https://example.com/feed.xml"},
            }
        ])

        result = runner.invoke(
            app, ["sources-update", "test_rss", "--schedule", "60"], env={"HOME": str(tmp_path)}
        )
        assert result.exit_code == 0
        assert "updated" in result.output.lower()


# ---------------------------------------------------------------------------
# Sources Test
# ---------------------------------------------------------------------------
class TestSourcesTest:
    def test_test_no_sources(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        result = runner.invoke(app, ["sources-test"], env={"HOME": str(tmp_path)})
        assert result.exit_code == 0
        assert "No sources" in result.output

    def test_test_not_found(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        result = runner.invoke(app, ["sources-test", "nonexistent"], env={"HOME": str(tmp_path)})
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Topics List
# ---------------------------------------------------------------------------
class TestTopicsList:
    def test_list_empty(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        result = runner.invoke(app, ["topics-list"], env={"HOME": str(tmp_path)})
        assert result.exit_code == 0
        assert "No topics" in result.output

    def test_list_with_topics(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        _write_topics(tmp_path, {
            "ai": {
                "display_name": "AI",
                "description": "Artificial Intelligence",
                "color": "blue",
            }
        })

        result = runner.invoke(app, ["topics-list"], env={"HOME": str(tmp_path)})
        assert result.exit_code == 0
        assert "ai" in result.output

    def test_list_json(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        _write_topics(tmp_path, {
            "ai": {
                "display_name": "AI",
                "description": "Artificial Intelligence",
                "color": "blue",
            }
        })

        result = runner.invoke(app, ["--json", "topics-list"], env={"HOME": str(tmp_path)})
        assert result.exit_code == 0
        assert "ai" in result.output


# ---------------------------------------------------------------------------
# Topics Show
# ---------------------------------------------------------------------------
class TestTopicsShow:
    def test_show_not_found(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        result = runner.invoke(app, ["topics-show", "nonexistent"], env={"HOME": str(tmp_path)})
        assert result.exit_code != 0

    def test_show_existing(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        _write_topics(tmp_path, {
            "ai": {
                "display_name": "AI",
                "description": "Artificial Intelligence",
                "color": "blue",
            }
        })

        result = runner.invoke(app, ["topics-show", "ai"], env={"HOME": str(tmp_path)})
        assert result.exit_code == 0
        assert "AI" in result.output


# ---------------------------------------------------------------------------
# Topics Remove
# ---------------------------------------------------------------------------
class TestTopicsRemove:
    def test_remove_not_found(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        result = runner.invoke(app, ["topics-remove", "nonexistent"], env={"HOME": str(tmp_path)})
        assert result.exit_code != 0

    def test_remove_with_force(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        _write_topics(tmp_path, {
            "ai": {
                "display_name": "AI",
                "description": "Artificial Intelligence",
                "color": "blue",
            }
        })

        result = runner.invoke(app, ["topics-remove", "ai", "--force"], env={"HOME": str(tmp_path)})
        assert result.exit_code == 0
        assert "removed" in result.output.lower()


# ---------------------------------------------------------------------------
# Topics Update
# ---------------------------------------------------------------------------
class TestTopicsUpdate:
    def test_update_not_found(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        result = runner.invoke(app, ["topics-update", "nonexistent", "--name", "New"], env={"HOME": str(tmp_path)})
        assert result.exit_code != 0

    def test_update_name(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        _write_topics(tmp_path, {
            "ai": {
                "display_name": "AI",
                "description": "Artificial Intelligence",
                "color": "blue",
            }
        })

        result = runner.invoke(
            app, ["topics-update", "ai", "--name", "Machine Learning"], env={"HOME": str(tmp_path)}
        )
        assert result.exit_code == 0
        assert "updated" in result.output.lower()


# ---------------------------------------------------------------------------
# Pipeline Show
# ---------------------------------------------------------------------------
class TestPipelineShow:
    def test_show_empty(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        result = runner.invoke(app, ["pipeline-show"], env={"HOME": str(tmp_path)})
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Pipeline Assign
# ---------------------------------------------------------------------------
class TestPipelineAssign:
    def test_assign_invalid_role(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        result = runner.invoke(app, ["pipeline-assign", "invalid", "ollama-local/qwen3:8b"], env={"HOME": str(tmp_path)})
        assert result.exit_code != 0

    def test_assign_invalid_format(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        result = runner.invoke(app, ["pipeline-assign", "selector", "invalid"], env={"HOME": str(tmp_path)})
        assert result.exit_code != 0

    def test_assign_unknown_provider(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        result = runner.invoke(app, ["pipeline-assign", "selector", "unknown/model"], env={"HOME": str(tmp_path)})
        assert result.exit_code != 0

    def test_assign_valid(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        result = runner.invoke(
            app, ["pipeline-assign", "selector", "ollama-local/qwen3:8b"], env={"HOME": str(tmp_path)}
        )
        assert result.exit_code == 0
        assert "assigned" in result.output.lower() or "ollama-local" in result.output


# ---------------------------------------------------------------------------
# Pipeline Unassign
# ---------------------------------------------------------------------------
class TestPipelineUnassign:
    def test_unassign_invalid_role(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        result = runner.invoke(app, ["pipeline-unassign", "invalid"], env={"HOME": str(tmp_path)})
        assert result.exit_code != 0

    def test_unassign_not_configured(self, tmp_path: Path) -> None:
        _setup_base_files(tmp_path)
        result = runner.invoke(app, ["pipeline-unassign", "selector"], env={"HOME": str(tmp_path)})
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# OPML Import
# ---------------------------------------------------------------------------
class TestOPMLImport:
    def test_import_file_not_found(self) -> None:
        result = import_opml("/nonexistent/file.opml")
        assert result.success is False
        assert any("not found" in e.lower() for e in result.errors)

    def test_import_valid_opml(self, tmp_path: Path) -> None:
        # The OPML parser only processes <outline> elements as direct children,
        # so outlines must be under the root (not wrapped in <body>).
        opml_content = """\
<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>Test Feeds</title></head>
  <outline text="Hacker News" title="Hacker News" xmlUrl="https://hnrss.org/frontpage" />
  <outline text="AI Blog" title="AI Blog" xmlUrl="https://example.com/ai.xml" />
</opml>"""
        opml_file = tmp_path / "test.opml"
        opml_file.write_text(opml_content)

        result = import_opml(str(opml_file), dry_run=True)
        assert result.success is True
        assert len(result.imported) == 2

    def test_import_entity_declaration(self, tmp_path: Path) -> None:
        opml_content = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<opml version="2.0">
  <head><title>Test</title></head>
  <outline text="Test" xmlUrl="&xxe;" />
</opml>"""
        opml_file = tmp_path / "bad.opml"
        opml_file.write_text(opml_content)

        result = import_opml(str(opml_file))
        assert result.success is False
        assert any("entity" in e.lower() or "xxe" in e.lower() for e in result.errors)

    def test_import_too_large(self, tmp_path: Path) -> None:
        opml_file = tmp_path / "big.opml"
        opml_file.write_bytes(b"x" * (1024 * 1024 + 1))

        result = import_opml(str(opml_file))
        assert result.success is False
        assert any("too large" in e.lower() for e in result.errors)

    def test_import_invalid_xml(self, tmp_path: Path) -> None:
        opml_file = tmp_path / "bad.xml"
        opml_file.write_text("not xml at all")

        result = import_opml(str(opml_file))
        assert result.success is False
        assert any("parse" in e.lower() for e in result.errors)


# ---------------------------------------------------------------------------
# OPML Export
# ---------------------------------------------------------------------------
class TestOPMLExport:
    def test_export_empty(self) -> None:
        result = export_opml([])
        assert "<opml" in result
        assert "xmlUrl" not in result

    def test_export_rss_sources(self) -> None:
        sources = [
            {
                "id": "hn",
                "name": "Hacker News",
                "type": "rss",
                "enabled": True,
                "config": {"feed_url": "https://hnrss.org/frontpage"},
            }
        ]
        result = export_opml(sources)
        assert "Hacker News" in result
        assert "hnrss.org" in result

    def test_export_excludes_disabled(self) -> None:
        sources = [
            {
                "id": "hn",
                "name": "Hacker News",
                "type": "rss",
                "enabled": False,
                "config": {"feed_url": "https://hnrss.org/frontpage"},
            }
        ]
        result = export_opml(sources)
        assert "hnrss.org" not in result

    def test_export_excludes_api_type(self) -> None:
        sources = [
            {
                "id": "api_source",
                "name": "API Source",
                "type": "api",
                "enabled": True,
                "config": {"list_url": "https://example.com/api"},
            }
        ]
        result = export_opml(sources)
        assert "example.com" not in result

    def test_export_strips_credentials(self) -> None:
        sources = [
            {
                "id": "hn",
                "name": "Hacker News",
                "type": "rss",
                "enabled": True,
                "config": {"feed_url": "https://user:pass@example.com/feed"},
            }
        ]
        result = export_opml(sources)
        assert "user:pass" not in result
        assert "example.com/feed" in result

    def test_export_deterministic_order(self) -> None:
        sources = [
            {"id": "b", "name": "B", "type": "rss", "enabled": True, "config": {"feed_url": "https://b.com/feed"}},
            {"id": "a", "name": "A", "type": "rss", "enabled": True, "config": {"feed_url": "https://a.com/feed"}},
        ]
        result = export_opml(sources)
        a_pos = result.find("a.com")
        b_pos = result.find("b.com")
        assert a_pos < b_pos

    def test_export_includes_topics(self) -> None:
        sources = [
            {
                "id": "hn",
                "name": "Hacker News",
                "type": "rss",
                "enabled": True,
                "config": {"feed_url": "https://hnrss.org/frontpage"},
                "topics": {"include": ["ai", "tech"]},
            }
        ]
        result = export_opml(sources)
        assert "ai" in result
        assert "tech" in result

    def test_export_empty_feed_url(self) -> None:
        sources = [
            {
                "id": "no_url",
                "name": "No URL",
                "type": "rss",
                "enabled": True,
                "config": {},
            }
        ]
        result = export_opml(sources)
        assert "no_url" not in result


# ---------------------------------------------------------------------------
# OPML Helpers
# ---------------------------------------------------------------------------
class TestOPMLHelpers:
    def test_normalize_url(self) -> None:
        assert _normalize_url("https://example.com/") == "https://example.com"
        assert _normalize_url("http://www.example.com/feed") == "https://example.com/feed"
        assert _normalize_url("HTTPS://EXAMPLE.COM/FEED") == "https://example.com/feed"

    def test_strip_credentials(self) -> None:
        assert _strip_credentials("https://user:pass@example.com/feed") == "https://example.com/feed"
        assert _strip_credentials("https://example.com/feed") == "https://example.com/feed"
        assert _strip_credentials("http://token:x-oauth-basic@api.example.com/feed") == "http://api.example.com/feed"

    def test_generate_source_id(self) -> None:
        assert _generate_source_id("Hacker News", set()) == "hacker_news"
        assert _generate_source_id("Hacker News", {"hacker_news"}) == "hacker_news_1"
        assert _generate_source_id("", set()) == "imported"

    def test_generate_source_id_collisions(self) -> None:
        existing = {"topic", "topic_1", "topic_2"}
        result = _generate_source_id("Topic", existing)
        assert result == "topic_3"

    def test_normalize_url_no_trailing_slash(self) -> None:
        assert _normalize_url("https://example.com") == "https://example.com"

    def test_normalize_url_www_stripped(self) -> None:
        assert _normalize_url("https://www.example.com/feed") == "https://example.com/feed"

    def test_strip_credentials_no_at(self) -> None:
        assert _strip_credentials("https://example.com/feed") == "https://example.com/feed"

    def test_strip_credentials_multiple_at(self) -> None:
        assert _strip_credentials("https://user:pass@example.com/feed?q=@other") == "https://example.com/feed?q=@other"


# ---------------------------------------------------------------------------
# Source Models
# ---------------------------------------------------------------------------
class TestSourceModels:
    def test_source_definition_defaults(self) -> None:
        defn = SourceDefinition(id="test", name="Test", type="rss")
        assert defn.enabled is True
        assert defn.schedule_minutes == 30
        assert defn.config == {}
        assert defn.requires_restart is False

    def test_source_definition_custom_fields(self) -> None:
        defn = SourceDefinition(
            id="custom",
            name="Custom",
            type="api",
            enabled=False,
            schedule_minutes=60,
            config={"list_url": "https://example.com/api"},
        )
        assert defn.enabled is False
        assert defn.schedule_minutes == 60
        assert defn.config == {"list_url": "https://example.com/api"}

    def test_source_test_result(self) -> None:
        result = SourceTestResult(source_id="test", outcome="success", message="OK")
        assert result.outcome == "success"
        assert result.latency_ms is None
        assert result.source_id == "test"

    def test_source_test_result_full(self) -> None:
        result = SourceTestResult(
            source_id="test",
            outcome="transport_error",
            message="Connection refused",
            latency_ms=123.4,
            status_code=503,
            reason_code="connection_refused",
        )
        assert result.outcome == "transport_error"
        assert result.latency_ms == 123.4
        assert result.status_code == 503
        assert result.reason_code == "connection_refused"
