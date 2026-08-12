<!--
Copyright (c) 2026 Martin.Bechard@DevConsult.ca
Artifact-ID: 1989ebf6-3664-42fb-95b9-f0d057a43c22
Created-UTC: 2026-08-12T15:00:04Z
Creating-Agent: Dev Artifact Reviewer
Runtime: Codex
Dispatched-Model: gpt-5.6-sol
Reasoning-Effort: low
Task-ID: /root/review_cd004
Artifact-ID-Evidence: runtime-supplied
Created-UTC-Evidence: runtime-supplied
Creating-Agent-Evidence: runtime-supplied
Runtime-Evidence: runtime-supplied
Dispatched-Model-Evidence: runtime-supplied
Reasoning-Effort-Evidence: runtime-supplied
Task-ID-Evidence: runtime-supplied
-->

# CD-004 Agent Report Worker Protocol Review Checklist

## Review Trace

- Target: `docs/design/components/CD-004-agent-report-worker-protocol.md`
- Review date: 2026-08-12
- Design mode: `PLANNED_DEVELOPMENT`
- Scope: Python and Rust envelopes and symbols, lifecycle, standard-output purity, progress limits, concurrency, cancellation, grace, forced termination, restart, path and privacy boundaries, diagnostics, atomicity, errors, tests, documentation acceptance, and implementation readiness.
- Authorities: `docs/requirements/functional/FR-001-agent-report-dynamic-app-and-static-export.md`, `docs/architecture/ARC-001-agent-report-dynamic-app-and-static-export.md`, `docs/design/high-level/HLD-003-agent-report-dynamic-app-and-static-export.md`, `docs/design/components/CD-002-agent-report-application-service.md`, current project configuration, and current Tauri process-management evidence.
- Templates and checklists: `module-design-template.md`, `review-checklist-structured.md`, and `review-checklist-module-design.md`.
- File placement: `docs/project-taxonomy.md` assigns completed review checklists to `docs/reviews/`; the requested path conforms.
- Terminology: `TERMINOLOGY STANDARDS LOADED`, ABSENT in configured snapshot revision `d801aa1fb7ddcc330a5e3173372ea6af4a3d08ec58074478e85aa5603e926658`. No governed preferred terms were available.

## Correction Re-review

- Re-reviewed target SHA-256: `e17a18fc6289405c6095adb05c4372ab88b9400f74f4ea5a213e6b0e11621817`
- Re-review date: 2026-08-12
- Re-review scope: Every original RVW-014 finding, with explicit checks for named `ServiceResult` schemas, exact Python and Rust envelopes, Worker-versus-host cancellation, path grants, `RecoveryCoordinator`, untrusted standard-error sanitation, 50-millisecond progress coalescing, and Unix/Windows process-tree mechanisms and tests.
- Result: Seven findings are resolved. CD004-01 is partially corrected but remains open because the operation dispatch ledger does not bind each named method to its exact `ServiceResult[T]` result type and wire schema.

### Final Closure Re-review

- Final target SHA-256: `2ff743f625dadfa9cc9b5bb2f592235916c73b609a3ac33b76f03d69756431ac`
- Final re-review date: 2026-08-12
- Final scope: The remaining CD004-01 exact per-operation `ServiceResult[T]` and result-schema binding, including rejection of a wrong valid CD-002 dataclass and a valid `PageResult` containing the wrong row class.
- Result: CD004-01 is resolved. All eight original RVW-014 findings are closed at the documentation-design level.

#### CD004-01 Final Closure — Resolved

- Status: pass
- Evidence type: summary
- Evidence source: final CD-004 Python Symbol Ledger, PC-01A, PR-05, Error Handling, and Python Test Targets; accepted CD-002 Public Contracts
- Correction evidence: `OperationBinding` binds an exact request class, named method, result class, optional page-row class, and serializer. `ServiceResultValue` enumerates all thirteen accepted result families. The dispatch and result ledger maps each operation to its exact `ServiceResult[T]` and exact wire result schema. The nested-schema ledger defines every retained CD-002 nested type. Runtime validation requires exact classes, rejects subclasses, validates every specialized page item, and checks snapshot and operation correlation before traversal or output.
- Wrong-valid-dataclass evidence: PC-01A states that a valid `SummaryResult` returned by `list_events` becomes `REPORT_WORKER_SERVICE_CONTRACT`. The planned test `test_each_operation_rejects_every_other_valid_cd002_result_dataclass_before_serialization` exhaustively verifies cross-operation rejection.
- Wrong-page-row evidence: PC-01A states that `PageResult[TurnRow]` returned by `list_agents` becomes `REPORT_WORKER_SERVICE_CONTRACT`. Runtime validation requires `type(value) is PageResult` and each `type(item)` to equal the operation binding's exact row class. The planned test `test_each_page_operation_rejects_a_valid_page_result_with_the_wrong_row_class` verifies this rule.
- Schema evidence: The ledger names `ServiceResult[PreflightResult]`, `ServiceResult[SnapshotMetadata]`, `ServiceResult[SummaryResult]`, five specialized `PageResult` bindings, `ServiceResult[TimeSeriesResult]`, `ServiceResult[EventDetail]`, `ServiceResult[RefreshSnapshotResult]`, `ServiceResult[ExportResult]`, and `ServiceResult[CloseSnapshotResult]`. It defines each top-level wire schema and every nested `WarningRecord`, `ReportScope`, metric, activity, row, bucket, and snapshot schema.
- Assessment: The Worker can no longer serialize a structurally valid CD-002 result under the wrong operation. The remaining cross-module result boundary is exact, exhaustive, and directly testable.
- Authority: HLD-003 CR-03 and TB-03; CD-002 exact service signatures and result dataclasses; review-module-design request/response type-binding and cross-operation rules.

