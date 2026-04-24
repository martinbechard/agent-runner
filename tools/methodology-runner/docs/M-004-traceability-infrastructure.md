# Traceability Infrastructure — Implementable Specification

---

## 1. TRACEABILITY DATA MODEL

### 1.1 Node Identity

Every traceable element in the pipeline is identified by a composite key:

```yaml
# Node identity schema
node:
  phase: integer          # 0-6
  element_type: string    # See element type registry below
  element_id: string      # The full prefixed ID (e.g., "RI-001", "F-003")
```

**Element Type Registry** — the canonical mapping from phase to element types and ID prefixes:

```yaml
element_type_registry:
  - phase: 0
    types:
      - name: "requirement"
        prefix: "RI"
        artifact_path: "docs/requirements/requirements-inventory.yaml"
        collection_path: "$.inventory_items"
        id_field: "id"

  - phase: 1
    types:
      - name: "feature"
        prefix: "F"
        artifact_path: "docs/features/feature-specification.yaml"
        collection_path: "$.features"
        id_field: "feature_id"
      - name: "acceptance_criterion"
        prefix: "AC"
        artifact_path: "docs/features/feature-specification.yaml"
        collection_path: "$.features[*].acceptance_criteria"
        id_field: "criterion_id"

  - phase: 2
    types:
      - name: "component"
        prefix: "C"
        artifact_path: "docs/design/solution-design.yaml"
        collection_path: "$.components"
        id_field: "component_id"
      - name: "interaction"
        prefix: "I"
        artifact_path: "docs/design/solution-design.yaml"
        collection_path: "$.interactions"
        id_field: "interaction_id"

  - phase: 3
    types:
      - name: "contract"
        prefix: "CT"
        artifact_path: "docs/design/interface-contracts.yaml"
        collection_path: "$.contracts"
        id_field: "contract_id"
      - name: "operation"
        prefix: "OP"
        artifact_path: "docs/design/interface-contracts.yaml"
        collection_path: "$.contracts[*].operation_name"
        id_field: "operation_name"
      - name: "schema"
        prefix: "S"
        artifact_path: "docs/design/interface-contracts.yaml"
        collection_path: "$.shared_types"
        id_field: "type_id"

  - phase: 4
    types:
      - name: "simulation"
        prefix: "SIM"
        artifact_path: "docs/simulations/simulation-definitions.yaml"
        collection_path: "$.simulations"
        id_field: "id"
      - name: "integration_scenario"
        prefix: "SCN"
        artifact_path: "docs/simulations/simulation-definitions.yaml"
        collection_path: "$.simulations[*].integration_scenarios"
        id_field: "id"

  - phase: 5
    types:
      - name: "module"
        prefix: "M"
        artifact_path: "docs/implementation/implementation-plan.yaml"
        collection_path: "$.implementation_order"
        id_field: "component_id"
      - name: "unit_test"
        prefix: "UT"
        artifact_path: "docs/implementation/implementation-plan.yaml"
        collection_path: "$.implementation_order[*].unit_test_plan"
        id_field: "test_id"

  - phase: 6
    types:
      - name: "acceptance_test"
        prefix: "AT"
        artifact_path: "docs/verification/verification-report.yaml"
        collection_path: "$.e2e_tests"
        id_field: "test_id"
```

### 1.2 Edge Schema

Each edge is a directed link from a downstream element to the upstream element it traces to. The direction convention is: **source performs the action on target**. "F-001 fulfills RI-003" means the feature is the source and the requirement is the target.

```yaml
# Single traceability edge
edge:
  source_ref: string       # Element ID of the downstream element (e.g., "F-001")
  target_ref: string       # Element ID of the upstream element (e.g., "RI-003")
  relationship_type: string  # One of the five canonical types (see below)
  source_phase: integer    # Phase number of source element (derived, for indexing)
  target_phase: integer    # Phase number of target element (derived, for indexing)
  rationale: string        # Optional. One sentence explaining why this link exists.
                           # Required when the connection is non-obvious.
```

