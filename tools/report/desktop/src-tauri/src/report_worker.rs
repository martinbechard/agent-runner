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

const MIN_RECORD_BYTES: usize = 4_096;
const MAX_MESSAGE_CHARS: usize = 512;
const STDERR_LINE_BYTES: usize = 4_096;
const HANDSHAKE_OPERATION_ID: &str = "op_000000000000000000000000";
const COMMAND_CAPACITY: usize = 128;

/// Non-path Application Service values inserted into the trusted startup handshake.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ServiceConfiguration {
    pub parser_version: String,
    pub pricing_digest: String,
    pub formatter_digest: String,
    pub default_page_size: u16,
    pub max_page_size: u16,
    pub max_time_buckets: u32,
}

/// Canonical roots that the native host authorizes the Worker to read.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PathAuthority {
    pub source_roots: Vec<PathBuf>,
}

/// Static limits and trusted startup values for one Supervisor.
#[derive(Debug, Clone)]
pub struct WorkerSupervisorConfig {
    pub max_in_flight: usize,
    pub cancellation_grace: Duration,
    pub startup_timeout: Duration,
    pub max_record_bytes: usize,
    pub max_stderr_bytes: usize,
    pub expected_package_version: String,
    pub service_configuration: ServiceConfiguration,
    pub path_authority: PathAuthority,
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
    pub message: &'static str,
}

impl SanitizedDiagnostic {
    /// Construct the single fixed record used for rejected child diagnostics.
    pub fn rejected() -> Self {
        Self {
            level: "warning",
            event: "worker.stderr_rejected",
            operation_id: None,
            code: None,
            message: "Worker diagnostic input was rejected.",
        }
    }

    fn limit_reached() -> Self {
        Self {
            level: "warning",
            event: "worker.stderr_limit_reached",
            operation_id: None,
            code: None,
            message: "Worker diagnostic limit was reached.",
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
    let (event, message) = match (value.event.as_str(), code) {
        ("worker.startup_failed", "REPORT_WORKER_STARTUP_FAILED") => {
            ("worker.startup_failed", "Worker startup failed.")
        }
        ("worker.invalid_input", "REPORT_WORKER_INVALID_JSON") => {
            ("worker.invalid_input", "Worker input validation failed.")
        }
        ("worker.invalid_input", "REPORT_WORKER_INVALID_ENVELOPE") => {
            ("worker.invalid_input", "Worker envelope validation failed.")
        }
        ("worker.service_contract", "REPORT_WORKER_SERVICE_CONTRACT") => {
            ("worker.service_contract", "Worker service contract failed.")
        }
        ("worker.internal_failure", "REPORT_WORKER_INTERNAL") => {
            ("worker.internal_failure", "Worker execution failed.")
        }
        ("worker.output_failed", "REPORT_WORKER_OUTPUT_FAILED") => {
            ("worker.output_failed", "Worker protocol output failed.")
        }
        ("worker.shutdown_failed", "REPORT_WORKER_SHUTDOWN_FAILED") => {
            ("worker.shutdown_failed", "Worker shutdown failed.")
        }
        _ => return None,
    };
    let level = match value.level.as_str() {
        "info" => "info",
        "warning" => "warning",
        "error" => "error",
        _ => return None,
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
            exact_keys(arguments, &["scope", "preflight_token"])?;
            validate_scope(object_field(arguments, "scope")?)?;
            string_field(arguments, "preflight_token")?;
            Ok(())
        }
        "get_summary" | "refresh_snapshot" | "close_snapshot" => exact_keys(arguments, &[]),
        "list_agents" => {
            exact_keys(arguments, &["filters", "cursor", "page_size"])?;
            validate_string_array_object(
                object_field(arguments, "filters")?,
                &["agent_ids", "roles", "states"],
            )?;
            nullable_string_field(arguments, "cursor")?;
            unsigned_field(arguments, "page_size")?;
            Ok(())
        }
        "list_turns" => {
            exact_keys(arguments, &["filters", "cursor", "page_size"])?;
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
            nullable_string_field(arguments, "cursor")?;
            unsigned_field(arguments, "page_size")?;
            Ok(())
        }
        "list_events" => {
            exact_keys(arguments, &["filters", "cursor", "page_size"])?;
            validate_event_filters(object_field(arguments, "filters")?)?;
            nullable_string_field(arguments, "cursor")?;
            unsigned_field(arguments, "page_size")?;
            Ok(())
        }
        "query_time_range" => {
            exact_keys(
                arguments,
                &[
                    "from_time",
                    "to_time",
                    "measure",
                    "requested_resolution_minutes",
                ],
            )?;
            string_field(arguments, "from_time")?;
            string_field(arguments, "to_time")?;
            string_field(arguments, "measure")?;
            unsigned_field(arguments, "requested_resolution_minutes")?;
            Ok(())
        }
        "query_sequence" => {
            exact_keys(
                arguments,
                &[
                    "focus_agent_id",
                    "filters",
                    "grouping",
                    "cursor",
                    "page_size",
                ],
            )?;
            nullable_string_field(arguments, "focus_agent_id")?;
            validate_event_filters(object_field(arguments, "filters")?)?;
            string_field(arguments, "grouping")?;
            nullable_string_field(arguments, "cursor")?;
            unsigned_field(arguments, "page_size")?;
            Ok(())
        }
        "query_coordination" => {
            exact_keys(
                arguments,
                &["work_item_ids", "agent_ids", "cursor", "page_size"],
            )?;
            string_array_field(arguments, "work_item_ids")?;
            string_array_field(arguments, "agent_ids")?;
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

fn validate_string_array_object(
    value: &Map<String, Value>,
    keys: &[&str],
) -> Result<(), SupervisorError> {
    exact_keys(value, keys)?;
    for key in keys {
        string_array_field(value, key)?;
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

fn string_field(value: &Map<String, Value>, key: &'static str) -> Result<(), SupervisorError> {
    value
        .get(key)
        .and_then(Value::as_str)
        .filter(|item| !item.is_empty())
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

fn bool_field(value: &Map<String, Value>, key: &'static str) -> Result<(), SupervisorError> {
    value
        .get(key)
        .and_then(Value::as_bool)
        .map(|_| ())
        .ok_or_else(|| protocol_error("REPORT_WORKER_PROTOCOL", key))
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
        if let Err(error) = spawn_stderr_reader(stderr, self.config.max_stderr_bytes) {
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
                    "pricing_digest": service.pricing_digest,
                    "formatter_digest": service.formatter_digest,
                    "default_page_size": service.default_page_size,
                    "max_page_size": service.max_page_size,
                    "max_time_buckets": service.max_time_buckets,
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
        let encoded = encode_json_line(&request.envelope, self.config.max_record_bytes)?;
        self.state.used_operation_ids.insert(operation_id.clone());
        self.state.operations.insert(
            operation_id.clone(),
            ActiveOperation {
                operation,
                snapshot_id,
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
        let Some(active) = self.state.operations.get_mut(&operation_id) else {
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
        match record {
            WorkerWireRecord::Progress(value) => {
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
        || config.service_configuration.pricing_digest.is_empty()
        || config.service_configuration.formatter_digest.is_empty()
        || config.service_configuration.default_page_size == 0
        || config.service_configuration.default_page_size
            > config.service_configuration.max_page_size
        || config.service_configuration.max_time_buckets == 0
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
                        // The native diagnostic sink is supplied by the later crate-root
                        // integration. Raw child bytes are intentionally discarded here.
                        let _ = sanitizer.ingest(&buffer[..count]);
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
