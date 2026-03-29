"""Tests for emitter factory and env var resolution."""

from __future__ import annotations

import pytest

from promptlint.emitters import _resolve_env_vars, create_emitter
from promptlint.emitters.jsonl import JsonlEmitter
from promptlint.emitters.sqlite import SqliteEmitter


def test_create_jsonl_emitter(tmp_path) -> None:
    emitter = create_emitter({"type": "jsonl", "path": str(tmp_path / "out.jsonl")})
    assert isinstance(emitter, JsonlEmitter)


def test_create_sqlite_emitter(tmp_path) -> None:
    emitter = create_emitter({"type": "sqlite", "path": str(tmp_path / "test.db")})
    assert isinstance(emitter, SqliteEmitter)


def test_unknown_type_raises() -> None:
    with pytest.raises(ValueError, match="Unknown backend type 'redis'"):
        create_emitter({"type": "redis"})


def test_resolve_env_vars(monkeypatch) -> None:
    monkeypatch.setenv("MY_SECRET", "s3cret")
    result = _resolve_env_vars({"auth": "${MY_SECRET}", "port": 9200})
    assert result["auth"] == "s3cret"
    assert result["port"] == 9200


def test_resolve_env_vars_missing_keeps_original() -> None:
    result = _resolve_env_vars({"auth": "${NONEXISTENT_VAR}"})
    assert result["auth"] == "${NONEXISTENT_VAR}"


def test_all_builtin_types_registered() -> None:
    for backend_type in ("jsonl", "elasticsearch", "prometheus", "sqlite", "webhook"):
        from promptlint.emitters import _EMITTER_FACTORIES

        assert backend_type in _EMITTER_FACTORIES, f"Missing registration for {backend_type}"
