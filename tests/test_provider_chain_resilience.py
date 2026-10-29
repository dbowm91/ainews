"""Regression tests for provider-chain and stage-resolution resilience.

Three defects are covered here:

1. A fallback provider that cannot be constructed (a missing credential, a
   malformed block) used to take the whole chain down with it -- including a
   primary that had already been yielded. The pipeline then had no provider
   at all and no visible error.
2. ``run_stage`` resolved the provider chain outside its try block, so a
   resolution failure escaped the stage untouched: no pipeline log, no error
   on the article, no metric. The article sat in ``pending`` forever.
3. A reasoning model can spend its whole token budget thinking and leave
   ``content`` empty while the answer sits in ``reasoning_content``. The
   adapter treated that as an empty response.
"""

from unittest.mock import MagicMock, patch

import pytest

from services.llm.errors import ProviderServerError


def _provider_def(provider_id, enabled=True, model="some-model"):
    pdef = MagicMock()
    pdef.id = provider_id
    pdef.enabled = enabled
    pdef.config = {"model": model, "max_tokens": 4096}
    return pdef


class TestProviderChainResilience:
    """``get_provider_chain`` must survive an unusable provider."""

    def test_broken_fallback_does_not_break_the_primary(self):
        """The defect: a broken fallback killed a working primary."""
        from services.llm import get_provider_chain

        providers = [
            _provider_def("local"),
            _provider_def("broken", model="broken-model"),
        ]
        primary_provider = MagicMock()

        with patch("services.llm.get_role_config") as mock_rc, \
                patch("services.llm._get_providers_config_cached") as mock_cfg, \
                patch("services.llm.get_breaker") as mock_breaker, \
                patch("services.llm.get_provider_by_id") as mock_get:
            config = MagicMock()
            config.providers = providers
            mock_cfg.return_value = config

            rc = MagicMock()
            rc.provider = "local"
            rc.model = "primary-model"
            rc.max_tokens = 4096
            mock_rc.return_value = rc

            breaker = MagicMock()
            breaker.can_execute.return_value = True
            mock_breaker.return_value = breaker

            def _get_by_id(provider_id):
                if provider_id == "broken":
                    raise ValueError("api_key must not be empty")
                return primary_provider

            mock_get.side_effect = _get_by_id

            chain = list(get_provider_chain("selector"))

        assert len(chain) == 1
        assert chain[0][0] is primary_provider
        assert chain[0][3] == "local"

    def test_broken_primary_falls_through_to_a_working_fallback(self):
        """An unusable primary is skipped, not fatal."""
        from services.llm import get_provider_chain

        providers = [
            _provider_def("local"),
            _provider_def("backup", model="backup-model"),
        ]
        backup_provider = MagicMock()

        with patch("services.llm.get_role_config") as mock_rc, \
                patch("services.llm._get_providers_config_cached") as mock_cfg, \
                patch("services.llm.get_breaker") as mock_breaker, \
                patch("services.llm.get_provider_by_id") as mock_get:
            config = MagicMock()
            config.providers = providers
            mock_cfg.return_value = config

            rc = MagicMock()
            rc.provider = "local"
            rc.model = "primary-model"
            rc.max_tokens = 4096
            mock_rc.return_value = rc

            breaker = MagicMock()
            breaker.can_execute.return_value = True
            mock_breaker.return_value = breaker

            def _get_by_id(provider_id):
                if provider_id == "local":
                    raise ValueError("api_key must not be empty")
                return backup_provider

            mock_get.side_effect = _get_by_id

            chain = list(get_provider_chain("selector"))

        assert len(chain) == 1
        assert chain[0][0] is backup_provider
        assert chain[0][3] == "backup"

    def test_healthy_primary_does_not_claim_the_circuit_is_open(self, caplog):
        """The 'circuit open' warning was logged unconditionally."""
        from services.llm import get_provider_chain

        providers = [_provider_def("local")]

        with patch("services.llm.get_role_config") as mock_rc, \
                patch("services.llm._get_providers_config_cached") as mock_cfg, \
                patch("services.llm.get_breaker") as mock_breaker, \
                patch("services.llm.get_provider_by_id", return_value=MagicMock()):
            config = MagicMock()
            config.providers = providers
            mock_cfg.return_value = config

            rc = MagicMock()
            rc.provider = "local"
            rc.model = "primary-model"
            rc.max_tokens = 4096
            mock_rc.return_value = rc

            breaker = MagicMock()
            breaker.can_execute.return_value = True
            mock_breaker.return_value = breaker

            with caplog.at_level("WARNING", logger="services.llm"):
                list(get_provider_chain("selector"))

        assert "circuit open" not in caplog.text

    def test_open_circuit_is_reported(self, caplog):
        """An open circuit is still reported, so the operator can see it."""
        from services.llm import get_provider_chain

        providers = [_provider_def("local")]

        with patch("services.llm.get_role_config") as mock_rc, \
                patch("services.llm._get_providers_config_cached") as mock_cfg, \
                patch("services.llm.get_breaker") as mock_breaker, \
                patch("services.llm.get_provider_by_id", return_value=MagicMock()):
            config = MagicMock()
            config.providers = providers
            mock_cfg.return_value = config

            rc = MagicMock()
            rc.provider = "local"
            rc.model = "primary-model"
            rc.max_tokens = 4096
            mock_rc.return_value = rc

            breaker = MagicMock()
            breaker.can_execute.return_value = False
            mock_breaker.return_value = breaker

            with caplog.at_level("WARNING", logger="services.llm"):
                list(get_provider_chain("selector"))

        assert "circuit open" in caplog.text

    def test_broken_fallback_is_reported(self, caplog):
        """A skipped fallback is visible in the log."""
        from services.llm import get_provider_chain

        providers = [
            _provider_def("local"),
            _provider_def("broken", model="broken-model"),
        ]

        with patch("services.llm.get_role_config") as mock_rc, \
                patch("services.llm._get_providers_config_cached") as mock_cfg, \
                patch("services.llm.get_breaker") as mock_breaker, \
                patch("services.llm.get_provider_by_id") as mock_get:
            config = MagicMock()
            config.providers = providers
            mock_cfg.return_value = config

            rc = MagicMock()
            rc.provider = "local"
            rc.model = "primary-model"
            rc.max_tokens = 4096
            mock_rc.return_value = rc

            breaker = MagicMock()
            breaker.can_execute.return_value = True
            mock_breaker.return_value = breaker

            def _get_by_id(provider_id):
                if provider_id == "broken":
                    raise ValueError("api_key must not be empty")
                return MagicMock()

            mock_get.side_effect = _get_by_id

            with caplog.at_level("WARNING", logger="services.llm"):
                list(get_provider_chain("selector"))

        assert "broken" in caplog.text


