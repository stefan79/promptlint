"""Webhook emitter — forwards results via HTTP POST."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from promptlint.models import AnalysisResult


class WebhookEmitter:
    """POSTs analysis results and feedback to an HTTP endpoint."""

    def __init__(self, config: dict) -> None:
        self._url = config["url"]
        self._headers = config.get("headers", {})
        self._timeout = config.get("timeout", 10)

    def write_analysis(self, result: AnalysisResult) -> None:
        payload = {"type": "analysis", "data": asdict(result)}
        self._post(payload)

    def write_feedback(self, feedback: dict) -> None:
        payload = {"type": "feedback", "data": feedback}
        self._post(payload)

    def _post(self, payload: dict) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        headers = {"Content-Type": "application/json", **self._headers}
        req = Request(self._url, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=self._timeout) as resp:
            resp.read()
