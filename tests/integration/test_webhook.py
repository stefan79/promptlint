"""Integration tests for webhook emitter (requires Docker)."""

from __future__ import annotations

import json
from urllib.request import urlopen

import pytest

from promptlint.emitters.webhook import WebhookEmitter
from promptlint.models import AnalysisResult

WEBHOOK_URL = "http://localhost:8888"


def _webhook_available() -> bool:
    try:
        with urlopen(WEBHOOK_URL, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


@pytest.mark.integration
def test_post_analysis_accepted() -> None:
    if not _webhook_available():
        pytest.skip("Webhook echo service not available")

    emitter = WebhookEmitter({"url": WEBHOOK_URL, "timeout": 5})
    result = AnalysisResult(instruction_count=7, severity="warning", density=18.5)

    # Should not raise — echo service accepts any POST
    emitter.write_analysis(result)


@pytest.mark.integration
def test_post_feedback_accepted() -> None:
    if not _webhook_available():
        pytest.skip("Webhook echo service not available")

    emitter = WebhookEmitter({"url": WEBHOOK_URL, "timeout": 5})

    emitter.write_feedback({"analysis_id": "test-123", "rating": "bad", "note": "integration test"})


@pytest.mark.integration
def test_echo_returns_posted_payload() -> None:
    """Verify the echo service mirrors back our payload."""
    if not _webhook_available():
        pytest.skip("Webhook echo service not available")

    payload = {"type": "analysis", "data": {"instruction_count": 42, "severity": "ok"}}
    body = json.dumps(payload, default=str).encode("utf-8")
    from urllib.request import Request

    req = Request(WEBHOOK_URL, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=5) as resp:
        echo = json.loads(resp.read())

    # Echo service returns the parsed JSON body in the "json" key
    assert echo["json"]["type"] == "analysis"
    assert echo["json"]["data"]["instruction_count"] == 42
