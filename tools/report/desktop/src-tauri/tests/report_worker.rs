// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Verify the native report-worker protocol, authority, diagnostics, and lifecycle boundaries.
// Design: docs/design/components/CD-004-agent-report-worker-protocol.md

#[allow(dead_code)]
#[path = "../src/report_worker.rs"]
mod report_worker;

use std::collections::BTreeMap;
use std::ffi::OsString;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Condvar, Mutex};
use std::time::{Duration, Instant};

use report_worker::{
    AutomationSurfaceWire, ExportModeWire, HostTerminalOutcome, OperationObserver, PathAuthority,
    ProgressCoalescer, ProgressDecision, ProgressEnvelope, RequestEnvelope, RestartReason,
    SanitizedDiagnostic, ServiceConfiguration, StderrSanitizer, StructuredError, SupervisorError,
    TrustedWorkerRequest, WORKER_PROTOCOL_VERSION, WorkerLaunchSpec, WorkerSupervisor,
    WorkerSupervisorConfig, WorkerWireRecord, parse_worker_record,
};
use serde_json::{Map, Value, json};
use tempfile::TempDir;

const OPERATION_ID: &str = "op_75ffcf97671b4ccbaf96790c";
const SNAPSHOT_ID: &str = "snap_46b9630e96ce4dc5a678a517";

fn map(value: Value) -> Map<String, Value> {
    value.as_object().expect("test value is an object").clone()
}

fn line(value: &str) -> Vec<u8> {
    let mut encoded = value.as_bytes().to_vec();
    encoded.push(b'\n');
    encoded
}

fn progress(completed: u64, phase: &str) -> ProgressEnvelope {
    ProgressEnvelope {
        protocol_version: WORKER_PROTOCOL_VERSION,
        operation_id: OPERATION_ID.to_owned(),
        operation: "refresh_snapshot".to_owned(),
        snapshot_id: Some(SNAPSHOT_ID.to_owned()),
        phase: phase.to_owned(),
        completed,
        total: Some(10),
        message: "Refreshing snapshot".to_owned(),
    }
}

