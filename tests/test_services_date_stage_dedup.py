"""Tests for date_utils, stage_cost, dedup_service, search config, webhook schemas, and quality_report_service."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from schemas.common import ProviderDef
from schemas.search import SearchConfig, _load_search_config_from_file, load_search_config
from schemas.webhook import WebhookCreate, WebhookResponse
from services.cost_tracker import CostSummary, ModelCost
from services.date_utils import format_date
from services.dedup_service import find_dedupe_candidates
from services.quality_report_service import get_quality_report
from services.stage_cost import estimate_stage_cost



# ---------------------------------------------------------------------------
# services/date_utils.py
# ---------------------------------------------------------------------------

class TestFormatDate:
    def test_returns_empty_string_for_none(self):
        assert format_date(None) == ""

    def test_returns_just_now_for_less_than_60s(self):
        now = datetime.now(timezone.utc)
        assert format_date(now) == "just now"

    def test_returns_minutes_ago_for_less_than_1hr(self):
        now = datetime.now(timezone.utc)
        dt = now - timedelta(minutes=5)
        assert format_date(dt) == "5 minutes ago"

    def test_returns_minutes_ago_at_2_minutes(self):
        now = datetime.now(timezone.utc)
        dt = now - timedelta(minutes=2, seconds=30)
        assert format_date(dt) == "2 minutes ago"

    def test_returns_1_hour_ago(self):
        now = datetime.now(timezone.utc)
        dt = now - timedelta(hours=1)
        assert format_date(dt) == "1 hour ago"

    def test_returns_hours_ago(self):
        now = datetime.now(timezone.utc)
        dt = now - timedelta(hours=3)
        assert format_date(dt) == "3 hours ago"

    def test_returns_yesterday(self):
        now = datetime.now(timezone.utc)
        dt = now - timedelta(days=1, hours=1)
        assert format_date(dt) == "yesterday"

    def test_returns_days_ago(self):
        now = datetime.now(timezone.utc)
        dt = now - timedelta(days=4)
        assert format_date(dt) == "4 days ago"

    def test_returns_same_year_format(self):
        now = datetime.now(timezone.utc)
        dt = now - timedelta(days=10)
        result = format_date(dt)
        assert ", " not in result
        assert len(result) > 0

    def test_returns_different_year_format(self):
        dt = datetime(2023, 6, 15, 12, 0, 0)
        result = format_date(dt)
        assert "Jun 15, 2023" == result

    def test_handles_naive_datetime(self):
        naive = datetime(2023, 1, 15, 10, 0, 0)
        result = format_date(naive)
        assert ", 2023" in result

    def test_handles_aware_datetime(self):
        aware = datetime(2023, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        result = format_date(aware)
        assert ", 2023" in result

    def test_future_datetime_returns_month_day(self):
        now = datetime.now(timezone.utc)
        dt = now + timedelta(days=1)
        result = format_date(dt)
        assert "ago" not in result

    def test_boundary_59_seconds_is_just_now(self):
        now = datetime.now(timezone.utc)
        dt = now - timedelta(seconds=59)
        assert format_date(dt) == "just now"

    def test_boundary_60_seconds_is_just_now(self):
        now = datetime.now(timezone.utc)
        dt = now - timedelta(seconds=60)
        assert format_date(dt) == "just now"


# ---------------------------------------------------------------------------
# services/stage_cost.py
# ---------------------------------------------------------------------------

class TestEstimateStageCost:
    def test_returns_error_for_unknown_stage(self):
        result = estimate_stage_cost("nonexistent")
        assert "error" in result
        assert "nonexistent" in result["error"]

    @patch("services.stage_cost.get_cost_summary")
    def test_returns_cost_for_known_stage_without_model(self, mock_summary):
        summary = CostSummary(
            stages={"select": 0.5},
            models=[
                ModelCost(provider="openai", model="gpt-4o", stages={"select": 10}),
            ],
        )
        mock_summary.return_value = summary
        result = estimate_stage_cost("select")
        assert result["stage"] == "select"
        assert result["model"] is None
        assert result["estimated_cost_usd"] == 0.5
        assert result["call_count"] == 10

    @patch("services.stage_cost.get_cost_summary")
    def test_returns_cost_for_known_stage_with_model(self, mock_summary):
        summary = CostSummary(
            stages={"select": 1.0},
            models=[
                ModelCost(
                    provider="openai",
                    model="gpt-4o",
                    estimated_cost_usd=10.0,
                    call_count=20,
                    stages={"select": 5, "write": 15},
                ),
            ],
        )
        mock_summary.return_value = summary
        result = estimate_stage_cost("select", model="openai/gpt-4o")
        assert result["stage"] == "select"
        assert result["model"] == "openai/gpt-4o"
        assert result["call_count"] == 5
        assert result["estimated_cost_usd"] == round(10.0 / 20 * 5, 4)

    @patch("services.stage_cost.get_cost_summary")
    def test_returns_zero_when_model_not_found(self, mock_summary):
        summary = CostSummary(stages={}, models=[])
        mock_summary.return_value = summary
        result = estimate_stage_cost("select", model="unknown/model")
        assert result["stage"] == "select"
        assert result["model"] == "unknown/model"
        assert result["estimated_cost_usd"] == 0.0
        assert result["call_count"] == 0
        assert "note" in result

    @patch("services.stage_cost.get_cost_summary")
    def test_handles_empty_cost_summary(self, mock_summary):
        summary = CostSummary(stages={}, models=[])
        mock_summary.return_value = summary
        result = estimate_stage_cost("research")
        assert result["stage"] == "research"
        assert result["model"] is None
        assert result["estimated_cost_usd"] == 0.0
        assert result["call_count"] == 0

    @patch("services.stage_cost.get_cost_summary")
    def test_handles_model_with_zero_calls(self, mock_summary):
        summary = CostSummary(
            stages={"write": 0.0},
            models=[
                ModelCost(
                    provider="anthropic",
                    model="claude-sonnet-4-20250514",
                    estimated_cost_usd=0.0,
                    call_count=0,
                    stages={"write": 0},
                ),
            ],
        )
        mock_summary.return_value = summary
        result = estimate_stage_cost("write", model="anthropic/claude-sonnet-4-20250514")
        assert result["estimated_cost_usd"] == 0.0
        assert result["call_count"] == 0

    def test_all_valid_stages_accepted(self):
        for stage in ("select", "research", "write", "edit", "finalize", "publish"):
            with patch("services.stage_cost.get_cost_summary", return_value=CostSummary()):
                result = estimate_stage_cost(stage)
                assert result["stage"] == stage


# ---------------------------------------------------------------------------
# services/dedup_service.py
# ---------------------------------------------------------------------------

class TestFindDedupeCandidates:
    @patch("services.dedup_service.normalize_url", return_value="https://example.com/article")
    @patch("services.dedup_service.db")
    def test_returns_empty_when_no_url_matches(self, mock_db, mock_norm_url):
        mock_db.session.execute.return_value.all.return_value = []
        result = find_dedupe_candidates("Some Title", url="https://example.com/article")
        assert result == []

    @patch("services.dedup_service.normalize_url", return_value="https://example.com/a")
    @patch("services.dedup_service.normalize_title", return_value="some title")
    @patch("services.dedup_service._escape_like_pattern", side_effect=lambda x: x)
    @patch("services.dedup_service.db")
    def test_finds_matches_by_url(self, mock_db, mock_esc, mock_norm_title, mock_norm_url):
        mock_row = (1, "Some Title", "https://example.com/a", "done",
                    datetime(2025, 1, 1, tzinfo=timezone.utc))
        mock_db.session.execute.return_value.all.return_value = [mock_row]
        result = find_dedupe_candidates("Other Title", url="https://example.com/a")
        assert len(result) == 1
        assert result[0]["id"] == 1

    @patch("services.dedup_service.normalize_url", return_value="")
    @patch("services.dedup_service.normalize_title", return_value="some title")
    @patch("services.dedup_service._escape_like_pattern", side_effect=lambda x: x)
    @patch("services.dedup_service.db")
    def test_finds_matches_by_title(self, mock_db, mock_esc, mock_norm_title, mock_norm_url):
        mock_row = (2, "Some Title Here", "https://other.com/b", "pending",
                    datetime(2025, 6, 1, tzinfo=timezone.utc))
        mock_db.session.execute.return_value.all.return_value = [mock_row]
        result = find_dedupe_candidates("Some Title Here")
        assert len(result) == 1
        assert result[0]["id"] == 2

    @patch("services.dedup_service.normalize_url", return_value="https://example.com/a")
    @patch("services.dedup_service.normalize_title", return_value="some title")
    @patch("services.dedup_service._escape_like_pattern", side_effect=lambda x: x)
    @patch("services.dedup_service.db")
    def test_respects_limit(self, mock_db, mock_esc, mock_norm_title, mock_norm_url):
        rows = [
            (i, f"Title {i}", f"https://example.com/{i}", "done",
             datetime(2025, 1, 1, tzinfo=timezone.utc))
            for i in range(1, 6)
        ]
        mock_db.session.execute.return_value.all.return_value = rows
        result = find_dedupe_candidates("Some Title", url="https://example.com/a", limit=2)
        assert len(result) <= 2

    @patch("services.dedup_service.normalize_url", return_value="https://example.com/a")
    @patch("services.dedup_service._escape_like_pattern", side_effect=lambda x: x)
    @patch("services.dedup_service.db")
    def test_handles_missing_url_gracefully(self, mock_db, mock_esc, mock_norm_url):
        mock_db.session.execute.return_value.all.return_value = []
        result = find_dedupe_candidates("Some Title", url=None)
        assert result == []

    @patch("services.dedup_service.normalize_url", return_value="")
    @patch("services.dedup_service.normalize_title", return_value="")
    @patch("services.dedup_service.db")
    def test_returns_empty_when_normalized_title_is_empty(self, mock_db, mock_norm_title, mock_norm_url):
        result = find_dedupe_candidates("Some Title")
        assert result == []


# ---------------------------------------------------------------------------
# schemas/search.py
# ---------------------------------------------------------------------------

class TestSearchConfig:
    def test_search_config_defaults(self):
        cfg = SearchConfig()
        assert cfg.providers == []
        assert cfg.default_provider == "duckduckgo"

    def test_search_config_with_providers(self):
        cfg = SearchConfig(
            providers=[ProviderDef(id="google", type="google", enabled=False)],
            default_provider="google",
        )
        assert len(cfg.providers) == 1
        assert cfg.providers[0].id == "google"
        assert cfg.default_provider == "google"

    @patch("schemas.search.cached_config_with_mtime")
    def test_load_search_config_delegates(self, mock_cached):
        mock_cached.return_value = SearchConfig(default_provider="test")
        result = load_search_config(path="/tmp/nonexistent.yaml")
        assert result.default_provider == "test"
        mock_cached.assert_called_once()

    def test_load_search_config_from_file_missing_returns_default(self):
        result = _load_search_config_from_file("/tmp/definitely_missing_providers.yaml")
        assert result.default_provider == "duckduckgo"
        assert len(result.providers) == 1
        assert result.providers[0].id == "duckduckgo"

    def test_load_search_config_from_file_existing(self, tmp_path):
        providers_yaml = (
            "search_providers:\n"
            "  - id: myprovider\n"
            "    type: custom\n"
            "    enabled: true\n"
            "default_search_provider: myprovider\n"
        )
        p = tmp_path / "providers.yaml"
        p.write_text(providers_yaml)
        result = _load_search_config_from_file(str(p))
        assert result.default_provider == "myprovider"
        assert len(result.providers) == 1
        assert result.providers[0].id == "myprovider"

    def test_load_search_config_from_file_empty_file(self, tmp_path):
        p = tmp_path / "providers.yaml"
        p.write_text("")
        result = _load_search_config_from_file(str(p))
        assert result.default_provider == "duckduckgo"
        assert result.providers == []


# ---------------------------------------------------------------------------
# schemas/webhook.py
# ---------------------------------------------------------------------------

class TestWebhookCreate:
    def test_valid_create(self):
        w = WebhookCreate(url="https://example.com/hook", event_type="article.published")
        assert w.url == "https://example.com/hook"
        assert w.event_type == "article.published"
        assert w.active is True
        assert w.secret is None
        assert w.name is None

    def test_create_with_optional_fields(self):
        w = WebhookCreate(
            url="https://example.com/hook",
            event_type="newsletter.sent",
            secret="mysecret",
            active=False,
            name="My Webhook",
        )
        assert w.secret == "mysecret"
        assert w.active is False
        assert w.name == "My Webhook"

    def test_create_missing_url_fails(self):
        with pytest.raises(Exception):
            WebhookCreate(event_type="article.published")

    def test_create_missing_event_type_fails(self):
        with pytest.raises(Exception):
            WebhookCreate(url="https://example.com/hook")


class TestWebhookResponse:
    def test_from_attributes(self):
        obj = MagicMock()
        obj.id = 42
        obj.url = "https://example.com/hook"
        obj.event_type = "article.published"
        obj.active = True
        obj.name = "Test"
        obj.created_at = "2025-01-15T12:00:00"
        resp = WebhookResponse.model_validate(obj, from_attributes=True)
        assert resp.id == 42
        assert resp.url == "https://example.com/hook"
        assert resp.event_type == "article.published"
        assert resp.active is True
        assert resp.created_at == "2025-01-15T12:00:00"

    def test_response_fields(self):
        resp = WebhookResponse(
            id=1,
            url="https://example.com/hook",
            event_type="article.published",
            active=True,
            created_at="2025-06-01T00:00:00",
        )
        assert resp.name is None


# ---------------------------------------------------------------------------
# services/quality_report_service.py
# ---------------------------------------------------------------------------

class TestGetQualityReport:
    @patch("services.quality_report_service.db")
    def test_returns_none_for_missing_article(self, mock_db):
        mock_db.session.get.return_value = None
        result = get_quality_report(999)
        assert result is None

    @patch("services.quality_report_service.QualityReport")
    @patch("services.quality_report_service.db")
    def test_returns_none_for_missing_report(self, mock_db, mock_qr_cls):
        mock_db.session.get.return_value = MagicMock()
        mock_qr_cls.query.filter_by.return_value.order_by.return_value.first.return_value = None
        result = get_quality_report(1)
        assert result is None

    @patch("services.quality_report_service.QualityReport")
    @patch("services.quality_report_service.db")
    def test_returns_report_dict(self, mock_db, mock_qr_cls):
        mock_db.session.get.return_value = MagicMock()
        report = MagicMock()
        report.id = 10
        report.article_id = 1
        report.article_version_id = 5
        report.stage = "edit"
        report.overall_score = 0.85
        report.groundedness = 0.9
        report.coherence = 0.8
        report.completeness = 0.7
        report.safety = 0.95
        report.citation_score = 0.6
        report.claim_score = 0.75
        report.passed = True
        report.needs_review = False
        report.findings = [
            {"severity": "error", "message": "bad claim"},
            {"severity": "warning", "message": "low grounding"},
            {"severity": "info", "message": "ok"},
        ]
        report.meta = {"run": "test"}
        report.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        mock_qr_cls.query.filter_by.return_value.order_by.return_value.first.return_value = report
        result = get_quality_report(1)
        assert result is not None
        assert result["id"] == 10
        assert result["overall_score"] == 0.85
        assert result["findings_total"] == 3
        assert len(result["findings_by_severity"]["error"]) == 1
        assert len(result["findings_by_severity"]["warning"]) == 1
        assert len(result["findings_by_severity"]["info"]) == 1
        assert result["created_at"] == "2025-06-01T00:00:00+00:00"

    @patch("services.quality_report_service.QualityReport")
    @patch("services.quality_report_service.db")
    def test_returns_none_on_sqlalchemy_error(self, mock_db, mock_qr_cls):
        mock_db.session.get.side_effect = SQLAlchemyError("db error")
        result = get_quality_report(1)
        assert result is None

    @patch("services.quality_report_service.QualityReport")
    @patch("services.quality_report_service.db")
    def test_report_with_empty_findings(self, mock_db, mock_qr_cls):
        mock_db.session.get.return_value = MagicMock()
        report = MagicMock()
        report.id = 11
        report.article_id = 2
        report.article_version_id = None
        report.stage = "edit"
        report.overall_score = 1.0
        report.groundedness = None
        report.coherence = None
        report.completeness = None
        report.safety = None
        report.citation_score = None
        report.claim_score = None
        report.passed = True
        report.needs_review = False
        report.findings = []
        report.meta = {}
        report.created_at = None
        mock_qr_cls.query.filter_by.return_value.order_by.return_value.first.return_value = report
        result = get_quality_report(2)
        assert result is not None
        assert result["findings_total"] == 0
        assert result["created_at"] is None
        assert result["findings_by_severity"] == {"error": [], "warning": [], "info": []}
