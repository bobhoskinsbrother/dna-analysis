# DNA Analysis

Read [agents.md](agents.md) for the full project description, architecture, database schema, LLM rules, and implementation plan.

## Development Workflow Rules

These rules are MANDATORY for all feature work and significant changes.

### Agent orchestration
The main agent acts as **architect and coordinator**. It MUST NOT write implementation code or tests directly. Instead, it follows this workflow:

1. **Plan** — Explore the codebase, design the approach, identify files to change, and define interfaces/contracts (function signatures, data shapes, test scenarios).
   - Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions).
   - If something goes sideways, STOP and re-plan immediately — don't keep pushing.
   - Use plan mode for verification steps, not just building.
2. **Write tests first** — Spawn three test agents **in parallel** using the Agent tool:
   - **Unit test agent** — writes isolated unit tests (models, services, pure functions). Give it the contracts, file paths, and expected behaviors.
   - **Functional test agent** — writes integration/component tests (DB round-trips, pipeline stages, matcher behavior). Give it the interfaces and interaction patterns.
   - **E2E test agent** — writes end-to-end tests that exercise the full pipeline (CSV ingestion through to Finding output). Give it the user-facing scenarios and acceptance criteria.
3. **Validate the tests** — Review rigour before running:
   - **Unit tests** — Are test cases fully triangulated? If not, reject before test run.
   - **Functional tests** — Same rigour as unit tests.
   - **E2E tests** — Do these reflect how an end user would interact with the system? If not, reject.
4. **Confirm tests fail** — Run all test suites to verify the new tests fail (red phase). If any test accidentally passes, the agent that wrote it must fix the test expectations.
5. **Write implementation** — Spawn one or more **implementation agents** in parallel (e.g., one per module) using the Agent tool. Give each agent the architectural plan, contracts, and the failing test file paths so it knows exactly what to satisfy.
6. **Verify** — Run all tests again to confirm green.
   - Never mark any task complete without proving it works.
   - Run tests, check outputs, demonstrate correctness.
7. **Split the problem** — Offload research, exploration, and parallel analysis to subagents.
   - For complex problems, throw more compute at it via subagents.
   - One task per subagent for focused execution.
8. **Share the details** — Each spawned agent receives a detailed prompt including:
   - The architectural context and plan from the main agent.
   - Specific file paths to create/modify.
   - Interfaces, data shapes, and function signatures to conform to.
   - For test agents: concrete test scenarios and expected behaviors.
   - For implementation agents: the failing test file paths as acceptance criteria.

### Test-first development
- Every new feature MUST have tests written BEFORE the implementation code.
- Write tests at all three levels:
  1. **Unit tests** — isolated logic (models, policy engine, parser)
  2. **Functional tests** — component/integration behavior (DB operations, importer pipelines, matcher queries)
  3. **E2E tests** — full pipeline flows (CSV in → Findings out)
- Tests must fail initially (red), then pass after implementation (green).
- Do not skip any test level — all three are required for every feature.
- **DO NOT SKIP ANY TESTS.** Never use `skip:` on tests. All tests must run and pass — no exceptions.
- **NEVER exclude or skip failing tests.** If a test fails, fix the test or the code — do not exclude it from the test run.

### Writing Tests

When writing tests, apply all of the following systematically. Do not treat any category as optional.

#### Boundary Value Analysis (BVA)

Every function parameter and model field must be tested at its boundaries:
- **ON point**: the exact boundary value
- **OFF point**: one step outside the boundary
- **IN point**: one step inside the boundary
- **Degenerate values**: empty strings, zero, negative numbers, `None`, empty collections
- **Default values**: verify the default is applied when the parameter is omitted

#### Wrong-Type Coverage

For every public function parameter and Pydantic model field, test with at least one wrong type:
- String where int expected, int where string expected, float where int expected
- `None` where required, bool where string/int expected, list/dict where scalar expected
- Verify the function raises `TypeError`, `ValidationError`, or equivalent — never silently coerces

#### Translation Edge Cases

For every field mapping or data transformation:
- Unknown/unmapped enum values — verify at both unit level (raises) AND functional level (proper error, not 500)
- Null/missing fields that the code expects to be present
- Extra unexpected fields (should be ignored, not cause errors)
- Empty collections — must not crash
- Case sensitivity: verify mappings are exact-match

### Tests over debugging
- When something breaks, do NOT reach for logs or manual debugging by default.
- First ask: "Is there a test that covers this problem area?"
  - If yes: understand why the existing test didn't catch the issue. Fix the test gap.
  - If no: write a test that reproduces the failure. Use the failing test to drive the fix.
- Debugging is the **absolute last resort**, only after tests have narrowed the problem.

### Self-Improvement Loop
After ANY correction from the user: update `tasks/lessons.md` with the pattern.
Write rules for yourself that prevent the same mistake.

## Task Management
1. **Plan First**: Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

## Core Principles
- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary.
- **Demand Elegance**: For non-trivial changes, pause and ask "is there a more elegant way?" Skip this for simple, obvious fixes.
