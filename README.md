# promptlint

Static analysis for assembled LLM prompts. Counts instructions, detects
redundancy and contradictions, scores complexity. Deterministic
(encoder-based NLP, no LLM calls).

## Install

Requires Python 3.10+.

```bash
pip install -e .
```

This installs all dependencies (PyTorch, Transformers, HDBSCAN, etc.) and
the `promptlint` CLI. First run downloads ~350 MB of models from HuggingFace
(DeBERTa for NLI, MiniLM for embeddings).

### Development

```bash
pip install -e ".[dev]"
```

Adds pytest, ruff, and mypy.

## Quick start

### Analyze a prompt file

```bash
promptlint analyze prompt.md
```

Output: instruction count, redundancy groups, contradictions, density, severity.

```bash
promptlint analyze prompt.md --format json
promptlint analyze prompt.md --format markdown
```

### Check with exit code (CI)

```bash
promptlint check prompt.md --fail-on warning
```

Exits with code 1 if severity meets or exceeds the threshold.

### Compare two prompt versions

```bash
promptlint diff old-prompt.md new-prompt.md
```

### Analyze structured input

```bash
promptlint analyze --claude-md ./CLAUDE.md --skills ./skills/
```

## Pipeline DSL

Define reusable analysis pipelines in YAML. Each pipeline has a fixed
preprocessing phase (`chunker -> classifier -> embedder`) and configurable
metric stages.

See [`examples/promptlint.yaml`](examples/promptlint.yaml) for a full example.

### Run a named pipeline

```bash
promptlint pipeline prompt.md --config promptlint.yaml --pipeline fast
```

### Run benchmarks

Compare pipelines against a corpus of prompt files:

```bash
promptlint benchmark --config promptlint.yaml --benchmark compare-all
promptlint benchmark --config promptlint.yaml --benchmark compare-all --output results.json
```

The benchmark runner:
1. Loads all `.md` and `.txt` files from the corpus directory
2. Runs a warm-up pass (excluded from timing)
3. Runs timed iterations and reports latency percentiles + quality metrics

### Pipeline YAML structure

```yaml
stages:
  # Define variants of built-in stages with config overrides
  chunker-strict:
    base: chunker
    config:
      min_chunk_words: 3

pipelines:
  default:
    metrics: [redundancy, contradiction, scorer]

  fast:
    preprocessing:
      classifier: fast-classifier
    metrics: [redundancy, scorer]

benchmarks:
  compare:
    pipelines: [default, fast]
    corpus: ./fixtures/bench_corpus/
    repeat: 5
```

**Built-in preprocessing stages:** `chunker`, `classifier`, `embedder`
**Built-in metric stages:** `redundancy`, `contradiction`, `scorer`

## Reverse proxy

Intercept live LLM API calls and analyze prompts in real time:

```bash
promptlint proxy --port 8100 --target https://api.anthropic.com
```

Then point your client at `http://localhost:8100` instead of the API.
Analysis results are returned as HTTP headers.

## Configuration

All thresholds are configurable via CLI flags:

| Flag | Default | Description |
|------|---------|-------------|
| `--warn-instructions` | 80 | Instruction count for warning severity |
| `--critical-instructions` | 150 | Instruction count for critical severity |
| `--warn-density` | 60.0 | Instructions per 1K tokens for warning |
| `--critical-density` | 90.0 | Instructions per 1K tokens for critical |
| `--classification-threshold` | 0.65 | NLI score to classify as instruction |
| `--contradiction-threshold` | 0.7 | NLI score to flag as contradiction |

## Running tests

```bash
# Fast tests only (no model loading)
pytest -m 'not slow'

# All tests including model-based integration tests
pytest

# With coverage
pytest --cov=promptlint --cov-report=term-missing
```

## Linting

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/
```

A pre-push git hook runs all three checks plus fast tests automatically.
