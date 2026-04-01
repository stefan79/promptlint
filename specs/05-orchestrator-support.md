# 05 — Orchestrator Support (Passive Observation)

> Status: **Implemented**
>
> See also: [spec 08 — Orchestrator Plugins](08-orchestrator-plugins.md) for
> **active instrumentation** (hooks, skills, explicit tagging). This spec
> covers **passive observation** only — parsing what's visible on the wire
> without installing anything in the orchestrator.

## Goal

Enable promptlint to understand orchestrator-level concerns from gateway
traffic alone: detect which orchestrator is sending requests, identify skills
and tools, attribute chunks to their source, and compute a stable prompt
fingerprint. No orchestrator modification required.

Target orchestrators for this spec: **Claude Code** and **generic agent
frameworks** only. Codex CLI is deferred to [spec 11](11-orchestrator-codex-cli.md).

## Scope

**In scope:**
- Orchestrator detection (Claude Code vs generic)
- Skill/tool/agent detection from wire traffic
- Source attribution on chunks (which skill/section contributed each chunk)
- Prompt fingerprinting (order-independent hash of normalized instruction set)
- `OrchestratorEnvelope` type linking orchestrator context to analysis
- Request ID capture from LLM provider response headers

**Out of scope (deferred):**
- Cross-skill redundancy/contradiction analysis (spec 13 — Per-Source Metrics)
- Codex CLI adapter (spec 11)
- Active instrumentation / plugins (spec 08)
- Privacy filtering / PII redaction (include user messages by default)
- Prompt drift tracking over time (future work)
- Feedback loop calibration (future work)

## Data types

### DetectedContext

Produced by passive detection. Contains what we can infer from the wire.

```python
@dataclass
class DetectedContext:
    orchestrator_name: str          # "claude-code", "generic", "unknown"
    skills: list[SkillInfo]         # detected skill invocations
    tools: list[ToolInfo]           # detected tool definitions
    agents: list[AgentInfo]         # detected agent launches
    system_prompt_source: str       # "body.system", "messages[0]", "configurable"
    request_id: str | None = None   # from LLM provider response headers

@dataclass
class SkillInfo:
    name: str
    source: str = "passive"         # "passive" or "active" (spec 08)

@dataclass
class ToolInfo:
    name: str
    param_count: int = 0

@dataclass
class AgentInfo:
    name: str
    agent_type: str = ""            # e.g. "subagent", "parallel"
```

### OrchestratorEnvelope

Links orchestrator context to an AnalysisResult without polluting AnalysisResult
fields. One envelope per analysis.

```python
@dataclass
class OrchestratorEnvelope:
    analysis_id: str                # links to AnalysisResult (via external ID)
    orchestrator_name: str          # "claude-code", "generic", "unknown"
    detected_skills: list[str]      # skill names
    detected_tools: list[str]       # tool names
    detected_agents: list[str]      # agent names
    prompt_fingerprint: str         # SHA-256 truncated to 16 hex chars
    request_id: str | None = None   # from LLM provider response headers
    model_id: str | None = None     # from NormalizedRequest
    timestamp: str = ""             # ISO 8601
```

### Source attribution on Chunk

Chunks gain an optional `source` field for provenance tracking:

```python
@dataclass
class Chunk:
    text: str
    source_section: str
    start_offset: int
    end_offset: int
    structural_type: str
    source: str = ""                # "system", "skill:<name>", "tool:<name>", "user", ""
```

## Orchestrator adapter protocol

```python
class OrchestratorAdapter(Protocol):
    name: str

    def detect(self, request: NormalizedRequest) -> DetectedContext | None: ...
```

Each adapter inspects a `NormalizedRequest` and returns a `DetectedContext` if
it recognizes the orchestrator's patterns, or `None` if it does not match.

Adapters are tried in registration order. First match wins.

## Claude Code adapter

Detection signals (all from `NormalizedRequest.messages`):

| Signal | How to detect | What to extract |
|--------|--------------|-----------------|
| Skill invocation | `tool_call.name == "Skill"` | `tool_call.input["skill"]` as skill name |
| Agent launch | `tool_call.name == "Agent"` | `tool_call.input.get("subagent_type", "agent")` |
| System reminders | `<system-reminder>` tags in any message content | Content between tags (skill/context boundary) |
| System prompt | `NormalizedRequest.system_prompt` is not None | Source = "system" |
| Tool definitions | `NormalizedRequest.tools` list | Tool names and parameter counts |

Detection trigger: request matches Claude Code if any message contains a
`tool_call` with `name == "Skill"` or `name == "Agent"`, OR if any message
content contains `<system-reminder>` tags.

