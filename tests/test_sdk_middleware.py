"""Tests for SDK middleware transports."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx
import pytest

from promptlint.gateways import (
    ConcurrencyConfig,
    GatewayCapability,
    PromptLintBlockedError,
    PromptLintOverloadError,
)
from promptlint.gateways.sdk_middleware import PromptLintAsyncTransport, PromptLintTransport
from promptlint.models import AnalysisResult


def _mock_analyzer(severity: str = "ok") -> MagicMock:
    analyzer = MagicMock()
    analyzer.analyze.return_value = AnalysisResult(
        instruction_count=5,
        unique_instruction_count=4,
        density=10.0,
        severity=severity,
    )
    return analyzer


def _anthropic_request() -> httpx.Request:
    body = {"system": "Be helpful.", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 100}
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages", content=json.dumps(body).encode())


class _EchoTransport(httpx.BaseTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True}, request=request)


class _AsyncEchoTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True}, request=request)


# --- PromptLintTransport ---


def test_transport_capabilities() -> None:
    transport = PromptLintTransport(target=_EchoTransport(), analyzer=_mock_analyzer())
    caps = transport.capabilities
    assert GatewayCapability.LOG_ONLY in caps
    assert GatewayCapability.ANNOTATE in caps
    assert GatewayCapability.BLOCK in caps


def test_transport_info() -> None:
    transport = PromptLintTransport(target=_EchoTransport(), analyzer=_mock_analyzer(), gateway_id="test-gw")
    assert transport.info.type == "sdk-middleware"
    assert transport.info.id == "test-gw"


def test_transport_injects_headers() -> None:
    analyzer = _mock_analyzer()
    transport = PromptLintTransport(target=_EchoTransport(), analyzer=analyzer)
    request = _anthropic_request()
    response = transport.handle_request(request)
    assert response.status_code == 200
    assert request.headers.get("x-promptlint-severity") == "ok"
    assert request.headers.get("x-promptlint-instructions") == "5"


def test_transport_no_headers_when_disabled() -> None:
    analyzer = _mock_analyzer()
    transport = PromptLintTransport(target=_EchoTransport(), analyzer=analyzer, inject_headers=False)
    request = _anthropic_request()
    transport.handle_request(request)
    assert "x-promptlint-severity" not in request.headers


def test_transport_blocks_on_severity() -> None:
    analyzer = _mock_analyzer(severity="critical")
    transport = PromptLintTransport(target=_EchoTransport(), analyzer=analyzer, block_on="critical")
    with pytest.raises(PromptLintBlockedError) as exc_info:
        transport.handle_request(_anthropic_request())
    assert exc_info.value.severity == "critical"


def test_transport_no_block_when_below_threshold() -> None:
    analyzer = _mock_analyzer(severity="warning")
    transport = PromptLintTransport(target=_EchoTransport(), analyzer=analyzer, block_on="critical")
    response = transport.handle_request(_anthropic_request())
    assert response.status_code == 200


def test_transport_no_block_when_not_configured() -> None:
    analyzer = _mock_analyzer(severity="critical")
    transport = PromptLintTransport(target=_EchoTransport(), analyzer=analyzer, block_on=None)
    response = transport.handle_request(_anthropic_request())
    assert response.status_code == 200


def test_transport_passthrough_on_empty_body() -> None:
    analyzer = _mock_analyzer()
    transport = PromptLintTransport(target=_EchoTransport(), analyzer=analyzer)
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages", content=b"")
    response = transport.handle_request(request)
    assert response.status_code == 200
    analyzer.analyze.assert_not_called()


def test_transport_passthrough_on_malformed_body() -> None:
    analyzer = _mock_analyzer()
    transport = PromptLintTransport(target=_EchoTransport(), analyzer=analyzer)
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages", content=b"not json")
    response = transport.handle_request(request)
    assert response.status_code == 200
    analyzer.analyze.assert_not_called()


def test_transport_overload_raises() -> None:
    analyzer = _mock_analyzer()
    transport = PromptLintTransport(
        target=_EchoTransport(), analyzer=analyzer, concurrency=ConcurrencyConfig(max_concurrent=1)
    )
    # Acquire the semaphore externally to simulate full
    assert transport._semaphore is not None
    transport._semaphore.acquire(blocking=False)
    with pytest.raises(PromptLintOverloadError):
        transport.handle_request(_anthropic_request())
    transport._semaphore.release()


def test_transport_unlimited_concurrency() -> None:
    analyzer = _mock_analyzer()
    transport = PromptLintTransport(
        target=_EchoTransport(), analyzer=analyzer, concurrency=ConcurrencyConfig(max_concurrent=0)
    )
    assert transport._semaphore is None
    response = transport.handle_request(_anthropic_request())
    assert response.status_code == 200


# --- PromptLintAsyncTransport ---


@pytest.mark.asyncio
async def test_async_transport_injects_headers() -> None:
    analyzer = _mock_analyzer()
    transport = PromptLintAsyncTransport(target=_AsyncEchoTransport(), analyzer=analyzer)
    request = _anthropic_request()
    response = await transport.handle_async_request(request)
    assert response.status_code == 200
    assert request.headers.get("x-promptlint-severity") == "ok"


@pytest.mark.asyncio
async def test_async_transport_blocks() -> None:
    analyzer = _mock_analyzer(severity="critical")
    transport = PromptLintAsyncTransport(target=_AsyncEchoTransport(), analyzer=analyzer, block_on="critical")
    with pytest.raises(PromptLintBlockedError):
        await transport.handle_async_request(_anthropic_request())


@pytest.mark.asyncio
async def test_async_transport_passthrough_empty_body() -> None:
    analyzer = _mock_analyzer()
    transport = PromptLintAsyncTransport(target=_AsyncEchoTransport(), analyzer=analyzer)
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages", content=b"")
    response = await transport.handle_async_request(request)
    assert response.status_code == 200
    analyzer.analyze.assert_not_called()
