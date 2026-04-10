---
name: architecture-decomposition
description: Decompose features into technology components with free-text expertise descriptions and explicit integration points
---

# Architecture Decomposition

This skill governs the decomposition discipline for PH-002
(Architecture). Its scope is the judgment calls that
generation_instructions do not cover: how to identify component
boundaries, how to choose integration protocols, how to maintain
technology coherence within a component, and how to write
expected_expertise descriptions.

Traceability mechanics -- source_refs, source_quote, coverage_check,
coverage_verdict, inherited_assumptions, and the Quote Test -- are
governed by the companion traceability-discipline skill loaded
alongside this one. This skill focuses on HOW to decompose and WHAT
to declare in the stack manifest.


## Output Schema: stack-manifest.yaml

Understanding the target schema drives every judgment call below.

```yaml
components:
  - id: CMP-NNN-slug        # sequential ID with mnemonic slug
    name: "Human-readable"   # what this component IS
    role: "One sentence"     # what this component DOES
    technology: python       # programming language
    runtime: "python3.12"   # specific runtime version
    frameworks: [fastapi]    # architectural dependencies (empty if not source-mandated)
    persistence: postgresql  # data storage (if any)
    expected_expertise: []   # FREE-TEXT knowledge areas (see Expertise Discipline below)
    features_served: [FT-001]
    source_refs: [FT-001]   # traceability to PH-001 and constraints

integration_points:
  - id: IP-NNN
    between: [CMP-001-x, CMP-002-y]
    protocol: "HTTP/JSON over TLS"
    contract_source: "Contract document produced in PH-004"

rationale: |
  Explains WHY this decomposition, not WHAT it contains.

open_assumptions:
  - id: ASM-PH2-NNN
    detail: "What is assumed"
    needs: "What confirmation is required"
    status: open
```

A component is a deployable unit of technology-coherent code, NOT
an infrastructure resource. A PostgreSQL database is persistence
WITHIN a component, never a standalone component. A Redis cache is
an implementation detail, not a component.


## Decomposition Procedure

Walk the feature specification in feature-ID order. For each feature,
decide which component it belongs to using these steps.

### Step 1: Technology Test

What technology does this feature require? Features implemented in
the same language, targeting the same runtime, belong in the same
candidate component. A Python API and a React dashboard cannot share
a component. Different language or runtime = different component.

### Step 2: Deployment Test

Would this feature deploy as part of the same artifact as the other
features in the candidate component? A backend server and its
database migrations share a deployment boundary. A mobile app and
the backend it calls do not. Different deployment target = different
component.

### Step 3: Scaling Test

Within the same technology and deployment, does this feature have
fundamentally different scaling characteristics? A synchronous API
handling 1000 req/s and a batch job running hourly have different
resource profiles. If scaling divergence is significant enough that
the features would be deployed at different scales in production,
split them. If no source constraint mandates different scaling,
keep them together.

### Step 4: Apply the Default

If all features pass all three tests (same technology, same deployment,
no scaling divergence), they form ONE component. The default is the
fewest components possible. You need a reason to split.

**Do NOT split for "separation of concerns" within a single runtime.**
Internal module boundaries are PH-003 (Solution Design), not PH-002
(Architecture). Three Python features accessing the same database and
deploying as one service are ONE component.

### Step 5: Declare Technology

For each component, assign:
- **technology**: the programming language
- **runtime**: specific version or environment
- **frameworks**: architectural dependencies (leave EMPTY if no source
  constraint mandates a specific framework; state the gap as an
  open_assumption instead)
- **persistence**: data storage if applicable

Every choice must trace to a source constraint or feature requirement.
If no source mandates the technology, declare it as an open_assumption.

### Step 6: Identify Integration Points

For every PAIR of components, ask: do they exchange data or trigger
behavior in each other?

- **YES**: declare an integration_point with protocol and
  contract_source. The contract_source always references a downstream
  phase (typically PH-004 Contract-First Interface Definitions).
- **NO**: no integration point.

**Implicit state sharing is forbidden.** Two components accessing the
same database IS an integration point:

```yaml
- id: IP-002
  between: [CMP-001-backend, CMP-003-worker]
  protocol: "shared-postgresql"
  contract_source: "Schema definition produced in PH-004"
```

If two components share data and you have not declared an integration
point, the decomposition is wrong.


## Expertise Description Discipline

This section governs the most important field in the stack manifest.
expected_expertise is the bridge between architecture and downstream
skill selection. Getting it wrong breaks the entire skill-routing
pipeline.

### The Rule

