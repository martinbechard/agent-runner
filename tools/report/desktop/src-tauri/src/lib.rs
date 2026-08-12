// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Serve privacy-bounded catalog and Dynamic Workspace commands to the Tauri desktop webview.
// Design: docs/design/components/CD-004-agent-report-worker-protocol.md

//! Native command boundary for the local agent report desktop application.

pub mod report_worker;

use std::collections::{BTreeMap, HashMap};
use std::env;
use std::ffi::OsString;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex, mpsc};
use std::time::{Duration as StdDuration, SystemTime};

use agent_report_core::{
    DiscoveryEntry, DiscoveryProgress, DiscoveryRequest, DiscoveryResponse, DiscoveryStats,
    PROTOCOL_VERSION, collect_rollout_paths, index_rollouts, read_codex_task_parents,
    read_codex_task_titles,
};
use chrono::{DateTime, Duration, NaiveDate, NaiveDateTime, SecondsFormat, Timelike, Utc};
use html_escape::{encode_double_quoted_attribute, encode_text};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};
use tauri::ipc::Channel;
use tauri::webview::NewWindowResponse;
use tauri::{AppHandle, Emitter, Manager, State, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use unicode_normalization::UnicodeNormalization;
use url::Url;

use report_worker::{
    AutomationSurfaceWire, ExportModeWire, HostTerminalOutcome, OperationObserver, PathAuthority,
    ProgressEnvelope, RequestEnvelope, SanitizedDiagnostic, ServiceConfiguration, StructuredError,
    TrustedWorkerRequest, WORKER_PROTOCOL_VERSION, WorkerLaunchSpec, WorkerSupervisor,
    WorkerSupervisorConfig,
};

static REPORT_WINDOW_COUNTER: AtomicU64 = AtomicU64::new(1);
static DIAGNOSTIC_WRITE_LOCK: Mutex<()> = Mutex::new(());
static REPORT_PROCESS: Mutex<Option<CommandChild>> = Mutex::new(None);
static REPORT_CANCEL_REQUESTED: AtomicBool = AtomicBool::new(false);
static OPAQUE_REFERENCE_COUNTER: AtomicU64 = AtomicU64::new(1);

const DIAGNOSTIC_LOG_FILENAME: &str = "agent-report.log";
const DIAGNOSTIC_LOG_PREVIOUS_FILENAME: &str = "agent-report.previous.log";
const DIAGNOSTIC_LOG_MAX_BYTES: u64 = 5 * 1024 * 1024;
const REPORT_PROGRESS_EVENT: &str = "report-operation-progress";
const MAX_SOURCE_REFERENCES: usize = 65_536;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RootReferenceDto {
    pub root_ref: String,
    pub display_name: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct NativeReportError {
    pub code: String,
    pub message: String,
    pub operation_id: Option<String>,
    pub recoverable: bool,
    pub current_source_revision: Option<String>,
    pub preflight_required: bool,
    pub restart_from_first_page: bool,
}

impl NativeReportError {
    fn new(code: &str, message: &str, operation_id: Option<&str>, recoverable: bool) -> Self {
        Self {
            code: code.to_owned(),
            message: message.to_owned(),
            operation_id: operation_id.map(str::to_owned),
            recoverable,
            current_source_revision: None,
            preflight_required: false,
            restart_from_first_page: false,
        }
    }

    fn protocol(message: &str, operation_id: Option<&str>) -> Self {
        Self::new("REPORT_PROTOCOL_ERROR", message, operation_id, true)
    }
}

impl From<StructuredError> for NativeReportError {
    fn from(error: StructuredError) -> Self {
        Self {
            code: error.code,
            message: error.message,
            operation_id: error.operation_id,
            recoverable: error.recoverable,
            current_source_revision: error.current_source_revision,
            preflight_required: error.preflight_required,
            restart_from_first_page: error.restart_from_first_page,
        }
    }
}

#[derive(Default)]
struct NativeReportState {
    roots: Mutex<HashMap<String, PathBuf>>,
    active_roots: Mutex<Vec<PathBuf>>,
    source_keys: Mutex<HashMap<String, PathBuf>>,
    source_refs: Mutex<HashMap<(String, String), PathBuf>>,
    source_refs_by_key: Mutex<HashMap<(String, String), String>>,
    snapshot_revisions: Mutex<HashMap<String, String>>,
    exports: Mutex<HashMap<String, PathBuf>>,
    supervisor: Mutex<Option<(Vec<PathBuf>, Arc<WorkerSupervisor>)>>,
}

impl Drop for NativeReportState {
    fn drop(&mut self) {
        if let Ok(supervisor) = self.supervisor.get_mut()
            && let Some((_roots, supervisor)) = supervisor.take()
        {
            let _ = supervisor.shutdown();
        }
    }
}

struct TauriOperationObserver {
    app: AppHandle,
    terminal: Mutex<Option<mpsc::SyncSender<HostTerminalOutcome>>>,
}

impl OperationObserver for TauriOperationObserver {
    fn on_progress(&self, value: ProgressEnvelope) {
        let _ = self.app.emit(
            REPORT_PROGRESS_EVENT,
            snake_to_camel(serde_json::to_value(value).unwrap_or(Value::Null)),
        );
    }

    fn on_terminal(&self, value: HostTerminalOutcome) {
        if let Ok(mut sender) = self.terminal.lock()
            && let Some(sender) = sender.take()
        {
            let _ = sender.send(value);
        }
    }
}

fn fixed_diagnostic_message(event: &str) -> &'static str {
    match event {
        "app_started" => "Agent Report started.",
        "panic" => "Agent Report stopped unexpectedly.",
        "diagnostic_log_created" => "Diagnostic log created on demand.",
        "sequence_popup_allowed" => "Allowed the generated sequence companion window.",
        "sequence_popup_denied" => "Denied an unauthorized report popup.",
        "view_parent_report" => "Unable to forward a parent report request.",
        "search_rollouts" => "Native rollout search failed.",
        "export_catalog" => "Native catalog export failed.",
        "generate_report" => "Classic report generation failed.",
        "open_report_window" => "Unable to open the selected report window.",
        "open_diagnostic_log" => "Unable to open the diagnostic log.",
        "report_worker_operation" => "A report worker operation failed.",
        "worker.startup_failed" => "Worker startup failed.",
        "worker.invalid_input" => "Worker input validation failed.",
        "worker.service_contract" => "Worker service contract failed.",
        "worker.internal_failure" => "Worker execution failed.",
        "worker.output_failed" => "Worker protocol output failed.",
        "worker.shutdown_failed" => "Worker shutdown failed.",
        "worker.stderr_rejected" => "Worker diagnostic input was rejected.",
        "worker.stderr_limit_reached" => "Worker diagnostic limit was reached.",
        _ if event.starts_with("webview.") => "The webview reported an operation failure.",
        _ => "A native operation failed.",
    }
}

#[cfg(unix)]
fn secure_diagnostic_file_permissions(path: &Path) -> Result<(), String> {
    use std::os::unix::fs::PermissionsExt;

    fs::set_permissions(path, fs::Permissions::from_mode(0o600))
        .map_err(|error| format!("unable to secure diagnostic log permissions: {error}"))
}

#[cfg(windows)]
fn secure_diagnostic_file_permissions(_path: &Path) -> Result<(), String> {
    // Windows diagnostic files inherit the per-user app-log directory ACL. Native
    // Windows packaging tests must verify that other local users cannot read it.
    Ok(())
}

#[cfg(not(any(unix, windows)))]
fn secure_diagnostic_file_permissions(_path: &Path) -> Result<(), String> {
    Ok(())
}

fn append_diagnostic_entry(log_path: &Path, level: &str, event: &str) -> Result<(), String> {
    let _guard = DIAGNOSTIC_WRITE_LOCK
        .lock()
        .map_err(|_| "diagnostic log writer lock is unavailable".to_owned())?;
    let parent = log_path
        .parent()
        .ok_or_else(|| "diagnostic log path has no parent folder".to_owned())?;
    fs::create_dir_all(parent)
        .map_err(|error| format!("unable to create diagnostic log folder: {error}"))?;
    if fs::metadata(log_path).is_ok_and(|metadata| metadata.len() >= DIAGNOSTIC_LOG_MAX_BYTES) {
        secure_diagnostic_file_permissions(log_path)?;
        let previous_path = log_path.with_file_name(DIAGNOSTIC_LOG_PREVIOUS_FILENAME);
        match fs::remove_file(&previous_path) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(format!(
                    "unable to replace previous diagnostic log: {error}"
                ));
            }
        }
        fs::rename(log_path, previous_path)
            .map_err(|error| format!("unable to rotate diagnostic log: {error}"))?;
    }
    let entry = serde_json::json!({
        "timestamp": DateTime::<Utc>::from(SystemTime::now())
            .to_rfc3339_opts(SecondsFormat::Millis, true),
        "level": level,
        "event": event,
        "message": fixed_diagnostic_message(event),
    });
    let mut options = OpenOptions::new();
    options.create(true).append(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut log = options
        .open(log_path)
        .map_err(|error| format!("unable to open diagnostic log: {error}"))?;
    secure_diagnostic_file_permissions(log_path)?;
    serde_json::to_writer(&mut log, &entry)
        .map_err(|error| format!("unable to serialize diagnostic entry: {error}"))?;
    log.write_all(b"\n")
        .and_then(|()| log.flush())
        .map_err(|error| format!("unable to persist diagnostic entry: {error}"))
}

fn diagnostic_log_path(app: &AppHandle) -> Result<PathBuf, String> {
    app.path()
        .app_log_dir()
        .map(|directory| directory.join(DIAGNOSTIC_LOG_FILENAME))
        .map_err(|error| format!("unable to resolve diagnostic log folder: {error}"))
}

fn record_diagnostic(app: &AppHandle, level: &str, event: &str) -> Result<(), String> {
    append_diagnostic_entry(&diagnostic_log_path(app)?, level, event)
}

fn record_failed_result<T>(
    app: &AppHandle,
    event: &str,
    result: Result<T, String>,
) -> Result<T, String> {
    if result.is_err() {
        let _ = record_diagnostic(app, "error", event);
    }
    result
}

fn initialize_diagnostics(app: &AppHandle) -> Result<(), String> {
    let log_path = diagnostic_log_path(app)?;
    append_diagnostic_entry(&log_path, "info", "app_started")?;
    let previous_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |panic_info| {
        let _ = append_diagnostic_entry(&log_path, "error", "panic");
        previous_hook(panic_info);
    }));
    Ok(())
}

fn opaque_reference(prefix: &str) -> String {
    format!(
        "{prefix}_{:024x}",
        OPAQUE_REFERENCE_COUNTER.fetch_add(1, Ordering::Relaxed)
    )
}

fn display_name(path: &Path) -> String {
    path.file_name()
        .and_then(|value| value.to_str())
        .filter(|value| !value.is_empty())
        .unwrap_or("Local folder")
        .chars()
        .take(256)
        .collect()
}

fn register_root(state: &NativeReportState, path: PathBuf) -> Result<RootReferenceDto, String> {
    let canonical = path
        .canonicalize()
        .map_err(|error| format!("unable to resolve selected folder: {error}"))?;
    if !canonical.is_dir() {
        return Err("selected report root is not a folder".to_owned());
    }
    let mut roots = state
        .roots
        .lock()
        .map_err(|_| "root registry is unavailable".to_owned())?;
    if let Some((root_ref, _)) = roots.iter().find(|(_, value)| **value == canonical) {
        return Ok(RootReferenceDto {
            root_ref: root_ref.clone(),
            display_name: display_name(&canonical),
        });
    }
    let root_ref = opaque_reference("root");
    roots.insert(root_ref.clone(), canonical.clone());
    Ok(RootReferenceDto {
        root_ref,
        display_name: display_name(&canonical),
    })
}

fn source_key_for_path(path: &Path) -> Result<String, String> {
    let absolute = path
        .canonicalize()
        .map_err(|error| format!("unable to resolve discovered source: {error}"))?;
    let normalized = absolute.to_string_lossy().replace('\\', "/");
    #[cfg(windows)]
    let normalized = normalized.to_lowercase();
    let normalized = normalized.nfc().collect::<String>();
    let domain = b"source-key-v1";
    let field = b"normalized_absolute_path";
    let value = normalized.as_bytes();
    let mut canonical = b"agent-report-cache-c14n-v1\0".to_vec();
    canonical.push(1);
    canonical.extend_from_slice(&(domain.len() as u64).to_be_bytes());
    canonical.extend_from_slice(domain);
    canonical.extend_from_slice(&(field.len() as u16).to_be_bytes());
    canonical.extend_from_slice(field);
    canonical.push(1);
    canonical.extend_from_slice(&(value.len() as u64).to_be_bytes());
    canonical.extend_from_slice(value);
    Ok(format!("{:x}", Sha256::digest(canonical)))
}

