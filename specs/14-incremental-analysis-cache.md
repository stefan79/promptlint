# 14 — Incremental Analysis Cache

> Status: **Draft**

## Goal

Reduce per-request latency for gateway proxies by caching analysis of static
prompt components (system prompt, tools, skills) and only analyzing the delta
(new conversation messages) on subsequent requests.

## Problem

Orchestrators like Claude Code send the same system prompt and tool definitions
on every API request. Only the conversation messages change between turns. The
full analysis pipeline — especially O(n^2) contradiction detection — is
prohibitively expensive to run on every request for large prompts (300+
instructions, 30K+ tokens).

## Design

### Cache key

Use the existing `compute_fingerprint()` (spec 05) on the concatenation of:
- System prompt text
- Sorted tool definitions (name + description)

This produces a 16-char hex fingerprint that identifies the static prompt
structure. The cache key is `(gateway_id, fingerprint)`.

### What gets cached

On first request for a given fingerprint:

```python
@dataclass
class CachedAnalysis:
    fingerprint: str
    chunks: list[Chunk]                    # raw structural chunks
    classified: list[ClassifiedChunk]      # instruction/non_instruction labels
    instructions: list[ClassifiedChunk]    # instruction-only subset
    embeddings: np.ndarray                 # (n_instructions, 384) matrix
    redundancy_groups: list[RedundancyGroup]
    original_text: str                     # for token counting
    created_at: str                        # ISO 8601 UTC
    hit_count: int = 0
```

### Incremental analysis flow

```
Request arrives
  |
  v
Fingerprint(system_prompt + tools)
  |
  +-- Cache MISS --> full pipeline, store CachedAnalysis, return result
  |
  +-- Cache HIT -->
        |
        v
      Extract new messages (user/assistant turns not in cache)
        |
        v
      Chunk + classify new messages only
        |
        v
      Embed new instructions only
        |
        v
      Redundancy: merge cached groups + check new instructions against cached
        |
        v
      Contradiction: ONLY check (cached x new) pairs + (new x new) pairs
        |  Skip (cached x cached) — already computed on first request
        |
        v
      Score: merge all instructions for final metrics
```

### Contradiction optimization

This is the key performance win. For n_cached=300 and n_new=5:

| Approach | Pairs | NLI calls |
|----------|-------|-----------|
| Full recompute | ~45,000 | ~90,000 |
| Incremental | ~1,500 + 10 | ~3,020 |
| **Speedup** | | **~30x** |

The pre-filter (embedding similarity > 0.3 + keyword overlap) further reduces
the actual NLI calls to a fraction of the raw pair count.

### Cache eviction

- **LRU with max entries** (default: 16) — one Claude Code session typically
  uses 1-2 fingerprints
- **TTL** (default: 1 hour) — stale entries are evicted on next access
- **Memory cap** — each entry is ~2-5MB (embeddings dominate); 16 entries = ~40-80MB

### Cache scope

The cache is per-`BuiltinProxy` instance (in-memory dict). No shared state
between processes. This is sufficient for single-process proxy deployments.

## Configuration

```yaml
gateway:
  type: builtin-proxy
  cache:
    enabled: true
    max_entries: 16
    ttl_seconds: 3600
```

## Integration points

- `BuiltinProxy._run_analysis()` — check cache before full pipeline
- `PromptAnalyzer` — new method `analyze_incremental(cached, new_messages)`
  that accepts a `CachedAnalysis` and only processes the delta
- `compute_fingerprint()` — reused from spec 05

## Metrics

The proxy should log cache hit/miss status per request:
- `X-Promptlint-Cache: HIT|MISS`
- `X-Promptlint-Cache-Key: <fingerprint>`
- Log: cached instruction count, new instruction count, wall-clock time

## Open questions

1. **Redundancy merging** — when new instructions are near-duplicates of cached
   ones, do we extend existing groups or create new ones? Extending is correct
   but requires updating the cached embeddings matrix.

2. **Contradiction accumulation** — should cached contradictions persist across
   turns, or recompute (cached x new) fresh each time? Persisting is faster but
   may miss contradictions that only emerge in combination with new context.

3. **Message identity** — how do we detect which messages are "new"? Options:
   (a) hash each message and diff against previous request, (b) assume messages
   are append-only and use list length, (c) fingerprint the full message list
   and fall back to full analysis on any change.