**expected_expertise entries are free-text descriptions of knowledge
areas, NOT Claude Code skill IDs, catalog names, or hyphenated slugs.**

This decouples the architecture from the skill catalog. The architect
reasons about "what knowledge will this component need?" without
knowing which SKILL.md files are installed. The Skill-Selector maps
expertise descriptions to concrete skill IDs at runtime. The mapping
is a trivial judgment call because expertise descriptions and skill
descriptions use similar natural language.

### How to Write Good Expertise Descriptions

Each entry is a natural-language phrase with three parts:
1. **Technology or domain**: "Python", "React", "PostgreSQL"
2. **Activity or concern**: "backend development", "component design"
3. **Specificity when warranted**: "with FastAPI", "using SQLAlchemy"

### CORRECT

```yaml
expected_expertise:
  - "Python backend development"
  - "FastAPI framework conventions and best practices"
  - "SQLAlchemy ORM patterns and migrations"
  - "Test-driven development with pytest"
  - "Python code review discipline"
```

### WRONG: Skill Catalog IDs

```yaml
expected_expertise:
  - "python-backend-impl"
  - "fastapi-conventions"
  - "sqlalchemy-patterns"
  - "pytest-tdd"
```

These are hyphenated slugs that look like file names. A job posting
would never list "fastapi-conventions" as a required skill. Rewrite
each as natural language.

### WRONG: Generic Without Technology

```yaml
expected_expertise:
  - "backend development"
  - "API design"
  - "database patterns"
```

Too vague for the Skill-Selector to map reliably. Always name the
specific technology: "Python backend development" not "backend
development", "PostgreSQL database design" not "database patterns".

### WRONG: Implementation-Level Tasks

```yaml
expected_expertise:
  - "Writing FastAPI dependency injection providers"
  - "Configuring SQLAlchemy session middleware"
```

These are implementation tasks, not knowledge areas. The right
abstraction level is framework expertise: "FastAPI framework
conventions and best practices".

### The Natural Language Test

For every expected_expertise entry:

> "Would a job posting use this exact phrase to describe a required
> skill?"

- **YES** -> legitimate expertise description. Keep it.
- **NO** -> likely a catalog leak or wrong abstraction level. Rewrite.

### How Catalog Leaking Happens

Your primary failure mode under pressure is writing expertise entries
that resemble skill-catalog identifiers. When pressured to be "precise"
or "actionable":

| Pressure | Leaked form | Correct form |
|----------|------------|-------------|
| "Be precise" | "tdd" | "Test-driven development with pytest" |
| "Be actionable" | "python-code-review" | "Python code review discipline" |
| "Match the catalog" | "fastapi-conventions" | "FastAPI framework conventions and best practices" |
| "Be concise" | "react-impl" | "React component design and hooks" |
| "Be specific" | "sqlalchemy-patterns" | "SQLAlchemy ORM patterns and migrations" |
| "Use IDs" | "accessibility-review" | "Accessibility review and WCAG compliance" |

### Catalog Leak Red Flags

If an expertise entry matches ANY of these patterns, it is a catalog
leak:
- Contains hyphens joining words (slug-case)
- Reads like a file name without the extension
- Omits articles, prepositions, or context words
- Could be copy-pasted as a directory name

**All of these mean: rewrite as natural-language prose.**


## TRANSFORM: Feature Specification -> Stack Manifest

### INPUT (PH-001 artifact, abbreviated)

```yaml
features:
  - feature_id: FT-001
    name: "Task Lifecycle"
    source_refs: [RI-001, RI-002, RI-004]
    acceptance_criteria:
      - text: "Creating a task persists it with title, description, and due date"
      - text: "Assigning a task records the assignee"
      - text: "Marking a task as complete changes its status"

  - feature_id: FT-002
    name: "Task Dashboard"
    source_refs: [RI-005, RI-006]
    acceptance_criteria:
      - text: "Dashboard displays open task count grouped by assigned user"
      - text: "With 10,000 tasks, the query completes in under 2 seconds"
    depends_on: [FT-001]

  - feature_id: FT-003
    name: "Assignment Notifications"
    source_refs: [RI-003]
    acceptance_criteria:
      - text: "When a task is assigned, an email is sent to the assignee"
    depends_on: [FT-001]
    inherited_assumptions:
      - id: ASM-007
        detail: "the email server supports SMTP"
```

### CORRECT OUTPUT