### Correction Disposition

#### CD004-01 — Partially corrected at intermediate digest; superseded by final closure

- Status: question
- Evidence type: summary
- Evidence source: corrected CD-004 Python Symbol Ledger, PC-01A, PC-04, PC-05, and Verification; accepted CD-002 Public Contracts
- Correction evidence: CD-004 removes the generic `invoke` and raised `ServiceFailure` model. It defines `OperationContext`, `ThreadCancellationToken`, `ProgressSink`, named CD-002 method dispatch, returned `ServiceResult[object]`, `ReportError` projection, cancellation mapping, invalid-result handling, and tests for named method and request-type dispatch.
- Remaining gap: The PC-01A dispatch ledger names each request type and named method but does not name that method's exact result binding, such as `ServiceResult[PreflightResult]`, `ServiceResult[SnapshotMetadata]`, `ServiceResult[PageResult[EventRow]]`, or `ServiceResult[CloseSnapshotResult]`. It also does not enumerate the accepted result schema for each operation. The generic `ServiceResult[object]` and generic dataclass serializer do not prove that an operation returned the correct CD-002 result type before serialization.
- Required correction: Add an operation-to-result ledger that names the exact `ServiceResult[T]` binding for all thirteen operations and the authoritative CD-002 result schema used for deterministic serialization. Require runtime rejection when a successful value has the wrong result dataclass for that exact operation. Add one parameterized test that supplies the wrong accepted dataclass to each dispatch route and expects `REPORT_WORKER_SERVICE_CONTRACT`.
- Authority: HLD-003 CR-03 and TB-03; CD-002 exact public service signatures; review-module-design request/response type-binding and cross-operation contract rules.
- Impact: A service double or faulty implementation can return a valid but wrong CD-002 dataclass. CD-004 would serialize it as a successful result for the wrong operation.
- Supersession: The Final Closure Re-review resolves this intermediate-digest gap at target digest `2ff743f625dadfa9cc9b5bb2f592235916c73b609a3ac33b76f03d69756431ac`.

#### CD004-02 — Resolved

- Status: pass
- Evidence type: summary
- Evidence source: corrected CD-004 Python Symbol Ledger, Rust Symbol Ledger, PC-03 through PC-06, and Verification
- Correction evidence: CD-004 now declares every Python envelope as an exact frozen slotted dataclass. It declares the Rust wire structs with `deny_unknown_fields`, required-null visitors, tagged `WorkerWireRecord`, literal validation, and unsigned 64-bit numeric bounds. `OperationObserver` is `Send + Sync + 'static`. `CancelledEnvelope` is wire-only, while `HostCancelledOutcome` alone owns `forced`.
- Assessment: Cross-language framing, field presence, thread-safety, and Worker-versus-host cancellation shapes are explicit and testable.

#### CD004-03 — Resolved

- Status: pass
- Evidence type: summary
- Evidence source: corrected CD-004 `TrustedWorkerRequest`, PC-01A, PC-09, and Rust Test Targets
- Correction evidence: `OutputGrant` is opaque, non-`Clone`, operation-bound, and consumed by `TrustedWorkerRequest::export`. The export constructor inserts the canonical target and replace decision. `path_free` applies exact recursive schemas and rejects path or unknown keys at every nesting level. The handshake receives roots only from canonical `PathAuthority.source_roots`.
- Assessment: Generic JSON cannot confer source or destination authority. The tests cover missing, reused, mismatched, nested, and symlink-escape cases.

#### CD004-04 — Resolved

- Status: pass
- Evidence type: summary
- Evidence source: corrected CD-004 Rust Symbol Ledger, PC-10 through PC-12, Rust State, PR-08 through PR-10, and Rust Test Targets
- Correction evidence: One `RecoveryCoordinator` command loop owns mutable generation state, admission, observer completion, deadlines, recovery, restart, and shutdown. `active_recovery` coalesces triggers. Shutdown has priority, includes `Starting -> Stopping`, cancels startup, prevents replacement, and coalesces repeated calls.
- Assessment: The design now defines one linearization point and explicit race outcomes. Tests cover simultaneous EOF/exit/grace events, restart coalescing, shutdown during handshake, and repeated shutdown.

#### CD004-05 — Resolved

- Status: pass
- Evidence type: summary
- Evidence source: corrected CD-004 PC-08, Internal Data And State, and Rust Test Targets
- Correction evidence: Every child standard-error byte is untrusted. The reader bounds lines, strictly decodes UTF-8, rejects unknown fields, validates an allowlisted schema, discards child timestamp and message, maps only accepted event/code pairs to fixed native text, emits one fixed rejection record, and enforces a sanitized-generation byte cap.
- Assessment: Raw loader, runtime, dependency, and operating-system stderr cannot enter native diagnostics. Tests cover traceback/path/environment content, invalid UTF-8, unknown fields, oversized unterminated input, and the generation cap.

#### CD004-06 — Resolved

