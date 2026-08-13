// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Supervise the local report worker through a strict, cancellable JSONL process boundary.
// Design: docs/design/components/CD-004-agent-report-worker-protocol.md

//! Native process supervision and wire validation for the Agent Report worker.

use std::collections::{BTreeMap, HashMap, HashSet};
use std::ffi::OsString;
use std::fmt;
use std::fs;
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, SyncSender};
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

use chrono::{DateTime, FixedOffset};
use serde::{Deserialize, Deserializer, Serialize};
use serde_json::{Map, Value, json};

/// The only protocol version accepted by this Supervisor.
pub const WORKER_PROTOCOL_VERSION: u32 = 1;

/// The hard maximum for one Worker JSONL record, including its line feed.
pub const MAX_WORKER_RECORD_BYTES: usize = 1_048_576;

/// The largest matrix result accepted from the Application Service.
pub const MAX_HEATMAP_CELLS: usize = 2_000;

/// The largest selected-cell evidence ledger accepted from the Application Service.
pub const MAX_HEATMAP_EVIDENCE_ITEMS: usize = 100;

const MAX_HEATMAP_LABEL_ESCAPED_BYTES: usize = 256;
const MAX_HEATMAP_FORMATTED_VALUE_ESCAPED_BYTES: usize = 64;
const MAX_HEATMAP_SUPPORTING_TEXT_ESCAPED_BYTES: usize = 80;
const MAX_HEATMAP_PREVIEW_ESCAPED_BYTES: usize = 4_096;
const MAX_HEATMAP_PROVENANCE_ITEMS: usize = 32;
const MAX_HEATMAP_PROVENANCE_ESCAPED_BYTES: usize = 256;
const MAX_HEATMAP_ROWS: usize = 200;

const WALL_TIME_ROW_KEYS: [&str; 8] = [
    "model_inference",
    "tool_execution",
    "test_process",
    "agent_wait",
    "user_pause",
    "watchdog",
    "approval_infrastructure",
    "unattributed",
];

const TOKEN_ROW_KEYS: [&str; 8] = [
    "uncached_input_tokens",
    "cached_input_tokens",
    "reasoning_tokens",
    "output_tokens",
    "tool_calls",
    "context_average",
    "context_maximum",
    "cost",
];

const MIN_RECORD_BYTES: usize = 4_096;
const MAX_MESSAGE_CHARS: usize = 512;
const STDERR_LINE_BYTES: usize = 4_096;
const HANDSHAKE_OPERATION_ID: &str = "op_000000000000000000000000";
const COMMAND_CAPACITY: usize = 128;

/// Non-path Application Service values inserted into the trusted startup handshake.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ServiceConfiguration {
    pub parser_version: String,
    pub pricing_version: String,
    pub pricing_digest: String,
    pub formatter_version: String,
    pub formatter_digest: String,
    pub default_page_size: u16,
    pub max_page_size: u16,
    pub max_heatmap_cells: u32,
}

/// Canonical roots that the native host authorizes the Worker to read.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PathAuthority {
    pub source_roots: Vec<PathBuf>,
}

/// Static limits and trusted startup values for one Supervisor.
#[derive(Clone)]
pub struct WorkerSupervisorConfig {
    pub max_in_flight: usize,
    pub cancellation_grace: Duration,
    pub startup_timeout: Duration,
    pub max_record_bytes: usize,
    pub max_stderr_bytes: usize,
    pub expected_package_version: String,
    pub service_configuration: ServiceConfiguration,
    pub path_authority: PathAuthority,
    pub diagnostic_sink: Option<Arc<dyn Fn(SanitizedDiagnostic) + Send + Sync>>,
}

impl fmt::Debug for WorkerSupervisorConfig {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("WorkerSupervisorConfig")
            .field("max_in_flight", &self.max_in_flight)
            .field("cancellation_grace", &self.cancellation_grace)
            .field("startup_timeout", &self.startup_timeout)
            .field("max_record_bytes", &self.max_record_bytes)
            .field("max_stderr_bytes", &self.max_stderr_bytes)
            .field("expected_package_version", &self.expected_package_version)
            .field("service_configuration", &self.service_configuration)
            .field("path_authority", &self.path_authority)
            .field(
                "diagnostic_sink",
                &self.diagnostic_sink.as_ref().map(|_| "configured"),
            )
            .finish()
    }
}

/// The native-host-selected executable, arguments, and environment for each generation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WorkerLaunchSpec {
    pub executable: PathBuf,
    pub arguments: Vec<OsString>,
    pub environment: BTreeMap<OsString, OsString>,
}

/// A verified Unix process group owned by one Supervisor generation.
#[cfg(unix)]
#[derive(Debug)]
pub struct ProcessTreeHandle {
    process_id: u32,
    process_group_id: i32,
}

/// An owned Windows process and kill-on-close Job Object.
#[cfg(windows)]
#[derive(Debug)]
pub struct ProcessTreeHandle {
    process_id: u32,
    job: std::os::windows::io::OwnedHandle,
    process: std::os::windows::io::OwnedHandle,
}

/// Canonical native-dialog authority that can be consumed by one export request.
#[derive(Debug)]
pub struct OutputGrant {
    operation_id: String,
    target: PathBuf,
    replace: bool,
}

impl OutputGrant {
    #[cfg(test)]
    #[doc(hidden)]
    pub fn for_test(operation_id: &str, target: PathBuf, replace: bool) -> Self {
        Self {
            operation_id: operation_id.to_owned(),
            target,
            replace,
        }
    }
}

/// The surface vocabulary accepted by the Application Service export request.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum AutomationSurfaceWire {
    Tauri,
    Cli,
    Mcp,
}

/// The explicit export modes accepted on the Worker wire.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ExportModeWire {
    Summary,
    Directory,
}

/// The two mutually exclusive snapshot Heatmap request and result variants.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum HeatmapQueryKindWire {
    Matrix,
    CellEvidence,
}

/// One trusted request sent from the Supervisor to the Worker.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RequestEnvelope {
    pub protocol_version: u32,
    pub operation_id: String,
    pub operation: String,
    #[serde(deserialize_with = "deserialize_required_nullable_string")]
    pub snapshot_id: Option<String>,
    pub arguments: Map<String, Value>,
}

/// The only Worker control request that bypasses ordinary operation capacity.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CancelEnvelope {
    pub protocol_version: u32,
    pub operation_id: String,
    #[serde(rename = "type")]
    pub record_type: CancelRecordType,
}

/// The exact literal used by a cancellation request.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CancelRecordType {
    #[serde(rename = "cancel")]
    Cancel,
}

/// A privacy-bounded error projected from the Application Service.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StructuredError {
    pub code: String,
    pub message: String,
    #[serde(deserialize_with = "deserialize_required_nullable_string")]
    pub operation_id: Option<String>,
    pub recoverable: bool,
    #[serde(deserialize_with = "deserialize_required_nullable_string")]
    pub current_source_revision: Option<String>,
    pub preflight_required: bool,
    pub restart_from_first_page: bool,
}

/// One bounded progress observation from an accepted Worker operation.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProgressEnvelope {
    pub protocol_version: u32,
    pub operation_id: String,
    pub operation: String,
    #[serde(deserialize_with = "deserialize_required_nullable_string")]
    pub snapshot_id: Option<String>,
    pub phase: String,
    pub completed: u64,
    #[serde(deserialize_with = "deserialize_required_nullable_u64")]
    pub total: Option<u64>,
    pub message: String,
}

/// One successful terminal Worker record.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResultEnvelope {
    pub protocol_version: u32,
    pub operation_id: String,
    pub operation: String,
    #[serde(deserialize_with = "deserialize_required_nullable_string")]
    pub snapshot_id: Option<String>,
    pub ok: bool,
    pub result: Map<String, Value>,
}

/// One failed terminal Worker record.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ErrorEnvelope {
    pub protocol_version: u32,
    pub operation_id: String,
    pub operation: String,
    #[serde(deserialize_with = "deserialize_required_nullable_string")]
    pub snapshot_id: Option<String>,
    pub ok: bool,
    pub error: StructuredError,
}

/// One cooperative terminal cancellation decoded from Worker stdout.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CancelledEnvelope {
    pub protocol_version: u32,
    pub operation_id: String,
    pub operation: String,
    #[serde(deserialize_with = "deserialize_required_nullable_string")]
    pub snapshot_id: Option<String>,
    pub ok: bool,
    pub error: StructuredError,
}

/// Every record that may legally appear on Worker stdout.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum WorkerWireRecord {
    Progress(ProgressEnvelope),
    Result(ResultEnvelope),
    Error(ErrorEnvelope),
    Cancelled(CancelledEnvelope),
}

/// A host cancellation outcome, including whether the Supervisor forced termination.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HostCancelledOutcome {
    pub operation_id: String,
    pub operation: String,
    pub snapshot_id: Option<String>,
    pub error: StructuredError,
    pub forced: bool,
}

/// Exactly one terminal event delivered to an operation observer.
#[derive(Debug, Clone, PartialEq)]
pub enum HostTerminalOutcome {
    Result(ResultEnvelope),
    Error(ErrorEnvelope),
    Cancelled(HostCancelledOutcome),
}

/// A thread-safe adapter seam for Tauri progress and terminal channels.
pub trait OperationObserver: Send + Sync + 'static {
    fn on_progress(&self, value: ProgressEnvelope);
    fn on_terminal(&self, value: HostTerminalOutcome);
}

/// Process states owned and serialized by the Recovery Coordinator.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SupervisorState {
    Stopped,
    Starting,
    Ready,
    Stopping,
    Failed,
}

/// The reason a process generation is intentionally replaced.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RestartReason {
    ForcedCancellation,
    EndOfFile,
    ProtocolFailure,
    ProcessExit,
    Explicit,
}

/// A path authority class reported without disclosing the rejected path.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PathKind {
    WorkerExecutable,
    Source,
    StagingRoot,
    OutputTarget,
}

/// Native validation, protocol, process, and lifecycle failures.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SupervisorError {
    InvalidConfiguration {
        field: &'static str,
        message: String,
    },
    InvalidState {
        expected: SupervisorState,
        actual: SupervisorState,
    },
    Spawn {
        message: String,
    },
    ProcessOwnership {
        platform: &'static str,
        message: String,
    },
    StartupTimeout,
    VersionMismatch {
        expected_protocol: u32,
        actual_protocol: u32,
        expected_package: String,
        actual_package: String,
    },
    Io {
        phase: &'static str,
        message: String,
    },
    Protocol {
        code: &'static str,
        message: String,
    },
    DuplicateOperation {
        operation_id: String,
    },
    Busy {
        maximum: usize,
    },
    OperationNotActive {
        operation_id: String,
    },
    PathNotAuthorized {
        kind: PathKind,
    },
    OutputGrantMismatch {
        operation_id: String,
    },
    ProcessTermination {
        process_id: u32,
        message: String,
    },
    RestartFailed {
        message: String,
    },
    CoordinatorClosed,
    StderrLimitExceeded,
}

impl fmt::Display for SupervisorError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidConfiguration { field, message } => {
                write!(formatter, "invalid {field}: {message}")
            }
            Self::InvalidState { expected, actual } => {
                write!(formatter, "expected {expected:?}, found {actual:?}")
            }
            Self::Spawn { message } => write!(formatter, "worker spawn failed: {message}"),
            Self::ProcessOwnership { platform, message } => {
                write!(formatter, "{platform} process ownership failed: {message}")
            }
            Self::StartupTimeout => formatter.write_str("worker startup timed out"),
            Self::VersionMismatch { .. } => formatter.write_str("worker version mismatch"),
            Self::Io { phase, message } => write!(formatter, "worker {phase} failed: {message}"),
            Self::Protocol { code, message } => write!(formatter, "{code}: {message}"),
            Self::DuplicateOperation { operation_id } => {
                write!(formatter, "duplicate operation {operation_id}")
            }
            Self::Busy { maximum } => write!(formatter, "worker capacity {maximum} is full"),
            Self::OperationNotActive { operation_id } => {
                write!(formatter, "operation {operation_id} is not active")
            }
            Self::PathNotAuthorized { kind } => {
                write!(formatter, "{kind:?} path is not authorized")
            }
            Self::OutputGrantMismatch { operation_id } => {
                write!(formatter, "output grant does not match {operation_id}")
            }
            Self::ProcessTermination {
                process_id,
                message,
            } => {
                write!(
                    formatter,
                    "process {process_id} termination failed: {message}"
                )
            }
            Self::RestartFailed { message } => {
                write!(formatter, "worker restart failed: {message}")
            }
            Self::CoordinatorClosed => formatter.write_str("worker coordinator is closed"),
            Self::StderrLimitExceeded => formatter.write_str("worker diagnostic limit was reached"),
        }
    }
}

impl std::error::Error for SupervisorError {}

fn deserialize_required_nullable_string<'de, D>(deserializer: D) -> Result<Option<String>, D::Error>
where
    D: Deserializer<'de>,
{
    Option::<String>::deserialize(deserializer)
}

fn deserialize_required_nullable_u64<'de, D>(deserializer: D) -> Result<Option<u64>, D::Error>
where
    D: Deserializer<'de>,
{
    Option::<u64>::deserialize(deserializer)
}

/// Decode and validate exactly one bounded Worker stdout record.
pub fn parse_worker_record(
    line: &[u8],
    max_record_bytes: usize,
) -> Result<WorkerWireRecord, SupervisorError> {
    if line.is_empty() || line.len() > max_record_bytes || line.last() != Some(&b'\n') {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid record framing",
        ));
    }
    let body = &line[..line.len() - 1];
    if body.starts_with(&[0xef, 0xbb, 0xbf]) || body.contains(&b'\n') || body.contains(&b'\r') {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid record framing",
        ));
    }
    let record: WorkerWireRecord = serde_json::from_slice(body)
        .map_err(|_| protocol_error("REPORT_WORKER_PROTOCOL", "invalid worker record"))?;
    validate_worker_record(&record)?;
    Ok(record)
}

fn validate_worker_record(record: &WorkerWireRecord) -> Result<(), SupervisorError> {
    match record {
        WorkerWireRecord::Progress(value) => {
            validate_common_record(
                value.protocol_version,
                &value.operation_id,
                &value.operation,
                value.snapshot_id.as_deref(),
            )?;
            validate_operation_name(&value.phase, "phase")?;
            validate_safe_message(&value.message)?;
            if value.total.is_some_and(|total| total < value.completed) {
                return Err(protocol_error(
                    "REPORT_WORKER_PROTOCOL",
                    "progress total is less than completed",
                ));
            }
        }
        WorkerWireRecord::Result(value) => {
            validate_common_record(
                value.protocol_version,
                &value.operation_id,
                &value.operation,
                value.snapshot_id.as_deref(),
            )?;
            if !value.ok {
                return Err(protocol_error(
                    "REPORT_WORKER_PROTOCOL",
                    "result ok must be true",
                ));
            }
        }
        WorkerWireRecord::Error(value) => {
            validate_common_record(
                value.protocol_version,
                &value.operation_id,
                &value.operation,
                value.snapshot_id.as_deref(),
            )?;
            if value.ok {
                return Err(protocol_error(
                    "REPORT_WORKER_PROTOCOL",
                    "error ok must be false",
                ));
            }
            validate_structured_error(&value.error, &value.operation_id)?;
        }
        WorkerWireRecord::Cancelled(value) => {
            validate_common_record(
                value.protocol_version,
                &value.operation_id,
                &value.operation,
                value.snapshot_id.as_deref(),
            )?;
            if value.ok || value.error.code != "REPORT_CANCELLED" {
                return Err(protocol_error(
                    "REPORT_WORKER_PROTOCOL",
                    "cancelled record has an invalid literal",
                ));
            }
            validate_structured_error(&value.error, &value.operation_id)?;
        }
    }
    Ok(())
}

fn validate_common_record(
    version: u32,
    operation_id: &str,
    operation: &str,
    snapshot_id: Option<&str>,
) -> Result<(), SupervisorError> {
    if version != WORKER_PROTOCOL_VERSION {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "protocol version mismatch",
        ));
    }
    validate_operation_id(operation_id)?;
    validate_operation_name(operation, "operation")?;
    validate_snapshot_id(snapshot_id)
}

fn validate_structured_error(
    error: &StructuredError,
    operation_id: &str,
) -> Result<(), SupervisorError> {
    if !valid_error_code(&error.code) || error.operation_id.as_deref() != Some(operation_id) {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid structured error correlation",
        ));
    }
    validate_safe_message(&error.message)?;
    if let Some(revision) = &error.current_source_revision {
        validate_visible_string(revision, 1, 256, "current source revision")?;
    }
    Ok(())
}

fn validate_operation_id(value: &str) -> Result<(), SupervisorError> {
    if value.len() == 27
        && value.starts_with("op_")
        && value[3..]
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        Ok(())
    } else {
        Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid operation id",
        ))
    }
}

fn validate_operation_name(value: &str, field: &'static str) -> Result<(), SupervisorError> {
    let mut bytes = value.bytes();
    let valid = value.len() <= 64
        && bytes.next().is_some_and(|byte| byte.is_ascii_lowercase())
        && bytes.all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_');
    if valid {
        Ok(())
    } else {
        Err(protocol_error("REPORT_WORKER_PROTOCOL", field))
    }
}

