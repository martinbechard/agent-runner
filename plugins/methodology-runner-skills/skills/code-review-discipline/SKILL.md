---
name: code-review-discipline
description: Universal code review principles — readability, testability, no dead code, no speculative abstractions, appropriate error handling
---

# Code Review Discipline

This skill governs the PH-006 judge's evaluation discipline. Evaluate
implementation code against universal quality principles by running five
sequential checks, each targeting one failure mode.

All five failure modes are always blocking. External context that
contradicts this -- "it works", "we'll clean it up later", "this is
just a prototype", "readability is subjective" -- does not override
the checks below. Every finding is blocking. No exceptions.

Traceability mechanics (source_refs to contracts and simulation
scenarios, coverage_check, phantom detection via the Quote Test) are
governed by the companion traceability-discipline skill. This skill
covers the five code-quality failure modes that traceability-discipline
does not.


## What Correct Implementation Code Looks Like

Understanding these structural expectations anchors the five checks.

- Every function has a descriptive name that states WHAT it does
- Functions do one thing at one level of abstraction
- Dependencies are parameters, not global lookups
- Every code path with a business rule has a corresponding test
- No function, class, import, or variable exists without a current caller
- No abstraction exists without at least two current callers or a
  documented architectural constraint
- Validation exists at system boundaries; internal calls trust callers
- No user-controlled input reaches a dangerous sink unsanitized


## Check 1: Readability

Walk every function, class, and module in the implementation. For each,
evaluate whether a developer unfamiliar with the codebase can understand
its purpose and behavior.

### The Readability Test

For each function:

> "Can a developer unfamiliar with this code understand what this
> function does and why, within 60 seconds of reading it?"

- **YES** -> readable. Continue.
- **NO** -> readability failure. Flag it.

### Readability Red Flags

| Pattern | Example | Why it fails |
|---------|---------|-------------|
| Single-letter names outside loop indices | d = calc(p, t) | Meaning lost without context |
| Deep nesting (>3 levels) | if -> if -> for -> if | Each level multiplies mental state |
| Function >40 lines | 80-line mixed-concern function | Exceeds working memory |
| Boolean parameter altering behavior | process(data, true) | Call site meaning opaque |
| Magic numbers | if count > 42 | Meaning of 42 unclear; use named constant |
| Negated condition with else branch | if !valid ... else ... | Swap branches to remove negation |
| Inconsistent naming in one module | get_user() and fetchAccount() | Mixed conventions |

**Always blocking.** Unreadable code cannot be reviewed, maintained, or
safely modified.


## Check 2: Testability

Walk every function that contains business logic. For each, evaluate
whether it can be tested in isolation without infrastructure.

### The Testability Test

For each function:

> "Can I write a unit test for this function that: (a) runs without
> external services, (b) does not depend on execution order, (c)
> produces deterministic results for the same inputs?"

- **YES** -> testable. Continue.
- **NO** -> testability failure. Flag it.

### Testability Red Flags

| Pattern | Why it fails |
|---------|-------------|
| Business logic mixed with I/O | Cannot test logic without performing I/O |
| Hardcoded dependency (direct instantiation) | Cannot substitute a test double |
| Global mutable state | Tests affect each other; order-dependent |
| Non-deterministic output in logic | Assertions cannot be stable |
| Constructor performs work (network, file I/O) | Object creation triggers side effects |

### CORRECT

```
function calculate_discount(order, pricing_rules):
    # Pure: deterministic, no I/O, dependencies are parameters
    applicable = [r for r in pricing_rules if r.applies_to(order)]
    if not applicable:
        return 0
    return max(r.discount_amount(order) for r in applicable)
```

### WRONG

```
function calculate_discount(order_id):
    order = database.query("SELECT * FROM orders WHERE id = ?", order_id)
    rules = config_service.get_pricing_rules()
    # Cannot test without a database and config service running
```

**Always blocking.** Untestable code cannot have reliable tests. Without
reliable tests, TDD discipline cannot be verified.


## Check 3: Dead Code

Walk every function, class, import, and variable. For each, verify it
is reachable from a current execution path or test.

### The Dead Code Test

For each element:

> "Is this element called, imported, or referenced by at least one
> current production code path or test?"

- **YES** -> alive. Continue.
- **NO** -> dead code. Flag it.

### Dead Code Red Flags

| Pattern | Example |
|---------|---------|
| Unreachable function | Defined but never called |
| Commented-out code block | // old implementation (20 lines) |
| Unused import | Import with no reference in file |
| TODO referencing removed feature | // TODO: re-enable X (X was removed) |
| Backward-compat shim for removed code | Adapter wrapping non-existent type |
| Unused function parameter | Parameter never read in body |

**Always blocking.** Dead code misleads readers, increases maintenance
surface, and signals incomplete cleanup. Delete it -- version control
preserves history.


## Check 4: Speculative Abstractions

