# Spec 10 — Positional Attention Risk ("Lost in the Middle")

Status: Draft

## Motivation

LLMs exhibit reduced attention to content in the middle of long contexts — the
"lost in the middle" phenomenon (Liu et al., 2023). Instructions placed in the
low-attention zone are more likely to be ignored, leading to silent failures
that are hard to diagnose.

promptlint already detects *what* instructions exist (classifier) and *whether*
they conflict (contradiction detector). This spec adds *where* instructions sit
in the attention curve, flagging those at highest risk of being overlooked.

## Goals

1. Score each instruction by its relative position in the assembled prompt
2. Flag instructions in the low-attention zone (middle ~40-60% of token span)
3. Produce a per-prompt "positional risk" metric: how many instructions are in
   the danger zone vs. well-placed (beginning/end)
4. Integrate with orchestrator context (spec 05) to attribute positional risk
   to specific skills/tools — e.g., "skill X always injects its instructions
   in the middle"

## Non-goals

- Reordering instructions automatically (that's the orchestrator's job)
- Modeling actual transformer attention patterns (we use a heuristic curve)
- Token-level analysis (we work at instruction/chunk granularity)

## Design

### Attention heuristic

Use a U-shaped positional weight curve:

```
weight(pos) = 1.0 - α * sin(π * pos / total_length)
```

Where `α` controls the depth of the attention trough (default 0.5). Instructions
near position 0 or `total_length` get weight ~1.0; instructions at
`total_length / 2` get weight ~0.5.

### Pipeline integration

New pipeline stage or scorer enhancement:

- Input: `ClassifiedChunk[]` with character/token offsets
- Output: each instruction annotated with `positional_risk: float` (0.0 = safe,
  1.0 = maximum risk)
- Aggregate metric: `positional_risk_score` = mean risk of all instructions
- High-risk count: number of instructions with risk > threshold (default 0.6)

### AnalysisResult fields

```python
positional_risk_score: float    # mean positional risk across instructions
high_risk_instruction_count: int  # instructions in the danger zone
```

### Severity contribution

- `high_risk_instruction_count > 3` → bump severity by one level
- `positional_risk_score > 0.7` → emit warning

## Open questions

1. Should the attention curve be configurable per model family? (Some models
   handle middle content better than others)
2. Should we weight by instruction importance (imperative > informational)?
3. Integration with spec 09 (linting rules) — should positional risk be a
   built-in rule or a custom rule?

## Dependencies

- Spec 01 (core pipeline) — classifier output with offsets
- Spec 05 (orchestrator support) — skill attribution for per-skill reporting
- Spec 09 (linting rules) — optional rule integration