fn validate_snapshot_id(value: Option<&str>) -> Result<(), SupervisorError> {
    if let Some(value) = value {
        validate_visible_string(value, 1, 128, "snapshot id")?;
    }
    Ok(())
}

fn validate_visible_string(
    value: &str,
    minimum: usize,
    maximum: usize,
    field: &'static str,
) -> Result<(), SupervisorError> {
    let length = value.chars().count();
    if (minimum..=maximum).contains(&length)
        && value
            .chars()
            .all(|character| character.is_ascii_graphic() && !character.is_ascii_whitespace())
    {
        Ok(())
    } else {
        Err(protocol_error("REPORT_WORKER_PROTOCOL", field))
    }
}

fn validate_safe_message(value: &str) -> Result<(), SupervisorError> {
    if value.chars().count() <= MAX_MESSAGE_CHARS
        && value.chars().all(|character| !character.is_control())
    {
        Ok(())
    } else {
        Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid safe message",
        ))
    }
}

fn valid_error_code(value: &str) -> bool {
    let mut bytes = value.bytes();
    value.len() <= 64
        && bytes.next().is_some_and(|byte| byte.is_ascii_uppercase())
        && bytes.all(|byte| byte.is_ascii_uppercase() || byte.is_ascii_digit() || byte == b'_')
}

fn protocol_error(code: &'static str, message: &'static str) -> SupervisorError {
    SupervisorError::Protocol {
        code,
        message: message.to_owned(),
    }
}

/// The observable outcome of one progress-coalescer observation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ProgressDecision {
    Emit(ProgressEnvelope),
    Pending,
    Ignored,
}

/// A deterministic per-operation latest-value coalescer.
#[derive(Debug)]
pub struct ProgressCoalescer {
    interval: Duration,
    last_observed_phase: Option<String>,
    last_observed_completed: u64,
    last_observed: Option<ProgressEnvelope>,
    last_emitted: Option<ProgressEnvelope>,
    pending: Option<ProgressEnvelope>,
    next_progress_at: Option<Instant>,
    last_clock: Option<Instant>,
}

impl ProgressCoalescer {
    /// Create an independent coalescer with the given minimum emission interval.
    pub fn new(interval: Duration) -> Self {
        Self {
            interval,
            last_observed_phase: None,
            last_observed_completed: 0,
            last_observed: None,
            last_emitted: None,
            pending: None,
            next_progress_at: None,
            last_clock: None,
        }
    }

    /// Validate and observe one progress value, retaining only the latest pending value.
    pub fn observe(
        &mut self,
        value: ProgressEnvelope,
        now: Instant,
    ) -> Result<ProgressDecision, SupervisorError> {
        validate_worker_record(&WorkerWireRecord::Progress(value.clone()))?;
        if self.last_clock.is_some_and(|last| now < last) {
            return Err(protocol_error(
                "REPORT_WORKER_PROTOCOL",
                "monotonic clock moved backwards",
            ));
        }
        self.last_clock = Some(now);
        if self.last_observed.as_ref() == Some(&value) {
            return Ok(ProgressDecision::Ignored);
        }
        if self.last_observed_phase.as_deref() == Some(value.phase.as_str())
            && value.completed < self.last_observed_completed
        {
            return Err(protocol_error(
                "REPORT_WORKER_PROTOCOL",
                "progress decreased",
            ));
        }
        self.last_observed_phase = Some(value.phase.clone());
        self.last_observed_completed = value.completed;
        self.last_observed = Some(value.clone());

        if self.last_emitted.is_none()
            || self
                .next_progress_at
                .is_some_and(|deadline| now >= deadline)
        {
            self.pending = None;
            self.last_emitted = Some(value.clone());
            self.next_progress_at = Some(now + self.interval);
            Ok(ProgressDecision::Emit(value))
        } else {
            self.pending = Some(value);
            Ok(ProgressDecision::Pending)
        }
    }

    /// Emit a pending value only when its minimum interval has elapsed.
    pub fn flush(&mut self, now: Instant) -> Option<ProgressEnvelope> {
        if self.last_clock.is_some_and(|last| now < last)
            || self.next_progress_at.is_none_or(|deadline| now < deadline)
        {
            return None;
        }
        self.last_clock = Some(now);
        let value = self.pending.take()?;
        self.last_emitted = Some(value.clone());
        self.next_progress_at = Some(now + self.interval);
        Some(value)
    }
}

/// One fixed-text native diagnostic derived from an allowlisted Worker stderr record.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct SanitizedDiagnostic {
    pub level: &'static str,
    pub event: &'static str,
    pub operation_id: Option<String>,
    pub code: Option<String>,
    pub message: String,
}

impl SanitizedDiagnostic {
    /// Construct the single fixed record used for rejected child diagnostics.
    pub fn rejected() -> Self {
        Self {
            level: "warning",
            event: "worker.stderr_rejected",
            operation_id: None,
            code: None,
            message: "Worker diagnostic input was rejected.".to_owned(),
        }
    }

    fn limit_reached() -> Self {
        Self {
            level: "warning",
            event: "worker.stderr_limit_reached",
            operation_id: None,
            code: None,
            message: "Worker diagnostic limit was reached.".to_owned(),
        }
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ChildDiagnostic {
    timestamp: String,
    level: String,
    event: String,
    #[serde(deserialize_with = "deserialize_required_nullable_string")]
    operation_id: Option<String>,
    #[serde(deserialize_with = "deserialize_required_nullable_string")]
    code: Option<String>,
    message: String,
}

/// Incrementally bound, validate, and map untrusted child stderr bytes.
#[derive(Debug)]
pub struct StderrSanitizer {
    buffer: Vec<u8>,
    discarding_oversize: bool,
    rejection_reported: bool,
    sanitized_bytes: usize,
    limit_reported: bool,
    maximum_bytes: usize,
}

impl StderrSanitizer {
    /// Create a generation-scoped sanitizer with a serialized native diagnostic cap.
    pub fn new(maximum_bytes: usize) -> Self {
        Self {
            buffer: Vec::with_capacity(STDERR_LINE_BYTES),
            discarding_oversize: false,
            rejection_reported: false,
            sanitized_bytes: 0,
            limit_reported: false,
            maximum_bytes,
        }
    }

    /// Consume arbitrary stderr bytes and return only newly accepted fixed diagnostics.
    pub fn ingest(&mut self, bytes: &[u8]) -> Vec<SanitizedDiagnostic> {
        let mut output = Vec::new();
        for &byte in bytes {
            if self.discarding_oversize {
                if byte == b'\n' {
                    self.discarding_oversize = false;
                    self.reject_once(&mut output);
                }
                continue;
            }
            if byte == b'\n' {
                let line = std::mem::take(&mut self.buffer);
                match sanitize_child_diagnostic(&line) {
                    Some(value) => self.push_bounded(value, &mut output),
                    None => self.reject_once(&mut output),
                }
            } else if self.buffer.len() + 2 > STDERR_LINE_BYTES {
                self.buffer.clear();
                self.discarding_oversize = true;
            } else {
                self.buffer.push(byte);
            }
        }
        output
    }

    fn reject_once(&mut self, output: &mut Vec<SanitizedDiagnostic>) {
        if !self.rejection_reported {
            self.rejection_reported = true;
            self.push_bounded(SanitizedDiagnostic::rejected(), output);
        }
    }

    fn push_bounded(&mut self, value: SanitizedDiagnostic, output: &mut Vec<SanitizedDiagnostic>) {
        if self.limit_reported {
            return;
        }
        let size = serde_json::to_vec(&value).map_or(0, |encoded| encoded.len() + 1);
        if self.sanitized_bytes.saturating_add(size) <= self.maximum_bytes {
            self.sanitized_bytes += size;
            output.push(value);
        } else {
            self.limit_reported = true;
            output.push(SanitizedDiagnostic::limit_reached());
        }
    }
}

fn sanitize_child_diagnostic(line: &[u8]) -> Option<SanitizedDiagnostic> {
    let text = std::str::from_utf8(line).ok()?;
    let value: ChildDiagnostic = serde_json::from_str(text).ok()?;
    if value.timestamp.chars().count() > 40
        || DateTime::<FixedOffset>::parse_from_rfc3339(&value.timestamp)
            .ok()?
            .offset()
            .local_minus_utc()
            != 0
        || !matches!(value.level.as_str(), "info" | "warning" | "error")
        || !valid_diagnostic_event(&value.event)
        || value
            .operation_id
            .as_deref()
            .is_some_and(|id| validate_operation_id(id).is_err())
        || value
            .code
            .as_deref()
            .is_none_or(|code| !valid_error_code(code))
        || validate_safe_message(&value.message).is_err()
    {
        return None;
    }
    let code = value.code.as_deref()?;
    let event = match (value.event.as_str(), code) {
        ("worker.startup_failed", "REPORT_WORKER_STARTUP_FAILED") => "worker.startup_failed",
        ("worker.invalid_input", "REPORT_WORKER_INVALID_JSON") => "worker.invalid_input",
        ("worker.invalid_input", "REPORT_WORKER_INVALID_ENVELOPE") => "worker.invalid_input",
        ("worker.service_contract", "REPORT_WORKER_SERVICE_CONTRACT") => "worker.service_contract",
        ("worker.internal_failure", "REPORT_WORKER_INTERNAL") => "worker.internal_failure",
        ("worker.output_failed", "REPORT_WORKER_OUTPUT_FAILED") => "worker.output_failed",
        ("worker.shutdown_failed", "REPORT_WORKER_SHUTDOWN_FAILED") => "worker.shutdown_failed",
        _ => return None,
    };
    let level = match value.level.as_str() {
        "info" => "info",
        "warning" => "warning",
        "error" => "error",
        _ => return None,
    };
    let message = if ["API_KEY=", "TOKEN=", "PASSWORD=", "SECRET="]
        .iter()
        .any(|marker| value.message.to_ascii_uppercase().contains(marker))
    {
        "Worker diagnostic contained a redacted sensitive value.".to_owned()
    } else {
        value.message
    };
    Some(SanitizedDiagnostic {
        level,
        event,
        operation_id: value.operation_id,
        code: value.code,
        message,
    })
}

fn valid_diagnostic_event(value: &str) -> bool {
    let mut bytes = value.bytes();
    value.len() <= 64
        && bytes.next().is_some_and(|byte| byte.is_ascii_lowercase())
        && bytes.all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_' || byte == b'.'
        })
}

/// An opaque request that has passed operation-specific schema and path validation.
#[derive(Debug)]
pub struct TrustedWorkerRequest {
    envelope: RequestEnvelope,
    output_grant: Option<OutputGrant>,
}

impl TrustedWorkerRequest {
    /// Validate one non-export operation and reject path authority at every object depth.
    pub fn path_free(envelope: RequestEnvelope) -> Result<Self, SupervisorError> {
        validate_path_free_envelope(&envelope)?;
        Ok(Self {
            envelope,
            output_grant: None,
        })
    }

    /// Consume one matching output grant and build the complete export request.
    pub fn export(
        operation_id: &str,
        snapshot_id: &str,
        surface: AutomationSurfaceWire,
        mode: Option<ExportModeWire>,
        include_sqlite_archive: bool,
        grant: OutputGrant,
    ) -> Result<Self, SupervisorError> {
        validate_operation_id(operation_id)?;
        validate_snapshot_id(Some(snapshot_id))?;
        if grant.operation_id != operation_id {
            return Err(SupervisorError::OutputGrantMismatch {
                operation_id: operation_id.to_owned(),
            });
        }
        let mut arguments = Map::new();
        arguments.insert(
            "surface".to_owned(),
            serde_json::to_value(surface).expect("enum serializes"),
        );
        let target = grant
            .target
            .to_str()
            .ok_or(SupervisorError::PathNotAuthorized {
                kind: PathKind::OutputTarget,
            })?;
        arguments.insert("target".to_owned(), Value::String(target.to_owned()));
        arguments.insert("replace".to_owned(), Value::Bool(grant.replace));
        arguments.insert(
            "mode".to_owned(),
            serde_json::to_value(mode).expect("enum serializes"),
        );
        arguments.insert(
            "include_sqlite_archive".to_owned(),
            Value::Bool(include_sqlite_archive),
        );
        let envelope = RequestEnvelope {
            protocol_version: WORKER_PROTOCOL_VERSION,
            operation_id: operation_id.to_owned(),
            operation: "export_snapshot".to_owned(),
            snapshot_id: Some(snapshot_id.to_owned()),
            arguments,
        };
        Ok(Self {
            envelope,
            output_grant: Some(grant),
        })
    }

    #[doc(hidden)]
    pub fn envelope(&self) -> &RequestEnvelope {
        &self.envelope
    }
}

fn validate_path_free_envelope(envelope: &RequestEnvelope) -> Result<(), SupervisorError> {
    if envelope.protocol_version != WORKER_PROTOCOL_VERSION {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "protocol version mismatch",
        ));
    }
    validate_operation_id(&envelope.operation_id)?;
    validate_operation_name(&envelope.operation, "operation")?;
    validate_snapshot_id(envelope.snapshot_id.as_deref())?;
    if contains_path_authority(&Value::Object(envelope.arguments.clone())) {
        return Err(SupervisorError::PathNotAuthorized {
            kind: PathKind::OutputTarget,
        });
    }
    validate_operation_arguments(
        &envelope.operation,
        envelope.snapshot_id.as_deref(),
        &envelope.arguments,
    )
}

fn contains_path_authority(value: &Value) -> bool {
    match value {
        Value::Object(object) => object.iter().any(|(key, value)| {
            matches!(
                key.as_str(),
                "target"
                    | "path"
                    | "root"
                    | "source_path"
                    | "source_roots"
                    | "authorized_source_roots"
            ) || contains_path_authority(value)
        }),
        Value::Array(values) => values.iter().any(contains_path_authority),
        _ => false,
    }
}

fn validate_operation_arguments(
    operation: &str,
    snapshot_id: Option<&str>,
    arguments: &Map<String, Value>,
) -> Result<(), SupervisorError> {
    let snapshot_required = !matches!(operation, "preflight_report" | "open_snapshot");
    if snapshot_required != snapshot_id.is_some() {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "snapshot correlation mismatch",
        ));
    }
    match operation {
        "preflight_report" => {
            exact_keys(arguments, &["scope"])?;
            validate_scope(object_field(arguments, "scope")?)
        }
        "open_snapshot" => {
            exact_keys(arguments, &["scope", "preflight_token", "source_revision"])?;
            validate_scope(object_field(arguments, "scope")?)?;
            string_field(arguments, "preflight_token")?;
            string_field(arguments, "source_revision")?;
            Ok(())
        }
        "get_summary" | "refresh_snapshot" | "close_snapshot" => exact_keys(arguments, &[]),
        "list_agents" => {
            exact_keys(arguments, &["filters", "sort", "cursor", "page_size"])?;
            let filters = object_field(arguments, "filters")?;
            exact_keys(filters, &["query", "agent_ids", "roles", "states"])?;
            string_field_allow_empty(filters, "query")?;
            for key in ["agent_ids", "roles", "states"] {
                string_array_field(filters, key)?;
            }
            validate_sort(object_field(arguments, "sort")?)?;
            nullable_string_field(arguments, "cursor")?;
            unsigned_field(arguments, "page_size")?;
            Ok(())
        }
        "list_turns" => {
            exact_keys(arguments, &["filters", "sort", "cursor", "page_size"])?;
            let filters = object_field(arguments, "filters")?;
            exact_keys(
                filters,
                &["turn_ids", "agent_ids", "states", "from_time", "to_time"],
            )?;
            for key in ["turn_ids", "agent_ids", "states"] {
                string_array_field(filters, key)?;
            }
            nullable_string_field(filters, "from_time")?;
            nullable_string_field(filters, "to_time")?;
            validate_sort(object_field(arguments, "sort")?)?;
            nullable_string_field(arguments, "cursor")?;
            unsigned_field(arguments, "page_size")?;
            Ok(())
        }
        "list_events" => {
            exact_keys(arguments, &["filters", "sort", "cursor", "page_size"])?;
            validate_event_filters(object_field(arguments, "filters")?)?;
            validate_sort(object_field(arguments, "sort")?)?;
            nullable_string_field(arguments, "cursor")?;
            unsigned_field(arguments, "page_size")?;
            Ok(())
        }
        "query_snapshot_time_range" => validate_snapshot_heatmap_request(arguments).map(|_| ()),
        "query_sequence" => {
            exact_keys(arguments, &["filters", "sort", "cursor", "page_size"])?;
            let filters = object_field(arguments, "filters")?;
            exact_keys(
                filters,
                &[
                    "focus_agent_id",
                    "event_filters",
                    "grouping",
                    "include_reasoning",
                ],
            )?;
            nullable_string_field(filters, "focus_agent_id")?;
            validate_event_filters(object_field(filters, "event_filters")?)?;
            string_field(filters, "grouping")?;
            bool_field(filters, "include_reasoning")?;
            validate_sort(object_field(arguments, "sort")?)?;
            nullable_string_field(arguments, "cursor")?;
            unsigned_field(arguments, "page_size")?;
            Ok(())
        }
        "query_coordination" => {
            exact_keys(arguments, &["filters", "sort", "cursor", "page_size"])?;
            let filters = object_field(arguments, "filters")?;
            exact_keys(
                filters,
                &[
                    "work_item_id",
                    "delegated_root_id",
                    "agent_id",
                    "operation",
                    "evidence",
                ],
            )?;
            for key in [
                "work_item_id",
                "delegated_root_id",
                "agent_id",
                "operation",
                "evidence",
            ] {
                nullable_string_field(filters, key)?;
            }
            validate_sort(object_field(arguments, "sort")?)?;
            nullable_string_field(arguments, "cursor")?;
            unsigned_field(arguments, "page_size")?;
            Ok(())
        }
        "get_event_details" => {
            exact_keys(arguments, &["event_id"])?;
            string_field(arguments, "event_id")?;
            Ok(())
        }
        "export_snapshot" | "worker_handshake" => Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "operation requires a trusted native constructor",
        )),
        _ => Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "unknown operation",
        )),
    }
}

