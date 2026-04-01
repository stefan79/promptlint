"""Unit tests for BuiltinProxy with mocked analyzer (no ML models)."""

from __future__ import annotations

import json
import threading
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from promptlint.gateways import ConcurrencyConfig, GatewayInfo
from promptlint.gateways.proxy import BuiltinProxy, analysis_headers
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


def _make_proxy(
    severity: str = "ok",
    block_on: str | None = None,
    concurrency: ConcurrencyConfig | None = None,
) -> tuple[BuiltinProxy, MagicMock]:
    analyzer = _mock_analyzer(severity)
    with patch.object(BuiltinProxy, "__init__", lambda self, **kw: None):  # noqa: ARG005
        proxy = BuiltinProxy()
    proxy._target = "http://localhost:9999"
    proxy._block_on = block_on
    proxy._vendor_override = None
    proxy._timeout = 10.0
    proxy._info = GatewayInfo(type="builtin-proxy", id="test-proxy-1")
    proxy._analyzer = analyzer
    concurrency = concurrency or ConcurrencyConfig()
    proxy._semaphore = threading.Semaphore(concurrency.max_concurrent) if concurrency.max_concurrent > 0 else None
    return proxy, analyzer


# --- Vendor detection passthrough ---


def test_passthrough_non_json_body() -> None:
    """Non-JSON POST bodies should pass through without analysis errors."""
    proxy, analyzer = _make_proxy()
    app = proxy.create_app()
    client = TestClient(app, raise_server_exceptions=False)
    # The forward will fail since no real target, but we should not get a 422 from analysis
    response = client.post("/v1/messages", content=b"not json at all")
    # Vendor detection fails on non-JSON -> passes through (connection error to fake target)
    assert response.status_code != 422 or "promptlint_blocked" not in response.text
    analyzer.analyze.assert_not_called()


def test_passthrough_unknown_vendor() -> None:
    """Requests that don't match any vendor should pass through."""
    proxy, analyzer = _make_proxy()
    app = proxy.create_app()
    client = TestClient(app, raise_server_exceptions=False)
    body = {"unknown_key": "value"}
    client.post("/v1/whatever", json=body)
    analyzer.analyze.assert_not_called()


# --- 429 on overload ---


def test_overload_returns_429() -> None:
    proxy, _analyzer = _make_proxy(concurrency=ConcurrencyConfig(max_concurrent=1))
    # Exhaust the semaphore
    assert proxy._semaphore is not None
    proxy._semaphore.acquire(blocking=False)
    app = proxy.create_app()
    client = TestClient(app, raise_server_exceptions=False)
    body = {"system": "Be helpful.", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 100}
    response = client.post("/v1/messages", json=body)
    assert response.status_code == 429
    assert response.json()["error"] == "promptlint_overload"
    assert response.headers.get("retry-after") == "1"
    proxy._semaphore.release()


# --- 422 on block ---


def test_block_returns_422() -> None:
    proxy, _analyzer = _make_proxy(severity="critical", block_on="critical")
    app = proxy.create_app()
    client = TestClient(app, raise_server_exceptions=False)
    body = {"system": "Be helpful.", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 100}
    response = client.post("/v1/messages", json=body)
    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "promptlint_blocked"
    assert data["severity"] == "critical"


def test_no_block_below_threshold() -> None:
    proxy, _analyzer = _make_proxy(severity="warning", block_on="critical")
    app = proxy.create_app()
    client = TestClient(app, raise_server_exceptions=False)
    body = {"system": "Be helpful.", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 100}
    response = client.post("/v1/messages", json=body)
    # Not blocked, forward fails but not 422
    assert response.status_code != 422 or "promptlint_blocked" not in response.text


# --- Header injection ---


def test_analysis_headers_populated() -> None:
    result = AnalysisResult(
        instruction_count=5,
        unique_instruction_count=4,
        density=10.0,
        severity="warning",
    )
    headers = analysis_headers(result)
    assert headers["X-Promptlint-Instructions"] == "5"
    assert headers["X-Promptlint-Unique"] == "4"
    assert headers["X-Promptlint-Density"] == "10.0"
    assert headers["X-Promptlint-Severity"] == "warning"
    assert headers["X-Promptlint-Contradictions"] == "0"


# --- result.gateway is populated ---


def test_result_gateway_populated() -> None:
    """Gateway-mediated analysis should set result.gateway."""
    proxy, _analyzer = _make_proxy()
    body = {"system": "Be helpful.", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 100}
    raw = json.dumps(body).encode()
    normalized = proxy.extract_request(raw)
    result = proxy._run_analysis(normalized)
    assert result.gateway is not None
    assert result.gateway.type == "builtin-proxy"
    assert result.gateway.id == "test-proxy-1"


# --- Non-POST passthrough ---


def test_get_passthrough() -> None:
    """GET requests should pass through without analysis."""
    proxy, analyzer = _make_proxy()
    app = proxy.create_app()
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health")
    # Will fail to connect to fake target, but the route exists
    analyzer.analyze.assert_not_called()
    # Should not be 405 Method Not Allowed
    assert response.status_code != 405


# --- create_app compat shim with fail_on ---


def test_create_app_compat_fail_on() -> None:
    """The create_app factory should map fail_on to block_on."""
    from promptlint.gateways.proxy import create_app

    with patch("promptlint.gateways.proxy.BuiltinProxy") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.create_app.return_value = MagicMock()
        mock_cls.return_value = mock_instance
        create_app(target="http://localhost:1234", fail_on="warning")
        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args
        assert call_kwargs.kwargs.get("block_on") == "warning"
        assert "fail_on" not in call_kwargs.kwargs
