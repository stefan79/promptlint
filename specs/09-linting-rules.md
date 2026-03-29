# 09 — Linting Rules Engine

> Status: **Draft — open questions below**

## Goal

Define a configurable rules engine that evaluates pipeline metrics and produces
a lint verdict (PASS, WARN, NO_PASS). This decouples metric computation
(pipeline) from policy decisions (what's acceptable for a given project/team).

Currently, the scorer stage in spec 01 assigns severity based on hardcoded
thresholds. This spec replaces that with user-defined rules that can vary per
project, per pipeline, or per prompt source.

## Concepts

### Verdict

Every lint run produces a verdict:

| Verdict | Meaning |
|---------|---------|
| **PASS** | Prompt meets all rules |
| **WARN** | Prompt violates soft rules — advisory only |
| **NO_PASS** | Prompt violates hard rules — should be blocked/rejected |

### Rule

A rule evaluates a single condition against pipeline metrics:

```yaml
rules:
  max-instructions:
    metric: instruction_count
    warn: 80
    fail: 150

  max-density:
    metric: density
    warn: 60.0
    fail: 90.0

  no-contradictions:
    metric: contradiction_count
    fail: 1        # any contradiction is a failure

  max-redundancy:
    metric: redundancy_ratio
    warn: 0.3
    fail: 0.5
```

### Rule evaluation

- Each rule compares a metric value against thresholds
- `fail` threshold → NO_PASS
- `warn` threshold → WARN
- Neither exceeded → PASS
- Final verdict = worst individual result (NO_PASS > WARN > PASS)

### Rulesets

A named collection of rules. Projects can define multiple rulesets for different
contexts (e.g., strict for production, relaxed for development):

```yaml
rulesets:
  default:
    rules:
      max-instructions:
        metric: instruction_count
        warn: 80
        fail: 150
      no-contradictions:
        metric: contradiction_count
        fail: 1

  strict:
    extends: default
    rules:
      max-instructions:
        warn: 40
        fail: 80
      max-density:
        metric: density
        warn: 30.0
        fail: 60.0

  ci:
    extends: default
    # Same as default but used in CI context
```

## Available metrics

Metrics produced by the pipeline that rules can reference:

| Metric | Type | Description |
|--------|------|-------------|
| `instruction_count` | int | Total instructions detected |
| `unique_instruction_count` | int | After deduplication |
| `density` | float | Instructions per 1K tokens |
| `redundancy_ratio` | float | 0.0–1.0, fraction of redundant instructions |
| `contradiction_count` | int | Number of contradiction pairs |
| `redundant_group_count` | int | Number of redundancy clusters |

## Interface

```python
@dataclass
class RuleResult:
    rule_name: str
    metric: str
    value: float
    verdict: str          # "pass" | "warn" | "no_pass"
    threshold: float | None  # the threshold that was exceeded, if any

@dataclass
class LintVerdict:
    verdict: str          # "pass" | "warn" | "no_pass"
    rules: list[RuleResult]
    summary: str          # human-readable one-liner
```

## Consumers

The verdict is consumed by:

| Consumer | Behavior |
|----------|----------|
| **CLI `check`** | Exit code 0 (PASS), 1 (WARN with `--fail-on warn`), 1 (NO_PASS) |
| **CLI `analyze`** | Display verdict in output |
| **Gateway** | Block request on NO_PASS (if gateway supports blocking) |
| **Emitters** | Write verdict alongside metrics |
| **CI** | Non-zero exit on NO_PASS |

## Relationship to existing code

- **Replaces**: the hardcoded severity logic in `scorer.py`
- **Extends**: `AnalysisResult` gets a `verdict: LintVerdict` field
- **Config**: rules live in `promptlint.yaml` (spec 06), with CLI flag overrides
  for simple cases (`--warn-instructions 80 --fail-instructions 150`)

## Open questions

1. **Custom rules** — should users be able to define rules beyond simple
   threshold comparisons? (e.g., "fail if contradiction_count > 0 AND
   instruction_count > 100"). Or is simple threshold-per-metric sufficient?

2. **Per-source rules** — should rules vary based on prompt source
   (e.g., stricter for system prompts, relaxed for tool results)?

3. **Rule inheritance** — `extends` keyword for rulesets. How deep can
   inheritance go? Allow only single-level, or support chains?

4. **Default ruleset** — should promptlint ship with a default ruleset
   baked in (the current thresholds), or require explicit configuration?

5. **Verdict naming** — PASS/WARN/NO_PASS vs pass/warning/critical
   (current severity naming). Should we keep backward compatibility with
   the existing severity field or clean-break?

6. **Integration with spec 04** — the gateway reads the verdict to decide
   blocking. Should the gateway config reference a ruleset by name, or
   just act on whatever verdict the pipeline produces?