- Status: pass
- Evidence type: summary
- Evidence source: corrected CD-004 `OperationSlot`, PC-03, PR-06, and Python Test Targets
- Correction evidence: `OperationSlot` now contains observed, emitted, pending, next-deadline, clock, and lock state. PC-03 defines an injected monotonic clock, immediate first emission, a 0.050-second minimum interval, latest-record coalescing, phase behavior, lock order, and no terminal bypass exception.
- Assessment: The contract deterministically limits each operation to at most 20 emissions in a half-open one-second interval. Tests cover zero and 50-millisecond boundaries, pending replacement, terminal behavior, and independent concurrent-operation intervals.

#### CD004-07 — Resolved at design level; implementation evidence remains a readiness blocker

- Status: pass
- Evidence type: summary
- Evidence source: corrected CD-004 Dependencies, PR-02, External Interfaces, Implementation Readiness, and Rust Test Targets
- Correction evidence: Unix uses `CommandExt::process_group(0)`, verifies `getpgid(pid) == pid`, signals only the stored negative group ID, handles `ESRCH`, and reaps the leader. Windows creates the process suspended, assigns it to a kill-on-close Job Object before `ResumeThread`, retains owned handles, terminates the Job Object, waits, and never invokes `taskkill`. Target-specific Cargo dependencies and failure cleanup are explicit.
- Assessment: The design contract is implementable. Native Linux, Apple Silicon macOS, and Windows x64 descendant/sentinel tests remain correctly listed as implementation-readiness evidence, not documentation-acceptance evidence.

#### CD004-08 — Resolved

- Status: pass
- Evidence type: exact quotation
- Evidence source: corrected CD-004 Implementation Readiness
- Evidence: `**BLOCKED.** The corrected design resolves the material CD-004 contract choices, but production implementation and acceptance still require changes outside the four owned files and platform evidence that does not exist.`
- Assessment: Readiness now names composition-root, crate-root, dependency, implementation, native-platform, and Markdown-verifier unblock conditions. It no longer authorizes unsupported implementation acceptance.

## Initial Findings And Corrections

This section records the first-pass findings against the earlier CD-004 content. The Correction Re-review disposition supersedes their original open status without deleting the audit trail.

### Response Adequacy

- **FINDING CD004-01 — The Python Worker contract contradicts the accepted Application Service contract.**
  - Severity: high
  - Checks: MD-08, MD-09, MD-11, MD-22
  - Target: Python Symbol Ledger, `ApplicationServicePort`; PC-04 and PC-05; PR-05; Documentation Acceptance; Implementation Readiness
  - Problem: CD-004 defines one generic `invoke(...) -> dict[str, JsonValue]` call and a raised `ServiceFailure`. CD-002 instead defines named service methods that return `ServiceResult[T]`, take `OperationContext`, and receive a `CancellationToken` object. CD-002 says expected failures do not raise. CD-004 therefore cannot bind the stated production factory without changing one accepted cross-module contract.
  - Correction: Define an adapter contract that exactly maps every supported operation to the accepted CD-002 method, request type, `OperationContext`, `CancellationToken`, `ProgressSink`, and `ServiceResult`. Alternatively, obtain an accepted parent/sibling design change before retaining `invoke` and `ServiceFailure`. Change Implementation Readiness to `BLOCKED` until the contracts agree.
  - Authority: HLD-003 CR-03 and TB-03 assign exact service invocation and validation to the Application Service; CD-002 Public Contracts defines its exact signatures and error model; review-module-design prohibits unsupported cross-owner contract transfer.
  - Impact: Implementers must guess which accepted contract to break. Cancellation and structured failures cannot be implemented or tested consistently.

- **FINDING CD004-02 — The envelope and observer symbol ledger is not literal enough to compile both sides.**
  - Severity: high
  - Checks: MD-05, MD-10, MD-11
  - Target: Python Symbol Ledger and Rust Symbol Ledger
  - Problem: Envelope entries say only “fields defined by PC-01” through “fields defined by PC-06”; they do not give literal Python field declarations or Rust field types and Serde attributes. `OperationObserver` lacks the `Send + Sync` bounds needed by reader-thread delivery. One Rust `CancelledEnvelope` also mixes a Worker wire record with the Supervisor-only `forced` outcome, although PC-06 says the dead Worker never writes `forced`.
  - Correction: Record complete declarations for every Python dataclass and Rust struct, including optionality, integer widths, Serde unknown-field policy, and wire tags. Require `OperationObserver: Send + Sync`. Separate the decoded Worker cancellation record from the Supervisor terminal outcome that adds `forced`.
  - Authority: HLD-003 delegates exact fields to CD-004; review-module-design requires literal complete types, signatures, and declared symbols without cross-phase ambiguity.
  - Impact: Independent Python and Rust implementations can produce incompatible JSON, fail Rust thread-safety checks, or accept a host-only field on the Worker wire.

