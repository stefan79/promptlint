# Improvement Backlog

Auto-generated from merged PRs. Tracks improvements needed in skills, agents, CLAUDE.md, and rules.

## Initial Review — Housekeeping (2026-03-29)

### Architect skill missing shared-module guidance

**Trigger:** Code review found duplicated NLI batch inference logic across `classifier.py` and `contradiction.py`, and duplicated model-loading across `__init__.py` and `pipeline.py`.

**Current state:** The architect skill documents the module layout as flat files per stage but has no guidance on extracting shared utilities when multiple stages share logic.

**Impacted files:**
- `.claude/skills/architect.md` — module layout section
- `CLAUDE.md` — module layout diagram

**Suggested fix:** Add to architect skill: "When two or more stages share >5 lines of identical logic (e.g. NLI batch inference, model loading), extract into a shared helper module (e.g. `_nli_helpers.py`, `_model_loader.py`). Update the module layout diagram accordingly."

---

### Code-review skill missing function length for closures/nested functions

**Trigger:** Code review flagged `proxy_messages()` at ~98 lines, but the 40-line rule in the skill doesn't clarify whether closures/nested scopes count separately or as part of the enclosing function.

**Current state:** Code-review skill says: "Functions longer than 40 lines" without clarifying nested function/closure scope.

**Impacted files:**
- `.claude/skills/code-review.md` — Technical Debt section, bullet 4

**Suggested fix:** Clarify: "Functions longer than 40 lines (including closures and nested functions measured individually). For route handlers containing request/response logic, the 40-line limit applies to the logical handler, not the outer closure."

---

### Test-rules skill missing fixture deduplication guidance

**Trigger:** Code review found `_make_instruction` helper duplicated across 3 test files. The test-rules skill says nothing about shared test utilities.

**Current state:** Test-rules skill covers test structure (plain functions, slow markers, edge cases) but not shared fixtures.

**Impacted files:**
- `.claude/skills/test-rules.md` — missing section on shared fixtures

**Suggested fix:** Add: "When a test helper or factory is used in 2+ test files, extract it to `conftest.py` as a pytest fixture. Prefer factory fixtures (returning a callable) over direct fixtures to allow per-test customization."

---

### CLAUDE.md missing encoding standard for file I/O

**Trigger:** Code review found `open()` calls without `encoding="utf-8"` in `cli.py`. No coding standard mentions encoding.

**Current state:** Python coding standards in CLAUDE.md cover type safety, formatting, and testing but not file I/O encoding.

**Impacted files:**
- `CLAUDE.md` — Python coding standards section

**Suggested fix:** Add to Python best practices: "Always pass `encoding='utf-8'` to `open()` for text files. Never rely on platform-default encoding."

---

### Test-coverage skill missing assertion strength check

**Trigger:** Test coverage review found `assert instruction_count >= 0` (trivially true) and missing `p99 >= p50` invariant checks.

**Current state:** Test-coverage skill checks that "Tests assert specific values, not just 'no exception'" but doesn't flag trivially-true assertions or missing invariant checks.

**Impacted files:**
- `.claude/skills/test-coverage.md` — Test Quality section

**Suggested fix:** Add to test quality checks: "Flag trivially-true assertions (e.g. `>= 0` for unsigned counts). Flag missing invariant assertions where mathematical relationships must hold (e.g. `p99 >= p50`, `unique <= total`)."

---

### Architect skill references future files that don't exist

**Trigger:** Skill review noted architect skill's file organization shows `stages/` subdirectory and `payload.py` that are not yet implemented.

**Current state:** Architect skill module layout includes planned-but-unimplemented files without marking them as future/planned.

**Impacted files:**
- `.claude/skills/architect.md` — file organization section

**Suggested fix:** Mark unimplemented paths with `(planned — spec XX)` suffix so reviewers don't flag missing files as bugs. Update as specs are implemented.

## PR #2 — Spec 03 Storage Backends Review (2026-03-29)

### Architect skill AnalysisResult diverges from implementation

**Trigger:** Code review found that architect skill defines `AnalysisResult` with
`id`, `timestamp`, `prompt_fingerprint`, `orchestrator: OrchestratorInfo`,
`gateway: GatewayInfo`, `model: ModelInfo`, `severity: Severity` (Enum), and
`metrics: dict[str, float]`. The actual `models.py` has a flat structure with
`severity: str`, `instruction_count: int`, `density: float`, etc. — none of the
rich gateway/orchestrator fields exist yet.

**Current state:** Architect skill shows the target architecture without
distinguishing current vs. future fields. The naming note added for
`AnalysisResult` vs `AnalysisPayload` helps, but field-level divergence is not
flagged.