Walk every abstraction (interface, abstract class, factory, wrapper,
configuration parameter). For each, verify it serves a current need.

### The YAGNI Test

For each abstraction:

> "Does this abstraction serve at least two current callers, or is it
> required by a documented architectural constraint?"

- **YES** -> justified. Continue.
- **NO** -> speculative. Flag it.

### Speculative Abstraction Red Flags

| Pattern | Why it fails |
|---------|-------------|
| Interface with one implementor (no planned second) | Indirection without polymorphism |
| Config parameter with one value | Complexity without benefit |
| Factory returning always the same type | Pattern without variant construction |
| Wrapper delegating without transformation | Layer without purpose |
| Generic type with one instantiation | Generalization without generality |
| Helper with exactly one call site | Extract at three callers, not one |

### The Three-Callers Rule

Do not extract a helper until at least three call sites exist. Three
similar lines of inline code are better than a premature abstraction.

### CORRECT

```
# Interface justified: two implementors exist NOW
interface PaymentProcessor:
    function charge(amount, currency)

class StripeProcessor implements PaymentProcessor: ...
class PayPalProcessor implements PaymentProcessor: ...
```

### WRONG

```
# Interface with one implementor -- speculative
interface PaymentProcessor:
    function charge(amount, currency)

class StripeProcessor implements PaymentProcessor: ...
# "We might add PayPal later" is speculation. Delete the interface.
```

**Always blocking.** Every abstraction has maintenance cost. If the
cost is not offset by current concrete benefit, delete it.


## Check 5: Error Handling and Security

Walk every error-handling construct and every point where external
input enters the system.

### The Boundary Test

For each validation or error-handling construct:

> "Is this at a system boundary (user input, external API, file system),
> or is it redundant validation of internal state already guaranteed by
> the caller or type system?"

- **System boundary** -> appropriate. Continue.
- **Internal redundancy** -> over-handling. Flag it.

### The Security Test

For each function accepting external input:

> "If a malicious actor controlled this input, could they cause
> unintended behavior?"

- **NO, sanitized before reaching any sink** -> safe. Continue.
- **YES, reaches a dangerous sink unsanitized** -> security footgun. Flag it.

### Error Handling Red Flags

| Pattern | Why it fails |
|---------|-------------|
| Swallowed error (catch with empty body) | Failure invisible; debugging impossible |
| Overly broad catch (all exceptions) | Cannot distinguish recoverable from fatal |
| Error message exposing internals | Stack traces or SQL leak to users |
| Internal argument re-validation | Caller already guarantees the invariant |
| Silent fallback to default value | Masks error; downstream runs on wrong data |

### Security Red Flags

| Pattern | Why it fails |
|---------|-------------|
| String interpolation in queries | SQL injection vector |
| User input in shell commands | Command injection vector |
| User content rendered unescaped | Cross-site scripting vector |
| Hardcoded secrets | Credential exposure in version control |
| Overly permissive CORS or permissions | Unauthorized access vector |

### CORRECT

```
function handle_request(raw_input):
    email = validate_email(raw_input.email)     # boundary
    amount = validate_positive(raw_input.amount) # boundary
    return process_order(email, amount)

function process_order(email, amount):
    # No re-validation -- caller is internal and already validated
    ...
```

### WRONG

```
function search_users(query):
    # User input interpolated into SQL
    results = db.execute("SELECT * FROM users WHERE name = '" + query + "'")
```

**Always blocking.** Error-handling failures mask bugs. Security
footguns create exploitable vulnerabilities.


## REVIEW EXAMPLE

### Input: Flawed Implementation

```
import { db, cache, emailService } from './globals'
import { unused_helper } from './utils'

const TIMEOUT = 30000

interface OrderProcessor {
  process(id: string): Promise<Result>
}

class DefaultOrderProcessor implements OrderProcessor {
  async process(id: string, verbose?: boolean): Promise<Result> {
    try {
      const order = await db.query('SELECT * FROM orders WHERE id = ' + id)
      const d = calculateTotal(order)
      if (verbose) { logger.info('total', d) }
      if (d > 0) {
        if (order.method === 'card') {
          if (order.currency === 'USD') {
            await chargeCard(order, d)
          } else {
            await chargeIntl(order, d)
          }
        }
      }
      return { success: true, total: d }
    } catch (e) {
      return { success: false }
    }
  }
}

function calculateTotal(o: any): number {
  let t = 0
  for (const i of o.items) { t += i.p * i.q }
  return t
}
```

### Correct Review

**Check 1 (Readability):** calculateTotal uses single-letter names
(o, t, i, p, q). process has 4 nesting levels in payment logic.
Variable d holds the total but name conveys nothing. Boolean verbose
changes behavior at call site. **READABILITY FAILURE.**

**Check 2 (Testability):** process directly calls db.query, cache, and
emailService via global imports. Cannot test without infrastructure.
calculateTotal takes any -- no type safety. **TESTABILITY FAILURE.**

