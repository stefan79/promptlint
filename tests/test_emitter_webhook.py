"""Tests for webhook emitter."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import ClassVar

import pytest

from promptlint.emitters.webhook import WebhookEmitter
from promptlint.models import AnalysisResult


class _CaptureHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures POST bodies."""

    received: ClassVar[list[dict]] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _CaptureHandler.received.append(json.loads(body))
        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def webhook_server():
    _CaptureHandler.received = []
    server = HTTPServer(("127.0.0.1", 0), _CaptureHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def test_write_analysis(webhook_server) -> None:
    emitter = WebhookEmitter({"url": webhook_server, "timeout": 5})
    result = AnalysisResult(instruction_count=3, severity="ok")

    emitter.write_analysis(result)

    assert len(_CaptureHandler.received) == 1
    payload = _CaptureHandler.received[0]
    assert payload["type"] == "analysis"
    assert payload["data"]["instruction_count"] == 3


def test_write_feedback(webhook_server) -> None:
    emitter = WebhookEmitter({"url": webhook_server, "timeout": 5})

    emitter.write_feedback({"rating": "good"})

    assert len(_CaptureHandler.received) == 1
    assert _CaptureHandler.received[0]["type"] == "feedback"


def test_custom_headers(webhook_server) -> None:
    emitter = WebhookEmitter(
        {
            "url": webhook_server,
            "headers": {"X-Custom": "test-value"},
            "timeout": 5,
        }
    )

    emitter.write_analysis(AnalysisResult())

    assert len(_CaptureHandler.received) == 1


def test_missing_url_raises() -> None:
    with pytest.raises(KeyError):
        WebhookEmitter({})