**Impacted files:**
- `.claude/skills/architect.md` — AnalysisResult definition

**Suggested fix:** Split the AnalysisResult section into "Current fields
(spec 01)" and "Planned additions (specs 04-08)". This prevents implementers
from building against aspirational fields and makes the migration path explicit
when later specs are implemented.

---

### Spec-review skill missing error handling readiness check

**Trigger:** Five code reviews all flagged that emitters use bare `urlopen()`
with no error handling. Spec 03 says nothing about failure behavior. The
spec-review skill checks "error cases specified?" but this was too generic to
catch the gap for network-dependent backends.

**Current state:** Spec-review skill section 5 (Implementation Readiness) asks
"Are error cases and edge cases specified?" without specific prompts for network
backends.

**Impacted files:**
- `.claude/skills/spec-review.md` — section 5 (Implementation Readiness)
- `specs/03-storage-backends.md` — missing error handling section

**Suggested fix:** Add to spec-review.md section 5: "For backends that make
network calls, does the spec define behavior on connection failure, timeout, and
HTTP error responses? (retry? raise? log-and-continue?)"

---

### Test-rules skill missing emitter edge cases

**Trigger:** Test coverage for emitters has gaps: no tests for write-after-close
(except SQLite), no tests for network failures, no tests for special characters
in data, no tests for large payloads.

**Current state:** Test-rules skill defines per-component edge cases for pipeline
stages (chunker, classifier, embedder, redundancy, contradiction, scorer) but
has no section for emitters.

**Impacted files:**
- `.claude/skills/test-rules.md`

**Suggested fix:** Add "Emitters" subsection under per-component edge cases:
- JSONL: write to read-only path, unicode content, deeply nested dataclasses
- SQLite: write after close, concurrent connections
- ES/Webhook: connection refused, HTTP 500, timeout, malformed URL
- Prometheus: NaN/inf values, empty severity string
- All: empty lists in AnalysisResult, Feedback with empty corrections, missing config keys

---

### Test-rules missing guidance for HTTP mock server pattern

**Trigger:** Three test files (`test_emitter_elasticsearch.py`,
`test_emitter_prometheus.py`, `test_emitter_webhook.py`) each duplicate a
`_CaptureHandler(BaseHTTPRequestHandler)` class with near-identical code for
capturing HTTP requests.

**Current state:** Test-rules says to extract shared helpers to `conftest.py`
(added in initial review) but has no specific guidance for the HTTP mock server
pattern used by network-dependent emitters.

**Impacted files:**
- `.claude/skills/test-rules.md`

**Suggested fix:** Add to test-rules.md: "For emitters and gateways that make
HTTP calls, use a shared capture server fixture in `tests/conftest.py` rather
than duplicating `_CaptureHandler` per test file. The shared fixture should
capture request bodies, paths, and headers."

---

### Architect skill "stateless" convention conflicts with SQLite emitter

**Trigger:** Architect skill says "Emitters are stateless" but SQLite emitter
holds a `sqlite3.Connection` and implements `close()`/context manager. Code
review flagged this contradiction.

**Current state:** Key conventions in architect skill: "Emitters are stateless —
they receive a payload and write it, no buffering."

**Impacted files:**
- `.claude/skills/architect.md` — Key conventions

**Suggested fix:** Amend to: "Emitters are stateless with respect to buffering —
they write immediately on each call. Emitters that hold connections (SQLite,
persistent HTTP sessions) must implement `close()` and `__enter__`/`__exit__`
for resource cleanup."

---

### Spec-review skill missing metric precision check

**Trigger:** Spec 03 defines `promptlint_severity` as "Gauge (labeled, value=1
for active severity)" without specifying the multi-label fan-out pattern (one
gauge per severity level with value 0 or 1). Implementation had to interpret
this.

**Current state:** Spec-review skill checks for ambiguities but has no specific
prompt for metric definitions being precise enough to implement.

**Impacted files:**
- `.claude/skills/spec-review.md` — section 3 (Ambiguities)

