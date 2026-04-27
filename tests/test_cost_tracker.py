"""Tests for the cost tracking service."""

from unittest.mock import MagicMock, patch

from services.cost_tracker import (
    _load_rates,
    _parse_metric_key,
    get_cost_summary,
)


class TestParseMetricKey:
    """Test metric key parsing."""

    def test_simple_key(self):
        name, labels = _parse_metric_key("llm.tokens")
        assert name == "llm.tokens"
        assert labels == {}

    def test_key_with_labels(self):
        name, labels = _parse_metric_key("llm.tokens{model=gpt-4o,provider=openai}")
        assert name == "llm.tokens"
        assert labels == {"model": "gpt-4o", "provider": "openai"}

    def test_key_with_single_label(self):
        name, labels = _parse_metric_key("llm.calls{provider=anthropic}")
        assert name == "llm.calls"
        assert labels == {"provider": "anthropic"}

    def test_non_llm_key(self):
        name, labels = _parse_metric_key("http.requests")
        assert name == "http.requests"
        assert labels == {}


class TestLoadRates:
    """Test cost rate loading."""

    def test_default_rates_loaded(self):
        rates = _load_rates()
        assert "openai/gpt-4o" in rates
        assert "input" in rates["openai/gpt-4o"]
        assert "output" in rates["openai/gpt-4o"]

    @patch.dict(
        "os.environ", {"COST_RATES": '{"custom/model": {"input": 1.0, "output": 2.0}}'}
    )
    def test_custom_rates_merge_with_defaults(self):
        rates = _load_rates()
        assert "custom/model" in rates
        assert "openai/gpt-4o" in rates  # defaults still present

    @patch.dict("os.environ", {"COST_RATES": "invalid json"})
    def test_invalid_json_falls_back_to_defaults(self):
        rates = _load_rates()
        assert "openai/gpt-4o" in rates


class TestGetCostSummary:
    """Test cost summary generation."""

    def test_empty_metrics(self):
        mock_metrics = MagicMock()
        mock_metrics.get_metrics.return_value = {"counters": {}}

        with patch("services.metrics.get_metrics") as mock_get:
            mock_get.return_value = mock_metrics
            summary = get_cost_summary()

        assert summary.total_tokens == 0
        assert summary.total_cost_usd == 0
        assert summary.total_calls == 0
        assert summary.models == []

    def test_with_llm_tokens(self):
        mock_metrics = MagicMock()
        mock_metrics.get_metrics.return_value = {
            "counters": {
                "llm.tokens{model=gpt-4o,provider=openai}": 50000,
                "llm.calls{model=gpt-4o,provider=openai}": 10,
            }
        }

        with patch("services.metrics.get_metrics") as mock_get:
            mock_get.return_value = mock_metrics
            summary = get_cost_summary()

        assert summary.total_tokens == 50000
        assert summary.total_calls == 10
        assert len(summary.models) == 1
        mc = summary.models[0]
        assert mc.provider == "openai"
        assert mc.model == "gpt-4o"
        assert mc.total_tokens == 50000
        assert mc.call_count == 10
        assert mc.estimated_cost_usd > 0

    def test_unknown_model_no_cost(self):
        mock_metrics = MagicMock()
        mock_metrics.get_metrics.return_value = {
            "counters": {
                "llm.tokens{model=unknown-model,provider=unknown}": 10000,
                "llm.calls{model=unknown-model,provider=unknown}": 5,
            }
        }

        with patch("services.metrics.get_metrics") as mock_get:
            mock_get.return_value = mock_metrics
            summary = get_cost_summary()

        assert summary.total_tokens == 10000
        assert summary.total_cost_usd == 0  # no pricing for unknown model

    def test_multiple_providers(self):
        mock_metrics = MagicMock()
        mock_metrics.get_metrics.return_value = {
            "counters": {
                "llm.tokens{model=gpt-4o,provider=openai}": 30000,
                "llm.calls{model=gpt-4o,provider=openai}": 5,
                "llm.tokens{model=claude-sonnet-4-20250514,provider=anthropic}": 20000,
                "llm.calls{model=claude-sonnet-4-20250514,provider=anthropic}": 3,
            }
        }

        with patch("services.metrics.get_metrics") as mock_get:
            mock_get.return_value = mock_metrics
            summary = get_cost_summary()

        assert summary.total_tokens == 50000
        assert len(summary.models) == 2
        # Should be sorted by cost descending
        assert (
            summary.models[0].estimated_cost_usd >= summary.models[1].estimated_cost_usd
        )
