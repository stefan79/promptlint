"""SQLite emitter — local structured queries without a server."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from promptlint.models import AnalysisResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    severity TEXT NOT NULL,
    instruction_count INTEGER NOT NULL,
    density REAL NOT NULL,
    contradiction_count INTEGER NOT NULL,
    redundancy_ratio REAL NOT NULL,
    data TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class SqliteEmitter:
    """Writes analysis results and feedback to a SQLite database."""

    def __init__(self, config: dict) -> None:
        self._db_path = config.get("path", "promptlint.db")
        self._conn = sqlite3.connect(self._db_path)
        self._conn.executescript(_SCHEMA)

    def write_analysis(self, result: AnalysisResult) -> None:
        data = asdict(result)
        self._conn.execute(
            "INSERT INTO analyses (severity, instruction_count, density, contradiction_count, redundancy_ratio, data) VALUES (?, ?, ?, ?, ?, ?)",
            (
                result.severity,
                result.instruction_count,
                result.density,
                len(result.contradictions),
                result.redundancy_ratio,
                json.dumps(data, default=str),
            ),
        )
        self._conn.commit()

    def write_feedback(self, feedback: dict) -> None:
        self._conn.execute(
            "INSERT INTO feedback (data) VALUES (?)",
            (json.dumps(feedback, default=str),),
        )
        self._conn.commit()
