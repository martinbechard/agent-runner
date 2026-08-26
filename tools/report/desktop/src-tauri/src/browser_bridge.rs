// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Expose the existing native report host to an authenticated development browser.
// Design: docs/architecture/ARC-001-agent-report-dynamic-app-and-static-export.md

use std::env;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::mpsc;
use std::thread;

use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use tauri::{AppHandle, Manager};
use tauri_plugin_shell::ShellExt;

use super::{
    CatalogSearchRequest, NativeReportState, execute_path_free, project_catalog_response,
    register_authorized_sources, register_root, resolve_catalog_search, search_catalog_sync,
};

const ENABLE_ENV: &str = "AGENT_REPORT_WEB_BRIDGE";
const MAX_REQUEST_BYTES: usize = 1_048_576;
const DEFAULT_ORIGIN: &str = "http://127.0.0.1:1420";

#[derive(Deserialize)]
struct BridgeCommand {
    command: String,
    payload: Value,
}

#[allow(deprecated, reason = "open only the authenticated loopback development URL")]
pub(crate) fn start_if_enabled(app: AppHandle) -> Result<(), std::io::Error> {
    if env::var(ENABLE_ENV).ok().as_deref() != Some("1") {
        return Ok(());
    }
    let origin = env::var("AGENT_REPORT_WEB_ORIGIN").unwrap_or_else(|_| DEFAULT_ORIGIN.to_owned());
    if origin != DEFAULT_ORIGIN && origin != "http://localhost:1420" {
        return Err(std::io::Error::other(
            "AGENT_REPORT_WEB_ORIGIN must be the local Vite origin",
        ));
    }
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let address = listener.local_addr()?;
    let token = launch_token();
    let browser_url = format!(
        "{origin}/?transport=live&bridge=http%3A%2F%2F{}#token={token}",
        address
    );
    eprintln!("Agent Report live browser: {browser_url}");
    app.shell()
        .open(browser_url, None)
        .map_err(std::io::Error::other)?;
    for window in app.webview_windows().values() {
        window.hide().map_err(std::io::Error::other)?;
    }
    thread::Builder::new()
        .name("agent-report-web-bridge".to_owned())
        .spawn(move || {
            for connection in listener.incoming() {
                match connection {
                    Ok(stream) => {
                        let connection_app = app.clone();
                        let connection_origin = origin.clone();
                        let connection_token = token.clone();
                        let _ = thread::Builder::new()
                            .name("agent-report-web-request".to_owned())
                            .spawn(move || {
                                handle_connection(
                                    stream,
                                    &connection_app,
                                    &connection_origin,
                                    &connection_token,
                                );
                            });
                    }
                    Err(error) => eprintln!("Agent Report web bridge connection failed: {error}"),
                }
            }
        })?;
    Ok(())
}

fn launch_token() -> String {
    let mut random = [0_u8; 32];
    getrandom::fill(&mut random)
        .expect("operating-system randomness is required for the web bridge");
    format!("{:x}", Sha256::digest(random))
}

fn handle_connection(mut stream: TcpStream, app: &AppHandle, allowed_origin: &str, token: &str) {
    let response = read_request(&mut stream)
        .and_then(|request| authorize_and_dispatch(request, app, allowed_origin, token));
    let (status, body) = match response {
        Ok(value) => (200, json!({"ok": true, "result": value})),
        Err((status, error)) => (status, json!({"ok": false, "error": error})),
    };
    let body = serde_json::to_vec(&body).unwrap_or_else(|_| b"{\"ok\":false}".to_vec());
    let reason = if status == 200 {
        "OK"
    } else if status == 401 {
        "Unauthorized"
    } else if status == 403 {
        "Forbidden"
    } else if status == 405 {
        "Method Not Allowed"
    } else {
        "Bad Request"
    };
    let headers = format!(
        "HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nAccess-Control-Allow-Origin: {allowed_origin}\r\nAccess-Control-Allow-Methods: POST, OPTIONS\r\nAccess-Control-Allow-Headers: authorization, content-type\r\nVary: Origin\r\nConnection: close\r\n\r\n",
        body.len()
    );
    let _ = stream.write_all(headers.as_bytes());
    let _ = stream.write_all(&body);
}