**Relationship Type Definitions** — each type has a semantic meaning and valid phase pairs:

```yaml
relationship_types:
  - type: "fulfills"
    meaning: "Source element satisfies or addresses target element"
    valid_pairs:
      - { source_phase: 1, target_phase: 0 }   # F fulfills RI
      - { source_phase: 6, target_phase: 1 }   # AT fulfills AC

  - type: "decomposes"
    meaning: "Source element breaks target element into finer-grained parts"
    valid_pairs:
      - { source_phase: 1, target_phase: 1 }   # AC decomposes F (within phase)
      - { source_phase: 2, target_phase: 1 }   # C decomposes F into architecture
      - { source_phase: 3, target_phase: 2 }   # CT decomposes I into contracts

  - type: "implements"
    meaning: "Source element provides a concrete realization of target element"
    valid_pairs:
      - { source_phase: 5, target_phase: 3 }   # M implements CT
      - { source_phase: 5, target_phase: 2 }   # M implements C

  - type: "tests"
    meaning: "Source element verifies the correctness of target element"
    valid_pairs:
      - { source_phase: 5, target_phase: 1 }   # UT tests AC
      - { source_phase: 6, target_phase: 1 }   # AT tests AC
      - { source_phase: 6, target_phase: 0 }   # AT tests RI (end-to-end)

  - type: "simulates"
    meaning: "Source element provides a test double for target element"
    valid_pairs:
      - { source_phase: 4, target_phase: 3 }   # SIM simulates CT
      - { source_phase: 4, target_phase: 3 }   # SC simulates OP
```

### 1.3 Graph Structure

The full traceability graph is a directed acyclic graph (DAG) with these properties:

- **Nodes**: all elements across all phases.
- **Edges**: all traceability links as defined above.
- **Partitioning**: edges are partitioned by the phase that produces them. Phase N produces edges from its own elements to elements in phases 0 through N-1 (and sometimes within phase N, e.g., AC decomposes F within Phase 1).
- **Root nodes**: RI-* items (Phase 0). These have no incoming edges. Every other node must be reachable from at least one root.
- **Leaf nodes**: AT-* items (Phase 6), UT-* items (Phase 5). These have no outgoing edges to later phases.

### 1.4 Supported Query Semantics

The graph must support five query types:

| Query | Input | Output | Algorithm |
|-------|-------|--------|-----------|
| **Forward trace** | An element ID (e.g., RI-003) | All elements downstream, organized by phase | BFS/DFS from the node following outgoing edges in the reverse direction (target-to-source, since edges point upstream). Equivalently: find all edges where target_ref matches, then recurse on each source_ref. |
| **Backward trace** | An element ID (e.g., AT-002) | All elements upstream, back to RI-* roots | BFS/DFS from the node following edges in the forward direction (source-to-target). Recurse on each target_ref. |
| **Coverage query** | A phase number N | For each element in phase N-1: list of phase-N elements that link to it, or "uncovered" | For every element in phase N-1, check if any edge exists with that element as target_ref and source_phase == N. |
| **Orphan detection** | A phase number N (N > 0) | Elements in phase N with no edge pointing to any element in phases 0..N-1 | For every element in phase N, check if any edge exists with that element as source_ref. If none, it is an orphan. |
| **Dead-end detection** | A phase number N (N < 6) | Elements in phase N with no edge from any element in phases N+1..6 | For every element in phase N, check if any edge exists with that element as target_ref and source_phase > N. If none, it is a dead end. |

---

## 2. STORAGE FORMAT

### 2.1 Directory Layout

