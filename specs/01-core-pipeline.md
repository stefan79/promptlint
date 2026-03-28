# promptlint — Specification v1.0

## Overview

`promptlint` is a Python library and CLI that analyzes assembled LLM prompts to count discrete behavioral instructions, detect redundancy, identify contradictions, and score structural complexity. It uses encoder-based NLP models — not regex heuristics or LLM calls — to produce deterministic, fast, reproducible analysis.

The tool answers two questions teams cannot answer today:

1. **How many discrete behavioral instructions does this prompt contain?**
2. **Do any of them contradict each other?**

---

## Problem Statement

Teams building on LLMs assemble prompts from multiple sources: system prompt templates, skills, constitutions, tool definitions, guardrail blocks, and conversation history. Each source contributes instructions independently. Nobody tracks the aggregate.

A typical production prompt easily exceeds 150 discrete instructions per call. The consequences:

- **Attention dilution** — the model spreads attention across constraint tracking instead of the task
- **Silent instruction dropping** — models quietly ignore instructions beyond a practical cognitive ceiling
- **Contradictions** — independently authored sections produce conflicting directives ("be concise" + "provide comprehensive detail")
- **Redundancy** — the same instruction expressed 3-4 ways across sections wastes tokens and context window
- **Unmeasured drift** — instruction count grows with every skill addition, with no visibility or governance

No existing tool measures this. LLM proxies (LiteLLM, PromptSail) track tokens and cost. Guardrail tools (Prompt Security, Lasso) detect injection and PII. Prompt linters (PromptDoctor) check bias and vulnerability. None decompose a prompt into instruction units or score structural complexity.

---

## Architecture

### Pipeline Overview

```
Input (prompt text)
    │
    ▼
┌──────────────┐
│  1. Chunker  │  Structural segmentation into candidate units
└──────┬───────┘
       │ chunks[]
       ▼
┌──────────────────────┐
│  2. Classifier       │  DeBERTa zero-shot NLI: instruction vs context/example/definition
│     (DeBERTa-v3)     │
└──────┬───────────────┘
       │ instructions[], non_instructions[]
       ▼
┌──────────────────────┐
│  3. Embedder         │  all-MiniLM-L6-v2: encode all instruction chunks
└──────┬───────────────┘
       │ embeddings[]
       ▼
┌──────────────────────────┐
│  4. Redundancy Detector  │  HDBSCAN clustering on embeddings
└──────┬───────────────────┘
       │ clusters[], redundant_groups[]
       ▼
┌──────────────────────────┐
│  5. Contradiction        │  DeBERTa cross-encoder NLI on filtered pairs
│     Detector             │  (pre-filtered by cosine similarity > threshold)
└──────┬───────────────────┘
       │ contradictions[]
       ▼
┌──────────────────────┐
│  6. Scorer           │  Aggregate metrics, section attribution, density
└──────┬───────────────┘
       │
       ▼
    AnalysisResult
```

### Stage 1: Chunker

**Purpose:** Split raw prompt text into candidate instruction units.

**Input:** Raw prompt string (may contain XML tags, markdown, plain text, JSON tool definitions).

**Strategy:** Structural segmentation, not sentence splitting. The chunker uses document structure to find boundaries, then splits within boundaries only when multiple instructions are concatenated.

**Rules:**

1. **XML-tagged blocks** — split on opening/closing tags. Each `<section>`, `<rule>`, `<instruction>` etc. becomes a boundary. Content within a tag is a candidate chunk.
2. **Markdown headers** — each `#`, `##`, `###` etc. starts a new section. Content between headers is further split by the rules below.
3. **Bullet points and numbered lists** — each list item is a candidate chunk.
4. **Paragraph breaks** — double newline creates a boundary.
5. **Sentence-level splitting within chunks** — split on semicolons unconditionally (they almost always separate independent directives). Do NOT split on coordinating conjunctions ("and", "but", "or") — compound instructions like "be concise and professional" are better kept as a single chunk and let the classifier (Stage 2) handle them as one unit. This avoids the circular dependency of needing a mini-classifier inside the chunker.
6. **Tool definition blocks** — JSON `tools` arrays are parsed. Each tool's `description` field is extracted and chunked separately. Parameter-level `description` fields are extracted if they contain behavioral directives.
7. **Minimum chunk size** — chunks shorter than 2 words are merged with their nearest neighbor. The previous threshold of 4 words incorrectly merged valid short instructions like "Be concise." or "No jargon." — this conflicts with the over-segmentation principle. At 2 words, only true fragments (articles, conjunctions) get merged.

