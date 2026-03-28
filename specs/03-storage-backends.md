# 03 — Storage Backends

> Status: **Draft — open questions below**

## Goal

Define a pluggable backend interface so pipeline results (per-call analysis,
time-series metrics, benchmark runs) can be written to different storage systems.

## Backends under consideration

| Backend | Use case |
|---------|----------|
| **JSON / JSONL (local)** | Default, zero-dep, good for CI and local dev |
| **Elasticsearch / OpenSearch** | Full-text search over analysis results, dashboards |
| **Prometheus** | Time-series metrics (instruction_count, density, contradiction_count as gauges/histograms) |
| **SQLite** | Local structured queries without a server |
| **Webhook (HTTP POST)** | Forward results to arbitrary endpoints |

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

## Open questions

1. **Interface shape** — single `write(result: AnalysisResult)` method, or
   separate `write_analysis()` / `write_benchmark()` / `write_metric()`?

2. **Batching & buffering** — should backends buffer writes and flush
   periodically, or write synchronously per call?

3. **Schema evolution** — when AnalysisResult gains fields, how do backends
   handle it? Elasticsearch is schema-flexible; Prometheus is not.

4. **Prometheus metric naming** — `promptlint_instruction_count`,
   `promptlint_density`, `promptlint_contradictions`? Labels for
   pipeline name, severity?

5. **Authentication** — env var references (`${ES_API_KEY}`) or a separate
   secrets mechanism?

6. **Retention / rotation** — should the JSONL backend support file rotation?
   Should we care, or leave it to logrotate?