fn snake_to_camel(value: Value) -> Value {
    match value {
        Value::Array(values) => Value::Array(values.into_iter().map(snake_to_camel).collect()),
        Value::Object(values) => Value::Object(
            values
                .into_iter()
                .map(|(key, value)| {
                    let mut converted = String::with_capacity(key.len());
                    let mut uppercase = false;
                    for character in key.chars() {
                        if character == '_' {
                            uppercase = true;
                        } else if uppercase {
                            converted.extend(character.to_uppercase());
                            uppercase = false;
                        } else {
                            converted.push(character);
                        }
                    }
                    (converted, snake_to_camel(value))
                })
                .collect(),
        ),
        other => other,
    }
}

fn request_object(request: &Value) -> Result<&Map<String, Value>, NativeReportError> {
    request
        .as_object()
        .ok_or_else(|| NativeReportError::protocol("The command request is invalid.", None))
}

fn required_string<'a>(
    request: &'a Map<String, Value>,
    key: &str,
    operation_id: Option<&str>,
) -> Result<&'a str, NativeReportError> {
    request
        .get(key)
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| NativeReportError::protocol("The command request is invalid.", operation_id))
}

fn singleton(value: Option<&Value>) -> Value {
    value
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .map_or_else(|| json!([]), |value| json!([value]))
}

fn wire_sort(value: Option<&Value>, operation_id: &str) -> Result<Value, NativeReportError> {
    let sort = value.and_then(Value::as_object).ok_or_else(|| {
        NativeReportError::protocol("The command sort is invalid.", Some(operation_id))
    })?;
    Ok(json!({
        "key": required_string(sort, "key", Some(operation_id))?,
        "direction": required_string(sort, "direction", Some(operation_id))?,
        "tie_break_key": required_string(sort, "tieBreakKey", Some(operation_id))?,
        "tie_break_direction": required_string(sort, "tieBreakDirection", Some(operation_id))?,
    }))
}

fn wire_request(
    operation: &str,
    request: Value,
) -> Result<TrustedWorkerRequest, NativeReportError> {
    let request = request_object(&request)?;
    let operation_id = required_string(request, "operationId", None)?;
    let snapshot_id = request.get("snapshotId").and_then(Value::as_str);
    let arguments = match operation {
        "preflight_report" => json!({"scope": {
            "root_thread_id": required_string(request, "rootThreadId", Some(operation_id))?,
            "include_children": request.get("includeChildren").and_then(Value::as_bool).unwrap_or(false),
            "include_collaborators": request.get("includeCollaborators").and_then(Value::as_bool).unwrap_or(false)
        }}),
        "open_snapshot" => json!({
            "scope": {
                "root_thread_id": required_string(request, "rootThreadId", Some(operation_id))?,
                "include_children": request.get("includeChildren").and_then(Value::as_bool).unwrap_or(false),
                "include_collaborators": request.get("includeCollaborators").and_then(Value::as_bool).unwrap_or(false)
            },
            "preflight_token": required_string(request, "preflightToken", Some(operation_id))?,
            "source_revision": required_string(request, "sourceRevision", Some(operation_id))?
        }),
        "get_summary" | "refresh_snapshot" | "close_snapshot" => json!({}),
        "list_agents" => {
            let filters = request
                .get("filters")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    NativeReportError::protocol(
                        "The command request is invalid.",
                        Some(operation_id),
                    )
                })?;
            json!({
                "filters": {
                    "query": filters.get("query").and_then(Value::as_str).unwrap_or(""),
                    "agent_ids": [], "roles": [], "states": singleton(filters.get("state"))
                },
                "sort": wire_sort(request.get("sort"), operation_id)?,
                "cursor": request.get("cursor").cloned().unwrap_or(Value::Null),
                "page_size": request.get("pageSize").cloned().unwrap_or(Value::Null)
            })
        }
        "list_turns" => {
            let filters = request
                .get("filters")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    NativeReportError::protocol(
                        "The command request is invalid.",
                        Some(operation_id),
                    )
                })?;
            json!({
                "filters": {
                    "turn_ids": [], "agent_ids": singleton(filters.get("agentId")),
                    "states": singleton(filters.get("state")), "from_time": null, "to_time": null
                },
                "sort": wire_sort(request.get("sort"), operation_id)?,
                "cursor": request.get("cursor").cloned().unwrap_or(Value::Null),
                "page_size": request.get("pageSize").cloned().unwrap_or(Value::Null)
            })
        }
        "list_events" => {
            let filters = request
                .get("filters")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    NativeReportError::protocol(
                        "The command request is invalid.",
                        Some(operation_id),
                    )
                })?;
            json!({
                "filters": {
                    "event_ids": [], "agent_ids": singleton(filters.get("agentId")),
                    "turn_ids": singleton(filters.get("turnId")), "kinds": singleton(filters.get("kind")),
                    "from_time": filters.get("fromTime").cloned().unwrap_or(Value::Null),
                    "to_time": filters.get("toTime").cloned().unwrap_or(Value::Null)
                },
                "sort": wire_sort(request.get("sort"), operation_id)?,
                "cursor": request.get("cursor").cloned().unwrap_or(Value::Null),
                "page_size": request.get("pageSize").cloned().unwrap_or(Value::Null)
            })
        }
        "query_time_range" => json!({
            "from_time": request.get("fromTime").cloned().unwrap_or(Value::Null),
            "to_time": request.get("toTime").cloned().unwrap_or(Value::Null),
            "measure": request.get("measure").cloned().unwrap_or(Value::Null),
            "group_by": request.get("groupBy").cloned().unwrap_or(Value::Null),
            "requested_resolution_minutes": request.get("requestedResolutionMinutes").cloned().unwrap_or(Value::Null),
            "maximum_rows": request.get("maximumRows").cloned().unwrap_or(Value::Null)
        }),
        "query_sequence" => {
            let filters = request
                .get("filters")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    NativeReportError::protocol(
                        "The command request is invalid.",
                        Some(operation_id),
                    )
                })?;
            json!({
                "filters": {
                    "focus_agent_id": filters.get("focusAgentId").cloned().unwrap_or(Value::Null),
                    "event_filters": {
                        "event_ids": [], "agent_ids": [], "turn_ids": [],
                        "kinds": filters.get("eventKinds").cloned().unwrap_or_else(|| json!([])),
                        "from_time": null, "to_time": null
                    },
                    "grouping": filters.get("grouping").cloned().unwrap_or(Value::Null),
                    "include_reasoning": filters.get("includeReasoning").cloned().unwrap_or(Value::Null)
                },
                "sort": wire_sort(request.get("sort"), operation_id)?,
                "cursor": request.get("cursor").cloned().unwrap_or(Value::Null),
                "page_size": request.get("pageSize").cloned().unwrap_or(Value::Null)
            })
        }
        "query_coordination" => {
            let filters = request
                .get("filters")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    NativeReportError::protocol(
                        "The command request is invalid.",
                        Some(operation_id),
                    )
                })?;
            json!({
                "filters": {
                    "work_item_id": filters.get("workItemId").cloned().unwrap_or(Value::Null),
                    "delegated_root_id": filters.get("delegatedRootId").cloned().unwrap_or(Value::Null),
                    "agent_id": filters.get("agentId").cloned().unwrap_or(Value::Null),
                    "operation": filters.get("operation").cloned().unwrap_or(Value::Null),
                    "evidence": filters.get("evidence").cloned().unwrap_or(Value::Null)
                },
                "sort": wire_sort(request.get("sort"), operation_id)?,
                "cursor": request.get("cursor").cloned().unwrap_or(Value::Null),
                "page_size": request.get("pageSize").cloned().unwrap_or(Value::Null)
            })
        }
        "get_event_details" => {
            json!({"event_id": request.get("eventId").cloned().unwrap_or(Value::Null)})
        }
        _ => {
            return Err(NativeReportError::protocol(
                "The report operation is unsupported.",
                Some(operation_id),
            ));
        }
    };
    let envelope = RequestEnvelope {
        protocol_version: WORKER_PROTOCOL_VERSION,
        operation_id: operation_id.to_owned(),
        operation: operation.to_owned(),
        snapshot_id: snapshot_id.map(str::to_owned),
        arguments: arguments.as_object().cloned().unwrap_or_default(),
    };
    TrustedWorkerRequest::path_free(envelope).map_err(|_| {
        NativeReportError::protocol(
            "The report request failed native validation.",
            Some(operation_id),
        )
    })
}

fn register_snapshot_revision(
    state: &NativeReportState,
    snapshot_id: &str,
    revision: &str,
) -> Result<(), NativeReportError> {
    let mut revisions = state.snapshot_revisions.lock().map_err(|_| {
        NativeReportError::protocol("The snapshot revision registry is unavailable.", None)
    })?;
    if !revisions.contains_key(snapshot_id) && revisions.len() >= MAX_SOURCE_REFERENCES {
        return Err(NativeReportError::new(
            "REPORT_UNAVAILABLE",
            "The native source registry reached its safety limit.",
            None,
            true,
        ));
    }
    revisions.insert(snapshot_id.to_owned(), revision.to_owned());
    Ok(())
}

fn register_snapshot_source_ref(
    state: &NativeReportState,
    snapshot_id: &str,
    source_key: &str,
    path: PathBuf,
) -> Result<String, NativeReportError> {
    let key = (snapshot_id.to_owned(), source_key.to_owned());
    let mut reverse = state
        .source_refs_by_key
        .lock()
        .map_err(|_| NativeReportError::protocol("The source registry is unavailable.", None))?;
    if let Some(source_ref) = reverse.get(&key) {
        return Ok(source_ref.clone());
    }
    let mut references = state
        .source_refs
        .lock()
        .map_err(|_| NativeReportError::protocol("The source registry is unavailable.", None))?;
    if references.len() >= MAX_SOURCE_REFERENCES {
        return Err(NativeReportError::new(
            "REPORT_UNAVAILABLE",
            "The native source registry reached its safety limit.",
            None,
            true,
        ));
    }
    let source_ref = opaque_reference("source");
    references.insert((snapshot_id.to_owned(), source_ref.clone()), path);
    reverse.insert(key, source_ref.clone());
    Ok(source_ref)
}

fn invalidate_snapshot_sources(
    state: &NativeReportState,
    snapshot_id: &str,
) -> Result<(), NativeReportError> {
    state
        .source_refs_by_key
        .lock()
        .map_err(|_| NativeReportError::protocol("The source registry is unavailable.", None))?
        .retain(|(registered_snapshot, _), _| registered_snapshot != snapshot_id);
    state
        .source_refs
        .lock()
        .map_err(|_| NativeReportError::protocol("The source registry is unavailable.", None))?
        .retain(|(registered_snapshot, _), _| registered_snapshot != snapshot_id);
    state
        .snapshot_revisions
        .lock()
        .map_err(|_| {
            NativeReportError::protocol("The snapshot revision registry is unavailable.", None)
        })?
        .remove(snapshot_id);
    Ok(())
}

fn resolve_snapshot_source_ref(
    state: &NativeReportState,
    snapshot_id: &str,
    source_ref: &str,
) -> Result<PathBuf, NativeReportError> {
    if !state
        .snapshot_revisions
        .lock()
        .map_err(|_| {
            NativeReportError::protocol("The snapshot revision registry is unavailable.", None)
        })?
        .contains_key(snapshot_id)
    {
        return Err(NativeReportError::new(
            "REPORT_NOT_FOUND",
            "The selected source is no longer available.",
            None,
            true,
        ));
    }
    state
        .source_refs
        .lock()
        .map_err(|_| NativeReportError::protocol("The source registry is unavailable.", None))?
        .get(&(snapshot_id.to_owned(), source_ref.to_owned()))
        .cloned()
        .ok_or_else(|| {
            NativeReportError::new(
                "REPORT_NOT_FOUND",
                "The selected source is no longer available.",
                None,
                true,
            )
        })
}

