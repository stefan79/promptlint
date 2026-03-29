"""Tests for SQLite emitter."""

from __future__ import annotations

import json
import sqlite3

from promptlint.emitters.sqlite import SqliteEmitter
from promptlint.models import AnalysisResult, Contradiction


def test_write_analysis(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")
    emitter = SqliteEmitter({"path": db_path})
    result = AnalysisResult(instruction_count=5, severity="warning", density=12.3)

    emitter.write_analysis(result)

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT severity, instruction_count, density, data FROM analyses").fetchone()
    assert row[0] == "warning"
    assert row[1] == 5
    assert abs(row[2] - 12.3) < 0.01
    data = json.loads(row[3])
    assert data["instruction_count"] == 5


def test_write_feedback(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")
    emitter = SqliteEmitter({"path": db_path})

    emitter.write_feedback({"analysis_id": "abc-123", "rating": "bad"})

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT data FROM feedback").fetchone()
    data = json.loads(row[0])
    assert data["rating"] == "bad"


def test_multiple_writes(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")
    emitter = SqliteEmitter({"path": db_path})

    emitter.write_analysis(AnalysisResult(instruction_count=1))
    emitter.write_analysis(AnalysisResult(instruction_count=2))

    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
    assert count == 2


def test_contradiction_count_stored(tmp_path, make_instruction) -> None:
    db_path = str(tmp_path / "test.db")
    emitter = SqliteEmitter({"path": db_path})
    result = AnalysisResult(
        instruction_count=4,
        contradictions=[
            Contradiction(
                instruction_a=make_instruction("Be concise"),
                instruction_b=make_instruction("Be verbose"),
                score=0.9,
            ),
        ],
    )

    emitter.write_analysis(result)

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT contradiction_count FROM analyses").fetchone()
    assert row[0] == 1


def test_empty_result(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")
    emitter = SqliteEmitter({"path": db_path})

    emitter.write_analysis(AnalysisResult())

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT severity, instruction_count FROM analyses").fetchone()
    assert row[0] == "ok"
    assert row[1] == 0
