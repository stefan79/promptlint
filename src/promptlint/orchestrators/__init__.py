"""Orchestrator adapters for passive detection of orchestrator patterns in LLM API traffic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from promptlint.gateways.normalizer import NormalizedRequest


@dataclass
class SkillInfo:
    name: str
    source: str = "passive"  # "passive" or "active" (spec 08)


@dataclass
class ToolInfo:
    name: str
    param_count: int = 0


@dataclass
class AgentInfo:
    name: str
    agent_type: str = ""


@dataclass
class DetectedContext:
    orchestrator_name: str  # "claude-code", "generic", "unknown"
    skills: list[SkillInfo] = field(default_factory=list)
    tools: list[ToolInfo] = field(default_factory=list)
    agents: list[AgentInfo] = field(default_factory=list)
    system_prompt_source: str = ""  # "body.system", "messages[0]", "configurable"
    request_id: str | None = None


@runtime_checkable
class OrchestratorAdapter(Protocol):
    name: str

    def detect(self, request: NormalizedRequest) -> DetectedContext | None: ...


_ADAPTERS: list[OrchestratorAdapter] = []


def register_adapter(adapter: OrchestratorAdapter) -> None:
    """Register an orchestrator adapter. First match wins during detection."""
    _ADAPTERS.append(adapter)


def clear_adapters() -> None:
    """Remove all registered adapters (for testing)."""
    _ADAPTERS.clear()


def get_adapters() -> list[OrchestratorAdapter]:
    """Return the current adapter registry (read-only copy)."""
    return list(_ADAPTERS)


def detect(request: NormalizedRequest) -> DetectedContext:
    """Run registered adapters in order; return first match or unknown context."""
    for adapter in _ADAPTERS:
        ctx = adapter.detect(request)
        if ctx is not None:
            return ctx
    return DetectedContext(orchestrator_name="unknown")


def register_default_adapters() -> None:
    """Register the built-in adapters if not already present."""
    from promptlint.orchestrators.claude_code import ClaudeCodeAdapter
    from promptlint.orchestrators.generic import GenericAdapter

    registered_names = {a.name for a in _ADAPTERS}
    if "claude-code" not in registered_names:
        _ADAPTERS.insert(0, ClaudeCodeAdapter())
    if "generic" not in registered_names:
        _ADAPTERS.append(GenericAdapter())