fn project_source_keys(
    value: &mut Value,
    snapshot_id: &str,
    state: &NativeReportState,
) -> Result<(), NativeReportError> {
    match value {
        Value::Array(values) => {
            for value in values {
                project_source_keys(value, snapshot_id, state)?;
            }
        }
        Value::Object(values) => {
            if let Some(source_key) = values.remove("source_key") {
                let projected = match source_key {
                    Value::Null => Value::Null,
                    Value::String(source_key) => {
                        let path = state
                            .source_keys
                            .lock()
                            .map_err(|_| {
                                NativeReportError::protocol(
                                    "The source registry is unavailable.",
                                    None,
                                )
                            })?
                            .get(&source_key)
                            .cloned()
                            .ok_or_else(|| {
                                NativeReportError::protocol(
                                    "The report source is unavailable.",
                                    None,
                                )
                            })?;
                        let source_ref =
                            register_snapshot_source_ref(state, snapshot_id, &source_key, path)?;
                        Value::String(source_ref)
                    }
                    _ => {
                        return Err(NativeReportError::protocol(
                            "The report source identity is invalid.",
                            None,
                        ));
                    }
                };
                values.insert("source_ref".to_owned(), projected);
            }
            for value in values.values_mut() {
                project_source_keys(value, snapshot_id, state)?;
            }
        }
        _ => {}
    }
    Ok(())
}

fn snapshot_projection(
    mut result: Map<String, Value>,
) -> Result<Map<String, Value>, NativeReportError> {
    let scope = result
        .remove("scope")
        .and_then(|value| value.as_object().cloned())
        .ok_or_else(|| NativeReportError::protocol("The snapshot result is invalid.", None))?;
    let revision = result
        .remove("revision_id")
        .ok_or_else(|| NativeReportError::protocol("The snapshot result is invalid.", None))?;
    result.insert("revision".to_owned(), revision);
    for (source, target) in [
        ("root_thread_id", "root_thread_id"),
        ("include_children", "include_children"),
        ("include_collaborators", "include_collaborators"),
    ] {
        result.insert(
            target.to_owned(),
            scope.get(source).cloned().ok_or_else(|| {
                NativeReportError::protocol("The snapshot scope is invalid.", None)
            })?,
        );
    }
    result.remove("pricing_version");
    result.remove("formatter_version");
    Ok(result)
}

fn first_or_null(value: Option<&Value>) -> Value {
    value
        .and_then(Value::as_array)
        .and_then(|values| values.first())
        .cloned()
        .unwrap_or(Value::Null)
}

fn project_page_binding(
    operation: &str,
    result: &mut Map<String, Value>,
) -> Result<(), NativeReportError> {
    let filters = result
        .get_mut("applied_filters")
        .and_then(Value::as_object_mut)
        .ok_or_else(|| NativeReportError::protocol("The page filters are invalid.", None))?;
    let projected = match operation {
        "list_agents" => json!({
            "query": filters.get("query").cloned().unwrap_or_else(|| json!("")),
            "state": first_or_null(filters.get("states")),
        }),
        "list_turns" => json!({
            "agent_id": first_or_null(filters.get("agent_ids")),
            "state": first_or_null(filters.get("states")),
        }),
        "list_events" => json!({
            "agent_id": first_or_null(filters.get("agent_ids")),
            "turn_id": first_or_null(filters.get("turn_ids")),
            "kind": first_or_null(filters.get("kinds")),
            "from_time": filters.get("from_time").cloned().unwrap_or(Value::Null),
            "to_time": filters.get("to_time").cloned().unwrap_or(Value::Null),
        }),
        "query_sequence" => {
            let event_filters = filters
                .get("event_filters")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    NativeReportError::protocol("The sequence filters are invalid.", None)
                })?;
            json!({
                "focus_agent_id": filters.get("focus_agent_id").cloned().unwrap_or(Value::Null),
                "event_kinds": event_filters.get("kinds").cloned().unwrap_or_else(|| json!([])),
                "grouping": filters.get("grouping").cloned().unwrap_or(Value::Null),
                "include_reasoning": filters.get("include_reasoning").cloned().unwrap_or(Value::Null),
            })
        }
        "query_coordination" => Value::Object(filters.clone()),
        _ => {
            return Err(NativeReportError::protocol(
                "The page operation is invalid.",
                None,
            ));
        }
    };
    result.insert("applied_filters".to_owned(), projected);
    Ok(())
}

fn retain_row_fields(row: &mut Value, fields: &[&str]) {
    if let Some(row) = row.as_object_mut() {
        row.retain(|key, _| fields.contains(&key.as_str()));
    }
}

fn project_page_rows(operation: &str, result: &mut Map<String, Value>) {
    let Some(items) = result.get_mut("items").and_then(Value::as_array_mut) else {
        return;
    };
    for row in items {
        if let Some(row) = row.as_object_mut()
            && matches!(
                operation,
                "list_events" | "query_sequence" | "query_coordination"
            )
            && let Some(summary) = row.remove("summary")
        {
            row.insert("label".to_owned(), summary);
        }
        match operation {
            "list_agents" => retain_row_fields(
                row,
                &[
                    "agent_id",
                    "nickname",
                    "role",
                    "state",
                    "started_at",
                    "last_activity_at",
                    "turn_count",
                    "event_count",
                ],
            ),
            "list_turns" => retain_row_fields(
                row,
                &[
                    "turn_id",
                    "agent_id",
                    "started_at",
                    "ended_at",
                    "state",
                    "event_count",
                    "summary",
                ],
            ),
            "list_events" => retain_row_fields(
                row,
                &[
                    "event_id",
                    "occurred_at",
                    "agent_id",
                    "turn_id",
                    "kind",
                    "label",
                    "evidence",
                    "source_key",
                    "has_detail",
                ],
            ),
            "query_sequence" => retain_row_fields(
                row,
                &[
                    "sequence_id",
                    "group_id",
                    "occurred_at",
                    "from_agent_id",
                    "from_agent_label",
                    "to_agent_id",
                    "to_agent_label",
                    "kind",
                    "label",
                    "evidence",
                    "event_id",
                    "repeat_count",
                    "reasoning_available",
                ],
            ),
            "query_coordination" => retain_row_fields(
                row,
                &[
                    "coordination_id",
                    "occurred_at",
                    "work_item_id",
                    "delegated_root_id",
                    "agent_id",
                    "operation",
                    "label",
                    "evidence",
                    "event_id",
                ],
            ),
            _ => {}
        }
    }
}

fn project_worker_result(
    operation: &str,
    mut result: Map<String, Value>,
    state: &NativeReportState,
) -> Result<Value, NativeReportError> {
    match operation {
        "open_snapshot" => {
            result = snapshot_projection(result)?;
            let snapshot_id = result
                .get("snapshot_id")
                .and_then(Value::as_str)
                .ok_or_else(|| {
                    NativeReportError::protocol("The snapshot result is invalid.", None)
                })?;
            let revision = result
                .get("revision")
                .and_then(Value::as_str)
                .ok_or_else(|| {
                    NativeReportError::protocol("The snapshot result is invalid.", None)
                })?;
            register_snapshot_revision(state, snapshot_id, revision)?;
        }
        "get_summary" => {
            let revision = result.remove("revision_id").ok_or_else(|| {
                NativeReportError::protocol("The summary result is invalid.", None)
            })?;
            result.insert("revision".to_owned(), revision);
            let scope = result
                .remove("scope")
                .and_then(|value| value.as_object().cloned())
                .ok_or_else(|| {
                    NativeReportError::protocol("The summary scope is invalid.", None)
                })?;
            let scope_label = format!(
                "{}{}{}",
                scope
                    .get("root_thread_id")
                    .and_then(Value::as_str)
                    .unwrap_or("Report"),
                if scope.get("include_children").and_then(Value::as_bool) == Some(true) {
                    " · children"
                } else {
                    ""
                },
                if scope.get("include_collaborators").and_then(Value::as_bool) == Some(true) {
                    " · collaborators"
                } else {
                    ""
                },
            );
            result.insert("scope_label".to_owned(), Value::String(scope_label));
            let live = result.get("mode").and_then(Value::as_str) == Some("live");
            result.remove("mode");
            result.insert("live".to_owned(), Value::Bool(live));
            if let Some(Value::Array(groups)) = result.get_mut("metric_groups") {
                for group in groups {
                    if let Some(metrics) = group.get_mut("metrics").and_then(Value::as_array_mut) {
                        for metric in metrics {
                            if let Some(metric) = metric.as_object_mut()
                                && let Some(display) = metric.remove("formatted_value")
                            {
                                metric.insert("display_value".to_owned(), display);
                                metric.remove("value");
                                metric.remove("unit");
                                metric.remove("provenance");
                            }
                        }
                    }
                }
            }
            result.remove("provenance");
        }
        "list_agents" | "list_turns" | "list_events" | "query_coordination" => {
            let revision = result
                .remove("revision_id")
                .ok_or_else(|| NativeReportError::protocol("The page result is invalid.", None))?;
            result.insert("revision".to_owned(), revision);
            project_page_binding(operation, &mut result)?;
            project_page_rows(operation, &mut result);
        }
        "query_sequence" => {
            if let Some(page) = result.get_mut("page").and_then(Value::as_object_mut) {
                let revision = page.remove("revision_id").ok_or_else(|| {
                    NativeReportError::protocol("The sequence result is invalid.", None)
                })?;
                page.insert("revision".to_owned(), revision);
                project_page_binding(operation, page)?;
                project_page_rows(operation, page);
            }
        }
        "query_time_range" => {
            let revision = result.remove("revision_id").ok_or_else(|| {
                NativeReportError::protocol("The heatmap result is invalid.", None)
            })?;
            result.insert("revision".to_owned(), revision);
        }
        "get_event_details" => {
            let revision = result.remove("revision_id").ok_or_else(|| {
                NativeReportError::protocol("The detail result is invalid.", None)
            })?;
            result.insert("revision".to_owned(), revision);
        }
        "refresh_snapshot" => {
            let changed = result
                .get("changed")
                .and_then(Value::as_bool)
                .ok_or_else(|| {
                    NativeReportError::protocol("The refresh result is invalid.", None)
                })?;
            let snapshot = result
                .remove("snapshot")
                .and_then(|value| value.as_object().cloned())
                .ok_or_else(|| {
                    NativeReportError::protocol("The refresh result is invalid.", None)
                })?;
            let snapshot = snapshot_projection(snapshot)?;
            let snapshot_id = snapshot
                .get("snapshot_id")
                .and_then(Value::as_str)
                .ok_or_else(|| {
                    NativeReportError::protocol("The refresh result is invalid.", None)
                })?;
            let revision = snapshot
                .get("revision")
                .and_then(Value::as_str)
                .ok_or_else(|| {
                    NativeReportError::protocol("The refresh result is invalid.", None)
                })?;
            if changed {
                invalidate_snapshot_sources(state, snapshot_id)?;
            }
            register_snapshot_revision(state, snapshot_id, revision)?;
            result.insert("snapshot".to_owned(), Value::Object(snapshot));
        }
        "close_snapshot" => {
            if result.get("closed").and_then(Value::as_bool) == Some(true) {
                let snapshot_id = result
                    .get("snapshot_id")
                    .and_then(Value::as_str)
                    .ok_or_else(|| {
                        NativeReportError::protocol("The close result is invalid.", None)
                    })?;
                invalidate_snapshot_sources(state, snapshot_id)?;
            }
        }
        "preflight_report" => {}
        _ => {
            return Err(NativeReportError::protocol(
                "The report operation is unsupported.",
                None,
            ));
        }
    }
    let snapshot_id = result
        .get("snapshot_id")
        .and_then(Value::as_str)
        .map(str::to_owned)
        .or_else(|| {
            result
                .get("snapshot")
                .and_then(|value| value.get("snapshot_id"))
                .and_then(Value::as_str)
                .map(str::to_owned)
        });
    if let Some(snapshot_id) = snapshot_id.as_deref() {
        let mut value = Value::Object(result);
        project_source_keys(&mut value, snapshot_id, state)?;
        return Ok(snake_to_camel(value));
    }
    Ok(snake_to_camel(Value::Object(result)))
}

fn project_export_result(
    mut result: Map<String, Value>,
    state: &NativeReportState,
) -> Result<Value, NativeReportError> {
    let target = result
        .remove("published_target")
        .and_then(|value| value.as_str().map(PathBuf::from))
        .ok_or_else(|| NativeReportError::protocol("The export result is invalid.", None))?;
    let target = target
        .canonicalize()
        .map_err(|_| NativeReportError::protocol("The published export is unavailable.", None))?;
    let export_id = opaque_reference("export");
    state
        .exports
        .lock()
        .map_err(|_| NativeReportError::protocol("The export registry is unavailable.", None))?
        .insert(export_id.clone(), target.clone());
    result.insert("export_id".to_owned(), Value::String(export_id));
    result.insert(
        "display_name".to_owned(),
        Value::String(display_name(&target)),
    );
    let revision = result
        .remove("revision_id")
        .ok_or_else(|| NativeReportError::protocol("The export revision is invalid.", None))?;
    result.insert("revision".to_owned(), revision);
    Ok(snake_to_camel(Value::Object(result)))
}

