# 03 — Storage Backends

> Status: **Implemented**

## Goal

Define a pluggable backend interface so pipeline results (per-call analysis,
time-series metrics, benchmark runs) can be written to different storage systems.

## Backends

| Backend | Use case |
|---------|----------|
| **JSON / JSONL (local)** | Default, zero-dep, good for CI and local dev |
| **Elasticsearch / OpenSearch** | Full-text search over analysis results, dashboards |
| **Prometheus** | Time-series metrics (instruction_count, density, contradiction_count as gauges/histograms) |
| **SQLite** | Local structured queries without a server |
| **Webhook (HTTP POST)** | Forward results to arbitrary endpoints |

## Emitter protocol

All backends implement the `Emitter` protocol:

```python
class Emitter(Protocol):
    def write_analysis(self, payload: AnalysisPayload) -> None: ...
    def write_feedback(self, feedback: Feedback) -> None: ...
```

- Emitters are **stateless** — they receive a payload and write it, no buffering.
- Serialization uses `dataclasses.asdict()` for schema-flexible backends.
- Each emitter lives in `src/promptlint/emitters/<name>.py`.

## Prometheus metrics

All metrics use the `promptlint_` prefix with labels `pipeline` and `severity`:

| Metric | Type |
|--------|------|
| `promptlint_instruction_count` | Gauge |
| `promptlint_density` | Gauge |
| `promptlint_contradiction_count` | Gauge |
| `promptlint_severity` | Gauge (labeled, value=1 for active severity) |

## Authentication

Env var expansion (`${VAR}`) for secrets in backend config. This is an interim
approach — when spec 06 (Configuration Language) is implemented, env var lookup
should migrate to the config layer as the single source of truth, with
`promptlint.yaml` supporting `${VAR}` interpolation natively.

## Retention

No file rotation in the JSONL backend. Leave to external tools (logrotate, etc.).

## Integration testing

- Docker Compose harness (`docker-compose.test.yml`) with Elasticsearch and
  Prometheus pushgateway services.
- Integration tests marked `@pytest.mark.integration`, run in a separate CI job.
- CLI command `promptlint test-backends --config <path>` for ad-hoc validation
  of configured backends: writes a test payload, reads it back where possible,
  reports pass/fail per backend.

## Example YAML (preview of spec 06)

```yaml
backends:
  local:
    type: jsonl
    path: ./promptlint-results.jsonl

  metrics:
    type: prometheus
    pushgateway: http://localhost:9091
    job: promptlint

  search:
    type: elasticsearch
    url: http://localhost:9200
    index: promptlint-analyses
    auth: ${ES_API_KEY}
```

## ~~Open questions~~ (all resolved)

1. ~~**Interface shape**~~ → Two methods: `write_analysis()` + `write_feedback()`.
2. ~~**Batching & buffering**~~ → Synchronous writes, no buffering. Emitters are stateless.
3. ~~**Schema evolution**~~ → `dataclasses.asdict()` serialization. No special migrations.
4. ~~**Prometheus metric naming**~~ → `promptlint_` prefix, `pipeline`/`severity` labels.
5. ~~**Authentication**~~ → Env var expansion for now; migrate to spec 06 config layer later.
6. ~~**Retention / rotation**~~ → No rotation. Leave to external tools.
7. **Integration testing** → Docker Compose harness, `@pytest.mark.integration` marker,
   `promptlint test-backends` CLI command for ad-hoc validation.