- **FINDING CD004-03 — Path authorization cannot be derived from the generic request contract.**
  - Severity: high
  - Checks: MD-09, MD-12, MD-18
  - Target: PC-01, PC-09, `WorkerSupervisor::submit`, Trust And Identity Boundaries, Verification
  - Problem: PC-01 leaves `arguments` operation-defined, while `submit` claims to validate all native path-bearing fields. The design gives no operation-to-path-field ledger, typed host request, recursive validation rule, or proof that an `OutputGrant` is required and consumed by the exact export request. `authorize_source` is public but is not bound to request construction or submission.
  - Correction: Enumerate every path-bearing operation and exact field. Define the trusted request builder or typed submission API that replaces untrusted values with canonical grants. Make `submit` reject an export without the matching unconsumed `OutputGrant`, and specify how source authorizations are bound so nested arbitrary JSON cannot smuggle path authority.
  - Authority: ARC-05 and ARC-06 assign native path authority to Tauri; HLD-003 TB-02 and CR-02 require native-configured-root filtering; review-module-design requires selectors, validation ownership, and disclosure boundaries per exact operation.
  - Impact: A superficially valid implementation can forward unvalidated paths or cannot implement the stated validation deterministically.

- **FINDING CD004-04 — Recovery and shutdown do not define a single concurrency owner.**
  - Severity: high
  - Checks: MD-14, MD-15, MD-16, MD-17
  - Target: Rust State, PC-10, PC-11, PR-08 through PR-10, `WorkerSupervisor::restart`, `WorkerSupervisor::shutdown`
  - Problem: EOF readers, exit handling, grace timers, explicit restart, and shutdown can all initiate termination or replacement. Generation IDs prevent stale actions, but the design does not define which actor wins, which lock or compare-and-set linearizes recovery, whether concurrent restart calls coalesce, or how shutdown behaves while `Starting`. The state diagram has no `Starting -> Stopping` transition even though application shutdown can occur during handshake.
  - Correction: Define one recovery coordinator and exact transition/lock rules. Specify idempotent behavior for repeated restart and shutdown, timer cancellation, observer completion, and shutdown during `Starting`. Add race tests for simultaneous EOF/exit/timer, explicit restart during recovery, and shutdown during handshake.
  - Authority: FR-001 Workflow 4 requires deterministic cancel and recovery; HLD-003 CR-02 assigns lifecycle ownership to the Supervisor; review-module-design requires state transitions, concurrency, failure timing, and verification.
  - Impact: Races can double-complete observers, spawn multiple replacements, or leave a child process after shutdown.

### Identity And Security

- **FINDING CD004-05 — The diagnostic contract lacks a safe ingestion rule for malformed or non-JSON stderr.**
  - Severity: medium
  - Checks: MD-18, MD-19
  - Target: PC-08, External Interfaces / Standard Error, Error Handling
  - Problem: The Worker promises JSON diagnostics, but a Python runtime, loader, dependency, or operating-system failure can write arbitrary stderr before Worker validation. The Supervisor “forwards records” without defining whether it parses, rejects, replaces, or safely summarizes malformed bytes. A byte cap alone does not meet the no-path, no-environment, and no-traceback disclosure rule.
  - Correction: Treat child stderr as untrusted. Define bounded incremental decoding, malformed-line handling, an allowlisted output schema, field and character limits, and a fixed replacement diagnostic. Never forward raw child bytes. Add tests with traceback, path, environment, invalid UTF-8, and an oversized unterminated line.
  - Authority: FR-001 privacy and diagnostic rules; ARC-15; HLD-003 TB-02; verify-documentation-page source and disclosure checks.
  - Impact: Startup and crash diagnostics can disclose paths, arguments, environment data, or transcript-adjacent content to logs or the webview.

### Other Contract Or Evidence

- **FINDING CD004-06 — The progress rate-limit state and boundary algorithm are missing.**
  - Severity: medium
  - Checks: MD-13, MD-14, MD-21
  - Target: `OperationSlot`, PC-03, PR-06, Python tests
  - Problem: PC-03 requires duplicate suppression and at most 20 progress records per second per operation, with a final-progress exception. `OperationSlot` has no last record, total, message, timestamp, or clock state. The document does not define the time window, clock, behavior at a phase change, or whether the final exception may exceed the stated maximum.
  - Correction: Add the exact per-operation progress state and injected monotonic clock. Define one deterministic window/token algorithm, phase-transition behavior, and whether “final progress” is inside or outside the numeric limit. Add boundary tests at the exact window edge and across concurrent operations.
  - Authority: HLD-003 OP-31 delegates bounded ordered progress to CD-004; review-module-design requires complete internal state, algorithms, configuration, and test seams.
  - Impact: Implementations will disagree on observable progress volume and tests will be timing-sensitive.

- **FINDING CD004-07 — Unix process-group creation and native platform verification remain incomplete.**
  - Severity: medium
  - Checks: MD-07, MD-15, MD-21, VP-04
  - Target: Dependencies, External Interfaces / Process Interface, `force_terminate_process_tree`, Rust tests
  - Problem: The design requires a new Unix process group but does not name the exact spawn hook or dependency that creates it. Current Tauri evidence recursively calls `pgrep` and `kill`, which does not prove the planned process-group contract. The named native tests are planned, and Windows execution evidence is not present.
  - Correction: Specify the exact Unix creation and signalling API and the Windows tree/job ownership mechanism, including required target-specific imports or dependencies. Keep implementation readiness blocked until Linux, macOS, and native Windows tests prove descendant termination and no unrelated-process termination.
  - Authority: FR-001 Workflow 4; ARC-05 and ARC-14; HLD-003 CR-02; current `tools/report/desktop/src-tauri/src/lib.rs` compatibility evidence.
  - Impact: Forced cancellation can orphan descendants or terminate processes outside the owned tree.