fn worker_target_triple() -> &'static str {
    #[cfg(all(target_arch = "aarch64", target_os = "macos"))]
    return "aarch64-apple-darwin";
    #[cfg(all(target_arch = "x86_64", target_os = "macos"))]
    return "x86_64-apple-darwin";
    #[cfg(all(target_arch = "x86_64", target_os = "windows"))]
    return "x86_64-pc-windows-msvc";
    #[cfg(all(target_arch = "aarch64", target_os = "windows"))]
    return "aarch64-pc-windows-msvc";
    #[cfg(all(target_arch = "x86_64", target_os = "linux"))]
    return "x86_64-unknown-linux-gnu";
    #[cfg(all(target_arch = "aarch64", target_os = "linux"))]
    return "aarch64-unknown-linux-gnu";
    #[allow(unreachable_code)]
    "unsupported-target"
}

fn worker_executable() -> Result<PathBuf, NativeReportError> {
    let suffix = if cfg!(windows) { ".exe" } else { "" };
    let mut candidates = Vec::new();
    if let Some(configured) = renderer_override(env::var_os("AGENT_REPORT_COMMAND")) {
        candidates.push(configured);
    }
    if let Ok(current) = env::current_exe()
        && let Some(directory) = current.parent()
    {
        candidates.push(directory.join(format!("agent-report{suffix}")));
        candidates.push(
            directory
                .join("../Resources")
                .join(format!("agent-report{suffix}")),
        );
    }
    candidates.push(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("binaries")
            .join(format!("agent-report-{}{suffix}", worker_target_triple())),
    );
    candidates
        .into_iter()
        .find_map(|candidate| candidate.is_file().then_some(candidate))
        .and_then(|candidate| candidate.canonicalize().ok())
        .ok_or_else(|| {
            NativeReportError::new(
                "REPORT_UNAVAILABLE",
                "The packaged report worker is unavailable.",
                None,
                true,
            )
        })
}

fn configuration_resource(
    contents: &[u8],
    version_key: &str,
) -> Result<(String, String), NativeReportError> {
    let document: Value = serde_json::from_slice(contents).map_err(|_| {
        NativeReportError::new(
            "REPORT_UNAVAILABLE",
            "The packaged report configuration is unavailable.",
            None,
            false,
        )
    })?;
    let version = document
        .get(version_key)
        .and_then(|value| match value {
            Value::String(value) => Some(value.clone()),
            Value::Number(value) => Some(value.to_string()),
            _ => None,
        })
        .filter(|value| !value.is_empty())
        .ok_or_else(|| {
            NativeReportError::new(
                "REPORT_UNAVAILABLE",
                "The packaged report configuration is invalid.",
                None,
                false,
            )
        })?;
    Ok((version, format!("{:x}", Sha256::digest(contents))))
}

fn worker_supervisor_config(
    app: &AppHandle,
    roots: Vec<PathBuf>,
) -> Result<WorkerSupervisorConfig, NativeReportError> {
    let pricing = include_bytes!("../../../../../docs/reference/openai-model-pricing.json");
    let formatters = include_bytes!("../../../tool-formatters.json");
    let (pricing_version, pricing_digest) = configuration_resource(pricing, "_updated_at")?;
    let (formatter_version, formatter_digest) = configuration_resource(formatters, "version")?;
    let diagnostic_app = app.clone();
    let diagnostic_sink: Arc<dyn Fn(SanitizedDiagnostic) + Send + Sync> =
        Arc::new(move |diagnostic| {
            let _ = record_diagnostic(&diagnostic_app, diagnostic.level, diagnostic.event);
        });
    Ok(WorkerSupervisorConfig {
        max_in_flight: 4,
        cancellation_grace: StdDuration::from_secs(2),
        startup_timeout: StdDuration::from_secs(15),
        max_record_bytes: report_worker::MAX_WORKER_RECORD_BYTES,
        max_stderr_bytes: 256 * 1024,
        expected_package_version: env!("CARGO_PKG_VERSION").to_owned(),
        service_configuration: ServiceConfiguration {
            parser_version: "1.20.0".to_owned(),
            pricing_version,
            pricing_digest,
            formatter_version,
            formatter_digest,
            default_page_size: 100,
            max_page_size: 500,
            max_heatmap_cells: 2_000,
        },
        path_authority: PathAuthority {
            source_roots: roots,
        },
        diagnostic_sink: Some(diagnostic_sink),
    })
}

fn worker_launch_arguments() -> Vec<OsString> {
    vec![
        OsString::from("--agent-report-worker"),
        OsString::from("--max-in-flight"),
        OsString::from("4"),
        OsString::from("--protocol-version"),
        OsString::from(WORKER_PROTOCOL_VERSION.to_string()),
    ]
}

fn supervisor_error(
    _error: impl std::fmt::Display,
    operation_id: Option<&str>,
) -> NativeReportError {
    NativeReportError::new(
        "REPORT_UNAVAILABLE",
        "The native report worker is unavailable. Try the operation again.",
        operation_id,
        true,
    )
}

fn ensure_supervisor(
    app: &AppHandle,
    state: &NativeReportState,
) -> Result<Arc<WorkerSupervisor>, NativeReportError> {
    let roots = state
        .active_roots
        .lock()
        .map_err(|_| NativeReportError::protocol("The report root state is unavailable.", None))?
        .clone();
    if roots.is_empty() {
        return Err(NativeReportError::new(
            "REPORT_DISCOVERY_FAILED",
            "Search the selected log folders before opening a report.",
            None,
            true,
        ));
    }
    let mut slot = state.supervisor.lock().map_err(|_| {
        NativeReportError::protocol("The report worker state is unavailable.", None)
    })?;
    if let Some((active_roots, supervisor)) = slot.as_ref()
        && active_roots == &roots
    {
        return Ok(Arc::clone(supervisor));
    }
    if let Some((_active_roots, supervisor)) = slot.take() {
        supervisor
            .shutdown()
            .map_err(|error| supervisor_error(error, None))?;
    }
    let executable = worker_executable()?;
    let launch = WorkerLaunchSpec {
        executable,
        arguments: worker_launch_arguments(),
        environment: BTreeMap::new(),
    };
    let supervisor = WorkerSupervisor::spawn(launch, worker_supervisor_config(app, roots.clone())?)
        .map_err(|error| supervisor_error(error, None))?;
    supervisor
        .wait_until_ready()
        .map_err(|error| supervisor_error(error, None))?;
    *slot = Some((roots, Arc::clone(&supervisor)));
    Ok(supervisor)
}

async fn execute_worker_request(
    app: AppHandle,
    request: TrustedWorkerRequest,
    export: bool,
) -> Result<Value, NativeReportError> {
    let operation_id = request.envelope().operation_id.clone();
    let join_operation_id = operation_id.clone();
    let operation = request.envelope().operation.clone();
    let diagnostic_app = app.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<NativeReportState>();
        let supervisor = ensure_supervisor(&app, &state)?;
        let (terminal_tx, terminal_rx) = mpsc::sync_channel(1);
        let observer = Arc::new(TauriOperationObserver {
            app: app.clone(),
            terminal: Mutex::new(Some(terminal_tx)),
        });
        supervisor
            .submit(request, observer)
            .map_err(|error| supervisor_error(error, Some(&operation_id)))?;
        match terminal_rx.recv() {
            Ok(HostTerminalOutcome::Result(result)) if export => {
                project_export_result(result.result, &state)
            }
            Ok(HostTerminalOutcome::Result(result)) => {
                project_worker_result(&operation, result.result, &state)
            }
            Ok(HostTerminalOutcome::Error(result)) => Err(result.error.into()),
            Ok(HostTerminalOutcome::Cancelled(result)) => Err(result.error.into()),
            Err(_) => Err(NativeReportError::new(
                "REPORT_UNAVAILABLE",
                "The report worker stopped before completing the operation.",
                Some(&operation_id),
                true,
            )),
        }
    })
    .await
    .map_err(|_| {
        NativeReportError::new(
            "REPORT_UNAVAILABLE",
            "The native report task stopped unexpectedly.",
            Some(&join_operation_id),
            true,
        )
    })?
    .inspect_err(|_error| {
        let _ = record_diagnostic(&diagnostic_app, "error", "report_worker_operation");
    })
}

async fn execute_path_free(
    app: AppHandle,
    operation: &'static str,
    request: Value,
) -> Result<Value, NativeReportError> {
    execute_worker_request(app, wire_request(operation, request)?, false).await
}

#[tauri::command]
async fn preflight_report(app: AppHandle, request: Value) -> Result<Value, NativeReportError> {
    execute_path_free(app, "preflight_report", request).await
}

#[tauri::command]
async fn open_snapshot(app: AppHandle, request: Value) -> Result<Value, NativeReportError> {
    execute_path_free(app, "open_snapshot", request).await
}

#[tauri::command]
async fn get_summary(app: AppHandle, request: Value) -> Result<Value, NativeReportError> {
    execute_path_free(app, "get_summary", request).await
}

#[tauri::command]
async fn list_agents(app: AppHandle, request: Value) -> Result<Value, NativeReportError> {
    execute_path_free(app, "list_agents", request).await
}

#[tauri::command]
async fn list_turns(app: AppHandle, request: Value) -> Result<Value, NativeReportError> {
    execute_path_free(app, "list_turns", request).await
}

#[tauri::command]
async fn list_events(app: AppHandle, request: Value) -> Result<Value, NativeReportError> {
    execute_path_free(app, "list_events", request).await
}

#[tauri::command]
async fn query_time_range(app: AppHandle, request: Value) -> Result<Value, NativeReportError> {
    execute_path_free(app, "query_time_range", request).await
}

#[tauri::command]
async fn query_sequence(app: AppHandle, request: Value) -> Result<Value, NativeReportError> {
    execute_path_free(app, "query_sequence", request).await
}

#[tauri::command]
async fn query_coordination(app: AppHandle, request: Value) -> Result<Value, NativeReportError> {
    execute_path_free(app, "query_coordination", request).await
}

#[tauri::command]
async fn get_event_details(app: AppHandle, request: Value) -> Result<Value, NativeReportError> {
    execute_path_free(app, "get_event_details", request).await
}

#[tauri::command]
async fn refresh_snapshot(app: AppHandle, request: Value) -> Result<Value, NativeReportError> {
    execute_path_free(app, "refresh_snapshot", request).await
}

#[tauri::command]
async fn close_snapshot(app: AppHandle, request: Value) -> Result<Value, NativeReportError> {
    execute_path_free(app, "close_snapshot", request).await
}

fn export_target(
    app: &AppHandle,
    mode: ExportModeWire,
) -> Result<Option<PathBuf>, NativeReportError> {
    let selected = match mode {
        ExportModeWire::Summary => app
            .dialog()
            .file()
            .set_file_name("agent-report-summary.html")
            .blocking_save_file(),
        ExportModeWire::Directory => app.dialog().file().blocking_pick_folder(),
    };
    let Some(selected) = selected else {
        return Ok(None);
    };
    let mut target = selected.into_path().map_err(|_| {
        NativeReportError::new(
            "REPORT_WRITE_FAILED",
            "The selected export location is unavailable.",
            None,
            true,
        )
    })?;
    if mode == ExportModeWire::Directory {
        target.push("agent-report-export");
    }
    if target.exists()
        && !app
            .dialog()
            .message("The selected export already exists. Replace it?")
            .title("Replace Agent Report export")
            .buttons(MessageDialogButtons::OkCancelCustom(
                "Replace".to_owned(),
                "Cancel".to_owned(),
            ))
            .blocking_show()
    {
        return Ok(None);
    }
    Ok(Some(target))
}

#[tauri::command]
async fn export_snapshot(
    app: AppHandle,
    request: Value,
) -> Result<Option<Value>, NativeReportError> {
    let request_object = request_object(&request)?;
    let operation_id = required_string(request_object, "operationId", None)?.to_owned();
    let snapshot_id =
        required_string(request_object, "snapshotId", Some(&operation_id))?.to_owned();
    let mode = match required_string(request_object, "mode", Some(&operation_id))? {
        "summary" => ExportModeWire::Summary,
        "directory" => ExportModeWire::Directory,
        _ => {
            return Err(NativeReportError::protocol(
                "The export mode is invalid.",
                Some(&operation_id),
            ));
        }
    };
    let Some(target) = export_target(&app, mode)? else {
        return Ok(None);
    };
    let replace = target.exists();
    let supervisor_app = app.clone();
    let supervisor = tauri::async_runtime::spawn_blocking(move || {
        let state = supervisor_app.state::<NativeReportState>();
        ensure_supervisor(&supervisor_app, &state)
    })
    .await
    .map_err(|_| supervisor_error("native export task stopped", Some(&operation_id)))??;
    let grant = supervisor
        .grant_output_target(&operation_id, &target, replace)
        .map_err(|error| supervisor_error(error, Some(&operation_id)))?;
    let trusted = TrustedWorkerRequest::export(
        &operation_id,
        &snapshot_id,
        AutomationSurfaceWire::Tauri,
        Some(mode),
        false,
        grant,
    )
    .map_err(|error| supervisor_error(error, Some(&operation_id)))?;
    execute_worker_request(app, trusted, true).await.map(Some)
}