fn validate_snapshot_heatmap_request(
    arguments: &Map<String, Value>,
) -> Result<HeatmapQueryKindWire, SupervisorError> {
    let query_kind = match string_field_value(arguments, "query_kind")? {
        "matrix" => HeatmapQueryKindWire::Matrix,
        "cell_evidence" => HeatmapQueryKindWire::CellEvidence,
        _ => {
            return Err(protocol_error(
                "REPORT_WORKER_PROTOCOL",
                "invalid Heatmap query kind",
            ));
        }
    };
    validate_heatmap_mode(string_field_value(arguments, "mode")?)?;
    match query_kind {
        HeatmapQueryKindWire::Matrix => {
            exact_keys(
                arguments,
                &[
                    "query_kind",
                    "from_time",
                    "to_time",
                    "mode",
                    "requested_resolution_minutes",
                    "maximum_rows",
                ],
            )?;
            validate_utc_range(arguments, "from_time", "to_time")?;
            let resolution = unsigned_field_value(arguments, "requested_resolution_minutes")?;
            if !matches!(resolution, 1 | 5 | 15 | 30 | 60) {
                return Err(protocol_error(
                    "REPORT_WORKER_PROTOCOL",
                    "invalid Heatmap resolution",
                ));
            }
            let maximum_rows = unsigned_field_value(arguments, "maximum_rows")?;
            if !(1..=200).contains(&maximum_rows) {
                return Err(protocol_error(
                    "REPORT_WORKER_PROTOCOL",
                    "invalid Heatmap row limit",
                ));
            }
        }
        HeatmapQueryKindWire::CellEvidence => {
            exact_keys(
                arguments,
                &[
                    "query_kind",
                    "mode",
                    "row_id",
                    "period_start_time",
                    "period_end_time",
                ],
            )?;
            validate_visible_string(
                string_field_value(arguments, "row_id")?,
                1,
                256,
                "Heatmap row id",
            )?;
            validate_utc_range(arguments, "period_start_time", "period_end_time")?;
        }
    }
    Ok(query_kind)
}

fn validate_heatmap_mode(mode: &str) -> Result<(), SupervisorError> {
    if matches!(mode, "wall_time" | "tokens" | "models") {
        Ok(())
    } else {
        Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid Heatmap mode",
        ))
    }
}

fn validate_utc_range(
    value: &Map<String, Value>,
    start_key: &'static str,
    end_key: &'static str,
) -> Result<(), SupervisorError> {
    let start = parse_utc_instant(string_field_value(value, start_key)?)?;
    let end = parse_utc_instant(string_field_value(value, end_key)?)?;
    if start < end {
        Ok(())
    } else {
        Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid Heatmap time range",
        ))
    }
}

fn parse_utc_instant(value: &str) -> Result<DateTime<FixedOffset>, SupervisorError> {
    let parsed = DateTime::parse_from_rfc3339(value)
        .map_err(|_| protocol_error("REPORT_WORKER_PROTOCOL", "invalid Heatmap UTC instant"))?;
    if parsed.offset().local_minus_utc() == 0 {
        Ok(parsed)
    } else {
        Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid Heatmap UTC instant",
        ))
    }
}

fn validate_snapshot_heatmap_result(
    request_snapshot_id: Option<&str>,
    arguments: &Map<String, Value>,
    result: &Map<String, Value>,
) -> Result<(), SupervisorError> {
    let request_snapshot_id = request_snapshot_id.ok_or_else(|| {
        protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "Heatmap result has no request snapshot",
        )
    })?;
    let request_kind = validate_snapshot_heatmap_request(arguments)?;
    let result_snapshot_id = string_field_value(result, "snapshot_id")?;
    if result_snapshot_id != request_snapshot_id {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "Heatmap snapshot correlation mismatch",
        ));
    }
    validate_visible_string(
        string_field_value(result, "revision_id")?,
        1,
        256,
        "Heatmap revision id",
    )?;
    let result_kind = match string_field_value(result, "query_kind")? {
        "matrix" => HeatmapQueryKindWire::Matrix,
        "cell_evidence" => HeatmapQueryKindWire::CellEvidence,
        _ => {
            return Err(protocol_error(
                "REPORT_WORKER_PROTOCOL",
                "invalid Heatmap result kind",
            ));
        }
    };
    if result_kind != request_kind {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "Heatmap result variant mismatch",
        ));
    }
    let mode = string_field_value(result, "mode")?;
    validate_heatmap_mode(mode)?;
    if mode != string_field_value(arguments, "mode")? {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "Heatmap mode correlation mismatch",
        ));
    }
    match result_kind {
        HeatmapQueryKindWire::Matrix => validate_heatmap_matrix_result(arguments, result),
        HeatmapQueryKindWire::CellEvidence => {
            validate_heatmap_cell_evidence_result(arguments, result)
        }
    }
}

fn validate_heatmap_matrix_result(
    arguments: &Map<String, Value>,
    result: &Map<String, Value>,
) -> Result<(), SupervisorError> {
    exact_keys(
        result,
        &[
            "snapshot_id",
            "revision_id",
            "query_kind",
            "mode",
            "from_time",
            "to_time",
            "requested_resolution_minutes",
            "actual_resolution_minutes",
            "maximum_rows",
            "omitted_row_count",
            "row_order",
            "total_cell_count",
            "rows",
            "provenance",
        ],
    )?;
    for key in [
        "from_time",
        "to_time",
        "requested_resolution_minutes",
        "maximum_rows",
    ] {
        if result.get(key) != arguments.get(key) {
            return Err(protocol_error(
                "REPORT_WORKER_PROTOCOL",
                "Heatmap matrix selector mismatch",
            ));
        }
    }
    let range_start = parse_utc_instant(string_field_value(result, "from_time")?)?;
    let range_end = parse_utc_instant(string_field_value(result, "to_time")?)?;
    if range_start >= range_end {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid Heatmap time range",
        ));
    }
    let requested_resolution = unsigned_field_value(result, "requested_resolution_minutes")?;
    let actual_resolution = unsigned_field_value(result, "actual_resolution_minutes")?;
    if !matches!(actual_resolution, 1 | 5 | 15 | 30 | 60)
        || actual_resolution < requested_resolution
    {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid Heatmap actual resolution",
        ));
    }
    let maximum_rows = usize::try_from(unsigned_field_value(result, "maximum_rows")?)
        .map_err(|_| protocol_error("REPORT_WORKER_PROTOCOL", "invalid Heatmap row limit"))?;
    unsigned_field_value(result, "omitted_row_count")?;
    let mode = string_field_value(result, "mode")?;
    let expected_row_order = match mode {
        "wall_time" => "runtime_state_contract",
        "tokens" => "token_contract",
        "models" => "model_first_occurrence_then_cost",
        _ => unreachable!("mode was validated before matrix validation"),
    };
    if string_field_value(result, "row_order")? != expected_row_order {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid Heatmap row order",
        ));
    }
    let declared_total = usize::try_from(unsigned_field_value(result, "total_cell_count")?)
        .map_err(|_| protocol_error("REPORT_WORKER_PROTOCOL", "invalid Heatmap cell count"))?;
    if declared_total > MAX_HEATMAP_CELLS {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "Heatmap cell limit exceeded",
        ));
    }
    let rows = array_field(result, "rows")?;
    if rows.len() > maximum_rows {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "Heatmap row limit exceeded",
        ));
    }
    let mut row_ids = HashSet::new();
    let mut row_keys = HashSet::new();
    let mut wall_time_order = WallTimeRowOrder::default();
    let mut model_cost_seen = false;
    let mut actual_total = 0usize;
    for (row_index, row) in rows.iter().enumerate() {
        let row = row.as_object().ok_or_else(|| {
            protocol_error("REPORT_WORKER_PROTOCOL", "invalid Heatmap matrix row")
        })?;
        let declared_index = usize::try_from(unsigned_field_value(row, "row_order_index")?)
            .map_err(|_| {
                protocol_error("REPORT_WORKER_PROTOCOL", "invalid Heatmap row order index")
            })?;
        if declared_index != row_index || declared_index >= MAX_HEATMAP_ROWS {
            return Err(protocol_error(
                "REPORT_WORKER_PROTOCOL",
                "invalid Heatmap row order index",
            ));
        }
        let row_key = string_field_value(row, "row_key")?;
        let row_kind = string_field_value(row, "row_kind")?;
        validate_heatmap_row_order(
            mode,
            row_key,
            row_kind,
            row_index,
            &mut wall_time_order,
            &mut model_cost_seen,
        )?;
        actual_total = actual_total
            .checked_add(validate_heatmap_matrix_row(
                row,
                &range_start,
                &range_end,
                actual_resolution,
            )?)
            .ok_or_else(|| {
                protocol_error("REPORT_WORKER_PROTOCOL", "invalid Heatmap cell count")
            })?;
        if !row_ids.insert(string_field_value(row, "row_id")?) {
            return Err(protocol_error(
                "REPORT_WORKER_PROTOCOL",
                "duplicate Heatmap row id",
            ));
        }
        if !row_keys.insert(row_key) {
            return Err(protocol_error(
                "REPORT_WORKER_PROTOCOL",
                "duplicate Heatmap row key",
            ));
        }
    }
    if actual_total != declared_total || actual_total > MAX_HEATMAP_CELLS {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "Heatmap cell total mismatch",
        ));
    }
    validate_provenance(result)
}

fn validate_heatmap_matrix_row(
    row: &Map<String, Value>,
    range_start: &DateTime<FixedOffset>,
    range_end: &DateTime<FixedOffset>,
    actual_resolution_minutes: u64,
) -> Result<usize, SupervisorError> {
    exact_keys(
        row,
        &[
            "row_id",
            "row_key",
            "row_order_index",
            "row_kind",
            "label",
            "scale",
            "cells",
        ],
    )?;
    validate_visible_string(string_field_value(row, "row_id")?, 1, 256, "Heatmap row id")?;
    validate_json_escaped_string(row, "label", MAX_HEATMAP_LABEL_ESCAPED_BYTES)?;
    let row_key = string_field_value(row, "row_key")?;
    let scale = validate_heatmap_scale(object_field(row, "scale")?)?;
    validate_heatmap_scale_for_row(row_key, scale)?;
    let cells = array_field(row, "cells")?;
    let mut previous_end: Option<DateTime<FixedOffset>> = None;
    for cell in cells {
        let cell = cell.as_object().ok_or_else(|| {
            protocol_error("REPORT_WORKER_PROTOCOL", "invalid Heatmap matrix cell")
        })?;
        let (start, end) = validate_heatmap_cell(cell, scale)?;
        if start < *range_start
            || end > *range_end
            || (end - start).num_seconds() > actual_resolution_minutes as i64 * 60
            || previous_end
                .as_ref()
                .is_some_and(|previous| start < *previous)
        {
            return Err(protocol_error(
                "REPORT_WORKER_PROTOCOL",
                "Heatmap cells are not chronological",
            ));
        }
        previous_end = Some(end);
    }
    Ok(cells.len())
}

#[derive(Default)]
struct WallTimeRowOrder {
    last_known_ordinal: Option<usize>,
    last_runtime_suffix: Option<String>,
    runtime_started: bool,
}

fn validate_heatmap_row_order(
    mode: &str,
    row_key: &str,
    row_kind: &str,
    row_index: usize,
    wall_time: &mut WallTimeRowOrder,
    model_cost_seen: &mut bool,
) -> Result<(), SupervisorError> {
    validate_heatmap_row_key_mode(mode, row_key, row_kind)?;
    match mode {
        "tokens" => {
            if TOKEN_ROW_KEYS.get(row_index).copied() != Some(row_key) {
                return Err(protocol_error(
                    "REPORT_WORKER_PROTOCOL",
                    "invalid token Heatmap row order",
                ));
            }
        }
        "wall_time" => {
            if let Some(ordinal) = WALL_TIME_ROW_KEYS
                .iter()
                .position(|known| *known == row_key)
            {
                if wall_time.runtime_started
                    || wall_time
                        .last_known_ordinal
                        .is_some_and(|previous| ordinal <= previous)
                {
                    return Err(protocol_error(
                        "REPORT_WORKER_PROTOCOL",
                        "invalid wall-time Heatmap row order",
                    ));
                }
                wall_time.last_known_ordinal = Some(ordinal);
            } else {
                let suffix = runtime_row_suffix(row_key)?;
                if wall_time
                    .last_runtime_suffix
                    .as_deref()
                    .is_some_and(|previous| suffix <= previous)
                {
                    return Err(protocol_error(
                        "REPORT_WORKER_PROTOCOL",
                        "invalid runtime Heatmap row order",
                    ));
                }
                wall_time.runtime_started = true;
                wall_time.last_runtime_suffix = Some(suffix.to_owned());
            }
        }
        "models" => {
            if *model_cost_seen {
                return Err(protocol_error(
                    "REPORT_WORKER_PROTOCOL",
                    "model Heatmap row follows cost",
                ));
            }
            if row_key == "cost" {
                *model_cost_seen = true;
            }
        }
        _ => unreachable!("Heatmap mode was validated before row validation"),
    }
    Ok(())
}

fn validate_heatmap_row_key_mode(
    mode: &str,
    row_key: &str,
    row_kind: &str,
) -> Result<(), SupervisorError> {
    let valid = match mode {
        "wall_time" => {
            (WALL_TIME_ROW_KEYS.contains(&row_key) || runtime_row_suffix(row_key).is_ok())
                && row_kind == "runtime_state"
        }
        "tokens" => {
            TOKEN_ROW_KEYS.contains(&row_key)
                && if row_key == "cost" {
                    row_kind == "cost"
                } else {
                    row_kind == "token_measure"
                }
        }
        "models" => {
            if row_key == "cost" {
                row_kind == "cost"
            } else {
                valid_model_row_key(row_key) && row_kind == "model"
            }
        }
        _ => false,
    };
    if valid {
        Ok(())
    } else {
        Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid Heatmap row key or kind",
        ))
    }
}

fn runtime_row_suffix(row_key: &str) -> Result<&str, SupervisorError> {
    let suffix = row_key.strip_prefix("runtime:").ok_or_else(|| {
        protocol_error("REPORT_WORKER_PROTOCOL", "invalid runtime Heatmap row key")
    })?;
    let valid = !suffix.is_empty()
        && suffix.len() <= 128
        && !WALL_TIME_ROW_KEYS.contains(&suffix)
        && suffix.chars().all(|character| {
            !character.is_control() && character != '\u{7f}' && !character.is_uppercase()
        });
    if valid {
        Ok(suffix)
    } else {
        Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid runtime Heatmap row key",
        ))
    }
}

fn valid_model_row_key(row_key: &str) -> bool {
    row_key.strip_prefix("model:").is_some_and(|digest| {
        digest.len() == 24
            && digest
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    })
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum HeatmapScaleWire {
    VisibleMaximum,
    ContextCapacity,
    ContextCapacityUnavailable,
}

fn validate_heatmap_scale(scale: &Map<String, Value>) -> Result<HeatmapScaleWire, SupervisorError> {
    match string_field_value(scale, "availability")? {
        "available" => {
            exact_keys(scale, &["availability", "minimum", "maximum", "basis"])?;
            let minimum = finite_number_field(scale, "minimum")?;
            let maximum = finite_number_field(scale, "maximum")?;
            if minimum > maximum
                || !matches!(
                    string_field_value(scale, "basis")?,
                    "visible_row_maximum" | "context_window_capacity"
                )
            {
                return Err(protocol_error(
                    "REPORT_WORKER_PROTOCOL",
                    "invalid available Heatmap scale",
                ));
            }
            Ok(match string_field_value(scale, "basis")? {
                "visible_row_maximum" => HeatmapScaleWire::VisibleMaximum,
                "context_window_capacity" => HeatmapScaleWire::ContextCapacity,
                _ => unreachable!("basis was validated above"),
            })
        }
        "unavailable" => {
            exact_keys(scale, &["availability", "reason"])?;
            if string_field_value(scale, "reason")? != "context_capacity_unavailable" {
                return Err(protocol_error(
                    "REPORT_WORKER_PROTOCOL",
                    "invalid unavailable Heatmap scale",
                ));
            }
            Ok(HeatmapScaleWire::ContextCapacityUnavailable)
        }
        _ => Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid Heatmap scale availability",
        )),
    }
}