- **FINDING CD004-08 — `READY` overstates the integration and verification evidence.**
  - Severity: high
  - Checks: MD-22, MD-23, VP-04
  - Target: Implementation Readiness and Verification
  - Problem: The source and tests do not yet exist; the package CLI and Rust crate root require out-of-scope integration edits; the CD-002 contract conflicts with CD-004; path binding and lifecycle races remain undefined; and native Windows evidence is absent. These are material implementation decisions, not only integration order.
  - Correction: Begin Implementation Readiness with `BLOCKED`. Name the CD-002 contract reconciliation, exact envelope declarations, path-binding API, recovery serialization, platform process ownership, and native test evidence as unblock conditions. Preserve Documentation Acceptance separately if the corrected document records these gaps accurately.
  - Authority: review-module-design requires `BLOCKED` when a required contract is open or a high-impact blocking question remains.
  - Impact: A `READY` handoff would authorize incompatible source work and defer safety-critical decisions into implementation.

## Completed Review Checklist

The statuses in this section record the initial review. The Correction Re-review section is the current assessment for target digest `e17a18fc6289405c6095adb05c4372ab88b9400f74f4ea5a213e6b0e11621817`.

### Structural And Workflow Checks

#### MD-01

- Status: pass
- Question: Do the ordered level-two headings exactly match the module design template, including leading acceptance and readiness decisions?
- Evidence type: assessment
- Evidence source: CD-004 and `module-design-template.md`
- Evidence: Both contain the same 27 level-two headings in the same order. `ACCEPTED` and `READY` are the first authored decisions in their respective sections.
- Assessment: The mandatory pre-semantic structural gate passes.

#### MD-02

- Status: pass
- Question: Does the review identify the target, authorities, mode, scope, template, and both checklist sets before assessment?
- Evidence type: summary
- Evidence source: this checklist, Review Trace
- Evidence: `- Design mode: PLANNED_DEVELOPMENT`
- Assessment: The review trace records the required inputs and methods.

#### MD-03

- Status: question
- Question: Does the completed checklist use the default artifact-adjacent filename required by review-module-design?
- Evidence type: summary
- Evidence source: task assignment and review-module-design
- Evidence: The task explicitly authorizes only `docs/reviews/RVW-014-cd-004-agent-report-worker-protocol-checklist.md`, while the skill default places a differently named checklist beside the target.
- Assessment: The explicit task output path governs. The requested centralized review path conforms to the project taxonomy.
- Correction: None unless the task owner changes the output contract.
- Authority: Task assignment and `docs/project-taxonomy.md`.
- Impact: No semantic impact; this records the deliberate naming/path exception.

### Source And Requirements Coverage

#### MD-04

- Status: pass
- Question: Does Requirements Coverage trace the target assignment and parent requirements, including progress, success, error, cancellation, supervision, atomicity, privacy, startup validation, and concurrency?
- Evidence type: summary
- Evidence source: CD-004 Requirements Coverage; FR-001; ARC-001; HLD-003
- Evidence: CD-004 maps the assignment plus OP-31 through OP-34, CR-02, CR-03, TB-02, TB-03, and applicable architecture constraints to contracts and tests.
- Assessment: The requirement inventory is broad and preserves the main scope-bearing qualifiers.

#### MD-05

- Status: fail
- Question: Are unsupported specifics labeled as propositions and are all exact type claims complete enough to review?
- Evidence type: summary
- Evidence source: CD-004 Python and Rust Symbol Ledgers
- Evidence: Constants and many decisions are justified, but envelope shapes defer their exact declarations to later prose and the observer and cancellation outcome types omit necessary distinctions.
- Assessment: The proposition ledger is useful, but it does not cure incomplete compile-time contracts.
- Correction: Apply CD004-02.
- Authority: review-module-design Artifact-Specific Questions.
- Impact: Cross-language implementations can diverge.

### Runtime Placement, Responsibilities, And Dependencies

#### MD-06

- Status: pass
- Question: Are runtime paths, entry points, owned files, namespaces, callers, and coherent responsibilities identified?
- Evidence type: exact quotation
- Evidence source: CD-004 Runtime Path
- Evidence: `The Python folder entry point is module agent_report.report_worker. Its executable entry point is agent_report.report_worker:main.`
- Assessment: The file trees and module names are literal, and responsibility remains focused on the process boundary.

#### MD-07

- Status: question
- Question: Are all dependencies and platform mechanisms sufficient for the stated runtime path?
- Evidence type: summary
- Evidence source: CD-004 Dependencies and External Interfaces; current Cargo configuration and Tauri source
- Evidence: Python and Serde dependencies are identified. Unix process-group construction and signalling are not bound to an exact API, and current source uses recursive process discovery instead.
- Assessment: Most dependencies are clear, but forced-termination implementation remains unresolved.
- Correction: Apply CD004-07.
- Authority: review-module-design Dependencies and External Interfaces checks.
- Impact: Native process ownership may not match the design.

### Public Contracts And Cross-Module Compatibility

#### MD-08

