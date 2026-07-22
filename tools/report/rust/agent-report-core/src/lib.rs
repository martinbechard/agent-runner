// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Discover and incrementally index local Codex rollout metadata for report clients.
// Design: docs/design/components/CD-001-codex-rollout-metrics.md

//! Shared native discovery and indexing for the agent report command and desktop app.

use std::collections::{BTreeSet, HashMap};
use std::fs::{self, File};
use std::io::{self, BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::sync::OnceLock;
use std::thread;
use std::time::Instant;

use aho_corasick::{AhoCorasick, AhoCorasickBuilder};
use crossbeam_channel::bounded;
use html_escape::decode_html_entities;
use regex::Regex;
use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;
use walkdir::WalkDir;

/// JSON protocol version shared by the native CLI and Python client.
pub const PROTOCOL_VERSION: u32 = 1;
const INDEX_TABLE: &str = "codex_rollout_discovery_v2";
const DISCOVERY_PARSER_VERSION: i64 = 4;
const MAX_WORKERS: usize = 64;

/// One request to discover metadata for an ordered list of rollout files.
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct DiscoveryRequest {
    /// Protocol version expected by the caller.
    pub version: u32,
    /// Ordered candidate JSONL files.
    pub paths: Vec<PathBuf>,
    /// Optional incremental SQLite index.
    pub index_path: Option<PathBuf>,
    /// Optional bounded worker count.
    pub workers: Option<usize>,
}

/// Recorded ownership metadata for one rollout.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct RolloutIdentity {
    /// Unique Codex thread identifier.
    pub thread_id: String,
    /// Parent thread identifier, or an empty string for a root.
    pub parent_thread_id: String,
    /// Recorded hierarchical agent path.
    pub agent_path: String,
    /// Recorded runtime nickname.
    pub agent_nickname: String,
}

/// Privacy-bounded metadata discovered from one rollout.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct DiscoveryEntry {
    /// Exact candidate path supplied by the caller.
    pub path: String,
    /// First usable session identity, when present.
    pub identity: Option<RolloutIdentity>,
    /// Sorted thread IDs found in user delegation envelopes.
    pub delegation_source_ids: Vec<String>,
    /// Timestamp recorded with the session identity.
    pub started_at: String,
    /// Workspace recorded with the session identity.
    pub workspace: String,
    /// Bounded title derived from the first genuine user request.
    pub task_title: String,
    /// Read diagnostic for an individual candidate, without transcript content.
    pub diagnostic: Option<String>,
}

/// Reconciled counts for one discovery operation.
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct DiscoveryStats {
    /// Number of requested candidates.
    pub candidate_files: usize,
    /// Number of files read by native workers.
    pub scanned_files: usize,
    /// Number of stable entries reused from SQLite.
    pub cached_files: usize,
    /// Number of files that changed while being read.
    pub unstable_files: usize,
    /// Number of candidates that could not be read or fingerprinted.
    pub unreadable_files: usize,
    /// Elapsed discovery time measured by the native process.
    pub elapsed_ms: u64,
    /// Effective bounded worker count.
    pub workers: usize,
}

/// Versioned native discovery response.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct DiscoveryResponse {
    /// Response protocol version.
    pub version: u32,
    /// Entries restored to request order.
    pub entries: Vec<DiscoveryEntry>,
    /// Cache and worker statistics.
    pub stats: DiscoveryStats,
}

/// Source of one completed candidate in a progress event.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DiscoverySource {
    /// Metadata came from the stable SQLite index.
    Cache,
    /// Metadata came from a native streaming worker.
    Scan,
}

/// Bounded progress snapshot suitable for a Tauri channel.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct DiscoveryProgress {
    /// Number of candidates completed so far.
    pub completed_files: usize,
    /// Total requested candidates.
    pub candidate_files: usize,
    /// Path most recently completed.
    pub path: String,
    /// Whether that result was cached or scanned.
    pub source: DiscoverySource,
}

