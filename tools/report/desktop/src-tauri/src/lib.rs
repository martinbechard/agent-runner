// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Serve privacy-bounded run search, export, and diagnostic commands to the Tauri desktop webview.
// Design: docs/design/components/CD-001-codex-rollout-metrics.md

//! Native command boundary for the local agent report desktop application.

use std::env;
use std::ffi::OsString;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::Mutex;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::SystemTime;

use agent_report_core::{
    DiscoveryProgress, DiscoveryRequest, DiscoveryResponse, DiscoveryStats, PROTOCOL_VERSION,
    collect_rollout_paths, index_rollouts, read_codex_task_titles,
};
use chrono::{
    DateTime, Duration, Local, LocalResult, NaiveDate, NaiveDateTime, SecondsFormat, TimeZone,
    Timelike, Utc,
};
use html_escape::{encode_double_quoted_attribute, encode_text};
use serde::{Deserialize, Serialize};
use tauri::ipc::Channel;
use tauri::webview::NewWindowResponse;
use tauri::{AppHandle, Emitter, Manager, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_shell::ShellExt;
use url::Url;

static REPORT_WINDOW_COUNTER: AtomicU64 = AtomicU64::new(1);
static DIAGNOSTIC_WRITE_LOCK: Mutex<()> = Mutex::new(());

const DIAGNOSTIC_LOG_FILENAME: &str = "agent-report.log";
const DIAGNOSTIC_LOG_PREVIOUS_FILENAME: &str = "agent-report.previous.log";
const DIAGNOSTIC_LOG_MAX_BYTES: u64 = 5 * 1024 * 1024;
const DIAGNOSTIC_MESSAGE_MAX_CHARS: usize = 16 * 1024;

fn bounded_diagnostic_message(message: &str) -> String {
    let sanitized = message.replace('\0', "�");
    let mut characters = sanitized.chars();
    let bounded = characters
        .by_ref()
        .take(DIAGNOSTIC_MESSAGE_MAX_CHARS)
        .collect::<String>();
    if characters.next().is_some() {
        format!("{bounded}… [truncated]")
    } else {
        bounded
    }
}

fn append_diagnostic_entry(
    log_path: &Path,
    level: &str,
    event: &str,
    message: &str,
) -> Result<(), String> {
    let _guard = DIAGNOSTIC_WRITE_LOCK
        .lock()
        .map_err(|_| "diagnostic log writer lock is unavailable".to_owned())?;
    let parent = log_path
        .parent()
        .ok_or_else(|| "diagnostic log path has no parent folder".to_owned())?;
    fs::create_dir_all(parent)
        .map_err(|error| format!("unable to create diagnostic log folder: {error}"))?;
    if fs::metadata(log_path).is_ok_and(|metadata| metadata.len() >= DIAGNOSTIC_LOG_MAX_BYTES) {
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
        "message": bounded_diagnostic_message(message),
    });
    let mut log = OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_path)
        .map_err(|error| format!("unable to open diagnostic log: {error}"))?;
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

fn record_diagnostic(
    app: &AppHandle,
    level: &str,
    event: &str,
    message: &str,
) -> Result<(), String> {
    append_diagnostic_entry(&diagnostic_log_path(app)?, level, event, message)
}

fn record_failed_result<T>(
    app: &AppHandle,
    event: &str,
    result: Result<T, String>,
) -> Result<T, String> {
    if let Err(error) = &result {
        let _ = record_diagnostic(app, "error", event, error);
    }
    result
}

