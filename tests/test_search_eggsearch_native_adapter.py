"""Opt-in ainews adapter test using a locally built Eggsearch wheel."""

from __future__ import annotations

import pytest

eggsearch = pytest.importorskip("eggsearch")
try:
    from services.search.eggsearch import EggsearchSearchProvider
    from services.search.evidence import SearchStatus
except ImportError as exc:
    pytest.skip(f"ainews runtime dependencies unavailable: {exc}", allow_module_level=True)


@pytest.fixture
def config_path(tmp_path):
    config = tmp_path / "eggsearch.toml"
    config.write_text(
        "[search]\n"
        "mode = 'off'\n"
        "default_max_results = 10\n"
        "max_results_cap = 50\n"
        "max_query_chars = 512\n"
        "timeout_ms = 8000\n"
        "default_providers = ['duckduckgo']\n"
        "sanitize_output = true\n\n"
        "[search.providers]\nduckduckgo = true\n\n"
        "[fetch]\n"
        "enabled = false\n"
        "timeout_ms = 8000\n"
        "max_bytes = 2000000\n"
        "max_chars_default = 12000\n"
        "max_chars_cap = 50000\n"
        "redirect_limit = 5\n"
        "allow_private_network = false\n"
        "allow_localhost = false\n"
        "sanitize_output = true\n\n"
        "[local]\nenabled = false\nroots = []\n",
        encoding="utf-8",
    )
    return config


def test_adapter_uses_native_sdk_offline(config_path):
    provider = EggsearchSearchProvider(
        "eggsearch", {"config_path": str(config_path), "timeout_seconds": 5}
    )
    # This fixture sets search.mode=off; no external provider request is made.
    outcome = provider.search_detailed("offline contract smoke", max_results=1)
    assert outcome.status in {SearchStatus.EMPTY, SearchStatus.FAILED}
    assert outcome.provider_attempts == ("eggsearch",)