struct HttpRequest {
    method: String,
    path: String,
    headers: Vec<(String, String)>,
    body: Vec<u8>,
}

fn read_request(stream: &mut TcpStream) -> Result<HttpRequest, (u16, Value)> {
    let mut bytes = Vec::new();
    let mut buffer = [0_u8; 8192];
    loop {
        let count = stream.read(&mut buffer).map_err(invalid_io)?;
        if count == 0 {
            break;
        }
        bytes.extend_from_slice(&buffer[..count]);
        if bytes.len() > MAX_REQUEST_BYTES {
            return Err(error(
                400,
                "REPORT_INVALID_REQUEST",
                "Bridge request exceeds the size limit.",
            ));
        }
        if let Some(header_end) = find_header_end(&bytes) {
            let header_text = String::from_utf8_lossy(&bytes[..header_end]);
            let content_length = header_text
                .lines()
                .find_map(|line| {
                    line.split_once(':')
                        .filter(|(name, _)| name.eq_ignore_ascii_case("content-length"))
                        .and_then(|(_, value)| value.trim().parse::<usize>().ok())
                })
                .unwrap_or(0);
            if content_length > MAX_REQUEST_BYTES {
                return Err(error(
                    400,
                    "REPORT_INVALID_REQUEST",
                    "Bridge request exceeds the size limit.",
                ));
            }
            if bytes.len() >= header_end + 4 + content_length {
                break;
            }
        }
    }
    let header_end = find_header_end(&bytes)
        .ok_or_else(|| error(400, "REPORT_INVALID_REQUEST", "Malformed HTTP request."))?;
    let head = String::from_utf8(bytes[..header_end].to_vec())
        .map_err(|_| error(400, "REPORT_INVALID_REQUEST", "HTTP headers must be UTF-8."))?;
    let mut lines = head.split("\r\n");
    let mut request_line = lines.next().unwrap_or_default().split_whitespace();
    let method = request_line.next().unwrap_or_default().to_owned();
    let path = request_line.next().unwrap_or_default().to_owned();
    let headers = lines
        .filter_map(|line| line.split_once(':'))
        .map(|(name, value)| (name.trim().to_ascii_lowercase(), value.trim().to_owned()))
        .collect();
    Ok(HttpRequest {
        method,
        path,
        headers,
        body: bytes[header_end + 4..].to_vec(),
    })
}

fn authorize_and_dispatch(
    request: HttpRequest,
    app: &AppHandle,
    allowed_origin: &str,
    token: &str,
) -> Result<Value, (u16, Value)> {
    let header = |name: &str| {
        request
            .headers
            .iter()
            .find(|(key, _)| key == name)
            .map(|(_, value)| value.as_str())
    };
    if header("origin") != Some(allowed_origin) {
        return Err(error(
            403,
            "REPORT_INVALID_REQUEST",
            "Bridge origin is not authorized.",
        ));
    }
    if request.method == "OPTIONS" && request.path == "/api/command" {
        return Ok(Value::Null);
    }
    if request.method != "POST" || request.path != "/api/command" {
        return Err(error(
            405,
            "REPORT_INVALID_REQUEST",
            "Only POST /api/command is available.",
        ));
    }
    if header("authorization") != Some(&format!("Bearer {token}")) {
        return Err(error(
            401,
            "REPORT_UNAVAILABLE",
            "Bridge authorization failed.",
        ));
    }
    let command: BridgeCommand = serde_json::from_slice(&request.body).map_err(|_| {
        error(
            400,
            "REPORT_INVALID_REQUEST",
            "Bridge command is invalid JSON.",
        )
    })?;
    dispatch(app, command).map_err(|value| (400, value))
}