/// Native discovery or index contract failure.
#[derive(Debug, Error)]
pub enum DiscoveryError {
    /// Request and engine protocol versions differ.
    #[error("unsupported discovery protocol version {actual}; expected {expected}")]
    UnsupportedVersion { actual: u32, expected: u32 },
    /// Worker count is outside the supported bound.
    #[error("discovery worker count must be between 1 and {MAX_WORKERS}, got {0}")]
    InvalidWorkerCount(usize),
    /// SQLite index creation, validation, read, or write failed.
    #[error("discovery index {path}: {detail}")]
    Index {
        /// Requested index path.
        path: PathBuf,
        /// Underlying SQLite or directory error.
        detail: String,
    },
    /// A bounded worker channel closed before all candidates completed.
    #[error("native discovery worker channel closed unexpectedly")]
    WorkerChannel,
    /// A requested catalog root could not be walked.
    #[error("rollout root {path}: {detail}")]
    RootWalk {
        /// Requested search root.
        path: PathBuf,
        /// Bounded filesystem diagnostic.
        detail: String,
    },
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Fingerprint {
    device: i64,
    inode: i64,
    size: i64,
    modified_at_ns: i64,
    changed_at_ns: i64,
}

#[derive(Clone, Debug)]
struct CachedEntry {
    fingerprint: Fingerprint,
    parser_version: i64,
    entry: DiscoveryEntry,
}

#[derive(Debug)]
struct ScanJob {
    index: usize,
    path: PathBuf,
    fingerprint_before: Fingerprint,
}

#[derive(Debug)]
struct ScanResult {
    index: usize,
    entry: DiscoveryEntry,
    stable_fingerprint: Option<Fingerprint>,
    unstable: bool,
    unreadable: bool,
}

/// Recursively collect JSONL candidates from caller-bounded roots.
///
/// Files are deduplicated and returned in lexical path order.
pub fn collect_rollout_paths(roots: &[PathBuf]) -> Result<Vec<PathBuf>, DiscoveryError> {
    let mut paths = BTreeSet::new();
    for root in roots {
        if root.is_file() {
            if root
                .extension()
                .is_some_and(|extension| extension == "jsonl")
            {
                paths.insert(root.clone());
            }
            continue;
        }
        if !root.exists() {
            return Err(DiscoveryError::RootWalk {
                path: root.clone(),
                detail: "path does not exist".to_owned(),
            });
        }
        for candidate in WalkDir::new(root).follow_links(false) {
            let candidate = candidate.map_err(|error| DiscoveryError::RootWalk {
                path: root.clone(),
                detail: error.to_string(),
            })?;
            if candidate.file_type().is_file()
                && candidate
                    .path()
                    .extension()
                    .is_some_and(|extension| extension == "jsonl")
            {
                paths.insert(candidate.into_path());
            }
        }
    }
    Ok(paths.into_iter().collect())
}

/// Discover rollout metadata with bounded parallel readers and one SQLite writer.
///
/// The callback runs on the caller thread after each cached or scanned candidate
/// completes. Results are always restored to request order.
pub fn index_rollouts<F>(
    request: DiscoveryRequest,
    progress: F,
) -> Result<DiscoveryResponse, DiscoveryError>
where
    F: Fn(DiscoveryProgress),
{
    if request.version != PROTOCOL_VERSION {
        return Err(DiscoveryError::UnsupportedVersion {
            actual: request.version,
            expected: PROTOCOL_VERSION,
        });
    }
    let workers = effective_worker_count(request.workers)?;
    let started = Instant::now();
    let mut stats = DiscoveryStats {
        candidate_files: request.paths.len(),
        workers,
        ..DiscoveryStats::default()
    };
    let mut completed = 0;
    let mut ordered = vec![None; request.paths.len()];
    let mut connection = match request.index_path.as_deref() {
        Some(path) => Some(open_index(path)?),
        None => None,
    };
    let cached = match connection.as_ref() {
        Some(connection) => load_cache(connection, request.index_path.as_deref().expect("index"))?,
        None => HashMap::new(),
    };

    let mut jobs = Vec::new();
    for (index, path) in request.paths.iter().enumerate() {
        let fingerprint_before = match file_fingerprint(path) {
            Ok(fingerprint) => fingerprint,
            Err(error) => {
                stats.unreadable_files += 1;
                stats.scanned_files += 1;
                completed += 1;
                let entry = unreadable_entry(path, &error);
                progress(DiscoveryProgress {
                    completed_files: completed,
                    candidate_files: request.paths.len(),
                    path: entry.path.clone(),
                    source: DiscoverySource::Scan,
                });
                ordered[index] = Some(entry);
                continue;
            }
        };
        let key = path.to_string_lossy();
        if let Some(cached_entry) = cached.get(key.as_ref())
            && cached_entry.parser_version == DISCOVERY_PARSER_VERSION
            && cached_entry.fingerprint == fingerprint_before
        {
            stats.cached_files += 1;
            completed += 1;
            progress(DiscoveryProgress {
                completed_files: completed,
                candidate_files: request.paths.len(),
                path: key.into_owned(),
                source: DiscoverySource::Cache,
            });
            ordered[index] = Some(cached_entry.entry.clone());
        } else {
            jobs.push(ScanJob {
                index,
                path: path.clone(),
                fingerprint_before,
            });
        }
    }

    let mut updates = Vec::new();
    if !jobs.is_empty() {
        let job_count = jobs.len();
        let capacity = workers.saturating_mul(2).max(1);
        let (job_sender, job_receiver) = bounded::<ScanJob>(capacity);
        let (result_sender, result_receiver) = bounded::<ScanResult>(capacity);
        thread::scope(|scope| {
            for _ in 0..workers {
                let receiver = job_receiver.clone();
                let sender = result_sender.clone();
                scope.spawn(move || {
                    while let Ok(job) = receiver.recv() {
                        if sender.send(run_scan_job(job)).is_err() {
                            break;
                        }
                    }
                });
            }
            drop(job_receiver);
            scope.spawn(move || {
                for job in jobs {
                    if job_sender.send(job).is_err() {
                        break;
                    }
                }
            });
            drop(result_sender);

            for _ in 0..job_count {
                let result = result_receiver
                    .recv()
                    .map_err(|_| DiscoveryError::WorkerChannel)?;
                stats.scanned_files += 1;
                stats.unstable_files += usize::from(result.unstable);
                stats.unreadable_files += usize::from(result.unreadable);
                completed += 1;
                progress(DiscoveryProgress {
                    completed_files: completed,
                    candidate_files: request.paths.len(),
                    path: result.entry.path.clone(),
                    source: DiscoverySource::Scan,
                });
                if let Some(fingerprint) = result.stable_fingerprint.clone() {
                    updates.push((fingerprint, result.entry.clone()));
                }
                ordered[result.index] = Some(result.entry);
            }
            Ok::<(), DiscoveryError>(())
        })?;
    }

    if let (Some(connection), Some(path)) = (connection.as_mut(), request.index_path.as_deref()) {
        write_updates(connection, path, &updates)?;
    }
    stats.elapsed_ms = u64::try_from(started.elapsed().as_millis()).unwrap_or(u64::MAX);
    let entries = ordered
        .into_iter()
        .map(|entry| entry.expect("every discovery candidate produces one entry"))
        .collect();
    Ok(DiscoveryResponse {
        version: PROTOCOL_VERSION,
        entries,
        stats,
    })
}

fn effective_worker_count(requested: Option<usize>) -> Result<usize, DiscoveryError> {
    let workers = requested.unwrap_or_else(|| {
        thread::available_parallelism()
            .map(usize::from)
            .unwrap_or(1)
            .min(8)
    });
    if !(1..=MAX_WORKERS).contains(&workers) {
        return Err(DiscoveryError::InvalidWorkerCount(workers));
    }
    Ok(workers)
}

fn run_scan_job(job: ScanJob) -> ScanResult {
    match scan_rollout(&job.path) {
        Ok(mut entry) => match file_fingerprint(&job.path) {
            Ok(after) if after == job.fingerprint_before => ScanResult {
                index: job.index,
                entry,
                stable_fingerprint: Some(after),
                unstable: false,
                unreadable: false,
            },
            Ok(_) => {
                entry.diagnostic = Some("rollout changed during native discovery".to_owned());
                ScanResult {
                    index: job.index,
                    entry,
                    stable_fingerprint: None,
                    unstable: true,
                    unreadable: false,
                }
            }
            Err(error) => {
                entry.diagnostic = Some(format!("unable to fingerprint after scan: {error}"));
                ScanResult {
                    index: job.index,
                    entry,
                    stable_fingerprint: None,
                    unstable: false,
                    unreadable: true,
                }
            }
        },
        Err(error) => ScanResult {
            index: job.index,
            entry: unreadable_entry(&job.path, &error),
            stable_fingerprint: None,
            unstable: false,
            unreadable: true,
        },
    }
}

fn scan_rollout(path: &Path) -> io::Result<DiscoveryEntry> {
    let file = File::open(path)?;
    let mut reader = BufReader::with_capacity(128 * 1024, file);
    let mut buffer = Vec::with_capacity(16 * 1024);
    let mut identity = None;
    let mut delegation_source_ids = BTreeSet::new();
    let mut started_at = String::new();
    let mut workspace = String::new();
    let mut task_title = String::new();
    let mut title_scan_complete = false;
    let mut infer_parent_from_delegation = false;

    loop {
        buffer.clear();
        if reader.read_until(b'\n', &mut buffer)? == 0 {
            break;
        }
        let line = trim_ascii_whitespace(&buffer);
        if line.is_empty() {
            continue;
        }
        let may_contain_delegation = delegation_marker().is_match(line);
        if identity.is_some() && title_scan_complete && !may_contain_delegation {
            continue;
        }
        let text = String::from_utf8_lossy(line);
        let Ok(record) = serde_json::from_str::<Value>(&text) else {
            continue;
        };
        if identity.is_none()
            && let Some(found) = recorded_identity(&record)
        {
            started_at = value_text(record.get("timestamp"));
            workspace = record
                .get("payload")
                .and_then(Value::as_object)
                .map(|payload| value_text(payload.get("cwd")))
                .unwrap_or_default();
            infer_parent_from_delegation = record
                .get("payload")
                .and_then(Value::as_object)
                .is_some_and(|payload| {
                    payload.get("thread_source").and_then(Value::as_str) == Some("subagent")
                        || payload.get("source").and_then(Value::as_str) == Some("subagent")
                });
            title_scan_complete = !found.parent_thread_id.is_empty();
            identity = Some(found);
        }
        if !title_scan_complete && let Some(content) = user_message_text(&record) {
            if let Some(title) = derive_task_title(&content) {
                if let Some(found) = identity.as_mut()
                    && infer_parent_from_delegation
                    && found.parent_thread_id.is_empty()
                    && let Some(source) = initial_delegation_source(&content)
                    && source != found.thread_id
                {
                    found.parent_thread_id = source;
                }
                task_title = title;
                title_scan_complete = true;
            }
        }
        if may_contain_delegation && let Some(content) = user_message_text(&record) {
            for captures in delegation_block_pattern().captures_iter(&content) {
                let Some(body) = captures.name("body") else {
                    continue;
                };
                if let Some(source) = delegation_source_pattern()
                    .captures(body.as_str())
                    .and_then(|source| source.name("source"))
                {
                    delegation_source_ids.insert(source.as_str().to_owned());
                }
            }
        }
    }

    Ok(DiscoveryEntry {
        path: path.to_string_lossy().into_owned(),
        identity,
        delegation_source_ids: delegation_source_ids.into_iter().collect(),
        started_at,
        workspace,
        task_title,
        diagnostic: None,
    })
}

fn recorded_identity(record: &Value) -> Option<RolloutIdentity> {
    if record.get("type").and_then(Value::as_str) != Some("session_meta") {
        return None;
    }
    let payload = record.get("payload")?.as_object()?;
    let thread_id =
        value_text(payload.get("id")).or_else_nonempty(|| value_text(payload.get("session_id")));
    if thread_id.is_empty() {
        return None;
    }
    let spawn = payload
        .get("source")
        .and_then(Value::as_object)
        .and_then(|source| source.get("subagent"))
        .and_then(Value::as_object)
        .and_then(|subagent| subagent.get("thread_spawn"))
        .and_then(Value::as_object);
    Some(RolloutIdentity {
        thread_id,
        parent_thread_id: spawn
            .map(|value| value_text(value.get("parent_thread_id")))
            .unwrap_or_default(),
        agent_path: spawn
            .map(|value| value_text(value.get("agent_path")))
            .unwrap_or_default(),
        agent_nickname: spawn
            .map(|value| value_text(value.get("agent_nickname")))
            .unwrap_or_default(),
    })
}

trait NonEmptyFallback {
    fn or_else_nonempty<F>(self, fallback: F) -> String
    where
        F: FnOnce() -> String;
}

impl NonEmptyFallback for String {
    fn or_else_nonempty<F>(self, fallback: F) -> String
    where
        F: FnOnce() -> String,
    {
        if self.is_empty() { fallback() } else { self }
    }
}

fn user_message_text(record: &Value) -> Option<String> {
    if record.get("type").and_then(Value::as_str) != Some("response_item") {
        return None;
    }
    let payload = record.get("payload")?.as_object()?;
    if payload.get("type").and_then(Value::as_str) != Some("message")
        || payload.get("role").and_then(Value::as_str) != Some("user")
    {
        return None;
    }
    let fragments = payload
        .get("content")?
        .as_array()?
        .iter()
        .filter_map(|item| item.get("text").and_then(Value::as_str))
        .filter(|text| !text.trim().is_empty())
        .collect::<Vec<_>>();
    (!fragments.is_empty()).then(|| fragments.join("\n"))
}

fn derive_task_title(content: &str) -> Option<String> {
    let mut request = content.trim().to_owned();
    const REQUEST_MARKER: &str = "## My request for Codex:";
    if let Some((_, suffix)) = request.split_once(REQUEST_MARKER) {
        request = suffix.trim().to_owned();
    }
    for _ in 0..3 {
        if let Some(delegation_input) = delegation_input_pattern()
            .captures(&request)
            .and_then(|captures| captures.name("input"))
        {
            request = delegation_input.as_str().trim().to_owned();
            continue;
        }
        let decoded = decode_html_entities(&request).into_owned();
        if decoded != request {
            request = decoded;
            continue;
        }
        break;
    }
    if [
        "<recommended_plugins>",
        "# AGENTS.md instructions for ",
        "<environment_context>",
        "<in-app-browser-context source=\"ambient-ui-state\">",
    ]
    .iter()
    .any(|prefix| request.starts_with(prefix))
    {
        return None;
    }
    if request
        .to_ascii_lowercase()
        .starts_with("<codex_delegation")
    {
        return None;
    }
    let without_secrets = redacted_environment_pattern().replace_all(&request, "");
    let normalized = without_secrets
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    let stripped = polite_prefix_pattern().replace(&normalized, "");
    let sentence = sentence_end_pattern()
        .split(&stripped)
        .next()
        .unwrap_or_default()
        .trim();
    let mut title = sentence
        .split_whitespace()
        .take(10)
        .collect::<Vec<_>>()
        .join(" ")
        .trim_end_matches([' ', ',', ':', ';', '-', '.'])
        .to_owned();
    title = trailing_joiner_pattern().replace(&title, "").into_owned();
    let first = title.chars().next()?;
    let mut result = first.to_uppercase().collect::<String>();
    result.push_str(&title[first.len_utf8()..]);
    Some(result)
}

fn initial_delegation_source(content: &str) -> Option<String> {
    let mut request = content.trim().to_owned();
    const REQUEST_MARKER: &str = "## My request for Codex:";
    if let Some((_, suffix)) = request.split_once(REQUEST_MARKER) {
        request = suffix.trim().to_owned();
    }
    for _ in 0..3 {
        let decoded = decode_html_entities(&request).into_owned();
        if decoded != request {
            request = decoded;
            continue;
        }
        break;
    }
    let block = delegation_block_pattern().captures(&request)?;
    if block.get(0)?.as_str().trim() != request {
        return None;
    }
    let body = block.name("body")?.as_str();
    delegation_source_pattern()
        .captures(body)
        .and_then(|captures| captures.name("source"))
        .map(|source| source.as_str().to_owned())
}

fn value_text(value: Option<&Value>) -> String {
    match value {
        Some(Value::String(value)) => value.clone(),
        Some(Value::Number(value)) => value.to_string(),
        Some(Value::Bool(value)) => value.to_string(),
        _ => String::new(),
    }
}

fn unreadable_entry(path: &Path, error: &io::Error) -> DiscoveryEntry {
    DiscoveryEntry {
        path: path.to_string_lossy().into_owned(),
        identity: None,
        delegation_source_ids: Vec::new(),
        started_at: String::new(),
        workspace: String::new(),
        task_title: String::new(),
        diagnostic: Some(format!("unable to read rollout: {error}")),
    }
}

fn open_index(path: &Path) -> Result<Connection, DiscoveryError> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| index_error(path, error))?;
    }
    let connection = Connection::open(path).map_err(|error| index_error(path, error))?;
    connection
        .busy_timeout(std::time::Duration::from_secs(5))
        .map_err(|error| index_error(path, error))?;
    connection
        .execute(
            &format!(
                "CREATE TABLE IF NOT EXISTS {INDEX_TABLE} (\
                 path TEXT PRIMARY KEY, device INTEGER NOT NULL, inode INTEGER NOT NULL, \
                 size INTEGER NOT NULL, modified_at_ns INTEGER NOT NULL, \
                 changed_at_ns INTEGER NOT NULL, thread_id TEXT NOT NULL, \
                 parent_thread_id TEXT NOT NULL, agent_path TEXT NOT NULL, \
                 agent_nickname TEXT NOT NULL, delegation_source_ids TEXT NOT NULL, \
                 started_at TEXT NOT NULL, workspace TEXT NOT NULL, task_title TEXT NOT NULL, \
                 parser_version INTEGER NOT NULL)"
            ),
            [],
        )
        .map_err(|error| index_error(path, error))?;
    let has_parser_version = connection
        .prepare(&format!("PRAGMA table_info({INDEX_TABLE})"))
        .and_then(|mut statement| {
            statement
                .query_map([], |row| row.get::<_, String>(1))?
                .collect::<Result<Vec<_>, _>>()
        })
        .map_err(|error| index_error(path, error))?
        .iter()
        .any(|column| column == "parser_version");
    if !has_parser_version {
        connection
            .execute(
                &format!(
                    "ALTER TABLE {INDEX_TABLE} ADD COLUMN parser_version INTEGER NOT NULL DEFAULT 0"
                ),
                [],
            )
            .map_err(|error| index_error(path, error))?;
    }
    Ok(connection)
}

