---
name: code-review
description: Review code for architecture compliance, edge cases, tech debt, and Python best practices
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash
---

# Code Review

Review implementation code for quality, compliance, and correctness.

## Steps

1. **Identify scope.** If a file or directory is given as argument, review that.
   Otherwise review files changed since the last commit (`git diff --name-only HEAD~1`).

2. **Architecture compliance.** Read the architect skill (`.claude/skills/architect.md`) and check:
   - Data flows match the documented pipeline (preprocessing → metrics → emitter)
   - Interfaces match their Protocol definitions (Emitter, GatewayListener, PipelineStage)
   - New code uses the correct data types (AnalysisResult, Feedback — not raw dicts)
   - Config changes go through the Config dataclass, not ad-hoc parameters
   - Resource management: stateful objects (DB connections, file handles) have close()/context manager

3. **Edge case coverage.** Cross-reference with the test-rules skill (`.claude/skills/test-rules.md`):
   - Every function with logic has tests for: empty input, single element, boundary
     values, and malformed input
   - Thresholds are tested at exactly the boundary (not just above/below)

4. **Technical debt.** Flag:
   - TODO/FIXME/HACK comments without linked issues
   - Duplicated logic (>5 lines repeated in 2+ places)
   - Functions longer than 40 lines
   - Circular imports
   - Unused imports or dead code (beyond what ruff catches)

5. **Python best practices.** Verify:
   - Type annotations on all public functions
   - `@dataclass` for data types, `Protocol` for interfaces (not ABCs)
   - `X | Y` union syntax, lowercase `list[]`/`dict[]` generics
   - No bare `except:`, no mutable default arguments
   - f-strings preferred over `.format()` or `%`

6. **Spec compliance.** Find the relevant spec in `specs/` for the code being reviewed:
   - Does the implementation match the spec's interface definitions?
   - Are all spec requirements implemented (not just a subset)?
   - Do field names, metric names, labels match exactly?
   - Are configuration options and defaults consistent with the spec?

7. **Report.** Output:

```
## Code Review: <scope>

### Architecture — PASS/FAIL
<list of violations or "Compliant">

### Edge Cases — PASS/WARN
<missing edge case tests>

### Technical Debt — PASS/WARN
<list of debt items or "Clean">

### Python Best Practices — PASS/FAIL
<list of violations or "Compliant">

### Spec Compliance — PASS/WARN
<issues where implementation diverges from its spec, or "Compliant">

### Verdict: PASS / FAIL
<summary with actionable fixes>

### Improvement Suggestions
<if any findings should have been caught earlier by the spec-review skill or
 prevented by better architect skill definitions, note them here for the
 IMPROVEMENTS.md backlog>
```