fn validate_heatmap_scale_for_row(
    row_key: &str,
    scale: HeatmapScaleWire,
) -> Result<(), SupervisorError> {
    let context_row = matches!(row_key, "context_average" | "context_maximum");
    let valid = if context_row {
        matches!(
            scale,
            HeatmapScaleWire::ContextCapacity | HeatmapScaleWire::ContextCapacityUnavailable
        )
    } else {
        scale == HeatmapScaleWire::VisibleMaximum
    };
    if valid {
        Ok(())
    } else {
        Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "Heatmap scale does not match the semantic row key",
        ))
    }
}

fn validate_heatmap_cell(
    cell: &Map<String, Value>,
    scale: HeatmapScaleWire,
) -> Result<(DateTime<FixedOffset>, DateTime<FixedOffset>), SupervisorError> {
    exact_keys(
        cell,
        &[
            "start_time",
            "end_time",
            "value",
            "formatted_value",
            "value_state",
            "applicable_zero",
            "contributing_evidence_count",
            "normalized_intensity",
            "supporting_text",
        ],
    )?;
    let start = parse_utc_instant(string_field_value(cell, "start_time")?)?;
    let end = parse_utc_instant(string_field_value(cell, "end_time")?)?;
    if start >= end {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid Heatmap cell range",
        ));
    }
    let value = nullable_finite_number_field(cell, "value")?;
    validate_json_escaped_string(
        cell,
        "formatted_value",
        MAX_HEATMAP_FORMATTED_VALUE_ESCAPED_BYTES,
    )?;
    let value_state = validate_heatmap_value_state(string_field_value(cell, "value_state")?)?;
    let applicable_zero = bool_field_value(cell, "applicable_zero")?;
    validate_value_state(value, value_state, applicable_zero)?;
    unsigned_field_value(cell, "contributing_evidence_count")?;
    let intensity = nullable_finite_number_field(cell, "normalized_intensity")?;
    if intensity.is_some_and(|value| !(0.0..=1.0).contains(&value))
        || (scale == HeatmapScaleWire::ContextCapacityUnavailable && intensity.is_some())
        || (scale != HeatmapScaleWire::ContextCapacityUnavailable
            && value.is_some() != intensity.is_some())
    {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid Heatmap normalized intensity",
        ));
    }
    let supporting_text = nullable_json_escaped_string(
        cell,
        "supporting_text",
        MAX_HEATMAP_SUPPORTING_TEXT_ESCAPED_BYTES,
    )?;
    if scale == HeatmapScaleWire::ContextCapacityUnavailable
        && (contains_percentage(string_field_value(cell, "formatted_value")?)
            || supporting_text.is_some_and(|text| {
                contains_percentage(text) || !valid_observed_token_support(text)
            }))
    {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "unavailable Heatmap context scale contains a percentage",
        ));
    }
    Ok((start, end))
}

fn validate_heatmap_cell_evidence_result(
    arguments: &Map<String, Value>,
    result: &Map<String, Value>,
) -> Result<(), SupervisorError> {
    exact_keys(
        result,
        &[
            "snapshot_id",
            "revision_id",
            "query_kind",
            "mode",
            "row_id",
            "row_key",
            "row_order_index",
            "row_label",
            "period_start_time",
            "period_end_time",
            "value",
            "formatted_value",
            "value_state",
            "applicable_zero",
            "evidence_items",
            "omitted_evidence_count",
            "provenance",
        ],
    )?;
    for key in ["row_id", "period_start_time", "period_end_time"] {
        if result.get(key) != arguments.get(key) {
            return Err(protocol_error(
                "REPORT_WORKER_PROTOCOL",
                "Heatmap evidence selector mismatch",
            ));
        }
    }
    let period_start = parse_utc_instant(string_field_value(result, "period_start_time")?)?;
    let period_end = parse_utc_instant(string_field_value(result, "period_end_time")?)?;
    if period_start >= period_end {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid Heatmap evidence period",
        ));
    }
    validate_heatmap_evidence_row_key(
        string_field_value(result, "mode")?,
        string_field_value(result, "row_key")?,
    )?;
    if unsigned_field_value(result, "row_order_index")? >= MAX_HEATMAP_ROWS as u64 {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid Heatmap row order index",
        ));
    }
    validate_json_escaped_string(result, "row_label", MAX_HEATMAP_LABEL_ESCAPED_BYTES)?;
    let value = nullable_finite_number_field(result, "value")?;
    validate_json_escaped_string(
        result,
        "formatted_value",
        MAX_HEATMAP_FORMATTED_VALUE_ESCAPED_BYTES,
    )?;
    let value_state = validate_heatmap_value_state(string_field_value(result, "value_state")?)?;
    validate_value_state(
        value,
        value_state,
        bool_field_value(result, "applicable_zero")?,
    )?;
    let items = array_field(result, "evidence_items")?;
    if items.len() > MAX_HEATMAP_EVIDENCE_ITEMS {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "Heatmap evidence limit exceeded",
        ));
    }
    let mut previous_time: Option<DateTime<FixedOffset>> = None;
    for item in items {
        let item = item.as_object().ok_or_else(|| {
            protocol_error("REPORT_WORKER_PROTOCOL", "invalid Heatmap evidence item")
        })?;
        let occurred_at = validate_heatmap_evidence_item(item)?;
        if occurred_at < period_start
            || occurred_at >= period_end
            || previous_time
                .as_ref()
                .is_some_and(|previous| occurred_at < *previous)
        {
            return Err(protocol_error(
                "REPORT_WORKER_PROTOCOL",
                "Heatmap evidence is not chronological",
            ));
        }
        previous_time = Some(occurred_at);
    }
    unsigned_field_value(result, "omitted_evidence_count")?;
    validate_provenance(result)
}

fn validate_heatmap_evidence_row_key(mode: &str, row_key: &str) -> Result<(), SupervisorError> {
    let valid = match mode {
        "wall_time" => WALL_TIME_ROW_KEYS.contains(&row_key) || runtime_row_suffix(row_key).is_ok(),
        "tokens" => TOKEN_ROW_KEYS.contains(&row_key),
        "models" => row_key == "cost" || valid_model_row_key(row_key),
        _ => false,
    };
    if valid {
        Ok(())
    } else {
        Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid Heatmap evidence row key",
        ))
    }
}

fn validate_heatmap_evidence_item(
    item: &Map<String, Value>,
) -> Result<DateTime<FixedOffset>, SupervisorError> {
    exact_keys(
        item,
        &[
            "event_id",
            "occurred_at",
            "value",
            "formatted_value",
            "duration_ms",
            "label",
            "preview",
            "evidence_method",
            "value_state",
            "has_detail",
        ],
    )?;
    let event_id = nullable_bounded_string(item, "event_id", 256)?;
    let occurred_at = parse_utc_instant(string_field_value(item, "occurred_at")?)?;
    let value = nullable_finite_number_field(item, "value")?;
    validate_json_escaped_string(
        item,
        "formatted_value",
        MAX_HEATMAP_FORMATTED_VALUE_ESCAPED_BYTES,
    )?;
    nullable_unsigned_field_value(item, "duration_ms")?;
    validate_json_escaped_string(item, "label", MAX_HEATMAP_LABEL_ESCAPED_BYTES)?;
    nullable_json_escaped_string(item, "preview", MAX_HEATMAP_PREVIEW_ESCAPED_BYTES)?;
    if !matches!(
        string_field_value(item, "evidence_method")?,
        "measured" | "derived" | "inferred" | "estimated" | "unavailable"
    ) {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid Heatmap evidence method",
        ));
    }
    let value_state = validate_heatmap_value_state(string_field_value(item, "value_state")?)?;
    validate_value_state(value, value_state, false)?;
    if bool_field_value(item, "has_detail")? && event_id.is_none() {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "Heatmap detail has no event identity",
        ));
    }
    Ok(occurred_at)
}

#[derive(Clone, Copy)]
enum HeatmapValueStateWire {
    Measured,
    Derived,
    Partial,
    Unavailable,
}

fn validate_heatmap_value_state(value: &str) -> Result<HeatmapValueStateWire, SupervisorError> {
    match value {
        "measured" => Ok(HeatmapValueStateWire::Measured),
        "derived" => Ok(HeatmapValueStateWire::Derived),
        "partial" => Ok(HeatmapValueStateWire::Partial),
        "unavailable" => Ok(HeatmapValueStateWire::Unavailable),
        _ => Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid Heatmap value state",
        )),
    }
}

fn validate_value_state(
    value: Option<f64>,
    state: HeatmapValueStateWire,
    applicable_zero: bool,
) -> Result<(), SupervisorError> {
    if matches!(state, HeatmapValueStateWire::Unavailable) && value.is_some()
        || applicable_zero
            && (!matches!(
                state,
                HeatmapValueStateWire::Measured | HeatmapValueStateWire::Derived
            ) || value != Some(0.0))
    {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid Heatmap value state combination",
        ));
    }
    Ok(())
}

fn validate_provenance(value: &Map<String, Value>) -> Result<(), SupervisorError> {
    let provenance = array_field(value, "provenance")?;
    if provenance.len() > MAX_HEATMAP_PROVENANCE_ITEMS {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "Heatmap provenance limit exceeded",
        ));
    }
    for item in provenance {
        let item = item.as_str().ok_or_else(|| {
            protocol_error("REPORT_WORKER_PROTOCOL", "invalid Heatmap provenance")
        })?;
        if item.is_empty()
            || json_escaped_content_bytes(item) > MAX_HEATMAP_PROVENANCE_ESCAPED_BYTES
        {
            return Err(protocol_error(
                "REPORT_WORKER_PROTOCOL",
                "invalid Heatmap provenance",
            ));
        }
    }
    Ok(())
}

pub(super) fn project_snapshot_heatmap_result(
    result: Map<String, Value>,
) -> Result<Map<String, Value>, SupervisorError> {
    fn project(value: Value) -> Result<Value, SupervisorError> {
        match value {
            Value::Array(values) => values
                .into_iter()
                .map(project)
                .collect::<Result<Vec<_>, _>>()
                .map(Value::Array),
            Value::Object(values) => {
                let mut output = Map::new();
                for (key, value) in values {
                    let mut projected = String::with_capacity(key.len());
                    let mut uppercase = false;
                    for character in key.chars() {
                        if character == '_' {
                            uppercase = true;
                        } else if uppercase {
                            projected.extend(character.to_uppercase());
                            uppercase = false;
                        } else {
                            projected.push(character);
                        }
                    }
                    if output.insert(projected, project(value)?).is_some() {
                        return Err(protocol_error(
                            "REPORT_WORKER_PROTOCOL",
                            "Heatmap projection key collision",
                        ));
                    }
                }
                Ok(Value::Object(output))
            }
            scalar => Ok(scalar),
        }
    }

    let projected = project(Value::Object(result))?;
    projected.as_object().cloned().ok_or_else(|| {
        protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "Heatmap projection is not an object",
        )
    })
}

fn validate_scope(value: &Map<String, Value>) -> Result<(), SupervisorError> {
    exact_keys(
        value,
        &[
            "root_thread_id",
            "include_children",
            "include_collaborators",
        ],
    )?;
    string_field(value, "root_thread_id")?;
    bool_field(value, "include_children")?;
    bool_field(value, "include_collaborators")
}

fn validate_event_filters(value: &Map<String, Value>) -> Result<(), SupervisorError> {
    exact_keys(
        value,
        &[
            "event_ids",
            "agent_ids",
            "turn_ids",
            "kinds",
            "from_time",
            "to_time",
        ],
    )?;
    for key in ["event_ids", "agent_ids", "turn_ids", "kinds"] {
        string_array_field(value, key)?;
    }
    nullable_string_field(value, "from_time")?;
    nullable_string_field(value, "to_time")
}

fn validate_sort(value: &Map<String, Value>) -> Result<(), SupervisorError> {
    exact_keys(
        value,
        &["key", "direction", "tie_break_key", "tie_break_direction"],
    )?;
    for key in ["key", "direction", "tie_break_key", "tie_break_direction"] {
        string_field(value, key)?;
    }
    Ok(())
}

fn exact_keys(value: &Map<String, Value>, keys: &[&str]) -> Result<(), SupervisorError> {
    if value.len() == keys.len() && keys.iter().all(|key| value.contains_key(*key)) {
        Ok(())
    } else {
        Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "invalid argument fields",
        ))
    }
}

fn object_field<'a>(
    value: &'a Map<String, Value>,
    key: &'static str,
) -> Result<&'a Map<String, Value>, SupervisorError> {
    value
        .get(key)
        .and_then(Value::as_object)
        .ok_or_else(|| protocol_error("REPORT_WORKER_PROTOCOL", key))
}

fn array_field<'a>(
    value: &'a Map<String, Value>,
    key: &'static str,
) -> Result<&'a Vec<Value>, SupervisorError> {
    value
        .get(key)
        .and_then(Value::as_array)
        .ok_or_else(|| protocol_error("REPORT_WORKER_PROTOCOL", key))
}

fn string_field(value: &Map<String, Value>, key: &'static str) -> Result<(), SupervisorError> {
    value
        .get(key)
        .and_then(Value::as_str)
        .filter(|item| !item.is_empty())
        .map(|_| ())
        .ok_or_else(|| protocol_error("REPORT_WORKER_PROTOCOL", key))
}

fn string_field_value<'a>(
    value: &'a Map<String, Value>,
    key: &'static str,
) -> Result<&'a str, SupervisorError> {
    value
        .get(key)
        .and_then(Value::as_str)
        .filter(|field| !field.is_empty())
        .ok_or_else(|| protocol_error("REPORT_WORKER_PROTOCOL", key))
}

fn string_field_allow_empty(
    value: &Map<String, Value>,
    key: &'static str,
) -> Result<(), SupervisorError> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(|_| ())
        .ok_or_else(|| protocol_error("REPORT_WORKER_PROTOCOL", key))
}

fn nullable_string_field(
    value: &Map<String, Value>,
    key: &'static str,
) -> Result<(), SupervisorError> {
    match value.get(key) {
        Some(Value::Null | Value::String(_)) => Ok(()),
        _ => Err(protocol_error("REPORT_WORKER_PROTOCOL", key)),
    }
}

fn unsigned_field(value: &Map<String, Value>, key: &'static str) -> Result<(), SupervisorError> {
    value
        .get(key)
        .and_then(Value::as_u64)
        .map(|_| ())
        .ok_or_else(|| protocol_error("REPORT_WORKER_PROTOCOL", key))
}

fn unsigned_field_value(
    value: &Map<String, Value>,
    key: &'static str,
) -> Result<u64, SupervisorError> {
    value
        .get(key)
        .and_then(Value::as_u64)
        .ok_or_else(|| protocol_error("REPORT_WORKER_PROTOCOL", key))
}

fn nullable_unsigned_field_value(
    value: &Map<String, Value>,
    key: &'static str,
) -> Result<Option<u64>, SupervisorError> {
    match value.get(key) {
        Some(Value::Null) => Ok(None),
        Some(_) => unsigned_field_value(value, key).map(Some),
        None => Err(protocol_error("REPORT_WORKER_PROTOCOL", key)),
    }
}

fn bool_field(value: &Map<String, Value>, key: &'static str) -> Result<(), SupervisorError> {
    value
        .get(key)
        .and_then(Value::as_bool)
        .map(|_| ())
        .ok_or_else(|| protocol_error("REPORT_WORKER_PROTOCOL", key))
}

fn bool_field_value(
    value: &Map<String, Value>,
    key: &'static str,
) -> Result<bool, SupervisorError> {
    value
        .get(key)
        .and_then(Value::as_bool)
        .ok_or_else(|| protocol_error("REPORT_WORKER_PROTOCOL", key))
}

fn finite_number_field(
    value: &Map<String, Value>,
    key: &'static str,
) -> Result<f64, SupervisorError> {
    value
        .get(key)
        .and_then(Value::as_f64)
        .filter(|number| number.is_finite())
        .ok_or_else(|| protocol_error("REPORT_WORKER_PROTOCOL", key))
}

fn nullable_finite_number_field(
    value: &Map<String, Value>,
    key: &'static str,
) -> Result<Option<f64>, SupervisorError> {
    match value.get(key) {
        Some(Value::Null) => Ok(None),
        Some(_) => finite_number_field(value, key).map(Some),
        None => Err(protocol_error("REPORT_WORKER_PROTOCOL", key)),
    }
}

fn validate_json_escaped_string(
    value: &Map<String, Value>,
    key: &'static str,
    maximum_escaped_bytes: usize,
) -> Result<(), SupervisorError> {
    let field = string_field_value(value, key)?;
    if json_escaped_content_bytes(field) <= maximum_escaped_bytes {
        Ok(())
    } else {
        Err(protocol_error("REPORT_WORKER_PROTOCOL", key))
    }
}

fn nullable_json_escaped_string<'a>(
    value: &'a Map<String, Value>,
    key: &'static str,
    maximum_escaped_bytes: usize,
) -> Result<Option<&'a str>, SupervisorError> {
    match value.get(key) {
        Some(Value::Null) => Ok(None),
        Some(Value::String(field))
            if !field.is_empty() && json_escaped_content_bytes(field) <= maximum_escaped_bytes =>
        {
            Ok(Some(field))
        }
        _ => Err(protocol_error("REPORT_WORKER_PROTOCOL", key)),
    }
}

fn json_escaped_content_bytes(value: &str) -> usize {
    serde_json::to_vec(value)
        .map(|encoded| encoded.len().saturating_sub(2))
        .unwrap_or(usize::MAX)
}