- Status: fail
- Question: Does the Worker-to-Application-Service contract preserve the accepted exact service API and error model?
- Evidence type: summary
- Evidence source: CD-004 Python Symbol Ledger
- Evidence: CD-004 defines a generic `ApplicationServicePort.invoke(...) -> dict[str, JsonValue]` protocol method.
- Assessment: This contradicts CD-002 named methods returning `ServiceResult[T]` with `OperationContext` and `CancellationToken`.
- Correction: Apply CD004-01.
- Authority: HLD-003 CR-03 and CD-002 Public Contracts.
- Impact: The stated production factory has no compatible implementation.

#### MD-09

- Status: fail
- Question: Does the operation ledger bind every operation to exact request and response types, validation owners, state owners, and failure phases?
- Evidence type: summary
- Evidence source: CD-004 Operation-Contract Ledger, PC-01, and CD-002 Public Contracts
- Evidence: The ledger covers six transport/supervisor methods but compresses every service operation into an open-ended operation string and arguments object.
- Assessment: Transport ownership is strong, but service-operation dispatch, typed conversion, path fields, and error conversion are not reconciled.
- Correction: Apply CD004-01 and CD004-03.
- Authority: review-module-design operation inventory reconciliation.
- Impact: Exact service and trust contracts are lost at the adapter boundary.

#### MD-10

- Status: fail
- Question: Are Python and Rust request, progress, result, error, cancel, and cancellation-outcome envelopes exact and mutually compatible?
- Evidence type: summary
- Evidence source: CD-004 Symbol Ledgers and PC-01 through PC-07
- Evidence: JSON examples and stable field tables are present, but declared types and decoding attributes are absent, and Rust conflates wire cancellation with the host-only `forced` outcome.
- Assessment: The wire prose is substantial but is not a complete cross-language declaration.
- Correction: Apply CD004-02.
- Authority: HLD-003 Worker operation envelope anchor and review-module-design literal-symbol rule.
- Impact: Serialization and validation can differ across runtimes.

#### MD-11

- Status: fail
- Question: Are every method signature, trait bound, result variant, and required field literal and complete?
- Evidence type: summary
- Evidence source: CD-004 Runtime Path
- Evidence: Major signatures are listed, but dataclass fields, Rust field types, Serde behavior, adapter dispatch, and thread-safety bounds are incomplete.
- Assessment: The implementation frame does not yet prevent compile-time and schema guesswork.
- Correction: Apply CD004-01 and CD004-02.
- Authority: review-module-design Artifact-Specific Questions.
- Impact: Implementers must make contract-bearing decisions in source.

### Path, Identity, Privacy, And Diagnostics

#### MD-12

- Status: fail
- Question: Does native path authority bind every path-bearing request field to a canonical source authorization or one-time output grant?
- Evidence type: summary
- Evidence source: CD-004 PC-01, PC-09, Public Contracts, and Trust And Identity Boundaries
- Evidence: Canonicalization and symlink rejection are described, but no exact operation-to-field binding or trusted request-construction path is defined.
- Assessment: The intended boundary is correct, but enforcement cannot be implemented from the generic request shape.
- Correction: Apply CD004-03.
- Authority: ARC-05, ARC-06, HLD-003 TB-02.
- Impact: Path authority can be bypassed or inconsistently applied.

#### MD-13

- Status: pass
- Question: Does standard output remain protocol-only and bounded?
- Evidence type: exact quotation
- Evidence source: CD-004 INV-01
- Evidence: `Standard output contains only valid PC-03 through PC-06 JSONL records.`
- Assessment: PC-07 additionally and explicitly permits the startup result while Starting. Framing, UTF-8, line-feed, size, BOM, partial-EOF, and contamination failures are defined and tested.

#### MD-14

- Status: fail
- Question: Is progress bounded, ordered, monotonic, concurrency-safe, and supported by complete internal state?
- Evidence type: summary
- Evidence source: CD-004 PC-03, `OperationSlot`, PR-06, and Verification
- Evidence: PC-03 states the observable rules, but `OperationSlot` and the algorithm omit the clock and record state needed for duplicate suppression and 20-per-second enforcement.
- Assessment: Output locking prevents byte interleaving, but the numeric rate contract is not implementable deterministically.
- Correction: Apply CD004-06.
- Authority: HLD-003 OP-31 and review-module-design processing-rule checks.
- Impact: Progress behavior and tests can be nondeterministic.

#### MD-15

- Status: fail
- Question: Are cancellation grace, forced termination, restart, and shutdown states fully defined across concurrent triggers?
- Evidence type: summary
- Evidence source: CD-004 PC-10, PC-11, Rust State, PR-08 through PR-10
- Evidence: Generation isolation, no replay, peer outcomes, and grace behavior are defined. Recovery leadership, concurrent trigger coalescing, and shutdown during Starting are not.
- Assessment: The happy paths are clear, but lifecycle races remain contract gaps.
- Correction: Apply CD004-04 and CD004-07.
- Authority: FR-001 Workflow 4 and HLD-003 CR-02.
- Impact: Multiple recovery actors can violate one-terminal and no-orphan invariants.

#### MD-16

- Status: pass
- Question: Does per-operation cancellation remain isolated until process-wide escalation is necessary?
- Evidence type: exact quotation
- Evidence source: CD-004 INV-06
- Evidence: `Cancellation selects one operation until forced process-wide recovery is necessary.`
- Assessment: PC-10 defines distinct forced-target and peer terminal outcomes and prohibits replay.

#### MD-17

