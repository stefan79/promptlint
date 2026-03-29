"""Tests for Prometheus pushgateway emitter."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import ClassVar

import pytest

from promptlint.emitters.prometheus import PrometheusEmitter
from promptlint.models import AnalysisResult, Feedback


class _CaptureHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures POST bodies."""

    received: ClassVar[list[bytes]] = []
    last_path: ClassVar[str] = ""

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _CaptureHandler.received.append(body)
        _CaptureHandler.last_path = self.path
        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def pushgateway():
    _CaptureHandler.received = []
    _CaptureHandler.last_path = ""
    server = HTTPServer(("127.0.0.1", 0), _CaptureHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def test_write_analysis_pushes_metrics(pushgateway) -> None:
    emitter = PrometheusEmitter({"pushgateway": pushgateway, "job": "test"})
    result = AnalysisResult(instruction_count=10, density=25.0, severity="warning")

    emitter.write_analysis(result)

    assert len(_CaptureHandler.received) == 1
    body = _CaptureHandler.received[0].decode("utf-8")
    assert "promptlint_instruction_count" in body
    assert "promptlint_density" in body
    assert "promptlint_contradiction_count" in body
    assert 'severity="warning"' in body


def test_pushes_to_correct_path(pushgateway) -> None:
    emitter = PrometheusEmitter({"pushgateway": pushgateway, "job": "myjob"})

    emitter.write_analysis(AnalysisResult())

    assert _CaptureHandler.last_path == "/metrics/job/myjob"


def test_metric_values(pushgateway) -> None:
    emitter = PrometheusEmitter({"pushgateway": pushgateway})
    result = AnalysisResult(instruction_count=42, density=15.5)

    emitter.write_analysis(result)

    body = _CaptureHandler.received[0].decode("utf-8")
    assert "42" in body
    assert "15.5" in body


def test_write_feedback_is_noop(pushgateway) -> None:
    emitter = PrometheusEmitter({"pushgateway": pushgateway})

    emitter.write_feedback(Feedback(analysis_id="test", rating="good"))

    assert len(_CaptureHandler.received) == 0


def test_format_includes_help_and_type(pushgateway) -> None:
    emitter = PrometheusEmitter({"pushgateway": pushgateway})

    emitter.write_analysis(AnalysisResult())

    body = _CaptureHandler.received[0].decode("utf-8")
    assert "# HELP promptlint_instruction_count" in body
    assert "# TYPE promptlint_instruction_count gauge" in body