**Output:** `List[Chunk]` where each `Chunk` has:

```python
@dataclass
class Chunk:
    text: str                  # the chunk content
    source_section: str        # which prompt section it came from
    start_offset: int          # character offset in original text
    end_offset: int            # character offset in original text
    structural_type: str       # "bullet", "paragraph", "xml_block", "tool_desc", "header_content"
```

**Over-segmentation is preferred.** It is better to produce two chunks that get merged in Stage 4 (redundancy detection) than one chunk that masks two independent instructions.

### Stage 2: Classifier

**Purpose:** Label each chunk as `instruction` or `non_instruction`.

**Model:** `microsoft/deberta-v3-base-mnli` (zero-shot NLI mode).

**Method:** For each chunk, construct NLI premise-hypothesis pairs using multiple hypothesis templates to avoid a single fragile framing:

```
Premise: <chunk text>

Instruction hypotheses (take max score):
  H1: "This is a behavioral instruction or constraint for an AI assistant."
  H2: "This is a rule or directive that must be followed."
  H3: "This text tells the AI what to do or not do."

Non-instruction hypothesis:
  H_neg: "This is background context, a definition, or an example."
```

Run all hypotheses through the NLI model. Score = softmax over entailment logits. The instruction score is `max(score(H1), score(H2), score(H3))` — using max across templates catches instructions that match different framings (e.g., "Format: JSON" matches H2 better than H1).

**Classification rule:**

```
if max(score(H1), score(H2), score(H3)) > threshold → label = "instruction"
else → label = "non_instruction"
```

**Threshold:** Default `0.65`. Configurable. Provisional — must be calibrated against real-world prompts (see Threshold Calibration Tests). Lower values catch softer instructions ("The tone should reflect our brand values") at the cost of some false positives. Higher values restrict to explicit imperatives.

**Batch processing:** All chunks are batched for GPU/CPU inference in a single forward pass. Padding to max length within the batch.

**Output:** Each `Chunk` gets an additional field:

```python
@dataclass
class ClassifiedChunk(Chunk):
    label: str           # "instruction" or "non_instruction"
    confidence: float    # classification confidence [0, 1]
```

### Stage 3: Embedder

**Purpose:** Generate dense vector representations of all instruction-classified chunks for similarity comparison.

**Model:** `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional embeddings).

**Input:** Only chunks where `label == "instruction"`.

**Output:** `np.ndarray` of shape `(n_instructions, 384)`.

**Notes:**
- Normalize embeddings to unit length for cosine similarity computation via dot product.
- Batch all instructions in a single encode call.

### Stage 4: Redundancy Detector

**Purpose:** Group semantically equivalent instructions to compute unique instruction count and identify wasted tokens.

**Method:** Adaptive strategy based on instruction count:

- **When `n_instructions >= 20`:** HDBSCAN clustering on the embedding matrix from Stage 3.
- **When `n_instructions < 20`:** Pairwise cosine similarity with a threshold of `0.80`. Group instructions where similarity exceeds the threshold using single-linkage. HDBSCAN is unreliable on small datasets in high-dimensional space — pairwise comparison is both simpler and more accurate here.

**HDBSCAN parameters (n >= 20):**

```python
hdbscan.HDBSCAN(
    min_cluster_size=2,        # minimum 2 instructions to form a redundancy group
    min_samples=1,             # allow small clusters
    metric='cosine',           # use cosine distance
    cluster_selection_epsilon=0.20  # merge clusters within this cosine distance (similarity > 0.80)
)
```

**Note:** `cluster_selection_epsilon` is set to `0.20` (cosine distance), corresponding to similarity > 0.80. The previous value of `0.15` (similarity > 0.85) was too strict and missed near-duplicates like "be concise" vs "keep responses brief" which typically land at ~0.78-0.82 similarity. This threshold is provisional and should be validated against the calibration corpus.

**Output:**

```python
@dataclass
class RedundancyGroup:
    canonical: ClassifiedChunk       # representative instruction (highest confidence)
    duplicates: List[ClassifiedChunk] # other instructions saying the same thing
    similarity: float                 # mean pairwise similarity within group
