# Lessons Learned

## 2026-04-17: Skipped test validation step (BVA, wrong-type, rigour review)

**Mistake:** After writing tests (RED phase), jumped straight to confirming RED and then implementation without validating test quality first.

**Rule:** Step 4 of the workflow is "Validate the tests" — review rigour BEFORE running:
- Unit tests: Are test cases fully triangulated with BVA? If not, reject before test run.
- Functional tests: Same rigour as unit tests.
- E2E tests: Do these reflect how an end user would interact with the system? If not, reject.

**Prevention:** After spawning test agents and before running any tests, always validate:
1. Boundary Value Analysis (BVA) — ON point, OFF point, IN point, degenerate values, defaults
2. Wrong-type coverage — at least one wrong type per public parameter
3. Edge cases — empty collections, None values, empty strings
4. Never skip this step, even when eager to see RED.
