---
name: spec-review
description: Review a spec file for instruction count, contradictions, and ambiguities using LLM analysis
user-invocable: true
allowed-tools: Read, Glob, Grep
---

# Spec Review

Review a spec file for instruction hygiene. Read the spec and analyze it directly.

## What to check

When invoked, read the spec file (passed as argument, or find the most recently modified file in `specs/`).

### 1. Instruction count (max 50)

Count every sentence in the spec that tells an implementer what to do, what not to do, or how something must behave. These include:

- Imperative statements ("stages always run in this order")
- Constraints ("no more than 3 metric stages")
- Behavioral rules ("metric stages short-circuit when below threshold")
- Requirements ("every pipeline must declare metrics")

Do NOT count: headings, table headers, examples, YAML snippets, code blocks, open questions, or purely descriptive/explanatory text.

List every instruction you find, numbered. Then give the total count.

- **PASS**: 50 or fewer instructions
- **FAIL**: more than 50 instructions — suggest which instructions to consolidate or remove

### 2. Contradictions (max 0)

Find any pair of instructions that contradict each other. A contradiction is when following one instruction would violate another.

- **PASS**: no contradictions found
- **FAIL**: list each contradicting pair with their instruction numbers

### 3. Ambiguities (max 0)

Find any instruction that could be interpreted in more than one way by a reasonable implementer. An ambiguity is when the instruction doesn't give enough information to act on, or uses vague terms without definition.

- **PASS**: no ambiguities found
- **WARN**: list each ambiguous instruction with the instruction number and explain what's unclear

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

### Verdict: PASS / FAIL
<summary of issues if any>
```