**Suggested fix:** Add to section 3: "For specs that define metrics (Prometheus,
OpenTelemetry), check that each metric specifies: exact label names, all
possible label values, and the value semantics (e.g., 'one gauge per severity
level, value=1 for active, 0 for others')."

---

### Spec-review skill missing storage schema readiness check

**Trigger:** SQLite emitter defines a full schema (columns, types, tables) that
is not specified in the spec. Reviewers flagged the gap between spec and
implementation.

**Current state:** Spec-review skill section 5 (Implementation Readiness) checks
"does every interface have concrete field definitions" but storage schemas are
not interfaces.

**Impacted files:**
- `.claude/skills/spec-review.md` — section 5

**Suggested fix:** Add: "For backends with schemas (SQL tables, ES mappings),
does the spec define the schema or at minimum the queryable columns/fields?"

---

### Code-review skill missing CI workflow checks

**Trigger:** CI workflow had shell precedence bug (`A || B && C`), used
`--ignore-missing-imports` globally (negating pyproject.toml overrides), and
post-merge workflow has shell injection risk from unescaped PR body/diff
interpolation.

**Current state:** Code-review skill scopes to Python code. CI workflows are not
in scope. No skill checks workflow quality.

**Impacted files:**
- `.claude/skills/code-review.md`

**Suggested fix:** Add a "CI/CD compliance" section: "Verify CI workflow commands
match tool configs in `pyproject.toml` (e.g., mypy flags, ruff config). Flag
global flag overrides that negate fine-grained config. Check that shell variables
containing untrusted content (PR bodies, diffs) are passed via files/heredocs,
not inline interpolation."

---

### Test-rules missing marker registration chain documentation

**Trigger:** The `integration` marker requires coordinated changes across
`pyproject.toml`, `conftest.py`, and CI workflow. A future developer adding a
new marker would not know all three locations.

**Current state:** Test-rules says "mark slow tests with `@pytest.mark.slow`"
but does not document the full registration chain.

**Impacted files:**
- `.claude/skills/test-rules.md`
- `CLAUDE.md`

**Suggested fix:** Add to test-rules.md: "When adding a new test marker:
(1) register in `pyproject.toml` `[tool.pytest.ini_options].markers`,
(2) add `--<name>` option in `tests/conftest.py` `pytest_addoption`,
(3) add skip logic in `pytest_collection_modifyitems`,
(4) add/update CI job in `.github/workflows/pr-review.yml`."

---

### CLAUDE.md missing mypy flags guidance

**Trigger:** CI workflow runs `mypy src/ --ignore-missing-imports` which globally
suppresses errors that `pyproject.toml` per-module overrides handle selectively.

**Current state:** CLAUDE.md says "`mypy src/` before push" without specifying
flags. No guidance to keep CI flags consistent with pyproject.toml.

**Impacted files:**
- `CLAUDE.md` — Linting section

**Suggested fix:** Add: "`mypy src/` without `--ignore-missing-imports` — use
`pyproject.toml` overrides for third-party packages."

## PR #2 — Implement spec 03: storage backend emitters (2026-03-29)

### Architect skill Feedback definition diverges from implementation

**Trigger:** The architect skill defines `Feedback` with `id: str` (uuid4) and `timestamp: datetime`, but the implementation in `models.py` has no `id` field and uses `timestamp: str` (ISO format string from a default factory). Emitter code and tests build against the actual implementation, not the architect definition.

**Current state:** Architect skill (`architect.md:152-160`) shows:
```python
class Feedback:
    id: str                          # uuid4
    analysis_id: str                 # links to AnalysisResult.id
    timestamp: datetime
```
Implementation (`models.py:44-50`) has no `id`, timestamp is `str`.

**Impacted files:**
- `.claude/skills/architect.md` — Feedback definition

**Suggested fix:** Update the Feedback definition in the architect skill to match the implementation: remove `id` field (or mark as planned), change `timestamp` to `str` with ISO format default. This is the same class of issue as the AnalysisResult divergence — the "current vs. planned" split suggested for AnalysisResult should also apply to Feedback.

---

### CLAUDE.md testing section missing integration test infrastructure

**Trigger:** PR adds `docker-compose.test.yml`, `@pytest.mark.integration` marker, `--integration` pytest flag, integration test directory (`tests/integration/`), and a CI integration job — none of which are documented in CLAUDE.md's testing or linting sections.

**Current state:** CLAUDE.md testing section says: "Tests that load ML models: mark with `@pytest.mark.slow`" and linting section says "`pytest -m 'not slow'` before push". No mention of integration tests, Docker services, or the `tests/integration/` directory.

**Impacted files:**
- `CLAUDE.md` — Testing section and Linting section

**Suggested fix:** Add to testing section: "Integration tests requiring Docker services (ES, Prometheus): mark with `@pytest.mark.integration`, place in `tests/integration/`. Run with `pytest --integration`. Docker services defined in `docker-compose.test.yml`." Update the linting section to: "`pytest -m 'not slow and not integration'` before push."

---

### Code-review skill missing `type: ignore` audit

**Trigger:** PR adds four `# type: ignore[arg-type]` comments across `__init__.py` and `pipeline.py` without documenting why the suppression is needed. These suppress a real type mismatch between `transformers` model types and the function signatures — the correct fix may be to adjust the type annotations.

**Current state:** Code-review skill checks "type annotations on all functions" and "mypy with `disallow_untyped_defs`" but has no guidance on reviewing `type: ignore` comments.

**Impacted files:**
- `.claude/skills/code-review.md` — Python Best Practices section

**Suggested fix:** Add: "Flag `# type: ignore` comments without an explanatory comment. Each suppression should document why it's needed and link to the upstream issue if it's a third-party typing gap. Prefer narrowing the suppression (e.g., `[arg-type]`) over bare `# type: ignore`."

---

### Spec-review skill missing config validation completeness check

**Trigger:** P2 review comment flagged that non-mapping backend configs (e.g., a scalar string) would crash `_cmd_test_backends` with an unhelpful `AttributeError`. The spec says nothing about what constitutes valid vs. invalid config shapes, so the implementer had to discover this edge case during code review.

**Current state:** Spec-review skill section 5 (Implementation Readiness) asks "Are configuration options listed with defaults?" but doesn't check whether the spec defines what invalid config looks like or how to handle it.

**Impacted files:**
- `.claude/skills/spec-review.md` — section 5 (Implementation Readiness)

**Suggested fix:** Add to section 5: "For specs that define configuration schemas, does the spec specify the expected shape (mapping vs. scalar vs. list) and what happens when config is malformed? At minimum: type constraints and a clear error message."

---

### CLAUDE.md module layout missing tests directory structure

**Trigger:** PR adds `tests/integration/` as a new directory convention alongside the existing `tests/test_*.py` flat structure. CLAUDE.md documents `src/promptlint/` layout but not `tests/` layout. A future implementer wouldn't know integration tests go in a subdirectory.

**Current state:** CLAUDE.md says "Test files mirror source: `src/promptlint/foo.py` → `tests/test_foo.py`" but doesn't document `tests/integration/` or the convention for non-mirrored test files (e.g., `test_cli_test_backends.py` doesn't mirror any single source file).