#[tauri::command]
async fn cancel_operation(app: AppHandle, request: Value) -> Result<(), NativeReportError> {
    let request = request_object(&request)?;
    let operation_id = required_string(request, "operationId", None)?.to_owned();
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<NativeReportState>();
        let slot = state.supervisor.lock().map_err(|_| {
            NativeReportError::protocol(
                "The report worker state is unavailable.",
                Some(&operation_id),
            )
        })?;
        let supervisor = slot
            .as_ref()
            .map(|(_, supervisor)| Arc::clone(supervisor))
            .ok_or_else(|| {
                NativeReportError::new(
                    "REPORT_UNAVAILABLE",
                    "There is no active report worker operation.",
                    Some(&operation_id),
                    true,
                )
            })?;
        drop(slot);
        supervisor
            .cancel(&operation_id)
            .map_err(|error| supervisor_error(error, Some(&operation_id)))
    })
    .await
    .map_err(|_| {
        NativeReportError::new(
            "REPORT_UNAVAILABLE",
            "The cancellation task stopped unexpectedly.",
            None,
            true,
        )
    })?
}

#[tauri::command]
#[allow(
    deprecated,
    reason = "open only a native-registry export selected by the user"
)]
fn reopen_export(
    app: AppHandle,
    state: State<'_, NativeReportState>,
    request: Value,
) -> Result<(), NativeReportError> {
    let request = request_object(&request)?;
    let export_id = required_string(request, "exportId", None)?;
    let target = state
        .exports
        .lock()
        .map_err(|_| NativeReportError::protocol("The export registry is unavailable.", None))?
        .get(export_id)
        .cloned()
        .ok_or_else(|| {
            NativeReportError::new(
                "REPORT_NOT_FOUND",
                "The selected export is no longer available.",
                None,
                true,
            )
        })?;
    app.shell()
        .open(target.to_string_lossy().into_owned(), None)
        .map_err(|_| {
            NativeReportError::new(
                "REPORT_UNAVAILABLE",
                "The selected export could not be opened.",
                None,
                true,
            )
        })
}

#[tauri::command]
#[allow(
    deprecated,
    reason = "open only a source resolved through native path authority"
)]
fn open_source_location(
    app: AppHandle,
    state: State<'_, NativeReportState>,
    request: Value,
) -> Result<(), NativeReportError> {
    let request = request_object(&request)?;
    let snapshot_id = required_string(request, "snapshotId", None)?;
    let source_ref = required_string(request, "sourceRef", None)?;
    let source = resolve_snapshot_source_ref(&state, snapshot_id, source_ref)?;
    app.shell()
        .open(source.to_string_lossy().into_owned(), None)
        .map_err(|_| {
            NativeReportError::new(
                "REPORT_UNAVAILABLE",
                "The selected source could not be opened.",
                None,
                true,
            )
        })
}

#[derive(Clone, Copy, Debug)]
struct CatalogDateRange {
    from: Option<DateTime<Utc>>,
    to_exclusive: Option<DateTime<Utc>>,
}

impl CatalogDateRange {
    fn parse(from_date: &str, to_date: &str) -> Result<Self, String> {
        let range = Self {
            from: parse_catalog_boundary(from_date, "From", false)?,
            to_exclusive: parse_catalog_boundary(to_date, "To", true)?,
        };
        if range
            .from
            .zip(range.to_exclusive)
            .is_some_and(|(from, to)| from >= to)
        {
            return Err("From date and hour must not be after To date and hour".to_owned());
        }
        Ok(range)
    }

    fn includes_entry(&self, entry: &DiscoveryEntry) -> bool {
        if self.from.is_none() && self.to_exclusive.is_none() {
            return true;
        }
        let Ok(created_at) = DateTime::parse_from_rfc3339(&entry.started_at) else {
            return true;
        };
        let Some(updated_at) = activity_timestamp(entry.modified_at_ns) else {
            return true;
        };
        let created_at = created_at.with_timezone(&Utc);
        !self
            .to_exclusive
            .is_some_and(|to_exclusive| created_at >= to_exclusive)
            && !self.from.is_some_and(|from| updated_at < from)
    }
}

fn parse_catalog_boundary(
    value: &str,
    label: &str,
    upper: bool,
) -> Result<Option<DateTime<Utc>>, String> {
    let value = value.trim();
    if value.is_empty() {
        return Ok(None);
    }
    let (parsed, increment) = if let Ok(date) = NaiveDate::parse_from_str(value, "%Y-%m-%d") {
        (
            date.and_hms_opt(0, 0, 0).expect("midnight is a valid time"),
            Duration::days(1),
        )
    } else if value.len() == 13
        && let Ok(hour) = NaiveDateTime::parse_from_str(&format!("{value}:00"), "%Y-%m-%dT%H:%M")
    {
        (hour, Duration::hours(1))
    } else if let Ok(hour) = NaiveDateTime::parse_from_str(value, "%Y-%m-%dT%H:%M") {
        if hour.minute() != 0 {
            return Err(format!(
                "Invalid {label} date/hour '{value}'; expected a whole UTC hour"
            ));
        }
        (hour, Duration::hours(1))
    } else {
        return Err(format!(
            "Invalid {label} date/hour '{value}'; expected YYYY-MM-DD or YYYY-MM-DDTHH"
        ));
    };
    let parsed = DateTime::from_naive_utc_and_offset(parsed, Utc);
    Ok(Some(if upper { parsed + increment } else { parsed }))
}

fn activity_timestamp(timestamp_ns: i64) -> Option<DateTime<Utc>> {
    DateTime::from_timestamp(
        timestamp_ns.div_euclid(1_000_000_000),
        u32::try_from(timestamp_ns.rem_euclid(1_000_000_000)).ok()?,
    )
}

/// Search controls accepted from the desktop webview.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SearchRequest {
    /// Caller-selected log roots.
    pub roots: Vec<PathBuf>,
    /// Optional persistent native index path.
    pub index_path: Option<PathBuf>,
    /// Optional Codex app state database used to resolve sidebar task titles.
    #[serde(default)]
    pub state_db_path: Option<PathBuf>,
    /// Case-insensitive query over normalized metadata.
    pub query: String,
    /// Optional inclusive UTC start date or hour.
    #[serde(default)]
    pub from_date: String,
    /// Optional inclusive UTC end date or hour.
    #[serde(default)]
    pub to_date: String,
    /// Whether descendant agent rollouts should appear as rows.
    pub include_descendants: bool,
    /// Optional bounded native worker count.
    pub workers: Option<usize>,
}

/// One privacy-bounded row returned to the webview.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CatalogEntry {
    /// Root or child Codex thread identifier.
    pub thread_id: String,
    /// Empty for roots; populated only for descendant rows.
    pub parent_thread_id: String,
    /// Codex app task title when available, otherwise the bounded derived title.
    pub task_title: String,
    /// Recorded session timestamp.
    pub started_at: String,
    /// Last observed rollout activity timestamp.
    pub last_activity_at: String,
    /// Recorded workspace path.
    pub workspace: String,
    /// Exact local rollout path.
    pub source_path: String,
    /// Recorded agent path.
    pub agent_path: String,
    /// Recorded runtime nickname.
    pub agent_nickname: String,
    /// Number of cross-root delegation sources found in the rollout.
    pub delegation_count: usize,
    /// Optional bounded read diagnostic.
    pub diagnostic: Option<String>,
}

/// Desktop catalog search response.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SearchResponse {
    /// Filtered root or root-and-descendant rows.
    pub entries: Vec<CatalogEntry>,
    /// Native scan and cache statistics.
    pub stats: DiscoveryStats,
}

/// One determinate progress update from the report renderer.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ReportGenerationProgress {
    pub completed: u8,
    pub total: u8,
    pub item_completed: Option<usize>,
    pub item_total: Option<usize>,
    pub label: String,
    pub detail: String,
    pub worker: Option<String>,
}

/// Initial local locations suggested by the native application.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopDefaults {
    /// Existing Codex stores registered behind opaque native references.
    pub roots: Vec<RootReferenceDto>,
    /// Whether the native diagnostic log location is available.
    pub diagnostics_available: bool,
}

/// Request to search again and write a privacy-bounded HTML catalog.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ExportCatalogRequest {
    /// Search contract that determines exported rows.
    pub search: CatalogSearchRequest,
}

/// Privacy-bounded catalog request received from the webview.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CatalogSearchRequest {
    pub root_refs: Vec<String>,
    pub query: String,
    #[serde(default)]
    pub from_date: String,
    #[serde(default)]
    pub to_date: String,
    pub include_descendants: bool,
    pub workers: Option<usize>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
