# 05 — Orchestrator Support (Passive Observation)

> Status: **Draft — open questions below**
>
> See also: [spec 08 — Orchestrator Plugins](08-orchestrator-plugins.md) for
> **active instrumentation** (hooks, skills, explicit tagging). This spec
> covers **passive observation** only — parsing what's visible on the wire
> without installing anything in the orchestrator.

## Goal

Enable promptlint to understand orchestrator-level concerns from gateway
traffic alone: detect skills, identify prompt structure, and emit enriched
datasets. No orchestrator modification required.

Target orchestrators: **Claude Code**, **Codex CLI**, and generic
agent frameworks.

## Core capabilities

### 1. Skill detection

Orchestrators like Claude Code dynamically assemble prompts from skills,
tools, constitutions, and system instructions. promptlint should:

- Parse skill boundaries from `<system-reminder>` tags, XML blocks, or
  markdown sections injected by the orchestrator.
- Label each instruction with its **source skill** (e.g. "commit skill",
  "review-pr skill", "base system prompt").
- Detect skill-to-skill redundancy and contradiction (cross-skill analysis).

### 2. Prompt identification

- Fingerprint assembled prompts (hash of normalized instruction set) so
  repeated invocations of the same prompt can be grouped.
- Track prompt **drift** over time (skills added/removed, instruction count
  changes).
- Correlate prompt fingerprints with outcomes (if feedback is available).

### 3. Feedback loop

- Accept human feedback on analysis results:
  - "This was actually not a contradiction" (false positive)
  - "This instruction was important but got buried" (attention signal)
  - "This prompt worked well / poorly" (outcome signal)
- Store feedback linked to prompt fingerprint + analysis result.
- Use accumulated feedback to calibrate thresholds over time.

### 4. Dataset emission

- Emit structured datasets (JSONL) containing:
  - Assembled prompt (full text + structured breakdown)
  - Analysis results (instructions, redundancy groups, contradictions)
  - Human feedback (if any)
  - Metadata (orchestrator, model, timestamp, prompt fingerprint)
- Datasets can feed into:
  - Prompt optimization pipelines
  - Fine-tuning data curation
  - Observability dashboards (via storage backends from spec 03)

## Passive detection strategies

What we can infer from the wire without orchestrator cooperation:

### Claude Code

| Signal | Detection method | Reliability |
|--------|-----------------|-------------|
| Skill invocation | `tool_use` with `name == "Skill"`, skill name in `input.skill` | High |
| Skill content | `tool_result` following Skill call contains full SKILL.md | High |
| Agent launch | `tool_use` with `name == "Agent"`, type in `input.subagent_type` | High |
| System reminders | Parse `<system-reminder>` tags from message content | High |
| Skill-to-instruction attribution | Heuristic: instructions in tool_result after Skill call belong to that skill | Medium |
| Base system prompt vs skills | System prompt is in `body["system"]`; skills arrive later via tool calls | Medium |
| Constitution | Usually in system prompt, no explicit marker | Low |

### Codex CLI

| Signal | Detection method | Reliability |
|--------|-----------------|-------------|
| System prompt | `messages[0]` where `role == "system"` | High |
| Tool definitions | `tools[]` array | High |
| Skill boundaries | TBD — Codex format not yet analyzed | Unknown |

### Generic agent frameworks

Configurable: user provides marker patterns (regex/xpath) in pipeline config.

## Orchestrator adapters

| Orchestrator | Skill marker | Prompt structure |
|-------------|-------------|-----------------|
| **Claude Code** | `Skill` tool calls, `<system-reminder>` tags | system + tools + skills (via tool calls) + user |
| **Codex CLI** | TBD | system (in messages) + tools + user |
| **Generic agent** | Configurable markers (regex/xpath) | Configurable |

## Limitations of passive mode

These require [spec 08 — active plugins](08-orchestrator-plugins.md):

- **Orchestrator version** — not in API payload
- **Exact instruction attribution** — which skill contributed which instruction in the system prompt
- **User feedback** — needs an in-orchestrator command
- **Session identity** — no session header on the wire

## Open questions

1. **Prompt fingerprinting** — hash the raw text, or hash the normalized
   instruction set (order-independent)? Raw text changes with every user
   message; instruction set is more stable.

2. **Dataset schema** — what fields are mandatory vs optional? Should we align
   with an existing format (HuggingFace datasets, JSONL conventions)?

3. **Privacy** — assembled prompts may contain user messages with PII.
   Redaction? Opt-in only for user message inclusion?

4. **Codex CLI** — how does Codex structure its prompts? Need to reverse-
   engineer or find docs. Is the prompt format stable enough to parse?

5. **Cross-skill analysis** — should this be a separate pipeline stage, or
   a post-processing step on top of the existing redundancy/contradiction
   detectors?

6. **Passive + active merge** — when spec 08 plugin provides explicit context,
   how does it override or supplement passive detection? Active wins on
   conflict, but do we keep both for comparison?
