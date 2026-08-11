// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Verify desktop catalog filtering and privacy-safe HTML export behavior.
// Design: docs/design/components/CD-001-codex-rollout-metrics.md

use std::fs::{self, FileTimes, OpenOptions};
use std::time::{Duration as StdDuration, SystemTime};

use agent_report_desktop::{
    SearchRequest, render_catalog_html, report_popup_is_allowed, report_window_url,
    search_catalog_sync,
};
use chrono::{DateTime, Local};
use rusqlite::Connection;
use tempfile::TempDir;

fn set_modified_at(path: &std::path::Path, timestamp: &str) {
    let timestamp = DateTime::parse_from_rfc3339(timestamp).expect("parse modification time");
    let elapsed = StdDuration::from_secs(
        timestamp
            .timestamp()
            .try_into()
            .expect("positive modification timestamp"),
    ) + StdDuration::from_nanos(timestamp.timestamp_subsec_nanos().into());
    OpenOptions::new()
        .write(true)
        .open(path)
        .expect("open rollout to set modification time")
        .set_times(FileTimes::new().set_modified(SystemTime::UNIX_EPOCH + elapsed))
        .expect("set rollout modification time");
}

fn rollout_filename(created_at: &str, suffix: &str) -> String {
    let created_at = DateTime::parse_from_rfc3339(created_at).expect("parse creation time");
    format!(
        "rollout-{}-{suffix}.jsonl",
        created_at.with_timezone(&Local).format("%Y-%m-%dT%H-%M-%S")
    )
}

#[test]
fn searches_roots_without_returning_descendant_transcript_content() {
    let directory = TempDir::new().expect("create temporary directory");
    let root = directory.path().join("root.jsonl");
    let child = directory.path().join("child.jsonl");
    fs::write(
        &root,
        concat!(
            "{\"timestamp\":\"2026-07-21T12:00:00Z\",\"type\":\"session_meta\",",
            "\"payload\":{\"id\":\"root\",\"cwd\":\"/work/example\"}}\n",
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",",
            "\"role\":\"user\",\"content\":[{\"text\":\"## My request for Codex:\\n",
            "Build the native report index. SECRET TRANSCRIPT BODY\"}]}}\n"
        ),
    )
    .expect("write root rollout");
    fs::write(
        &child,
        concat!(
            "{\"timestamp\":\"2026-07-21T12:01:00Z\",\"type\":\"session_meta\",",
            "\"payload\":{\"id\":\"child\",\"source\":{\"subagent\":{\"thread_spawn\":{",
            "\"parent_thread_id\":\"root\",\"agent_path\":\"main/child\",",
            "\"agent_nickname\":\"Ada\"}}}}}\n"
        ),
    )
    .expect("write child rollout");

    let response = search_catalog_sync(SearchRequest {
        roots: vec![directory.path().to_path_buf()],
        index_path: Some(directory.path().join("index.sqlite3")),
        state_db_path: None,
        query: "native report".to_owned(),
        from_date: String::new(),
        to_date: String::new(),
        include_descendants: false,
        workers: Some(2),
    })
    .expect("search desktop catalog");

    assert_eq!(response.entries.len(), 1);
    assert_eq!(response.entries[0].thread_id, "root");
    assert_eq!(
        response.entries[0].task_title,
        "Build the native report index"
    );
    let serialized = serde_json::to_string(&response).expect("serialize catalog response");
    assert!(!serialized.contains("SECRET TRANSCRIPT BODY"));
}

#[test]
fn escapes_catalog_html_at_the_native_boundary() {
    let directory = TempDir::new().expect("create temporary directory");
    let rollout = directory.path().join("unsafe.jsonl");
    fs::write(
        &rollout,
        concat!(
            "{\"timestamp\":\"2026-07-21T12:00:00Z\",\"type\":\"session_meta\",",
            "\"payload\":{\"id\":\"root\",\"cwd\":\"/work/<unsafe>\"}}\n",
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",",
            "\"role\":\"user\",\"content\":[{\"text\":\"<script>alert(1)</script>\"}]}}\n"
        ),
    )
    .expect("write rollout");
    let response = search_catalog_sync(SearchRequest {
        roots: vec![directory.path().to_path_buf()],
        index_path: None,
        state_db_path: None,
        query: String::new(),
        from_date: String::new(),
        to_date: String::new(),
        include_descendants: false,
        workers: Some(1),
    })
    .expect("search desktop catalog");

    let html = render_catalog_html(&response);

    assert!(!html.contains("<script>alert(1)</script>"));
    assert!(html.contains("&lt;script&gt;alert(1)&lt;/script&gt;"));
    assert!(html.contains("/work/&lt;unsafe&gt;"));
    assert!(html.contains("href=\"file://"));
}