struct CatalogDiagnosticDto {
    code: String,
    message: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
struct CatalogEntryDto {
    thread_id: String,
    parent_thread_id: String,
    task_title: String,
    started_at: String,
    last_activity_at: String,
    workspace_label: String,
    source_ref: String,
    source_label: String,
    agent_label: String,
    agent_nickname: String,
    delegation_count: usize,
    diagnostic: Option<CatalogDiagnosticDto>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
struct CatalogSearchResponseDto {
    entries: Vec<CatalogEntryDto>,
    stats: DiscoveryStats,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
struct DiscoveryProgressDto {
    completed_files: usize,
    candidate_files: usize,
    #[serde(rename = "sourceLabel")]
    source_label: String,
    source: agent_report_core::DiscoverySource,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
struct CatalogExportResultDto {
    export_id: String,
    display_name: String,
    entry_count: usize,
}

/// Result of one native catalog export.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ExportResult {
    /// Exact written output path.
    pub output_path: PathBuf,
    /// Number of rows written.
    pub entry_count: usize,
}

/// Request to invoke the bundled full renderer for one selected root.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct GenerateReportRequest {
    /// Selected root thread identifier.
    pub thread_id: String,
    /// Log roots used to resolve its descendants.
    pub roots: Vec<PathBuf>,
    /// User-selected report output path.
    pub output_path: PathBuf,
    /// Whether native spawned descendants should be included.
    pub include_children: bool,
    /// Whether cross-root delegation links should be followed.
    pub include_delegations: bool,
    /// Number of bounded worker threads used by the renderer.
    pub workers: usize,
}

/// Search caller-selected roots synchronously for tests and native commands.
pub fn search_catalog_sync(request: SearchRequest) -> Result<SearchResponse, String> {
    search_catalog_with_progress(request, |_| {})
}

fn search_catalog_with_progress<F>(
    request: SearchRequest,
    progress: F,
) -> Result<SearchResponse, String>
where
    F: Fn(DiscoveryProgress),
{
    if request.roots.is_empty() {
        return Err("Select at least one Codex log folder".to_owned());
    }
    let date_range = CatalogDateRange::parse(&request.from_date, &request.to_date)?;
    let paths = collect_rollout_paths(&request.roots).map_err(|error| error.to_string())?;
    let mut response = index_rollouts(
        DiscoveryRequest {
            version: PROTOCOL_VERSION,
            paths,
            index_path: request.index_path,
            workers: request.workers,
        },
        progress,
    )
    .map_err(|error| error.to_string())?;
    if let Some(state_path) = request.state_db_path.as_deref() {
        let thread_ids = response
            .entries
            .iter()
            .filter_map(|entry| {
                entry
                    .identity
                    .as_ref()
                    .map(|identity| identity.thread_id.clone())
            })
            .collect::<Vec<_>>();
        if let Ok(titles) = read_codex_task_titles(state_path, thread_ids.clone()) {
            for entry in &mut response.entries {
                if let Some(title) = entry
                    .identity
                    .as_ref()
                    .and_then(|identity| titles.get(&identity.thread_id))
                {
                    entry.task_title.clone_from(title);
                }
            }
        }
        if let Ok(parents) = read_codex_task_parents(state_path, thread_ids) {
            for entry in &mut response.entries {
                if let Some(identity) = entry.identity.as_mut() {
                    identity.parent_thread_id = parents
                        .get(&identity.thread_id)
                        .cloned()
                        .unwrap_or_default();
                }
            }
        }
    }
    Ok(filter_catalog(
        response,
        &request.query,
        request.include_descendants,
        date_range,
    ))
}

fn filter_catalog(
    response: DiscoveryResponse,
    query: &str,
    include_descendants: bool,
    date_range: CatalogDateRange,
) -> SearchResponse {
    let normalized_query = query.trim().to_lowercase();
    let mut entries = response
        .entries
        .into_iter()
        .filter_map(|entry| {
            if !date_range.includes_entry(&entry) {
                return None;
            }
            let identity = entry.identity?;
            let last_activity_at = activity_timestamp(entry.modified_at_ns)?.to_rfc3339();
            if !include_descendants && !identity.parent_thread_id.is_empty() {
                return None;
            }
            let catalog_entry = CatalogEntry {
                thread_id: identity.thread_id,
                parent_thread_id: identity.parent_thread_id,
                task_title: entry.task_title,
                started_at: entry.started_at,
                last_activity_at,
                workspace: entry.workspace,
                source_path: entry.path,
                agent_path: identity.agent_path,
                agent_nickname: identity.agent_nickname,
                delegation_count: entry.delegation_source_ids.len(),
                diagnostic: entry.diagnostic,
            };
            let searchable = format!(
                "{}\n{}\n{}\n{}\n{}\n{}",
                catalog_entry.task_title,
                catalog_entry.thread_id,
                catalog_entry.workspace,
                catalog_entry.source_path,
                catalog_entry.agent_path,
                catalog_entry.agent_nickname,
            )
            .to_lowercase();
            (normalized_query.is_empty() || searchable.contains(&normalized_query))
                .then_some(catalog_entry)
        })
        .collect::<Vec<_>>();
    entries.sort_by(|left, right| {
        right
            .last_activity_at
            .cmp(&left.last_activity_at)
            .then_with(|| right.started_at.cmp(&left.started_at))
            .then_with(|| left.source_path.cmp(&right.source_path))
    });
    SearchResponse {
        entries,
        stats: response.stats,
    }
}

fn codex_local_paths() -> (Option<PathBuf>, Option<PathBuf>) {
    let Some(home) = env::var_os("HOME").map(PathBuf::from) else {
        return (None, None);
    };
    let codex = home.join(".codex");
    (
        Some(
            codex
                .join("agent-report")
                .join("rollout-discovery-v2.sqlite3"),
        ),
        codex
            .join("state_5.sqlite")
            .is_file()
            .then(|| codex.join("state_5.sqlite")),
    )
}

fn resolve_catalog_search(
    request: CatalogSearchRequest,
    state: &NativeReportState,
) -> Result<SearchRequest, String> {
    if request.root_refs.is_empty() {
        return Err("Select at least one Codex log folder".to_owned());
    }
    let roots_registry = state
        .roots
        .lock()
        .map_err(|_| "root registry is unavailable".to_owned())?;
    let roots = request
        .root_refs
        .iter()
        .map(|root_ref| {
            roots_registry
                .get(root_ref)
                .cloned()
                .ok_or_else(|| "A selected report root is no longer available".to_owned())
        })
        .collect::<Result<Vec<_>, _>>()?;
    drop(roots_registry);
    let (index_path, state_db_path) = codex_local_paths();
    *state
        .active_roots
        .lock()
        .map_err(|_| "report root state is unavailable".to_owned())? = roots.clone();
    Ok(SearchRequest {
        roots,
        index_path,
        state_db_path,
        query: request.query,
        from_date: request.from_date,
        to_date: request.to_date,
        include_descendants: request.include_descendants,
        workers: request.workers,
    })
}

fn project_catalog_response(
    response: &SearchResponse,
    state: &NativeReportState,
) -> Result<CatalogSearchResponseDto, String> {
    let mut entries = Vec::with_capacity(response.entries.len());
    for entry in &response.entries {
        let path = PathBuf::from(&entry.source_path)
            .canonicalize()
            .map_err(|error| format!("unable to resolve discovered source: {error}"))?;
        let source_key = source_key_for_path(&path)?;
        state
            .source_keys
            .lock()
            .map_err(|_| "source registry is unavailable".to_owned())?
            .insert(source_key, path.clone());
        let source_ref = register_snapshot_source_ref(
            state,
            "catalog",
            &source_key_for_path(&path)?,
            path.clone(),
        )
        .map_err(|error| error.message)?;
        entries.push(CatalogEntryDto {
            thread_id: entry.thread_id.clone(),
            parent_thread_id: entry.parent_thread_id.clone(),
            task_title: entry.task_title.clone(),
            started_at: entry.started_at.clone(),
            last_activity_at: entry.last_activity_at.clone(),
            workspace_label: display_name(Path::new(&entry.workspace)),
            source_ref,
            source_label: display_name(&path),
            agent_label: display_name(Path::new(&entry.agent_path)),
            agent_nickname: entry.agent_nickname.clone(),
            delegation_count: entry.delegation_count,
            diagnostic: entry.diagnostic.as_ref().map(|_| CatalogDiagnosticDto {
                code: "REPORT_DISCOVERY_FAILED".to_owned(),
                message: "This rollout could not be read completely.".to_owned(),
            }),
        });
    }
    Ok(CatalogSearchResponseDto {
        entries,
        stats: response.stats.clone(),
    })
}

fn register_authorized_sources(roots: &[PathBuf], state: &NativeReportState) -> Result<(), String> {
    let paths = collect_rollout_paths(roots).map_err(|error| error.to_string())?;
    let mut registry = state
        .source_keys
        .lock()
        .map_err(|_| "source registry is unavailable".to_owned())?;
    registry.clear();
    for path in paths {
        let canonical = path
            .canonicalize()
            .map_err(|error| format!("unable to resolve discovered source: {error}"))?;
        registry.insert(source_key_for_path(&canonical)?, canonical);
    }
    Ok(())
}

/// Render one self-contained, escaped catalog document from normalized rows.
pub fn render_catalog_html(response: &SearchResponse) -> String {
    let rows = response
        .entries
        .iter()
        .map(|entry| {
            let source_text = encode_text(&entry.source_path);
            let source_markup = Url::from_file_path(Path::new(&entry.source_path))
                .ok()
                .map(|url| {
                    format!(
                        "<a href=\"{}\">{}</a>",
                        encode_double_quoted_attribute(url.as_str()),
                        source_text,
                    )
                })
                .unwrap_or_else(|| source_text.into_owned());
            format!(
                "<article class=\"run\"><p class=\"time\">{}</p><h2>{}</h2>\
                 <p class=\"thread\">{}</p><dl><dt>Workspace</dt><dd>{}</dd>\
                 <dt>Source</dt><dd>{}</dd></dl></article>",
                encode_text(&entry.last_activity_at),
                encode_text(if entry.task_title.is_empty() {
                    "Untitled Codex run"
                } else {
                    &entry.task_title
                }),
                encode_text(&entry.thread_id),
                encode_text(&entry.workspace),
                source_markup,
            )
        })
        .collect::<String>();
    format!(
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">\
         <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\
         <title>Agent report run index</title><style>\
         :root{{color-scheme:light;font-family:system-ui,sans-serif;background:#e8edf2;color:#132334}}\
         body{{max-width:980px;margin:0 auto;padding:48px 24px}}h1{{font-size:2.4rem;margin:0}}\
         .summary{{color:#52616f;margin:8px 0 32px}}.run{{background:#fff;border-left:5px solid #c77a19;\
         margin:14px 0;padding:18px 22px;box-shadow:0 8px 24px #1d304412}}.time,.thread{{font-family:monospace}}\
         .time{{color:#7b4a0c;font-size:.78rem;text-transform:uppercase}}h2{{margin:4px 0 8px}}\
         dl{{display:grid;grid-template-columns:90px 1fr;gap:5px 12px;margin-bottom:0}}dt{{font-weight:700}}\
         dd{{margin:0;overflow-wrap:anywhere}}</style></head><body><h1>Agent report run index</h1>\
         <p class=\"summary\">{} runs · {} scanned · {} reused from index</p>{}</body></html>",
        response.entries.len(),
        response.stats.scanned_files,
        response.stats.cached_files,
        rows,
    )
}

#[tauri::command]
fn desktop_defaults(
    app: AppHandle,
    state: State<'_, NativeReportState>,
) -> Result<DesktopDefaults, String> {
    let diagnostics_available = diagnostic_log_path(&app).is_ok();
    let Some(home) = env::var_os("HOME").map(PathBuf::from) else {
        return Ok(DesktopDefaults {
            roots: Vec::new(),
            diagnostics_available,
        });
    };
    let codex = home.join(".codex");
    let roots = [codex.join("sessions"), codex.join("archived_sessions")]
        .into_iter()
        .filter(|path| path.is_dir())
        .map(|path| register_root(&state, path))
        .collect::<Result<Vec<_>, _>>()?;
    Ok(DesktopDefaults {
        roots,
        diagnostics_available,
    })
}

#[tauri::command]
fn add_root(
    app: AppHandle,
    state: State<'_, NativeReportState>,
) -> Result<Vec<RootReferenceDto>, String> {
    let Some(selected) = app.dialog().file().blocking_pick_folder() else {
        return Ok(Vec::new());
    };
    let path = selected
        .into_path()
        .map_err(|error| format!("unable to resolve selected folder: {error}"))?;
    Ok(vec![register_root(&state, path)?])
}

#[tauri::command]
async fn search_rollouts(
    app: AppHandle,
    state: State<'_, NativeReportState>,
    request: CatalogSearchRequest,
    on_event: Channel<DiscoveryProgressDto>,
) -> Result<CatalogSearchResponseDto, String> {
    let request = resolve_catalog_search(request, &state)?;
    let state_app = app.clone();
    let result = match tauri::async_runtime::spawn_blocking(move || {
        register_authorized_sources(&request.roots, &state_app.state::<NativeReportState>())?;
        let response = search_catalog_with_progress(request, |event| {
            if event.completed_files == 1
                || event.completed_files == event.candidate_files
                || event.completed_files % 64 == 0
            {
                let _ = on_event.send(DiscoveryProgressDto {
                    completed_files: event.completed_files,
                    candidate_files: event.candidate_files,
                    source_label: display_name(Path::new(&event.path)),
                    source: event.source,
                });
            }
        })?;
        project_catalog_response(&response, &state_app.state::<NativeReportState>())
    })
    .await
    {
        Ok(result) => result,
        Err(error) => Err(format!("native search task failed: {error}")),
    };
    record_failed_result(&app, "search_rollouts", result)
}

#[tauri::command]
async fn export_catalog(
    app: AppHandle,
    state: State<'_, NativeReportState>,
    request: ExportCatalogRequest,
) -> Result<Option<CatalogExportResultDto>, String> {
    let Some(selected) = app
        .dialog()
        .file()
        .set_file_name("agent-report-index.html")
        .blocking_save_file()
    else {
        return Ok(None);
    };
    let output_path = selected
        .into_path()
        .map_err(|error| format!("unable to resolve selected output: {error}"))?;
    let search = resolve_catalog_search(request.search, &state)?;
    let state_app = app.clone();
    let result = match tauri::async_runtime::spawn_blocking(move || {
        let response = search_catalog_sync(search)?;
        ensure_output_parent(&output_path)?;
        fs::write(&output_path, render_catalog_html(&response))
            .map_err(|error| format!("unable to write catalog: {error}"))?;
        let output_path = output_path
            .canonicalize()
            .map_err(|error| format!("unable to resolve exported catalog: {error}"))?;
        let export_id = opaque_reference("export");
        state_app
            .state::<NativeReportState>()
            .exports
            .lock()
            .map_err(|_| "export registry is unavailable".to_owned())?
            .insert(export_id.clone(), output_path.clone());
        Ok(Some(CatalogExportResultDto {
            export_id,
            display_name: display_name(&output_path),
            entry_count: response.entries.len(),
        }))
    })
    .await
    {
        Ok(result) => result,
        Err(error) => Err(format!("native export task failed: {error}")),
    };
    record_failed_result(&app, "export_catalog", result)
}

#[tauri::command]
async fn generate_report(
    app: AppHandle,
    request: GenerateReportRequest,
    on_event: Channel<ReportGenerationProgress>,
) -> Result<ExportResult, String> {
    let result = generate_full_report(&app, request, &on_event).await;
    record_failed_result(&app, "generate_report", result)
}

#[tauri::command]
fn cancel_report_generation() -> Result<(), String> {
    REPORT_CANCEL_REQUESTED.store(true, Ordering::SeqCst);
    let child = REPORT_PROCESS
        .lock()
        .map_err(|_| "report process lock is unavailable".to_owned())?
        .take();
    if let Some(child) = child {
        terminate_process_tree(child.pid());
        let _ = child.kill();
    }
    Ok(())
}

#[cfg(unix)]
fn terminate_process_tree(pid: u32) {
    let output = Command::new("pgrep")
        .args(["-P", &pid.to_string()])
        .output();
    if let Ok(output) = output {
        for child_pid in String::from_utf8_lossy(&output.stdout)
            .lines()
            .filter_map(|value| value.trim().parse::<u32>().ok())
        {
            terminate_process_tree(child_pid);
            let _ = Command::new("kill")
                .args(["-KILL", &child_pid.to_string()])
                .status();
        }
    }
}

#[cfg(windows)]
fn terminate_process_tree(pid: u32) {
    let _ = Command::new("taskkill")
        .args(["/PID", &pid.to_string(), "/T", "/F"])
        .status();
}

fn renderer_override(value: Option<OsString>) -> Option<PathBuf> {
    value.filter(|path| !path.is_empty()).map(PathBuf::from)
}

fn full_report_arguments(request: &GenerateReportRequest) -> Vec<OsString> {
    let mut arguments = vec![
        OsString::from("--progress"),
        OsString::from("--codex-thread"),
        OsString::from(&request.thread_id),
        OsString::from("--output"),
        request.output_path.as_os_str().to_owned(),
        OsString::from("--workers"),
        OsString::from(request.workers.to_string()),
    ];
    for root in &request.roots {
        arguments.push(OsString::from("--sessions-root"));
        arguments.push(root.as_os_str().to_owned());
    }
    if request.include_children {
        arguments.push(OsString::from("--include-children"));
    }
    if request.include_delegations {
        arguments.push(OsString::from("--include-delegations"));
    }
    arguments
}

fn completed_report(
    request: GenerateReportRequest,
    success: bool,
    status: String,
    stderr: &[u8],
) -> Result<ExportResult, String> {
    if !success {
        let diagnostic = String::from_utf8_lossy(stderr).trim().to_owned();
        return Err(format!(
            "full report renderer failed: {}",
            if diagnostic.is_empty() {
                status
            } else {
                diagnostic
            }
        ));
    }
    Ok(ExportResult {
        output_path: request.output_path,
        entry_count: 1,
    })
}

async fn generate_full_report(
    app: &AppHandle,
    request: GenerateReportRequest,
    on_event: &Channel<ReportGenerationProgress>,
) -> Result<ExportResult, String> {
    if request.thread_id.trim().is_empty() {
        return Err("Select a root run before generating a report".to_owned());
    }
    if !(1..=64).contains(&request.workers) {
        return Err("Worker threads must be between 1 and 64".to_owned());
    }
    ensure_output_parent(&request.output_path)?;
    let arguments = full_report_arguments(&request);
    REPORT_CANCEL_REQUESTED.store(false, Ordering::SeqCst);
    let command = if let Some(renderer) = renderer_override(env::var_os("AGENT_REPORT_COMMAND")) {
        app.shell().command(renderer).args(arguments)
    } else {
        app.shell()
            .sidecar("agent-report")
            .map_err(|error| format!("unable to prepare bundled full report renderer: {error}"))?
            .args(arguments)
    };
    let (mut receiver, child) = command
        .spawn()
        .map_err(|error| format!("unable to start full report renderer: {error}"))?;
    *REPORT_PROCESS
        .lock()
        .map_err(|_| "report process lock is unavailable".to_owned())? = Some(child);
    let mut stderr = Vec::new();
    let mut exit_code = None;
    while let Some(event) = receiver.recv().await {
        match event {
            CommandEvent::Stderr(line) => {
                if let Ok(text) = std::str::from_utf8(&line)
                    && let Some(payload) = text.strip_prefix("AGENT_REPORT_PROGRESS ")
                    && let Ok(progress) = serde_json::from_str::<ReportGenerationProgress>(payload)
                {
                    let _ = on_event.send(progress);
                } else {
                    stderr.extend_from_slice(&line);
                    stderr.push(b'\n');
                }
            }
            CommandEvent::Terminated(payload) => exit_code = payload.code,
            CommandEvent::Error(error) => {
                stderr.extend_from_slice(error.as_bytes());
                stderr.push(b'\n');
            }
            CommandEvent::Stdout(_) => {}
            _ => {}
        }
    }
    REPORT_PROCESS
        .lock()
        .map_err(|_| "report process lock is unavailable".to_owned())?
        .take();
    if REPORT_CANCEL_REQUESTED.swap(false, Ordering::SeqCst) {
        return Err("Report generation cancelled".to_owned());
    }
    completed_report(
        request,
        exit_code == Some(0),
        exit_code.map_or_else(
            || "terminated without an exit code".to_owned(),
            |code| format!("exit status {code}"),
        ),
        &stderr,
    )
}

fn ensure_output_parent(path: &Path) -> Result<(), String> {
    let Some(parent) = path.parent() else {
        return Err("Select an output path with a parent folder".to_owned());
    };
    fs::create_dir_all(parent).map_err(|error| format!("unable to create output folder: {error}"))
}

/// Resolve and validate an existing local HTML artifact before a report webview loads it.
pub fn report_window_url(path: &Path) -> Result<Url, String> {
    let canonical = path
        .canonicalize()
        .map_err(|error| format!("unable to resolve report {}: {error}", path.display()))?;
    if !canonical.is_file() {
        return Err(format!("report is not a file: {}", canonical.display()));
    }
    let is_html = canonical
        .extension()
        .and_then(|extension| extension.to_str())
        .is_some_and(|extension| {
            extension.eq_ignore_ascii_case("html") || extension.eq_ignore_ascii_case("htm")
        });
    if !is_html {
        return Err(format!(
            "report must be an HTML file: {}",
            canonical.display()
        ));
    }
    Url::from_file_path(&canonical).map_err(|_| {
        format!(
            "unable to convert report path to a local URL: {}",
            canonical.display()
        )
    })
}

/// Return whether a report popup is its existing, same-folder sequence companion.
pub fn report_popup_is_allowed(opener_path: &Path, popup_url: &Url) -> bool {
    let Some(stem) = opener_path.file_stem().and_then(|stem| stem.to_str()) else {
        return false;
    };
    let Some(extension) = opener_path
        .extension()
        .and_then(|extension| extension.to_str())
    else {
        return false;
    };
    let Some(parent) = opener_path.parent() else {
        return false;
    };
    let expected = parent.join(format!("{stem}-sequence.{extension}"));
    let Ok(candidate) = popup_url.to_file_path() else {
        return false;
    };
    expected
        .canonicalize()
        .ok()
        .zip(candidate.canonicalize().ok())
        .is_some_and(|(expected, candidate)| expected == candidate)
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
struct ParentReportRequest {
    thread_id: String,
    task_title: String,
    source_path: String,
}

fn parent_report_request(url: &Url) -> Option<ParentReportRequest> {
    if url.scheme() != "agent-report"
        || url.host_str() != Some("view-parent-report")
        || !matches!(url.path(), "" | "/")
    {
        return None;
    }
    let mut thread_id = String::new();
    let mut task_title = String::new();
    let mut source_path = String::new();
    for (key, value) in url.query_pairs() {
        match key.as_ref() {
            "thread_id" => thread_id = value.into_owned(),
            "title" => task_title = value.into_owned(),
            "source_path" => source_path = value.into_owned(),
            _ => {}
        }
    }
    if thread_id.is_empty()
        || thread_id.len() > 160
        || !thread_id
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || ".-_:/".contains(character))
        || task_title.chars().count() > 1_024
        || source_path.chars().count() > 8_192
    {
        return None;
    }
    Some(ParentReportRequest {
        thread_id,
        task_title,
        source_path,
    })
}

#[tauri::command]
async fn open_report_window(
    app: AppHandle,
    state: State<'_, NativeReportState>,
    export_id: String,
) -> Result<(), String> {
    let output_path = state
        .exports
        .lock()
        .map_err(|_| "export registry is unavailable".to_owned())?
        .get(&export_id)
        .cloned()
        .ok_or_else(|| "The selected export is no longer available".to_owned())?;
    let output_path = if output_path.is_dir() {
        output_path.join("index.html")
    } else {
        output_path
    };
    let result = (|| {
        let url = report_window_url(&output_path)?;
        let report_path = url.to_file_path().map_err(|_| {
            format!(
                "unable to recover the local report path from URL: {}",
                url.as_str()
            )
        })?;
        let title = output_path
            .file_stem()
            .and_then(|stem| stem.to_str())
            .filter(|stem| !stem.is_empty())
            .unwrap_or("Report");
        let label = format!(
            "report-{}",
            REPORT_WINDOW_COUNTER.fetch_add(1, Ordering::Relaxed)
        );
        let navigation_app = app.clone();
        let popup_app = app.clone();
        WebviewWindowBuilder::new(&app, label, WebviewUrl::CustomProtocol(url))
            .title(format!("Agent Report — {title}"))
            .inner_size(1280.0, 800.0)
            .min_inner_size(720.0, 480.0)
            .on_navigation(move |navigation_url| {
                let Some(request) = parent_report_request(navigation_url) else {
                    return true;
                };
                if navigation_app.emit("view-parent-report", request).is_err() {
                    let _ = record_diagnostic(&navigation_app, "error", "view_parent_report");
                }
                false
            })
            .on_new_window(move |popup_url, _features| {
                let allowed = report_popup_is_allowed(&report_path, &popup_url);
                let _ = record_diagnostic(
                    &popup_app,
                    if allowed { "info" } else { "warning" },
                    if allowed {
                        "sequence_popup_allowed"
                    } else {
                        "sequence_popup_denied"
                    },
                );
                if allowed {
                    NewWindowResponse::Allow
                } else {
                    NewWindowResponse::Deny
                }
            })
            .build()
            .map_err(|error| format!("unable to open report window: {error}"))?;
        Ok(())
    })();
    record_failed_result(&app, "open_report_window", result)
}

#[tauri::command]
fn record_client_error(app: AppHandle, context: String, _message: String) -> Result<(), String> {
    let event = context
        .chars()
        .take(64)
        .map(|character| {
            if character.is_ascii_alphanumeric() || matches!(character, '-' | '_' | '.') {
                character
            } else {
                '_'
            }
        })
        .collect::<String>();
    record_diagnostic(&app, "error", &format!("webview.{event}"))
}

#[tauri::command]
#[allow(
    deprecated,
    reason = "reuse the already bundled shell opener for one native-only local log path"
)]
fn open_diagnostic_log(app: AppHandle) -> Result<(), String> {
    let log_path = diagnostic_log_path(&app)?;
    if !log_path.is_file() {
        append_diagnostic_entry(&log_path, "info", "diagnostic_log_created")?;
    }
    let result = app
        .shell()
        .open(log_path.to_string_lossy().into_owned(), None)
        .map_err(|error| format!("unable to open diagnostic log: {error}"));
    record_failed_result(&app, "open_diagnostic_log", result)
}

