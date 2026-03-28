# 02 — Pipeline DSL

> Status: **Ready for implementation — all open questions resolved**

## Goal

Define a YAML-based language for composing analysis pipelines from reusable
building blocks. Each pipeline declares which metric stages to run on top of a
shared preprocessing chain. Pipelines can be benchmarked against each other on
the same corpus.

## Core concepts

| Concept | Description |
|---------|-------------|
| **Preprocessing** | A fixed, ordered chain of stages that always runs: `chunker → classifier → embedder`. Produces the shared context (chunks, classified instructions, embeddings) that all metric stages consume. Individual stages can be swapped for variants via `preprocessing:` overrides. |
| **Metric stage** | A registered unit of work that consumes preprocessed context and produces specific keys in the result (e.g. `redundancy` produces `redundancy_groups` + `redundancy_ratio`). |
| **Stage variant** | A named configuration of a built-in stage with overridden settings (e.g. `chunker-strict` is `chunker` with `min_chunk_words: 3`). |
| **Pipeline** | A named configuration that optionally overrides preprocessing stages and declares which metric stages to run. |
| **Corpus** | A directory or manifest of prompt files used for benchmarking. |
| **Benchmark run** | Executes one or more pipelines against a corpus. All pipeline metrics are calculated and flushed to the metrics emitter, plus per-stage and overall latency. |

## Two-phase architecture

Every pipeline runs in two phases:

### Phase 1: Preprocessing (implicit, always runs)

```
chunker → classifier → embedder
```

- Produces: chunks, classified instructions (with is_instruction flag), embeddings
- Always runs in this order — metric stages depend on it
- Pipelines can swap individual preprocessing stages for variants

### Phase 2: Metrics (configurable per pipeline)

Each metric stage receives the full preprocessed context and writes its own
keys to the result:

| Metric stage | Result keys |
|-------------|-------------|
| `redundancy` | `redundancy_groups`, `redundancy_ratio` |
| `contradiction` | `contradictions`, `contradiction_count` |
| `scorer` | `instruction_count`, `token_count`, `severity`, ... |

Metric stages are independent and safe for parallel execution — the runner
may execute them concurrently. Omitting a metric stage means its keys are
absent from the result.

## Example YAML

```yaml
stages:
  # Define variants of built-in stages with config overrides
  chunker-strict:
    base: chunker
    config:
      min_chunk_words: 3
      split_semicolons: true

  fast-classifier:
    base: classifier
    config:
      classification_threshold: 0.70
      model: "typeform/distilbert-base-uncased-mnli"   # smaller model

  skip-contradiction-short:
    base: contradiction
    config:
      min_instructions: 10   # below this, return empty defaults without running NLI

pipelines:
  default:
    # preprocessing uses built-in defaults
    metrics: [redundancy, contradiction, scorer]

  strict:
    preprocessing:
      chunker: chunker-strict    # swap in the stricter chunker
    metrics: [redundancy, contradiction, scorer]

  fast:
    preprocessing:
      classifier: fast-classifier
    metrics: [redundancy, scorer]
    # no contradiction — trades accuracy for speed

  minimal:
    metrics: [scorer]
    # just instruction count, token count, severity

benchmarks:
  compare-pipelines:
    pipelines: [default, strict, fast]
    corpus: ./fixtures/bench_corpus/
    metrics: [latency_p50, latency_p99, instruction_count, redundancy_ratio, contradiction_count]
    repeat: 5
```

## Example results

```json
// "default" — all metric stages
{
  "instruction_count": 42,
  "token_count": 3800,
  "redundancy_groups": ["..."],
  "redundancy_ratio": 0.15,
  "contradictions": ["..."],
  "contradiction_count": 2,
  "severity": "high"
}

// "fast" — no contradiction keys
{
  "instruction_count": 42,
  "token_count": 3800,
  "redundancy_groups": ["..."],
  "redundancy_ratio": 0.15,
  "severity": "medium"
}

// "minimal" — scorer only
{
  "instruction_count": 42,
  "token_count": 3800,
  "severity": "low"
}
```

## Open questions

~~1. **Stage interface contract** — resolved: preprocessing is a fixed chain
   with known types, metric stages all consume the same preprocessed context
   and write to their own result keys.~~

~~2. **Custom stage registration** — resolved: not needed. All stages are
   built-in. Customization is through config overrides on existing stages
   (stage variants), not by injecting new code.~~

~~3. **Conditional stages** — resolved: no DSL-level conditionals. Metric
   stages accept config parameters like `min_instructions` and short-circuit
   to fixed defaults (e.g. empty contradictions list) when the input is below
   the threshold. The DSL stays declarative; the optimization is just config.~~

~~4. **Benchmark storage** — resolved: local JSON files. Benchmarks are a
   dev-time activity; a JSON file you can commit or diff is sufficient.
   Storage backend integration (spec 03) can be added later if needed.~~

~~5. **Pipeline inheritance** — resolved: no inheritance. Pipelines are flat
   and explicit. With only 3 metric stages, duplication is minimal and
   readability is better than chasing `extends` chains.~~

~~6. **Warm-up** — resolved: separate warm-up pass. The benchmark runner
   executes each pipeline once with a dummy input before starting the clock.
   Explicit and avoids wasting measured iterations.~~
