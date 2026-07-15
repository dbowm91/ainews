from __future__ import annotations

from typing import Any

from ainews_cli.sources.models import (
    SourceAdapterField,
    SourceAdapterMetadata,
    SourceDefinition,
    SourceTestResult,
)
from ainews_cli.sources.registry import register_source_adapter


@register_source_adapter("rss")
class RSSSourceAdapter:
    metadata = SourceAdapterMetadata(
        type_id="rss",
        display_name="RSS Feed",
        description="RSS or Atom feed source",
        endpoint_field="feed_url",
        auth_fields=[],
        opml_representable=True,
        default_schedule_minutes=30,
        requires_config=["feed_url"],
        sensitive_fields=["api_key"],
        user_facing_fields=["feed_url"],
    )

    def fields(self) -> list[SourceAdapterField]:
        return [
            SourceAdapterField(name="id", label="Source ID", description="Unique identifier (lowercase, underscores)", field_type="text", required=True),
            SourceAdapterField(name="name", label="Display Name", description="Human-readable name", field_type="text", required=True),
            SourceAdapterField(name="feed_url", label="Feed URL", description="RSS or Atom feed URL", field_type="url", required=True),
            SourceAdapterField(name="max_items", label="Max Items", description="Maximum items per fetch", field_type="int", required=False, default="50"),
            SourceAdapterField(name="schedule_minutes", label="Schedule (minutes)", description="Polling interval in minutes", field_type="int", required=False, default="30"),
            SourceAdapterField(name="request_timeout", label="Request Timeout", description="HTTP timeout in seconds", field_type="int", required=False, default="15"),
        ]

    def build_definition(self, values: dict[str, Any]) -> SourceDefinition:
        config = {
            "feed_url": values.get("feed_url", ""),
            "max_items": int(values.get("max_items", 50)),
            "request_timeout": int(values.get("request_timeout", 15)),
            "user_agent": "AINewsBot/1.0",
            "min_content_length": 200,
        }
        return SourceDefinition(
            id=values.get("id", ""),
            name=values.get("name", ""),
            type="rss",
            enabled=True,
            schedule_minutes=int(values.get("schedule_minutes", 30)),
            config=config,
            endpoint_summary=config.get("feed_url", ""),
        )

    def test_source(self, definition: SourceDefinition) -> SourceTestResult:
        from ainews_cli.doctor.checks.sources import probe_source
        url = definition.config.get("feed_url", "")
        if not url:
            return SourceTestResult(
                source_id=definition.id,
                outcome="config_error",
                message="No feed URL configured",
            )
        result = probe_source(url, "rss")
        return SourceTestResult(
            source_id=definition.id,
            outcome=result["outcome"],
            message=result["message"],
            latency_ms=result.get("latency_ms"),
            status_code=result.get("status_code"),
            reason_code=result.get("reason_code"),
        )

    def get_endpoint_summary(self, config: dict[str, Any]) -> str:
        return config.get("feed_url", "(no URL)")

    def redact_config(self, config: dict[str, Any]) -> dict[str, Any]:
        return dict(config)

    def opml_repr(self, definition: SourceDefinition) -> dict[str, str] | None:
        url = definition.config.get("feed_url", "")
        if not url:
            return None
        return {
            "text": definition.name,
            "title": definition.name,
            "xmlUrl": url,
        }

    def from_opml(self, attributes: dict[str, str]) -> dict[str, Any] | None:
        xml_url = attributes.get("xmlUrl", "")
        if not xml_url:
            return None
        title = attributes.get("title") or attributes.get("text", "")
        return {
            "name": title,
            "feed_url": xml_url,
        }


