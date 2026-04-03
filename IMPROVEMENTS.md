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

Now I have full context. Let me analyze the PR diff against the skills and produce findings.

## PR #3 — Implement gateway integration (spec 04) (2026-04-01)

### Spec-review skill missing vendor detection ambiguity check

**Trigger:** Code review found P1 bug where `max_tokens` in the vendor detector
classified OpenAI requests as Anthropic. The spec's detection table was ambiguous
about `max_tokens` being a tiebreaker — the original spec said Anthropic markers
include `"max_tokens"` but didn't note that OpenAI also commonly uses `max_tokens`.

**Current state:** Spec-review check #3 (Ambiguities) says: "Find any instruction
that could be interpreted in more than one way by a reasonable implementer."
It does not specifically guide reviewers to check decision tables/lookup tables
for overlapping conditions or ambiguous discrimination logic.

**Impacted files:**
- `.claude/skills/spec-review.md` — check #3 (Ambiguities)

**Suggested fix:** Add to check #3: "For detection/dispatch tables (vendor
detection, route matching, config lookup), verify that conditions are mutually
exclusive and that the documented evaluation order resolves all overlaps. Flag
any row where a real-world input could match multiple rows."

---

### Spec-review skill missing backward-compatibility check for replaced APIs

**Trigger:** Code review found P1 bug where the compatibility `create_app` shim
silently drops `fail_on`, breaking existing callers. The spec defined `block_on`
as the new name but didn't specify that the old `fail_on` must remain functional
in the compatibility shim.

**Current state:** Spec-review check #6 (Review-proofing) covers resource
management, type safety, test coverage, and CI/CD. It does not check for backward
compatibility when a spec replaces or renames an existing API.

**Impacted files:**
- `.claude/skills/spec-review.md` — check #6 (Review-proofing)

**Suggested fix:** Add to check #6: "When a spec replaces or renames an existing
API (function, CLI flag, config key), verify the spec defines: (a) a migration
path or compatibility shim, (b) which old parameters map to new ones, (c) what
happens to callers using the old API. Flag any replaced API without explicit
backward-compat instructions."

---

### Spec-review skill missing HTTP method coverage check

**Trigger:** Code review found P2 bug where the refactored proxy only registered
`POST` routes, breaking `GET /v1/models` and other non-POST methods that the
previous proxy supported. The spec defined route matching only for POST endpoints.

**Current state:** Spec-review check #5 (Implementation readiness) checks for
"error cases and edge cases specified" but doesn't specifically check whether
specs that replace existing functionality preserve the full surface area of what
they replace.

**Impacted files:**
- `.claude/skills/spec-review.md` — check #5 (Implementation readiness)

**Suggested fix:** Add to check #5: "When a spec refactors or replaces existing
behavior, verify the spec explicitly addresses all capabilities of the replaced
code — not just the primary path. Check for secondary routes, optional parameters,
edge-case handling, and HTTP methods that the old implementation supported."

---

### Architect skill GatewayListener protocol diverges from implementation

**Trigger:** The implemented `GatewayListener` protocol uses `extract_request()`
returning `NormalizedRequest`, while the architect skill still shows
`extract_messages()` returning `list[MessageRecord]`. The spec also added
`capabilities` and `info` properties not in the architect skill.

**Current state:** Architect skill (line 184-189) defines:
```python
class GatewayListener(Protocol):
    def extract_messages(self, raw_request: bytes) -> list[MessageRecord]: ...
    def inject_headers(self, response: Any, payload: AnalysisResult) -> None: ...
    def should_block(self, payload: AnalysisResult) -> bool: ...
```

**Impacted files:**
- `.claude/skills/architect.md` — Gateway protocol section

**Suggested fix:** Update GatewayListener to match implementation:
```python
class GatewayListener(Protocol):
    @property
    def capabilities(self) -> GatewayCapability: ...
    @property
    def info(self) -> GatewayInfo: ...
    def extract_request(self, raw_body: bytes) -> NormalizedRequest: ...
    def inject_headers(self, response: Any, result: AnalysisResult) -> None: ...
    def should_block(self, result: AnalysisResult) -> bool: ...
```
Also add `GatewayCapability` flag enum and `ConcurrencyConfig` to the interfaces section.