- Status: fail
- Question: Does Supervisor concurrency define one linearization point for operation admission, observer completion, recovery, restart, and shutdown?
- Evidence type: assessment
- Evidence source: CD-004 Rust State, PC-12, and PR-08 through PR-10
- Evidence: A mutex-protected generation is named, but lock scope and winning transitions across all initiators are not defined.
- Assessment: Generation IDs solve stale-event isolation, not simultaneous-current-generation ownership.
- Correction: Apply CD004-04.
- Authority: review-module-design concurrency and state-transition checks.
- Impact: Double completion and duplicate replacement remain possible.

#### MD-18

- Status: fail
- Question: Are privacy, disclosure, and logging rules enforced for both valid diagnostics and uncontrolled child stderr?
- Evidence type: summary
- Evidence source: CD-004 PC-08, INV-10, External Interfaces, and Error Handling
- Evidence: Valid Worker diagnostics have a strict allowlist and byte caps. The Supervisor behavior for arbitrary pre-startup or crash stderr is not specified.
- Assessment: The disclosure policy is strong but incomplete at the untrusted process boundary.
- Correction: Apply CD004-05.
- Authority: FR-001 Privacy, Cost, And Provenance Rules; ARC-15; HLD-003 TB-02.
- Impact: Raw paths, environment data, or tracebacks can enter native logs.

### Effects, Atomicity, Errors, And Verification

#### MD-19

- Status: pass
- Question: Does one phase ledger distinguish submission, service completion, cancellation, deadline, forced termination, restart, and shutdown?
- Evidence type: summary
- Evidence source: CD-004 External And Asynchronous Effect Phases and Processing Diagram
- Evidence: EP-01 through EP-07 name initiator, submission owner, executor, committed state, visibility, failure, retry, and completion evidence.
- Assessment: The effect ledger and diagrams preserve atomic publication and no-replay intent. Findings MD-08 and MD-17 concern missing boundary details, not phase omission.

#### MD-20

- Status: pass
- Question: Does the design preserve atomic state and artifact publication on success, error, cancellation, forced termination, and restart?
- Evidence type: exact quotation
- Evidence source: CD-004 INV-09
- Evidence: `A result is not visible before the Application Service completes atomic publication. Failure and cancellation cannot expose a partial revision or export.`
- Assessment: Ownership remains with CD-002, CD-003, and CD-006, and CD-004 emits no premature success.

#### MD-21

- Status: question
- Question: Do Error Handling and Verification cover framing, stdout purity, progress, concurrency, cancellation races, forced process-tree termination, restart, paths, privacy, and atomicity?
- Evidence type: summary
- Evidence source: CD-004 Error Handling and Verification
- Evidence: The planned test names cover most stated outcomes. Missing cases include recovery-trigger races, shutdown during handshake, exact progress-window edges, malformed untrusted stderr, and typed service-contract mapping.
- Assessment: Test planning is extensive but does not close the findings in this review.
- Correction: Add the cases required by CD004-01, CD004-04, CD004-05, and CD004-06.
- Authority: review-module-design Verification questions.
- Impact: Critical boundary defects can survive the named test suite.

#### MD-22

- Status: fail
- Question: Is Documentation Acceptance supported independently from implementation readiness?
- Evidence type: summary
- Evidence source: CD-004 Documentation Acceptance and this checklist
- Evidence: The section structure separates the decisions, but Documentation Acceptance claims exact service signatures and that every internal choice is justified despite the cross-module mismatch and missing path/lifecycle contracts.
- Assessment: The current `ACCEPTED` rationale overstates completeness. Documentation can become acceptable after it records and resolves or explicitly blocks on these gaps.
- Correction: Correct the findings, then reassess acceptance separately from readiness.
- Authority: review-module-design Documentation Acceptance rule.
- Impact: Reviewers may treat incomplete contracts as accepted authority.

#### MD-23

- Status: fail
- Question: Is implementation readiness truthful for all four owned files and required integration surfaces?
- Evidence type: exact quotation
- Evidence source: CD-004 Implementation Readiness
- Evidence: `**READY.** The four owned files can be implemented from this design without a material CD-004 decision.`
- Assessment: Findings CD004-01 through CD004-07 include material contract, state, security, and platform decisions.
- Correction: Apply CD004-08.
- Authority: review-module-design readiness rule.
- Impact: Implementation would proceed with incompatible or unsafe assumptions.

### Shared Structured-Artifact And Sentence Checks

#### SA-01

- Status: pass
- Question: Does the design preserve architecture and HLD boundaries rather than owning business semantics, cache internals, export format, or UI rendering?
- Evidence type: exact quotation
- Evidence source: CD-004 Current Understanding
- Evidence: `The module does not own report calculations, snapshot business rules, export content, webview state, or user-interface rendering.`
- Assessment: The component scope is coherent. The `invoke` mismatch is a boundary-contract defect, not broad scope drift.

#### SA-02

- Status: pass
- Question: Are requirements distinguished from module-local solution propositions with basis, necessity, and owner?
- Evidence type: summary
- Evidence source: CD-004 Requirements Coverage and Justified Module Propositions
- Evidence: WP-01 through WP-09 record decisions, bases, necessity, and CD-004 ownership.
- Assessment: The decision model is inspectable. Unsupported or incomplete propositions are separately failed above.

#### SA-03