fn contains_percentage(value: &str) -> bool {
    let lower = value.to_lowercase();
    value.contains(['%', '\u{066a}', '\u{fe6a}', '\u{ff05}']) || lower.contains("percent")
}

fn valid_observed_token_support(value: &str) -> bool {
    value
        .strip_suffix(" tokens observed")
        .is_some_and(|number| {
            !number.is_empty()
                && number.bytes().all(|byte| {
                    byte.is_ascii_digit() || matches!(byte, b',' | b'.' | b'K' | b'M' | b'B')
                })
        })
}

fn nullable_bounded_string<'a>(
    value: &'a Map<String, Value>,
    key: &'static str,
    maximum_bytes: usize,
) -> Result<Option<&'a str>, SupervisorError> {
    match value.get(key) {
        Some(Value::Null) => Ok(None),
        Some(Value::String(field)) if !field.is_empty() && field.len() <= maximum_bytes => {
            Ok(Some(field))
        }
        _ => Err(protocol_error("REPORT_WORKER_PROTOCOL", key)),
    }
}

fn string_array_field(value: &Map<String, Value>, key: &str) -> Result<(), SupervisorError> {
    value
        .get(key)
        .and_then(Value::as_array)
        .filter(|items| items.iter().all(Value::is_string))
        .map(|_| ())
        .ok_or_else(|| protocol_error("REPORT_WORKER_PROTOCOL", "invalid string array argument"))
}

enum SupervisorCommand {
    WaitUntilReady {
        reply: SyncSender<Result<(), SupervisorError>>,
    },
    Submit {
        request: TrustedWorkerRequest,
        observer: Arc<dyn OperationObserver>,
        reply: SyncSender<Result<(), SupervisorError>>,
    },
    Cancel {
        operation_id: String,
        reply: SyncSender<Result<(), SupervisorError>>,
    },
    Restart {
        reason: RestartReason,
        reply: SyncSender<Result<(), SupervisorError>>,
    },
    Shutdown {
        reply: SyncSender<Result<(), SupervisorError>>,
    },
    WorkerRecord {
        generation_id: u64,
        record: WorkerWireRecord,
    },
    WorkerProtocolFailure {
        generation_id: u64,
        error: SupervisorError,
    },
    WorkerEof {
        generation_id: u64,
    },
    ProcessExited {
        generation_id: u64,
        exit_code: Option<i32>,
    },
    GraceExpired {
        generation_id: u64,
        operation_id: String,
    },
    StartupExpired {
        generation_id: u64,
    },
}

#[derive(Debug, Clone, Copy)]
struct RecoveryAttempt {
    source_generation: u64,
    target_generation: u64,
}

/// The public thread-safe handle for one coordinator-owned Worker process.
pub struct WorkerSupervisor {
    commands: SyncSender<SupervisorCommand>,
    coordinator: Mutex<Option<JoinHandle<()>>>,
    shutdown_complete: AtomicBool,
}

impl WorkerSupervisor {
    /// Validate static authority, establish process-tree ownership, and start the handshake.
    ///
    /// The returned Supervisor remains in `Starting` until `wait_until_ready` succeeds.
    pub fn spawn(
        mut launch: WorkerLaunchSpec,
        mut config: WorkerSupervisorConfig,
    ) -> Result<Arc<Self>, SupervisorError> {
        validate_static_configuration(&mut launch, &mut config)?;
        let (commands, receiver) = mpsc::sync_channel(COMMAND_CAPACITY);
        let (bootstrap_tx, bootstrap_rx) = mpsc::sync_channel(1);
        let coordinator_commands = commands.clone();
        let coordinator = thread::Builder::new()
            .name("agent-report-worker-coordinator".to_owned())
            .spawn(move || {
                RecoveryCoordinator::new(launch, config, coordinator_commands, receiver)
                    .run(bootstrap_tx);
            })
            .map_err(|_| SupervisorError::Spawn {
                message: "unable to start recovery coordinator".to_owned(),
            })?;
        match bootstrap_rx.recv() {
            Ok(Ok(())) => Ok(Arc::new(Self {
                commands,
                coordinator: Mutex::new(Some(coordinator)),
                shutdown_complete: AtomicBool::new(false),
            })),
            Ok(Err(error)) => {
                let _ = coordinator.join();
                Err(error)
            }
            Err(_) => {
                let _ = coordinator.join();
                Err(SupervisorError::CoordinatorClosed)
            }
        }
    }

    /// Wait for the current startup or recovery handshake to reach `Ready`.
    pub fn wait_until_ready(&self) -> Result<(), SupervisorError> {
        self.request(|reply| SupervisorCommand::WaitUntilReady { reply })
    }

    /// Bind one exact native-selected output target to one operation.
    pub fn grant_output_target(
        &self,
        operation_id: &str,
        target: &Path,
        replace: bool,
    ) -> Result<OutputGrant, SupervisorError> {
        validate_operation_id(operation_id)?;
        let target = canonicalize_nonexistent_target(target)?;
        Ok(OutputGrant {
            operation_id: operation_id.to_owned(),
            target,
            replace,
        })
    }

    /// Write one trusted operation and retain its observer until terminal delivery.
    pub fn submit(
        &self,
        request: TrustedWorkerRequest,
        observer: Arc<dyn OperationObserver>,
    ) -> Result<(), SupervisorError> {
        self.request(|reply| SupervisorCommand::Submit {
            request,
            observer,
            reply,
        })
    }

    /// Request cooperative cancellation and start one grace deadline after the flush.
    pub fn cancel(&self, operation_id: &str) -> Result<(), SupervisorError> {
        validate_operation_id(operation_id)?;
        self.request(|reply| SupervisorCommand::Cancel {
            operation_id: operation_id.to_owned(),
            reply,
        })
    }

    /// Serialize a generation replacement and wait for its new handshake result.
    pub fn restart(&self, reason: RestartReason) -> Result<(), SupervisorError> {
        self.request(|reply| SupervisorCommand::Restart { reason, reply })
    }

    /// Stop admission, terminate the owned tree, reap it, and join the coordinator.
    pub fn shutdown(&self) -> Result<(), SupervisorError> {
        if self.shutdown_complete.load(Ordering::Acquire) {
            return Ok(());
        }
        let result = self.request(|reply| SupervisorCommand::Shutdown { reply });
        if result.is_ok() {
            self.shutdown_complete.store(true, Ordering::Release);
            if let Some(join) = self
                .coordinator
                .lock()
                .map_err(|_| SupervisorError::CoordinatorClosed)?
                .take()
            {
                join.join()
                    .map_err(|_| SupervisorError::CoordinatorClosed)?;
            }
        }
        result
    }

    fn request(
        &self,
        command: impl FnOnce(SyncSender<Result<(), SupervisorError>>) -> SupervisorCommand,
    ) -> Result<(), SupervisorError> {
        let (reply_tx, reply_rx) = mpsc::sync_channel(1);
        self.commands
            .send(command(reply_tx))
            .map_err(|_| SupervisorError::CoordinatorClosed)?;
        reply_rx
            .recv()
            .map_err(|_| SupervisorError::CoordinatorClosed)?
    }
}

struct ActiveOperation {
    operation: String,
    snapshot_id: Option<String>,
    arguments: Map<String, Value>,
    observer: Arc<dyn OperationObserver>,
    progress: ProgressCoalescer,
}

struct OwnedProcess {
    child: Child,
    stdin: Option<ChildStdin>,
    tree: ProcessTreeHandle,
}

struct CoordinatorState {
    lifecycle: SupervisorState,
    generation_id: u64,
    active_recovery: Option<RecoveryAttempt>,
    process: Option<OwnedProcess>,
    operations: HashMap<String, ActiveOperation>,
    used_operation_ids: HashSet<String>,
    grace_deadlines: HashMap<String, Instant>,
    startup_waiters: Vec<SyncSender<Result<(), SupervisorError>>>,
    restart_waiters: Vec<SyncSender<Result<(), SupervisorError>>>,
}

struct RecoveryCoordinator {
    launch: WorkerLaunchSpec,
    config: WorkerSupervisorConfig,
    commands: SyncSender<SupervisorCommand>,
    receiver: Receiver<SupervisorCommand>,
    state: CoordinatorState,
}

impl RecoveryCoordinator {
    fn new(
        launch: WorkerLaunchSpec,
        config: WorkerSupervisorConfig,
        commands: SyncSender<SupervisorCommand>,
        receiver: Receiver<SupervisorCommand>,
    ) -> Self {
        Self {
            launch,
            config,
            commands,
            receiver,
            state: CoordinatorState {
                lifecycle: SupervisorState::Stopped,
                generation_id: 0,
                active_recovery: None,
                process: None,
                operations: HashMap::new(),
                used_operation_ids: HashSet::new(),
                grace_deadlines: HashMap::new(),
                startup_waiters: Vec::new(),
                restart_waiters: Vec::new(),
            },
        }
    }

    fn run(mut self, bootstrap: SyncSender<Result<(), SupervisorError>>) {
        self.state.generation_id = 1;
        let started = self.start_generation();
        let should_continue = started.is_ok();
        let _ = bootstrap.send(started);
        if !should_continue {
            return;
        }
        loop {
            match self.receiver.recv_timeout(Duration::from_millis(10)) {
                Ok(command) => {
                    let stop = matches!(command, SupervisorCommand::Shutdown { .. });
                    self.handle_command(command);
                    if stop {
                        break;
                    }
                }
                Err(RecvTimeoutError::Timeout) => {}
                Err(RecvTimeoutError::Disconnected) => break,
            }
            self.poll_process_exit();
        }
        if self.state.lifecycle != SupervisorState::Stopped {
            let _ = self.stop_process();
        }
    }

    fn start_generation(&mut self) -> Result<(), SupervisorError> {
        let generation_id = self.state.generation_id;
        let mut process = spawn_owned_process(&self.launch)?;
        let Some(stdout) = process.child.stdout.take() else {
            cleanup_failed_spawn(&mut process);
            return Err(SupervisorError::Spawn {
                message: "worker stdout pipe is unavailable".to_owned(),
            });
        };
        let Some(stderr) = process.child.stderr.take() else {
            cleanup_failed_spawn(&mut process);
            return Err(SupervisorError::Spawn {
                message: "worker stderr pipe is unavailable".to_owned(),
            });
        };
        if let Err(error) = spawn_stdout_reader(
            generation_id,
            stdout,
            self.config.max_record_bytes,
            self.commands.clone(),
        ) {
            cleanup_failed_spawn(&mut process);
            return Err(error);
        }
        if let Err(error) = spawn_stderr_reader(
            stderr,
            self.config.max_stderr_bytes,
            self.config.diagnostic_sink.clone(),
        ) {
            cleanup_failed_spawn(&mut process);
            return Err(error);
        }
        self.state.process = Some(process);
        self.state.lifecycle = SupervisorState::Starting;
        self.state.operations.clear();
        self.state.used_operation_ids.clear();
        self.state.grace_deadlines.clear();
        if let Err(error) = self.write_handshake() {
            let _ = self.stop_process();
            self.state.lifecycle = SupervisorState::Failed;
            return Err(error);
        }
        let timeout = self.config.startup_timeout;
        let commands = self.commands.clone();
        if let Err(error) = thread::Builder::new()
            .name(format!("agent-report-worker-startup-{generation_id}"))
            .spawn(move || {
                thread::sleep(timeout);
                let _ = commands.send(SupervisorCommand::StartupExpired { generation_id });
            })
            .map_err(|_| SupervisorError::Spawn {
                message: "unable to start startup timer".to_owned(),
            })
        {
            let _ = self.stop_process();
            self.state.lifecycle = SupervisorState::Failed;
            return Err(error);
        }
        Ok(())
    }

    fn handle_command(&mut self, command: SupervisorCommand) {
        match command {
            SupervisorCommand::WaitUntilReady { reply } => match self.state.lifecycle {
                SupervisorState::Ready => send_reply(reply, Ok(())),
                SupervisorState::Starting => self.state.startup_waiters.push(reply),
                actual => send_reply(
                    reply,
                    Err(SupervisorError::InvalidState {
                        expected: SupervisorState::Ready,
                        actual,
                    }),
                ),
            },
            SupervisorCommand::Submit {
                request,
                observer,
                reply,
            } => {
                let result = self.submit(request, observer);
                send_reply(reply, result);
            }
            SupervisorCommand::Cancel {
                operation_id,
                reply,
            } => {
                let result = self.cancel(operation_id);
                send_reply(reply, result);
            }
            SupervisorCommand::Restart { reason, reply } => self.restart(reason, reply),
            SupervisorCommand::Shutdown { reply } => {
                let result = self.shutdown();
                send_reply(reply, result);
            }
            SupervisorCommand::WorkerRecord {
                generation_id,
                record,
            } => {
                if generation_id == self.state.generation_id {
                    self.handle_worker_record(record);
                }
            }
            SupervisorCommand::WorkerProtocolFailure {
                generation_id,
                error,
            } => {
                if generation_id == self.state.generation_id {
                    self.handle_generation_failure(RestartReason::ProtocolFailure, error);
                }
            }
            SupervisorCommand::WorkerEof { generation_id } => {
                if generation_id == self.state.generation_id {
                    self.handle_generation_failure(
                        RestartReason::EndOfFile,
                        protocol_error("REPORT_WORKER_EOF", "worker output ended"),
                    );
                }
            }
            SupervisorCommand::ProcessExited {
                generation_id,
                exit_code,
            } => {
                if generation_id == self.state.generation_id {
                    self.handle_generation_failure(
                        RestartReason::ProcessExit,
                        SupervisorError::RestartFailed {
                            message: match exit_code {
                                Some(_) => "worker process exited unexpectedly".to_owned(),
                                None => "worker process exit status was unavailable".to_owned(),
                            },
                        },
                    );
                }
            }
            SupervisorCommand::GraceExpired {
                generation_id,
                operation_id,
            } => {
                if generation_id == self.state.generation_id
                    && self
                        .state
                        .grace_deadlines
                        .get(&operation_id)
                        .is_some_and(|deadline| Instant::now() >= *deadline)
                    && self.state.operations.contains_key(&operation_id)
                {
                    self.force_cancel(operation_id);
                }
            }
            SupervisorCommand::StartupExpired { generation_id } => {
                if generation_id == self.state.generation_id
                    && self.state.lifecycle == SupervisorState::Starting
                {
                    self.fail_startup(SupervisorError::StartupTimeout);
                }
            }
        }
    }

    fn write_handshake(&mut self) -> Result<(), SupervisorError> {
        let roots = self
            .config
            .path_authority
            .source_roots
            .iter()
            .map(|path| {
                path.to_str().map(str::to_owned).ok_or_else(|| {
                    SupervisorError::InvalidConfiguration {
                        field: "source_roots",
                        message: "a source root is not valid UTF-8".to_owned(),
                    }
                })
            })
            .collect::<Result<Vec<_>, _>>()?;
        let service = &self.config.service_configuration;
        let request = RequestEnvelope {
            protocol_version: WORKER_PROTOCOL_VERSION,
            operation_id: HANDSHAKE_OPERATION_ID.to_owned(),
            operation: "worker_handshake".to_owned(),
            snapshot_id: None,
            arguments: json!({
                "supervisor_protocol_version": WORKER_PROTOCOL_VERSION,
                "expected_package_version": self.config.expected_package_version,
                "service_config": {
                    "authorized_source_roots": roots,
                    "parser_version": service.parser_version,
                    "pricing_version": service.pricing_version,
                    "pricing_digest": service.pricing_digest,
                    "formatter_version": service.formatter_version,
                    "formatter_digest": service.formatter_digest,
                    "default_page_size": service.default_page_size,
                    "max_page_size": service.max_page_size,
                    "max_heatmap_cells": service.max_heatmap_cells,
                }
            })
            .as_object()
            .expect("handshake arguments are an object")
            .clone(),
        };
        self.write_json_line(&request)
    }

    fn submit(
        &mut self,
        request: TrustedWorkerRequest,
        observer: Arc<dyn OperationObserver>,
    ) -> Result<(), SupervisorError> {
        if self.state.lifecycle != SupervisorState::Ready {
            return Err(SupervisorError::InvalidState {
                expected: SupervisorState::Ready,
                actual: self.state.lifecycle,
            });
        }
        let operation_id = request.envelope.operation_id.clone();
        if self.state.used_operation_ids.contains(&operation_id) {
            return Err(SupervisorError::DuplicateOperation { operation_id });
        }
        if self.state.operations.len() >= self.config.max_in_flight {
            return Err(SupervisorError::Busy {
                maximum: self.config.max_in_flight,
            });
        }
        let operation = request.envelope.operation.clone();
        let snapshot_id = request.envelope.snapshot_id.clone();
        let arguments = request.envelope.arguments.clone();
        let encoded = encode_json_line(&request.envelope, self.config.max_record_bytes)?;
        self.state.used_operation_ids.insert(operation_id.clone());
        self.state.operations.insert(
            operation_id.clone(),
            ActiveOperation {
                operation,
                snapshot_id,
                arguments,
                observer,
                progress: ProgressCoalescer::new(Duration::ZERO),
            },
        );
        if let Err(error) = self.write_encoded_line(&encoded) {
            self.handle_generation_failure(RestartReason::ProtocolFailure, error.clone());
            return Err(error);
        }
        let _consumed_grant = request.output_grant;
        Ok(())
    }