#[test]
fn round_trips_exact_wire_records_and_rejects_unknown_missing_nullable_and_wrong_literal_fields() {
    let record = parse_worker_record(
        &line(r#"{"protocol_version":1,"operation_id":"op_75ffcf97671b4ccbaf96790c","type":"progress","operation":"list_events","snapshot_id":null,"phase":"query","completed":4,"total":10,"message":"Reading events"}"#),
        4096,
    )
    .expect("valid progress record");
    assert!(matches!(record, WorkerWireRecord::Progress(_)));

    for invalid in [
        line(
            r#"{"protocol_version":1,"operation_id":"op_75ffcf97671b4ccbaf96790c","type":"progress","operation":"list_events","phase":"query","completed":4,"total":10,"message":"Reading events"}"#,
        ),
        line(
            r#"{"protocol_version":1,"operation_id":"op_75ffcf97671b4ccbaf96790c","type":"progress","operation":"list_events","snapshot_id":null,"phase":"query","completed":4,"total":10,"message":"Reading events","extra":true}"#,
        ),
        line(
            r#"{"protocol_version":1,"operation_id":"op_75ffcf97671b4ccbaf96790c","type":"result","operation":"list_events","snapshot_id":null,"ok":false,"result":{}}"#,
        ),
        line(
            r#"{"protocol_version":1,"operation_id":"op_75ffcf97671b4ccbaf96790c","type":"cancelled","operation":"list_events","snapshot_id":null,"ok":false,"forced":true,"error":{"code":"REPORT_CANCELLED","message":"Operation cancelled","operation_id":"op_75ffcf97671b4ccbaf96790c","recoverable":true,"current_source_revision":null,"preflight_required":false,"restart_from_first_page":false}}"#,
        ),
    ] {
        assert!(parse_worker_record(&invalid, 4096).is_err());
    }
}

#[test]
fn validates_progress_bounds_and_correlation() {
    let decreasing_total = line(
        r#"{"protocol_version":1,"operation_id":"op_75ffcf97671b4ccbaf96790c","type":"progress","operation":"list_events","snapshot_id":null,"phase":"query","completed":11,"total":10,"message":"Reading events"}"#,
    );
    assert!(parse_worker_record(&decreasing_total, 4096).is_err());

    let mismatched_error = line(
        r#"{"protocol_version":1,"operation_id":"op_75ffcf97671b4ccbaf96790c","type":"error","operation":"list_events","snapshot_id":null,"ok":false,"error":{"code":"REPORT_INVALID_REQUEST","message":"Invalid request","operation_id":"op_000000000000000000000001","recoverable":true,"current_source_revision":null,"preflight_required":false,"restart_from_first_page":false}}"#,
    );
    assert!(parse_worker_record(&mismatched_error, 4096).is_err());
}

#[test]
fn progress_coalesces_to_latest_record_and_phase_per_operation() {
    let mut coalescer = ProgressCoalescer::new(Duration::from_millis(50));
    let start = Instant::now();

    assert_eq!(
        coalescer.observe(progress(0, "scan"), start).unwrap(),
        ProgressDecision::Emit(progress(0, "scan"))
    );
    assert_eq!(
        coalescer
            .observe(progress(1, "scan"), start + Duration::from_millis(49))
            .unwrap(),
        ProgressDecision::Pending
    );
    assert_eq!(
        coalescer
            .observe(progress(0, "publish"), start + Duration::from_millis(49))
            .unwrap(),
        ProgressDecision::Pending
    );
    assert_eq!(
        coalescer.flush(start + Duration::from_millis(50)),
        Some(progress(0, "publish"))
    );
    assert!(coalescer.observe(progress(0, "publish"), start).is_err());
}

#[test]
fn rejects_path_fields_in_path_free_operations_at_any_nesting_level() {
    let request = RequestEnvelope {
        protocol_version: WORKER_PROTOCOL_VERSION,
        operation_id: OPERATION_ID.to_owned(),
        operation: "list_events".to_owned(),
        snapshot_id: Some(SNAPSHOT_ID.to_owned()),
        arguments: map(json!({
            "filters": {
                "event_ids": [],
                "agent_ids": [],
                "turn_ids": [],
                "kinds": [],
                "from_time": null,
                "to_time": null,
                "target": "/tmp/not-authorized"
            },
            "cursor": null,
            "page_size": 100
        })),
    };

    assert!(matches!(
        TrustedWorkerRequest::path_free(request),
        Err(SupervisorError::PathNotAuthorized { .. }) | Err(SupervisorError::Protocol { .. })
    ));
}

#[test]
fn operation_bindings_accept_each_exact_path_free_argument_schema() {
    let scope = json!({
        "root_thread_id": "019ff5f0-6b8c-7f92-9f32-14caeeefb442",
        "include_children": false,
        "include_collaborators": false
    });
    let event_filters = json!({
        "event_ids": [], "agent_ids": [], "turn_ids": [], "kinds": [],
        "from_time": null, "to_time": null
    });
    let cases = [
        ("preflight_report", None, json!({"scope": scope.clone()})),
        (
            "open_snapshot",
            None,
            json!({"scope": scope, "preflight_token": "preflight-token"}),
        ),
        ("get_summary", Some(SNAPSHOT_ID), json!({})),
        (
            "list_agents",
            Some(SNAPSHOT_ID),
            json!({
                "filters": {"agent_ids": [], "roles": [], "states": []},
                "cursor": null,
                "page_size": 100
            }),
        ),
        (
            "list_turns",
            Some(SNAPSHOT_ID),
            json!({
                "filters": {
                    "turn_ids": [], "agent_ids": [], "states": [],
                    "from_time": null, "to_time": null
                },
                "cursor": null,
                "page_size": 100
            }),
        ),
        (
            "list_events",
            Some(SNAPSHOT_ID),
            json!({"filters": event_filters.clone(), "cursor": null, "page_size": 100}),
        ),
        (
            "query_time_range",
            Some(SNAPSHOT_ID),
            json!({
                "from_time": "2026-08-12T12:00:00Z",
                "to_time": "2026-08-12T13:00:00Z",
                "measure": "wall_time",
                "requested_resolution_minutes": 5
            }),
        ),
        (
            "query_sequence",
            Some(SNAPSHOT_ID),
            json!({
                "focus_agent_id": null,
                "filters": event_filters,
                "grouping": "operation",
                "cursor": null,
                "page_size": 100
            }),
        ),
        (
            "query_coordination",
            Some(SNAPSHOT_ID),
            json!({
                "work_item_ids": [], "agent_ids": [], "cursor": null, "page_size": 100
            }),
        ),
        (
            "get_event_details",
            Some(SNAPSHOT_ID),
            json!({"event_id": "evt_75ffcf97671b4ccbaf96790c"}),
        ),
        ("refresh_snapshot", Some(SNAPSHOT_ID), json!({})),
        ("close_snapshot", Some(SNAPSHOT_ID), json!({})),
    ];

    for (index, (operation, snapshot_id, arguments)) in cases.into_iter().enumerate() {
        let request = RequestEnvelope {
            protocol_version: WORKER_PROTOCOL_VERSION,
            operation_id: format!("op_{index:024x}"),
            operation: operation.to_owned(),
            snapshot_id: snapshot_id.map(str::to_owned),
            arguments: map(arguments),
        };
        TrustedWorkerRequest::path_free(request)
            .unwrap_or_else(|error| panic!("{operation} must be bound: {error}"));
    }
}

#[test]
fn operation_bindings_reject_unknown_operations_and_snapshot_mismatch() {
    let unknown = RequestEnvelope {
        protocol_version: WORKER_PROTOCOL_VERSION,
        operation_id: OPERATION_ID.to_owned(),
        operation: "unknown_operation".to_owned(),
        snapshot_id: Some(SNAPSHOT_ID.to_owned()),
        arguments: Map::new(),
    };
    assert!(TrustedWorkerRequest::path_free(unknown).is_err());

    let missing_snapshot = RequestEnvelope {
        protocol_version: WORKER_PROTOCOL_VERSION,
        operation_id: OPERATION_ID.to_owned(),
        operation: "get_summary".to_owned(),
        snapshot_id: None,
        arguments: Map::new(),
    };
    assert!(TrustedWorkerRequest::path_free(missing_snapshot).is_err());
}

#[test]
fn export_builder_inserts_target_and_replace_only_from_consumed_grant() {
    let temp = TempDir::new().unwrap();
    let target = temp.path().join("report");
    let grant = report_worker::OutputGrant::for_test(OPERATION_ID, target.clone(), true);

    let request = TrustedWorkerRequest::export(
        OPERATION_ID,
        SNAPSHOT_ID,
        AutomationSurfaceWire::Tauri,
        Some(ExportModeWire::Directory),
        false,
        grant,
    )
    .expect("matching grant");
    let envelope = request.envelope();

    assert_eq!(envelope.operation, "export_snapshot");
    assert_eq!(envelope.arguments.get("target"), Some(&json!(target)));
    assert_eq!(envelope.arguments.get("replace"), Some(&json!(true)));
}

#[cfg(unix)]
#[test]
fn grant_output_target_canonicalizes_without_accepting_a_symlink_ancestor() {
    use std::os::unix::fs::symlink;

    let temp = TempDir::new().unwrap();
    let executable = worker_script(
        &temp,
        "#!/bin/sh\nread -r handshake\nprintf '%s\\n' '{\"protocol_version\":1,\"operation_id\":\"op_000000000000000000000000\",\"type\":\"result\",\"operation\":\"worker_handshake\",\"snapshot_id\":null,\"ok\":true,\"result\":{\"worker_protocol_version\":1,\"worker_package_version\":\"0.10.2\"}}'\nwhile read -r line; do :; done\n",
    );
    let supervisor = WorkerSupervisor::spawn(
        WorkerLaunchSpec {
            executable,
            arguments: vec![],
            environment: BTreeMap::new(),
        },
        supervisor_config(temp.path()),
    )
    .unwrap();
    supervisor.wait_until_ready().unwrap();

    let target = temp.path().join("new-report");
    let grant = supervisor
        .grant_output_target(OPERATION_ID, &target, false)
        .unwrap();
    let request = TrustedWorkerRequest::export(
        OPERATION_ID,
        SNAPSHOT_ID,
        AutomationSurfaceWire::Tauri,
        None,
        false,
        grant,
    )
    .unwrap();
    assert_eq!(
        request.envelope().arguments["target"],
        json!(fs::canonicalize(temp.path()).unwrap().join("new-report"))
    );

    let real = temp.path().join("real");
    fs::create_dir(&real).unwrap();
    let linked = temp.path().join("linked");
    symlink(&real, &linked).unwrap();
    assert!(matches!(
        supervisor.grant_output_target(OPERATION_ID, &linked.join("report"), false),
        Err(SupervisorError::PathNotAuthorized { .. })
    ));
    supervisor.shutdown().unwrap();
}

#[test]
fn stderr_allowlist_maps_valid_record_to_fixed_native_message() {
    let mut sanitizer = StderrSanitizer::new(65_536);
    let diagnostics = sanitizer.ingest(&line(
        r#"{"timestamp":"2026-08-12T12:00:00Z","level":"error","event":"worker.internal_failure","operation_id":"op_75ffcf97671b4ccbaf96790c","code":"REPORT_WORKER_INTERNAL","message":"/secret/path API_KEY=value"}"#,
    ));

    assert_eq!(
        diagnostics,
        vec![SanitizedDiagnostic {
            level: "error",
            event: "worker.internal_failure",
            operation_id: Some(OPERATION_ID.to_owned()),
            code: Some("REPORT_WORKER_INTERNAL".to_owned()),
            message: "Worker execution failed.",
        }]
    );
    assert!(!format!("{diagnostics:?}").contains("secret"));
    assert!(!format!("{diagnostics:?}").contains("API_KEY"));
}

#[test]
fn stderr_rejects_unknown_invalid_and_oversized_lines_once() {
    let mut sanitizer = StderrSanitizer::new(65_536);
    let mut input = vec![0xff, b'\n'];
    input.extend_from_slice(&line(
        r#"{"timestamp":"2026-08-12T12:00:00Z","level":"error","event":"unknown","operation_id":null,"code":"UNKNOWN","message":"raw"}"#,
    ));
    input.extend(std::iter::repeat_n(b'x', 4097));
    input.push(b'\n');

    assert_eq!(
        sanitizer.ingest(&input),
        vec![SanitizedDiagnostic::rejected()]
    );
}

#[cfg(unix)]
fn worker_script(temp: &TempDir, body: &str) -> PathBuf {
    use std::os::unix::fs::PermissionsExt;

    let path = temp.path().join("worker.sh");
    fs::write(&path, body).unwrap();
    fs::set_permissions(&path, fs::Permissions::from_mode(0o700)).unwrap();
    path
}

fn supervisor_config(source_root: &Path) -> WorkerSupervisorConfig {
    WorkerSupervisorConfig {
        max_in_flight: 2,
        cancellation_grace: Duration::from_millis(100),
        startup_timeout: Duration::from_secs(2),
        max_record_bytes: 65_536,
        max_stderr_bytes: 65_536,
        expected_package_version: "0.10.2".to_owned(),
        service_configuration: ServiceConfiguration {
            parser_version: "parser-v1".to_owned(),
            pricing_digest: "sha256:pricing".to_owned(),
            formatter_digest: "sha256:formatters".to_owned(),
            default_page_size: 100,
            max_page_size: 500,
            max_time_buckets: 2_000,
        },
        path_authority: PathAuthority {
            source_roots: vec![source_root.to_path_buf()],
        },
    }
}

#[derive(Default)]
struct RecordingObserver {
    values: Mutex<Vec<HostTerminalOutcome>>,
    ready: Condvar,
}

impl RecordingObserver {
    fn wait_for_terminal(&self) -> HostTerminalOutcome {
        let deadline = Instant::now() + Duration::from_secs(3);
        let mut values = self.values.lock().unwrap();
        while values.is_empty() {
            let remaining = deadline.saturating_duration_since(Instant::now());
            assert!(
                !remaining.is_zero(),
                "timed out waiting for terminal outcome"
            );
            let (next, timeout) = self.ready.wait_timeout(values, remaining).unwrap();
            values = next;
            assert!(!timeout.timed_out() || !values.is_empty());
        }
        values.remove(0)
    }
}

impl OperationObserver for RecordingObserver {
    fn on_progress(&self, _value: ProgressEnvelope) {}

    fn on_terminal(&self, value: HostTerminalOutcome) {
        self.values.lock().unwrap().push(value);
        self.ready.notify_all();
    }
}

#[cfg(unix)]
#[test]
fn starts_worker_and_validates_handshake_before_ready() {
    let temp = TempDir::new().unwrap();
    let executable = worker_script(
        &temp,
        "#!/bin/sh\nread -r handshake\nprintf '%s\\n' '{\"protocol_version\":1,\"operation_id\":\"op_000000000000000000000000\",\"type\":\"result\",\"operation\":\"worker_handshake\",\"snapshot_id\":null,\"ok\":true,\"result\":{\"worker_protocol_version\":1,\"worker_package_version\":\"0.10.2\"}}'\nwhile read -r line; do :; done\n",
    );
    let launch = WorkerLaunchSpec {
        executable,
        arguments: Vec::<OsString>::new(),
        environment: BTreeMap::new(),
    };

    let supervisor = WorkerSupervisor::spawn(launch, supervisor_config(temp.path())).unwrap();
    supervisor.wait_until_ready().unwrap();
    supervisor.shutdown().unwrap();
}

#[cfg(unix)]
#[test]
fn rejects_protocol_and_package_version_mismatch() {
    let temp = TempDir::new().unwrap();
    let executable = worker_script(
        &temp,
        "#!/bin/sh\nread -r handshake\nprintf '%s\\n' '{\"protocol_version\":1,\"operation_id\":\"op_000000000000000000000000\",\"type\":\"result\",\"operation\":\"worker_handshake\",\"snapshot_id\":null,\"ok\":true,\"result\":{\"worker_protocol_version\":1,\"worker_package_version\":\"wrong\"}}'\n",
    );
    let supervisor = WorkerSupervisor::spawn(
        WorkerLaunchSpec {
            executable,
            arguments: vec![],
            environment: BTreeMap::new(),
        },
        supervisor_config(temp.path()),
    )
    .unwrap();

    assert!(matches!(
        supervisor.wait_until_ready(),
        Err(SupervisorError::VersionMismatch { .. })
    ));
    supervisor.shutdown().unwrap();
}

#[cfg(unix)]
#[test]
fn times_out_and_reaps_a_worker_that_never_completes_handshake() {
    let temp = TempDir::new().unwrap();
    let pid_path = temp.path().join("worker-pid");
    let executable = worker_script(
        &temp,
        &format!(
            "#!/bin/sh\nprintf '%s' \"$$\" > '{}'\nread -r handshake\nsleep 10\n",
            pid_path.display()
        ),
    );
    let mut config = supervisor_config(temp.path());
    config.startup_timeout = Duration::from_secs(2);
    let supervisor = WorkerSupervisor::spawn(
        WorkerLaunchSpec {
            executable,
            arguments: vec![],
            environment: BTreeMap::new(),
        },
        config,
    )
    .unwrap();

    let waiter_supervisor = supervisor.clone();
    let waiter = std::thread::spawn(move || waiter_supervisor.wait_until_ready());
    let pid_deadline = Instant::now() + Duration::from_secs(3);
    while !pid_path.exists() && Instant::now() < pid_deadline {
        std::thread::sleep(Duration::from_millis(5));
    }

    assert!(matches!(
        waiter.join().unwrap(),
        Err(SupervisorError::StartupTimeout)
    ));
    let pid = fs::read_to_string(pid_path).unwrap();
    assert!(
        !std::process::Command::new("kill")
            .args(["-0", pid.trim()])
            .stderr(std::process::Stdio::null())
            .status()
            .unwrap()
            .success()
    );
    supervisor.shutdown().unwrap();
}

#[cfg(unix)]
#[test]
fn cooperative_cancel_prevents_forced_termination() {
    let temp = TempDir::new().unwrap();
    let executable = worker_script(
        &temp,
        "#!/bin/sh\nread -r handshake\nprintf '%s\\n' '{\"protocol_version\":1,\"operation_id\":\"op_000000000000000000000000\",\"type\":\"result\",\"operation\":\"worker_handshake\",\"snapshot_id\":null,\"ok\":true,\"result\":{\"worker_protocol_version\":1,\"worker_package_version\":\"0.10.2\"}}'\nwhile read -r line; do case \"$line\" in *'\"type\":\"cancel\"'*) printf '%s\\n' '{\"protocol_version\":1,\"operation_id\":\"op_75ffcf97671b4ccbaf96790c\",\"type\":\"cancelled\",\"operation\":\"get_summary\",\"snapshot_id\":\"snap_46b9630e96ce4dc5a678a517\",\"ok\":false,\"error\":{\"code\":\"REPORT_CANCELLED\",\"message\":\"Operation cancelled\",\"operation_id\":\"op_75ffcf97671b4ccbaf96790c\",\"recoverable\":true,\"current_source_revision\":null,\"preflight_required\":false,\"restart_from_first_page\":false}}' ;; esac; done\n",
    );
    let supervisor = WorkerSupervisor::spawn(
        WorkerLaunchSpec {
            executable,
            arguments: vec![],
            environment: BTreeMap::new(),
        },
        supervisor_config(temp.path()),
    )
    .unwrap();
    supervisor.wait_until_ready().unwrap();
    let observer = Arc::new(RecordingObserver::default());
    let request = TrustedWorkerRequest::path_free(RequestEnvelope {
        protocol_version: 1,
        operation_id: OPERATION_ID.to_owned(),
        operation: "get_summary".to_owned(),
        snapshot_id: Some(SNAPSHOT_ID.to_owned()),
        arguments: Map::new(),
    })
    .unwrap();
    supervisor.submit(request, observer.clone()).unwrap();
    supervisor.cancel(OPERATION_ID).unwrap();

    let HostTerminalOutcome::Cancelled(cancelled) = observer.wait_for_terminal() else {
        panic!("cooperative cancellation must remain a cancelled host outcome");
    };
    assert!(!cancelled.forced);
    std::thread::sleep(Duration::from_millis(150));
    supervisor.restart(RestartReason::Explicit).unwrap();
    supervisor.shutdown().unwrap();
}

#[cfg(unix)]
#[test]
fn shutdown_during_handshake_completes_waiters_without_replacement() {
    let temp = TempDir::new().unwrap();
    let executable = worker_script(&temp, "#!/bin/sh\nread -r handshake\nsleep 10\n");
    let supervisor = WorkerSupervisor::spawn(
        WorkerLaunchSpec {
            executable,
            arguments: vec![],
            environment: BTreeMap::new(),
        },
        supervisor_config(temp.path()),
    )
    .unwrap();
    let waiter_supervisor = supervisor.clone();
    let waiter = std::thread::spawn(move || waiter_supervisor.wait_until_ready());
    std::thread::sleep(Duration::from_millis(20));
    supervisor.shutdown().unwrap();
    assert!(matches!(
        waiter.join().unwrap(),
        Err(SupervisorError::InvalidState {
            actual: report_worker::SupervisorState::Stopping,
            ..
        })
    ));
}

#[cfg(unix)]
#[test]
fn grace_expiry_reports_forced_cancel_and_restarts_without_replay() {
    let temp = TempDir::new().unwrap();
    let count_path = temp.path().join("ordinary-count");
    let executable = worker_script(
        &temp,
        &format!(
            "#!/bin/sh\nread -r handshake\nprintf '%s\\n' '{{\"protocol_version\":1,\"operation_id\":\"op_000000000000000000000000\",\"type\":\"result\",\"operation\":\"worker_handshake\",\"snapshot_id\":null,\"ok\":true,\"result\":{{\"worker_protocol_version\":1,\"worker_package_version\":\"0.10.2\"}}}}'\nwhile read -r line; do case \"$line\" in *'\"type\":\"cancel\"'*) : ;; *) printf x >> '{}' ;; esac; done\n",
            count_path.display()
        ),
    );
    let launch = WorkerLaunchSpec {
        executable,
        arguments: vec![],
        environment: BTreeMap::new(),
    };
    let supervisor = WorkerSupervisor::spawn(launch, supervisor_config(temp.path())).unwrap();
    supervisor.wait_until_ready().unwrap();
    let observer = Arc::new(RecordingObserver::default());
    let request = TrustedWorkerRequest::path_free(RequestEnvelope {
        protocol_version: 1,
        operation_id: OPERATION_ID.to_owned(),
        operation: "get_summary".to_owned(),
        snapshot_id: Some(SNAPSHOT_ID.to_owned()),
        arguments: Map::new(),
    })
    .unwrap();
    supervisor.submit(request, observer.clone()).unwrap();
    supervisor.cancel(OPERATION_ID).unwrap();

    let HostTerminalOutcome::Cancelled(cancelled) = observer.wait_for_terminal() else {
        panic!("forced cancellation must produce a cancelled host outcome");
    };
    assert!(cancelled.forced);
    supervisor.wait_until_ready().unwrap();
    assert_eq!(fs::read_to_string(&count_path).unwrap(), "x");
    supervisor.restart(RestartReason::Explicit).unwrap();
    supervisor.shutdown().unwrap();
}

#[test]
fn operation_observer_satisfies_send_sync_static_bounds() {
    fn assert_observer<T: Send + Sync + 'static>() {}
    assert_observer::<RecordingObserver>();
}

#[test]
fn structured_error_shape_is_publicly_constructible_for_host_outcomes() {
    let error = StructuredError {
        code: "REPORT_CANCELLED".to_owned(),
        message: "Operation cancelled".to_owned(),
        operation_id: Some(OPERATION_ID.to_owned()),
        recoverable: true,
        current_source_revision: None,
        preflight_required: false,
        restart_from_first_page: false,
    };
    assert_eq!(error.operation_id.as_deref(), Some(OPERATION_ID));
}