```
docs/traceability/
  registry.yaml              # Element type registry (section 1.1 above)
  phase-0-links.yaml         # Edges produced by Phase 0 (typically empty; root phase)
  phase-1-links.yaml         # Edges from Phase 1 elements to Phase 0 elements
  phase-2-links.yaml         # Edges from Phase 2 elements to Phase 0-1 elements
  phase-3-links.yaml         # Edges from Phase 3 elements to Phase 0-2 elements
  phase-4-links.yaml         # Edges from Phase 4 elements to Phase 0-3 elements
  phase-5-links.yaml         # Edges from Phase 5 elements to Phase 0-4 elements
  phase-6-links.yaml         # Edges from Phase 6 elements to Phase 0-5 elements
  graph-index.yaml           # Merged index (auto-generated from per-phase files)
  validation-report.yaml     # Latest validation report
```

Rationale for per-phase partitioning:
- Each phase writes only its own file, avoiding merge conflicts.
- Incremental updates add or replace a single file.
- The merged index is derived, never hand-edited.

### 2.2 Per-Phase Link File Schema

```yaml
# docs/traceability/phase-{N}-links.yaml
---
metadata:
  phase_id: "PH-{NNN}-{name}"            # e.g., "PH-001-feature-specification"
  phase_number: 1                          # Integer for programmatic use
  artifact_path: "docs/features/feature-specification.yaml"
  generated_at: "2026-04-08T14:30:00Z"    # ISO 8601 timestamp
  source_element_count: 12                 # Total elements in this phase's artifact
  edge_count: 28                           # Total edges in this file

edges:
  - source_ref: "F-001"
    target_ref: "RI-001"
    relationship_type: "fulfills"
    rationale: ""

  - source_ref: "F-001"
    target_ref: "RI-002"
    relationship_type: "fulfills"
    rationale: "RI-002 specifies OAuth; F-001 covers all auth methods including OAuth"

  - source_ref: "AC-001-01"
    target_ref: "F-001"
    relationship_type: "decomposes"
    rationale: ""

  # ... one entry per edge
```

Field constraints:
- `source_ref` must be an element belonging to phase N (the phase this file represents).
- `target_ref` must be an element belonging to phase 0 through N (same or earlier).
- `relationship_type` must be one of the five canonical types and the source/target phases must match a valid pair from section 1.2.
- `rationale` is optional (empty string when the link is self-evident).

### 2.3 Merged Index Schema

The merged index is auto-generated by concatenating all per-phase files and building adjacency lists for efficient querying. It is never edited directly.

```yaml
# docs/traceability/graph-index.yaml
# AUTO-GENERATED — do not edit. Rebuild with: trace-tool rebuild-index
---
metadata:
  generated_at: "2026-04-08T15:00:00Z"
  phases_included: [0, 1, 2, 3, 4, 5, 6]
  total_nodes: 87
  total_edges: 214

# Adjacency list: for each element, its outgoing edges (source=this element)
# and incoming edges (target=this element)
nodes:
  RI-001:
    phase: 0
    type: "requirement"
    outgoing: []                # RI items have no outgoing edges (they are roots)
    incoming:                   # Elements that trace TO this RI item
      - { ref: "F-001", relationship: "fulfills", phase: 1 }
      - { ref: "F-002", relationship: "fulfills", phase: 1 }
      - { ref: "AT-001", relationship: "tests", phase: 6 }

  F-001:
    phase: 1
    type: "feature"
    outgoing:                   # Elements this feature traces TO (upstream)
      - { ref: "RI-001", relationship: "fulfills", phase: 0 }
      - { ref: "RI-002", relationship: "fulfills", phase: 0 }
    incoming:                   # Elements that trace TO this feature (downstream)
      - { ref: "AC-001-01", relationship: "decomposes", phase: 1 }
      - { ref: "C-001", relationship: "decomposes", phase: 2 }

  # ... one entry per element across all phases
```

### 2.4 Incremental Update Protocol

When a phase completes and produces new traceability links:

