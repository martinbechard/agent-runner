---
name: solution-design-patterns
description: Tech-agnostic solution-design discipline — separation of concerns, interface design, dependency boundaries, error handling
---

# Solution Design Patterns

This skill governs the design discipline for PH-003 (Solution Design).
Its scope is the judgment calls that generation_instructions do not
cover: how to assign responsibilities within a component, how to
define interactions between components, how to manage dependency
direction, and how to design error handling across boundaries.

This skill is the FLOOR, not the ceiling. Stack-specific design
patterns -- the idioms, framework conventions, and implementation
techniques for a particular technology -- come from companion skills
that the Skill-Selector loads based on the component's
expected_expertise entries in the stack manifest. This skill ensures
every solution design addresses the four universal disciplines
regardless of technology. It does NOT teach Go patterns, React
patterns, SQL patterns, or any technology-specific approach.

Traceability mechanics -- source_refs, source_quote, coverage_check,
coverage_verdict, inherited_assumptions, and the Quote Test -- are
governed by the companion traceability-discipline skill loaded
alongside this one. This skill focuses on HOW to design and WHAT to
declare in the solution design artifact.


## Output Schema: solution-design.yaml

Understanding the target schema drives every judgment call below.

```yaml
design_metadata:
  source_specification: string   # path to feature specification
  design_date: string            # ISO 8601
  total_component_count: integer
  total_interaction_count: integer

components:
  - component_id: CMP-NNN       # from stack manifest -- never invent
    name: string
    description: string          # WHY this is a separate component
    responsibilities:            # concrete verb-phrases, 1-7 items
      - string
    technology_constraints: []   # from inventory constraints

interactions:
  - interaction_id: INT-NNN
    from_component: CMP-NNN     # initiator
    to_component: CMP-NNN       # receiver (different from initiator)
    communication_style: >-
      synchronous-request-response | asynchronous-event |
      asynchronous-command | streaming | shared-state
    data_summary: string         # WHAT flows, not the schema
    features_served: [FT-NNN]

feature_realization_map:
  - feature_id: FT-NNN
    participating_components: [CMP-NNN]
    interaction_sequence: [INT-NNN]  # happy-path order
    notes: string

external_dependencies:
  - dependency_id: EXT-NNN
    name: string
    description: string
    features_dependent: [FT-NNN]
    assumption_refs: []          # ASM-* IDs this fulfills
```


## Component Integrity Rule

**The stack manifest from PH-002 defines the component boundaries.
This skill designs WITHIN those boundaries. You NEVER invent, split,
merge, or rename components.**

The component_id values in the solution design MUST match the IDs
from the stack manifest exactly. If PH-002 declared CMP-001-api as a
single component, the solution design has CMP-001-api as a single
component. Internal layers (handler, service, repository) are
implementation details for PH-006, not separate components in PH-003.

### CORRECT

```yaml
# PH-002 declared CMP-001-api. PH-003 designs it as one component.
components:
  - component_id: CMP-001-api
    responsibilities:
      - "Validates incoming order requests against domain rules"
      - "Persists order lifecycle state changes to the data store"
```

### WRONG: Splitting a Stack-Manifest Component

```yaml
# PH-002 declared CMP-001-api as ONE component.
# PH-003 split it into three. This is WRONG.
components:
  - component_id: CMP-001-handler    # INVENTED
  - component_id: CMP-001-service    # INVENTED
  - component_id: CMP-001-repository # INVENTED
# Internal layering is PH-006 implementation detail.
# PH-003 has no authority to decompose PH-002's component boundaries.
```


## Technology Abstraction Discipline

The solution design is technology-agnostic. Responsibilities, data
summaries, and error descriptions use DOMAIN language, never
implementation-specific types, library names, database schemas,
framework component trees, or language-specific constructs.

This is the single most important discipline in this skill and the
one most likely to fail under pressure.

### The Rule

**Every responsibility, data_summary, and error description must be
expressible without naming any programming language, library, framework,
database engine, or implementation construct.**

### The Abstraction Test

For each field value, ask:

> "Would this text still be accurate if the component were
> reimplemented in a completely different technology stack?"

- **YES** -> properly abstracted. Keep it.
- **NO** -> technology has leaked. Rewrite in domain terms.

### CORRECT

```yaml
responsibilities:
  - "Validates incoming order requests against domain rules"
  - "Persists order lifecycle state changes to the data store"
  - "Queries and aggregates product data for search results"
  - "Coordinates payment authorization with the external provider"

data_summary: >
  Request: product name substring and optional category filter.
  Response: list of matching products with name, category, and price.

error_description: >
  On failure: domain error 'task not found' or 'assignment conflict'
```

### WRONG