fn initialize_diagnostics(app: &AppHandle) -> Result<(), String> {
    let log_path = diagnostic_log_path(app)?;
    append_diagnostic_entry(
        &log_path,
        "info",
        "app_started",
        &format!("Agent Report {} started", env!("CARGO_PKG_VERSION")),
    )?;
    let previous_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |panic_info| {
        let _ = append_diagnostic_entry(&log_path, "error", "panic", &panic_info.to_string());
        previous_hook(panic_info);
    }));
    Ok(())
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

    fn includes_candidate(&self, path: &Path) -> bool {
        if self.from.is_none() && self.to_exclusive.is_none() {
            return true;
        }
        let Some(created_at) = encoded_rollout_timestamp(path) else {
            return true;
        };
        let Ok(updated_at) = fs::metadata(path).and_then(|metadata| metadata.modified()) else {
            return true;
        };
        let updated_at = DateTime::<Utc>::from(updated_at);
        let occurred_during = |timestamp: DateTime<Utc>| {
            !self.from.is_some_and(|from| timestamp < from)
                && !self
                    .to_exclusive
                    .is_some_and(|to_exclusive| timestamp >= to_exclusive)
        };
        let spans_range = self
            .from
            .zip(self.to_exclusive)
            .is_some_and(|(from, to_exclusive)| created_at < from && updated_at >= to_exclusive);
        occurred_during(created_at) || occurred_during(updated_at) || spans_range
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

fn encoded_rollout_timestamp(path: &Path) -> Option<DateTime<Utc>> {
    let filename = path.file_name()?.to_str()?;
    let start = filename.find("rollout-")? + "rollout-".len();
    let timestamp = filename.get(start..start + 19)?;
    let timestamp = NaiveDateTime::parse_from_str(timestamp, "%Y-%m-%dT%H-%M-%S").ok()?;
    match Local.from_local_datetime(&timestamp) {
        LocalResult::Single(timestamp) => Some(timestamp.with_timezone(&Utc)),
        LocalResult::Ambiguous(first, second) => {
            Some((if first <= second { first } else { second }).with_timezone(&Utc))
        }
        LocalResult::None => None,
    }
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

/// Initial local locations suggested by the native application.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopDefaults {
    /// Existing Codex stores under the current user's home directory.
    pub roots: Vec<PathBuf>,
    /// Default incremental native index path.
    pub index_path: Option<PathBuf>,
    /// Current Codex app state database, when the standard path exists.
    pub state_db_path: Option<PathBuf>,
    /// Persistent local JSONL file used for bounded troubleshooting diagnostics.
    pub diagnostic_log_path: PathBuf,
}

/// Request to search again and write a privacy-bounded HTML catalog.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ExportCatalogRequest {
    /// Search contract that determines exported rows.
    pub search: SearchRequest,
    /// User-selected output path.
    pub output_path: PathBuf,
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
    /// Whether cross-root delegation links should be followed.
    pub include_delegations: bool,
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
    let paths = collect_rollout_paths(&request.roots)
        .map_err(|error| error.to_string())?
        .into_iter()
        .filter(|path| date_range.includes_candidate(path))
        .collect();
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
        let thread_ids = response.entries.iter().filter_map(|entry| {
            entry
                .identity
                .as_ref()
                .map(|identity| identity.thread_id.clone())
        });
        if let Ok(titles) = read_codex_task_titles(state_path, thread_ids) {
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
    }
    Ok(filter_catalog(
        response,
        &request.query,
        request.include_descendants,
    ))
}

