---
name: tdd
description: Test-driven development discipline — red/green/refactor, failing test first, minimal implementation to pass, refactoring under a green bar
---

# Test-Driven Development

This skill governs the test-driven development discipline for PH-006
(Incremental Implementation). Its scope is the cadence and rigor of
building production code: write the failing test first, implement the
minimum to pass, refactor only under a green bar.

This skill is the FLOOR, not the ceiling. Stack-specific testing
idioms -- pytest fixtures, Jest matchers, Go table-driven tests --
come from companion skills loaded by the Skill-Selector based on the
component's expected_expertise entries. This skill ensures every
implementation follows the TDD discipline regardless of technology.

Traceability mechanics -- source_refs, source_quote, coverage_check,
coverage_verdict, inherited_assumptions, and the Quote Test -- are
governed by the companion traceability-discipline skill loaded
alongside this one. This skill focuses on HOW to build code and
WHAT cadence to follow.

## The Iron Law

**NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST.**

Write code before the test? Delete it. Start over.

- **BECAUSE:** Code written without a failing test has no proof that
  the test catches its absence. A test that passes on its first run
  might pass for the wrong reason -- you never saw it detect the
  missing behavior.

**No exceptions:**
- Don't keep it as "reference"
- Don't "adapt" it while writing tests
- Don't look at it while drafting the test
- Delete means delete

**Violating the letter of the rules is violating the spirit of the
rules.**

## The Red-Green-Refactor Cycle

Every unit of behavior follows this three-step cycle. No steps are
optional. No steps may be reordered.

### RED -- Write One Failing Test

Write a single test that describes the next behavior to implement.
The test name states what the production code should do, not how.

- **RULE:** One behavior per test. If the test name contains "and,"
  split it into two tests.
  - **BECAUSE:** Compound tests hide which behavior broke.

- **RULE:** The test MUST fail for the RIGHT REASON -- the absence
  of the behavior being tested, not a typo, import error, or syntax
  mistake.
  - **BECAUSE:** A test that fails for the wrong reason proves
    nothing about the behavior. Fixing the typo might make it pass
    without implementing anything.

#### What Counts as a Correct Failure

| Failure Type | Correct? | Why |
|---|---|---|
| Function does not exist | YES | Behavior is absent |
| Function returns wrong value | YES | Logic not yet implemented |
| Assertion mismatch on expected output | YES | Implementation incomplete |
| Import error on module you are about to create | YES | Module is the behavior |
| Typo in existing module path | NO | Test is broken, not behavior |
| Syntax error in test file | NO | Fix the test first |
| Test framework cannot discover the test | NO | Configuration problem |

#### CORRECT: Failing for the Right Reason

```typescript
// Test for behavior that does not exist yet
test('calculates overdue fee based on days past due date', () => {
  const loan = { dueDate: '2026-04-01', returnDate: '2026-04-04' };
  const fee = calculateOverdueFee(loan);
  expect(fee).toBe(3.00); // $1/day * 3 days
});

// Run: ReferenceError: calculateOverdueFee is not defined
// Correct failure -- the function does not exist yet.
```

#### WRONG: Failing for the Wrong Reason

```typescript
import { calculateOverdueFee } from './circulaiton'; // typo!

test('calculates overdue fee', () => {
  const fee = calculateOverdueFee({
    dueDate: '2026-04-01', returnDate: '2026-04-04'
  });
  expect(fee).toBe(3.00);
});

// Run: Cannot find module './circulaiton'
// Wrong failure -- fails because of a misspelled path, NOT because
// the behavior is absent. Fixing the typo might reveal the function
// already exists and passes.
```


### Verify RED -- Watch It Fail

**MANDATORY. Never skip this step.**

Run the test. Confirm all three:
1. The test fails (not errors from broken test infrastructure)
2. The failure message matches what you expect
3. The failure is caused by absent behavior

- **RULE:** If the test passes immediately, you are testing existing
  behavior. Delete the test and write one that exercises the new
  behavior you intend to add.
  - **BECAUSE:** A test that never failed cannot prove it detects the
    absence of the feature.

- **RULE:** If the test errors (syntax, import, configuration), fix
  the error first. Confirm it fails for the right reason before
  moving to GREEN.
  - **BECAUSE:** An erroring test is not a failing test. You have not
    completed RED until you see the correct assertion failure.


### GREEN -- Minimal Implementation

Write the simplest code that makes the failing test pass.

- **RULE:** Just enough to turn the test green, no more.
  - **BECAUSE:** Every line beyond what the test demands is untested
    code. Untested code is unverified behavior.

- **RULE:** Do not refactor during GREEN. Do not add error handling
  the test does not require. Do not generalize.
  - **BECAUSE:** GREEN is about making one specific test pass.
    Generalization and cleanup have their own step.

#### CORRECT: Minimal Implementation

```typescript
// RED asked: calculateOverdueFee({ dueDate, returnDate }) => 3.00

const DAILY_OVERDUE_RATE = 1.00;

function calculateOverdueFee(
  loan: { dueDate: string; returnDate: string }
): number {
  const due = new Date(loan.dueDate);
  const returned = new Date(loan.returnDate);
  const msPerDay = 86_400_000;
  const daysLate = Math.floor(
    (returned.getTime() - due.getTime()) / msPerDay
  );
  return daysLate > 0 ? daysLate * DAILY_OVERDUE_RATE : 0;
}
// Just enough. No configurability, no currency formatting, no logging.
```

#### WRONG: Over-Engineering During GREEN

