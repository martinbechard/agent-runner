// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Verify the native report engine's standard-I/O protocol and failure contract.
// Design: docs/design/components/CD-001-codex-rollout-metrics.md

use std::fs;
use std::io::Write;
use std::process::{Command, Stdio};

use serde_json::{Value, json};
use tempfile::TempDir;

fn run_engine(request: &Value) -> std::process::Output {
    let mut child = Command::new(env!("CARGO_BIN_EXE_agent-report-engine"))
        .arg("index")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("start native report engine");
    child
        .stdin
        .take()
        .expect("engine standard input")
        .write_all(request.to_string().as_bytes())
        .expect("write engine request");
    child.wait_with_output().expect("wait for native engine")
}

#[test]
fn returns_one_versioned_json_document_on_standard_output() {
    let directory = TempDir::new().expect("create temporary directory");
    let rollout = directory.path().join("rollout.jsonl");
    fs::write(
        &rollout,
        concat!(
            "{\"timestamp\":\"2026-07-21T12:00:00Z\",",
            "\"type\":\"session_meta\",\"payload\":{\"id\":\"root\"}}\n"
        ),
    )
    .expect("write rollout");

    let output = run_engine(&json!({
        "version": 1,
        "paths": [rollout],
        "index_path": directory.path().join("index.sqlite3"),
        "workers": 2
    }));

    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(output.stderr.is_empty());
    let response: Value = serde_json::from_slice(&output.stdout).expect("valid JSON response");
    assert_eq!(response["version"], 1);
    assert_eq!(response["entries"][0]["identity"]["thread_id"], "root");
    assert_eq!(response["stats"]["scanned_files"], 1);
}

#[test]
fn uses_nonzero_exit_and_stderr_for_contract_failures() {
    let output = run_engine(&json!({
        "version": 99,
        "paths": [],
        "index_path": null,
        "workers": 1
    }));

    assert!(!output.status.success());
    assert!(output.stdout.is_empty());
    assert!(
        String::from_utf8_lossy(&output.stderr)
            .contains("unsupported discovery protocol version 99")
    );
}