**Impacted files:**
- `CLAUDE.md` — Module layout section

**Suggested fix:** Add a `tests/` layout section: "Unit tests mirror source (`test_foo.py`). Integration tests requiring external services go in `tests/integration/`. CLI command tests use `test_cli_<command>.py`."

## PR #3 — Spec 04 Gateway Integration Review (2026-03-30)

### `should_block` duplicated across 3 gateway classes

**Trigger:** `/simplify` code reuse review found identical `should_block` method
in `BuiltinProxy`, `PromptLintTransport`, and `PromptLintAsyncTransport`.

**Current state:** Each class has its own 3-line `should_block` method comparing
`SEVERITY_ORDER[result.severity]` against `SEVERITY_ORDER[self._block_on]`.

**Impacted files:**
- `src/promptlint/gateways/proxy.py`
- `src/promptlint/gateways/sdk_middleware.py`

**Suggested fix:** Extract a free function `should_block(severity: str,
block_on: str | None) -> bool` in `gateways/__init__.py`. All three classes
delegate to it.

---

### `_run_analysis` duplicated between proxy and sdk_middleware

**Trigger:** `/simplify` code reuse review found near-identical analysis logic
in `BuiltinProxy._run_analysis` (proxy.py:76-89) and the module-level
`_run_analysis` in sdk_middleware.py:33-51.

**Current state:** Both acquire a semaphore, call `analyzer.analyze()`, set
`result.gateway`, and release the semaphore. The proxy version doesn't pass a
message to `PromptLintOverloadError`. Cannot deduplicate directly due to circular
import (`sdk_middleware` imports `analysis_headers` from `proxy`).

**Impacted files:**
- `src/promptlint/gateways/proxy.py`
- `src/promptlint/gateways/sdk_middleware.py`

**Suggested fix:** Move both `_run_analysis` and `analysis_headers` to
`gateways/__init__.py` (or a new `gateways/_helpers.py`), breaking the circular
dependency. Both modules then import from the shared location.

---

### `__init__` boilerplate duplicated across gateway classes

**Trigger:** `/simplify` code quality review found that `BuiltinProxy`,
`PromptLintTransport`, and `PromptLintAsyncTransport` all repeat the same
`__init__` pattern: create `GatewayInfo`, create `PromptAnalyzer`, create
`ConcurrencyConfig`, create semaphore.

**Current state:** ~15 lines of identical initialization in 3 classes.

