# 02 — Pipeline DSL

> Status: **Draft — open questions below**

## Goal

Define a YAML-based language for composing analysis pipelines from reusable
building blocks (stages). Each pipeline is a named, ordered sequence of stages
with per-stage config overrides. Pipelines can be benchmarked against each other
on the same corpus.

## Core concepts

| Concept | Description |
|---------|-------------|
| **Stage** | A registered, reusable unit of work (e.g. `chunker`, `classifier`, `embedder`, `redundancy`, `contradiction`, `scorer`). Stages from spec 01 are built-in; users can register custom ones. |
| **Pipeline** | A named, ordered list of stages with optional config overrides. |
| **Corpus** | A directory or manifest of prompt files used for benchmarking. |
| **Benchmark run** | Executes one or more pipelines against a corpus, records latency + quality metrics per stage and overall. |

## Example YAML

```yaml
stages:
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

pipelines:
  default:
    stages: [chunker, classifier, embedder, redundancy, contradiction, scorer]

  strict:
    stages: [chunker-strict, classifier, embedder, redundancy, contradiction, scorer]

  fast:
    stages: [chunker, fast-classifier, embedder, redundancy, scorer]
    # note: no contradiction stage — trades accuracy for speed

benchmarks:
  compare-pipelines:
    pipelines: [default, strict, fast]
    corpus: ./fixtures/bench_corpus/
    metrics: [latency_p50, latency_p99, instruction_count, redundancy_ratio, contradiction_count]
    repeat: 5
```

## Open questions

1. **Stage interface contract** — should stages declare their inputs/outputs
   formally (typed ports), or is the current implicit convention (list of chunks
   in, list of chunks out) sufficient?

2. **Custom stage registration** — Python entry-points? A `stages:` section
   pointing to `module:class`? Both?

3. **Conditional stages** — should a pipeline support `if:` guards (e.g. skip
   contradiction detection when instruction count < 10)?

4. **Benchmark storage** — where do benchmark results go? Local JSON? Feed into
   a storage backend from spec 03?

5. **Pipeline inheritance** — should one pipeline be able to extend another
   (`extends: default`) to reduce duplication?

6. **Warm-up** — benchmarks need model warm-up. Separate warm-up pass, or
   discard first N iterations?