    fn cancel(&mut self, operation_id: String) -> Result<(), SupervisorError> {
        if !self.state.operations.contains_key(&operation_id) {
            return Err(SupervisorError::OperationNotActive { operation_id });
        }
        if self.state.grace_deadlines.contains_key(&operation_id) {
            return Ok(());
        }
        let request = CancelEnvelope {
            protocol_version: WORKER_PROTOCOL_VERSION,
            operation_id: operation_id.clone(),
            record_type: CancelRecordType::Cancel,
        };
        self.write_json_line(&request)?;
        let deadline = Instant::now() + self.config.cancellation_grace;
        self.state
            .grace_deadlines
            .insert(operation_id.clone(), deadline);
        let commands = self.commands.clone();
        let generation_id = self.state.generation_id;
        let delay = self.config.cancellation_grace;
        let timer_operation_id = operation_id.clone();
        if let Err(error) = thread::Builder::new()
            .name(format!("agent-report-worker-cancel-{generation_id}"))
            .spawn(move || {
                thread::sleep(delay);
                let _ = commands.send(SupervisorCommand::GraceExpired {
                    generation_id,
                    operation_id: timer_operation_id,
                });
            })
            .map_err(|_| SupervisorError::Spawn {
                message: "unable to start cancellation timer".to_owned(),
            })
        {
            self.state.grace_deadlines.remove(&operation_id);
            self.handle_generation_failure(RestartReason::ProtocolFailure, error.clone());
            return Err(error);
        }
        Ok(())
    }

    fn restart(&mut self, reason: RestartReason, reply: SyncSender<Result<(), SupervisorError>>) {
        match self.state.lifecycle {
            SupervisorState::Starting if self.state.active_recovery.is_some() => {
                self.state.restart_waiters.push(reply);
            }
            SupervisorState::Ready | SupervisorState::Failed => {
                self.state.restart_waiters.push(reply);
                let error = SupervisorError::RestartFailed {
                    message: format!("worker generation replaced after {reason:?}"),
                };
                self.begin_recovery(error);
            }
            actual => send_reply(
                reply,
                Err(SupervisorError::InvalidState {
                    expected: SupervisorState::Ready,
                    actual,
                }),
            ),
        }
    }

    fn handle_worker_record(&mut self, record: WorkerWireRecord) {
        if self.state.lifecycle == SupervisorState::Starting {
            self.handle_handshake(record);
            return;
        }
        if self.state.lifecycle != SupervisorState::Ready {
            return;
        }
        let operation_id = worker_record_operation_id(&record).to_owned();
        let Some(active) = self.state.operations.get(&operation_id) else {
            self.handle_generation_failure(
                RestartReason::ProtocolFailure,
                protocol_error("REPORT_WORKER_PROTOCOL", "unknown operation record"),
            );
            return;
        };
        if worker_record_operation(&record) != active.operation
            || worker_record_snapshot_id(&record) != active.snapshot_id.as_deref()
        {
            self.handle_generation_failure(
                RestartReason::ProtocolFailure,
                protocol_error("REPORT_WORKER_PROTOCOL", "record correlation mismatch"),
            );
            return;
        }
        if let WorkerWireRecord::Result(value) = &record
            && active.operation == "query_snapshot_time_range"
            && let Err(error) = validate_snapshot_heatmap_result(
                active.snapshot_id.as_deref(),
                &active.arguments,
                &value.result,
            )
        {
            self.handle_generation_failure(RestartReason::ProtocolFailure, error);
            return;
        }
        match record {
            WorkerWireRecord::Progress(value) => {
                let Some(active) = self.state.operations.get_mut(&operation_id) else {
                    return;
                };
                let decision = active.progress.observe(value, Instant::now());
                match decision {
                    Ok(ProgressDecision::Emit(value)) => {
                        let observer = active.observer.clone();
                        invoke_observer(move || observer.on_progress(value));
                    }
                    Ok(ProgressDecision::Pending | ProgressDecision::Ignored) => {}
                    Err(error) => {
                        self.handle_generation_failure(RestartReason::ProtocolFailure, error)
                    }
                }
            }
            WorkerWireRecord::Result(value) => {
                self.complete_operation(&operation_id, HostTerminalOutcome::Result(value));
            }
            WorkerWireRecord::Error(value) => {
                self.complete_operation(&operation_id, HostTerminalOutcome::Error(value));
            }
            WorkerWireRecord::Cancelled(value) => {
                let outcome = HostCancelledOutcome {
                    operation_id: value.operation_id,
                    operation: value.operation,
                    snapshot_id: value.snapshot_id,
                    error: value.error,
                    forced: false,
                };
                self.complete_operation(&operation_id, HostTerminalOutcome::Cancelled(outcome));
            }
        }
    }

    fn handle_handshake(&mut self, record: WorkerWireRecord) {
        let WorkerWireRecord::Result(result) = record else {
            self.fail_startup(protocol_error(
                "REPORT_WORKER_STARTUP_FAILED",
                "unexpected startup record",
            ));
            return;
        };
        if result.operation_id != HANDSHAKE_OPERATION_ID
            || result.operation != "worker_handshake"
            || result.snapshot_id.is_some()
            || result.result.len() != 2
        {
            self.fail_startup(protocol_error(
                "REPORT_WORKER_STARTUP_FAILED",
                "invalid startup result",
            ));
            return;
        }
        let actual_protocol = result
            .result
            .get("worker_protocol_version")
            .and_then(Value::as_u64)
            .and_then(|value| u32::try_from(value).ok());
        let actual_package = result
            .result
            .get("worker_package_version")
            .and_then(Value::as_str);
        let (Some(actual_protocol), Some(actual_package)) = (actual_protocol, actual_package)
        else {
            self.fail_startup(protocol_error(
                "REPORT_WORKER_STARTUP_FAILED",
                "invalid startup version fields",
            ));
            return;
        };
        if actual_protocol != WORKER_PROTOCOL_VERSION
            || actual_package != self.config.expected_package_version
        {
            self.fail_startup(SupervisorError::VersionMismatch {
                expected_protocol: WORKER_PROTOCOL_VERSION,
                actual_protocol,
                expected_package: self.config.expected_package_version.clone(),
                actual_package: actual_package.to_owned(),
            });
            return;
        }
        self.state.lifecycle = SupervisorState::Ready;
        if let Some(recovery) = self.state.active_recovery {
            debug_assert_eq!(recovery.target_generation, self.state.generation_id);
            debug_assert!(recovery.source_generation < recovery.target_generation);
        }
        self.state.active_recovery = None;
        complete_waiters(&mut self.state.startup_waiters, Ok(()));
        complete_waiters(&mut self.state.restart_waiters, Ok(()));
    }

    fn complete_operation(&mut self, operation_id: &str, outcome: HostTerminalOutcome) {
        self.state.grace_deadlines.remove(operation_id);
        if let Some(active) = self.state.operations.remove(operation_id) {
            let observer = active.observer;
            invoke_observer(move || observer.on_terminal(outcome));
        }
    }

    fn force_cancel(&mut self, operation_id: String) {
        let target = self.state.operations.remove(&operation_id);
        self.state.grace_deadlines.clear();
        if let Some(active) = target {
            let outcome = HostTerminalOutcome::Cancelled(HostCancelledOutcome {
                operation_id: operation_id.clone(),
                operation: active.operation,
                snapshot_id: active.snapshot_id,
                error: structured_host_error(
                    "REPORT_WORKER_TERMINATED",
                    "Worker was terminated after cancellation grace expired.",
                    &operation_id,
                ),
                forced: true,
            });
            let observer = active.observer;
            invoke_observer(move || observer.on_terminal(outcome));
        }
        self.begin_recovery(SupervisorError::RestartFailed {
            message: "worker generation ended after forced cancellation".to_owned(),
        });
    }

    fn handle_generation_failure(&mut self, _reason: RestartReason, error: SupervisorError) {
        match self.state.lifecycle {
            SupervisorState::Starting => self.fail_startup(error),
            SupervisorState::Ready => self.begin_recovery(error),
            _ => {}
        }
    }

    fn begin_recovery(&mut self, error: SupervisorError) {
        if self.state.active_recovery.is_some() {
            return;
        }
        let source_generation = self.state.generation_id;
        let target_generation = source_generation.saturating_add(1);
        self.state.active_recovery = Some(RecoveryAttempt {
            source_generation,
            target_generation,
        });
        self.state.lifecycle = SupervisorState::Failed;
        self.fail_active_operations(&error);
        if let Err(termination_error) = self.stop_process() {
            self.state.active_recovery = None;
            complete_waiters(
                &mut self.state.startup_waiters,
                Err(termination_error.clone()),
            );
            complete_waiters(&mut self.state.restart_waiters, Err(termination_error));
            return;
        }
        self.state.generation_id = target_generation;
        if let Err(start_error) = self.start_generation() {
            self.state.lifecycle = SupervisorState::Failed;
            self.state.active_recovery = None;
            complete_waiters(&mut self.state.startup_waiters, Err(start_error.clone()));
            complete_waiters(&mut self.state.restart_waiters, Err(start_error));
        }
    }

    fn fail_startup(&mut self, error: SupervisorError) {
        self.state.lifecycle = SupervisorState::Failed;
        self.state.active_recovery = None;
        let _ = self.stop_process();
        complete_waiters(&mut self.state.startup_waiters, Err(error.clone()));
        complete_waiters(&mut self.state.restart_waiters, Err(error));
    }

    fn fail_active_operations(&mut self, _cause: &SupervisorError) {
        let active = std::mem::take(&mut self.state.operations);
        self.state.grace_deadlines.clear();
        for (operation_id, operation) in active {
            let error = ErrorEnvelope {
                protocol_version: WORKER_PROTOCOL_VERSION,
                operation_id: operation_id.clone(),
                operation: operation.operation,
                snapshot_id: operation.snapshot_id,
                ok: false,
                error: structured_host_error(
                    "REPORT_WORKER_RESTARTED",
                    "Worker restarted before the operation completed.",
                    &operation_id,
                ),
            };
            let observer = operation.observer;
            invoke_observer(move || observer.on_terminal(HostTerminalOutcome::Error(error)));
        }
    }

    fn shutdown(&mut self) -> Result<(), SupervisorError> {
        self.state.lifecycle = SupervisorState::Stopping;
        self.fail_active_operations(&SupervisorError::CoordinatorClosed);
        let result = self.stop_process();
        self.state.lifecycle = SupervisorState::Stopped;
        complete_waiters(
            &mut self.state.startup_waiters,
            Err(SupervisorError::InvalidState {
                expected: SupervisorState::Ready,
                actual: SupervisorState::Stopping,
            }),
        );
        complete_waiters(
            &mut self.state.restart_waiters,
            Err(SupervisorError::InvalidState {
                expected: SupervisorState::Ready,
                actual: SupervisorState::Stopping,
            }),
        );
        result
    }

    fn write_json_line(&mut self, value: &impl Serialize) -> Result<(), SupervisorError> {
        let encoded = encode_json_line(value, self.config.max_record_bytes)?;
        self.write_encoded_line(&encoded)
    }

    fn write_encoded_line(&mut self, encoded: &[u8]) -> Result<(), SupervisorError> {
        let stdin = self
            .state
            .process
            .as_mut()
            .and_then(|process| process.stdin.as_mut())
            .ok_or_else(|| SupervisorError::Io {
                phase: "stdin",
                message: "worker input is unavailable".to_owned(),
            })?;
        stdin
            .write_all(encoded)
            .and_then(|()| stdin.flush())
            .map_err(|_| SupervisorError::Io {
                phase: "stdin",
                message: "unable to write worker request".to_owned(),
            })
    }

    fn stop_process(&mut self) -> Result<(), SupervisorError> {
        let Some(mut process) = self.state.process.take() else {
            return Ok(());
        };
        process.stdin.take();
        let termination = force_terminate_process_tree(&process.tree);
        let waited =
            process
                .child
                .wait()
                .map(|_| ())
                .map_err(|_| SupervisorError::ProcessTermination {
                    process_id: process.tree.process_id(),
                    message: "unable to reap worker process".to_owned(),
                });
        termination.and(waited)
    }

    fn poll_process_exit(&mut self) {
        if !matches!(
            self.state.lifecycle,
            SupervisorState::Starting | SupervisorState::Ready
        ) {
            return;
        }
        let status = self
            .state
            .process
            .as_mut()
            .and_then(|process| process.child.try_wait().ok())
            .flatten();
        if let Some(status) = status {
            self.handle_command(SupervisorCommand::ProcessExited {
                generation_id: self.state.generation_id,
                exit_code: status.code(),
            });
        }
    }
}

fn worker_record_operation_id(record: &WorkerWireRecord) -> &str {
    match record {
        WorkerWireRecord::Progress(value) => &value.operation_id,
        WorkerWireRecord::Result(value) => &value.operation_id,
        WorkerWireRecord::Error(value) => &value.operation_id,
        WorkerWireRecord::Cancelled(value) => &value.operation_id,
    }
}

fn worker_record_operation(record: &WorkerWireRecord) -> &str {
    match record {
        WorkerWireRecord::Progress(value) => &value.operation,
        WorkerWireRecord::Result(value) => &value.operation,
        WorkerWireRecord::Error(value) => &value.operation,
        WorkerWireRecord::Cancelled(value) => &value.operation,
    }
}

fn worker_record_snapshot_id(record: &WorkerWireRecord) -> Option<&str> {
    match record {
        WorkerWireRecord::Progress(value) => value.snapshot_id.as_deref(),
        WorkerWireRecord::Result(value) => value.snapshot_id.as_deref(),
        WorkerWireRecord::Error(value) => value.snapshot_id.as_deref(),
        WorkerWireRecord::Cancelled(value) => value.snapshot_id.as_deref(),
    }
}

fn structured_host_error(code: &str, message: &str, operation_id: &str) -> StructuredError {
    StructuredError {
        code: code.to_owned(),
        message: message.to_owned(),
        operation_id: Some(operation_id.to_owned()),
        recoverable: true,
        current_source_revision: None,
        preflight_required: false,
        restart_from_first_page: false,
    }
}

fn encode_json_line(value: &impl Serialize, maximum: usize) -> Result<Vec<u8>, SupervisorError> {
    let mut encoded = serde_json::to_vec(value).map_err(|_| {
        protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "unable to serialize worker request",
        )
    })?;
    encoded.push(b'\n');
    if encoded.len() > maximum {
        return Err(protocol_error(
            "REPORT_WORKER_PROTOCOL",
            "worker request is too large",
        ));
    }
    Ok(encoded)
}

fn send_reply(reply: SyncSender<Result<(), SupervisorError>>, result: Result<(), SupervisorError>) {
    let _ = reply.send(result);
}

fn complete_waiters(
    waiters: &mut Vec<SyncSender<Result<(), SupervisorError>>>,
    result: Result<(), SupervisorError>,
) {
    for waiter in std::mem::take(waiters) {
        let _ = waiter.send(result.clone());
    }
}

fn invoke_observer(callback: impl FnOnce()) {
    let _ = std::panic::catch_unwind(std::panic::AssertUnwindSafe(callback));
}

fn validate_static_configuration(
    launch: &mut WorkerLaunchSpec,
    config: &mut WorkerSupervisorConfig,
) -> Result<(), SupervisorError> {
    if !(1..=64).contains(&config.max_in_flight) {
        return Err(invalid_config("max_in_flight", "must be between 1 and 64"));
    }
    for (field, value) in [
        ("cancellation_grace", config.cancellation_grace),
        ("startup_timeout", config.startup_timeout),
    ] {
        if value.is_zero() || value > Duration::from_secs(60) {
            return Err(invalid_config(
                field,
                "must be positive and at most 60 seconds",
            ));
        }
    }
    if !(MIN_RECORD_BYTES..=MAX_WORKER_RECORD_BYTES).contains(&config.max_record_bytes) {
        return Err(invalid_config(
            "max_record_bytes",
            "must be between 4096 and 1048576",
        ));
    }
    if !(MIN_RECORD_BYTES..=MAX_WORKER_RECORD_BYTES).contains(&config.max_stderr_bytes) {
        return Err(invalid_config(
            "max_stderr_bytes",
            "must be between 4096 and 1048576",
        ));
    }
    if config.expected_package_version.is_empty()
        || config.service_configuration.parser_version.is_empty()
        || config.service_configuration.pricing_version.is_empty()
        || config.service_configuration.pricing_digest.is_empty()
        || config.service_configuration.formatter_version.is_empty()
        || config.service_configuration.formatter_digest.is_empty()
        || config.service_configuration.default_page_size == 0
        || config.service_configuration.default_page_size
            > config.service_configuration.max_page_size
        || config.service_configuration.max_heatmap_cells == 0
    {
        return Err(invalid_config(
            "service_configuration",
            "contains an empty version or invalid limit",
        ));
    }
    if !launch.executable.is_absolute() {
        return Err(SupervisorError::PathNotAuthorized {
            kind: PathKind::WorkerExecutable,
        });
    }
    let executable =
        fs::canonicalize(&launch.executable).map_err(|_| SupervisorError::PathNotAuthorized {
            kind: PathKind::WorkerExecutable,
        })?;
    if !fs::metadata(&executable).is_ok_and(|metadata| metadata.is_file()) {
        return Err(SupervisorError::PathNotAuthorized {
            kind: PathKind::WorkerExecutable,
        });
    }
    launch.executable = executable;

    if config.path_authority.source_roots.is_empty() {
        return Err(invalid_config("source_roots", "must not be empty"));
    }
    let mut roots = Vec::with_capacity(config.path_authority.source_roots.len());
    let mut seen = HashSet::new();
    for root in &config.path_authority.source_roots {
        if !root.is_absolute() {
            return Err(SupervisorError::PathNotAuthorized {
                kind: PathKind::Source,
            });
        }
        let canonical = fs::canonicalize(root).map_err(|_| SupervisorError::PathNotAuthorized {
            kind: PathKind::Source,
        })?;
        if !fs::metadata(&canonical).is_ok_and(|metadata| metadata.is_dir())
            || !seen.insert(canonical.clone())
        {
            return Err(SupervisorError::PathNotAuthorized {
                kind: PathKind::Source,
            });
        }
        roots.push(canonical);
    }
    config.path_authority.source_roots = roots;
    Ok(())
}