1. The orchestrator writes (or overwrites) `docs/traceability/phase-{N}-links.yaml`.
2. The orchestrator runs `trace-tool rebuild-index` which reads all per-phase files and regenerates `graph-index.yaml`.
3. The orchestrator runs `trace-tool validate` to check the updated graph.

When a phase is re-run (e.g., after upstream changes):

1. Overwrite the phase's link file entirely. Per-phase files are atomic — no partial updates.
2. If the re-run phase is not the last, also overwrite all downstream phase link files (since their target elements may have changed IDs).
3. Rebuild the index and re-validate.

No locking is needed: only one phase runs at a time (orchestrator guarantee), and each phase writes only its own file.

---

## 3. VALIDATION SCRIPTS

All validation scripts read the per-phase link files and the phase artifacts. They produce structured YAML reports to stdout and exit with code 0 (all checks pass) or 1 (failures found).

### 3.1 Completeness Check

**Purpose**: Every element in phase N has at least one edge connecting it to an element in phase N-1 (or earlier).

**Script**: `trace-tool check completeness [--phase N]`

**Algorithm**:

```
function check_completeness(phase_number):
    if phase_number == 0:
        return PASS  # Root phase has no upstream

    # 1. Load all elements from phase N's artifact
    elements = load_elements_from_artifact(phase_number)

    # 2. Load edges from phase-{N}-links.yaml
    edges = load_edges(phase_number)

    # 3. Build set of source_refs from edges
    linked_sources = { e.source_ref for e in edges }

    # 4. Find elements with no edge
    orphans = [ el for el in elements if el.id not in linked_sources ]

    # 5. Report
    report:
      phase: phase_number
      total_elements: len(elements)
      linked_elements: len(elements) - len(orphans)
      orphan_count: len(orphans)
      orphans:
        - element_id: "C-005"
          element_type: "component"
          issue: "No traceability edge to any upstream element"
      status: PASS if len(orphans) == 0 else FAIL
```

**When run without `--phase`**: iterates phases 1 through 6 and reports each.

### 3.2 Consistency Check

**Purpose**: Every element ID referenced in any edge (source_ref or target_ref) exists in the corresponding phase artifact.

**Script**: `trace-tool check consistency`

**Algorithm**:

```
function check_consistency():
    broken_refs = []

    for phase_number in 0..6:
        edges = load_edges(phase_number)

        for edge in edges:
            # Check source_ref exists in phase_number's artifact
            source_phase = phase_number
            if not element_exists(source_phase, edge.source_ref):
                broken_refs.append({
                    file: "phase-{phase_number}-links.yaml",
                    ref: edge.source_ref,
                    ref_role: "source_ref",
                    expected_phase: source_phase,
                    issue: "Element does not exist in phase artifact"
                })

            # Check target_ref exists in the target phase's artifact
            target_phase = resolve_phase_from_prefix(edge.target_ref)
            if not element_exists(target_phase, edge.target_ref):
                broken_refs.append({
                    file: "phase-{phase_number}-links.yaml",
                    ref: edge.target_ref,
                    ref_role: "target_ref",
                    expected_phase: target_phase,
                    issue: "Element does not exist in phase artifact"
                })

            # Check relationship_type is valid for this phase pair
            if not is_valid_pair(edge.relationship_type, source_phase, target_phase):
                broken_refs.append({
                    file: "phase-{phase_number}-links.yaml",
                    ref: "{edge.source_ref} -> {edge.target_ref}",
                    ref_role: "relationship_type",
                    issue: "Relationship '{edge.relationship_type}' is not valid "
                           "between phase {source_phase} and phase {target_phase}"
                })

    report:
      total_edges_checked: sum of all edge counts
      broken_reference_count: len(broken_refs)
      broken_references: broken_refs
      status: PASS if len(broken_refs) == 0 else FAIL
```

**Helper**: `resolve_phase_from_prefix(element_id)` uses the element type registry to map a prefix (e.g., "RI" from "RI-003") to a phase number.

