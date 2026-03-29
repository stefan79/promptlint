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