#[test]
fn accepts_only_existing_local_html_for_report_windows() {
    let directory = TempDir::new().expect("create temporary directory");
    let report = directory.path().join("report with spaces.html");
    let text = directory.path().join("not-a-report.txt");
    fs::write(&report, "<!doctype html><title>Report</title>").expect("write report");
    fs::write(&text, "not html").expect("write text file");

    let url = report_window_url(&report).expect("build report file URL");

    assert_eq!(url.scheme(), "file");
    assert_eq!(
        url.to_file_path().expect("convert URL back to path"),
        report.canonicalize().expect("canonical report path")
    );
    assert!(report_window_url(&text).is_err());
    assert!(report_window_url(&directory.path().join("missing.html")).is_err());
}

#[test]
fn allows_only_the_generated_sequence_companion_as_a_report_popup() {
    let directory = TempDir::new().expect("create temporary directory");
    let report = directory.path().join("run report.html");
    let sequence = directory.path().join("run report-sequence.html");
    let unrelated = directory.path().join("other.html");
    fs::write(&report, "<!doctype html><title>Report</title>").expect("write report");
    fs::write(&sequence, "<!doctype html><title>Sequence</title>").expect("write sequence");
    fs::write(&unrelated, "<!doctype html><title>Other</title>").expect("write other report");

    let mut sequence_url = report_window_url(&sequence).expect("build sequence file URL");
    sequence_url.set_query(Some("view=sequence"));
    sequence_url.set_fragment(Some("agent-sequence"));

    assert!(report_popup_is_allowed(&report, &sequence_url));
    assert!(!report_popup_is_allowed(
        &report,
        &report_window_url(&unrelated).expect("build unrelated file URL")
    ));
    assert!(!report_popup_is_allowed(
        &report,
        &"https://example.com/report.html"
            .parse()
            .expect("parse external URL")
    ));
}

#[test]
fn overlays_codex_app_titles_on_discovered_rollouts() {
    let directory = TempDir::new().expect("create temporary directory");
    let rollout = directory.path().join("root.jsonl");
    fs::write(
        &rollout,
        concat!(
            "{\"timestamp\":\"2026-07-21T12:00:00Z\",\"type\":\"session_meta\",",
            "\"payload\":{\"id\":\"root\",\"cwd\":\"/work/example\"}}\n",
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",",
            "\"role\":\"user\",\"content\":[{\"text\":\"Fallback first prompt\"}]}}\n"
        ),
    )
    .expect("write root rollout");
    let state_path = directory.path().join("state_5.sqlite");
    let connection = Connection::open(&state_path).expect("open state fixture");
    connection
        .execute(
            "CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT NOT NULL)",
            (),
        )
        .expect("create threads fixture");
    connection
        .execute(
            "CREATE TABLE thread_spawn_edges (parent_thread_id TEXT NOT NULL, child_thread_id TEXT PRIMARY KEY, status TEXT NOT NULL)",
            (),
        )
        .expect("create spawn-edge fixture");
    connection
        .execute(
            "INSERT INTO threads (id, title) VALUES (?1, ?2)",
            ("root", "Stored desktop task title"),
        )
        .expect("insert title fixture");

    let response = search_catalog_sync(SearchRequest {
        roots: vec![directory.path().to_path_buf()],
        index_path: None,
        state_db_path: Some(state_path),
        query: "desktop task".to_owned(),
        from_date: String::new(),
        to_date: String::new(),
        include_descendants: false,
        workers: Some(1),
    })
    .expect("search titled desktop catalog");

    assert_eq!(response.entries[0].task_title, "Stored desktop task title");
}

#[test]
fn treats_reused_delegation_tasks_as_roots_when_codex_has_no_spawn_edge() {
    let directory = TempDir::new().expect("create temporary directory");
    let rollout = directory.path().join("reused.jsonl");
    fs::write(
        &rollout,
        concat!(
            "{\"timestamp\":\"2026-07-21T12:00:00Z\",\"type\":\"session_meta\",",
            "\"payload\":{\"id\":\"reused\",\"cwd\":\"/work/example\",",
            "\"thread_source\":\"subagent\"}}\n",
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",",
            "\"role\":\"user\",\"content\":[{\"text\":\"<codex_delegation>",
            "<source_thread_id>origin</source_thread_id><input>Dispatch current work</input>",
            "</codex_delegation>\"}]}}\n"
        ),
    )
    .expect("write reused rollout");
    let state_path = directory.path().join("state_5.sqlite");
    let connection = Connection::open(&state_path).expect("open state fixture");
    connection
        .execute(
            "CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT NOT NULL)",
            (),
        )
        .expect("create threads fixture");
    connection
        .execute(
            "CREATE TABLE thread_spawn_edges (parent_thread_id TEXT NOT NULL, child_thread_id TEXT PRIMARY KEY, status TEXT NOT NULL)",
            (),
        )
        .expect("create spawn-edge fixture");
    connection
        .execute(
            "INSERT INTO threads (id, title) VALUES ('reused', 'Dispatch current work')",
            (),
        )
        .expect("insert task fixture");

    let response = search_catalog_sync(SearchRequest {
        roots: vec![directory.path().to_path_buf()],
        index_path: None,
        state_db_path: Some(state_path),
        query: String::new(),
        from_date: String::new(),
        to_date: String::new(),
        include_descendants: false,
        workers: Some(1),
    })
    .expect("search reused root task");

    assert_eq!(response.entries.len(), 1);
    assert_eq!(response.entries[0].thread_id, "reused");
}

