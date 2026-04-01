---
name: architect
description: Architecture reference for code generation — interfaces, protocols, data flow, and implementation patterns
user-invocable: true
allowed-tools: Read, Glob, Grep, Edit, Write, Bash
---

# promptlint Architecture Guide

Use this reference when generating or modifying code. All new code must conform
to these interfaces and patterns.

## Data flow

```
Gateway ──captures──▶ MessageRecord
                          │
                          ▼
                    NormalizedRequest
                          │
                          ▼ pipeline runner
                    AnalysisResult ──▶ Emitter(s)
                          │
                          │ linked by analysis_id
                          ▼
                       Feedback ──▶ Emitter(s)
```

## Core interfaces

### AnalysisResult — the universal contract

Every emitter accepts this. Every pipeline produces this. This is the single
type that crosses the pipeline→emitter boundary.

> **Naming note:** The architecture diagrams and specs previously used
> `AnalysisResult`. The implementation uses `AnalysisResult` — this is the
> canonical name. The full `AnalysisResult` with gateway/orchestrator context
> fields (shown below) will be built incrementally as specs 04-08 are
> implemented.

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

class Severity(str, Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"

@dataclass
class OrchestratorInfo:
    name: str                        # "claude-code", "codex-cli", "langchain"
    version: str | None = None       # from active plugin (spec 08), None if passive

@dataclass
class GatewayInfo:
    type: str                        # "builtin-proxy", "nginx", "sdk-middleware"
    id: str                          # instance identifier

@dataclass
class ModelInfo:
    provider: str                    # "anthropic", "openai", "google"
    model_id: str                    # "claude-sonnet-4-20250514", "gpt-4o"

@dataclass
class SkillInfo:
    name: str
    instruction_count: int = 0

@dataclass
class ToolInfo:
    name: str
    param_count: int = 0

@dataclass
class AgentInfo:
    name: str

@dataclass
class Instruction:
    text: str
    source: str                      # section/skill that contributed this
    type: str                        # "behavioral", "constraint", "tool_constraint"
    confidence: float

@dataclass
class AnalysisResult:
    id: str                          # uuid4
    timestamp: datetime
    prompt_fingerprint: str          # hash of normalized instruction set

    # Source context
    orchestrator: OrchestratorInfo
    gateway: GatewayInfo
    model: ModelInfo

    # Prompt decomposition
    skills: list[SkillInfo] = field(default_factory=list)
    tools: list[ToolInfo] = field(default_factory=list)
    agents: list[AgentInfo] = field(default_factory=list)

    # Pipeline results — KV pairs, pipeline-defined
    metrics: dict[str, float] = field(default_factory=dict)

    # Instruction breakdown
    instructions: list[Instruction] = field(default_factory=list)
    redundancy_groups: list = field(default_factory=list)  # RedundancyGroup from models.py
    contradictions: list = field(default_factory=list)      # Contradiction from models.py

    # Severity
    severity: Severity = Severity.OK
    warnings: list[str] = field(default_factory=list)
```

### MessageRecord — gateway capture

Exists independently of analysis. One per API request observed.

```python
@dataclass
class Provenance:
    type: str                        # "skill", "tool", "agent", "user", "system"
    name: str | None = None          # skill/tool/agent name if applicable
    version: str | None = None

@dataclass
class ToolCall:
    name: str
    input: dict
    output: str | None = None

@dataclass
class MessageRecord:
    id: str                          # uuid4
    timestamp: datetime
    role: str                        # "user", "assistant", "system", "tool_result"

    generated_by: Provenance
    orchestrator: OrchestratorInfo

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)

    analysis_id: str | None = None   # links to AnalysisResult.id
```

### Feedback — CLI-driven

```python
@dataclass
class Feedback:
    id: str                          # uuid4
    analysis_id: str                 # links to AnalysisResult.id
    timestamp: datetime
    rating: str                      # "good" | "bad"
    corrections: list[str] = field(default_factory=list)
    note: str = ""
```

### Emitter protocol

All backends implement this. Keep it simple — two methods.

```python
from typing import Protocol

class Emitter(Protocol):
    def write_analysis(self, result: AnalysisResult) -> None: ...
    def write_feedback(self, feedback: Feedback) -> None: ...
```

When implementing a new emitter:
1. Create `src/promptlint/emitters/<name>.py`
2. Implement the `Emitter` protocol
3. Register in the emitter factory (config-driven, spec 06)
4. Add tests in `tests/test_emitter_<name>.py`

### Gateway protocol

All gateway listeners implement this.

```python
class GatewayListener(Protocol):
    def extract_messages(self, raw_request: bytes) -> list[MessageRecord]: ...
    def inject_headers(self, response: Any, payload: AnalysisResult) -> None: ...
    def should_block(self, payload: AnalysisResult) -> bool: ...
```

### NormalizedRequest — vendor-agnostic

The gateway normalizes vendor-specific formats before handing to the pipeline.

```python
@dataclass
class NormalizedRequest:
    vendor: str                      # "anthropic", "openai", "gemini"
    system_prompt: str
    tools: list[dict]
    messages: list[MessageRecord]
    raw_body: bytes                  # preserved for forwarding

    # Orchestrator context (from spec 08 plugin, if available)
    orchestrator_context: OrchestratorContext | None = None
```

### OrchestratorContext — from active plugin (spec 08)

Provided by orchestrator hooks/plugins. Not available in passive mode.

```python
@dataclass
class OrchestratorContext:
    orchestrator: str
    version: str
    session_id: str
    active_skills: list[str] = field(default_factory=list)
    active_tools: list[str] = field(default_factory=list)
    active_agents: list[str] = field(default_factory=list)
    timestamp: datetime | None = None
    skill_instruction_counts: dict[str, int] = field(default_factory=dict)
    prompt_hash: str | None = None