@register_source_adapter("api")
class APISourceAdapter:
    metadata = SourceAdapterMetadata(
        type_id="api",
        display_name="REST API",
        description="JSON REST API source",
        endpoint_field="list_url",
        auth_fields=["api_key"],
        opml_representable=False,
        default_schedule_minutes=60,
        requires_config=["list_url"],
        sensitive_fields=["api_key"],
        user_facing_fields=["list_url"],
    )

    def fields(self) -> list[SourceAdapterField]:
        return [
            SourceAdapterField(name="id", label="Source ID", description="Unique identifier (lowercase, underscores)", field_type="text", required=True),
            SourceAdapterField(name="name", label="Display Name", description="Human-readable name", field_type="text", required=True),
            SourceAdapterField(name="list_url", label="List URL", description="URL returning a list of items", field_type="url", required=True),
            SourceAdapterField(name="api_key", label="API Key", description="API key for authentication", field_type="password", required=False, sensitive=True),
            SourceAdapterField(name="max_items", label="Max Items", description="Maximum items per fetch", field_type="int", required=False, default="30"),
            SourceAdapterField(name="schedule_minutes", label="Schedule (minutes)", description="Polling interval in minutes", field_type="int", required=False, default="60"),
        ]

    def build_definition(self, values: dict[str, Any]) -> SourceDefinition:
        config = {
            "list_url": values.get("list_url", ""),
            "max_items": int(values.get("max_items", 30)),
            "request_timeout": 15,
            "user_agent": "AINewsBot/1.0",
        }
        if values.get("api_key"):
            config["api_key"] = values["api_key"]
        return SourceDefinition(
            id=values.get("id", ""),
            name=values.get("name", ""),
            type="api",
            enabled=True,
            schedule_minutes=int(values.get("schedule_minutes", 60)),
            config=config,
            endpoint_summary=config.get("list_url", ""),
        )

    def test_source(self, definition: SourceDefinition) -> SourceTestResult:
        from ainews_cli.doctor.checks.sources import probe_source
        url = definition.config.get("list_url", "")
        if not url:
            return SourceTestResult(
                source_id=definition.id,
                outcome="config_error",
                message="No list URL configured",
            )
        result = probe_source(url, "api")
        return SourceTestResult(
            source_id=definition.id,
            outcome=result["outcome"],
            message=result["message"],
            latency_ms=result.get("latency_ms"),
            status_code=result.get("status_code"),
            reason_code=result.get("reason_code"),
        )

    def get_endpoint_summary(self, config: dict[str, Any]) -> str:
        return config.get("list_url", "(no URL)")

    def redact_config(self, config: dict[str, Any]) -> dict[str, Any]:
        redacted = dict(config)
        if "api_key" in redacted:
            redacted["api_key"] = "****" + redacted["api_key"][-4:] if len(redacted["api_key"]) > 4 else "****"
        return redacted

    def opml_repr(self, definition: SourceDefinition) -> dict[str, str] | None:
        return None

    def from_opml(self, attributes: dict[str, str]) -> dict[str, Any] | None:
        return None


@register_source_adapter("web")
class WebSourceAdapter:
    metadata = SourceAdapterMetadata(
        type_id="web",
        display_name="Web Scraper",
        description="HTML scraping source",
        endpoint_field="listing_url",
        auth_fields=[],
        opml_representable=False,
        default_schedule_minutes=60,
        requires_config=["listing_url"],
        sensitive_fields=[],
        user_facing_fields=["listing_url"],
    )

    def fields(self) -> list[SourceAdapterField]:
        return [
            SourceAdapterField(name="id", label="Source ID", description="Unique identifier (lowercase, underscores)", field_type="text", required=True),
            SourceAdapterField(name="name", label="Display Name", description="Human-readable name", field_type="text", required=True),
            SourceAdapterField(name="base_url", label="Base URL", description="Website base URL", field_type="url", required=True),
            SourceAdapterField(name="listing_url", label="Listing URL", description="Page listing articles", field_type="url", required=True),
            SourceAdapterField(name="card_selector", label="Card CSS Selector", description="CSS selector for article cards", field_type="text", required=True),
            SourceAdapterField(name="link_selector", label="Link CSS Selector", description="CSS selector for article links", field_type="text", required=True),
            SourceAdapterField(name="schedule_minutes", label="Schedule (minutes)", description="Polling interval in minutes", field_type="int", required=False, default="60"),
        ]

    def build_definition(self, values: dict[str, Any]) -> SourceDefinition:
        config = {
            "base_url": values.get("base_url", ""),
            "listing_url": values.get("listing_url", ""),
            "listing": {
                "card_selector": values.get("card_selector", ""),
                "link_selector": values.get("link_selector", ""),
                "link_attribute": "href",
            },
            "article": {},
            "max_items": 50,
            "request_delay_min": 1.5,
            "request_delay_max": 4.0,
            "max_retries": 3,
            "user_agent": "AINewsBot/1.0",
        }
        return SourceDefinition(
            id=values.get("id", ""),
            name=values.get("name", ""),
            type="web",
            enabled=True,
            schedule_minutes=int(values.get("schedule_minutes", 60)),
            config=config,
            endpoint_summary=config.get("listing_url", ""),
        )

    def test_source(self, definition: SourceDefinition) -> SourceTestResult:
        from ainews_cli.doctor.checks.sources import probe_source
        url = definition.config.get("listing_url", "")
        if not url:
            return SourceTestResult(
                source_id=definition.id,
                outcome="config_error",
                message="No listing URL configured",
            )
        result = probe_source(url, "web")
        return SourceTestResult(
            source_id=definition.id,
            outcome=result["outcome"],
            message=result["message"],
            latency_ms=result.get("latency_ms"),
            status_code=result.get("status_code"),
            reason_code=result.get("reason_code"),
        )

    def get_endpoint_summary(self, config: dict[str, Any]) -> str:
        return config.get("listing_url", "(no URL)")

    def redact_config(self, config: dict[str, Any]) -> dict[str, Any]:
        return dict(config)

    def opml_repr(self, definition: SourceDefinition) -> dict[str, str] | None:
        return None

    def from_opml(self, attributes: dict[str, str]) -> dict[str, Any] | None:
        return None
