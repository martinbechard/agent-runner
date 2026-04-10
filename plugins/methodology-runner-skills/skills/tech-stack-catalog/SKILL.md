---
name: tech-stack-catalog
description: High-level catalog of candidate technology stacks with shallow per-stack properties and selection criteria
---

# Tech Stack Catalog

This skill provides a technology selection procedure and reference
catalog for the PH-002 Architecture phase. It is consumed alongside
architecture-decomposition: that skill identifies component boundaries,
this skill informs the technology choice for each component.

This is deliberately shallow. Deep per-stack implementation knowledge
is the job of tech-specific skills loaded in later phases. This skill
answers "which stack?" not "how to use the stack?"


## Technology Selection Procedure

When architecture-decomposition Step 5 asks you to declare technology
for a component, walk this procedure for each component.

### Step 1: Check Source Constraints

Read the feature specification and inherited requirements for explicit
technology mentions. If the source names a technology ("the backend
must use Python", "deploy as a Go microservice"), use it and trace the
choice to the source ref. No further selection needed for that
dimension.

Organizational preferences (CTO wants Rust, team prefers TypeScript)
are NOT source constraints. Record them as open_assumptions with a
disposition (accepted or rejected) and a rationale grounded in the
catalog. Never silently ignore or silently comply -- document the
decision.

### Step 2: Classify the Workload

Determine which workload archetype best matches the component:

- **HTTP API** -- request/response serving (REST, gRPC, GraphQL)
- **Interactive UI** -- browser-based user interaction
- **CLI tool** -- command-line application for users or CI
- **Background worker** -- queue consumer, batch processor, cron job
- **Real-time** -- persistent connections (WebSocket, SSE, streaming)
- **ML service** -- model inference or training pipeline
- **Data pipeline** -- ETL, data transformation, analytics
- **Mobile app** -- native iOS/Android application
- **Systems library** -- performance-critical library, WASM target

### Step 3: Consult the Catalog

Look up the workload archetype in the Stack Catalog below. Each entry
lists recommended stacks with their trade-offs for that archetype.

### Step 4: Apply Tiebreakers

If multiple stacks are equally viable and no source constraint
distinguishes them, apply these in order:

1. **Source constraints first.** Named technologies in the source
   requirements take precedence. Trace the choice.
2. **Team expertise second.** Prefer the stack the team knows. Declare
   team-based choices as open_assumptions.
3. **Ecosystem fit third.** Pick the stack whose library ecosystem
   most directly supports the feature's primary concern.
4. **Simplicity fourth.** Prefer fewer runtime dependencies, simpler
   deployment, smaller container.
5. **Consistency last.** Prefer the stack already used by other
   components in this manifest, to reduce cognitive overhead.

### Step 5: Record the Choice

Populate the component's technology, runtime, frameworks, and
persistence fields. If the choice was not source-mandated, declare it
as an open_assumption with needs: "stakeholder confirmation of
technology choice".


## Stack Catalog

### HTTP API

| Stack | When to pick | When to avoid |
|---|---|---|
| **Python (FastAPI/Django)** | Data processing features, ML integration, team knows Python | CPU-bound hot paths with sub-ms latency requirements |
| **Node.js (TypeScript)** | Full-stack TS team, heavy I/O, real-time endpoints | CPU-intensive computation per request |
| **Go** | High-throughput (10K+ req/s), operational simplicity (single binary) | Complex business logic where expressiveness matters more than throughput |
| **Rust (Axum/Actix)** | Extreme latency requirements, systems-adjacent API | Standard CRUD -- development velocity cost is too high |

### Interactive UI

| Stack | When to pick | When to avoid |
|---|---|---|
| **TypeScript + React** | Large ecosystem needed, complex state management | Simple content-heavy pages (use server rendering) |
| **TypeScript + Vue/Svelte** | Smaller team, simpler mental model preferred | Need for vast third-party component library |
| **TypeScript + Next.js/Nuxt** | SEO matters, initial load performance critical | Pure SPA with no SSR needs (adds deployment complexity) |

### CLI Tool

| Stack | When to pick | When to avoid |
|---|---|---|
| **Rust (Clap)** | End-user distribution, fast startup, cross-platform binary | Rapid prototyping, team unfamiliar with Rust |
| **Go** | Single binary, faster development, simpler language | Complex argument parsing or text processing |
| **Python (Click/Typer)** | Developer tool, team knows Python, pipx distribution OK | End-user tool where runtime dependency is a problem |

### Background Worker

| Stack | When to pick | When to avoid |
|---|---|---|
| **Python** | Data-heavy work (ETL, ML, report generation) | High message throughput with low resource budget |
| **Go** | High throughput, low memory footprint per worker | Complex data transformation logic with many library dependencies |
| **Node.js** | I/O-dominant work (calling external APIs, aggregation) | CPU-intensive processing per message |

### Real-Time Communication

| Stack | When to pick | When to avoid |
|---|---|---|
| **Node.js** | WebSocket/SSE, moderate connection count, mature library ecosystem | 100K+ simultaneous connections |
| **Go** | High connection count (goroutines are cheap), SSE from existing Go API | Team unfamiliar with Go concurrency patterns |

### ML Inference

| Stack | When to pick | When to avoid |
|---|---|---|
| **Python** | Always -- ecosystem (PyTorch, TensorFlow, HuggingFace, scikit-learn) is decisive | Never avoid for ML inference |
| **Go/Rust API gateway** | Front a Python inference service for routing, auth, rate-limiting | N/A -- two-component pattern, not standalone |

### Data Pipeline / ETL

| Stack | When to pick | When to avoid |
|---|---|---|
| **Python** | Default (pandas, polars, dbt, Spark/Beam Python API) | Extreme streaming throughput per stage |
| **Go/Rust** | Individual streaming stages with high throughput needs | Batch analytics with complex transformations |

### Mobile

| Stack | When to pick | When to avoid |
|---|---|---|
| **Swift** | iOS with deep platform API integration (camera, sensors, background) | Cross-platform requirements |
| **Kotlin** | Android with deep platform API integration | Cross-platform requirements |
| **React Native** | Both platforms, team knows TypeScript, features are UI-over-API | Heavy native API usage |
| **Flutter** | Both platforms, custom rendering, Dart acceptable | Team strongly prefers TypeScript |

### Systems / WASM

| Stack | When to pick | When to avoid |
|---|---|---|
| **Rust** | Memory safety without GC, WASM target, performance-critical | Standard application code where GC is acceptable |
| **Go** | Simpler systems tool, acceptable GC pauses | WASM (GC overhead), zero-allocation requirements |


## Quick-Reference Properties

For cross-cutting decisions that span archetypes (e.g., choosing
between two backends that serve different features):

| Stack | Concurrency model | Deployment | Ecosystem breadth | Team availability |
|---|---|---|---|---|
| Python | async/await (I/O), multiprocessing (CPU) | Container or venv | Vast (data, ML, web) | High |
| Node.js (TS) | Event loop, worker threads | Container; needs Node runtime | Vast (web, tooling) | High |
| Go | Goroutines + channels | Single binary, tiny container | Moderate (networking, cloud) | Moderate |
| Rust | async/await (tokio), ownership | Single binary, no runtime | Growing (systems, WASM) | Low |
| TS Frontend | Single-threaded + async fetch | Browser bundle, SSR optional | Vast (UI components) | High |


## What This Skill Does NOT Cover

- **Implementation patterns** for any stack (downstream skills like
  python-backend-impl, react-impl)
- **Framework selection within a stack** (FastAPI vs Django is PH-003
  or a stack-specific skill)
- **Infrastructure provisioning** (databases, queues, cloud services
  are operational concerns, not architecture)
- **expected_expertise descriptions** (governed by
  architecture-decomposition's Expertise Description Discipline)
