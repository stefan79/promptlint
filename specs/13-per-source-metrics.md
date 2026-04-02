# Spec 13 — Per-Source Metrics Breakdown

Status: Draft

## Motivation

promptlint currently produces metrics for the entire assembled prompt. But
orchestrators build prompts from distinct sources: system prompt, skills, tools,
agent instructions, and user messages. Knowing *where* problems come from is
essential for fixing them.

A contradiction in the system prompt is a different fix than a contradiction
between two skills, which is different from a user message contradicting a tool
definition. Per-source metrics enable targeted debugging and attribution.

## Goals

1. Break down all existing metrics by source attribution:
   - System prompt
   - Per-skill (e.g., `code-review`, `simplify`)
   - Per-tool definition
   - Per-agent instruction
   - User messages
2. Cross-source analysis: detect contradictions and redundancy *between* sources
   (e.g., skill A vs. skill B, system prompt vs. tool definition)
3. Per-source complexity scores and instruction counts
4. Identify which source contributes most to prompt bloat

## Design sketch

### Pipeline extension

After the existing pipeline produces whole-prompt metrics, a new stage maps
each instruction/chunk back to its source (using orchestrator attribution from
spec 05) and re-aggregates:

```python
@dataclass
class SourceMetrics:
    source_type: str          # "system", "skill", "tool", "agent", "user"
    source_name: str | None   # e.g., "code-review", "Read", None for system
    instruction_count: int
    redundancy_groups: int
    contradictions: int
    complexity_score: float
```

### Cross-source findings

```python
@dataclass
class CrossSourceFinding:
    finding_type: str         # "contradiction" | "redundancy"
    source_a: str
    source_b: str
    details: list[str]        # the conflicting/redundant instructions
```

### AnalysisResult extension

```python
source_metrics: list[SourceMetrics]
cross_source_findings: list[CrossSourceFinding]
```

## Dependencies

- Spec 05 (orchestrator support) — source attribution for chunks/instructions
- Spec 01 (core pipeline) — existing metrics to break down
- Spec 09 (linting rules) — optional per-source rules (e.g., "no skill may
  exceed 10 instructions")