```

**Unique instruction count** = total instruction count - sum of duplicates across all groups.

**Noise handling:** HDBSCAN labels unclustered points as noise (-1). These are unique instructions with no redundant counterpart. They count toward unique instruction count.

### Stage 5: Contradiction Detector

**Purpose:** Find pairs of instructions that impose conflicting behavioral requirements.

**Model:** `microsoft/deberta-v3-base-mnli` (cross-encoder NLI mode, same model as Stage 2).

**Pre-filtering:** Computing NLI on all instruction pairs is O(n²). For n=150 instructions, that's 11,175 pairs — expensive. Pre-filter using two complementary strategies (union):

1. **Embedding similarity:** Compute cosine similarity matrix from Stage 3 embeddings. Select pairs where `cosine_similarity > 0.3`.
2. **Keyword overlap:** Extract content nouns and verbs from each instruction (stopword-filtered). Select pairs that share at least 1 content word. This catches semantic opposites that have low embedding similarity but discuss the same topic — e.g., "always use formal language" vs "be casual and conversational" both contain "language"-adjacent terms but may land at cosine similarity < 0.3.
3. Exclude pairs within the same redundancy group (already identified as equivalent).
4. Deduplicate the union of strategy 1 and 2.

This typically reduces pairs from ~11K to ~300-700.

**NLI classification:** For each filtered pair (A, B), run:

```
Premise: A
Hypothesis: B
→ scores for: entailment, neutral, contradiction
```

AND the reverse:

```
Premise: B
Hypothesis: A
→ scores for: entailment, neutral, contradiction
```

**Aggregation:** `contradiction_score = max(forward_contradiction, reverse_contradiction)`. Using max (not mean) because contradiction may be directional — "be concise" contradicts "provide comprehensive detail" more strongly than the reverse.

**Minimum reverse gate:** To reduce false positives from asymmetric scores, require `min(forward_contradiction, reverse_contradiction) > 0.4`. A pair where one direction scores 0.71 but the reverse scores 0.15 is likely noise, not a genuine contradiction.

**Threshold:** Report pairs where `contradiction_score > 0.7` AND `min(forward, reverse) > 0.4`. Both thresholds are configurable and provisional — calibrate against the contradiction test corpus.

**Output:**

```python
@dataclass
class Contradiction:
    instruction_a: ClassifiedChunk
    instruction_b: ClassifiedChunk
    score: float                    # contradiction confidence [0, 1]
    direction: str                  # "a_contradicts_b", "b_contradicts_a", or "bidirectional"
```

### Stage 6: Scorer

**Purpose:** Aggregate all analysis into a single result object with governance-relevant metrics.

**Metrics:**

| Metric | Formula | Description |
|--------|---------|-------------|
| `instruction_count` | count(label == instruction) | Raw instruction count |
| `unique_instruction_count` | instruction_count - total_duplicates | After deduplication |
| `redundancy_ratio` | 1 - (unique / raw) | Fraction of instructions that are redundant |
| `contradiction_count` | count(contradictions) | Number of contradicting pairs |
| `density` | instruction_count / (total_tokens / 1000) | Instructions per 1K tokens |
| `section_distribution` | dict[section → count] | Instructions per prompt section |
| `max_section_density` | max(section_density values) | Hottest section |

**Token counting:** Use `tiktoken` with `cl100k_base` encoding (GPT-4/Claude compatible). This is for the density metric only — the actual instruction detection is encoder-based, not token-based.

**Output:**

```python
@dataclass
class AnalysisResult:
    # Counts
    instruction_count: int
    unique_instruction_count: int
    non_instruction_count: int
    total_chunks: int

    # Rates
    density: float                           # instructions per 1K tokens
    redundancy_ratio: float                  # 0.0 = no redundancy, 1.0 = all redundant

    # Detail
    instructions: List[ClassifiedChunk]
    non_instructions: List[ClassifiedChunk]
    redundant_groups: List[RedundancyGroup]
    contradictions: List[Contradiction]

    # Section breakdown
    section_distribution: Dict[str, int]     # section_name → instruction count
    section_density: Dict[str, float]        # section_name → instructions per 1K tokens

    # Governance
    warnings: List[str]                      # human-readable warning messages
    severity: str                            # "ok", "warning", "critical"