---

### Architect skill NormalizedRequest diverges from implementation

**Trigger:** The implementation added `model_id` field and changed `system_prompt`
to `str | None` and `messages` to `list[NormalizedMessage]` (not
`list[MessageRecord]`). The architect skill still shows the old definition.

**Current state:** Architect skill (line 196-206) shows `system_prompt: str` (not
optional), `messages: list[MessageRecord]` (wrong type), and no `model_id` field.

**Impacted files:**
- `.claude/skills/architect.md` — NormalizedRequest section

**Suggested fix:** Update to match implementation: `system_prompt: str | None`,
`messages: list[NormalizedMessage]`, add `model_id: str | None = None`. Add the
`NormalizedMessage` and `ToolCall` dataclass definitions. This also resolves the
inconsistency between the `ToolCall` in architect (under MessageRecord) and the
gateway-specific `ToolCall` in normalizer.

---

### Architect skill vendor detection uses path-based detection, implementation uses body sniffing

**Trigger:** The implementation uses body-sniffing (top-level JSON keys) for
vendor detection, but the architect skill still says "The gateway detects vendor
from request path."

**Current state:** Architect skill (line 284) says: "The gateway detects vendor
from request path and normalizes:" with a table showing URL paths (`/v1/messages`,
`/v1/chat/completions`, etc.).

**Impacted files:**
- `.claude/skills/architect.md` — Vendor normalization section

**Suggested fix:** Update to: "The gateway detects vendor by body sniffing
(top-level JSON keys), with optional config override. Detection order: Gemini
(`system_instruction` or `contents`) → Anthropic (`system` key) → OpenAI
(fallback when `messages` present)." Remove URL paths from the detection table
(paths are routing, not detection).

---

### Architect skill AnalysisResult missing `gateway: GatewayInfo | None` field

**Trigger:** Implementation added `gateway: GatewayInfo | None = None` to
`AnalysisResult`, but the architect skill shows `gateway: GatewayInfo` as
required (non-optional). The spec explicitly calls this out as needing update.

**Current state:** Architect skill (line 98): `gateway: GatewayInfo` — no
`| None`, no default.

**Impacted files:**
- `.claude/skills/architect.md` — AnalysisResult definition

**Suggested fix:** Change to `gateway: GatewayInfo | None = None` with comment:
"Set by gateway adapter; None for direct PromptAnalyzer.analyze() calls."

---

### CLAUDE.md module layout missing gateways/ submodules

**Trigger:** PR added `src/promptlint/gateways/` with `__init__.py`,
`normalizer.py`, `proxy.py`, and `sdk_middleware.py`, but CLAUDE.md's module
layout section still shows the flat structure without the gateways package.

**Current state:** CLAUDE.md module layout shows `proxy.py` at top level, no
`gateways/` directory.

**Impacted files:**
- `CLAUDE.md` — Module layout section

**Suggested fix:** Update module layout to include:
```
├── gateways/
│   ├── __init__.py          # GatewayListener protocol, GatewayCapability, exceptions
│   ├── normalizer.py        # Vendor detection + normalization
│   ├── proxy.py             # BuiltinProxy (FastAPI reverse proxy)
│   └── sdk_middleware.py    # httpx transport middleware
├── proxy.py                 # Deprecated shim → gateways.proxy
```

---

### Test-rules skill missing gateway/transport test patterns

**Trigger:** PR added 54 gateway unit tests using patterns not covered by
test-rules: mock analyzers, mock httpx transports (`_EchoTransport`,
`_AsyncEchoTransport`), FastAPI `TestClient` with `raise_server_exceptions=False`,
and semaphore exhaustion testing. These patterns will recur for every new gateway.

**Current state:** Test-rules per-component edge cases cover Chunker, Classifier,
Embedder, Redundancy, Contradiction, and Scorer. No gateway-specific patterns.

**Impacted files:**
- `.claude/skills/test-rules.md` — Per-component edge cases section

**Suggested fix:** Add gateway edge cases: "**Gateway/Transport**: mock analyzer
returning each severity level, mock httpx transports (sync `_EchoTransport` and
async `_AsyncEchoTransport`), `TestClient(raise_server_exceptions=False)` for
proxy tests, semaphore exhaustion (429/PromptLintOverloadError), malformed body
passthrough, vendor detection fallback, `block_on` at each severity boundary."

