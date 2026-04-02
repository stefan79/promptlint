"""OrchestratorEnvelope and prompt fingerprinting."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from promptlint.models import ClassifiedChunk
    from promptlint.orchestrators import DetectedContext


EMPTY_FINGERPRINT = "0" * 16


@dataclass
class OrchestratorEnvelope:
    """Links orchestrator context to an AnalysisResult without polluting it."""

    analysis_id: str
    orchestrator_name: str
    detected_skills: list[str] = field(default_factory=list)
    detected_tools: list[str] = field(default_factory=list)
    detected_agents: list[str] = field(default_factory=list)
    prompt_fingerprint: str = EMPTY_FINGERPRINT
    request_id: str | None = None
    model_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())


def compute_fingerprint(instructions: list[ClassifiedChunk]) -> str:
    """Compute order-independent fingerprint from normalized instruction texts."""
    if not instructions:
        return EMPTY_FINGERPRINT
    texts = sorted(" ".join(chunk.text.lower().split()) for chunk in instructions)
    joined = "\n".join(texts)
    return hashlib.sha256(joined.encode()).hexdigest()[:16]


def build_envelope(
    analysis_id: str,
    context: DetectedContext,
    instructions: list[ClassifiedChunk],
    model_id: str | None = None,
) -> OrchestratorEnvelope:
    """Construct an OrchestratorEnvelope from detection results and analysis."""
    return OrchestratorEnvelope(
        analysis_id=analysis_id,
        orchestrator_name=context.orchestrator_name,
        detected_skills=[s.name for s in context.skills],
        detected_tools=[t.name for t in context.tools],
        detected_agents=[a.name for a in context.agents],
        prompt_fingerprint=compute_fingerprint(instructions),
        request_id=context.request_id,
        model_id=model_id,
    )
