"""Tests for JSONL emitter."""

from __future__ import annotations

import json

from promptlint.emitters.jsonl import JsonlEmitter
from promptlint.models import AnalysisResult, Feedback


def test_write_analysis(tmp_path) -> None:
    path = tmp_path / "results.jsonl"
    emitter = JsonlEmitter({"path": str(path)})
    result = AnalysisResult(instruction_count=5, severity="warning", density=12.3)

    emitter.write_analysis(result)

    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["type"] == "analysis"
    assert record["data"]["instruction_count"] == 5
    assert record["data"]["severity"] == "warning"


def test_write_feedback(tmp_path) -> None:
    path = tmp_path / "results.jsonl"
    emitter = JsonlEmitter({"path": str(path)})

    emitter.write_feedback(Feedback(analysis_id="abc-123", rating="bad", note="wrong count"))

    lines = path.read_text(encoding="utf-8").strip().split("\n")
    record = json.loads(lines[0])
    assert record["type"] == "feedback"
    assert record["data"]["rating"] == "bad"


def test_multiple_writes_append(tmp_path) -> None:
    path = tmp_path / "results.jsonl"
    emitter = JsonlEmitter({"path": str(path)})

    emitter.write_analysis(AnalysisResult(instruction_count=1))
    emitter.write_analysis(AnalysisResult(instruction_count=2))
    emitter.write_feedback(Feedback(analysis_id="test", rating="good"))

    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3


def test_creates_parent_directories(tmp_path) -> None:
    path = tmp_path / "deep" / "nested" / "results.jsonl"
    emitter = JsonlEmitter({"path": str(path)})

    emitter.write_analysis(AnalysisResult())

    assert path.exists()


def test_default_path(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    emitter = JsonlEmitter({"type": "jsonl"})

    emitter.write_analysis(AnalysisResult())

    assert (tmp_path / "promptlint-results.jsonl").exists()


def test_empty_result(tmp_path) -> None:
    path = tmp_path / "results.jsonl"
    emitter = JsonlEmitter({"path": str(path)})

    emitter.write_analysis(AnalysisResult())

    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["data"]["instruction_count"] == 0
    assert record["data"]["severity"] == "ok"
