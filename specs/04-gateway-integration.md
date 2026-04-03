# 04 — Gateway Integration

> Status: **Implemented**

## Goal

Replace the hard-coded FastAPI reverse proxy from spec 01 with a pluggable
listener model. The gateway extracts LLM request payloads, normalizes them to a
vendor-agnostic format, hands them to the pipeline, and optionally blocks or
annotates the response based on analysis results.

## V1 scope

V1 implements three gateway types:

1. **Built-in reverse proxy** — refactored from spec 01 to use the gateway
   abstraction and vendor normalizer
2. **SDK middleware** — wraps `httpx.Client` transport used by Anthropic/OpenAI
   SDKs
3. **Gateway abstraction + vendor normalizer** — shared layer used by both

**Deferred to future versions:**

- Nginx/OpenResty sidecar (Lua plugin or mirror subrequest)
- MITM / transparent proxy (mitmproxy script)
- LLM gateway plugins (LiteLLM, Portkey, Helicone)

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌──────────┐
│  LLM Client │─────▶│   Gateway    │─────▶│ LLM API  │
└─────────────┘      │  (any type)  │      └──────────┘
                     └──────┬───────┘
                            │ NormalizedRequest
                            ▼
                     ┌──────────────┐
                     │  promptlint  │──▶ emitter(s)
                     │  (pipeline)  │
                     └──────────────┘
```

The gateway's job is to:

1. Detect the vendor from the request body
2. Normalize the request to `NormalizedRequest`
3. Hand it to the pipeline (sync; gateway adapters use `asyncio.to_thread()`
   for async contexts)
4. Optionally block or annotate the request based on analysis severity

## Concurrency model

The pipeline is synchronous. Gateway adapters that run in async contexts (the
built-in proxy, SDK middleware with async clients) use `asyncio.to_thread()` to
call the pipeline without blocking the event loop.

A bounded semaphore limits concurrent pipeline executions. When the semaphore
is full, the gateway returns HTTP 429 (built-in proxy) or raises
`PromptLintOverloadError` (SDK middleware). No retry or queuing.

```python
@dataclass
class ConcurrencyConfig:
    max_concurrent: int = 10  # bounded semaphore size
```

The semaphore is created once per gateway instance at `__init__` time. For
`max_concurrent = 0`, no semaphore is used (unlimited concurrency).

## Gateway capabilities

Each gateway type declares its capabilities via an enum. The pipeline runner
checks capabilities before attempting actions that not all gateways support.

```python
from enum import Flag, auto

class GatewayCapability(Flag):
    LOG_ONLY = auto()    # can only log analysis results
    ANNOTATE = auto()    # can inject response headers
    BLOCK = auto()       # can block requests based on severity
```

| Gateway type | Capabilities |
|-------------|-------------|
| Built-in proxy | `LOG_ONLY \| ANNOTATE \| BLOCK` |
| SDK middleware | `LOG_ONLY \| ANNOTATE \| BLOCK` |
| Nginx sidecar (future) | `LOG_ONLY` |
| LLM gateway plugin (future) | `LOG_ONLY \| ANNOTATE` |

## Gateway protocol

```python
from typing import Protocol

class GatewayListener(Protocol):
    @property
    def capabilities(self) -> GatewayCapability: ...

    @property
    def info(self) -> GatewayInfo: ...

    def extract_request(self, raw_request: bytes) -> NormalizedRequest: ...

    def inject_headers(self, response: Any, result: AnalysisResult) -> None: ...

    def should_block(self, result: AnalysisResult) -> bool: ...
```

`inject_headers()` and `should_block()` are no-ops when the gateway lacks
`ANNOTATE` or `BLOCK` capability respectively. Callers must check capabilities
before invoking.

## Data types

### NormalizedMessage

Lightweight message type for gateway-to-pipeline transfer. Does NOT carry
provenance or orchestrator context — those are added later.

```python
@dataclass
class NormalizedMessage:
    role: str        # "user", "assistant", "system", "tool_result"
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)

@dataclass
class ToolCall:
    name: str
    input: dict
    output: str | None = None