```

**Severity rules (defaults, configurable):**

```
ok:       instruction_count < 80 AND density < 60 AND contradiction_count == 0
warning:  instruction_count 80-150 OR density 60-90 OR contradiction_count 1-3
critical: instruction_count > 150 OR density > 90 OR contradiction_count > 3
```

**Threshold rationale:** These thresholds are grounded in empirical research, not guesswork:

- **80 (warning):** Models with linear decay patterns (e.g., Claude Sonnet, GPT-4.1) show measurable degradation from instruction #1 onward. At 80 instructions, even a 97% per-instruction compliance rate yields only ~9% probability of following all instructions simultaneously (P = 0.97^80 ≈ 0.09) per the "Curse of Instructions" formula P(all) = P(individual)^n [1].
- **150 (critical):** The IFScale benchmark [2] found that reasoning models (o3, Gemini 2.5 Pro) maintain near-perfect accuracy until ~150 instructions, then exhibit "threshold decay" with sharp performance drops and rising variance. This is the empirically observed inflection point where even the best models begin systematic failure. At 150 instructions with 95% individual accuracy, P(all) = 0.95^150 ≈ 0.0005.
- **Density thresholds (60/90):** Derived from observed prompt structures — high-density prompts pack more instructions per token, leaving less room for context and examples between directives. No direct research citation; these remain provisional.
- **Contradiction thresholds:** Based on the observation that contradictions force the model to silently resolve conflicts, consuming attention budget unpredictably. Even a single contradiction can flip behavior between calls. No direct citation; these remain provisional.

---

## Model Stack

| Component | Model | Size | Inference | Purpose |
|-----------|-------|------|-----------|---------|
| Classifier | microsoft/deberta-v3-base-mnli | 184M params, ~700MB | CPU: ~50ms/batch | Instruction vs non-instruction |
| Embedder | sentence-transformers/all-MiniLM-L6-v2 | 22M params, ~90MB | CPU: ~20ms/batch | Chunk similarity |
| Contradiction | microsoft/deberta-v3-base-mnli | (same model) | CPU: ~80ms/batch | NLI on instruction pairs |
| Clustering | hdbscan | n/a | CPU: <5ms | Redundancy grouping |
| Tokenizer | tiktoken (cl100k_base) | n/a | CPU: <1ms | Density metric |

**Total model footprint:** ~800MB on disk, ~1.2GB in memory (single model loaded once, shared between classifier and contradiction stages).

**No GPU required.** All inference runs on CPU within the latency budget.

---

## Performance Budget

Target: **< 200ms** for a 10K token prompt on a modern CPU (M-series Mac or 4-core x86).

| Stage | Time (CPU) | Notes |
|-------|-----------|-------|
| Chunking | < 5ms | String operations only |
| Classification | ~ 50ms | Batched, 300 chunks |
| Embedding | ~ 20ms | Batched, ~150 instruction chunks |
| Clustering | < 5ms | HDBSCAN on 150×384 matrix |
| Pre-filtering | < 2ms | Cosine similarity matrix + threshold |
| Contradiction detection | ~ 120ms | ~300-700 pairs (embedding + keyword pre-filter union), batched |
| Scoring | < 2ms | Aggregation |
| **Total** | **< 210ms** | |

**Cold start:** First call loads models (~3-5s). Subsequent calls reuse cached models. For proxy mode, models stay warm in memory.

---

## Input Format

The library accepts prompts in multiple formats:

### 1. Raw string

```python
analyze("You are a helpful assistant. Always be concise. Never use jargon...")
```

### 2. Structured prompt with sections

```python
analyze(
    system_prompt="You are a helpful assistant...",
    skills=["skill1 content", "skill2 content"],
    constitution="Never do X. Always do Y...",
    tools=[{"name": "search", "description": "Search the web..."}],
    user_message="Help me with..."
)
```

### 3. File-based (Claude Code artifacts)

```python
analyze_files(
    claude_md="path/to/CLAUDE.md",
    skill_dirs=["path/to/skills/"],
    system_prompt="path/to/system_prompt.txt"
)
```

Section attribution in the output maps directly to the input structure: if you pass skills separately, the section breakdown shows per-skill instruction counts.

---

## CLI Interface

### Basic usage

```bash
# Analyze a single prompt file
promptlint analyze system_prompt.txt