/// Build and run the desktop application with a deliberately narrow command surface.
pub fn run() {
    tauri::Builder::default()
        .manage(NativeReportState::default())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            initialize_diagnostics(app.handle()).map_err(std::io::Error::other)?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            desktop_defaults,
            add_root,
            search_rollouts,
            export_catalog,
            preflight_report,
            open_snapshot,
            get_summary,
            list_agents,
            list_turns,
            list_events,
            query_time_range,
            query_sequence,
            query_coordination,
            get_event_details,
            refresh_snapshot,
            export_snapshot,
            close_snapshot,
            cancel_operation,
            reopen_export,
            open_source_location,
            generate_report,
            cancel_report_generation,
            open_report_window,
            record_client_error,
            open_diagnostic_log,
        ])
        .run(tauri::generate_context!())
        .expect("error while running agent report desktop application");
}

#[cfg(test)]
mod tests {
    use std::ffi::OsString;
    use std::fs;
    use std::path::PathBuf;
    #[cfg(unix)]
    use std::process::Command;
    #[cfg(unix)]
    use std::thread;
    #[cfg(unix)]
    use std::time::Duration;

    use serde_json::Value;
    use tempfile::TempDir;

    #[cfg(unix)]
    use super::terminate_process_tree;
    use super::{
        DIAGNOSTIC_LOG_MAX_BYTES, GenerateReportRequest, NativeReportState,
        append_diagnostic_entry, full_report_arguments, parent_report_request,
        project_worker_result, register_snapshot_revision, register_snapshot_source_ref,
        renderer_override, resolve_snapshot_source_ref, wire_request, worker_launch_arguments,
    };