```typescript
function calculateOverdueFee(
  loan: { dueDate: string; returnDate: string },
  options?: {
    ratePerDay?: number;       // YAGNI -- no test asks for this
    currency?: string;          // YAGNI -- no test asks for this
    maxFee?: number;            // YAGNI -- no test asks for this
    gracePeriodDays?: number;   // YAGNI -- no test asks for this
  }
): number { /* ... */ }
// Over-engineered. The test asked for a $1/day calculation.
// Options, caps, and grace periods are untested, unverified scope.
```


### Verify GREEN -- Watch It Pass

**MANDATORY. Never skip this step.**

Run the test. Confirm all three:
1. The new test passes
2. All existing tests still pass
3. No errors or warnings in the output

- **RULE:** If the new test still fails, fix the production code,
  not the test.
  - **BECAUSE:** The test defines the desired behavior. Changing the
    test to match wrong output is testing the implementation, not
    the behavior.

- **RULE:** If other tests broke, fix them now before proceeding.
  - **BECAUSE:** A red bar anywhere means you introduced a
    regression. Regressions compound if left unfixed.


### REFACTOR -- Clean Under a Green Bar

After GREEN, and ONLY after GREEN, improve the code's structure while
keeping all tests passing.

- **RULE:** The bar must stay green throughout refactoring. Run tests
  after every structural change.
  - **BECAUSE:** If refactoring breaks a test, the refactoring changed
    behavior, not just structure.

- **RULE:** If the bar goes red during refactoring, revert the last
  change and try a smaller step.
  - **BECAUSE:** A failing test during refactoring means the change
    was not behavior-preserving. Pushing through with a red bar
    combines structural and behavioral changes -- two unknowns
    instead of one.

- **RULE:** Do NOT add new behavior during REFACTOR. New behavior
  starts with a new RED step.
  - **BECAUSE:** Behavior added during REFACTOR enters the codebase
    without a failing test proving it works.

#### What Belongs in REFACTOR

| Action | Belongs? | Why |
|---|---|---|
| Rename a variable for clarity | YES | Structure, no behavior change |
| Extract a helper function | YES | Structure, tests still pass |
| Remove code duplication | YES | Structure, tests still pass |
| Add error handling for new edge case | NO | New behavior -- needs RED first |
| Optimize a hot path | DEPENDS | If tests still pass and output unchanged, yes |
| Add logging | DEPENDS | If tests don't assert on side effects, yes |


## Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Response |
|---|---|---|
| **Writing tests after code** | Tests pass immediately -- no proof they catch the bug. Tests are biased by seeing the implementation. | Delete the code. Write the test. Watch it fail. Implement fresh. |
| **Skipping the RED step** | "I know it'll fail." You don't. It might pass (existing behavior) or fail for the wrong reason (typo). | Run the test. Every time. No exceptions. |
| **Refactoring with a red bar** | Two unknowns: the refactoring AND the failing test. You cannot tell which change caused what. | Get to green first. Then refactor. |
| **Testing implementation, not behavior** | Test breaks on any internal change even when behavior is unchanged. Refactoring becomes impossible. | Test inputs and outputs. Mock only at true system boundaries. |
| **Giant GREEN steps** | Writing 200 lines to pass one test means most lines are untested. | Each test should require a small, focused change. Large GREEN means RED was too coarse. |
| **Skipping Verify GREEN** | "It obviously passes." It might not. Or other tests might have broken. | Run all tests. Every time. |

## Rationalizations

| Excuse | Reality |
|---|---|
| "Too simple to test" | Simple code breaks. The test takes 30 seconds. |
| "I'll write tests after" | Tests-after = "what does this do?" Tests-first = "what should this do?" The difference is bias. |
| "I already manually tested it" | Manual testing is ad-hoc, non-repeatable, and incomplete. No record, no regression protection. |
| "Deleting X hours of work is wasteful" | Sunk cost fallacy. The time is gone. Rewrite with confidence or keep code you cannot trust. |
| "Need to explore first" | Fine. Throw away the exploration. Start fresh with RED. Exploration that becomes production code skipped TDD. |
| "The test is hard to write" | Hard to test = hard to use. The test is telling you the design needs work. |
| "TDD slows me down" | TDD is faster than debugging. You pay upfront for certainty instead of paying later for uncertainty. |
| "This is different because..." | It is not. This rationalization is the most common and the most wrong. |
| "The simulation already covers this" | Simulations (PH-005) validate contracts, not implementations. Implementation needs its own tests against real code. |
| "We're behind schedule, skip tests" | Tests prevent the rework that put you behind. Skipping them makes the problem worse. |


## Red Flags -- STOP and Start Over

If any of these are happening, you have left the TDD discipline:

- Production code exists without a failing test that preceded it
- A test passed on its first run (you never saw RED)
- You changed a test assertion to match incorrect output
- You refactored while any test was failing
- You added behavior during a REFACTOR step
- You wrote "I'll add tests later" or "tests can come after"
- You kept pre-TDD code as "reference" while writing tests

**All of these mean: delete the untested code, start over with RED.**


## Methodology Integration

This skill works alongside other methodology skills in PH-006:

- **traceability-discipline** loads alongside this skill and governs
  traceability of implementation back to prior-phase artifacts. This
  skill does not repeat traceability rules.

- **code-review-discipline** is used by the JUDGE to verify that the
  implementation follows TDD cadence. The judge checks for evidence
  of red-green-refactor discipline in the implementation history.

- Prior phases provide the behavioral specifications that drive RED
  step test cases. Each test should trace to a contract operation
  (PH-004) or simulation scenario (PH-005). Traceability-discipline
  governs how that trace is recorded.

- PH-005 simulations are NOT a substitute for implementation tests.
  Simulations validate contract correctness before code exists.
  TDD tests validate that the implementation satisfies the contract.
  Both are required.