fn invalid_config(field: &'static str, message: &'static str) -> SupervisorError {
    SupervisorError::InvalidConfiguration {
        field,
        message: message.to_owned(),
    }
}

fn canonicalize_nonexistent_target(target: &Path) -> Result<PathBuf, SupervisorError> {
    if !target.is_absolute()
        || target
            .components()
            .any(|component| matches!(component, Component::ParentDir))
    {
        return Err(SupervisorError::PathNotAuthorized {
            kind: PathKind::OutputTarget,
        });
    }
    let mut existing = target;
    let mut suffix = Vec::new();
    while !existing.exists() {
        let name = existing
            .file_name()
            .ok_or(SupervisorError::PathNotAuthorized {
                kind: PathKind::OutputTarget,
            })?;
        suffix.push(name.to_os_string());
        existing = existing
            .parent()
            .ok_or(SupervisorError::PathNotAuthorized {
                kind: PathKind::OutputTarget,
            })?;
    }
    if fs::symlink_metadata(existing).is_ok_and(|metadata| metadata.file_type().is_symlink()) {
        return Err(SupervisorError::PathNotAuthorized {
            kind: PathKind::OutputTarget,
        });
    }
    let mut canonical =
        fs::canonicalize(existing).map_err(|_| SupervisorError::PathNotAuthorized {
            kind: PathKind::OutputTarget,
        })?;
    for component in suffix.into_iter().rev() {
        canonical.push(component);
    }
    Ok(canonical)
}

#[cfg(unix)]
fn spawn_owned_process(launch: &WorkerLaunchSpec) -> Result<OwnedProcess, SupervisorError> {
    use std::os::unix::process::CommandExt;

    let mut command = Command::new(&launch.executable);
    command
        .args(&launch.arguments)
        .envs(&launch.environment)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .process_group(0);
    let mut child = command.spawn().map_err(|_| SupervisorError::Spawn {
        message: "unable to start worker executable".to_owned(),
    })?;
    let process_id = child.id();
    let process_group_id = unsafe { unix_process::getpgid(process_id as i32) };
    if process_group_id <= 0 || process_group_id != process_id as i32 {
        let _ = child.kill();
        let _ = child.wait();
        return Err(SupervisorError::ProcessOwnership {
            platform: "unix",
            message: "worker did not enter its own process group".to_owned(),
        });
    }
    let stdin = child.stdin.take().ok_or_else(|| SupervisorError::Spawn {
        message: "worker stdin pipe is unavailable".to_owned(),
    })?;
    Ok(OwnedProcess {
        child,
        stdin: Some(stdin),
        tree: ProcessTreeHandle {
            process_id,
            process_group_id,
        },
    })
}

#[cfg(windows)]
fn spawn_owned_process(_launch: &WorkerLaunchSpec) -> Result<OwnedProcess, SupervisorError> {
    // Rust's standard Command API cannot suspend a process before Job Object assignment.
    // The accepted Cargo integration adds windows-sys for that atomic creation sequence.
    Err(SupervisorError::ProcessOwnership {
        platform: "windows",
        message: "suspended Job Object launch requires the accepted target dependency".to_owned(),
    })
}

#[cfg(not(any(unix, windows)))]
fn spawn_owned_process(_launch: &WorkerLaunchSpec) -> Result<OwnedProcess, SupervisorError> {
    Err(SupervisorError::ProcessOwnership {
        platform: "unsupported",
        message: "no owned process-tree implementation is available".to_owned(),
    })
}

fn spawn_stdout_reader(
    generation_id: u64,
    stdout: impl Read + Send + 'static,
    maximum: usize,
    commands: SyncSender<SupervisorCommand>,
) -> Result<(), SupervisorError> {
    thread::Builder::new()
        .name(format!("agent-report-worker-stdout-{generation_id}"))
        .spawn(move || read_worker_stdout(generation_id, stdout, maximum, commands))
        .map(|_| ())
        .map_err(|_| SupervisorError::Spawn {
            message: "unable to start worker stdout reader".to_owned(),
        })
}

fn cleanup_failed_spawn(process: &mut OwnedProcess) {
    process.stdin.take();
    let _ = force_terminate_process_tree(&process.tree);
    let _ = process.child.wait();
}

fn read_worker_stdout(
    generation_id: u64,
    mut stdout: impl Read,
    maximum: usize,
    commands: SyncSender<SupervisorCommand>,
) {
    let mut line = Vec::with_capacity(maximum.min(16 * 1024));
    let mut byte = [0_u8; 1];
    loop {
        match stdout.read(&mut byte) {
            Ok(0) if line.is_empty() => {
                let _ = commands.send(SupervisorCommand::WorkerEof { generation_id });
                return;
            }
            Ok(0) => {
                let _ = commands.send(SupervisorCommand::WorkerProtocolFailure {
                    generation_id,
                    error: protocol_error("REPORT_WORKER_PROTOCOL", "partial record at EOF"),
                });
                return;
            }
            Ok(_) => {
                line.push(byte[0]);
                if line.len() > maximum {
                    let _ = commands.send(SupervisorCommand::WorkerProtocolFailure {
                        generation_id,
                        error: protocol_error(
                            "REPORT_WORKER_PROTOCOL",
                            "worker record is too large",
                        ),
                    });
                    return;
                }
                if byte[0] == b'\n' {
                    match parse_worker_record(&line, maximum) {
                        Ok(record) => {
                            if commands
                                .send(SupervisorCommand::WorkerRecord {
                                    generation_id,
                                    record,
                                })
                                .is_err()
                            {
                                return;
                            }
                            line.clear();
                        }
                        Err(error) => {
                            let _ = commands.send(SupervisorCommand::WorkerProtocolFailure {
                                generation_id,
                                error,
                            });
                            return;
                        }
                    }
                }
            }
            Err(_) => {
                let _ = commands.send(SupervisorCommand::WorkerProtocolFailure {
                    generation_id,
                    error: SupervisorError::Io {
                        phase: "stdout",
                        message: "unable to read worker output".to_owned(),
                    },
                });
                return;
            }
        }
    }
}

fn spawn_stderr_reader(
    mut stderr: impl Read + Send + 'static,
    maximum: usize,
    diagnostic_sink: Option<Arc<dyn Fn(SanitizedDiagnostic) + Send + Sync>>,
) -> Result<(), SupervisorError> {
    thread::Builder::new()
        .name("agent-report-worker-stderr".to_owned())
        .spawn(move || {
            let mut sanitizer = StderrSanitizer::new(maximum);
            let mut buffer = [0_u8; 1024];
            loop {
                match stderr.read(&mut buffer) {
                    Ok(0) | Err(_) => return,
                    Ok(count) => {
                        for diagnostic in sanitizer.ingest(&buffer[..count]) {
                            if let Some(sink) = diagnostic_sink.as_ref() {
                                let sink = Arc::clone(sink);
                                invoke_observer(move || sink(diagnostic));
                            }
                        }
                    }
                }
            }
        })
        .map(|_| ())
        .map_err(|_| SupervisorError::Spawn {
            message: "unable to start worker stderr reader".to_owned(),
        })
}

impl ProcessTreeHandle {
    fn process_id(&self) -> u32 {
        self.process_id
    }
}

/// Force termination of only the verified process tree owned by this Supervisor.
#[cfg(unix)]
pub fn force_terminate_process_tree(tree: &ProcessTreeHandle) -> Result<(), SupervisorError> {
    if tree.process_group_id <= 0 || tree.process_group_id != tree.process_id as i32 {
        return Err(SupervisorError::ProcessOwnership {
            platform: "unix",
            message: "stored process group is not the worker-owned group".to_owned(),
        });
    }
    let result = unsafe { unix_process::kill(-tree.process_group_id, unix_process::SIGKILL) };
    if result == 0 {
        return Ok(());
    }
    let error = std::io::Error::last_os_error();
    if error.raw_os_error() == Some(unix_process::ESRCH) {
        Ok(())
    } else {
        Err(SupervisorError::ProcessTermination {
            process_id: tree.process_id,
            message: "unable to signal owned process group".to_owned(),
        })
    }
}

#[cfg(unix)]
mod unix_process {
    pub const SIGKILL: i32 = 9;
    pub const ESRCH: i32 = 3;

    unsafe extern "C" {
        pub fn getpgid(process_id: i32) -> i32;
        pub fn kill(process_or_group: i32, signal: i32) -> i32;
    }
}

/// Force termination of only the Windows Job Object owned by this Supervisor.
#[cfg(windows)]
pub fn force_terminate_process_tree(tree: &ProcessTreeHandle) -> Result<(), SupervisorError> {
    use std::os::windows::io::AsRawHandle;

    const WAIT_OBJECT_0: u32 = 0;
    const WAIT_MILLISECONDS: u32 = 30_000;
    let terminated = unsafe { windows_job::TerminateJobObject(tree.job.as_raw_handle(), 1) };
    let waited = unsafe {
        windows_job::WaitForSingleObject(tree.process.as_raw_handle(), WAIT_MILLISECONDS)
    };
    if terminated != 0 && waited == WAIT_OBJECT_0 {
        Ok(())
    } else {
        Err(SupervisorError::ProcessTermination {
            process_id: tree.process_id,
            message: "unable to terminate and reap owned Job Object".to_owned(),
        })
    }
}

#[cfg(windows)]
mod windows_job {
    use std::ffi::c_void;

    #[link(name = "kernel32")]
    unsafe extern "system" {
        pub fn TerminateJobObject(job: *mut c_void, exit_code: u32) -> i32;
        pub fn WaitForSingleObject(handle: *mut c_void, milliseconds: u32) -> u32;
    }
}

#[cfg(not(any(unix, windows)))]
pub fn force_terminate_process_tree(_tree: &ProcessTreeHandle) -> Result<(), SupervisorError> {
    Err(SupervisorError::ProcessOwnership {
        platform: "unsupported",
        message: "no process-tree termination implementation is available".to_owned(),
    })
}

#[cfg(test)]
mod heatmap_contract_tests {
    use super::*;
    use chrono::{Duration as ChronoDuration, SecondsFormat, Utc};

    const SNAPSHOT_ID: &str = "snap_46b9630e96ce4dc5a678a517";

    fn matrix_arguments() -> Map<String, Value> {
        json!({
            "query_kind": "matrix",
            "from_time": "2026-08-12T12:00:00Z",
            "to_time": "2026-08-14T00:00:00Z",
            "mode": "tokens",
            "requested_resolution_minutes": 1,
            "maximum_rows": 1
        })
        .as_object()
        .expect("matrix arguments")
        .clone()
    }

    fn evidence_arguments() -> Map<String, Value> {
        json!({
            "query_kind": "cell_evidence",
            "mode": "tokens",
            "row_id": "token:uncached_input",
            "period_start_time": "2026-08-12T12:00:00Z",
            "period_end_time": "2026-08-12T12:05:00Z"
        })
        .as_object()
        .expect("evidence arguments")
        .clone()
    }

    fn matrix_result(cell_count: usize) -> Map<String, Value> {
        let start = DateTime::parse_from_rfc3339("2026-08-12T12:00:00Z")
            .expect("fixture start")
            .with_timezone(&Utc);
        let cells = (0..cell_count)
            .map(|offset| {
                let cell_start = start + ChronoDuration::minutes(offset as i64);
                let cell_end = cell_start + ChronoDuration::minutes(1);
                json!({
                    "start_time": cell_start.to_rfc3339_opts(SecondsFormat::Secs, true),
                    "end_time": cell_end.to_rfc3339_opts(SecondsFormat::Secs, true),
                    "value": 0.0,
                    "formatted_value": "0",
                    "value_state": "measured",
                    "applicable_zero": true,
                    "contributing_evidence_count": 0,
                    "normalized_intensity": 0.0,
                    "supporting_text": null
                })
            })
            .collect::<Vec<_>>();
        json!({
            "snapshot_id": SNAPSHOT_ID,
            "revision_id": "revision-1",
            "query_kind": "matrix",
            "mode": "tokens",
            "from_time": "2026-08-12T12:00:00Z",
            "to_time": "2026-08-14T00:00:00Z",
            "requested_resolution_minutes": 1,
            "actual_resolution_minutes": 1,
            "maximum_rows": 1,
            "omitted_row_count": 0,
            "row_order": "token_contract",
            "total_cell_count": cell_count,
            "rows": [{
                "row_id": "token:uncached_input",
                "row_key": "uncached_input_tokens",
                "row_order_index": 0,
                "row_kind": "token_measure",
                "label": "Uncached input",
                "scale": {
                    "availability": "available",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "basis": "visible_row_maximum"
                },
                "cells": cells
            }],
            "provenance": ["normalized events"]
        })
        .as_object()
        .expect("matrix result")
        .clone()
    }

    fn evidence_result(item_count: usize) -> Map<String, Value> {
        let start = DateTime::parse_from_rfc3339("2026-08-12T12:00:00Z")
            .expect("fixture start")
            .with_timezone(&Utc);
        let items = (0..item_count)
            .map(|offset| {
                json!({
                    "event_id": null,
                    "occurred_at": (start + ChronoDuration::seconds(offset as i64))
                        .to_rfc3339_opts(SecondsFormat::Secs, true),
                    "value": null,
                    "formatted_value": "Unavailable",
                    "duration_ms": null,
                    "label": "main · gpt-5 · high",
                    "preview": "x".repeat(4096),
                    "evidence_method": "unavailable",
                    "value_state": "unavailable",
                    "has_detail": false
                })
            })
            .collect::<Vec<_>>();
        json!({
            "snapshot_id": SNAPSHOT_ID,
            "revision_id": "revision-1",
            "query_kind": "cell_evidence",
            "mode": "tokens",
            "row_id": "token:uncached_input",
            "row_key": "uncached_input_tokens",
            "row_order_index": 0,
            "row_label": "Uncached input",
            "period_start_time": "2026-08-12T12:00:00Z",
            "period_end_time": "2026-08-12T12:05:00Z",
            "value": 1.0,
            "formatted_value": "1",
            "value_state": "measured",
            "applicable_zero": false,
            "evidence_items": items,
            "omitted_evidence_count": 17,
            "provenance": ["normalized events"]
        })
        .as_object()
        .expect("evidence result")
        .clone()
    }

    fn maximal_matrix_result() -> Map<String, Value> {
        let start = DateTime::parse_from_rfc3339("2026-08-12T12:00:00Z")
            .expect("fixture start")
            .with_timezone(&Utc);
        let formatted = "\\".repeat(MAX_HEATMAP_FORMATTED_VALUE_ESCAPED_BYTES / 2);
        let supporting = "\\".repeat(MAX_HEATMAP_SUPPORTING_TEXT_ESCAPED_BYTES / 2);
        let label = "\\".repeat(MAX_HEATMAP_LABEL_ESCAPED_BYTES / 2);
        let cells = (0..10)
            .map(|offset| {
                let cell_start = start + ChronoDuration::minutes(offset);
                let cell_end = cell_start + ChronoDuration::minutes(1);
                json!({
                    "start_time": cell_start.to_rfc3339_opts(SecondsFormat::Secs, true),
                    "end_time": cell_end.to_rfc3339_opts(SecondsFormat::Secs, true),
                    "value": u64::MAX,
                    "formatted_value": formatted,
                    "value_state": "measured",
                    "applicable_zero": false,
                    "contributing_evidence_count": u64::MAX,
                    "normalized_intensity": 0.9999999999999999,
                    "supporting_text": supporting
                })
            })
            .collect::<Vec<_>>();
        let rows = (0..MAX_HEATMAP_ROWS)
            .map(|index| {
                json!({
                    "row_id": format!("row_{index:024x}"),
                    "row_key": format!("runtime:{index:03}_{}", "\\".repeat(124)),
                    "row_order_index": index,
                    "row_kind": "runtime_state",
                    "label": label,
                    "scale": {
                        "availability": "available",
                        "minimum": -1.7976931348623157e308_f64,
                        "maximum": 1.7976931348623157e308_f64,
                        "basis": "visible_row_maximum"
                    },
                    "cells": cells
                })
            })
            .collect::<Vec<_>>();
        json!({
            "snapshot_id": SNAPSHOT_ID,
            "revision_id": "revision-1",
            "query_kind": "matrix",
            "mode": "wall_time",
            "from_time": "2026-08-12T12:00:00Z",
            "to_time": "2026-08-12T12:10:00Z",
            "requested_resolution_minutes": 1,
            "actual_resolution_minutes": 1,
            "maximum_rows": MAX_HEATMAP_ROWS,
            "omitted_row_count": 0,
            "row_order": "runtime_state_contract",
            "total_cell_count": MAX_HEATMAP_CELLS,
            "rows": rows,
            "provenance": vec![
                "\\".repeat(MAX_HEATMAP_PROVENANCE_ESCAPED_BYTES / 2);
                MAX_HEATMAP_PROVENANCE_ITEMS
            ]
        })
        .as_object()
        .expect("maximal matrix result")
        .clone()
    }

