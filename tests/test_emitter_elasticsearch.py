"""Tests for Elasticsearch emitter."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import ClassVar

import pytest

from promptlint.emitters.elasticsearch import ElasticsearchEmitter
from promptlint.models import AnalysisResult, Feedback


class _CaptureHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures POST bodies."""

    received: ClassVar[list[dict]] = []
    last_path: ClassVar[str] = ""
    last_headers: ClassVar[dict[str, str]] = {}

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _CaptureHandler.received.append(json.loads(body))
        _CaptureHandler.last_path = self.path
        _CaptureHandler.last_headers = dict(self.headers)
        self.send_response(201)
        self.end_headers()
        self.wfile.write(b'{"result":"created"}')

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def es_server():
    _CaptureHandler.received = []
    _CaptureHandler.last_path = ""
    _CaptureHandler.last_headers = {}
    server = HTTPServer(("127.0.0.1", 0), _CaptureHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def test_write_analysis(es_server) -> None:
    emitter = ElasticsearchEmitter({"url": es_server, "index": "test-index"})
    result = AnalysisResult(instruction_count=5, severity="warning")

    emitter.write_analysis(result)

    assert len(_CaptureHandler.received) == 1
    doc = _CaptureHandler.received[0]
    assert doc["instruction_count"] == 5
    assert doc["record_type"] == "analysis"


def test_posts_to_correct_index(es_server) -> None:
    emitter = ElasticsearchEmitter({"url": es_server, "index": "my-index"})

    emitter.write_analysis(AnalysisResult())

    assert _CaptureHandler.last_path == "/my-index/_doc"


def test_write_feedback(es_server) -> None:
    emitter = ElasticsearchEmitter({"url": es_server, "index": "test"})

    emitter.write_feedback(Feedback(analysis_id="abc", rating="bad"))

    doc = _CaptureHandler.received[0]
    assert doc["record_type"] == "feedback"
    assert doc["rating"] == "bad"


def test_auth_header(es_server) -> None:
    emitter = ElasticsearchEmitter({"url": es_server, "index": "test", "auth": "my-api-key"})

    emitter.write_analysis(AnalysisResult())

    assert _CaptureHandler.last_headers.get("Authorization") == "ApiKey my-api-key"


def test_no_auth_header(es_server) -> None:
    emitter = ElasticsearchEmitter({"url": es_server, "index": "test"})

    emitter.write_analysis(AnalysisResult())

    assert "Authorization" not in _CaptureHandler.last_headers


def test_default_index(es_server) -> None:
    emitter = ElasticsearchEmitter({"url": es_server})

    emitter.write_analysis(AnalysisResult())

    assert _CaptureHandler.last_path == "/promptlint-analyses/_doc"