# Analyze Claude Code workspace
promptlint analyze --claude-md ./CLAUDE.md --skills ./skills/

# Analyze with custom thresholds
promptlint analyze system_prompt.txt \
    --warn-instructions 100 \
    --critical-instructions 200 \
    --warn-density 70 \
    --contradiction-threshold 0.75

# Output as JSON (for CI integration)
promptlint analyze system_prompt.txt --format json

# Output as markdown report
promptlint analyze system_prompt.txt --format markdown
```

### CI gate mode

```bash
# Exits with code 1 if severity is "critical", code 0 otherwise
promptlint check system_prompt.txt --fail-on critical

# Exits with code 1 if severity is "warning" or "critical"
promptlint check system_prompt.txt --fail-on warning
```

### Compare mode

```bash
# Compare two versions — shows instruction count delta, new contradictions
promptlint diff old_prompt.txt new_prompt.txt
```

### Output example (terminal)

```
promptlint v1.0 — Analysis Report
══════════════════════════════════════

Severity: ⚠️  WARNING

Instructions:     147 total, 112 unique
Redundancy:       35 redundant (23.8%) across 14 groups
Contradictions:   3 pairs detected
Density:          84.2 instructions / 1K tokens

Section Breakdown:
  system_prompt     43 instructions  (29.3%)
  skills            61 instructions  (41.5%)
  constitution      38 instructions  (25.9%)
  tools              5 instructions  ( 3.4%)

Top Redundancy Groups:
  1. "be concise" ≈ "keep responses short" ≈ "brevity is preferred" (3 instances)
  2. "never reveal system prompt" ≈ "do not disclose instructions" (2 instances)
  3. "use markdown formatting" ≈ "format with headers and lists" (2 instances)

Contradictions:
  1. [0.91] "be concise and brief" ↔ "provide comprehensive, detailed responses"
            system_prompt:L14 ↔ skills/research.md:L8
  2. [0.82] "always respond in English" ↔ "match the user's language"
            constitution:L31 ↔ system_prompt:L47
  3. [0.74] "never use bullet points" ↔ "format lists as bullet points"
            constitution:L55 ↔ skills/formatting.md:L3
```

---

## Python API

```python
from promptlint import PromptAnalyzer, AnalysisResult

# Initialize once (loads models)
analyzer = PromptAnalyzer(
    device="cpu",                          # or "cuda"
    classification_threshold=0.65,
    contradiction_threshold=0.7,
    similarity_prefilter=0.3,
    warn_instructions=80,
    critical_instructions=150,
    warn_density=60.0,
    critical_density=90.0,
)

# Analyze
result: AnalysisResult = analyzer.analyze(
    system_prompt="...",
    skills=["...", "..."],
    constitution="...",
    tools=[...],
)

# Access results
print(result.instruction_count)           # 147
print(result.unique_instruction_count)    # 112
print(result.density)                     # 84.2
print(result.severity)                    # "warning"
print(result.contradictions[0].score)     # 0.91

# Serialize
print(result.to_json())
print(result.to_markdown())

# Integration: raise if critical
result.raise_if(severity="critical")  # raises PromptLintError if severity >= critical
```

---

## Integration Surfaces

### 1. Reverse Proxy (primary)

Promptlint runs as a local HTTP reverse proxy that sits between Claude Code (or any LLM client) and the Anthropic API. This is the primary integration because it sees the **full assembled request** — system prompt, tools, complete message history — on every API call.

**Setup:**

```bash
# Start the proxy (models are loaded once, stay warm in memory)
promptlint proxy --port 8100 --target https://api.anthropic.com

# Point Claude Code at the proxy
export ANTHROPIC_BASE_URL=http://localhost:8100
claude
```

Or persist in Claude Code settings (`~/.claude/settings.json`):

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:8100"
  }
}
```