---

### Code-review skill missing deprecation shim quality check

**Trigger:** The `proxy.py` backward-compatibility shim silently drops `fail_on`
in `**kwargs` rather than mapping it, which a code review check should catch.

**Current state:** Code-review step #2 (Architecture compliance) checks
interfaces match protocols and step #6 (Spec compliance) checks field names
match. Neither checks that deprecated shims actually forward all parameters
correctly.

**Impacted files:**
- `.claude/skills/code-review.md` — step #4 (Technical debt)

**Suggested fix:** Add to step #4: "Deprecated shims and compatibility wrappers:
verify they forward all parameters from the old API to the new one. Check that
renamed parameters are mapped (not silently dropped via `**kwargs`). Test that
the shim produces identical behavior to the old code for all documented use cases."

## PR #4 — Spec 05 Orchestrator Support Review (2026-04-01)

### `_make_request` test helper duplicated across 3 orchestrator test files

**Trigger:** `/simplify` code reuse review found identical `_make_request()`
factory functions in `test_orchestrator_claude_code.py`,
`test_orchestrator_generic.py`, and `test_orchestrators_init.py` with minor
signature differences (default vendor, presence of model_id).

**Current state:** Three copies construct `NormalizedRequest` with identical
body logic. Adding a field to `NormalizedRequest` requires updating all three.

**Impacted files:**
- `tests/test_orchestrator_claude_code.py`
- `tests/test_orchestrator_generic.py`
- `tests/test_orchestrators_init.py`

**Suggested fix:** Add `pythonpath = ["tests"]` to `pyproject.toml`
`[tool.pytest.ini_options]`, create `tests/helpers.py` with shared
`make_normalized_request()`, and import from each test file. Alternatively,
add as a pytest fixture factory in `tests/conftest.py`.

---

### `AgentInfo.name` and `AgentInfo.agent_type` always set to same value

**Trigger:** `/simplify` code quality review found that `claude_code.py` always
sets `AgentInfo(name=agent_type, agent_type=agent_type)`, making the two fields
carry identical information.

**Current state:** `AgentInfo` has both `name: str` and `agent_type: str = ""`.
In all current usage, `name` is set to the same value as `agent_type`.

**Impacted files:**
- `src/promptlint/orchestrators/__init__.py` — `AgentInfo` dataclass
- `src/promptlint/orchestrators/claude_code.py`

**Suggested fix:** Either remove `name` and rename `agent_type` to `name`, or
document the intended semantic distinction (e.g., `name` = display name,
`agent_type` = classification). If spec 08 active plugins provide richer agent
metadata, the distinction may become meaningful — add a comment explaining this.

---

### Stringly-typed orchestrator names across 4 files

**Trigger:** `/simplify` code quality review flagged `"claude-code"`, `"generic"`,
`"unknown"` as raw string literals repeated across `__init__.py`, `claude_code.py`,
`generic.py`, and `envelope.py` with no shared constant or `Literal` type.

**Current state:** A typo in any one location (e.g., `"claude_code"` vs
`"claude-code"`) would silently break adapter matching.

**Impacted files:**
- `src/promptlint/orchestrators/__init__.py`
- `src/promptlint/orchestrators/claude_code.py`
- `src/promptlint/orchestrators/generic.py`

