"""Opt-in contract test for locally built Eggsearch native wheels.

Run with the qualification wheel on PYTHONPATH; ordinary CI skips when the
optional binding is not installed.
"""

from __future__ import annotations

import asyncio

import pytest

eggsearch = pytest.importorskip("eggsearch")


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


def test_native_wheel_import_contract_and_offline_provider_status(config_path):
    client = eggsearch.AsyncEggsearch(str(config_path))
    contracts = client.tool_contracts()
    tools = {item["name"]: item for item in contracts["tools"]}
    assert contracts["fingerprint"]
    assert "web_search" in tools
    assert "query" in tools["web_search"]["input_schema"]["properties"]

    async def check_status():
        try:
            status = await client.provider_status()
            assert isinstance(status, dict)
        finally:
            await client.aclose()

    asyncio.run(check_status())