**Proxy behavior:**

1. Receives the full Anthropic API request (`/v1/messages`)
2. Extracts `system`, `tools`, and `messages` from the request body
3. Runs the promptlint analysis pipeline (~210ms)
4. Adds analysis headers to the forwarded request:
   - `X-Promptlint-Instructions: 147`
   - `X-Promptlint-Unique: 112`
   - `X-Promptlint-Density: 84.2`
   - `X-Promptlint-Severity: warning`
   - `X-Promptlint-Contradictions: 3`
5. **If severity is `critical` and `--fail-on critical` is set:** returns HTTP 422 with the analysis report instead of forwarding the request
6. **Otherwise:** forwards the request to the Anthropic API and streams the response back transparently

**Logging:** Every request is logged with its analysis summary. This provides a time-series of instruction count, density, and contradiction trends across a session.

```
[2026-03-27 14:32:01] POST /v1/messages → 147 instructions (112 unique), density 84.2, severity WARNING, 3 contradictions
[2026-03-27 14:32:15] POST /v1/messages → 149 instructions (113 unique), density 85.1, severity WARNING, 3 contradictions
[2026-03-27 14:33:42] POST /v1/messages → 162 instructions (118 unique), density 91.3, severity CRITICAL — BLOCKED
```

**Implementation:** FastAPI with `httpx` for async forwarding. Supports streaming responses (`text/event-stream`) pass-through.

### 2. CI Pipeline (static analysis)

```yaml
# GitHub Actions
- name: Promptlint Check
  run: |
    promptlint check \
      --claude-md ./CLAUDE.md \
      --skills ./skills/ \
      --fail-on warning \
      --format json > prompt-report.json

- name: Upload Report
  uses: actions/upload-artifact@v4
  with:
    name: promptlint-report
    path: prompt-report.json
```

### 3. LiteLLM Callback Plugin (alternative for LiteLLM users)

```python
from litellm.integrations.custom_callback import CustomCallback
from promptlint import PromptAnalyzer

class PromptLintCallback(CustomCallback):
    def __init__(self):
        self.analyzer = PromptAnalyzer()

    async def async_pre_call_hook(self, kwargs, completion_response, start_time, end_time):
        messages = kwargs.get("messages", [])
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        tools = kwargs.get("tools", [])

        result = self.analyzer.analyze(system_prompt=system, tools=tools)

        # Add headers for passthrough logging
        kwargs.setdefault("extra_headers", {})
        kwargs["extra_headers"]["X-Prompt-Instructions"] = str(result.instruction_count)
        kwargs["extra_headers"]["X-Prompt-Density"] = f"{result.density:.1f}"
        kwargs["extra_headers"]["X-Prompt-Severity"] = result.severity

        if result.severity == "critical":
            raise Exception(f"Prompt blocked: {result.instruction_count} instructions, density {result.density:.1f}")
```

### 4. MCP Tool (for in-session analysis)

Expose as an MCP tool so Claude Code or other MCP clients can call it during a session:

```json
{
  "name": "promptlint_analyze",
  "description": "Analyze the current prompt assembly for instruction count, contradictions, and density",
  "input_schema": {
    "type": "object",
    "properties": {
      "prompt_text": { "type": "string" },
      "sections": {
        "type": "object",
        "properties": {
          "system_prompt": { "type": "string" },
          "skills": { "type": "array", "items": { "type": "string" } },
          "constitution": { "type": "string" }
        }
      }
    }
  }
}
```

---

## Dependencies

### Runtime

```
torch >= 2.0              # model inference
transformers >= 4.36      # DeBERTa
sentence-transformers     # MiniLM embedder
hdbscan >= 0.8.33         # clustering
tiktoken                  # token counting for density metric
numpy                     # array operations
scikit-learn              # cosine similarity matrix
fastapi                   # reverse proxy server
uvicorn                   # ASGI server
httpx                     # async HTTP client for forwarding requests
```

### Development

```
pytest
pytest-benchmark          # latency regression tests
ruff                      # linting
```

### Optional

```
litellm                   # LiteLLM callback plugin mode
```

---

## File Structure

