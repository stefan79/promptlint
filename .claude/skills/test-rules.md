---
name: test-rules
description: Testing standards and edge case requirements for writing unit tests
user-invocable: true
allowed-tools: Read, Glob, Grep, Edit, Write, Bash
---

# promptlint Testing Rules

## Required test cases for every function with logic

1. **Happy path** — normal expected input
2. **Empty input** — empty string, empty list, empty dict
3. **Single element** — one chunk, one instruction, one message
4. **None / missing optionals** — every `Optional` / `| None` field
5. **Boundary conditions** — thresholds at exactly the boundary value (e.g. score == 0.65, instruction_count == 80, instruction_count == 150)
6. **Off-by-one** — one above and one below each threshold
7. **Maximum load** — large input (1000+ chunks, 500+ instructions) to verify no quadratic blowup
8. **Malformed input** — invalid XML tags, unclosed brackets, mixed encodings, NaN/inf in numeric fields

## Per-component edge cases

- **Chunker**: nested XML tags, empty tags, XML inside code blocks, bullet with no text, 1-word chunks (below min_chunk_words)
- **Classifier**: chunk that's exactly on the threshold, chunk with no alphabetic characters
- **Embedder**: identical texts (should produce identical embeddings), empty string
- **Redundancy**: all instructions identical (one giant group), no redundancy at all, exactly 20 instructions (threshold between pairwise/HDBSCAN)
- **Contradiction**: instruction contradicting itself, pair just below threshold, pair with one direction only
- **Scorer**: zero instructions (avoid division by zero), zero tokens

## Test style

- `pytest` with plain functions, no class-based tests
- Tests that load ML models: `@pytest.mark.slow`
- Files mirror source: `src/promptlint/foo.py` → `tests/test_foo.py`
- Target 90%+ coverage on non-ML code (`pytest-cov`)