fn load_cache(
    connection: &Connection,
    index_path: &Path,
) -> Result<HashMap<String, CachedEntry>, DiscoveryError> {
    let mut statement = connection
        .prepare(&format!(
            "SELECT path, device, inode, size, modified_at_ns, changed_at_ns, \
             thread_id, parent_thread_id, agent_path, agent_nickname, \
             delegation_source_ids, started_at, workspace, task_title, parser_version \
             FROM {INDEX_TABLE}"
        ))
        .map_err(|error| index_error(index_path, error))?;
    let rows = statement
        .query_map([], |row| {
            let thread_id: String = row.get(6)?;
            let sources: String = row.get(10)?;
            let delegation_source_ids =
                serde_json::from_str::<Vec<String>>(&sources).unwrap_or_default();
            Ok((
                row.get::<_, String>(0)?,
                CachedEntry {
                    fingerprint: Fingerprint {
                        device: row.get(1)?,
                        inode: row.get(2)?,
                        size: row.get(3)?,
                        modified_at_ns: row.get(4)?,
                        changed_at_ns: row.get(5)?,
                    },
                    parser_version: row.get(14)?,
                    entry: DiscoveryEntry {
                        path: row.get(0)?,
                        identity: (!thread_id.is_empty()).then(|| RolloutIdentity {
                            thread_id,
                            parent_thread_id: row.get(7).unwrap_or_default(),
                            agent_path: row.get(8).unwrap_or_default(),
                            agent_nickname: row.get(9).unwrap_or_default(),
                        }),
                        delegation_source_ids,
                        started_at: row.get(11).unwrap_or_default(),
                        workspace: row.get(12).unwrap_or_default(),
                        task_title: row.get(13).unwrap_or_default(),
                        diagnostic: None,
                    },
                },
            ))
        })
        .map_err(|error| index_error(index_path, error))?;
    let mut cache = HashMap::new();
    for row in rows {
        let (path, entry) = row.map_err(|error| index_error(index_path, error))?;
        cache.insert(path, entry);
    }
    Ok(cache)
}