### 3.3 Coverage Report

**Purpose**: For each phase boundary (N-1 to N), show what percentage of phase N-1 elements are targeted by at least one edge from phase N.

**Script**: `trace-tool check coverage`

**Algorithm**:

```
function check_coverage():
    coverage_rows = []

    for target_phase in 0..5:
        source_phase = target_phase + 1

        # All elements in the target (upstream) phase
        upstream_elements = load_elements_from_artifact(target_phase)
        upstream_ids = { el.id for el in upstream_elements }

        # All edges from the source (downstream) phase
        edges = load_edges(source_phase)
        covered_ids = { e.target_ref for e in edges if resolve_phase_from_prefix(e.target_ref) == target_phase }

        uncovered_ids = upstream_ids - covered_ids

        coverage_rows.append({
            upstream_phase: target_phase,
            downstream_phase: source_phase,
            upstream_element_count: len(upstream_ids),
            covered_count: len(covered_ids),
            uncovered_count: len(uncovered_ids),
            coverage_pct: round(len(covered_ids) / len(upstream_ids) * 100, 1) if upstream_ids else 100.0,
            uncovered_elements: sorted(uncovered_ids)
        })

    report:
      phase_coverage: coverage_rows
      overall_status: PASS if all rows have coverage_pct == 100.0 else FAIL

    # Example output:
    # phase_coverage:
    #   - upstream_phase: 0
    #     downstream_phase: 1
    #     upstream_element_count: 42
    #     covered_count: 40
    #     uncovered_count: 2
    #     coverage_pct: 95.2
    #     uncovered_elements: ["RI-017", "RI-038"]
```

### 3.4 End-to-End Trace Check

**Purpose**: For each RI-* item, trace the full chain through all phases down to Phase 6 and flag items that do not reach a Phase 6 acceptance test.

**Script**: `trace-tool check end-to-end`

**Algorithm**:

```
function check_end_to_end():
    # Load the merged index (or build it from per-phase files)
    graph = load_graph_index()

    # Get all RI items
    ri_items = [ node for node in graph.nodes if node.phase == 0 ]

    # Get the out-of-scope RI items from the feature specification
    out_of_scope_ids = load_out_of_scope_ids()

    chains = []
    incomplete_count = 0

    for ri in ri_items:
        if ri.id in out_of_scope_ids:
            chains.append({
                ri_id: ri.id,
                status: "out-of-scope",
                chain: [],
                reached_phases: [0],
                terminal_phase: 0,
                notes: "Excluded in feature specification out_of_scope section"
            })
            continue

        # BFS forward: find all elements reachable from this RI item
        # "Forward" means: find edges where target_ref == current node,
        # then follow source_ref as the next node
        visited = {}         # element_id -> phase
        queue = [ri.id]
        visited[ri.id] = 0

        while queue:
            current = queue.pop(0)
            # Find all edges where target_ref == current
            for edge in graph.incoming_edges(current):
                if edge.source_ref not in visited:
                    visited[edge.source_ref] = resolve_phase_from_prefix(edge.source_ref)
                    queue.append(edge.source_ref)

        reached_phases = sorted(set(visited.values()))
        terminal_phase = max(reached_phases)

        # Build the chain as a list of elements per phase
        chain_by_phase = {}
        for elem_id, phase in visited.items():
            chain_by_phase.setdefault(phase, []).append(elem_id)

        has_phase_6 = 6 in reached_phases
        if not has_phase_6:
            incomplete_count += 1

        chains.append({
            ri_id: ri.id,
            status: "complete" if has_phase_6 else "incomplete",
            reached_phases: reached_phases,
            terminal_phase: terminal_phase,
            chain: chain_by_phase,
            notes: "" if has_phase_6 else "Chain does not reach Phase 6 (verification)"
        })

    report:
      total_ri_items: len(ri_items)
      out_of_scope: count where status == "out-of-scope"
      in_scope: count where status != "out-of-scope"
      complete_chains: count where status == "complete"
      incomplete_chains: incomplete_count
      completion_pct: round(complete / in_scope * 100, 1)
      chains: chains  # Full detail
      status: PASS if incomplete_count == 0 else FAIL
```