```yaml
components:
  - id: CMP-001-backend
    name: "Task Management API"
    role: "HTTP API implementing task CRUD, assignment, dashboard queries, and notification dispatch"
    technology: python
    runtime: "python3.12"
    frameworks:
      - fastapi
      - sqlalchemy
    persistence: postgresql
    expected_expertise:
      - "Python backend development"
      - "FastAPI framework conventions and best practices"
      - "SQLAlchemy ORM patterns and migrations"
      - "Test-driven development with pytest"
      - "Python code review discipline"
    features_served: [FT-001, FT-002, FT-003]
    source_refs: [FT-001, FT-002, FT-003]

integration_points: []

rationale: |
  All three features operate on the same domain entity (tasks) within a
  single technology and deployment boundary. No source constraint mandates
  separate deployment or different technologies. A single Python backend
  is the simplest architecture satisfying the requirements.

open_assumptions:
  - id: ASM-PH2-001
    detail: "Python 3.12 and FastAPI chosen based on team familiarity; no source constraint mandates either"
    needs: "stakeholder confirmation of technology choice"
    status: open
```

### What makes this correct

- **Step 1-3:** All features pass all three tests -> one component
- **Step 4:** Default applied -- single component, fewest possible
- **Step 5:** Technology declared as assumption (no source mandate)
- **Step 6:** Zero integration points (single component has no cross-
  component interfaces)
- **Expertise:** All entries pass the Natural Language Test

### COUNTER-EXAMPLES

```yaml
# WRONG: database as a separate component
- id: CMP-001-backend
  persistence: postgresql
- id: CMP-002-database
  name: "PostgreSQL Database"
  technology: postgresql
  # A database is persistence WITHIN a component, not a component itself.
  # Components are deployable units of application code.

# WRONG: god component spanning technologies
- id: CMP-001-everything
  technology: python
  frameworks: [fastapi, react]
  features_served: [FT-001, FT-002, FT-003, FT-004]
  # React is JavaScript/TypeScript. Different technology = different component.

# WRONG: premature split within one technology
- id: CMP-001-tasks
  features_served: [FT-001]
- id: CMP-002-dashboard
  features_served: [FT-002]
- id: CMP-003-notifications
  features_served: [FT-003]
  # All Python, same deployment, same domain. Three components for one
  # technology creates 3 unnecessary integration points.

# WRONG: implicit state sharing
components:
  - id: CMP-001-backend
    persistence: postgresql
  - id: CMP-002-worker
    persistence: postgresql
integration_points: []
  # Both access the same database. Must declare an integration point
  # with protocol: "shared-postgresql".

# WRONG: expertise as catalog IDs
expected_expertise:
  - "python-backend-impl"
  - "fastapi-conventions"
  - "sqlalchemy-patterns"
  # Fails Natural Language Test. Rewrite as prose.

# WRONG: technology without source justification and no assumption
technology: rust
frameworks: [actix-web]
  # No source constraint mandates Rust. Must be declared as
  # open_assumption, or traced to a specific requirement.
```


## Anti-Patterns

### God Component
Spans multiple technologies or deployment boundaries. If a component
lists both Python and TypeScript frameworks, split along the technology
boundary.

### Premature Decomposition
Splits features that share technology, deployment, and domain into
separate components. Creates unnecessary integration points. The cost
of unnecessary integration always exceeds the cost of a larger
component.

### Database as Component
Treats a data store (PostgreSQL, Redis, S3) as a standalone component
instead of as persistence within an application component. Databases
are infrastructure, not deployable application code. A PostgreSQL
instance is the persistence field on CMP-001, not CMP-002.

### Implicit State Sharing
Two components access the same store without a declared integration
point. If CMP-001 writes to PostgreSQL and CMP-002 reads from the
same PostgreSQL, declare the coupling. Undeclared shared state is
the architecture's equivalent of a global variable.

### Expertise Catalog Leak
expected_expertise entries that look like skill IDs (hyphenated slugs)
instead of natural-language knowledge descriptions. Apply the Natural
Language Test.


## Generator Pre-Emission Checklist

1. Every FT-* appears in at least one component's features_served
2. No component spans multiple technology boundaries
3. Every pair of data-exchanging components has an integration_point
4. Every expected_expertise entry passes the Natural Language Test
5. Technology choices traced to source or declared as open_assumptions
6. rationale explains WHY this decomposition, not just WHAT it contains
7. Shared data stores have explicit integration points
8. No component serves zero features
9. Databases are persistence within components, not standalone components
10. contract_source references PH-004 or another downstream phase
11. Frameworks listed only when source-mandated; otherwise open_assumption
12. Traceability checks deferred to traceability-discipline