fn write_updates(
    connection: &mut Connection,
    index_path: &Path,
    updates: &[(Fingerprint, DiscoveryEntry)],
) -> Result<(), DiscoveryError> {
    if updates.is_empty() {
        return Ok(());
    }
    let transaction = connection
        .transaction()
        .map_err(|error| index_error(index_path, error))?;
    {
        let mut statement = transaction
            .prepare(&format!(
                "INSERT INTO {INDEX_TABLE} (path, device, inode, size, modified_at_ns, \
                 changed_at_ns, thread_id, parent_thread_id, agent_path, agent_nickname, \
                 delegation_source_ids, started_at, workspace, task_title, parser_version) \
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) \
                 ON CONFLICT(path) DO UPDATE SET device=excluded.device, inode=excluded.inode, \
                 size=excluded.size, modified_at_ns=excluded.modified_at_ns, \
                 changed_at_ns=excluded.changed_at_ns, thread_id=excluded.thread_id, \
                 parent_thread_id=excluded.parent_thread_id, agent_path=excluded.agent_path, \
                 agent_nickname=excluded.agent_nickname, \
                 delegation_source_ids=excluded.delegation_source_ids, \
                 started_at=excluded.started_at, workspace=excluded.workspace, \
                 task_title=excluded.task_title, parser_version=excluded.parser_version"
            ))
            .map_err(|error| index_error(index_path, error))?;
        for (fingerprint, entry) in updates {
            let empty_identity = RolloutIdentity {
                thread_id: String::new(),
                parent_thread_id: String::new(),
                agent_path: String::new(),
                agent_nickname: String::new(),
            };
            let identity = entry.identity.as_ref().unwrap_or(&empty_identity);
            statement
                .execute(params![
                    entry.path,
                    fingerprint.device,
                    fingerprint.inode,
                    fingerprint.size,
                    fingerprint.modified_at_ns,
                    fingerprint.changed_at_ns,
                    identity.thread_id,
                    identity.parent_thread_id,
                    identity.agent_path,
                    identity.agent_nickname,
                    serde_json::to_string(&entry.delegation_source_ids)
                        .expect("string list always serializes"),
                    entry.started_at,
                    entry.workspace,
                    entry.task_title,
                    DISCOVERY_PARSER_VERSION,
                ])
                .map_err(|error| index_error(index_path, error))?;
        }
    }
    transaction
        .commit()
        .map_err(|error| index_error(index_path, error))
}

