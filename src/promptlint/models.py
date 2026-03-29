"""Dataclasses for the promptlint analysis pipeline."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


class PromptLintError(Exception):
    """Raised when prompt analysis exceeds configured severity thresholds."""


@dataclass
class Chunk:
    text: str
    source_section: str
    start_offset: int
    end_offset: int
    structural_type: str  # "bullet", "paragraph", "xml_block", "tool_desc", "header_content"


@dataclass
class ClassifiedChunk(Chunk):
    label: str = ""  # "instruction" or "non_instruction"
    confidence: float = 0.0


@dataclass
class RedundancyGroup:
    canonical: ClassifiedChunk
    duplicates: list[ClassifiedChunk] = field(default_factory=list)
    similarity: float = 0.0


@dataclass
class Contradiction:
    instruction_a: ClassifiedChunk
    instruction_b: ClassifiedChunk
    score: float = 0.0
    direction: str = "bidirectional"  # "a_contradicts_b", "b_contradicts_a", or "bidirectional"


@dataclass
class Feedback:
    analysis_id: str
    rating: str  # "good" | "bad"
    corrections: list[str] = field(default_factory=list)
    note: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())


@dataclass
class AnalysisResult:
    # Counts
    instruction_count: int = 0
    unique_instruction_count: int = 0
    non_instruction_count: int = 0
    total_chunks: int = 0

    # Rates
    density: float = 0.0
    redundancy_ratio: float = 0.0

    # Detail
    instructions: list[ClassifiedChunk] = field(default_factory=list)
    non_instructions: list[ClassifiedChunk] = field(default_factory=list)
    redundant_groups: list[RedundancyGroup] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)

    # Section breakdown
    section_distribution: dict[str, int] = field(default_factory=dict)
    section_density: dict[str, float] = field(default_factory=dict)

    # Governance
    warnings: list[str] = field(default_factory=list)
    severity: str = "ok"

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    def to_markdown(self) -> str:
        lines = [
            "# Promptlint Analysis Report",
            "",
            f"**Severity:** {self.severity.upper()}",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Instructions (total) | {self.instruction_count} |",
            f"| Instructions (unique) | {self.unique_instruction_count} |",
            f"| Redundancy ratio | {self.redundancy_ratio:.1%} |",
            f"| Contradictions | {len(self.contradictions)} |",
            f"| Density (per 1K tokens) | {self.density:.1f} |",
            "",
        ]

        if self.section_distribution:
            lines.append("## Section Breakdown")
            lines.append("")
            lines.append("| Section | Instructions | % |")
            lines.append("|---------|-------------|---|")
            for section, count in sorted(self.section_distribution.items(), key=lambda x: -x[1]):
                pct = (count / self.instruction_count * 100) if self.instruction_count else 0
                lines.append(f"| {section} | {count} | {pct:.1f}% |")
            lines.append("")

        if self.redundant_groups:
            lines.append("## Redundancy Groups")
            lines.append("")
            for i, group in enumerate(self.redundant_groups, 1):
                texts = [f'"{group.canonical.text}"'] + [f'"{d.text}"' for d in group.duplicates]
                lines.append(f"{i}. {' ≈ '.join(texts)} ({len(group.duplicates) + 1} instances)")
            lines.append("")

        if self.contradictions:
            lines.append("## Contradictions")
            lines.append("")
            for i, c in enumerate(self.contradictions, 1):
                lines.append(f'{i}. [{c.score:.2f}] "{c.instruction_a.text}" ↔ "{c.instruction_b.text}"')
                lines.append(f"   {c.instruction_a.source_section} ↔ {c.instruction_b.source_section}")
            lines.append("")

        if self.warnings:
            lines.append("## Warnings")
            lines.append("")
            for w in self.warnings:
                lines.append(f"- {w}")
            lines.append("")

        return "\n".join(lines)

    def raise_if(self, severity: str = "critical") -> None:
        severity_order = {"ok": 0, "warning": 1, "critical": 2}
        if severity_order.get(self.severity, 0) >= severity_order.get(severity, 0):
            raise PromptLintError(
                f"Prompt severity is {self.severity}: "
                f"{self.instruction_count} instructions, "
                f"density {self.density:.1f}, "
                f"{len(self.contradictions)} contradictions"
            )
