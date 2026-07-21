// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Serve privacy-bounded run search and export commands to the Tauri desktop webview.
// Design: docs/design/components/CD-001-codex-rollout-metrics.md

//! Native command boundary for the local agent report desktop application.

use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

use agent_report_core::{
    DiscoveryProgress, DiscoveryRequest, DiscoveryResponse, DiscoveryStats, PROTOCOL_VERSION,
    collect_rollout_paths, index_rollouts,
};
use html_escape::{encode_double_quoted_attribute, encode_text};
use serde::{Deserialize, Serialize};
use tauri::ipc::Channel;
use tauri::{AppHandle, WebviewUrl, WebviewWindowBuilder};
use url::Url;

static REPORT_WINDOW_COUNTER: AtomicU64 = AtomicU64::new(1);

/// Search controls accepted from the desktop webview.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SearchRequest {
    /// Caller-selected log roots.
    pub roots: Vec<PathBuf>,
    /// Optional persistent native index path.
    pub index_path: Option<PathBuf>,
    /// Case-insensitive query over normalized metadata.
    pub query: String,
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
    /// Bounded task title derived by the native core.
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

/// Request to invoke the installed full Python renderer for one selected root.
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
    let paths = collect_rollout_paths(&request.roots).map_err(|error| error.to_string())?;
    let response = index_rollouts(
        DiscoveryRequest {
            version: PROTOCOL_VERSION,
            paths,
            index_path: request.index_path,
            workers: request.workers,
        },
        progress,
    )
    .map_err(|error| error.to_string())?;
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
fn desktop_defaults() -> DesktopDefaults {
    let Some(home) = env::var_os("HOME").map(PathBuf::from) else {
        return DesktopDefaults {
            roots: Vec::new(),
            index_path: None,
        };
    };
    let codex = home.join(".codex");
    let roots = [codex.join("sessions"), codex.join("archived_sessions")]
        .into_iter()
        .filter(|path| path.is_dir())
        .collect();
    DesktopDefaults {
        roots,
        index_path: Some(
            codex
                .join("agent-report")
                .join("rollout-discovery-v2.sqlite3"),
        ),
    }
}

#[tauri::command]
async fn search_rollouts(
    request: SearchRequest,
    on_event: Channel<DiscoveryProgress>,
) -> Result<SearchResponse, String> {
    tauri::async_runtime::spawn_blocking(move || {
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
    .map_err(|error| format!("native search task failed: {error}"))?
}

#[tauri::command]
async fn export_catalog(request: ExportCatalogRequest) -> Result<ExportResult, String> {
    tauri::async_runtime::spawn_blocking(move || {
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
    .map_err(|error| format!("native export task failed: {error}"))?
}

#[tauri::command]
async fn generate_report(request: GenerateReportRequest) -> Result<ExportResult, String> {
    tauri::async_runtime::spawn_blocking(move || generate_full_report(request))
        .await
        .map_err(|error| format!("report generation task failed: {error}"))?
}

fn generate_full_report(request: GenerateReportRequest) -> Result<ExportResult, String> {
    if request.thread_id.trim().is_empty() {
        return Err("Select a root run before generating a report".to_owned());
    }
    ensure_output_parent(&request.output_path)?;
    let renderer = env::var_os("AGENT_REPORT_COMMAND")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("agent-report"));
    let mut command = Command::new(&renderer);
    command
        .arg("--codex-thread")
        .arg(&request.thread_id)
        .arg("--output")
        .arg(&request.output_path);
    for root in &request.roots {
        command.arg("--sessions-root").arg(root);
    }
    if request.include_delegations {
        command.arg("--include-delegations");
    }
    let output = command.output().map_err(|error| {
        format!(
            "unable to start full report renderer {}: {error}. Install agent-report or set AGENT_REPORT_COMMAND",
            renderer.display()
        )
    })?;
    if !output.status.success() {
        let diagnostic = String::from_utf8_lossy(&output.stderr).trim().to_owned();
        return Err(format!(
            "full report renderer failed: {}",
            if diagnostic.is_empty() {
                output.status.to_string()
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

#[tauri::command]
async fn open_report_window(app: AppHandle, output_path: PathBuf) -> Result<(), String> {
    let url = report_window_url(&output_path)?;
    let title = output_path
        .file_stem()
        .and_then(|stem| stem.to_str())
        .filter(|stem| !stem.is_empty())
        .unwrap_or("Report");
    let label = format!(
        "report-{}",
        REPORT_WINDOW_COUNTER.fetch_add(1, Ordering::Relaxed)
    );
    WebviewWindowBuilder::new(&app, label, WebviewUrl::CustomProtocol(url))
        .title(format!("Agent Report — {title}"))
        .inner_size(1280.0, 800.0)
        .min_inner_size(720.0, 480.0)
        .build()
        .map_err(|error| format!("unable to open report window: {error}"))?;
    Ok(())
}

/// Build and run the desktop application with a deliberately narrow command surface.
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            desktop_defaults,
            search_rollouts,
            export_catalog,
            generate_report,
            open_report_window,
        ])
        .run(tauri::generate_context!())
        .expect("error while running agent report desktop application");
}