```
promptlint/
├── pyproject.toml
├── README.md
├── src/
│   └── promptlint/
│       ├── __init__.py           # public API: PromptAnalyzer, AnalysisResult
│       ├── chunker.py            # Stage 1: structural segmentation
│       ├── classifier.py         # Stage 2: DeBERTa zero-shot instruction classification
│       ├── embedder.py           # Stage 3: MiniLM embedding
│       ├── redundancy.py         # Stage 4: HDBSCAN clustering
│       ├── contradiction.py      # Stage 5: NLI cross-encoder contradiction detection
│       ├── scorer.py             # Stage 6: metric aggregation
│       ├── models.py             # dataclasses: Chunk, ClassifiedChunk, etc.
│       ├── prompt_parser.py      # input parsing: raw string, structured, file-based
│       ├── config.py             # thresholds, defaults
│       ├── proxy.py              # FastAPI reverse proxy with analysis middleware
│       └── cli.py                # CLI entry point (analyze, check, diff, proxy commands)
├── tests/
│   ├── test_chunker.py
│   ├── test_classifier.py
│   ├── test_redundancy.py
│   ├── test_contradiction.py
│   ├── test_scorer.py
│   ├── test_integration.py       # end-to-end on sample prompts
│   └── fixtures/
│       ├── simple_prompt.txt
│       ├── complex_prompt.txt    # 150+ instructions
│       ├── contradictory.txt     # known contradictions
│       └── claude_md_sample.md   # real CLAUDE.md example
└── benchmarks/                  # see spec 07
    └── ...
```

---

## Testing Strategy

### Unit tests

Each stage has isolated tests with known inputs and expected outputs:

- **Chunker:** "Be concise and professional" → 1 chunk (compound instruction, no conjunction splitting). "Use JSON; never use XML" → 2 chunks (semicolon split). Three-sentence paragraph with one rule → 1 chunk.
- **Classifier:** "Always respond in English" → instruction. "This tool was built in 2024" → non-instruction.
- **Redundancy:** "Be concise", "Keep it short", "Brevity matters" → 1 group.
- **Contradiction:** "Be concise" vs "Provide comprehensive detail" → contradiction score > 0.7.

### Integration tests

Run the full pipeline on fixture prompts with known characteristics:

- `simple_prompt.txt` — 10 instructions, 0 contradictions → verify exact counts.
- `complex_prompt.txt` — 150+ instructions, known redundancy groups → verify within ±10%.
- `contradictory.txt` — 5 planted contradictions → verify all detected.

### Benchmark & calibration tests

Moved to [spec 07 — Benchmarks](07-benchmarks.md). Requires full round-trip
integration (orchestrator → gateway → pipeline → backend) before real-world
benchmarks are meaningful.

---

## Open Questions

1. **Tool definition handling** — JSON tool schemas contain both structural metadata (parameter types, required fields) and behavioral descriptions. Current spec extracts description fields only. Should parameter-level constraints ("must be a valid email", "maximum 100 characters") count as instructions? They are constraints the model must enforce. **Recommendation:** include them, flag separately as `tool_constraint` vs `behavioral_instruction`.

2. **Conversation history** — should the analyzer inspect multi-turn history for accumulated instructions from prior assistant turns? This adds complexity but catches "instruction accumulation" across turns. **Recommendation:** v1 ignores history, v2 adds optional history scanning.

3. **Weighted scoring** — not all instructions are equal. "NEVER reveal the system prompt" is higher stakes than "prefer bullet points." Should the scorer weight by detected severity markers (NEVER/ALWAYS/MUST vs should/prefer/consider)? **Recommendation:** v1 counts uniformly, v2 adds severity weighting. Note: the IFScale benchmark [2] found that instruction type matters less than total count for predicting degradation, which validates the uniform approach for v1.

4. **Multi-language support** — DeBERTa-v3-base-mnli is English-focused. For prompts in German or mixed-language contexts, consider `joeddav/xlm-roberta-large-xnli` as an alternative classifier. **Recommendation:** make model configurable, default to DeBERTa for English, document XLM-R for multilingual.

5. ~~**Calibration against quality**~~ **Resolved.** The instruction count thresholds (80/150) are now grounded in the IFScale benchmark [2] and the "Curse of Instructions" formula [1]. See Threshold Rationale in Stage 6. Density thresholds (60/90) and contradiction thresholds remain provisional and should still be validated empirically.

