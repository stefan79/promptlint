---
name: test-coverage
description: Verify that spec requirements are covered by unit tests and tests behave correctly
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash
---

# Test Coverage Review

Check that a spec's requirements are properly covered by unit tests.

## Steps

1. **Identify inputs.** If a spec path is given as argument, use it. Otherwise find the
   most recently modified spec in `specs/`. Then find the corresponding implementation
   files in `src/promptlint/` and test files in `tests/`.

2. **Extract spec requirements.** Read the spec and list every testable requirement
   (behavioral rules, constraints, edge cases, thresholds, error conditions).

3. **Map requirements to tests.** For each requirement, search the test files for a
   test that exercises it. A requirement is "covered" if at least one test asserts the
   expected behavior.

4. **Check test quality.** For each test file, verify:
   - Tests use plain functions (no class-based tests)
   - Slow tests (model loading) are marked `@pytest.mark.slow`
   - Edge cases from the test-rules skill are present (empty input, single element,
     boundary values, malformed input)
   - Tests assert specific values, not just "no exception"

5. **Run the tests.** Execute `pytest <test_files> -m 'not slow' --tb=short -q` and
   report pass/fail.

6. **Report.** Output a coverage matrix:

```
## Test Coverage: <spec name>

### Requirements (<covered>/<total>) — PASS/FAIL
| # | Requirement | Test | Status |
|---|------------|------|--------|
| 1 | <requirement> | test_foo | covered |
| 2 | <requirement> | — | MISSING |

### Test Quality
- Edge cases: <present>/<expected>
- Slow markers: correct / missing on <list>
- Style violations: <list or "none">

### Test Run
<pytest output summary>

### Missing Tests
<list of requirements without test coverage, with suggested test names>
```