class TestRunStageProviderResolution:
    """A provider-resolution failure must be recorded, not swallowed."""

    def test_resolution_failure_is_recorded_not_raised(self):
        """The defect: the error escaped the stage and vanished."""
        from tasks.pipeline import run_stage

        article = MagicMock()
        article.id = 7

        with patch("tasks.pipeline.db") as mock_db, \
                patch("tasks.pipeline._get_provider_for_stage") as mock_resolve, \
                patch("tasks.pipeline._handle_stage_exception") as mock_handle:
            mock_db.session.get.return_value = article
            mock_resolve.side_effect = RuntimeError("no provider available")
            mock_handle.return_value = {"article_id": 7, "result": "error"}

            result = run_stage(
                "selector",
                7,
                MagicMock(),
                task_self=MagicMock(),
                run_id=None,
            )

        mock_handle.assert_called_once()
        assert result == {"article_id": 7, "result": "error"}

    def test_resolution_failure_does_not_escape_the_stage(self):
        """The stage must not raise out of run_stage."""
        from tasks.pipeline import run_stage

        article = MagicMock()
        article.id = 7

        with patch("tasks.pipeline.db") as mock_db, \
                patch("schemas.pipeline.get_role_config") as mock_rc, \
                patch("tasks.pipeline._get_provider_for_stage") as mock_resolve, \
                patch("tasks.pipeline._handle_stage_exception") as mock_handle:
            mock_db.session.get.return_value = article
            mock_rc.return_value = MagicMock()
            mock_resolve.side_effect = RuntimeError("boom")
            mock_handle.return_value = {"article_id": 7, "result": "error"}

            # Must not raise.
            run_stage("selector", 7, MagicMock(), task_self=MagicMock(), run_id=None)

    def test_open_circuit_uses_the_circuit_open_handler(self):
        """An open circuit degrades the article instead of vanishing."""
        from services.circuit_breaker import CircuitOpenError
        from tasks.pipeline import run_stage

        with patch("tasks.pipeline.db") as mock_db, \
                patch("schemas.pipeline.get_role_config") as mock_rc, \
                patch("tasks.pipeline._get_provider_for_stage") as mock_resolve, \
                patch("tasks.pipeline._handle_circuit_open_module") as mock_circuit, \
                patch("tasks.pipeline._handle_stage_exception") as mock_handle:
            mock_db.session.get.return_value = MagicMock()
            mock_rc.return_value = MagicMock()
            mock_resolve.side_effect = CircuitOpenError("all providers failed")
            mock_circuit.return_value = {"article_id": 7, "result": "degraded"}

            result = run_stage(
                "selector",
                7,
                MagicMock(),
                task_self=MagicMock(),
                run_id=None,
            )

        mock_circuit.assert_called_once()
        mock_handle.assert_not_called()
        assert result == {"article_id": 7, "result": "degraded"}

    def test_resolution_failure_writes_a_pipeline_log(self):
        """The failure has to reach the audit trail, not just the log file."""
        from tasks.pipeline import run_stage

        article = MagicMock()
        article.id = 7

        with patch("tasks.pipeline.db") as mock_db, \
                patch("schemas.pipeline.get_role_config") as mock_rc, \
                patch("tasks.pipeline._get_provider_for_stage") as mock_resolve, \
                patch("tasks.pipeline._log_pipeline") as mock_log, \
                patch("tasks.pipeline.get_metrics") as mock_metrics, \
                patch("services.pipeline_monitor.record_stage_result"), \
                patch("tasks.pipeline._handle_stage_failure", return_value=False):
            mock_db.session.get.return_value = article
            mock_rc.return_value = MagicMock()
            mock_resolve.side_effect = RuntimeError("no provider available")

            with pytest.raises(RuntimeError):
                run_stage(
                    "selector",
                    7,
                    MagicMock(),
                    task_self=MagicMock(),
                    run_id=99,
                )

        mock_log.assert_called_once()
        assert mock_log.call_args[0][1] == "selector"
        assert mock_log.call_args[0][2] == "error"