```

### DetectedContext — from passive observation (spec 05)

Produced by orchestrator adapters parsing wire traffic.

```python
@dataclass
class DetectedContext:
    orchestrator_name: str          # "claude-code", "generic", "unknown"
    skills: list[SkillInfo]
    tools: list[ToolInfo]
    agents: list[AgentInfo]
    system_prompt_source: str       # "body.system", "messages[0]", etc.
    request_id: str | None = None   # from LLM provider response headers
```

### OrchestratorEnvelope — links orchestrator context to analysis (spec 05)

```python
@dataclass
class OrchestratorEnvelope:
    analysis_id: str
    orchestrator_name: str
    detected_skills: list[str]
    detected_tools: list[str]
    detected_agents: list[str]
    prompt_fingerprint: str         # SHA-256 of normalized instructions, 16 hex chars
    request_id: str | None = None
    model_id: str | None = None
    timestamp: str = ""
```

## Two-phase pipeline architecture (spec 02)

Every pipeline runs in two phases:

### Phase 1: Preprocessing (fixed, always runs)

```
chunker → classifier → embedder
```

Produces the shared context (chunks, classified instructions, embeddings).
Pipelines can swap individual preprocessing stages for variants via
`preprocessing:` overrides in YAML config.

### Phase 2: Metric stages (configurable per pipeline)

Each metric stage consumes the preprocessed context and writes specific keys
to the result. Metric stages are independent and safe for parallel execution.

| Metric stage | Result keys |
|-------------|-------------|
| `redundancy` | `redundancy_groups`, `redundancy_ratio` |
| `contradiction` | `contradictions`, `contradiction_count` |
| `scorer` | `instruction_count`, `token_count`, `severity`, ... |

All stages are built-in. Customization is through config overrides (stage
variants), not by injecting new code. Metric stages accept parameters like
`min_instructions` and short-circuit to fixed defaults when input is below
the threshold.

### Pipeline stage protocol

```python
from typing import Protocol, Any

class PipelineStage(Protocol):
    """A single step in the analysis pipeline."""
    name: str

    def process(self, context: PipelineContext) -> PipelineContext: ...

@dataclass
class PipelineContext:
    """Mutable bag passed through the pipeline."""
    raw_text: str
    chunks: list = field(default_factory=list)
    instructions: list = field(default_factory=list)
    embeddings: Any = None                    # numpy array
    redundancy_groups: list = field(default_factory=list)
    contradictions: list = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    severity: Severity = Severity.OK
    warnings: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)  # per-stage config overrides
```

## Vendor normalization

The gateway detects vendor from request path and normalizes:

| Vendor | Path | System prompt | Tools format |
|--------|------|--------------|-------------|
| Anthropic | `/v1/messages` | `body["system"]` (string or content blocks) | `body["tools"]` with `input_schema` |
| OpenAI | `/v1/chat/completions` | `messages[0]` where role=system | `body["tools"]` with `function.parameters` |
| Gemini | `/v1beta/models/*/generateContent` | `body["system_instruction"]` | `body["tools"][0]["function_declarations"]` |

## Claude Code passive detection

When observing Claude Code traffic at the gateway:

```python
# Detect skill invocations
for msg in messages:
    if msg.role == "assistant":
        for tc in msg.tool_calls:
            if tc.name == "Skill":
                skill_name = tc.input.get("skill")
                # Next tool_result contains the SKILL.md content
            elif tc.name == "Agent":
                agent_type = tc.input.get("subagent_type")

# Parse system reminders from any content
import re
SYSTEM_REMINDER_RE = re.compile(r"<system-reminder>(.*?)</system-reminder>", re.DOTALL)
```

## File organization

```
src/promptlint/
├── __init__.py              # PromptAnalyzer (public API)
├── models.py                # Core dataclasses (Chunk, ClassifiedChunk, AnalysisResult, Feedback)
├── config.py                # PromptLintConfig
├── stages/                  # Pipeline stages (spec 02)
│   ├── __init__.py
│   ├── chunker.py
│   ├── classifier.py
│   ├── embedder.py
│   ├── redundancy.py
│   ├── contradiction.py
│   └── scorer.py
├── emitters/                # Storage backends (spec 03)
│   ├── __init__.py
│   ├── jsonl.py
│   ├── elasticsearch.py
│   ├── prometheus.py
│   ├── sqlite.py
│   └── webhook.py
├── gateways/                # Gateway listeners (spec 04)
│   ├── __init__.py
│   ├── proxy.py             # built-in FastAPI proxy
│   ├── normalizer.py        # vendor-specific → NormalizedRequest
│   └── sdk_middleware.py
├── orchestrators/           # Orchestrator adapters (spec 05)
│   ├── __init__.py          # OrchestratorAdapter protocol, registry, SkillInfo/ToolInfo/AgentInfo
│   ├── claude_code.py       # Claude Code passive detection
│   ├── generic.py           # Generic adapter (fallback)
│   └── envelope.py          # OrchestratorEnvelope, compute_fingerprint
├── pipeline.py              # Pipeline runner (spec 02)
├── prompt_parser.py         # Input parsing
└── cli.py                   # CLI commands
```

## Key conventions

- **Pure Python, no LLM calls** — all analysis is deterministic encoder-based NLP
- **CPU only** — target < 210ms for 10K token prompt
- **AnalysisResult is the universal contract** — never bypass it
- **Emitters are stateless** — they receive a payload and write it, no buffering
- **Gateways normalize first** — always produce NormalizedRequest before pipeline
- **Passive before active** — passive detection works without orchestrator changes; active enriches it
- **Config-driven** — all thresholds, stage selection, backend choice via `promptlint.yaml`
