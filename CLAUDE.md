# promptlint

Static analysis for assembled LLM prompts. Counts instructions, detects
redundancy and contradictions, scores complexity. Deterministic (encoder-based
NLP, no LLM calls).

## Architecture

```
                    ┌─────────────────────────────────┐
                    │         promptlint.yaml          │
                    │  (pipelines, backends, gateway,  │
                    │   orchestrator config)            │
                    └────────────────┬────────────────┘
                                     │ configures
         ┌───────────────────────────┼───────────────────────────┐
         │                           │                           │
         ▼                           ▼                           ▼
┌─────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
│ Gateway Listener │   │   Pipeline Runner    │   │      Emitters        │
│                  │   │                      │   │                      │
│ - Built-in proxy │   │ Two-phase pipeline:  │   │ - JSONL (local)      │
│ - Nginx sidecar  │──▶│ 1. Preprocessing:    │──▶│ - Elasticsearch      │
│ - SDK middleware  │   │    chunk→classify→   │   │ - Prometheus         │
│ - LLM gateway    │   │    embed             │   │ - SQLite             │
│   plugin         │   │ 2. Metrics (parallel):│   │ - Webhook            │
│                  │   │    redundancy,        │   │                      │
│                  │   │    contradiction,     │   │                      │
│                  │   │    scorer             │   │                      │
└────────┬─────────┘   └──────────┬───────────┘   └──────────▲───────────┘
         │                        │                           │
         │ captures               │ produces                  │ writes
         ▼                        ▼                           │
┌─────────────────┐   ┌──────────────────────┐               │
│ MessageRecord    │   │  AnalysisResult     │───────────────┘
│                  │   │                      │
│ - role, content  │   │ - metrics (KV)       │
│ - provenance     │   │ - instructions[]     │
│   (skill/tool/   │   │ - redundancy_groups[]│
│    agent)        │   │ - contradictions[]   │
│ - orchestrator   │   │ - severity           │
│ - analysis_id ───┼──▶│ - prompt_fingerprint │
└─────────────────┘   │ - orchestrator ctx   │
                      │ - skills/tools/agents│
                      └──────────┬───────────┘
                                 │
                                 │ linked by analysis_id
                                 ▼
                      ┌──────────────────────┐
                      │     Feedback          │
                      │                       │
                      │ - analysis_id         │
                      │ - rating (good/bad)   │
                      │ - corrections[]       │
                      │ - note                │
                      │ - timestamp           │
                      └───────────────────────┘
                        ▲
                        │ `promptlint feedback <id>`
                        │  CLI command in orchestrator
```

## Core interfaces (summary)

For full interface definitions with code, invoke `/architect`.

| Interface | Purpose | Boundary |
|-----------|---------|----------|
| **AnalysisResult** | Universal exchange type. Every pipeline produces, every emitter consumes. | pipeline → emitter |
| **MessageRecord** | What the gateway captures. Exists whether or not analysis runs. | gateway → pipeline |
| **Feedback** | CLI-driven (`promptlint feedback <id>`), linked by analysis_id. | user → emitter |
| **Emitter** | Protocol: `write_analysis()` + `write_feedback()` | pipeline/feedback → storage |
| **GatewayListener** | Protocol: `extract_messages()` + `inject_headers()` + `should_block()` | network → pipeline |
| **NormalizedRequest** | Vendor-agnostic (Anthropic/OpenAI/Gemini) request after gateway normalization | gateway internal |
| **OrchestratorContext** | From active plugin (spec 08): version, skills, session ID | orchestrator → gateway |
| **PipelineStage** | Protocol: `name` + `process(context) → context` | pipeline internal |

## Orchestrator wire formats

Orchestrators assemble prompts differently. The gateway must normalize:

| Orchestrator | System prompt | Skills | Tools | Detection |
|-------------|--------------|--------|-------|-----------|
| **Claude Code** | `body["system"]` | `Skill` tool calls (lazy-loaded SKILL.md) | `body["tools"]` | `<system-reminder>` tags, Skill/Agent tool_use |
| **Codex CLI** | `messages[0]` role=system | N/A | `body["tools"]` (OpenAI format) | TBD |
| **Generic** | Configurable | Configurable markers | Configurable | User-defined regex/xpath |

Two observation modes:
- **Passive (spec 05)**: parse wire traffic only, heuristic attribution
- **Active (spec 08)**: orchestrator plugin provides explicit context (version, active skills, session ID)

## Specs