**Suggested fix:** Use `Literal["claude-code", "generic", "unknown"]` for
`orchestrator_name` in `DetectedContext` and `OrchestratorEnvelope`. This gives
mypy enforcement at all callsites. Same treatment as the existing suggestion for
`GatewayInfo.type` and vendor strings (PR #3 improvement).

---

### `SkillInfo.source` should use Literal type

**Trigger:** `/simplify` code quality review flagged `source: str = "passive"`
with comment `# "passive" or "active" (spec 08)` but no type enforcement.

**Current state:** Any string is accepted. When spec 08 adds active sources,
a mistyped `"actve"` would not be caught by mypy.

**Impacted files:**
- `src/promptlint/orchestrators/__init__.py` — `SkillInfo.source`

**Suggested fix:** Change to `source: Literal["passive", "active"] = "passive"`.

---

### `OrchestratorEnvelope` flattens structured lists, discarding tool/skill metadata

**Trigger:** `/simplify` code quality review noted that `build_envelope()` maps
`context.skills`, `context.tools`, and `context.agents` to plain `list[str]`
(names only), silently dropping `ToolInfo.param_count` and `SkillInfo.source`.

**Current state:** The envelope cannot reconstruct which skills were passive vs.
active, or how many parameters each tool has.

**Impacted files:**
- `src/promptlint/orchestrators/envelope.py` — `build_envelope()`

**Suggested fix:** Either store the full dataclass lists in the envelope (change
`detected_skills: list[str]` to `detected_skills: list[SkillInfo]`), or
document the intentional simplification with a comment explaining that consumers
needing full metadata should use `DetectedContext` directly.

---

### `_ADAPTERS` module-level mutable list is not thread-safe

**Trigger:** `/simplify` efficiency review flagged that `_ADAPTERS` is a bare
Python list mutated by `register_adapter`, `clear_adapters`, and
`register_default_adapters`, and iterated by `detect`. Under a multi-threaded
ASGI server, concurrent mutations and iterations race with no locking.

**Current state:** No threading protection. `register_default_adapters` has a
TOCTOU race (check-then-insert is not atomic).

**Impacted files:**
- `src/promptlint/orchestrators/__init__.py`

**Suggested fix:** Add a `threading.Lock` around mutations and iteration, or use
an immutable-swap pattern (build a new tuple and assign atomically). The lock is
simpler and matches the existing `threading.Semaphore` pattern in gateways.

Now I have the full picture. Here are the findings for skills/agents/rules/CLAUDE.md improvements:

## PR #4 — Implement spec 05: orchestrator passive detection (2026-04-02)

### Spec-review skill should check for input validation at wire-data boundaries

**Trigger:** Code review found a P2: `tc.input` from normalized wire data could
be non-dict, causing `AttributeError` in `ClaudeCodeAdapter.detect()`. The spec
and architect skill both showed `tc.input.get("skill")` without any guard,
giving the implementer no signal that validation was needed. The spec-review
skill's "Review-proofing" section didn't catch this class of issue.

**Current state:** The spec-review skill's §6 "Review-proofing" checks for
resource management, type safety, test coverage, and CI/CD — but not for
defensive handling of data from external/untrusted sources (wire traffic, user
input, API responses). The architect skill's "Claude Code passive detection"
code snippet shows bare `.get()` on `tc.input` with no `isinstance` guard.

**Impacted files:**
- `.claude/skills/spec-review.md` — §6 Review-proofing
- `.claude/skills/architect.md` — "Claude Code passive detection" section

**Suggested fix:** Add to spec-review §6 Review-proofing: "External data
validation: does the spec identify which inputs come from untrusted sources
(wire traffic, API responses, user config)? Are defensive checks specified for
fields that could be malformed (wrong type, missing keys, unexpected structure)?
Any Protocol method that processes `NormalizedRequest` fields or tool call
inputs operates on external data." Also update the architect skill's Claude Code
detection snippet to include the `isinstance(tc.input, dict)` guard as the
canonical pattern.

---

### Spec-review skill should check registry/factory idempotency requirements

**Trigger:** Code review found a P2: `register_default_adapters()` no-oped when
any adapter was pre-registered, preventing built-in adapters from being added in
plugin scenarios. The spec didn't specify idempotency semantics for the
registration function, and spec-review didn't flag this gap.

**Current state:** The spec-review skill's §5 "Implementation readiness" checks
for open questions, field definitions, error/edge cases, config options, and
testing strategy — but doesn't check for behavioral contracts of registration or
factory functions (idempotency, ordering guarantees, interaction with
pre-existing state).

**Impacted files:**
- `.claude/skills/spec-review.md` — §5 Implementation readiness

**Suggested fix:** Add to spec-review §5 Implementation readiness: "Registry and
factory patterns: if the spec defines a registry (adapter registry, emitter
factory, stage registry), are registration semantics specified? Check for:
idempotency (what happens when called twice?), interaction with pre-existing
entries (do custom registrations survive default registration?), ordering
guarantees (first-match-wins documented?), and cleanup/reset behavior."

---

### Architect skill has colliding type names across spec boundaries

**Trigger:** The architect skill now defines `SkillInfo`, `ToolInfo`, and
`AgentInfo` in *two* separate sections with different field sets — once under
AnalysisResult (spec 08, planned) and once under DetectedContext (spec 05,
implemented). A note was added in this PR, but the collision is structural.

**Current state:** The architect skill includes a comment: "the `SkillInfo`,
`ToolInfo`, and `AgentInfo` types below are defined in `orchestrators/__init__.py`
and are **distinct** from the same-named types in the AnalysisResult section
above." This relies on implementers reading the comment carefully. Code
generators and future spec implementations may import the wrong one.

**Impacted files:**
- `.claude/skills/architect.md` — DetectedContext and AnalysisResult sections
- `specs/08-orchestrator-plugins.md` — will need to resolve naming when implemented

**Suggested fix:** Add a "Naming conventions" section to the architect skill that
explicitly lists same-name types with different definitions and their canonical
import paths. Recommend that spec 08 implementation either (a) renames the
AnalysisResult-level types (e.g., `AnalysisSkillInfo`) or (b) consolidates into
one definition with an optional `instruction_count` field. Flag this as a
required pre-implementation decision in spec 08.

---

### CLAUDE.md spec 07 status still says "blocked on 02-05"

**Trigger:** This PR updated spec 05's status to "Implemented" in CLAUDE.md, but
spec 07 (Benchmarks) still reads "Draft, blocked on 02-05". With spec 05 now
implemented, the blocker description is stale.

**Current state:** CLAUDE.md spec table row: `| 07 | Benchmarks | Draft, blocked on 02-05 |`

**Impacted files:**
- `CLAUDE.md` — spec status table

**Suggested fix:** Update to `"Draft, blocked on 02-04"` (specs 01, 03, 05 are
implemented; specs 02 and 04 remain). Or if spec 02 (Pipeline DSL) is the
primary remaining blocker, simplify to `"Draft, blocked on 02+04"`.

---

### Code-review skill should explicitly check adapter/protocol boundary validation

**Trigger:** Both P2 review findings in this PR were about defensive handling at
protocol boundaries — malformed tool call inputs and registration idempotency.
The code-review skill checks "edge case coverage" by referencing test-rules, but
doesn't specifically call out protocol/adapter boundary validation as a review
target.

**Current state:** Code-review skill §3 "Edge case coverage" says: "Every
function with logic has tests for: empty input, single element, boundary
values, and malformed input." This is generic — it doesn't highlight that
`Protocol` implementations receiving external data (gateway, orchestrator
adapters) need stronger input validation than internal pipeline stages.

**Impacted files:**
- `.claude/skills/code-review.md` — §3 Edge case coverage

**Suggested fix:** Add to code-review §3: "Protocol boundary validation: code
implementing `OrchestratorAdapter`, `GatewayListener`, or `Emitter` protocols
processes data from external sources. Verify that inputs from
`NormalizedRequest` (tool call inputs, message content, tool definitions) are
type-checked before field access. Registry/factory functions should be tested
for idempotency and interaction with pre-existing state."

## PR #5 — Spec 06 Configuration Language Review (2026-04-03)

### `_deep_validate_backends` duplicates `_cmd_test_backends` probe loop

**Trigger:** `/simplify` code reuse review found that `config_loader._deep_validate_backends` and `cli._cmd_test_backends` both iterate backend configs, call `create_emitter()`, write test `AnalysisResult`/`Feedback`, and check for errors. The only difference is output format (error list vs print).

**Current state:** Two independent implementations of the same backend probe logic.

**Impacted files:**
- `src/promptlint/config_loader.py` — `_deep_validate_backends`
- `src/promptlint/cli.py` — `_cmd_test_backends`

**Suggested fix:** Extract a shared `probe_backends(backends: dict) -> list[str]` function. `_cmd_test_backends` calls it and formats output. `_deep_validate_backends` delegates directly.

---

### `_deep_validate_backends` writes real records to production backends

**Trigger:** `/simplify` efficiency review found that deep validation writes actual `AnalysisResult` and `Feedback` records to every configured backend (JSONL, SQLite, Elasticsearch, webhook, Prometheus) with no cleanup.

**Current state:** Running `promptlint validate --deep` pollutes production storage with test data.

**Impacted files:**
- `src/promptlint/config_loader.py` — `_deep_validate_backends`

**Suggested fix:** Add a `ping()` or `check_connectivity()` method to the `Emitter` protocol for lightweight validation. JSONL/SQLite: check path is writable. ES: `GET /`. Webhook: `HEAD` request. Prometheus: `GET` pushgateway. Fall back to current behavior only if `ping()` is not implemented.

---

### `GatewaySettings.type` and `OrchestratorSettings.type` should use Literal types

**Trigger:** `/simplify` code quality review found both fields are `str` but validated against fixed sets at runtime. No mypy enforcement.

**Current state:** `GatewaySettings.type: str` validated against `{"builtin-proxy", "sdk-middleware"}`. `OrchestratorSettings.type: str` has no validation at all.

**Impacted files:**
- `src/promptlint/config_loader.py`

**Suggested fix:** Use `Literal["builtin-proxy", "sdk-middleware"]` and `Literal["generic", "claude-code"]`. Consistent with existing `Literal` usage in `orchestrators/__init__.py`.

---

### `_SEARCH_CHAIN` frozen at import time creates test friction

**Trigger:** `/simplify` efficiency review noted that `Path.home()` is evaluated once at module import. Tests must monkey-patch the entire `_SEARCH_CHAIN` list to override home directory.

**Current state:** `test_discover_home_config` patches `_SEARCH_CHAIN` directly — fragile coupling to a private module-level variable.

**Impacted files:**
- `src/promptlint/config_loader.py` — `_SEARCH_CHAIN`
- `tests/test_config_loader.py` — `test_discover_home_config`

**Suggested fix:** Compute `_SEARCH_CHAIN` lazily inside `discover_config()` or accept an optional `search_chain` parameter for testability.

Here are the improvement findings:

## PR #5 — Implement spec 06: Configuration Language (2026-04-03)

### Spec-review should check CLI error handling for all entry points

**Trigger:** Code review found that `promptlint validate --config <missing-file>` produced a traceback instead of a user-friendly error. The spec defined `discover_config()` behavior (raises `FileNotFoundError`) and the `validate` CLI command, but didn't specify how the CLI surfaces that error. The spec-review skill didn't catch this gap.

**Current state:** Spec-review check #5 (Implementation readiness) says "Are error cases and edge cases specified?" but doesn't specifically check that **every CLI subcommand documents its error-to-exit-code mapping**. Check #6 (Review-proofing) mentions "resource management" and "type safety" but not CLI UX for error paths.

**Impacted files:**
- `.claude/skills/spec-review.md` — checks 5 and 6

**Suggested fix:** Add to check #5 (Implementation readiness): "For specs that add CLI subcommands: does the spec define how each error type maps to user-facing output? Every exception that can reach the CLI entry point needs an explicit catch-and-print path, not a raw traceback." Add to check #6 (Review-proofing): "CLI error UX: every new subcommand handles all exceptions from its called functions with user-friendly messages and appropriate exit codes."

---

### Spec-review and code-review should flag truthiness-based type validation

**Trigger:** Code review found two bugs from the same pattern: `if backends_raw` skips validation when `backends: []` (falsy but wrong type), and `if feedback_raw and not isinstance(feedback_raw, dict)` silently coerces falsy non-dict values like `false` or `0`. Both stem from using Python truthiness checks where type checks were intended.

**Current state:** Code-review check #5 (Python best practices) lists "No bare `except:`, no mutable default arguments" but doesn't flag truthiness-as-type-guard. Spec-review has no check for this pattern. Neither skill warns about the distinction between "missing/None" vs "present but wrong type" vs "present but falsy."

**Impacted files:**
- `.claude/skills/code-review.md` — check 5 (Python best practices)
- `.claude/skills/spec-review.md` — check 6 (Review-proofing)

**Suggested fix:** Add to code-review check #5: "Validation code must use `is not None` or explicit type checks (`isinstance`), not truthiness (`if x`), when the intent is to distinguish missing values from wrong-type values. `if x and not isinstance(x, dict)` silently accepts `[]`, `0`, `False`, `''` — use `if x is not None and not isinstance(x, dict)` instead." Add to spec-review check #6: "Type coercion: when a spec defines a field as a mapping, does it specify behavior for wrong-type-but-falsy inputs like `[]`, `false`, `0`?"

---

### Architect skill missing config_loader interfaces and discovery chain

**Trigger:** PR #5 introduced `PromptLintSettings`, `GatewaySettings`, `OrchestratorSettings`, `AnalysisSettings`, `ConfigError`, and the `discover_config` → `load_settings` → `parse_settings_dict` public API. None of these appear in the architect skill, which is the authoritative interface reference that spec-review and code-review cross-check against.

**Current state:** The architect skill documents interfaces for pipeline (`AnalysisResult`, `Feedback`, `Emitter`, `GatewayListener`, `PipelineStage`) but has no section for configuration types. The file organization section in the skill doesn't include `config_loader.py`.

**Impacted files:**
- `.claude/skills/architect.md` — Core interfaces section and file organization

**Suggested fix:** Add a "Configuration" section to the architect skill covering: `PromptLintSettings` (top-level), `GatewaySettings`, `OrchestratorSettings`, `AnalysisSettings`, `ConfigError`, and the public API (`discover_config`, `load_settings`, `validate_config`, `settings_to_config`). Add `config_loader.py` to the file organization. This ensures future specs that interact with config (gateway, orchestrator plugins) are reviewed against the actual config interfaces.

---

### Test-rules missing per-component edge cases for config parsing

**Trigger:** The 43 tests in this PR cover many validation paths but miss the two falsy-value bugs found by code review (`backends: []` and `feedback: false`). The test-rules skill defines per-component edge cases for Chunker, Classifier, Embedder, etc., but has no section for config parsing despite it being a new component with its own edge case patterns.

**Current state:** Test-rules "Per-component edge cases" section covers only pipeline stages: Chunker, Classifier, Embedder, Redundancy, Contradiction, Scorer.

**Impacted files:**
- `.claude/skills/test-rules.md` — Per-component edge cases section

**Suggested fix:** Add a **Config loader** entry: "wrong-type-but-falsy values for mapping fields (`backends: []`, `feedback: false`, `dataset: 0`), env var in every value position (string, nested dict, list item), config file with only comments, duplicate backend names, circular cross-references (feedback backend referencing itself), all gateway types with missing required fields."

---

### Spec-develop agent should run `/code-review` before creating PR

**Trigger:** The three P2 code review findings (missing error handling, truthiness validation, silent coercion) were all caught by the external code review after the PR was created. The spec-develop agent runs quality checks (ruff, mypy, pytest) in Phase 2 step 10, but doesn't run the `/code-review` skill which would have caught architecture compliance and edge case issues before the PR was opened.

**Current state:** Phase 2 step 10 runs `ruff check`, `ruff format`, `mypy`, and `pytest`. Phase 2 step 11 re-runs `/spec-review`. There is no step that runs `/code-review` on the implementation before creating the PR.

**Impacted files:**
- `.claude/agents/spec-develop.md` — Phase 2, between steps 10 and 11

**Suggested fix:** Add a step between 10 and 11: "**Self code-review.** Run `/code-review` on all new and modified files. Address any FAIL findings before proceeding. WARN findings should be evaluated — fix if straightforward, otherwise note in the PR description."

---

### CLAUDE.md core interfaces table missing configuration boundary

**Trigger:** PR #5 added config types that mediate between the YAML file and every other subsystem (pipeline, gateway, orchestrator, emitters). The Core interfaces table in CLAUDE.md lists pipeline→emitter, gateway→pipeline, user→emitter boundaries but not config→everything.

**Current state:** The "Core interfaces (summary)" table has 8 entries covering pipeline, gateway, emitter, and orchestrator boundaries. No entry for config loading.

**Impacted files:**
- `CLAUDE.md` — Core interfaces table

**Suggested fix:** Add row: `| **PromptLintSettings** | Top-level config parsed from promptlint.yaml. Wires pipelines, backends, gateways, orchestrators. | YAML file → all subsystems |`
