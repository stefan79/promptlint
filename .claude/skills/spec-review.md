---
name: spec-review
description: Review a spec file for instruction hygiene, architecture consistency, and implementation readiness
user-invocable: true
allowed-tools: Read, Glob, Grep
---

# Spec Review

Review a spec file for quality and readiness before implementation. Catches
issues that would otherwise surface as code review findings.

## Prerequisites

Before reviewing, read these references:
- **Architect skill** (`.claude/skills/architect.md`) — for interface definitions,
  data flow, naming conventions, and key design decisions
- **CLAUDE.md** — for coding standards, module layout, and key decisions
- **Related specs** mentioned in the spec being reviewed

## What to check

When invoked, read the spec file (passed as argument, or find the most recently
modified file in `specs/`).

### 1. Instruction count (max 50)

Count every sentence in the spec that tells an implementer what to do, what not
to do, or how something must behave. These include:

- Imperative statements ("stages always run in this order")
- Constraints ("no more than 3 metric stages")
- Behavioral rules ("metric stages short-circuit when below threshold")
- Requirements ("every pipeline must declare metrics")

Do NOT count: headings, table headers, examples, YAML snippets, code blocks,
open questions, or purely descriptive/explanatory text.

List every instruction you find, numbered. Then give the total count.

- **PASS**: 50 or fewer instructions
- **FAIL**: more than 50 instructions — suggest which instructions to consolidate or remove

### 2. Contradictions (max 0)

Find any pair of instructions that contradict each other. A contradiction is
when following one instruction would violate another.

Also check for contradictions between this spec and:
- The architect skill's interface definitions and data flow
- CLAUDE.md's key decisions and coding standards
- Other specs referenced by this one

- **PASS**: no contradictions found
- **FAIL**: list each contradicting pair with their instruction numbers and source

### 3. Ambiguities (max 0)

Find any instruction that could be interpreted in more than one way by a
reasonable implementer. An ambiguity is when the instruction doesn't give enough
information to act on, or uses vague terms without definition.

- **PASS**: no ambiguities found
- **WARN**: list each ambiguous instruction with the instruction number and explain what's unclear

### 4. Architecture consistency

Cross-reference with the architect skill and CLAUDE.md:

- **Type names**: Does the spec use the same type names as the architect skill?
  (e.g., `AnalysisResult` not `AnalysisPayload`, `Feedback` not `dict`)
- **Interface signatures**: Do protocol methods match the architect skill definitions?
- **Data flow**: Does the spec's data flow match the documented pipeline?
- **Module placement**: Does the spec place new files in the correct locations
  per the module layout in CLAUDE.md?
- **Key decisions**: Does the spec respect the key decisions in CLAUDE.md?
  (pure Python, no LLM calls, CPU only, config-driven, etc.)

- **PASS**: fully consistent
- **FAIL**: list each inconsistency with the spec instruction and the conflicting reference

### 5. Implementation readiness

Check whether the spec provides enough detail for implementation without
requiring back-and-forth:

- Are all open questions resolved?
- Does every interface have concrete field definitions (not just descriptions)?
- Are error cases and edge cases specified?
- Are configuration options listed with defaults?
- Is the testing strategy defined (unit tests, integration tests, markers)?
- Are external dependencies identified?

- **PASS**: ready for implementation
- **WARN**: list gaps that an implementer would need to resolve

### 6. Review-proofing

Anticipate issues that automated code review would flag:

- Resource management: does the spec address cleanup/close for stateful resources?
- Type safety: are all data types specified as dataclasses, not raw dicts?
- Test coverage: does the spec define what needs integration vs unit tests?
- CI/CD: does the spec affect workflows? Are those changes specified?

- **PASS**: no predictable review issues
- **WARN**: list likely code review findings with suggested spec additions

## Output format

```
## Spec Review: <filename>

### Instructions (<count>/50) — PASS/FAIL
1. <instruction text>
2. <instruction text>
...

### Contradictions — PASS/FAIL
<list pairs or "None found">

### Ambiguities — PASS/WARN
<list ambiguous instructions or "None found">

### Architecture Consistency — PASS/FAIL
<list inconsistencies or "Consistent">

### Implementation Readiness — PASS/WARN
<list gaps or "Ready">

### Review-Proofing — PASS/WARN
<list likely review findings or "Clean">

### Verdict: PASS / FAIL
<summary of issues if any>
```