**Output example** (abbreviated):

```yaml
total_ri_items: 42
out_of_scope: 3
in_scope: 39
complete_chains: 37
incomplete_chains: 2
completion_pct: 94.9
chains:
  - ri_id: "RI-001"
    status: "complete"
    reached_phases: [0, 1, 2, 3, 4, 5, 6]
    terminal_phase: 6
    chain:
      0: ["RI-001"]
      1: ["F-001", "AC-001-01", "AC-001-02"]
      2: ["C-001", "C-003", "I-001"]
      3: ["CT-001", "OP-001"]
      4: ["SIM-001", "SC-001-01", "SC-001-02"]
      5: ["M-001", "UT-001-01"]
      6: ["AT-001", "AT-002"]

  - ri_id: "RI-038"
    status: "incomplete"
    reached_phases: [0, 1, 2]
    terminal_phase: 2
    chain:
      0: ["RI-038"]
      1: ["F-012", "AC-012-01"]
      2: ["C-007"]
    notes: "Chain does not reach Phase 6 (verification)"
status: "FAIL"
```

### 3.5 Combined Validation

**Script**: `trace-tool validate`

Runs all four checks in sequence. Reports a unified result:

```yaml
validation_report:
  timestamp: "2026-04-08T15:00:00Z"
  checks:
    completeness: { status: "PASS", orphan_count: 0 }
    consistency: { status: "PASS", broken_ref_count: 0 }
    coverage: { status: "FAIL", min_coverage_pct: 95.2, gap_phase_pair: "0->1" }
    end_to_end: { status: "FAIL", incomplete_chains: 2 }
  overall_status: "FAIL"
  first_failure: "coverage"
```

This report is written to `docs/traceability/validation-report.yaml` and its exit code reflects overall_status.

---

## 4. QUERY INTERFACE

### 4.1 CLI Tool: `trace-tool`

A single binary/script with subcommands. All output defaults to YAML for machine consumption; `--format table` switches to human-readable tabular output.

#### Command: `trace-tool forward <element_id>`

Trace forward from an element to all downstream elements.

```
$ trace-tool forward RI-003

forward_trace:
  origin: "RI-003"
  origin_phase: 0
  downstream:
    phase_1:
      - id: "F-002"
        relationship: "fulfills"
      - id: "AC-002-01"
        relationship: "decomposes"
        via: "F-002"
    phase_2:
      - id: "C-001"
        relationship: "decomposes"
        via: "F-002"
      - id: "I-003"
        relationship: "decomposes"
        via: "F-002"
    phase_3:
      - id: "CT-003"
        relationship: "decomposes"
        via: "I-003"
    phase_4:
      - id: "SIM-003"
        relationship: "simulates"
        via: "CT-003"
    phase_5:
      - id: "M-001"
        relationship: "implements"
        via: "CT-003"
      - id: "UT-001-03"
        relationship: "tests"
        via: "AC-002-01"
    phase_6:
      - id: "AT-004"
        relationship: "tests"
        via: "AC-002-01"
  reaches_phase_6: true
```

**Table format** (`--format table`):

```
Phase | Element    | Relationship | Via
------+------------+--------------+--------
  1   | F-002      | fulfills     | direct
  1   | AC-002-01  | decomposes   | F-002
  2   | C-001      | decomposes   | F-002
  2   | I-003      | decomposes   | F-002
  3   | CT-003     | decomposes   | I-003
  4   | SIM-003    | simulates    | CT-003
  5   | M-001      | implements   | CT-003
  5   | UT-001-03  | tests        | AC-002-01
  6   | AT-004     | tests        | AC-002-01
```