fn dispatch(app: &AppHandle, command: BridgeCommand) -> Result<Value, Value> {
    match command.command.as_str() {
        "desktop_defaults" => {
            let state = app.state::<NativeReportState>();
            let roots = env::var_os("HOME")
                .into_iter()
                .flat_map(|home| {
                    let codex = std::path::PathBuf::from(home).join(".codex");
                    [codex.join("sessions"), codex.join("archived_sessions")]
                })
                .filter(|path| path.is_dir())
                .map(|path| register_root(&state, path))
                .collect::<Result<Vec<_>, _>>()
                .map_err(string_error)?;
            Ok(json!({"roots": roots, "diagnosticsAvailable": false}))
        }
        "search_rollouts" => {
            let request = serde_json::from_value::<CatalogSearchRequest>(command.payload)
                .map_err(|_| protocol_error("Catalog request is invalid."))?;
            let state = app.state::<NativeReportState>();
            let search = resolve_catalog_search(request, &state).map_err(string_error)?;
            register_authorized_sources(&search.roots, &state).map_err(string_error)?;
            let response = search_catalog_sync(search).map_err(string_error)?;
            serde_json::to_value(project_catalog_response(&response, &state).map_err(string_error)?)
                .map_err(|_| protocol_error("Catalog response could not be encoded."))
        }
        "preflight_report"
        | "open_snapshot"
        | "get_summary"
        | "list_agents"
        | "list_turns"
        | "list_events"
        | "query_snapshot_time_range"
        | "query_sequence"
        | "query_coordination"
        | "get_event_details"
        | "refresh_snapshot"
        | "close_snapshot" => {
            let operation = match command.command.as_str() {
                "preflight_report" => "preflight_report",
                "open_snapshot" => "open_snapshot",
                "get_summary" => "get_summary",
                "list_agents" => "list_agents",
                "list_turns" => "list_turns",
                "list_events" => "list_events",
                "query_snapshot_time_range" => "query_snapshot_time_range",
                "query_sequence" => "query_sequence",
                "query_coordination" => "query_coordination",
                "get_event_details" => "get_event_details",
                "refresh_snapshot" => "refresh_snapshot",
                "close_snapshot" => "close_snapshot",
                _ => unreachable!(),
            };
            let (sender, receiver) = mpsc::sync_channel(1);
            let command_app = app.clone();
            tauri::async_runtime::spawn(async move {
                let _ =
                    sender.send(execute_path_free(command_app, operation, command.payload).await);
            });
            receiver
                .recv()
                .map_err(|_| protocol_error("Report command stopped unexpectedly."))?
                .map_err(|error| {
                    serde_json::to_value(error)
                        .unwrap_or_else(|_| protocol_error("Report command failed."))
                })
        }
        "record_client_error"
        | "open_diagnostic_log"
        | "open_report_window"
        | "reopen_export"
        | "open_source_location"
        | "cancel_report_operation" => Ok(Value::Null),
        _ => Err(protocol_error("Bridge command is not available.")),
    }
}

fn find_header_end(bytes: &[u8]) -> Option<usize> {
    bytes.windows(4).position(|window| window == b"\r\n\r\n")
}
fn invalid_io(_error: std::io::Error) -> (u16, Value) {
    error(
        400,
        "REPORT_INVALID_REQUEST",
        "Bridge request could not be read.",
    )
}
fn string_error(_message: String) -> Value {
    protocol_error("The native catalog operation failed.")
}
fn protocol_error(message: &str) -> Value {
    json!({"code":"REPORT_INVALID_REQUEST","message":message,"operationId":null,"recoverable":true,"currentSourceRevision":null,"preflightRequired":false,"restartFromFirstPage":false})
}
fn error(status: u16, code: &str, message: &str) -> (u16, Value) {
    (status, json!({"code":code,"message":message}))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn launch_tokens_are_256_bit_hex_values() {
        let first = launch_token();
        let second = launch_token();
        assert_eq!(first.len(), 64);
        assert!(first.bytes().all(|byte| byte.is_ascii_hexdigit()));
        assert_ne!(first, second);
    }

    #[test]
    fn header_boundary_requires_the_complete_delimiter() {
        assert_eq!(find_header_end(b"POST / HTTP/1.1\r\n\r\n{}"), Some(15));
        assert_eq!(find_header_end(b"POST / HTTP/1.1\r\n"), None);
    }
}