fn index_error(path: &Path, error: impl std::fmt::Display) -> DiscoveryError {
    DiscoveryError::Index {
        path: path.to_path_buf(),
        detail: error.to_string(),
    }
}

#[cfg(unix)]
fn file_fingerprint(path: &Path) -> io::Result<Fingerprint> {
    use std::os::unix::fs::MetadataExt;

    let metadata = path.metadata()?;
    Ok(Fingerprint {
        device: i64::try_from(metadata.dev()).unwrap_or(i64::MAX),
        inode: i64::try_from(metadata.ino()).unwrap_or(i64::MAX),
        size: i64::try_from(metadata.size()).unwrap_or(i64::MAX),
        modified_at_ns: seconds_and_nanos(metadata.mtime(), metadata.mtime_nsec()),
        changed_at_ns: seconds_and_nanos(metadata.ctime(), metadata.ctime_nsec()),
    })
}

#[cfg(not(unix))]
fn file_fingerprint(path: &Path) -> io::Result<Fingerprint> {
    use std::time::UNIX_EPOCH;

    let metadata = path.metadata()?;
    let modified = metadata
        .modified()?
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default();
    let modified_at_ns = i64::try_from(modified.as_nanos()).unwrap_or(i64::MAX);
    Ok(Fingerprint {
        device: 0,
        inode: 0,
        size: i64::try_from(metadata.len()).unwrap_or(i64::MAX),
        modified_at_ns,
        changed_at_ns: modified_at_ns,
    })
}

