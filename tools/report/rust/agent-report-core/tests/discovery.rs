// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Verify native rollout discovery, concurrency, and incremental index behavior.
// Design: docs/design/components/CD-001-codex-rollout-metrics.md

use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};

use agent_report_core::{DiscoveryRequest, index_rollouts, read_codex_task_titles};
use rusqlite::Connection;
use serde_json::{Value, json};
use tempfile::TempDir;

fn write_lines(path: &Path, lines: &[Value]) {
    let body = lines
        .iter()
        .map(Value::to_string)
        .collect::<Vec<_>>()
        .join("\n");
    fs::write(path, format!("{body}\n")).expect("write rollout fixture");
}

fn session_record(thread_id: &str, parent: Option<&str>) -> Value {
    let source = parent.map(|parent_thread_id| {
        json!({
            "subagent": {
                "thread_spawn": {
                    "parent_thread_id": parent_thread_id,
                    "agent_path": format!("main/{thread_id}"),
                    "agent_nickname": "Ada"
                }
            }
        })
    });
    json!({
        "timestamp": "2026-07-21T12:00:00Z",
        "type": "session_meta",
        "payload": {
            "id": thread_id,
            "cwd": "/workspace/example",
            "source": source
        }
    })
}

fn user_record(text: &str) -> Value {
    json!({
        "timestamp": "2026-07-21T12:00:01Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": text}]
        }
    })
}

fn request(paths: Vec<PathBuf>, index_path: Option<PathBuf>, workers: usize) -> DiscoveryRequest {
    DiscoveryRequest {
        version: 1,
        paths,
        index_path,
        workers: Some(workers),
    }
}

#[test]
fn reads_nonempty_codex_app_titles_by_thread_id() {
    let directory = TempDir::new().expect("create temporary directory");
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
            "INSERT INTO threads (id, title) VALUES (?1, ?2), (?3, ?4)",
            ("root", "Stored task title", "blank", ""),
        )
        .expect("insert title fixtures");

    let titles =
        read_codex_task_titles(&state_path, ["root", "blank", "missing"].map(str::to_owned))
            .expect("read Codex task titles");

    assert_eq!(
        titles,
        HashMap::from([("root".to_owned(), "Stored task title".to_owned())])
    );
}

#[test]
fn streams_identity_title_and_mixed_case_delegation_metadata() {
    let directory = TempDir::new().expect("create temporary directory");
    let path = directory.path().join("rollout.jsonl");
    let delegation = concat!(
        "<CoDeX_DeLeGaTiOn>\n",
        "<source_thread_id>source-thread</source_thread_id>\n",
        "<input>Continue the linked task</input>\n",
        "</CoDeX_DeLeGaTiOn>"
    );
    write_lines(
        &path,
        &[
            session_record("child-thread", Some("parent-thread")),
            user_record("## My request for Codex:\nInvestigate native indexing performance."),
            user_record(delegation),
        ],
    );
    fs::OpenOptions::new()
        .append(true)
        .open(&path)
        .expect("open fixture")
        .write_all(b"{partial")
        .expect("append partial JSON");

    let response =
        index_rollouts(request(vec![path.clone()], None, 2), |_| {}).expect("discover rollout");

    assert_eq!(response.version, 1);
    assert_eq!(response.stats.scanned_files, 1);
    let entry = &response.entries[0];
    let identity = entry.identity.as_ref().expect("rollout identity");
    assert_eq!(identity.thread_id, "child-thread");
    assert_eq!(identity.parent_thread_id, "parent-thread");
    assert_eq!(identity.agent_path, "main/child-thread");
    assert_eq!(identity.agent_nickname, "Ada");
    assert_eq!(entry.started_at, "2026-07-21T12:00:00Z");
    assert_eq!(entry.workspace, "/workspace/example");
    assert!(entry.task_title.is_empty());
    assert_eq!(entry.delegation_source_ids, vec!["source-thread"]);
}

#[test]
fn derives_root_title_from_delegation_input_instead_of_xml_tags() {
    let directory = TempDir::new().expect("create temporary directory");
    let path = directory.path().join("delegated-root.jsonl");
    write_lines(
        &path,
        &[
            session_record("delegated-root", None),
            user_record(
                "<codex_delegation><source_thread_id>coordinator</source_thread_id>\
                 <input>Build the shared native report engine.</input></codex_delegation>",
            ),
        ],
    );

    let response =
        index_rollouts(request(vec![path], None, 1), |_| {}).expect("discover delegated root");

    assert_eq!(
        response.entries[0].task_title,
        "Build the shared native report engine"
    );
    assert_eq!(
        response.entries[0]
            .identity
            .as_ref()
            .expect("rollout identity")
            .parent_thread_id,
        ""
    );
}