fn filter_catalog(
    response: DiscoveryResponse,
    query: &str,
    include_descendants: bool,
) -> SearchResponse {
    let normalized_query = query.trim().to_lowercase();
    let mut entries = response
        .entries
        .into_iter()
        .filter_map(|entry| {
            let identity = entry.identity?;
            if !include_descendants && !identity.parent_thread_id.is_empty() {
                return None;
            }
            let catalog_entry = CatalogEntry {
                thread_id: identity.thread_id,
                parent_thread_id: identity.parent_thread_id,
                task_title: entry.task_title,
                started_at: entry.started_at,
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
            .started_at
            .cmp(&left.started_at)
            .then_with(|| left.source_path.cmp(&right.source_path))
    });
    SearchResponse {
        entries,
        stats: response.stats,
    }
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
                encode_text(&entry.started_at),
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
fn desktop_defaults(app: AppHandle) -> Result<DesktopDefaults, String> {
    let diagnostic_log_path = diagnostic_log_path(&app)?;
    let Some(home) = env::var_os("HOME").map(PathBuf::from) else {
        return Ok(DesktopDefaults {
            roots: Vec::new(),
            index_path: None,
            state_db_path: None,
            diagnostic_log_path,
        });
    };
    let codex = home.join(".codex");
    let roots = [codex.join("sessions"), codex.join("archived_sessions")]
        .into_iter()
        .filter(|path| path.is_dir())
        .collect();
    Ok(DesktopDefaults {
        roots,
        index_path: Some(
            codex
                .join("agent-report")
                .join("rollout-discovery-v2.sqlite3"),
        ),
        state_db_path: codex
            .join("state_5.sqlite")
            .is_file()
            .then(|| codex.join("state_5.sqlite")),
        diagnostic_log_path,
    })
}

#[tauri::command]
async fn search_rollouts(
    app: AppHandle,
    request: SearchRequest,
    on_event: Channel<DiscoveryProgress>,
) -> Result<SearchResponse, String> {
    let result = match tauri::async_runtime::spawn_blocking(move || {
        search_catalog_with_progress(request, |event| {
            if event.completed_files == 1
                || event.completed_files == event.candidate_files
                || event.completed_files % 64 == 0
            {
                let _ = on_event.send(event);
            }
        })
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
    request: ExportCatalogRequest,
) -> Result<ExportResult, String> {
    let result = match tauri::async_runtime::spawn_blocking(move || {
        let response = search_catalog_sync(request.search)?;
        ensure_output_parent(&request.output_path)?;
        fs::write(&request.output_path, render_catalog_html(&response))
            .map_err(|error| format!("unable to write catalog: {error}"))?;
        Ok(ExportResult {
            output_path: request.output_path,
            entry_count: response.entries.len(),
        })
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
) -> Result<ExportResult, String> {
    let result = generate_full_report(&app, request).await;
    record_failed_result(&app, "generate_report", result)
}

fn renderer_override(value: Option<OsString>) -> Option<PathBuf> {
    value.filter(|path| !path.is_empty()).map(PathBuf::from)
}

fn full_report_arguments(request: &GenerateReportRequest) -> Vec<OsString> {
    let mut arguments = vec![
        OsString::from("--codex-thread"),
        OsString::from(&request.thread_id),
        OsString::from("--output"),
        request.output_path.as_os_str().to_owned(),
    ];
    for root in &request.roots {
        arguments.push(OsString::from("--sessions-root"));
        arguments.push(root.as_os_str().to_owned());
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
) -> Result<ExportResult, String> {
    if request.thread_id.trim().is_empty() {
        return Err("Select a root run before generating a report".to_owned());
    }
    ensure_output_parent(&request.output_path)?;
    let arguments = full_report_arguments(&request);
    if let Some(renderer) = renderer_override(env::var_os("AGENT_REPORT_COMMAND")) {
        let renderer_display = renderer.display().to_string();
        let output = tauri::async_runtime::spawn_blocking(move || {
            Command::new(&renderer).args(&arguments).output()
        })
        .await
        .map_err(|error| format!("report generation task failed: {error}"))?
        .map_err(|error| {
            format!("unable to start full report renderer {renderer_display}: {error}")
        })?;
        return completed_report(
            request,
            output.status.success(),
            output.status.to_string(),
            &output.stderr,
        );
    }

    let output = app
        .shell()
        .sidecar("agent-report")
        .map_err(|error| format!("unable to prepare bundled full report renderer: {error}"))?
        .args(arguments)
        .output()
        .await
        .map_err(|error| format!("unable to start bundled full report renderer: {error}"))?;
    let status = output.status.code().map_or_else(
        || "terminated without an exit code".to_owned(),
        |code| format!("exit status {code}"),
    );
    completed_report(request, output.status.success(), status, &output.stderr)
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
async fn open_report_window(app: AppHandle, output_path: PathBuf) -> Result<(), String> {
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
        WebviewWindowBuilder::new(&app, label, WebviewUrl::CustomProtocol(url))
            .title(format!("Agent Report — {title}"))
            .inner_size(1280.0, 800.0)
            .min_inner_size(720.0, 480.0)
            .on_navigation(move |navigation_url| {
                let Some(request) = parent_report_request(navigation_url) else {
                    return true;
                };
                if let Err(error) = navigation_app.emit("view-parent-report", request) {
                    let _ = record_diagnostic(
                        &navigation_app,
                        "error",
                        "view_parent_report",
                        &format!("unable to forward parent report request: {error}"),
                    );
                }
                false
            })
            .on_new_window(move |popup_url, _features| {
                if report_popup_is_allowed(&report_path, &popup_url) {
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
fn record_client_error(app: AppHandle, context: String, message: String) -> Result<(), String> {
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
    record_diagnostic(&app, "error", &format!("webview.{event}"), &message)
}

#[tauri::command]
#[allow(
    deprecated,
    reason = "reuse the already bundled shell opener for one native-only local log path"
)]
fn open_diagnostic_log(app: AppHandle) -> Result<(), String> {
    let log_path = diagnostic_log_path(&app)?;
    if !log_path.is_file() {
        append_diagnostic_entry(
            &log_path,
            "info",
            "diagnostic_log_created",
            "Diagnostic log created on demand",
        )?;
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
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            initialize_diagnostics(app.handle()).map_err(std::io::Error::other)?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            desktop_defaults,
            search_rollouts,
            export_catalog,
            generate_report,
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

    use serde_json::Value;
    use tempfile::TempDir;

    use super::{
        DIAGNOSTIC_LOG_MAX_BYTES, GenerateReportRequest, append_diagnostic_entry,
        full_report_arguments, parent_report_request, renderer_override,
    };

    #[test]
    fn appends_structured_diagnostics_and_rotates_a_full_log() {
        let directory = TempDir::new().expect("create temporary directory");
        let log_path = directory.path().join("agent-report.log");
        let previous_path = directory.path().join("agent-report.previous.log");
        fs::write(&log_path, vec![b'x'; DIAGNOSTIC_LOG_MAX_BYTES as usize])
            .expect("seed a full diagnostic log");

        append_diagnostic_entry(
            &log_path,
            "error",
            "generate_report",
            "renderer failed\nwith a quoted \"detail\"",
        )
        .expect("append diagnostic entry");

        assert_eq!(
            fs::metadata(previous_path)
                .expect("read rotated log metadata")
                .len(),
            DIAGNOSTIC_LOG_MAX_BYTES,
        );
        let line = fs::read_to_string(log_path).expect("read current diagnostic log");
        let entry: Value = serde_json::from_str(line.trim()).expect("parse diagnostic JSON line");
        assert_eq!(entry["level"], "error");
        assert_eq!(entry["event"], "generate_report");
        assert_eq!(
            entry["message"],
            "renderer failed\nwith a quoted \"detail\""
        );
        assert!(
            entry["timestamp"]
                .as_str()
                .is_some_and(|value| value.ends_with('Z'))
        );
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
    fn passes_selected_roots_and_delegation_mode_to_the_renderer() {
        let request = GenerateReportRequest {
            thread_id: "root-thread".to_owned(),
            roots: vec![
                PathBuf::from("/tmp/sessions"),
                PathBuf::from("/tmp/archive"),
            ],
            output_path: PathBuf::from("/tmp/report.html"),
            include_delegations: true,
        };

        assert_eq!(
            full_report_arguments(&request),
            vec![
                OsString::from("--codex-thread"),
                OsString::from("root-thread"),
                OsString::from("--output"),
                OsString::from("/tmp/report.html"),
                OsString::from("--sessions-root"),
                OsString::from("/tmp/sessions"),
                OsString::from("--sessions-root"),
                OsString::from("/tmp/archive"),
                OsString::from("--include-delegations"),
            ]
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
