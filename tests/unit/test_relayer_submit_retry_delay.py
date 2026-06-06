# pyright: reportPrivateUsage=false
"""Tests that relayer_submit_retry_delay_ms is decoupled from relayer_poll_frequency_ms.

The fix introduced a dedicated field for the submit-retry back-off so that operators
can tune how quickly the SDK retries a transient wallet-busy / nonce-behind error
without touching the polling cadence used while waiting for transaction mining.
"""

import asyncio
import dataclasses
from typing import Any
from urllib.parse import urlparse

import httpx

import polymarket._internal.actions.relayer.gasless as _gasless_mod
from polymarket.environments import PRODUCTION

# ---------------------------------------------------------------------------
# Environment field contract
# ---------------------------------------------------------------------------


def test_environment_has_relayer_submit_retry_delay_ms_field() -> None:
    """The new field must exist on the dataclass with the expected default."""
    assert hasattr(PRODUCTION, "relayer_submit_retry_delay_ms")
    assert PRODUCTION.relayer_submit_retry_delay_ms == 500


def test_submit_retry_delay_independent_of_poll_frequency() -> None:
    """Changing poll_frequency must NOT affect the retry delay, and vice-versa."""
    env_custom_poll = dataclasses.replace(PRODUCTION, relayer_poll_frequency_ms=9999)
    assert env_custom_poll.relayer_submit_retry_delay_ms == 500  # unchanged

    env_custom_retry = dataclasses.replace(PRODUCTION, relayer_submit_retry_delay_ms=100)
    assert env_custom_retry.relayer_poll_frequency_ms == 2000  # unchanged


def test_environment_fields_are_independently_settable() -> None:
    """Both fields can be set to distinct values simultaneously."""
    env = dataclasses.replace(
        PRODUCTION,
        relayer_poll_frequency_ms=3000,
        relayer_submit_retry_delay_ms=250,
    )
    assert env.relayer_poll_frequency_ms == 3000
    assert env.relayer_submit_retry_delay_ms == 250


# ---------------------------------------------------------------------------
# Sync retry path uses relayer_submit_retry_delay_ms
# ---------------------------------------------------------------------------


def test_sync_retry_uses_submit_retry_delay_not_poll_frequency() -> None:
    """When a retryable 400 is returned the sync path sleeps for
    relayer_submit_retry_delay_ms, not relayer_poll_frequency_ms."""
    from _relayer_helpers import (  # noqa: PLC0415
        SPENDER,
        TOKEN,
        install_sync_relayer_handler,
        make_sync_deposit_client,
    )

    attempts = {"n": 0}
    sleep_calls: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = urlparse(str(request.url)).path
        if path == "/v1/account/transactions/params":
            return httpx.Response(200, json={"address": "0xRELAY", "nonce": "0"}, request=request)
        if path == "/submit":
            attempts["n"] += 1
            if attempts["n"] == 1:
                return httpx.Response(
                    400,
                    json={"error": "wallet busy: active action in flight"},
                    request=request,
                )
            return httpx.Response(
                200,
                json={
                    "state": "STATE_NEW",
                    "transactionHash": None,
                    "transactionID": "tx-ok",
                },
                request=request,
            )
        return httpx.Response(404, request=request)

    def _capture_sleep(secs: float) -> None:
        sleep_calls.append(secs)

    original = _gasless_mod.time.sleep  # type: ignore[attr-defined]
    _gasless_mod.time.sleep = _capture_sleep  # type: ignore[attr-defined]
    try:
        with make_sync_deposit_client() as client:
            # Set poll frequency high (10 s) and submit retry low (0.05 s) — they must differ
            client._ctx = dataclasses.replace(
                client._ctx,
                environment=dataclasses.replace(
                    client._ctx.environment,
                    relayer_poll_frequency_ms=10_000,
                    relayer_submit_retry_delay_ms=50,
                ),
            )
            install_sync_relayer_handler(client, handler)
            handle = client.approve_erc20(token_address=TOKEN, spender_address=SPENDER, amount=1)
    finally:
        _gasless_mod.time.sleep = original  # type: ignore[attr-defined]

    assert handle.transaction_id == "tx-ok"
    assert attempts["n"] == 2, "expected exactly one retry"
    assert len(sleep_calls) == 1, "expected exactly one sleep call for the retry"
    # The sleep must use 50 ms (0.05 s) — not 10 000 ms (10 s).
    # The value comes from integer arithmetic (50 / 1000) so exact comparison is safe.
    assert sleep_calls[0] == 0.05, (
        f"retry delay was {sleep_calls[0]} s; expected 0.05 s (relayer_submit_retry_delay_ms=50)"
    )


# ---------------------------------------------------------------------------
# Async retry path uses relayer_submit_retry_delay_ms
# ---------------------------------------------------------------------------


def test_async_retry_uses_submit_retry_delay_not_poll_frequency() -> None:
    """When a retryable 400 is returned the async path sleeps for
    relayer_submit_retry_delay_ms, not relayer_poll_frequency_ms."""
    from _relayer_helpers import (  # noqa: PLC0415
        SPENDER,
        TOKEN,
        install_relayer_handler,
        make_deposit_client,
    )

    attempts: dict[str, int] = {"n": 0}
    sleep_calls: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = urlparse(str(request.url)).path
        if path == "/v1/account/transactions/params":
            return httpx.Response(200, json={"address": "0xRELAY", "nonce": "0"}, request=request)
        if path == "/submit":
            attempts["n"] += 1
            if attempts["n"] == 1:
                return httpx.Response(
                    400,
                    json={"error": "wallet busy: active action in flight"},
                    request=request,
                )
            return httpx.Response(
                200,
                json={
                    "state": "STATE_NEW",
                    "transactionHash": None,
                    "transactionID": "tx-async-ok",
                },
                request=request,
            )
        return httpx.Response(404, request=request)

    original_asyncio_sleep = _gasless_mod.asyncio.sleep  # type: ignore[attr-defined]

    async def _capture_asyncio_sleep(secs: float) -> None:
        sleep_calls.append(secs)

    _gasless_mod.asyncio.sleep = _capture_asyncio_sleep  # type: ignore[attr-defined]

    async def run() -> Any:
        client = await make_deposit_client()
        client._ctx = dataclasses.replace(
            client._ctx,
            environment=dataclasses.replace(
                client._ctx.environment,
                relayer_poll_frequency_ms=10_000,
                relayer_submit_retry_delay_ms=50,
            ),
        )
        install_relayer_handler(client, handler)
        try:
            return await client.approve_erc20(
                token_address=TOKEN,
                spender_address=SPENDER,
                amount=1,
            )
        finally:
            await client.close()

    try:
        handle = asyncio.run(run())
    finally:
        _gasless_mod.asyncio.sleep = original_asyncio_sleep  # type: ignore[attr-defined]

    assert handle.transaction_id == "tx-async-ok"
    assert attempts["n"] == 2
    assert len(sleep_calls) == 1
    assert sleep_calls[0] == 0.05, (  # noqa: FURB152
        f"async retry delay was {sleep_calls[0]} s; expected 0.05 s"
    )