#[test]
fn infers_parent_from_initial_delegation_without_spawn_metadata() {
    let directory = TempDir::new().expect("create temporary directory");
    let path = directory.path().join("delegated-subagent.jsonl");
    write_lines(
        &path,
        &[
            json!({
                "timestamp": "2026-07-21T12:00:00Z",
                "type": "session_meta",
                "payload": {
                    "id": "delegated-subagent",
                    "cwd": "/workspace/example",
                    "source": "vscode",
                    "thread_source": "subagent"
                }
            }),
            user_record("<recommended_plugins></recommended_plugins>"),
            user_record(
                "<codex_delegation><source_thread_id>coordinator</source_thread_id>\
                 <input>Build the shared native report engine.</input></codex_delegation>",
            ),
        ],
    );

    let response =
        index_rollouts(request(vec![path], None, 1), |_| {}).expect("discover delegated subagent");

    let entry = &response.entries[0];
    let identity = entry.identity.as_ref().expect("rollout identity");
    assert_eq!(identity.parent_thread_id, "coordinator");
    assert_eq!(entry.task_title, "Build the shared native report engine");
    assert_eq!(entry.delegation_source_ids, vec!["coordinator"]);
}

#[test]
fn derives_delegation_title_after_the_user_request_marker() {
    let directory = TempDir::new().expect("create temporary directory");
    let path = directory.path().join("delegated-root-with-context.jsonl");
    write_lines(
        &path,
        &[
            session_record("delegated-root-with-context", None),
            user_record(
                "<in-app-browser-context>local context</in-app-browser-context>\n\
                 ## My request for Codex:\n\
                 <codex_delegation><source_thread_id>coordinator</source_thread_id>\
                 <input>&lt;codex_delegation&gt;&lt;source_thread_id&gt;parent&lt;/source_thread_id&gt;\
                 &lt;input&gt;Build the shared native desktop index.&lt;/input&gt;\
                 &lt;/codex_delegation&gt;</input></codex_delegation>",
            ),
        ],
    );

    let response =
        index_rollouts(request(vec![path], None, 1), |_| {}).expect("discover delegated root");

    assert_eq!(
        response.entries[0].task_title,
        "Build the shared native desktop index"
    );
}

#[test]
fn reuses_stable_cache_and_invalidates_only_changed_files() {
    let directory = TempDir::new().expect("create temporary directory");
    let index_path = directory.path().join("discovery.sqlite3");
    let first_path = directory.path().join("first.jsonl");
    let second_path = directory.path().join("second.jsonl");
    write_lines(&first_path, &[session_record("first", None)]);
    write_lines(&second_path, &[session_record("second", None)]);
    let paths = vec![first_path.clone(), second_path.clone()];

    let first = index_rollouts(request(paths.clone(), Some(index_path.clone()), 2), |_| {})
        .expect("build discovery index");
    assert_eq!(first.stats.scanned_files, 2);
    assert_eq!(first.stats.cached_files, 0);

    let warm = index_rollouts(request(paths.clone(), Some(index_path.clone()), 2), |_| {})
        .expect("reuse discovery index");
    assert_eq!(warm.stats.scanned_files, 0);
    assert_eq!(warm.stats.cached_files, 2);

    write_lines(&second_path, &[session_record("replacement", None)]);
    let changed = index_rollouts(request(paths, Some(index_path), 2), |_| {})
        .expect("refresh changed discovery metadata");
    assert_eq!(changed.stats.scanned_files, 1);
    assert_eq!(changed.stats.cached_files, 1);
    assert_eq!(
        changed.entries[1]
            .identity
            .as_ref()
            .expect("replacement identity")
            .thread_id,
        "replacement"
    );
}

#[test]
fn preserves_input_order_with_bounded_parallel_workers() {
    let directory = TempDir::new().expect("create temporary directory");
    let paths = (0..40)
        .map(|index| {
            let path = directory.path().join(format!("{index:02}.jsonl"));
            write_lines(
                &path,
                &[session_record(&format!("thread-{index:02}"), None)],
            );
            path
        })
        .collect::<Vec<_>>();

    let response =
        index_rollouts(request(paths, None, 3), |_| {}).expect("discover rollout set in parallel");

    assert_eq!(response.stats.candidate_files, 40);
    assert_eq!(response.stats.scanned_files, 40);
    let ids = response
        .entries
        .iter()
        .map(|entry| entry.identity.as_ref().expect("identity").thread_id.clone())
        .collect::<Vec<_>>();
    assert_eq!(
        ids,
        (0..40)
            .map(|index| format!("thread-{index:02}"))
            .collect::<Vec<_>>()
    );
}

#[test]
fn reports_an_unavailable_index_instead_of_changing_algorithms() {
    let directory = TempDir::new().expect("create temporary directory");
    let path = directory.path().join("rollout.jsonl");
    let unavailable_index = directory.path().join("index.sqlite3");
    fs::create_dir(&unavailable_index).expect("create directory at index path");
    write_lines(&path, &[session_record("root", None)]);

    let error = index_rollouts(request(vec![path], Some(unavailable_index), 1), |_| {})
        .expect_err("index failure must be surfaced");

    assert!(error.to_string().contains("discovery index"));
}

use std::io::Write as _;
