# 06 — Configuration Language

> Status: **Draft — open questions below**

## Goal

A single configuration file (`promptlint.yaml`) that wires together pipelines,
backends, gateways, and orchestrator adapters. This is the top-level entry
point for a promptlint deployment.

## Example

```yaml
# promptlint.yaml

stages:
  chunker-claude:
    base: chunker
    config:
      skill_markers: ["<system-reminder>"]

pipelines:
  production:
    stages: [chunker-claude, classifier, embedder, redundancy, contradiction, scorer]
    config:
      classification_threshold: 0.60

  fast-check:
    stages: [chunker-claude, classifier, scorer]

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
  type: nginx-sidecar
  listen: 0.0.0.0:8100
  pipeline: production
  backends: [local, metrics, search]
  block_on: critical

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
    include_user_messages: false   # PII protection
```

## Design principles

1. **Convention over configuration** — sensible defaults for everything;
   minimal config for simple use cases.
2. **Environment variable interpolation** — `${VAR}` syntax for secrets.
3. **Single file** — one `promptlint.yaml` describes the full deployment.
4. **Composable** — `!include` directive for splitting large configs.
5. **Validated** — JSON Schema for the config file; `promptlint validate`
   CLI command.

## Open questions

1. **Config discovery** — `promptlint.yaml` in CWD, then `~/.config/promptlint/`,
   then `/etc/promptlint/`? Or explicit `--config` flag only?

2. **Multiple gateways** — can you run multiple gateways in one process
   (e.g. built-in proxy + SDK middleware), or one gateway per process?

3. **Hot reload** — should config changes be picked up without restart?
   Important for long-running proxy/gateway processes.

4. **Profile support** — `promptlint --profile staging` to select a named
   config variant? Or use env var interpolation for that?

5. **Schema versioning** — `version: 2` field for breaking changes?

6. **Validation depth** — should `promptlint validate` just check syntax,
   or also verify backends are reachable and models are downloadable?
