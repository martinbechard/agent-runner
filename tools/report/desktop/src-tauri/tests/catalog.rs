// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Verify desktop catalog filtering and privacy-safe HTML export behavior.
// Design: docs/design/components/CD-001-codex-rollout-metrics.md

use std::fs;

use agent_report_desktop::{
    SearchRequest, render_catalog_html, report_window_url, search_catalog_sync,
};
use tempfile::TempDir;

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
        query: "native report".to_owned(),
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
        query: String::new(),
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