#[cfg(unix)]
fn seconds_and_nanos(seconds: i64, nanos: i64) -> i64 {
    seconds.saturating_mul(1_000_000_000).saturating_add(nanos)
}

fn trim_ascii_whitespace(mut value: &[u8]) -> &[u8] {
    while value.first().is_some_and(u8::is_ascii_whitespace) {
        value = &value[1..];
    }
    while value.last().is_some_and(u8::is_ascii_whitespace) {
        value = &value[..value.len() - 1];
    }
    value
}

fn delegation_marker() -> &'static AhoCorasick {
    static MARKER: OnceLock<AhoCorasick> = OnceLock::new();
    MARKER.get_or_init(|| {
        AhoCorasickBuilder::new()
            .ascii_case_insensitive(true)
            .build(["<codex_delegation", "\\u003ccodex_delegation"])
            .expect("static delegation markers are valid")
    })
}

fn delegation_block_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| {
        Regex::new(r"(?is)<codex_delegation\b[^>]*>(?P<body>.*?)</codex_delegation>")
            .expect("static delegation block pattern is valid")
    })
}

fn delegation_source_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| {
        Regex::new(
            r"(?is)<source_thread_id>\s*(?P<source>[A-Za-z0-9][A-Za-z0-9._:/-]*)\s*</source_thread_id>",
        )
        .expect("static delegation source pattern is valid")
    })
}

fn delegation_input_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| {
        Regex::new(r"(?is)<input>\s*(?P<input>.*?)\s*</input>")
            .expect("static delegation input pattern is valid")
    })
}

fn redacted_environment_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| {
        Regex::new(r"\b[A-Z][A-Z0-9_]*\s*=\s*\[redacted\]")
            .expect("static redacted environment pattern is valid")
    })
}

fn polite_prefix_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| {
        Regex::new(r"(?i)^(?:please\s+|can you\s+|could you\s+|would you\s+)")
            .expect("static polite prefix pattern is valid")
    })
}

fn sentence_end_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| Regex::new(r"[.!?](?:\s|$)").expect("static sentence pattern is valid"))
}

fn trailing_joiner_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| {
        Regex::new(r"(?i)\s+(?:and|for|from|to|using|with)$")
            .expect("static trailing joiner pattern is valid")
    })
}