```

### NormalizedRequest

Vendor-agnostic request produced by the normalizer. This is the input to the
pipeline.

```python
@dataclass
class NormalizedRequest:
    vendor: str                     # "anthropic", "openai", "gemini"
    system_prompt: str | None
    tools: list[dict]
    messages: list[NormalizedMessage]
    raw_body: bytes                 # preserved for forwarding
    model_id: str | None = None     # extracted from body if present

    # Orchestrator context (from spec 08 plugin, if available)
    orchestrator_context: OrchestratorContext | None = None
```

### GatewayInfo

Added to `AnalysisResult` to record which gateway produced the analysis.

```python
@dataclass
class GatewayInfo:
    type: str   # "builtin-proxy", "sdk-middleware"
    id: str     # instance identifier (config-provided or auto-generated uuid)
```

The `AnalysisResult` dataclass gains a `gateway: GatewayInfo | None` field
(default `None`, set by the gateway adapter before emitting). This is `None`
when analysis runs without a gateway (e.g., direct `PromptAnalyzer.analyze()`
calls). The architect skill shows `gateway: GatewayInfo` as required; that
definition will be updated to `GatewayInfo | None` when this spec is
implemented.

## Vendor detection and normalization

### Detection strategy

Body sniffing is the default. The normalizer inspects top-level keys in the
parsed JSON body to determine the vendor:

| Vendor | Distinguishing keys |
|--------|-------------------|
| Gemini | `"system_instruction"` or `"contents"` (instead of `"messages"`) |
| Anthropic | `"system"` as top-level key (string or list), OR `"max_tokens"` as top-level key (required in Anthropic API, absent in OpenAI) |
| OpenAI | `"messages"` present AND neither Gemini nor Anthropic markers found |

Detection order: Gemini (most distinctive keys) -> Anthropic -> OpenAI (final
fallback). The key tiebreaker between Anthropic and OpenAI is `"max_tokens"`:
Anthropic requires it at the top level; OpenAI uses `"max_tokens"` or
`"max_completion_tokens"` but neither is required. If `"messages"` is present
but no Gemini or Anthropic markers match, the body is classified as OpenAI.

If no vendor can be determined (e.g., empty body or unrecognized structure),
the gateway raises `VendorDetectionError`. The user can override detection via
config:

```yaml
gateway:
  vendor: anthropic  # skip auto-detection
