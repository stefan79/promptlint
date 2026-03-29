"""Storage backend emitters for promptlint analysis results."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from promptlint.models import AnalysisResult


class Emitter(Protocol):
    """Protocol for storage backends."""

    def write_analysis(self, result: AnalysisResult) -> None: ...

    def write_feedback(self, feedback: dict) -> None: ...


_EMITTER_FACTORIES: dict[str, type] = {}


def register_emitter(name: str, cls: type) -> None:
    """Register an emitter class by type name."""
    _EMITTER_FACTORIES[name] = cls


def create_emitter(config: dict) -> Emitter:
    """Create an emitter from a backend config dict."""
    backend_type: str = config.get("type", "")
    if backend_type not in _EMITTER_FACTORIES:
        available = list(_EMITTER_FACTORIES)
        msg = f"Unknown backend type '{backend_type}'. Available: {available}"
        raise ValueError(msg)

    resolved = _resolve_env_vars(config)
    emitter: Emitter = _EMITTER_FACTORIES[backend_type](resolved)
    return emitter


def _resolve_env_vars(config: dict) -> dict:
    """Replace ${VAR} references with environment variable values."""
    result = {}

    def _expand(m: re.Match[str]) -> str:
        var_name: str = m.group(1)
        return os.environ.get(var_name, m.group(0))

    for key, value in config.items():
        if isinstance(value, str):
            result[key] = re.sub(r"\$\{(\w+)\}", _expand, value)
        else:
            result[key] = value
    return result


# Auto-register built-in emitters on import
from promptlint.emitters.elasticsearch import ElasticsearchEmitter  # noqa: E402
from promptlint.emitters.jsonl import JsonlEmitter  # noqa: E402
from promptlint.emitters.prometheus import PrometheusEmitter  # noqa: E402
from promptlint.emitters.sqlite import SqliteEmitter  # noqa: E402
from promptlint.emitters.webhook import WebhookEmitter  # noqa: E402

register_emitter("jsonl", JsonlEmitter)
register_emitter("elasticsearch", ElasticsearchEmitter)
register_emitter("prometheus", PrometheusEmitter)
register_emitter("sqlite", SqliteEmitter)
register_emitter("webhook", WebhookEmitter)