#[test]
fn selects_rollouts_created_updated_or_spanning_the_requested_range() {
    let directory = TempDir::new().expect("create temporary directory");
    for (created_at, suffix, thread_id, recorded_at, modified_at) in [
        (
            "2026-07-21T12:15:00Z",
            "created-during",
            "created-during",
            "2026-07-21T12:15:00Z",
            "2026-07-21T14:00:00Z",
        ),
        (
            "2026-07-21T10:00:00Z",
            "updated-during",
            "updated-during",
            "2026-07-21T10:00:00Z",
            "2026-07-21T12:30:00Z",
        ),
        (
            "2026-07-21T10:00:00Z",
            "spanning",
            "spanning",
            "2026-07-21T10:00:00Z",
            "2026-07-21T14:00:00Z",
        ),
        (
            "2026-07-21T10:00:00Z",
            "completed-before",
            "completed-before",
            "2026-07-21T10:00:00Z",
            "2026-07-21T11:59:00Z",
        ),
        (
            "2026-07-21T13:00:00Z",
            "started-after",
            "started-after",
            "2026-07-21T13:00:00Z",
            "2026-07-21T14:00:00Z",
        ),
    ] {
        let filename = rollout_filename(created_at, suffix);
        let path = directory.path().join(filename);
        fs::write(
            &path,
            format!(
                "{{\"timestamp\":\"{recorded_at}\",\"type\":\"session_meta\",\"payload\":{{\"id\":\"{thread_id}\",\"cwd\":\"/work/example\"}}}}\n\
                 {{\"timestamp\":\"2026-07-21T14:00:00Z\",\"type\":\"response_item\",\"payload\":{{\"type\":\"message\",\"role\":\"user\",\"content\":[{{\"text\":\"Full {thread_id} context.\"}}]}}}}\n"
            ),
        )
        .expect("write dated rollout");
        set_modified_at(&path, modified_at);
    }

    let search = || {
        search_catalog_sync(SearchRequest {
            roots: vec![directory.path().to_path_buf()],
            index_path: Some(directory.path().join("index.sqlite3")),
            state_db_path: None,
            query: String::new(),
            from_date: "2026-07-21T12".to_owned(),
            to_date: "2026-07-21T12".to_owned(),
            include_descendants: false,
            workers: Some(2),
        })
        .expect("search UTC date range")
    };
    let response = search();

    assert_eq!(response.stats.candidate_files, 5);
    assert_eq!(response.stats.scanned_files, 5);
    assert_eq!(response.stats.cached_files, 0);
    let mut selected_ids = response
        .entries
        .iter()
        .map(|entry| entry.thread_id.as_str())
        .collect::<Vec<_>>();
    selected_ids.sort_unstable();
    assert_eq!(
        selected_ids,
        vec!["created-during", "spanning", "updated-during"]
    );
    assert_eq!(
        response
            .entries
            .iter()
            .find(|entry| entry.thread_id == "spanning")
            .expect("spanning rollout entry")
            .task_title,
        "Full spanning context"
    );

    let warm = search();
    assert_eq!(warm.stats.candidate_files, 5);
    assert_eq!(warm.stats.scanned_files, 0);
    assert_eq!(warm.stats.cached_files, 5);
}

#[test]
fn rejects_invalid_or_reversed_date_ranges() {
    let directory = TempDir::new().expect("create temporary directory");
    let request = |from_date: &str, to_date: &str| SearchRequest {
        roots: vec![directory.path().to_path_buf()],
        index_path: None,
        state_db_path: None,
        query: String::new(),
        from_date: from_date.to_owned(),
        to_date: to_date.to_owned(),
        include_descendants: false,
        workers: Some(1),
    };

    assert_eq!(
        search_catalog_sync(request("2026-02-30", "")),
        Err("Invalid From date/hour '2026-02-30'; expected YYYY-MM-DD or YYYY-MM-DDTHH".to_owned())
    );
    assert_eq!(
        search_catalog_sync(request("2026-07-22", "2026-07-21")),
        Err("From date and hour must not be after To date and hour".to_owned())
    );
}