#### Command: `trace-tool backward <element_id>`

Trace backward from an element to all upstream elements, terminating at RI-* roots.

```
$ trace-tool backward AT-004

backward_trace:
  origin: "AT-004"
  origin_phase: 6
  upstream:
    phase_1:
      - id: "AC-002-01"
        relationship: "tests"
    phase_1:
      - id: "F-002"
        relationship: "decomposes"
        via: "AC-002-01"
    phase_0:
      - id: "RI-003"
        relationship: "fulfills"
        via: "F-002"
      - id: "RI-007"
        relationship: "fulfills"
        via: "F-002"
  root_requirements: ["RI-003", "RI-007"]
```

#### Command: `trace-tool coverage [--phase N]`

Same as the coverage validation check (section 3.3) but available as a standalone query. Without `--phase`, reports all phase boundaries.

#### Command: `trace-tool orphans [--phase N]`

Lists elements with no upstream connection (completeness check, section 3.1).

#### Command: `trace-tool dead-ends [--phase N]`

Lists elements with no downstream continuation:

```
$ trace-tool dead-ends --phase 2

dead_ends:
  phase: 2
  elements:
    - id: "C-005"
      type: "component"
      issue: "No phase 3+ element traces to this component"
    - id: "I-008"
      type: "interaction"
      issue: "No phase 3+ element traces to this interaction"
```

#### Command: `trace-tool rebuild-index`

Reads all `phase-{N}-links.yaml` files, merges them, and writes `graph-index.yaml`. Run after any phase link file changes.

#### Command: `trace-tool validate`

Runs all four validation checks (section 3.5).

### 4.2 Programmatic API

For agents that need to query traceability during their work (e.g., the Judge verifying traceability claims, or the Generator building its mapping), the query interface is also available as a library.

**TypeScript interface** (reference implementation):

```typescript
interface TraceNode {
  elementId: string;
  phase: number;
  elementType: string;
}

interface TraceEdge {
  sourceRef: string;
  targetRef: string;
  relationshipType: "fulfills" | "decomposes" | "implements" | "tests" | "simulates";
  sourcePhase: number;
  targetPhase: number;
  rationale: string;
}

interface TraceChain {
  origin: string;
  elementsByPhase: Map<number, string[]>;
  reachedPhases: number[];
  isComplete: boolean;          // reaches Phase 6
}

interface CoverageResult {
  upstreamPhase: number;
  downstreamPhase: number;
  coveredIds: string[];
  uncoveredIds: string[];
  coveragePct: number;
}

interface TraceGraph {
  // Load from per-phase files or from the merged index
  static load(traceabilityDir: string): TraceGraph;

  // Core queries
  forwardTrace(elementId: string): TraceChain;
  backwardTrace(elementId: string): TraceChain;
  coverageForPhase(targetPhase: number, sourcePhase: number): CoverageResult;
  orphans(phase: number): TraceNode[];
  deadEnds(phase: number): TraceNode[];

  // Edge-level queries
  outgoingEdges(elementId: string): TraceEdge[];  // edges where source_ref == elementId
  incomingEdges(elementId: string): TraceEdge[];  // edges where target_ref == elementId

  // Bulk queries
  allRoots(): TraceNode[];                          // all RI-* items
  endToEndChains(): TraceChain[];                   // one chain per RI item
  elementExists(elementId: string): boolean;

  // Mutation (used by generators and orchestrator)
  addEdge(edge: TraceEdge): void;
  removeEdgesForPhase(phase: number): void;
  writePhaseFile(phase: number): void;              // writes phase-{N}-links.yaml
  rebuildIndex(): void;                             // writes graph-index.yaml
}
```

**Python interface** (equivalent):