class TestReasoningContentFallback:
    """A reasoning model can leave ``content`` empty."""

    def test_message_text_prefers_content(self):
        from services.llm.openai import _message_text

        message = MagicMock()
        message.content = "the answer"
        message.reasoning_content = "thinking out loud"

        assert _message_text(message) == "the answer"

    def test_message_text_falls_back_to_reasoning(self):
        from services.llm.openai import _message_text

        message = MagicMock()
        message.content = ""
        message.reasoning_content = "the answer, after thinking"

        assert _message_text(message) == "the answer, after thinking"

    def test_message_text_empty_when_there_is_nothing(self):
        from services.llm.openai import _message_text

        message = MagicMock()
        message.content = ""
        message.reasoning_content = None

        assert _message_text(message) == ""

    def test_do_chat_uses_reasoning_content(self):
        """The chat call must not raise 'empty content' for a reasoning model."""
        from services.llm.openai import OpenAIProvider

        provider = OpenAIProvider(
            "openai-test",
            {
                "api_key": "sk-test",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o-mini",
            },
        )

        message = MagicMock()
        message.content = ""
        message.reasoning_content = "LOCAL OK"

        choice = MagicMock()
        choice.message = message
        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = None

        client = MagicMock()
        client.chat.completions.create.return_value = resp
        provider._client = client

        result = provider._do_chat([{"role": "user", "content": "hi"}])

        assert result.text == "LOCAL OK"

    def test_do_chat_still_raises_when_both_are_empty(self):
        from services.llm.openai import OpenAIProvider

        provider = OpenAIProvider(
            "openai-test",
            {
                "api_key": "sk-test",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o-mini",
            },
        )

        message = MagicMock()
        message.content = ""
        message.reasoning_content = ""

        choice = MagicMock()
        choice.message = message
        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = None

        client = MagicMock()
        client.chat.completions.create.return_value = resp
        provider._client = client

        with pytest.raises(ProviderServerError):
            provider._do_chat([{"role": "user", "content": "hi"}])

    def test_structured_call_uses_reasoning_content(self):
        from services.llm.openai import OpenAIProvider

        provider = OpenAIProvider(
            "openai-test",
            {
                "api_key": "sk-test",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o-mini",
            },
        )

        message = MagicMock()
        message.content = ""
        message.reasoning_content = '{"selected": true}'

        choice = MagicMock()
        choice.message = message
        choice.finish_reason = "length"
        resp = MagicMock()
        resp.choices = [choice]

        client = MagicMock()
        client.chat.completions.create.return_value = resp
        provider._client = client

        out = provider._do_chat_with_schema(
            [{"role": "user", "content": "hi"}],
            MagicMock(),
            None,
            0.0,
            1024,
            {"type": "object"},
        )

        assert out == '{"selected": true}'