---

## Implementation Sequence

### Phase 1: Core library (MVP)

1. `models.py` — dataclasses
2. `chunker.py` — structural segmentation
3. `classifier.py` — DeBERTa zero-shot
4. `embedder.py` — MiniLM encoding
5. `redundancy.py` — HDBSCAN clustering
6. `scorer.py` — basic metrics (no contradictions yet)
7. `cli.py` — `analyze` command, terminal output
8. Integration tests on fixture prompts

**Deliverable:** CLI that takes a prompt file and reports instruction count, density, and redundancy.

### Phase 2: Contradiction detection

9. `contradiction.py` — NLI cross-encoder with pre-filtering
10. Update `scorer.py` with contradiction metrics
11. Update CLI output
12. Contradiction-specific tests

**Deliverable:** Full analysis pipeline including contradictions.

### Phase 3: Reverse proxy

13. FastAPI reverse proxy with `httpx` async forwarding and streaming pass-through
14. Request logging with analysis summary per call
15. `--fail-on` blocking mode (HTTP 422 on critical severity)
16. JSON and markdown output formats for CLI and proxy responses

**Deliverable:** `promptlint proxy` command — point Claude Code at it via `ANTHROPIC_BASE_URL` for live analysis of every API call.

### Phase 4: Additional integrations

17. CI pipeline example (GitHub Actions) for static analysis of prompt files
18. `diff` command for version comparison
19. LiteLLM callback plugin (for teams already using LiteLLM)

**Deliverable:** CI gates and alternative proxy integrations.

---

## References

[1] **"Curse of Instructions: LLMs Cannot Follow Multiple Instructions at Once"** — Tingyu Zhu et al., EMNLP 2024 Findings. Introduces ManyIFEval benchmark and the formula P(all) = P(individual)^n. Demonstrates that GPT-4o drops to 15% success on 10 simultaneous instructions. https://aclanthology.org/2024.findings-emnlp.637.pdf

[2] **"IFScale: How Many Instructions Can LLMs Follow at Once?"** — Jaroslawicz et al., Distyl AI, 2025. Tests 20 frontier models on up to 500 simultaneous instructions. Identifies three degradation patterns (threshold decay, linear decay, exponential decay) and the ~150-instruction inflection point for reasoning models. https://arxiv.org/abs/2507.11538

[3] **"IFEval: Instruction-Following Evaluation for Large Language Models"** — Zhou et al., Google, 2023. Foundational benchmark with 25 types of verifiable instructions. Defines the instruction categories used across subsequent research. https://arxiv.org/abs/2311.07911

[4] **"Lost in the Middle: How Language Models Use Long Contexts"** — Liu et al., 2023. Demonstrates the U-shaped attention curve: information in the middle of long contexts is retrieved least reliably. Relevant to instruction positioning within prompts. https://arxiv.org/abs/2307.03172

[5] **"Cognitive Load Limits in Large Language Models"** — ICE benchmark, 2024. Formalizes computational cognitive load theory for LLMs. Shows that context saturation and attentional residue degrade multi-hop reasoning before context windows are exhausted. https://arxiv.org/pdf/2509.19517

[6] **"Effective Context Engineering for AI Agents"** — Anthropic, 2025. Frames all prompt content as drawing from a "finite attention budget" and recommends "the smallest possible set of high-signal tokens." https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents

[7] **"RAG-MCP: Mitigating Prompt Bloat in LLM Tool Selection"** — 2025. Addresses prompt bloat from tool definitions and proposes retrieval-augmented tool selection to reduce instruction count per call. https://arxiv.org/html/2505.03275v1

[8] **"When Instructions Multiply: Measuring and Estimating LLM Capabilities"** — 2025. Tests 10 LLMs with increasing instruction counts; confirms consistent degradation across all model families. https://arxiv.org/abs/2509.21051

[9] **"GPT-4.1 Prompting Guide"** — OpenAI, 2025. Notes that when conflicting instructions exist, the model "tends to follow the one closer to the end of the prompt," confirming positional bias effects. https://developers.openai.com/cookbook/examples/gpt4-1_prompting_guide