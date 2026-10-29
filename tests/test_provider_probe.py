"""Regression tests for the provider probe.

The probe has to answer one question: does this provider actually serve a
request? Two things used to stop it from answering that:

* It only tried ``GET /models``. An OpenAI-compatible gateway that does not
  implement that route answered 404, which the probe reported as success --
  a green tick on a provider that might well be unusable.
* It sent the credential but not the provider's own headers. A gateway that
  needs a routing header rejected every probe, so a working provider was
  reported as broken.
"""

from unittest.mock import MagicMock, patch

import requests

from ainews_cli.providers.openai import OpenAIProviderAdapter


def _definition(headers=None, model="some-model"):
    adapter = OpenAIProviderAdapter()
    values = {
        "id": "probe-test",
        "base_url": "https://example.test/v1",
        "api_key": "sk-test",
        "model": model,
    }
    if headers:
        values["headers"] = headers
    return adapter.build_definition(values)


class TestProviderProbe:
    """The probe must prove the provider works."""

    def test_models_endpoint_success_is_a_pass(self):
        adapter = OpenAIProviderAdapter()
        definition = _definition()

        resp = MagicMock()
        resp.status_code = 200
        with patch("ainews_cli.providers.openai.requests.get", return_value=resp):
            result = adapter.probe(definition, {"api_key": "sk-test"})

        assert result.success
        assert result.status_code == 200

    def test_missing_models_route_falls_back_to_a_completion(self):
        """A 404 on /models must not be reported as a working provider."""
        adapter = OpenAIProviderAdapter()
        definition = _definition()

        models_resp = MagicMock()
        models_resp.status_code = 404

        completion_resp = MagicMock()
        completion_resp.status_code = 200
        completion_resp.json.return_value = {"choices": [{"message": {"content": "pong"}}]}

        with patch("ainews_cli.providers.openai.requests.get", return_value=models_resp), \
                patch("ainews_cli.providers.openai.requests.post", return_value=completion_resp):
            result = adapter.probe(definition, {"api_key": "sk-test"})

        assert result.success
        assert result.status_code == 200

    def test_endpoint_that_serves_nothing_is_a_failure(self):
        """Both routes dead means the provider does not work."""
        adapter = OpenAIProviderAdapter()
        definition = _definition()

        models_resp = MagicMock()
        models_resp.status_code = 404

        completion_resp = MagicMock()
        completion_resp.status_code = 502

        with patch("ainews_cli.providers.openai.requests.get", return_value=models_resp), \
                patch("ainews_cli.providers.openai.requests.post", return_value=completion_resp):
            result = adapter.probe(definition, {"api_key": "sk-test"})

        assert not result.success
        assert "502" in (result.error or "")

    def test_empty_choices_are_a_failure(self):
        """A 200 with no choices is not a usable provider."""
        adapter = OpenAIProviderAdapter()
        definition = _definition()

        models_resp = MagicMock()
        models_resp.status_code = 404

        completion_resp = MagicMock()
        completion_resp.status_code = 200
        completion_resp.json.return_value = {"choices": []}

        with patch("ainews_cli.providers.openai.requests.get", return_value=models_resp), \
                patch("ainews_cli.providers.openai.requests.post", return_value=completion_resp):
            result = adapter.probe(definition, {"api_key": "sk-test"})

        assert not result.success

    def test_custom_headers_are_sent(self):
        """A gateway that needs a routing header must get it."""
        adapter = OpenAIProviderAdapter()
        definition = _definition(headers={"x-opencode-session": "sess-123"})

        models_resp = MagicMock()
        models_resp.status_code = 404

        completion_resp = MagicMock()
        completion_resp.status_code = 200
        completion_resp.json.return_value = {"choices": [{"message": {"content": "pong"}}]}

        with patch("ainews_cli.providers.openai.requests.get", return_value=models_resp) as mock_get, \
                patch("ainews_cli.providers.openai.requests.post", return_value=completion_resp) as mock_post:
            result = adapter.probe(definition, {"api_key": "sk-test"})

        assert result.success
        assert mock_get.call_args.kwargs["headers"]["x-opencode-session"] == "sess-123"
        assert mock_post.call_args.kwargs["headers"]["x-opencode-session"] == "sess-123"

    def test_authorization_header_is_always_sent(self):
        adapter = OpenAIProviderAdapter()
        definition = _definition()

        resp = MagicMock()
        resp.status_code = 200
        with patch("ainews_cli.providers.openai.requests.get", return_value=resp) as mock_get:
            adapter.probe(definition, {"api_key": "sk-secret"})

        assert mock_get.call_args.kwargs["headers"]["Authorization"] == "Bearer sk-secret"

    def test_probe_never_leaks_the_credential_in_an_error(self):
        adapter = OpenAIProviderAdapter()
        definition = _definition()

        with patch("ainews_cli.providers.openai.requests.get",
                   side_effect=requests.RequestException("failed with Bearer sk-secret")):
            result = adapter.probe(definition, {"api_key": "sk-secret"})

        assert not result.success
        assert "sk-secret" not in (result.error or "")


class TestAdminProbeWiring:
    """The admin panel's test button uses the same probe."""

    def test_probe_reports_the_configured_model_when_discovery_is_empty(self):
        from services.admin_settings import probe_provider

        view = MagicMock()
        view.id = "probe-test"
        view.type = "openai"
        view.local = False
        view.model = "configured-model"
        view.endpoint = "https://example.test/v1"
        view.api_key_ref = "${SOME_KEY}"
        view.headers = ()

        adapter = MagicMock()
        adapter.build_definition.return_value = MagicMock()
        probe_result = MagicMock()
        probe_result.success = True
        probe_result.error = None
        probe_result.latency_ms = 12.0
        adapter.probe.return_value = probe_result
        discovery = MagicMock()
        discovery.success = True
        discovery.models = []
        adapter.discover_models.return_value = discovery

        with patch("services.admin_settings.read_providers", return_value=[view]), \
                patch("ainews_cli.providers.registry.get_adapter", return_value=adapter), \
                patch.dict("os.environ", {"SOME_KEY": "sk-test"}):
            result = probe_provider("probe-test")

        assert result.ok
        assert result.models == ("configured-model",)

    def test_probe_fails_without_a_credential_for_a_hosted_provider(self):
        from services.admin_settings import probe_provider

        view = MagicMock()
        view.id = "probe-test"
        view.type = "openai"
        view.local = False
        view.model = "m"
        view.endpoint = "https://example.test/v1"
        view.api_key_ref = "${MISSING_KEY}"
        view.headers = ()

        with patch("services.admin_settings.read_providers", return_value=[view]), \
                patch.dict("os.environ", {}, clear=False):
            result = probe_provider("probe-test")

        assert not result.ok
        assert "credential" in result.detail