**Impacted files:**
- `src/promptlint/gateways/proxy.py`
- `src/promptlint/gateways/sdk_middleware.py`

**Suggested fix:** Extract a `GatewayBase` mixin or dataclass that handles
shared init (analyzer, info, semaphore, block_on). Gateway classes inherit/compose
it and add only their transport-specific fields.

---

### `_load_models` duplicated between PromptAnalyzer and _PipelineAnalyzer

**Trigger:** `/simplify` code reuse review found identical model-loading logic
in `__init__.py` and `pipeline.py`.

**Current state:** Both load classifier (tokenizer + model), contradiction
(tokenizer + model), and embedder with identical code (~20 lines each).

**Impacted files:**
- `src/promptlint/__init__.py`
- `src/promptlint/pipeline.py`

**Suggested fix:** Extract a `load_models(config: Config) -> ModelBundle`
function in a shared module (e.g. `_model_loader.py`). Both analyzers call it.

---

### httpx.AsyncClient created per request in proxy

**Trigger:** `/simplify` efficiency review found that `_forward_request` and
`proxy_passthrough_route` each create a new `httpx.AsyncClient` per request.

**Current state:** `async with httpx.AsyncClient(timeout=...) as client:` inside
every route handler. Connection pooling is wasted since the client is discarded
after each request.

**Impacted files:**
- `src/promptlint/gateways/proxy.py`

**Suggested fix:** Create the `httpx.AsyncClient` once in `BuiltinProxy.__init__`
(or via a FastAPI lifespan handler) and reuse it across requests. Add `aclose()`
in shutdown.

---

### Double JSON parse in _forward_request

**Trigger:** `/simplify` efficiency review found that `_forward_request` parses
the body JSON again just to check `body.get("stream", False)`, even though
normalization already parsed it.

**Current state:** `json.loads(body_bytes)` at proxy.py:198 duplicates the parse
done during `normalize()`.

**Impacted files:**
- `src/promptlint/gateways/proxy.py`

**Suggested fix:** Add `is_streaming: bool` field to `NormalizedRequest` during
normalization. Pass it through to `_forward_request` instead of re-parsing.

---

### threading.Semaphore used in async context

**Trigger:** `/simplify` efficiency review noted that the async transport uses
`threading.Semaphore` even though analysis runs via `asyncio.to_thread`.

**Current state:** `threading.Semaphore` works but doesn't integrate with the
asyncio event loop — it blocks the thread rather than yielding.

**Impacted files:**
- `src/promptlint/gateways/sdk_middleware.py`
- `src/promptlint/gateways/proxy.py`

**Suggested fix:** Use `asyncio.Semaphore` for async gateways to avoid blocking
the event loop during semaphore acquisition. Keep `threading.Semaphore` for the
sync transport.

---

### `_forward_request` parameter sprawl

**Trigger:** `/simplify` code quality review flagged `_forward_request` taking
6 parameters (request, body_bytes, path, target, timeout, result).

**Current state:** Free function at module level with too many positional params.

**Impacted files:**
- `src/promptlint/gateways/proxy.py`

**Suggested fix:** Make it a method on `BuiltinProxy` (it already accesses
`_target` and `_timeout` via params). Reduces to 3 params: request, body_bytes,
result.

---

### Vendor and GatewayInfo.type should use Literal types or enums

**Trigger:** `/simplify` code quality review flagged stringly-typed `vendor` in
normalizer and `GatewayInfo.type`.

**Current state:** `vendor: str` in normalizer accepts arbitrary strings.
`GatewayInfo.type: str` same. No compile-time checking of valid values.

**Impacted files:**
- `src/promptlint/gateways/__init__.py` — `GatewayInfo.type`
- `src/promptlint/gateways/normalizer.py` — vendor field

**Suggested fix:** Use `Literal["anthropic", "openai", "gemini"]` for vendor
and `Literal["builtin-proxy", "sdk-middleware"]` for `GatewayInfo.type`.

---

### normalized.messages silently dropped

**Trigger:** `/simplify` code quality review noted that `NormalizedRequest` has
a `messages` field populated by the normalizer, but neither proxy nor
sdk_middleware passes it to the analyzer.

**Current state:** Messages are extracted during normalization but never used.
This is expected (spec 05 covers message analysis), but undocumented.

**Impacted files:**
- `src/promptlint/gateways/normalizer.py`
- `src/promptlint/gateways/proxy.py`
- `src/promptlint/gateways/sdk_middleware.py`

**Suggested fix:** Add a `# TODO(spec-05): pass messages to analyzer for
per-turn analysis` comment in the analysis callsites. Or defer to spec 05
implementation.