    fn maximal_evidence_result() -> Map<String, Value> {
        let mut result = evidence_result(MAX_HEATMAP_EVIDENCE_ITEMS);
        result["row_label"] = json!("\\".repeat(MAX_HEATMAP_LABEL_ESCAPED_BYTES / 2));
        result["formatted_value"] =
            json!("\\".repeat(MAX_HEATMAP_FORMATTED_VALUE_ESCAPED_BYTES / 2));
        result["provenance"] = json!(vec![
            "\\".repeat(MAX_HEATMAP_PROVENANCE_ESCAPED_BYTES / 2);
            MAX_HEATMAP_PROVENANCE_ITEMS
        ]);
        for (index, item) in result["evidence_items"]
            .as_array_mut()
            .expect("evidence items")
            .iter_mut()
            .enumerate()
        {
            item["event_id"] = json!(format!("event_{index:0250}"));
            item["value"] = json!(u64::MAX);
            item["formatted_value"] =
                json!("\\".repeat(MAX_HEATMAP_FORMATTED_VALUE_ESCAPED_BYTES / 2));
            item["duration_ms"] = json!(u64::MAX);
            item["label"] = json!("\\".repeat(MAX_HEATMAP_LABEL_ESCAPED_BYTES / 2));
            item["preview"] = json!("\\".repeat(MAX_HEATMAP_PREVIEW_ESCAPED_BYTES / 2));
            item["evidence_method"] = json!("measured");
            item["value_state"] = json!("measured");
            item["has_detail"] = json!(true);
        }
        result
    }

    fn matrix_envelope(result: Map<String, Value>) -> Value {
        json!({
            "protocol_version": WORKER_PROTOCOL_VERSION,
            "operation_id": "op_75ffcf97671b4ccbaf96790c",
            "type": "result",
            "operation": "query_snapshot_time_range",
            "snapshot_id": SNAPSHOT_ID,
            "ok": true,
            "result": result
        })
    }

    #[test]
    fn validates_exact_heatmap_variants_and_projects_values_losslessly() {
        let matrix = matrix_result(1);
        validate_snapshot_heatmap_result(Some(SNAPSHOT_ID), &matrix_arguments(), &matrix)
            .expect("valid matrix");

        let evidence = evidence_result(1);
        validate_snapshot_heatmap_result(Some(SNAPSHOT_ID), &evidence_arguments(), &evidence)
            .expect("valid evidence");
        let projected = project_snapshot_heatmap_result(evidence).expect("lossless projection");
        assert_eq!(projected["snapshotId"], SNAPSHOT_ID);
        assert_eq!(projected["revisionId"], "revision-1");
        assert!(projected.get("revision").is_none());
        assert_eq!(projected["rowKey"], "uncached_input_tokens");
        assert_eq!(projected["rowOrderIndex"], 0);
        assert_eq!(projected["evidenceItems"][0]["value"], Value::Null);
        assert_eq!(
            projected["evidenceItems"][0]["evidenceMethod"],
            "unavailable"
        );
    }

    #[test]
    fn rejects_cross_variant_scale_and_identity_mismatches() {
        let mut wrong_variant = matrix_result(1);
        wrong_variant.insert("query_kind".to_owned(), json!("cell_evidence"));
        assert!(
            validate_snapshot_heatmap_result(
                Some(SNAPSHOT_ID),
                &matrix_arguments(),
                &wrong_variant,
            )
            .is_err()
        );

        let mut mixed_scale = matrix_result(1);
        mixed_scale["rows"][0]["scale"] = json!({
            "availability": "unavailable",
            "reason": "context_capacity_unavailable",
            "minimum": 0.0
        });
        assert!(
            validate_snapshot_heatmap_result(Some(SNAPSHOT_ID), &matrix_arguments(), &mixed_scale,)
                .is_err()
        );

        let mut wrong_snapshot = matrix_result(1);
        wrong_snapshot.insert("snapshot_id".to_owned(), json!("another-snapshot"));
        assert!(
            validate_snapshot_heatmap_result(
                Some(SNAPSHOT_ID),
                &matrix_arguments(),
                &wrong_snapshot,
            )
            .is_err()
        );

        let mut absent_revision = matrix_result(1);
        absent_revision.remove("revision_id");
        assert!(
            validate_snapshot_heatmap_result(
                Some(SNAPSHOT_ID),
                &matrix_arguments(),
                &absent_revision,
            )
            .is_err()
        );

        let mut fractional_duration = evidence_result(1);
        fractional_duration["evidence_items"][0]["duration_ms"] = json!(1.5);
        assert!(
            validate_snapshot_heatmap_result(
                Some(SNAPSHOT_ID),
                &evidence_arguments(),
                &fractional_duration,
            )
            .is_err()
        );
    }

    #[test]
    fn enforces_heatmap_cardinality_and_compact_record_bounds() {
        let matrix = matrix_result(MAX_HEATMAP_CELLS);
        validate_snapshot_heatmap_result(Some(SNAPSHOT_ID), &matrix_arguments(), &matrix)
            .expect("2,000 cells remain valid");
        let matrix_record = json!({
            "protocol_version": WORKER_PROTOCOL_VERSION,
            "operation_id": "op_75ffcf97671b4ccbaf96790c",
            "type": "result",
            "operation": "query_snapshot_time_range",
            "snapshot_id": SNAPSHOT_ID,
            "ok": true,
            "result": matrix
        });
        assert!(serde_json::to_vec(&matrix_record).unwrap().len() + 1 < MAX_WORKER_RECORD_BYTES);

        let oversized_matrix = matrix_result(MAX_HEATMAP_CELLS + 1);
        assert!(
            validate_snapshot_heatmap_result(
                Some(SNAPSHOT_ID),
                &matrix_arguments(),
                &oversized_matrix,
            )
            .is_err()
        );

        let evidence = evidence_result(MAX_HEATMAP_EVIDENCE_ITEMS);
        validate_snapshot_heatmap_result(Some(SNAPSHOT_ID), &evidence_arguments(), &evidence)
            .expect("100 evidence items remain valid");
        let evidence_record = json!({
            "protocol_version": WORKER_PROTOCOL_VERSION,
            "operation_id": "op_75ffcf97671b4ccbaf96790c",
            "type": "result",
            "operation": "query_snapshot_time_range",
            "snapshot_id": SNAPSHOT_ID,
            "ok": true,
            "result": evidence
        });
        assert!(serde_json::to_vec(&evidence_record).unwrap().len() + 1 < MAX_WORKER_RECORD_BYTES);

        let oversized_evidence = evidence_result(MAX_HEATMAP_EVIDENCE_ITEMS + 1);
        assert!(
            validate_snapshot_heatmap_result(
                Some(SNAPSHOT_ID),
                &evidence_arguments(),
                &oversized_evidence,
            )
            .is_err()
        );
    }

    #[test]
    fn enforces_semantic_row_order_and_scale_correlation() {
        let mut context_matrix = matrix_result(1);
        let row_template = context_matrix["rows"][0].clone();
        let context_rows = TOKEN_ROW_KEYS[..=5]
            .iter()
            .enumerate()
            .map(|(index, row_key)| {
                let mut row = row_template.clone();
                row["row_id"] = json!(format!("row_{index:024x}"));
                row["row_key"] = json!(row_key);
                row["row_order_index"] = json!(index);
                if *row_key == "context_average" {
                    row["scale"] = json!({
                        "availability": "unavailable",
                        "reason": "context_capacity_unavailable"
                    });
                    row["cells"][0]["value"] = Value::Null;
                    row["cells"][0]["formatted_value"] = json!("N/A");
                    row["cells"][0]["value_state"] = json!("unavailable");
                    row["cells"][0]["applicable_zero"] = json!(false);
                    row["cells"][0]["normalized_intensity"] = Value::Null;
                    row["cells"][0]["supporting_text"] = json!("200 tokens observed");
                }
                row
            })
            .collect::<Vec<_>>();
        context_matrix["maximum_rows"] = json!(context_rows.len());
        context_matrix["total_cell_count"] = json!(context_rows.len());
        context_matrix["rows"] = json!(context_rows);
        let mut context_arguments = matrix_arguments();
        context_arguments["maximum_rows"] = json!(6);
        validate_snapshot_heatmap_result(Some(SNAPSHOT_ID), &context_arguments, &context_matrix)
            .expect("valid unavailable context scale and nullable cells");

        let mut skipped_token_prefix = matrix_result(1);
        skipped_token_prefix["rows"][0]["row_key"] = json!("output_tokens");
        assert!(
            validate_snapshot_heatmap_result(
                Some(SNAPSHOT_ID),
                &matrix_arguments(),
                &skipped_token_prefix,
            )
            .is_err()
        );

        let mut noncontiguous_index = matrix_result(1);
        noncontiguous_index["rows"][0]["row_order_index"] = json!(1);
        assert!(
            validate_snapshot_heatmap_result(
                Some(SNAPSHOT_ID),
                &matrix_arguments(),
                &noncontiguous_index,
            )
            .is_err()
        );

        assert!(
            validate_heatmap_scale_for_row("context_average", HeatmapScaleWire::VisibleMaximum,)
                .is_err()
        );
        assert!(
            validate_heatmap_scale_for_row("output_tokens", HeatmapScaleWire::ContextCapacity,)
                .is_err()
        );
        let mut unavailable_context_cell = matrix_result(1)["rows"][0]["cells"][0]
            .as_object()
            .expect("matrix cell")
            .clone();
        unavailable_context_cell["value"] = Value::Null;
        unavailable_context_cell["formatted_value"] = json!("N/A");
        unavailable_context_cell["value_state"] = json!("unavailable");
        unavailable_context_cell["applicable_zero"] = json!(false);
        unavailable_context_cell["normalized_intensity"] = Value::Null;
        unavailable_context_cell["supporting_text"] = json!("200 tokens observed");
        validate_heatmap_cell(
            &unavailable_context_cell,
            HeatmapScaleWire::ContextCapacityUnavailable,
        )
        .expect("valid unavailable context cell");
        unavailable_context_cell["formatted_value"] = json!("50%");
        assert!(
            validate_heatmap_cell(
                &unavailable_context_cell,
                HeatmapScaleWire::ContextCapacityUnavailable,
            )
            .is_err()
        );
        unavailable_context_cell["formatted_value"] = json!("N/A");
        unavailable_context_cell["supporting_text"] = json!("capacity unknown");
        assert!(
            validate_heatmap_cell(
                &unavailable_context_cell,
                HeatmapScaleWire::ContextCapacityUnavailable,
            )
            .is_err()
        );
        assert!(runtime_row_suffix("runtime:").is_err());
        assert!(runtime_row_suffix("runtime:Unknown").is_err());
        assert!(runtime_row_suffix("runtime:model_inference").is_err());
        assert_eq!(
            runtime_row_suffix("runtime:custom state").expect("canonical spaced runtime key"),
            "custom state"
        );
        assert!(runtime_row_suffix("runtime:custom\nstate").is_err());
        let mut custom_runtime_matrix = maximal_matrix_result();
        custom_runtime_matrix["maximum_rows"] = json!(1);
        custom_runtime_matrix["total_cell_count"] = json!(10);
        custom_runtime_matrix["rows"]
            .as_array_mut()
            .expect("runtime rows")
            .truncate(1);
        custom_runtime_matrix["rows"][0]["row_key"] = json!("runtime:custom state");
        let custom_runtime_arguments = json!({
            "query_kind": "matrix",
            "from_time": "2026-08-12T12:00:00Z",
            "to_time": "2026-08-12T12:10:00Z",
            "mode": "wall_time",
            "requested_resolution_minutes": 1,
            "maximum_rows": 1
        })
        .as_object()
        .expect("custom runtime arguments")
        .clone();
        validate_snapshot_heatmap_result(
            Some(SNAPSHOT_ID),
            &custom_runtime_arguments,
            &custom_runtime_matrix,
        )
        .expect("canonical spaced runtime row crosses the Worker boundary");
        assert!(valid_model_row_key("model:0123456789abcdef01234567"));
        assert!(!valid_model_row_key("model:0123456789ABCDEF01234567"));

        let mut wall_order = WallTimeRowOrder::default();
        let mut cost_seen = false;
        validate_heatmap_row_order(
            "wall_time",
            "tool_execution",
            "runtime_state",
            0,
            &mut wall_order,
            &mut cost_seen,
        )
        .expect("known state may be absent from a returned prefix");
        assert!(
            validate_heatmap_row_order(
                "wall_time",
                "model_inference",
                "runtime_state",
                1,
                &mut wall_order,
                &mut cost_seen,
            )
            .is_err()
        );

        let mut runtime_order = WallTimeRowOrder::default();
        validate_heatmap_row_order(
            "wall_time",
            "runtime:beta",
            "runtime_state",
            0,
            &mut runtime_order,
            &mut cost_seen,
        )
        .expect("first unknown runtime state");
        assert!(
            validate_heatmap_row_order(
                "wall_time",
                "runtime:alpha",
                "runtime_state",
                1,
                &mut runtime_order,
                &mut cost_seen,
            )
            .is_err()
        );

        let mut model_order = WallTimeRowOrder::default();
        let mut model_cost_seen = false;
        validate_heatmap_row_order(
            "models",
            "cost",
            "cost",
            0,
            &mut model_order,
            &mut model_cost_seen,
        )
        .expect("cost may be the only returned model row");
        assert!(
            validate_heatmap_row_order(
                "models",
                "model:0123456789abcdef01234567",
                "model",
                1,
                &mut model_order,
                &mut model_cost_seen,
            )
            .is_err()
        );
    }

    #[test]
    fn counts_json_escaped_content_at_exact_and_plus_one_boundaries() {
        for (exact, too_large, maximum) in [
            ("\\".repeat(40), "\\".repeat(40) + "x", 80),
            ("\u{1}".repeat(13) + "xx", "\u{1}".repeat(13) + "xxx", 80),
            ("é".repeat(40), "é".repeat(41), 80),
        ] {
            assert_eq!(json_escaped_content_bytes(&exact), maximum);
            assert!(json_escaped_content_bytes(&too_large) > maximum);
        }

        let mut matrix = matrix_result(1);
        matrix["rows"][0]["cells"][0]["supporting_text"] = json!("\\".repeat(40));
        validate_snapshot_heatmap_result(Some(SNAPSHOT_ID), &matrix_arguments(), &matrix)
            .expect("exact escaped supporting-text boundary");
        matrix["rows"][0]["cells"][0]["supporting_text"] = json!("\\".repeat(40) + "x");
        assert!(
            validate_snapshot_heatmap_result(Some(SNAPSHOT_ID), &matrix_arguments(), &matrix)
                .is_err()
        );

        let mut evidence = evidence_result(1);
        evidence["evidence_items"][0]["preview"] = json!("\u{1}".repeat(682) + "xxxx");
        validate_snapshot_heatmap_result(Some(SNAPSHOT_ID), &evidence_arguments(), &evidence)
            .expect("exact escaped preview boundary");
        evidence["evidence_items"][0]["preview"] = json!("\u{1}".repeat(682) + "xxxxx");
        assert!(
            validate_snapshot_heatmap_result(Some(SNAPSHOT_ID), &evidence_arguments(), &evidence,)
                .is_err()
        );
    }

    #[test]
    fn proves_maximal_heatmap_variants_fit_one_complete_jsonl_record() {
        let matrix = maximal_matrix_result();
        let matrix_arguments = json!({
            "query_kind": "matrix",
            "from_time": "2026-08-12T12:00:00Z",
            "to_time": "2026-08-12T12:10:00Z",
            "mode": "wall_time",
            "requested_resolution_minutes": 1,
            "maximum_rows": MAX_HEATMAP_ROWS
        })
        .as_object()
        .expect("matrix arguments")
        .clone();
        validate_snapshot_heatmap_result(Some(SNAPSHOT_ID), &matrix_arguments, &matrix)
            .expect("maximal 200 by 10 matrix");
        let matrix_bytes = serde_json::to_vec(&matrix_envelope(matrix)).unwrap().len() + 1;
        assert!(matrix_bytes <= MAX_WORKER_RECORD_BYTES, "{matrix_bytes}");

        let evidence = maximal_evidence_result();
        validate_snapshot_heatmap_result(Some(SNAPSHOT_ID), &evidence_arguments(), &evidence)
            .expect("maximal 100-item evidence result");
        let evidence_bytes = serde_json::to_vec(&matrix_envelope(evidence))
            .unwrap()
            .len()
            + 1;
        assert!(
            evidence_bytes <= MAX_WORKER_RECORD_BYTES,
            "{evidence_bytes}"
        );
    }
}
