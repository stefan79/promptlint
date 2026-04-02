# 06 — Configuration Language

> Status: **Implemented**

## Goal

A single configuration file (`promptlint.yaml`) that wires together pipelines,
backends, gateways, and orchestrator adapters. This is the top-level entry
point for a promptlint deployment.

## Config discovery

Search chain (first match wins):

1. `--config <path>` CLI flag (explicit, highest priority)
2. `./promptlint.yaml` (current working directory)
3. `~/.config/promptlint/promptlint.yaml`
4. `/etc/promptlint/promptlint.yaml`

If no config is found and one is required, the CLI prints the search chain
and exits with an error.

## Schema version

Every config file has an optional `version` field (default: `1`). The loader
validates the version against `SUPPORTED_VERSIONS = {1}` and raises
`ConfigError` for unknown versions.

## Example

```yaml
# promptlint.yaml
version: 1

stages:
  chunker-claude:
    base: chunker
    config:
      skill_markers: ["<system-reminder>"]

pipelines:
  production:
    metrics: [redundancy, contradiction, scorer]
    preprocessing:
      chunker: chunker-claude

  fast-check:
    metrics: [scorer]

backends:
  local:
    type: jsonl
    path: /var/log/promptlint/results.jsonl

  metrics:
    type: prometheus
    pushgateway: http://pushgateway:9091
    job: promptlint
    labels:
      env: production

  search:
    type: elasticsearch
    url: https://es.internal:9200
    index: promptlint
    auth: ${ES_API_KEY}

gateway:
  type: builtin-proxy
  listen: 0.0.0.0:8100
  pipeline: production
  backends: [local, metrics, search]
  block_on: critical
  target: https://api.anthropic.com

orchestrator:
  type: claude-code
  skill_detection: true
  prompt_fingerprint: true
  feedback:
    enabled: true
    backend: local
  dataset:
    enabled: true
    path: /data/promptlint-dataset.jsonl
    include_user_messages: false

analysis:
  classification_threshold: 0.60
  warn_instructions: 100
```

## Design principles

1. **Convention over configuration** — sensible defaults for everything;
   minimal config for simple use cases.
2. **Environment variable interpolation** — `${VAR}` syntax for secrets.
   Unresolved variables are kept as-is (no error).
3. **Single file** — one `promptlint.yaml` describes the full deployment.
4. **Validated** — `promptlint validate` CLI command with optional `--deep`
   for backend connectivity checks.
5. **No hot reload** — config is loaded at startup; changes require restart.
6. **No profiles** — use `${VAR}` interpolation or separate config files
   for different environments.

## Config sections

### `version` (int, default: 1)

Schema version. Validated against supported versions.

### `stages`, `pipelines`, `benchmarks`

Delegated to the existing pipeline DSL parser (`pipeline_config.py`). See
spec 02 for format details.

### `backends` (map of name -> emitter config)

Each backend must be a mapping with a `type` field. Types: `jsonl`,
`elasticsearch`, `prometheus`, `sqlite`, `webhook`.

### `gateway`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | str | `builtin-proxy` | `builtin-proxy` or `sdk-middleware` |
| `listen` | str | `0.0.0.0:8100` | Bind address for proxy |
| `pipeline` | str | `""` | Named pipeline to use |
| `backends` | list[str] | `[]` | Backend names for result storage |
| `block_on` | str or null | `null` | Severity threshold for blocking |
| `target` | str | `https://api.anthropic.com` | Upstream URL |
| `vendor_override` | str or null | `null` | Force vendor detection |
| `max_concurrent` | int | `10` | Concurrency limit |
| `timeout` | float | `300.0` | Request timeout seconds |

One gateway per process. Multiple gateways require separate processes.

### `orchestrator`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | str | `generic` | Orchestrator adapter name |
| `skill_detection` | bool | `true` | Enable skill detection |
| `prompt_fingerprint` | bool | `true` | Compute prompt fingerprint |
| `feedback.enabled` | bool | `false` | Enable feedback collection |
| `feedback.backend` | str | `""` | Backend for feedback storage |
| `dataset.enabled` | bool | `false` | Enable dataset collection |
| `dataset.path` | str | `""` | Dataset output path |
| `dataset.include_user_messages` | bool | `false` | Include user messages (PII) |

### `analysis`

Global analysis threshold overrides. All fields are optional; when omitted,
the `Config` dataclass defaults apply.

| Field | Type | Default |
|-------|------|---------|
| `classification_threshold` | float | `0.50` |
| `contradiction_threshold` | float | `0.7` |
| `redundancy_similarity` | float | `0.70` |
| `warn_instructions` | int | `80` |
| `critical_instructions` | int | `150` |
| `warn_density` | float | `60.0` |
| `critical_density` | float | `90.0` |

## Validation

### Syntax validation (`promptlint validate`)

- YAML structure is valid
- `version` is a supported integer
- All backend configs are mappings with `type` field
- Gateway type is `builtin-proxy` or `sdk-middleware`
- Gateway backend references exist in `backends`
- Gateway pipeline reference exists in `pipelines`
- Feedback backend reference exists in `backends` (when enabled)
- Pipeline DSL validation (stages, metrics, preprocessing)

### Deep validation (`promptlint validate --deep`)

All syntax checks plus:
- Each backend is instantiated and tested with a probe write
- Reports per-backend pass/fail

## Cross-reference validation

- `gateway.backends` must reference names defined in `backends`
- `gateway.pipeline` must reference a name defined in `pipelines`
- `orchestrator.feedback.backend` must reference a name defined in `backends`
  (only checked when `feedback.enabled` is true)

## Error handling

All validation errors raise `ConfigError` with a descriptive message. The
`validate_config()` function catches all errors and returns them as a list
of strings for CLI display.

## Implementation

| File | Purpose |
|------|---------|
| `src/promptlint/config_loader.py` | Discovery, parsing, validation, env var resolution |
| `src/promptlint/cli.py` | `validate` subcommand |
| `tests/test_config_loader.py` | Unit tests (43 tests) |

### Key types

- `PromptLintSettings` — top-level config dataclass
- `GatewaySettings` — gateway section
- `OrchestratorSettings` — orchestrator section with nested `FeedbackSettings`, `DatasetSettings`
- `AnalysisSettings` — threshold overrides
- `ConfigError` — validation error type

### Public API

- `discover_config(explicit_path?) -> Path | None` — search chain
- `load_settings(path) -> PromptLintSettings` — load and validate
- `parse_settings_dict(raw) -> PromptLintSettings` — parse from dict
- `validate_config(path, deep?) -> list[str]` — validate, returns errors
- `settings_to_config(settings) -> dict` — convert to Config kwargs

## Resolved decisions

1. **Config discovery**: `--config` flag > CWD > `~/.config/` > `/etc/`
2. **Multiple gateways**: One gateway per process
3. **Hot reload**: No — require restart
4. **Profile support**: Use `${VAR}` interpolation instead
5. **Schema versioning**: `version: 1` field included
6. **Validation depth**: Syntax by default, `--deep` for connectivity
