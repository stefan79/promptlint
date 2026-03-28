# 04 — Gateway Integration

> Status: **Draft — open questions below**

## Goal

Replace the hard-coded FastAPI reverse proxy from spec 01 with a pluggable
listener model. promptlint should be deployable as:

1. **Built-in reverse proxy** (current behavior, kept as one option)
2. **Nginx/OpenResty sidecar** (Lua plugin or mirror subrequest)
3. **LLM gateway plugin** (LiteLLM, Portkey, Helicone, custom)
4. **MITM / transparent proxy** (mitmproxy script)
5. **SDK middleware** (wrap Anthropic/OpenAI client)

## Architecture sketch

```
┌─────────────┐      ┌──────────────┐      ┌──────────┐
│  LLM Client │─────▶│   Gateway    │─────▶│ LLM API  │
└─────────────┘      │  (any type)  │      └──────────┘
                     └──────┬───────┘
                            │ extract prompt
                            ▼
                     ┌──────────────┐
                     │  promptlint  │──▶ backend(s)
                     │  (pipeline)  │
                     └──────────────┘
```

The gateway's only job is to **extract the prompt payload** and hand it to
promptlint. promptlint runs the configured pipeline and writes to configured
backend(s). Optionally the gateway can **block or annotate** the request based
on severity.

## Gateway types

### Built-in proxy (existing)
Keep current FastAPI proxy. Refactor to use the pipeline DSL from spec 02.

### Nginx sidecar
- `mirror` directive sends a copy of the request body to a local promptlint
  HTTP endpoint (non-blocking).
- Or: OpenResty Lua script calls promptlint and injects response headers.

### LLM gateway plugin
- LiteLLM: `CustomCallback` with `async_log_pre_api_call`.
- Portkey/Helicone: webhook integration.
- Generic: any gateway that supports request/response hooks.

### SDK middleware
- Wrap `httpx.Client` transport used by Anthropic/OpenAI SDKs.
- Intercept `send()`, extract prompt, analyze, optionally block.

## What's observable on the wire

Based on analysis of Claude Code, Codex CLI, and standard LLM API formats:

### Anthropic API (Claude Code)

```python
{
    "system": "...",             # string or list of content blocks
    "tools": [{"name", "description", "input_schema"}],
    "messages": [
        {"role": "user", "content": "..."},
        {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Skill", "input": {"skill": "commit"}}
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "content": "<full SKILL.md content>"}
        ]}
    ]
}
```

**Reliably extractable:**

| Signal | Where | How |
|--------|-------|-----|
| System prompt | `body["system"]` | Direct |
| Tool definitions | `body["tools"]` | Direct |
| Skill invocations | `tool_use` where `name == "Skill"` | `input.skill` has name |
| Skill content | `tool_result` after Skill call | Contains full SKILL.md |
| Agent launches | `tool_use` where `name == "Agent"` | `input.subagent_type` |
| System reminders | Any message content | Parse `<system-reminder>` tags |

**Not extractable (needs spec 08 active plugin):**

| Signal | Why |
|--------|-----|
| Which instructions came from which skill | No attribution markers in assembled prompt |
| System-reminder deduplication | No sequence numbers or IDs |
| Orchestrator version | Not in API payload |
| Session identity | No session header |

### OpenAI API (Codex CLI)

```python
{
    "messages": [
        {"role": "system", "content": "..."},
        {"role": "user", "content": "..."}
    ],
    "tools": [{"type": "function", "function": {"name", "description", "parameters"}}]
}
```

System prompt is inside `messages` (role=system), not a top-level field.

### Gemini API

```python
{
    "system_instruction": {"parts": [{"text": "..."}]},
    "contents": [{"role": "user", "parts": [{"text": "..."}]}],
    "tools": [{"function_declarations": [...]}]
}
```

### Vendor normalizer

The gateway needs a vendor normalizer that produces a common structure:

```python
@dataclass
class NormalizedRequest:
    vendor: str                     # anthropic | openai | gemini
    system_prompt: str
    tools: list[dict]
    messages: list[MessageRecord]
    raw_body: bytes                 # preserved for forwarding
```

Each gateway adapter detects the vendor from the request path or content
structure and normalizes accordingly.

## Open questions

1. **Async vs sync** — nginx mirror is fire-and-forget; SDK middleware is
   inline. Should the pipeline always run async, or should the gateway decide?

2. **Blocking semantics** — who decides to block? The gateway adapter, or a
   post-pipeline hook? What about non-blocking gateways like nginx mirror?

3. **Header injection** — only possible for inline gateways. Should we
   standardize which gateways support annotation vs just logging?

4. **Rate limiting** — if promptlint analysis is slower than the LLM call,
   should the gateway skip analysis under load?

5. **Vendor auto-detection** — detect from URL path (`/v1/messages` =
   Anthropic, `/v1/chat/completions` = OpenAI) or require explicit config?

6. **Enrichment from spec 08** — when an orchestrator plugin provides
   `OrchestratorContext` (via sidecar file or header), should the gateway
   merge it into `NormalizedRequest` or keep it separate?
