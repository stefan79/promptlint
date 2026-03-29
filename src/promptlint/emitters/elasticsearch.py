"""Elasticsearch / OpenSearch emitter."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from promptlint.models import AnalysisResult, Feedback


class ElasticsearchEmitter:
    """Indexes analysis results and feedback into Elasticsearch."""

    def __init__(self, config: dict) -> None:
        self._url = config["url"].rstrip("/")
        self._index = config.get("index", "promptlint-analyses")
        self._auth = config.get("auth")
        self._timeout = config.get("timeout", 10)

    def write_analysis(self, result: AnalysisResult) -> None:
        doc = asdict(result)
        doc["record_type"] = "analysis"
        self._index_doc(doc)

    def write_feedback(self, feedback: Feedback) -> None:
        doc = {**asdict(feedback), "record_type": "feedback"}
        self._index_doc(doc)

    def _index_doc(self, doc: dict) -> None:
        url = f"{self._url}/{self._index}/_doc"
        body = json.dumps(doc, default=str).encode("utf-8")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._auth:
            headers["Authorization"] = f"ApiKey {self._auth}"
        req = Request(url, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=self._timeout) as resp:
            resp.read()