```

### Normalization

Each vendor has a normalizer function that produces `NormalizedRequest`:

```python
def normalize_anthropic(body: dict, raw: bytes) -> NormalizedRequest: ...
def normalize_openai(body: dict, raw: bytes) -> NormalizedRequest: ...
def normalize_gemini(body: dict, raw: bytes) -> NormalizedRequest: ...
```

Normalization rules per vendor:

**Anthropic:**
- `system_prompt` = `body["system"]` (string or content blocks, joined with `\n\n`)
- `tools` = `body["tools"]` (direct)
- `messages` = `body["messages"]`, each converted to `NormalizedMessage`
- `model_id` = `body.get("model")`
- Content blocks (`list[dict]`) are flattened: text blocks joined, tool_use
  blocks converted to `ToolCall`

**OpenAI:**
- `system_prompt` = content of first message where `role == "system"` (removed
  from messages list)
- `tools` = `body["tools"]` (wrapped in function format)
- `messages` = remaining `body["messages"]`
- `model_id` = `body.get("model")`

**Gemini:**
- `system_prompt` = `body["system_instruction"]["parts"]` joined
- `tools` = `body["tools"][0]["function_declarations"]` (unwrapped)
- `messages` = `body["contents"]` mapped from `parts` format
- `model_id` = `body.get("model")` (URL-based extraction deferred; normalizer
  receives body only)

## What's observable on the wire

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

## Gateway types (v1)

### Built-in proxy

Refactored FastAPI proxy. Uses the gateway abstraction and vendor normalizer
instead of hard-coded Anthropic extraction.

Changes from spec 01 proxy:
- Delegates body parsing to `VendorNormalizer`
- Supports Anthropic, OpenAI, and Gemini endpoints (not just `/v1/messages`)
- Calls pipeline via `asyncio.to_thread()` with bounded semaphore
- Blocking decisions come from `block_on` config (not `--fail-on` CLI flag only)
- Returns HTTP 429 when semaphore is full

Route matching:
- `POST /v1/messages` — Anthropic
- `POST /v1/chat/completions` — OpenAI
- `POST /v1beta/models/*/generateContent` — Gemini
- All other routes — pass through without analysis

### SDK middleware

Wraps `httpx.Client` transport to intercept requests before they reach the LLM
API. Works with both Anthropic and OpenAI Python SDKs since both use httpx.

```python
from promptlint.gateways import PromptLintTransport

import anthropic

client = anthropic.Anthropic(
    http_client=httpx.Client(
        transport=PromptLintTransport(
            target=httpx.HTTPTransport(),
            analyzer=PromptAnalyzer(),
        )
    )
)
```

The transport:
1. Intercepts `handle_request()`
2. Parses body, normalizes via `VendorNormalizer`
3. Runs pipeline (sync, with threading semaphore)
4. Checks `should_block()` — raises `PromptLintBlockedError` if severity
   exceeds threshold
5. Injects `X-Promptlint-*` headers into the outgoing request
6. Delegates to the wrapped transport

For async clients, `PromptLintAsyncTransport` wraps `handle_async_request()`
and uses `asyncio.to_thread()` for the pipeline call.

## Blocking semantics

The gateway does NOT decide blocking on its own. Blocking is configured per
gateway instance via `block_on`:

```yaml
gateway:
  type: builtin-proxy
  block_on: critical           # block when severity >= critical
  # block_on: warning          # stricter: block on warning too
  # block_on: null             # never block (log only)
```

When a future rules engine (spec 09) exists, the gateway defers to its verdict.
Until then, blocking is severity-threshold based.

Gateways without `BLOCK` capability ignore `block_on` config.

## Configuration

### Full gateway config schema

```yaml
gateway:
  # Required
  type: builtin-proxy          # "builtin-proxy" | "sdk-middleware"

  # Optional vendor override (default: auto-detect via body sniffing)
  vendor: null                 # "anthropic" | "openai" | "gemini" | null

  # Instance identity
  id: null                     # string, auto-generated uuid if null

  # Blocking
  block_on: null               # "warning" | "critical" | null (never block)

  # Concurrency
  max_concurrent: 10           # bounded semaphore size, 0 = unlimited

  # Built-in proxy specific
  proxy:
    target: "https://api.anthropic.com"
    host: "0.0.0.0"
    port: 8100
    timeout: 300.0             # upstream request timeout in seconds

  # SDK middleware specific
  sdk:
    inject_headers: true       # add X-Promptlint-* headers to outgoing request
```

### Defaults

| Setting | Default | Rationale |
|---------|---------|-----------|
| `type` | (required) | No sensible default |
| `vendor` | `null` (auto-detect) | Body sniffing works for all three vendors |
| `id` | auto-generated uuid4 | Unique per instance |
| `block_on` | `null` | Safe default: observe only, never block |
| `max_concurrent` | `10` | Reasonable for single-machine deployment |
| `proxy.target` | `https://api.anthropic.com` | Most common use case |
| `proxy.port` | `8100` | Avoids conflicts with common services |
| `proxy.timeout` | `300.0` | LLM responses can be slow |
| `sdk.inject_headers` | `true` | Headers are the primary annotation mechanism |

## Error handling

### Vendor detection failure

If body sniffing cannot determine the vendor, raise `VendorDetectionError`.
The built-in proxy returns HTTP 400 with a JSON body explaining the error.
The SDK middleware raises the exception to the caller.

### Pipeline failure

If the pipeline raises an unexpected exception, the gateway logs the error and
falls through — the request is forwarded without analysis. Analysis failures
must never block legitimate LLM traffic.

Exception: if the pipeline raises `PromptLintBlockedError` (severity exceeded
threshold), the gateway blocks the request as configured.

### Concurrency overflow

When the bounded semaphore is full:
- Built-in proxy: returns HTTP 429 with `Retry-After: 1` header
- SDK middleware: raises `PromptLintOverloadError`

### Malformed request body

If the request body is not valid JSON:
- Built-in proxy: forwards the request without analysis (pass-through)
- SDK middleware: forwards the request without analysis

### Upstream timeout

The built-in proxy uses the configured `timeout` for upstream requests. On
timeout, it returns HTTP 504 Gateway Timeout.

## Resolved questions

| # | Question | Decision |
|---|----------|----------|
| Q1 | Async vs sync | Pipeline stays sync, gateway adapters use `asyncio.to_thread()` for async contexts |
| Q2 | Blocking semantics | Gateway acts on severity threshold via `block_on` config. Future rules engine (spec 09) will provide richer verdicts |
| Q3 | Header injection | Capability enum per gateway: `BLOCK`, `ANNOTATE`, `LOG_ONLY` |
| Q4 | Rate limiting | Bounded semaphore (configurable, default 10), return HTTP 429 when full. No retry/queuing |
| Q5 | Vendor detection | Body sniffing as default (top-level keys distinguish vendors), optional `vendor:` config override. No URL path matching for detection |
| Q6 | Spec 08 enrichment | Separate optional field `orchestrator_context: OrchestratorContext \| None` on NormalizedRequest |

## Testing strategy

### Unit tests

| Component | Test file | What to test |
|-----------|-----------|-------------|
| Vendor detection | `tests/test_normalizer.py` | Body sniffing correctly identifies Anthropic/OpenAI/Gemini from sample bodies. Unknown body raises `VendorDetectionError`. Config override skips detection. |
| Normalization (Anthropic) | `tests/test_normalizer.py` | System prompt extraction (string and content blocks). Tool extraction. Message conversion including tool_use/tool_result. Content block flattening. |
| Normalization (OpenAI) | `tests/test_normalizer.py` | System message extraction and removal. Function-wrapped tools. |
| Normalization (Gemini) | `tests/test_normalizer.py` | System instruction parts. Function declarations unwrapping. Contents-to-messages mapping. |
| Semaphore | `tests/test_gateway.py` | Concurrent access up to limit succeeds. Exceeding limit raises/returns 429. |
| GatewayCapability | `tests/test_gateway.py` | Capability checks. No-op behavior when capability missing. |
| SDK middleware | `tests/test_sdk_middleware.py` | Transport intercepts request. Headers injected. Blocking raises exception. Pass-through on malformed body. Async variant. |
| GatewayInfo on result | `tests/test_gateway.py` | AnalysisResult includes gateway field after processing. |

### Integration tests (`@pytest.mark.integration`)

| Test | What it covers |
|------|---------------|
| Built-in proxy full flow | Start proxy, send Anthropic/OpenAI request to proxy targeting echo service (port 8888), verify analysis headers in forwarded request, verify response pass-through |
| Proxy blocking | Send request that triggers critical severity, verify HTTP 422 response |
| Proxy overload | Exhaust semaphore, verify HTTP 429 |
| Proxy streaming | Send streaming request, verify SSE pass-through with analysis headers |

Integration tests use the existing echo service from `docker-compose.test.yml`
(mendhak/http-https-echo on port 8888).

### Test markers

- Fast unit tests: no marker (run by default)
- Model-loading tests: `@pytest.mark.slow`
- Docker-dependent tests: `@pytest.mark.integration`

## Dependencies

No new runtime dependencies. The gateway uses `fastapi`, `httpx`, and standard
library modules already in `pyproject.toml`.

## File organization

```
src/promptlint/
├── gateways/
│   ├── __init__.py          # GatewayListener protocol, GatewayCapability enum,
│   │                        #   GatewayInfo, ConcurrencyConfig
│   ├── normalizer.py        # VendorNormalizer, NormalizedRequest,
│   │                        #   NormalizedMessage, vendor detection + normalization
│   ├── proxy.py             # BuiltinProxy (refactored from src/promptlint/proxy.py)
│   └── sdk_middleware.py    # PromptLintTransport, PromptLintAsyncTransport
├── models.py                # + GatewayInfo import, AnalysisResult.gateway field
└── proxy.py                 # thin re-export shim → gateways.proxy (deprecated
                             #   with DeprecationWarning, removed in v2)
```