| # | Spec | Status |
|---|------|--------|
| 01 | [Core Pipeline](specs/01-core-pipeline.md) | Implemented |
| 02 | [Pipeline DSL](specs/02-pipeline-dsl.md) | Implemented |
| 03 | [Storage Backends](specs/03-storage-backends.md) | Implemented |
| 04 | [Gateway Integration](specs/04-gateway-integration.md) | Implemented |
| 05 | [Orchestrator Support (Passive)](specs/05-orchestrator-support.md) | Implemented |
| 06 | [Configuration Language](specs/06-configuration.md) | Implemented |
| 07 | [Benchmarks](specs/07-benchmarks.md) | Draft |
| 08 | [Orchestrator Plugins (Active)](specs/08-orchestrator-plugins.md) | Draft |
| 09 | [Linting Rules Engine](specs/09-linting-rules.md) | Draft |
| 10 | [Positional Attention Risk](specs/10-positional-attention.md) | Draft |
| 11 | [Orchestrator: Codex CLI](specs/11-orchestrator-codex-cli.md) | Draft |
| 12 | [Orchestrator: OpenCode](specs/12-orchestrator-opencode.md) | Draft |
| 13 | [Per-Source Metrics](specs/13-per-source-metrics.md) | Draft |
| 14 | [Incremental Analysis Cache](specs/14-incremental-analysis-cache.md) | Draft |

## Module layout

```
src/promptlint/
├── __init__.py          # PromptAnalyzer (public API)
├── models.py            # dataclasses (Chunk, ClassifiedChunk, etc.)
├── config.py            # PromptLintConfig (all thresholds)
├── config_loader.py     # YAML config discovery, parsing, validation (spec 06)
├── chunker.py           # Stage 1: structural segmentation
├── classifier.py        # Stage 2: DeBERTa zero-shot NLI
├── embedder.py          # Stage 3: MiniLM sentence embeddings
├── redundancy.py        # Stage 4: HDBSCAN / pairwise clustering
├── contradiction.py     # Stage 5: NLI cross-encoder
├── scorer.py            # Stage 6: metrics + severity
├── prompt_parser.py     # Input parsing (raw, structured, files)
├── emitters/            # Storage backends (spec 03)
│   ├── __init__.py      # Emitter protocol, factory, env var resolution
│   ├── jsonl.py         # JSONL file backend
│   ├── elasticsearch.py # Elasticsearch/OpenSearch backend
│   ├── prometheus.py    # Prometheus pushgateway backend
│   ├── sqlite.py        # SQLite backend
│   └── webhook.py       # HTTP POST webhook backend
├── gateways/            # Gateway listeners (spec 04)
│   ├── __init__.py      # GatewayListener protocol, GatewayInfo, exceptions
│   ├── normalizer.py    # Vendor-specific → NormalizedRequest
│   ├── proxy.py         # Built-in FastAPI reverse proxy
│   └── sdk_middleware.py # httpx transport middleware
├── orchestrators/       # Orchestrator adapters (spec 05)
│   ├── __init__.py      # OrchestratorAdapter protocol, registry, data types
│   ├── claude_code.py   # Claude Code passive detection
│   ├── generic.py       # Generic adapter (fallback)
│   └── envelope.py      # OrchestratorEnvelope, prompt fingerprinting
├── cli.py               # CLI (analyze, check, diff, pipeline, benchmark, test-backends, proxy)
└── proxy.py             # FastAPI reverse proxy
```

## Python coding standards

### Formatting & style
- **ruff** for linting and formatting (config in pyproject.toml)
- Line length: 120 chars
- Imports: sorted by isort (via ruff), `promptlint` as first-party
- Python 3.10+ features: use `X | Y` unions, `list[]`/`dict[]` lowercase generics

### Type safety
- **mypy** with `disallow_untyped_defs` — all functions must have type annotations
- Use `Protocol` for interfaces, not ABCs
- Use `@dataclass` for data types, not dicts

### Documentation
- Module-level docstring only when the module's purpose isn't obvious from its name
- Public API functions: one-line docstring
- No docstrings on private helpers, tests, or obvious methods
- Comments only where the logic isn't self-evident

### Testing
- Use `pytest`, plain functions, no class-based tests
- Tests that load ML models: mark with `@pytest.mark.slow`
- Test files mirror source: `src/promptlint/foo.py` → `tests/test_foo.py`
- For edge case requirements, invoke `/test-rules`

### Linting (enforced by hooks)
- `ruff check --fix` + `ruff format` on every file save
- `ruff check` + `mypy src/` + `pytest -m 'not slow'` before push

## Key decisions

- **Pure Python** — encoder models (DeBERTa, MiniLM, HDBSCAN) are Python-native
- **No LLM calls** — deterministic, fast, no API keys needed for analysis
- **CPU only** — all inference within ~210ms latency budget
- **AnalysisResult is the universal contract** — every emitter and consumer speaks this type
- **MessageRecord and AnalysisResult are separate but linked** — messages exist independently of analysis
- **Feedback is CLI-driven** — `promptlint feedback <id>` command, no UI for now
