"""HTTPX client construction shared by synchronous LLM SDK adapters."""

from __future__ import annotations

import httpx
from eggfetch.integrations.httpx import EggFetchTransport


def create_eggfetch_transport(*, limits: httpx.Limits) -> EggFetchTransport:
    return EggFetchTransport(
        limits=limits,
        trust_env=True,
        verify=True,
        http1=True,
        http2=False,
    )


def create_httpx_client(*, timeout: float, limits: httpx.Limits) -> httpx.Client:
    """Create a genuine HTTPX client backed by EggFetch's sync transport.

    SDKs still receive HTTPX's public client type. Transport options belong on
    ``EggFetchTransport`` because HTTPX does not forward them to custom
    transports.
    """
    transport = create_eggfetch_transport(limits=limits)
    return httpx.Client(transport=transport, timeout=timeout)
