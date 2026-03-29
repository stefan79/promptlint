"""Integration tests for the built-in proxy gateway.

Requires:
- Echo service on port 8888 (mendhak/http-https-echo from docker-compose.test.yml)
- ML models (DeBERTa, MiniLM) downloaded locally

Run with: pytest --integration tests/integration/test_proxy.py
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from promptlint.gateways.proxy import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
def echo_proxy() -> TestClient:
    """Proxy targeting the local echo service."""
    try:
        app = create_app(target="http://localhost:8888")
    except OSError as exc:
        pytest.skip(f"ML models not available: {exc}")
    return TestClient(app, raise_server_exceptions=False)


def test_proxy_forwards_anthropic_request(echo_proxy: TestClient) -> None:
    body = {
        "system": "You are helpful.",
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 100,
        "model": "claude-sonnet-4-20250514",
    }
    response = echo_proxy.post("/v1/messages", json=body)
    assert response.status_code == 200


def test_proxy_forwards_openai_request(echo_proxy: TestClient) -> None:
    body = {
        "messages": [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
        ],
        "model": "gpt-4o",
    }
    response = echo_proxy.post("/v1/chat/completions", json=body)
    assert response.status_code == 200


def test_proxy_passthrough_non_json(echo_proxy: TestClient) -> None:
    response = echo_proxy.post("/health", content=b"ping")
    # Should pass through without analysis errors
    assert response.status_code in (200, 422)
