# 08 — Orchestrator Plugins (Active Instrumentation)

> Status: **Draft — open questions below**

## Goal

Spec 05 covers **passive observation** — parsing orchestrator conventions from
the gateway wire format. This spec covers **active instrumentation**: installing
hooks, skills, or plugins directly into the orchestrator so it explicitly tags
instructions with provenance, reports its version, and exposes a feedback
surface to the user.

Active instrumentation gives us what passive observation cannot: clean
attribution, orchestrator version, and a user-facing feedback command.

## Why separate from spec 05

| Concern | Spec 05 (passive) | Spec 08 (active) |
|---------|-------------------|-------------------|
| Deployment | Zero-install, gateway-only | Requires per-orchestrator setup |
| Attribution | Heuristic (parse tags, infer skill names) | Explicit (orchestrator tags each source) |
| Orchestrator version | Not available on the wire | Injected by plugin |
| Feedback | External CLI (`promptlint feedback <id>`) | In-orchestrator command (e.g. `/promptlint-feedback`) |
| Prompt fingerprint | Computed by promptlint | Can include orchestrator-side hash |

Both modes should work together — passive provides the baseline, active
enriches it.

## Claude Code plugin

### Installation

Claude Code supports hooks (shell commands on events) and skills (markdown
files with tool access). The plugin is a combination:

```
~/.claude/skills/promptlint/
├── SKILL.md              # user-invocable /promptlint-feedback skill
└── hooks.json            # hook config to inject into .claude/settings.json
```

Or project-level:

```
.claude/skills/promptlint/
├── SKILL.md
└── ...
```

### Hook: prompt tagging

Claude Code hooks fire on events like `PreToolUse`, `PostToolUse`,
`Notification`. We use a **`PreToolUse` hook on all tool calls** or a
**custom `UserPromptSubmit` hook** to inject a provenance header into the
request before it hits the API.

However, hooks cannot modify the API payload directly — they can only
approve/block tool calls or run side-effects. So the tagging approach is:

**Option 1: Sidecar annotation file**

The hook writes a sidecar file (e.g. `/tmp/promptlint-context.json`) with
the current orchestrator state before each API call:

```json
{
  "orchestrator": "claude-code",
  "version": "1.0.34",
  "active_skills": ["commit", "review-pr", "simplify"],
  "active_tools": ["Read", "Edit", "Bash", "Grep", "Glob"],
  "active_agents": [],
  "session_id": "abc123",
  "timestamp": "2026-03-28T14:30:00Z"
}
```

The gateway reads this file to enrich `MessageRecord` with provenance.
Works because gateway and orchestrator run on the same machine.

**Option 2: Custom HTTP header**

If Claude Code supports custom headers (via `ANTHROPIC_EXTRA_HEADERS` or
similar env var), inject an `X-Promptlint-Context` header with the
orchestrator state. The gateway reads it without needing filesystem access.

**Option 3: Prepend to user message**

The hook prepends a `<promptlint-context>` XML block to the user message
content. The gateway strips it before forwarding. Hacky but works with any
gateway.

### Skill: feedback command

A Claude Code skill that lets the user give feedback inline:

```yaml
---
name: promptlint-feedback
description: Give feedback on the last prompt analysis
user-invocable: true
allowed-tools: Bash
---

When the user invokes /promptlint-feedback, run:

    promptlint feedback last --rating $ARGUMENTS

If no arguments, ask for:
- Rating: good / bad
- Optional note explaining why

Show the analysis summary and confirm feedback was recorded.
```

Usage in Claude Code:
```
> /promptlint-feedback bad "false positive contradiction between logging rules"
```

### Skill: analysis on demand

```yaml
---
name: promptlint-analyze
description: Analyze the current prompt for instruction bloat
user-invocable: true
allowed-tools: Bash
---

Run `promptlint analyze --format terminal` on the current conversation's
assembled prompt. If the gateway is running, fetch the latest analysis via
`promptlint show last`. Otherwise, note that the gateway must be active.
```

## Codex CLI plugin

Codex CLI's extension model is less mature. Options:

### Wrapper script

A shell wrapper around `codex` that:
1. Sets `OPENAI_BASE_URL` to point through the promptlint gateway
2. Writes orchestrator context to the sidecar file
3. Invokes `codex` with all original arguments

```bash
#!/bin/bash
# promptlint-codex wrapper
export OPENAI_BASE_URL="http://localhost:8100/v1"

# Write context sidecar
cat > /tmp/promptlint-context.json << EOF
{
  "orchestrator": "codex-cli",
  "version": "$(codex --version 2>/dev/null || echo unknown)",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

exec codex "$@"
```

### Feedback via standalone CLI

Since Codex doesn't have a skill system, feedback is via the standalone
`promptlint feedback` command in a separate terminal.

## Generic agent framework plugin

For LangChain, CrewAI, AutoGen, etc. — provide a Python callback:

```python
from promptlint.plugins import PromptLintCallback

callback = PromptLintCallback(
    orchestrator="langchain",
    version="0.3.1",
    gateway_url="http://localhost:8100",
)

# LangChain
chain = LLMChain(..., callbacks=[callback])

# CrewAI
crew = Crew(..., callbacks=[callback])
```

The callback:
1. Intercepts the assembled prompt before the LLM call
2. Writes orchestrator context (active tools, agent name, etc.)
3. Forwards to the gateway or runs the pipeline directly
4. Exposes `callback.last_analysis` for programmatic feedback

## Wire protocol: orchestrator → promptlint

Whether via sidecar file, HTTP header, or XML block, the context payload
is the same:

```python
@dataclass
class OrchestratorContext:
    orchestrator: str              # "claude-code", "codex-cli", "langchain"
    version: str                   # orchestrator version
    session_id: str                # conversation/session identifier
    active_skills: list[str]       # currently loaded skill names
    active_tools: list[str]        # available tool names
    active_agents: list[str]       # running subagent names/types
    timestamp: datetime

    # Optional enrichment
    skill_instruction_counts: dict[str, int]  # skill_name → instruction count
    prompt_hash: str | None        # orchestrator-computed fingerprint
```

## Interaction with other specs

| Spec | Interaction |
|------|------------|
| **04 Gateway** | Gateway reads OrchestratorContext from sidecar/header/XML. Enriches MessageRecord. |
| **05 Passive orchestrator** | Active context supplements heuristic parsing. When both available, active wins. |
| **03 Backends** | Feedback writes through emitters. OrchestratorContext fields added to AnalysisPayload. |
| **06 Config** | `orchestrator.plugin` section configures which mechanism (sidecar/header/XML) and paths. |

## Open questions

1. **Sidecar vs header vs XML** — which mechanism for Claude Code? Sidecar is
   cleanest but assumes co-located processes. Header requires env var support.
   XML is universal but pollutes the prompt.

2. **Hook limitations** — Claude Code hooks can't modify API payloads. Is
   the sidecar file approach reliable enough (race conditions between hook
   write and gateway read)?

3. **Skill installation UX** — should `promptlint install claude-code` copy
   the skill files and configure hooks automatically? Or manual setup with
   docs?

4. **Codex prompt format** — need to reverse-engineer how Codex assembles
   its system prompt, tools, and user messages. Is the format stable?

5. **Feedback aggregation** — when feedback accumulates, how does it flow back
   to threshold calibration? Manual review, or automated adjustment?

6. **Session tracking** — should the plugin track analysis across a full
   session (multiple API calls) and report session-level metrics (total
   instructions seen, drift over conversation)?
