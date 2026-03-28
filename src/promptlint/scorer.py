"""Stage 6: Metric aggregation and severity scoring."""

from __future__ import annotations

from collections import defaultdict

import tiktoken

from promptlint.config import Config
from promptlint.models import AnalysisResult, ClassifiedChunk, Contradiction, RedundancyGroup


def score(
    instructions: list[ClassifiedChunk],
    non_instructions: list[ClassifiedChunk],
    redundancy_groups: list[RedundancyGroup],
    contradictions: list[Contradiction],
    all_chunks: list[ClassifiedChunk],
    original_text: str,
    config: Config,
) -> AnalysisResult:
    """Aggregate analysis results into a single scored result."""
    instruction_count = len(instructions)
    total_duplicates = sum(len(g.duplicates) for g in redundancy_groups)
    unique_instruction_count = instruction_count - total_duplicates
    redundancy_ratio = 1 - (unique_instruction_count / instruction_count) if instruction_count > 0 else 0.0

    # Token counting for density
    enc = tiktoken.get_encoding("cl100k_base")
    total_tokens = len(enc.encode(original_text))
    density = (instruction_count / (total_tokens / 1000)) if total_tokens > 0 else 0.0

    # Section distribution
    section_distribution: dict[str, int] = defaultdict(int)
    for inst in instructions:
        section_distribution[inst.source_section] += 1

    # Section density (tokens per section approximated from chunk offsets)
    section_texts: dict[str, str] = defaultdict(str)
    for ch in all_chunks:
        section_texts[ch.source_section] += " " + ch.text
    section_density: dict[str, float] = {}
    for section, text in section_texts.items():
        section_tokens = len(enc.encode(text))
        section_inst_count = section_distribution.get(section, 0)
        section_density[section] = (section_inst_count / (section_tokens / 1000)) if section_tokens > 0 else 0.0

    # Severity and warnings
    contradiction_count = len(contradictions)
    warnings: list[str] = []
    severity = _compute_severity(instruction_count, density, contradiction_count, config, warnings)

    return AnalysisResult(
        instruction_count=instruction_count,
        unique_instruction_count=unique_instruction_count,
        non_instruction_count=len(non_instructions),
        total_chunks=len(all_chunks),
        density=density,
        redundancy_ratio=redundancy_ratio,
        instructions=instructions,
        non_instructions=non_instructions,
        redundant_groups=redundancy_groups,
        contradictions=contradictions,
        section_distribution=dict(section_distribution),
        section_density=section_density,
        warnings=warnings,
        severity=severity,
    )


def _compute_severity(
    instruction_count: int,
    density: float,
    contradiction_count: int,
    config: Config,
    warnings: list[str],
) -> str:
    """Determine severity level and populate warnings list."""
    severity = "ok"

    # Instruction count
    if instruction_count > config.critical_instructions:
        severity = "critical"
        warnings.append(
            f"Instruction count ({instruction_count}) exceeds critical threshold ({config.critical_instructions}). "
            f"At 95% per-instruction accuracy, P(all followed) ≈ {0.95 ** instruction_count:.6f}."
        )
    elif instruction_count >= config.warn_instructions:
        severity = max(severity, "warning", key=lambda s: {"ok": 0, "warning": 1, "critical": 2}[s])
        warnings.append(
            f"Instruction count ({instruction_count}) exceeds warning threshold ({config.warn_instructions})."
        )

    # Density
    if density > config.critical_density:
        severity = "critical"
        warnings.append(f"Instruction density ({density:.1f}/1K tokens) exceeds critical threshold ({config.critical_density}).")
    elif density >= config.warn_density:
        severity = max(severity, "warning", key=lambda s: {"ok": 0, "warning": 1, "critical": 2}[s])
        warnings.append(f"Instruction density ({density:.1f}/1K tokens) exceeds warning threshold ({config.warn_density}).")

    # Contradictions
    if contradiction_count > config.critical_contradictions:
        severity = "critical"
        warnings.append(f"Found {contradiction_count} contradictions (critical threshold: {config.critical_contradictions}).")
    elif contradiction_count >= config.warn_contradictions:
        severity = max(severity, "warning", key=lambda s: {"ok": 0, "warning": 1, "critical": 2}[s])
        warnings.append(f"Found {contradiction_count} contradiction(s).")

    return severity