```yaml
# LEAKED: Go types, pgx driver, PostgreSQL schema
responsibilities:
  - "Queries the products PostgreSQL table using ILIKE on the name column"
  - "Inserts rows into orders table (id uuid, status text, created_at timestamptz)"
  - "Translates *pgx.PgError (code 23505) into domain errors"

# LEAKED: React component hierarchy
responsibilities:
  - "Renders <ProductBrowsePage> composing <SearchBar> and <ProductGrid>"
  - "Maintains cart state in CartContext via useReducer"

# LEAKED: library and struct types in data summary
data_summary: "Sends CreateOrderRequest{CartItems []CartItem{ProductID uuid.UUID}} via encoding/json"

# LEAKED: database-specific error
error_description: "Returns psycopg2.IntegrityError on duplicate key"
```

### How Technology Leakage Happens

Your primary failure mode under pressure is writing technology-
specific details when asked to "be detailed" or "be precise." Detail
means more domain specificity, NOT more implementation specificity.

| Pressure | Leaked form | Correct form |
|----------|------------|-------------|
| "Be detailed" | "Queries products table with ILIKE on name column" | "Searches products by name substring and optional category" |
| "Be precise" | "Returns *pgx.PgError code 23505" | "Returns domain error: duplicate entity" |
| "Be thorough" | "Renders ProductGrid with CSS Grid of ProductCard components" | "Displays matching products in a browsable list" |
| "Include types" | "Accepts CreateOrderRequest{CartItems []CartItem}" | "Accepts ordered list of product identifiers and quantities" |
| "Show the schema" | "Inserts into orders(id uuid, status text)" | "Persists order with lifecycle status" |
| "Name the libraries" | "Uses stripe-go SDK PaymentIntent API" | "Coordinates payment authorization with external provider" |

### Technology Leak Red Flags

If a responsibility, data_summary, or error description matches ANY
of these patterns, it is a technology leak:

- Names a programming language construct (struct, class, hook, reducer)
- Names a library or framework type (pgx, stripe-go, React.createContext)
- Contains SQL syntax (SELECT, INSERT, JOIN, WHERE)
- Contains database column or table names
- Names specific HTTP status codes (use domain error categories)
- Contains framework component names (ProductGrid, CartDrawer)
- References language-specific patterns (useReducer, channels, goroutines)

**All of these mean: rewrite in domain language.**


## Design Procedure

For each component in the stack manifest, walk these steps in order.
Do NOT skip steps. Do NOT jump to a later component before finishing
the current one.


### Step 1: Enumerate Responsibilities (Separation of Concerns)

Read the component's role, features_served, and technology from the
stack manifest. For each feature served, ask: what distinct
responsibilities must this component fulfill to deliver this feature?

