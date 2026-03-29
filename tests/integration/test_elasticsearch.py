"""Integration tests for Elasticsearch emitter (requires Docker)."""

from __future__ import annotations

import json
from urllib.request import Request, urlopen

import pytest

from promptlint.emitters.elasticsearch import ElasticsearchEmitter
from promptlint.models import AnalysisResult

ES_URL = "http://localhost:9200"
TEST_INDEX = "promptlint-integration-test"


def _es_available() -> bool:
    try:
        with urlopen(f"{ES_URL}/_cluster/health", timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def _delete_index() -> None:
    try:
        req = Request(f"{ES_URL}/{TEST_INDEX}", method="DELETE")
        with urlopen(req, timeout=5) as resp:
            resp.read()
    except Exception:
        pass


def _refresh_index() -> None:
    req = Request(f"{ES_URL}/{TEST_INDEX}/_refresh", method="POST")
    with urlopen(req, timeout=5) as resp:
        resp.read()


def _search_index() -> list[dict]:
    req = Request(f"{ES_URL}/{TEST_INDEX}/_search", method="GET")
    with urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read())
    return [hit["_source"] for hit in data["hits"]["hits"]]


@pytest.fixture(autouse=True)
def clean_index():
    _delete_index()
    yield
    _delete_index()


@pytest.mark.integration
def test_write_and_read_back() -> None:
    if not _es_available():
        pytest.skip("Elasticsearch not available")

    emitter = ElasticsearchEmitter({"url": ES_URL, "index": TEST_INDEX})
    result = AnalysisResult(instruction_count=42, severity="warning", density=15.0)

    emitter.write_analysis(result)
    _refresh_index()

    docs = _search_index()
    assert len(docs) == 1
    assert docs[0]["instruction_count"] == 42
    assert docs[0]["severity"] == "warning"


@pytest.mark.integration
def test_write_feedback_and_read_back() -> None:
    if not _es_available():
        pytest.skip("Elasticsearch not available")

    emitter = ElasticsearchEmitter({"url": ES_URL, "index": TEST_INDEX})

    emitter.write_feedback({"analysis_id": "test-id", "rating": "bad"})
    _refresh_index()

    docs = _search_index()
    assert len(docs) == 1
    assert docs[0]["_type"] == "feedback"
    assert docs[0]["rating"] == "bad"