- Status: pass
- Question: Does the document avoid unsupported exact quotations, hidden reasoning requests, vague buzzwords, TODO markers, and stale comparative framing?
- Evidence type: assessment
- Evidence source: CD-004 full page
- Evidence: No hidden-reasoning request, TODO marker, or material buzzword pattern was identified. Claims are presented as source trace, proposition, contract, or explicit out-of-scope decision.
- Assessment: The prose is concrete and reviewable.

#### SA-04

- Status: question
- Question: Does every prose sentence pass Needed, Clear, and Definite reference checks?
- Evidence type: assessment
- Evidence source: CD-004 full page; verify-documentation-page Sentence Review
- Evidence: No material unnecessary sentence or unresolved definite-reference failure was identified. Several long contract sentences and table cells remain dense, but their technical content is needed and their referents are established.
- Assessment: STE clarity is generally good. The substantive ambiguities are recorded as contract findings rather than style findings. This is not formal ASD-STE100 verification.
- Correction: When correcting the contracts, split sentences that combine validation, ownership, timing, and recovery into separate statements without changing normative force.
- Authority: ste-technical-writing and verify-documentation-page.
- Impact: Dense corrections could otherwise conceal changes in ownership or timing.

#### SA-05

- Status: n/a
- Question: Do Markdown/YAML companion mapping checks apply?
- Evidence type: not applicable
- Evidence source: CD-004 and task assignment
- Evidence: CD-004 has no YAML companion in the review scope.
- Assessment: Markdown/YAML mapping does not apply.

## Verifier Assessment

### VP-01 Format And Shared Contract

- Status: pass
- Question: Does the page use the selected module-design structure and required opening shared sections?
- Evidence type: summary
- Evidence source: CD-004 and `module-design-template.md`
- Evidence: All template sections are present in order. The opening sections contain source-backed content or explicit not-yet-identified statements.
- Assessment: Format verification passes.

### VP-02 Source Authority

- Status: fail
- Question: Are material claims supported by the strongest applicable source and reconciled when sources disagree?
- Evidence type: summary
- Evidence source: CD-004, CD-002, FR-001, ARC-001, and HLD-003
- Evidence: Parent behavior and boundaries are well traced, but the Worker service API contradicts the accepted CD-002 exact contract and is still presented as ready.
- Assessment: Source-authority verification fails for the service boundary and readiness conclusion.
- Correction: Apply CD004-01 and CD004-08.
- Authority: verify-documentation-page Source And Link Checks.
- Impact: The module can direct incompatible implementation.

### VP-03 Diagrams

- Status: pass
- Question: Are editable diagrams present for parent topology, state transitions, ordered asynchronous exchanges, branches, recovery, and cancellation?
- Evidence type: summary
- Evidence source: CD-004 Parent Context, Internal Data And State, and Processing Diagram
- Evidence: The page contains Mermaid topology, two state diagrams, a sequence diagram, and a validation flowchart.
- Assessment: Diagram selection and coverage satisfy the module-design triggers. Finding CD004-04 requires lifecycle content corrections in both prose and diagrams.

### VP-04 Links And Current Evidence

- Status: question
- Question: Did automated Markdown link verification complete, and does current runtime evidence prove the planned native behavior?
- Evidence type: exact quotation
- Evidence source: retained `verify_markdown_links` tool response
- Evidence: `Path is outside configured workspace roots: /Users/martinbechard/dev/agent-runner`
- Assessment: The configured verifier rejected the repository root, so the skill prohibits a fallback link pass. Directly inspected linked authority files exist, but that is not a replacement verifier result. Current Tauri evidence proves only recursive child termination on supported hosts; it does not prove the planned process-group contract or native Windows behavior.
- Correction: Configure the repository as an allowed verifier workspace and rerun Markdown link verification. Run the planned native process-tree tests on Linux, macOS, and Windows after implementation.
- Authority: verify-documentation-page Source And Link Checks and the structured tool rejection.
- Impact: Anchor correctness and native cross-platform behavior remain unverified.

### VP-05 Steady-State Quality

- Status: pass
- Question: Is the page steady-state, focused, free of unresolved TODO markers, and appropriately structured rather than carrying qualifying sequences only in prose?
- Evidence type: assessment
- Evidence source: CD-004 full page
- Evidence: No TODO marker or historical-version framing was found. Ordered flows and branches have editable Mermaid diagrams. The module stays focused on Worker and Supervisor responsibilities.
- Assessment: Steady-state verification passes, subject to the contract corrections above.

## Review Conclusion

Documentation acceptance: **ACCEPTED** for target digest `2ff743f625dadfa9cc9b5bb2f592235916c73b609a3ac33b76f03d69756431ac`. All eight original RVW-014 findings are resolved. The final correction binds every operation to its exact `ServiceResult[T]`, result schema, nested schema, page-row type, and correlation rules and verifies wrong-valid-dataclass rejection.

Implementation readiness: **BLOCKED**, consistent with the corrected CD-004 decision. Production integration, implementation, platform dependencies, native Linux/macOS/Windows process-tree evidence, and Markdown link verification remain explicit unblock conditions.

Verifier result: **PASS WITH AN EXTERNAL VERIFICATION GAP**. The module-design structure, source authority, operation contracts, diagrams, steady-state prose, and every RVW-014 correction pass. No documentation correction remains. Automated Markdown link verification did not execute because the configured verifier rejected the repository root as outside its workspace roots; the corrected design therefore properly retains rerunning that check as an implementation-readiness unblock condition.