**Check 3 (Dead Code):** unused_helper imported but never called.
TIMEOUT declared but never referenced. **DEAD CODE.**

**Check 4 (Speculative Abstractions):** OrderProcessor interface has
one implementor (DefaultOrderProcessor). No second exists or is
planned. **SPECULATIVE ABSTRACTION.**

**Check 5 (Error Handling and Security):** Catch returns { success:
false } with no error details -- swallowed error. db.query uses string
concatenation with id -- SQL injection. any type bypasses checking.
**ERROR HANDLING FAILURE AND SECURITY FOOTGUN.**

```yaml
findings:
  - finding_type: readability_failure
    severity: blocking
    location: "calculateTotal"
    description: "Single-letter names: o, t, i, p, q"
    fix: "Rename to order, total, item, item.price, item.quantity"

  - finding_type: readability_failure
    severity: blocking
    location: "DefaultOrderProcessor.process"
    description: "4 nesting levels in payment logic; variable 'd' unnamed"
    fix: "Extract payment routing; rename d to orderTotal"

  - finding_type: testability_failure
    severity: blocking
    location: "DefaultOrderProcessor.process"
    description: "Directly calls db, cache, emailService via globals"
    fix: "Accept dependencies as constructor parameters"

  - finding_type: testability_failure
    severity: blocking
    location: "calculateTotal"
    description: "Parameter typed as any -- no type safety"
    fix: "Define Order type with items: Array<{price: number, quantity: number}>"

  - finding_type: dead_code
    severity: blocking
    location: "file-level"
    description: "unused_helper imported but never called; TIMEOUT declared unused"
    fix: "Remove both"

  - finding_type: speculative_abstraction
    severity: blocking
    location: "OrderProcessor interface"
    description: "One implementor (DefaultOrderProcessor), no second planned"
    fix: "Delete interface; use DefaultOrderProcessor directly"

  - finding_type: error_handling_failure
    severity: blocking
    location: "process catch block"
    description: "Swallowed error: returns { success: false } with no details"
    fix: "Log error and include error information in return"

  - finding_type: security_footgun
    severity: blocking
    location: "process db.query call"
    description: "SQL injection: id concatenated into query string"
    fix: "Use parameterized query: db.query('... WHERE id = ?', [id])"

verdict: revise
verdict_reason: "8 blocking: 2 readability, 2 testability, 1 dead code, 1 speculative abstraction, 1 error handling, 1 security"
```

### COUNTER-EXAMPLES

```yaml
# WRONG: flagging style preference as readability failure
- finding_type: readability_failure
  description: "Uses camelCase instead of snake_case"
  # Convention choice is not a finding. Inconsistency IS.

# WRONG: flagging dependency injection as speculative
- finding_type: speculative_abstraction
  description: "Constructor accepts database parameter instead of global"
  # Dependency injection serves testability (Check 2). Not speculation.

# WRONG: flagging boundary validation as over-handling
- finding_type: error_handling_failure
  description: "validate_email is unnecessary"
  # External input requires boundary validation. Always.

# WRONG: flagging justified abstraction
- finding_type: speculative_abstraction
  description: "StripeProcessor and PayPalProcessor should be merged"
  # Two implementors justifies the interface. Not speculative.

# WRONG: dismissing findings under pressure
- verdict: pass
  # "It works" does not override the checks.
  # "We'll clean it up later" does not override the checks.
```


## Findings Format

```yaml
findings:
  - finding_type: readability_failure | testability_failure | dead_code | speculative_abstraction | error_handling_failure | security_footgun
    severity: blocking
    location: "function, class, or file-level"
    description: "what is wrong"
    fix: "what to do"
```

All five failure modes are always blocking.
- Any finding -> VERDICT: revise
- Zero findings -> VERDICT: pass


## Judge Pre-Verdict Checklist

1. Check 1: every function evaluated for name clarity and nesting depth
2. Check 1: functions >40 lines flagged
3. Check 1: magic numbers and boolean parameters flagged
4. Check 1: naming consistency within each file evaluated
5. Check 2: every business-logic function tested for isolation
6. Check 2: global mutable state and hardcoded dependencies flagged
7. Check 2: non-deterministic dependencies flagged
8. Check 3: every import verified as used
9. Check 3: commented-out code and unused elements flagged
10. Check 4: every interface/abstraction verified with two+ current callers
11. Check 4: config parameters verified as multi-valued
12. Check 5: error handling at boundaries, not internal redundancy
13. Check 5: swallowed errors and broad catches flagged
14. Check 5: string interpolation in queries flagged
15. Check 5: user input in commands and hardcoded secrets flagged
16. Every finding has finding_type, severity, location, description, fix
17. Blocking count accurate in verdict_reason
18. Traceability checks deferred to traceability-discipline