```python
class TraceGraph:
    @classmethod
    def load(cls, traceability_dir: str) -> "TraceGraph": ...

    def forward_trace(self, element_id: str) -> TraceChain: ...
    def backward_trace(self, element_id: str) -> TraceChain: ...
    def coverage_for_phase(self, target_phase: int, source_phase: int) -> CoverageResult: ...
    def orphans(self, phase: int) -> list[TraceNode]: ...
    def dead_ends(self, phase: int) -> list[TraceNode]: ...
    def outgoing_edges(self, element_id: str) -> list[TraceEdge]: ...
    def incoming_edges(self, element_id: str) -> list[TraceEdge]: ...
    def element_exists(self, element_id: str) -> bool: ...

    def add_edge(self, edge: TraceEdge) -> None: ...
    def remove_edges_for_phase(self, phase: int) -> None: ...
    def write_phase_file(self, phase: int) -> None: ...
    def rebuild_index(self) -> None: ...
```

### 4.3 Agent Integration Patterns

How each agent uses the query interface during its work:

| Agent | Query Pattern | Purpose |
|-------|---------------|---------|
| **Checklist Extractor** | `coverage_for_phase(current - 1, current)` | Identify upstream elements that need checklist items |
| **Checklist Validator** | `element_exists(source_ref)` for each item | Grounding check: does the referenced element exist? |
| **Artifact Generator** | `backward_trace(element_id)` for each element it creates | Build the traceability mapping as it generates |
| **Artifact Generator** | `incoming_edges(checklist_item_id)` | Verify every checklist item has a mapping entry |
| **Judge** | `forward_trace(ri_item)` | Verify that traceability claims connect to real upstream requirements |
| **Judge** | `element_exists(artifact_location)` | Verify artifact_location refs in evaluations |
| **Traceability Validator** | `orphans(N)`, `dead_ends(N)`, `coverage_for_phase(N-1, N)` | All intra-phase checks |
| **Traceability Validator** | `end_to_end_chains()` | Cross-phase chain integrity |
| **Orchestrator** | `validate()` (combined check) | Gate phase completion |

---

## 5. IMPLEMENTATION STACK

**Recommended concrete stack**:

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Storage format | YAML | Human-readable, supported by all pipeline languages, structure maps directly to the data model |
| CLI tool language | TypeScript (Node.js) | Matches the project's existing TypeScript server; can share types with the programmatic API |
| YAML parsing | `yaml` npm package (or `js-yaml`) | Preserves comments, handles anchors, widely used |
| Graph traversal | In-memory adjacency lists | The graph is small (hundreds of nodes, low thousands of edges); no database needed |
| CLI framework | `commander` or `yargs` | Standard Node.js CLI libraries |
| Validation output | YAML to stdout + exit code | Machine-readable for orchestrator, human-readable for debugging |
| Testing | `vitest` | Matches the project's existing test framework |

**Alternative stacks** (if constraints differ):

- **Python-only project**: Use `pyyaml` + `click` for CLI. Same data model and algorithms.
- **Polyglot project**: Implement the storage format and per-phase files in YAML (language-agnostic), and provide thin CLI wrappers in each language that read the YAML files.
- **Large-scale project** (thousands of requirements): Replace the in-memory graph with SQLite. Schema maps directly: `nodes` table (element_id, phase, type), `edges` table (source_ref, target_ref, relationship_type, rationale). Queries become SQL.

---

## 6. FILE REFERENCE SUMMARY

| File | Written By | Read By | Format |
|------|-----------|---------|--------|
| `docs/traceability/registry.yaml` | Human (once) | All tools | YAML |
| `docs/traceability/phase-{N}-links.yaml` | Orchestrator after each phase | `trace-tool`, all agents | YAML |
| `docs/traceability/graph-index.yaml` | `trace-tool rebuild-index` | `trace-tool` queries, agents | YAML |
| `docs/traceability/validation-report.yaml` | `trace-tool validate` | Orchestrator, human review | YAML |
| Phase artifacts (per element_type_registry) | Artifact Generator | `trace-tool` consistency checks | YAML |