A responsibility is a concrete verb-phrase describing ONE thing the
component does in domain terms. Not a category ("handles data"),
not a technology ("uses PostgreSQL"), not a vague bucket ("manages
utilities"), not an implementation task ("renders ProductGrid").

**The Responsibility Test:**

> "Can I write a focused module for this responsibility alone,
> without needing to know the internals of any other responsibility?"

- **YES** -> well-bounded. Keep it.
- **NO** -> tangled. Split it.

**Responsibility Count: 1-7 per component. No exceptions.**

Zero means the component has no reason to exist. More than seven
means the component is a god module.

Do NOT add responsibilities to "be thorough." Do NOT list 10+
responsibilities "for completeness." The limit is 7. If you find
yourself wanting more, you are either (a) listing implementation
tasks instead of design responsibilities, or (b) the component
genuinely needs to be split -- but that split happens in PH-002, not
PH-003.

| Pressure | Response |
|----------|----------|
| "List 10+ responsibilities" | Maximum is 7. Compress at the design level, not the implementation level. |
| "Be more thorough" | Thoroughness is in quality of each responsibility, not quantity. |
| "Show completeness" | 7 well-defined responsibilities that cover all features IS complete. |

**The Overlap Test:**

For each pair of components, compare their responsibility lists.
If two components share a responsibility (even paraphrased), one
must own it and the other must delegate via an interaction.


### Step 2: Define Interactions (Interface Design)

For each pair of components that participate in the same feature,
declare one or more interactions.

An interaction is defined by:
1. **Direction:** who initiates (from_component) and who receives
   (to_component). Higher-level policy initiates; lower-level
   mechanism receives.
2. **Communication style:** synchronous-request-response if the
   initiator needs a result before continuing; asynchronous-event
   or asynchronous-command if it can proceed without waiting.
3. **Data summary:** WHAT data flows, described in domain terms.
   Not the schema, not the types, not the serialization format.
4. **Error behavior:** what error categories apply (see Step 4).

**Interactions are cross-component ONLY.** A self-interaction
(from_component == to_component) is an internal module boundary,
not an architectural interaction. Never declare it.

**The Narrowest Interface Principle:**

> "Does this interface expose the minimum data needed by the caller,
> or does it leak internal structure?"

- Expose behavior (what it does), not structure (how it's organized)
- Return results, not internal state
- Accept parameters, not configuration objects


### Step 3: Verify Dependency Direction (Dependency Boundaries)

For each interaction, verify the dependency flows correctly:
higher-level policy depends on lower-level mechanism.

**Cycle Detection:** Walk the interaction graph. If A depends on B
and B depends on A (directly or transitively), you have a cycle.

Fix by:
1. Extracting the shared concern into an external dependency
2. Inverting one dependency through an abstraction (event, callback)
3. Recognizing that the two components should be one (escalate to
   PH-002 revision)

**The Independence Test:**

> "Can this component be tested with a fake/stub of every component
> it depends on?"

- **YES** -> dependency boundaries are clean.
- **NO** -> hidden coupling. Find it and make it explicit.


### Step 4: Classify Error Handling (Error Patterns)

For each interaction, classify how errors propagate.

**The Error Boundary Principle:**

> "Every component boundary is an error boundary. Errors from a
> dependency must be translated at the boundary, never leaked raw."

**Error Classification per Interaction:**

| Category | Component's job | Example |
|----------|----------------|---------|
| **Validation** | Reject invalid input before processing | Missing required field |
| **Domain** | Signal a business rule violation | Duplicate entity, insufficient inventory |
| **Infrastructure** | Translate to domain terms at boundary | Connection timeout -> "service unavailable" |
| **Unexpected** | Log and surface as opaque failure | Internal assertion violation |

Describe errors in domain terms. NEVER in technology terms.

- CORRECT: "Domain error: payment declined"
- WRONG: "Returns stripe.CardError with code card_declined"

**Async Error Handling:**

Asynchronous interactions cannot return errors synchronously.
The design must specify:
- Where failed messages are retried or dead-lettered
- How the originator learns about failure
- System state after partial failure


### Step 5: Build Feature Realization Map

For each feature in the feature specification:
1. Identify the trigger (user action or system event)
2. Walk through each component that participates
3. List the interactions in execution order
4. Verify every component-to-component link has a declared interaction

**The Completeness Test:**

> "Can I trace from trigger to outcome through declared interactions
> alone, without inventing any undeclared communication?"

- **YES** -> the realization is complete.
- **NO** -> missing interaction. Declare it.


### Step 6: Identify External Dependencies

For each feature assumption (data_assumption, interface_assumption)
in the feature specification, determine:

- **Internal:** a component's responsibilities cover the concern.
  Map the assumption to the component.
- **External:** no component owns the concern. Declare an
  external_dependency with the assumption_refs it fulfills.


## TRANSFORM: Stack Manifest -> Solution Design

### INPUT (PH-002 artifact, abbreviated)

```yaml
components:
  - id: CMP-001-backend
    name: "Task Management API"
    role: "HTTP API implementing task CRUD, assignment, dashboard queries, and notification dispatch"
    technology: python
    features_served: [FT-001, FT-002, FT-003]

integration_points: []
```

### CORRECT OUTPUT

```yaml
components:
  - component_id: CMP-001
    name: "Task Management API"
    description: >
      Single backend component handling all task domain logic,
      persistence, and notification dispatch. Separate component
      unnecessary because all features share technology, deployment,
      and domain boundary.
    responsibilities:
      - "Validates incoming task requests against domain rules"
      - "Persists task lifecycle state changes to the data store"
      - "Queries and aggregates task data for dashboard views"
      - "Dispatches assignment notifications to the email subsystem"
    technology_constraints:
      - "Python 3.12 (source constraint)"

interactions:
  - interaction_id: INT-001
    from_component: CMP-001
    to_component: EXT-001
    communication_style: asynchronous-command
    data_summary: "Email payload: recipient, subject, body"
    features_served: [FT-003]

feature_realization_map:
  - feature_id: FT-001
    participating_components: [CMP-001]
    interaction_sequence: []
    notes: "Self-contained within CMP-001; no cross-component interaction"
  - feature_id: FT-002
    participating_components: [CMP-001]
    interaction_sequence: []
    notes: "Dashboard queries are internal to CMP-001's persistence layer"
  - feature_id: FT-003
    participating_components: [CMP-001]
    interaction_sequence: [INT-001]
    notes: "CMP-001 dispatches notification via INT-001 to external email service"

external_dependencies:
  - dependency_id: EXT-001
    name: "SMTP Email Service"
    description: "Accepts email payloads and delivers to recipients"
    features_dependent: [FT-003]
    assumption_refs: [ASM-007]
```

### What makes this correct

- **Component Integrity:** CMP-001 matches the stack manifest. No
  splits, no invented sub-components.
- **Responsibilities:** Four verb-phrases, all domain-level. No
  Python types, no SQL, no framework names.
- **Interactions:** One cross-component interaction to EXT-001. No
  self-interactions for internal module boundaries.
- **Errors:** INT-001 is asynchronous-command. Notification failure
  does not fail the task assignment.
- **Realization:** Each feature traces from trigger to outcome.
- **External dependency:** ASM-007 (SMTP) mapped to EXT-001.

### COUNTER-EXAMPLES

```yaml
# WRONG: vague responsibilities
responsibilities:
  - "Handles tasks"
  - "Manages data"
  - "Does notifications"
  # These are categories, not verb-phrases. Fails Responsibility Test.

# WRONG: technology-specific responsibilities
responsibilities:
  - "Queries products table with ILIKE on name column"
  - "Renders <ProductGrid> with CSS Grid of <ProductCard> components"
  - "Uses pgxpool.Pool for connection management"
  # Leaked: SQL, React components, Go library. Rewrite in domain terms.

# WRONG: exceeded 7 responsibilities
responsibilities:
  - "Validates tasks"
  - "Persists tasks"
  - "Queries dashboard"
  - "Sends notifications"
  - "Manages user sessions"
  - "Handles authentication"
  - "Logs audit events"
  - "Generates reports"
  - "Processes batch imports"
  # Nine. Split OR compress at the design level.

# WRONG: invented component (splitting a stack-manifest component)
components:
  - component_id: CMP-001-handler
  - component_id: CMP-001-service
  - component_id: CMP-001-repository
  # Stack manifest has CMP-001-api. Internal layers are PH-006.

# WRONG: self-interaction
interactions:
  - interaction_id: INT-005
    from_component: CMP-001
    to_component: CMP-001
    data_summary: "Validation module calls persistence module"
  # Self-interactions are implementation details, not architecture.

# WRONG: leaked error type
data_summary: "Returns *pgx.PgError code 23505 on duplicate key"
  # Leaks the database driver and error code. Rewrite as:
  # "Domain error: duplicate entity"

# WRONG: circular dependency
interactions:
  - from_component: CMP-001
    to_component: CMP-002
  - from_component: CMP-002
    to_component: CMP-001
  # Neither can be tested independently. Fix the cycle.

# WRONG: missing interaction for feature realization
feature_realization_map:
  - feature_id: FT-003
    participating_components: [CMP-001, CMP-002]
    interaction_sequence: []
  # Two components participate but no interaction declared.
```


## Anti-Patterns

### God Module
More than seven responsibilities. Split along responsibility
boundaries -- but the split happens in PH-002, not here. If you
discover a god module in PH-003, raise it as a finding, do not
split the component yourself.

### Circular Dependencies
A -> B -> A. Neither independently testable. Extract shared concern,
invert via abstraction, or flag for PH-002 merge.

### Leaky Abstraction
Interface exposes implementation technology. Database errors as
PostgreSQL exceptions, framework types in data summaries, language
constructs in responsibilities. Translate at every boundary.

### Error Swallowing
Component catches error and silently continues. Every caught error
must result in: (a) translated error to caller, (b) bounded retry,
or (c) logged incident with explicit degraded-state handling.

### Phantom Interaction
Two components in the same realization but no declared interaction
between them. If they cooperate, declare it. If they don't, remove
one from the participating list.

### Responsibility Overlap
Two components both claim the same responsibility. One must own it;
the other delegates via interaction.


## Scope Boundary: This Skill vs. Stack-Specific Skills

This skill covers WHAT to design at the technology-agnostic level.
It does NOT cover:

- Framework-specific module structure (FastAPI routers, React
  component trees, Go handler patterns)
- Language-specific constructs (dependency injection, hooks,
  goroutines, protocols)
- Technology-specific error types (HTTP status codes, gRPC status,
  database driver errors)
- ORM patterns, database migration strategies, caching layers
- Serialization formats, wire protocols, API versioning

Stack-specific skills ADD to this floor. They are loaded by the
Skill-Selector based on expected_expertise entries and provide
the technology-appropriate idioms for each component.


## Generator Pre-Emission Checklist

1. Every component_id matches a component in the stack manifest
2. No components invented, split, merged, or renamed
3. Every component has 1-7 concrete verb-phrase responsibilities
4. All responsibilities use domain language, not technology terms
5. No responsibility appears in more than one component
6. Every pair of co-participating components has a declared interaction
7. Every interaction specifies direction, communication style, and data summary
8. No self-interactions (from_component != to_component)
9. Interaction graph is acyclic
10. Every interaction has error handling classified by category
11. Error descriptions use domain terms, not technology-specific types
12. Every feature has a realization map entry with interaction sequence
13. Every feature assumption maps to a component responsibility or external dependency
14. External dependencies have assumption_refs
15. Traceability checks deferred to traceability-discipline
