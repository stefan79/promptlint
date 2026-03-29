"""JSONL file emitter — default, zero-dependency backend."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from promptlint.models import AnalysisResult, Feedback


class JsonlEmitter:
    """Appends analysis results and feedback as JSON lines to a local file."""

    def __init__(self, config: dict) -> None:
        self._path = Path(config.get("path", "promptlint-results.jsonl"))

    def write_analysis(self, result: AnalysisResult) -> None:
        record = {"type": "analysis", "data": asdict(result)}
        self._append(record)

    def write_feedback(self, feedback: Feedback) -> None:
        record = {"type": "feedback", "data": asdict(feedback)}
        self._append(record)

    def _append(self, record: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