    fn state_with_source_reference(directory: &TempDir) -> (NativeReportState, String, String) {
        let state = NativeReportState::default();
        let snapshot_id = "snap_46b9630e96ce4dc5a678a517".to_owned();
        register_snapshot_revision(&state, &snapshot_id, "revision-1")
            .expect("register snapshot revision");
        let source_ref = register_snapshot_source_ref(
            &state,
            &snapshot_id,
            "source-key-1",
            directory.path().join("rollout.jsonl"),
        )
        .expect("register source reference");
        (state, snapshot_id, source_ref)
    }

    #[test]
    fn open_source_location_rejects_a_reference_after_snapshot_close() {
        let directory = TempDir::new().expect("create temporary directory");
        let (state, snapshot_id, source_ref) = state_with_source_reference(&directory);

        project_worker_result(
            "close_snapshot",
            serde_json::json!({"snapshot_id":snapshot_id.clone(),"closed":true})
                .as_object()
                .expect("close result object")
                .clone(),
            &state,
        )
        .expect("project close result");

        assert!(resolve_snapshot_source_ref(&state, &snapshot_id, &source_ref).is_err());
        assert!(
            state
                .source_refs
                .lock()
                .expect("source registry")
                .is_empty()
        );
        assert!(
            state
                .source_refs_by_key
                .lock()
                .expect("reverse source registry")
                .is_empty()
        );
    }

    #[test]
    fn open_source_location_rejects_an_old_reference_after_changed_refresh() {
        let directory = TempDir::new().expect("create temporary directory");
        let (state, snapshot_id, source_ref) = state_with_source_reference(&directory);

        project_worker_result(
            "refresh_snapshot",
            serde_json::json!({
                "changed": true,
                "snapshot": {
                    "snapshot_id": snapshot_id.clone(),
                    "revision_id": "revision-2",
                    "scope": {
                        "root_thread_id": "root-thread",
                        "include_children": false,
                        "include_collaborators": false
                    }
                }
            })
            .as_object()
            .expect("refresh result object")
            .clone(),
            &state,
        )
        .expect("project refresh result");

        assert!(resolve_snapshot_source_ref(&state, &snapshot_id, &source_ref).is_err());
        assert_eq!(
            state
                .snapshot_revisions
                .lock()
                .expect("snapshot revision registry")
                .get(&snapshot_id)
                .map(String::as_str),
            Some("revision-2"),
        );
    }

    #[test]
    fn translates_every_workspace_command_to_the_explicit_worker_shape() {
        let page = |filters: Value, sort: Value| {
            serde_json::json!({
                "operationId": "op_75ffcf97671b4ccbaf96790c",
                "snapshotId": "snap_46b9630e96ce4dc5a678a517",
                "cursor": null,
                "pageSize": 100,
                "filters": filters,
                "sort": sort,
            })
        };
        let sort = |key: &str, tie_break: &str| {
            serde_json::json!({
                "key": key,
                "direction": "ascending",
                "tieBreakKey": tie_break,
                "tieBreakDirection": "ascending",
            })
        };
        let cases = [
            (
                "preflight_report",
                serde_json::json!({"operationId":"op_75ffcf97671b4ccbaf96790c","rootThreadId":"root","includeChildren":false,"includeCollaborators":false}),
            ),
            (
                "open_snapshot",
                serde_json::json!({"operationId":"op_75ffcf97671b4ccbaf96790c","rootThreadId":"root","includeChildren":false,"includeCollaborators":false,"preflightToken":"token","sourceRevision":"revision"}),
            ),
            (
                "get_summary",
                serde_json::json!({"operationId":"op_75ffcf97671b4ccbaf96790c","snapshotId":"snap_46b9630e96ce4dc5a678a517"}),
            ),
            (
                "list_agents",
                page(
                    serde_json::json!({"query":"","state":null}),
                    sort("started_at", "agent_id"),
                ),
            ),
            (
                "list_turns",
                page(
                    serde_json::json!({"agentId":null,"state":null}),
                    sort("started_at", "turn_id"),
                ),
            ),
            (
                "list_events",
                page(
                    serde_json::json!({"agentId":null,"turnId":null,"kind":null,"fromTime":null,"toTime":null}),
                    sort("occurred_at", "event_id"),
                ),
            ),
            (
                "query_time_range",
                serde_json::json!({"operationId":"op_75ffcf97671b4ccbaf96790c","snapshotId":"snap_46b9630e96ce4dc5a678a517","fromTime":"2026-08-12T12:00:00Z","toTime":"2026-08-12T13:00:00Z","measure":"wall_time","groupBy":"agent","requestedResolutionMinutes":5,"maximumRows":20}),
            ),
            (
                "query_sequence",
                page(
                    serde_json::json!({"focusAgentId":null,"eventKinds":[],"grouping":"none","includeReasoning":false}),
                    sort("occurred_at", "sequence_id"),
                ),
            ),
            (
                "query_coordination",
                page(
                    serde_json::json!({"workItemId":null,"delegatedRootId":null,"agentId":null,"operation":null,"evidence":null}),
                    sort("occurred_at", "coordination_id"),
                ),
            ),
            (
                "get_event_details",
                serde_json::json!({"operationId":"op_75ffcf97671b4ccbaf96790c","snapshotId":"snap_46b9630e96ce4dc5a678a517","eventId":"event-1"}),
            ),
            (
                "refresh_snapshot",
                serde_json::json!({"operationId":"op_75ffcf97671b4ccbaf96790c","snapshotId":"snap_46b9630e96ce4dc5a678a517"}),
            ),
            (
                "close_snapshot",
                serde_json::json!({"operationId":"op_75ffcf97671b4ccbaf96790c","snapshotId":"snap_46b9630e96ce4dc5a678a517"}),
            ),
        ];

        for (operation, request) in cases {
            let trusted = wire_request(operation, request).expect(operation);
            assert_eq!(trusted.envelope().operation, operation);
            assert!(
                trusted
                    .envelope()
                    .arguments
                    .keys()
                    .all(|key| !key.contains(char::is_uppercase))
            );
        }
    }

    #[test]
    fn launches_the_reserved_worker_entrypoint_without_colliding_with_classic_cli_input() {
        assert_eq!(
            worker_launch_arguments(),
            vec![
                OsString::from("--agent-report-worker"),
                OsString::from("--max-in-flight"),
                OsString::from("4"),
                OsString::from("--protocol-version"),
                OsString::from("1"),
            ]
        );
    }

    #[test]
    fn appends_structured_diagnostics_and_rotates_a_full_log() {
        let directory = TempDir::new().expect("create temporary directory");
        let log_path = directory.path().join("agent-report.log");
        let previous_path = directory.path().join("agent-report.previous.log");
        fs::write(&log_path, vec![b'x'; DIAGNOSTIC_LOG_MAX_BYTES as usize])
            .expect("seed a full diagnostic log");

        append_diagnostic_entry(&log_path, "error", "generate_report")
            .expect("append diagnostic entry");

        assert_eq!(
            fs::metadata(previous_path)
                .expect("read rotated log metadata")
                .len(),
            DIAGNOSTIC_LOG_MAX_BYTES,
        );
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(
                fs::metadata(directory.path().join("agent-report.previous.log"))
                    .expect("read rotated diagnostic metadata")
                    .permissions()
                    .mode()
                    & 0o777,
                0o600,
            );
        }
        let line = fs::read_to_string(log_path).expect("read current diagnostic log");
        let entry: Value = serde_json::from_str(line.trim()).expect("parse diagnostic JSON line");
        assert_eq!(entry["level"], "error");
        assert_eq!(entry["event"], "generate_report");
        assert_eq!(entry["message"], "Classic report generation failed.");
        assert!(!line.contains(directory.path().to_string_lossy().as_ref()));
        assert!(
            entry["timestamp"]
                .as_str()
                .is_some_and(|value| value.ends_with('Z'))
        );
    }

    #[cfg(unix)]
    #[test]
    fn diagnostic_logs_are_readable_and_writable_only_by_the_current_user() {
        use std::os::unix::fs::PermissionsExt;

        let directory = TempDir::new().expect("create temporary directory");
        let log_path = directory.path().join("agent-report.log");

        append_diagnostic_entry(&log_path, "warning", "sequence_popup_denied")
            .expect("append diagnostic entry");

        assert_eq!(
            fs::metadata(log_path)
                .expect("read diagnostic metadata")
                .permissions()
                .mode()
                & 0o777,
            0o600,
        );
    }

    #[cfg(windows)]
    #[test]
    fn diagnostic_logs_use_the_per_user_app_directory_acl_on_windows() {
        let directory = TempDir::new().expect("create temporary directory");
        let log_path = directory.path().join("agent-report.log");

        append_diagnostic_entry(&log_path, "warning", "sequence_popup_denied")
            .expect("append diagnostic entry using the inherited directory ACL");

        assert!(log_path.is_file());
    }

    #[test]
    fn defaults_to_bundled_renderer_without_an_override() {
        assert_eq!(renderer_override(None), None);
    }

    #[test]
    fn retains_an_explicit_development_renderer_override() {
        let path = PathBuf::from("/tmp/development-agent-report");

        assert_eq!(renderer_override(Some(OsString::from(&path))), Some(path));
    }

    #[test]
    fn passes_selected_roots_and_report_scope_to_the_renderer() {
        let request = GenerateReportRequest {
            thread_id: "root-thread".to_owned(),
            roots: vec![
                PathBuf::from("/tmp/sessions"),
                PathBuf::from("/tmp/archive"),
            ],
            output_path: PathBuf::from("/tmp/report.html"),
            include_children: true,
            include_delegations: true,
            workers: 6,
        };

        assert_eq!(
            full_report_arguments(&request),
            vec![
                OsString::from("--progress"),
                OsString::from("--codex-thread"),
                OsString::from("root-thread"),
                OsString::from("--output"),
                OsString::from("/tmp/report.html"),
                OsString::from("--workers"),
                OsString::from("6"),
                OsString::from("--sessions-root"),
                OsString::from("/tmp/sessions"),
                OsString::from("--sessions-root"),
                OsString::from("/tmp/archive"),
                OsString::from("--include-children"),
                OsString::from("--include-delegations"),
            ]
        );
    }

    #[test]
    fn omits_report_scope_flags_when_disabled() {
        let request = GenerateReportRequest {
            thread_id: "root-thread".to_owned(),
            roots: vec![PathBuf::from("/tmp/sessions")],
            output_path: PathBuf::from("/tmp/report.html"),
            include_children: false,
            include_delegations: false,
            workers: 1,
        };

        let arguments = full_report_arguments(&request);

        assert!(!arguments.contains(&OsString::from("--include-children")));
        assert!(!arguments.contains(&OsString::from("--include-delegations")));
    }

    #[cfg(unix)]
    #[test]
    fn terminates_descendants_of_a_cancelled_renderer() {
        let mut parent = Command::new("sh")
            .args(["-c", "sleep 60 & wait"])
            .spawn()
            .expect("spawn renderer fixture");
        let child_pid = (0..20)
            .find_map(|_| {
                let output = Command::new("pgrep")
                    .args(["-P", &parent.id().to_string()])
                    .output()
                    .expect("query renderer child");
                let pid = String::from_utf8_lossy(&output.stdout)
                    .lines()
                    .next()
                    .and_then(|value| value.parse::<u32>().ok());
                if pid.is_none() {
                    thread::sleep(Duration::from_millis(10));
                }
                pid
            })
            .expect("renderer child started");

        terminate_process_tree(parent.id());
        let _ = parent.kill();
        let _ = parent.wait();

        assert!(
            !Command::new("kill")
                .args(["-0", &child_pid.to_string()])
                .status()
                .expect("check renderer child")
                .success()
        );
    }

    #[test]
    fn recognizes_only_bounded_parent_report_navigation_requests() {
        let request = parent_report_request(
            &url::Url::parse(
                "agent-report://view-parent-report?thread_id=parent-thread&title=Parent%20task\
                 &source_path=%2Flogs%2Fparent.jsonl",
            )
            .expect("parse parent report URL"),
        )
        .expect("recognize parent report request");

        assert_eq!(request.thread_id, "parent-thread");
        assert_eq!(request.task_title, "Parent task");
        assert_eq!(request.source_path, "/logs/parent.jsonl");
        assert!(
            parent_report_request(
                &url::Url::parse("file:///tmp/report.html").expect("parse file URL")
            )
            .is_none()
        );
        assert!(
            parent_report_request(
                &url::Url::parse("agent-report://view-parent-report?thread_id=")
                    .expect("parse empty request URL")
            )
            .is_none()
        );
    }
}