### Source attribution rules

1. System prompt content: `source = "system"`
2. Content inside `<system-reminder>` tags: `source = "system-reminder"`
3. Tool result content following a `Skill` tool call: `source = "skill:<name>"`
4. Tool result content following an `Agent` tool call: `source = "agent:<name>"`
5. User messages: `source = "user"`
6. Everything else: `source = ""`

## Generic adapter

Matches any request that no other adapter claims. Always returns a
`DetectedContext` with `orchestrator_name = "generic"`.

Extracts tools from `NormalizedRequest.tools` and sets
`system_prompt_source` based on vendor.

## Prompt fingerprinting

Compute a stable fingerprint from the normalized instruction set:

1. Collect all instruction texts from `AnalysisResult.instructions`
2. Normalize: lowercase, strip whitespace, collapse internal whitespace
3. Sort alphabetically
4. Join with newline separator
5. SHA-256 hash, truncate to first 16 hex characters

```python
def compute_fingerprint(instructions: list[ClassifiedChunk]) -> str:
    texts = sorted(
        " ".join(chunk.text.lower().split())
        for chunk in instructions
    )
    joined = "\n".join(texts)
    return hashlib.sha256(joined.encode()).hexdigest()[:16]
```

If no instructions are present, return `"0" * 16` (empty fingerprint).

## Request ID capture

When the gateway receives a response from the LLM provider, capture the
request ID from response headers:

- Anthropic: `request-id` header
- OpenAI: `x-request-id` header
- Gemini: `x-goog-request-id` header (if present)

Store in `DetectedContext.request_id` and `OrchestratorEnvelope.request_id`.

## Integration with gateway

The orchestrator detection runs inside the gateway after normalization, before
or after pipeline analysis:

```
raw_request → normalize → NormalizedRequest
                               │
                               ├──▶ OrchestratorAdapter.detect() → DetectedContext
                               │
                               └──▶ pipeline.analyze() → AnalysisResult
                                         │
                                         ▼
                              compute_fingerprint(result.instructions)
                                         │
                                         ▼
                              OrchestratorEnvelope(analysis_id, context, fingerprint)
```

The gateway is responsible for:
1. Running adapter detection on NormalizedRequest
2. Running the analysis pipeline
3. Computing the prompt fingerprint from analysis results
4. Constructing the OrchestratorEnvelope
5. Passing envelope alongside AnalysisResult to emitters (future: spec 03 extension)

For this spec, the envelope is logged. Emitter integration is future work.

## File organization

```
src/promptlint/orchestrators/
├── __init__.py          # OrchestratorAdapter protocol, detect(), SkillInfo/ToolInfo/AgentInfo
├── claude_code.py       # ClaudeCodeAdapter
├── generic.py           # GenericAdapter
├── envelope.py          # OrchestratorEnvelope, compute_fingerprint
```

## Testing strategy

Unit tests (fast, no ML models):
- `tests/test_orchestrator_claude_code.py`: Claude Code detection with various message patterns
- `tests/test_orchestrator_generic.py`: Generic adapter fallback behavior
- `tests/test_orchestrator_envelope.py`: Fingerprinting, envelope construction
- `tests/test_orchestrators_init.py`: Adapter registry, detection dispatch

Test cases per adapter:
- Happy path: typical Claude Code request with skills, tools, agents
- No skills: plain Anthropic request (should fall through to generic)
- Empty messages: request with no messages
- Mixed signals: request with system-reminder tags but no Skill tool calls
- Malformed tool calls: missing input fields, empty names
- Fingerprinting: same instructions in different order produce same hash
- Fingerprinting: empty instruction list produces zero hash

## Resolved decisions

1. **Prompt fingerprinting**: Hash normalized instruction set (order-independent,
   SHA-256 truncated to 16 hex). Also capture request ID from provider response
   headers as tracing metadata.

2. **Dataset schema**: Separate `OrchestratorEnvelope` type. Orchestrator
   context is static per request; AnalysisResult stays clean. Linked by
   analysis_id.

3. **Privacy**: Include user messages by default. No opt-out for now.

4. **Codex CLI**: Deferred to spec 11. Only Claude Code + generic adapters here.

5. **Cross-skill analysis**: Not in scope. Whole-prompt metrics only. Chunks get
   `source` attribution so spec 13 (Per-Source Metrics) can use it later.

6. **Passive/active merge**: Active wins on conflict, passive provides fallback.
   Interface defined here; spec 08 fills in active detection.
