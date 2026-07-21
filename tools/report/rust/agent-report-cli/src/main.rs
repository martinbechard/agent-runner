// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Expose the shared native report engine through a versioned JSON standard-I/O protocol.
// Design: docs/design/components/CD-001-codex-rollout-metrics.md

use std::io::{self, Read};
use std::process::ExitCode;

use agent_report_core::{DiscoveryRequest, index_rollouts};

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("agent-report-engine: {error}");
            ExitCode::FAILURE
        }
    }
}

fn run() -> Result<(), String> {
    let command = std::env::args().nth(1).unwrap_or_default();
    if command != "index" {
        return Err("expected command `index`".to_owned());
    }
    let mut request_json = String::new();
    io::stdin()
        .read_to_string(&mut request_json)
        .map_err(|error| format!("unable to read request: {error}"))?;
    let request = serde_json::from_str::<DiscoveryRequest>(&request_json)
        .map_err(|error| format!("invalid discovery request: {error}"))?;
    let response = index_rollouts(request, |_| {}).map_err(|error| error.to_string())?;
    serde_json::to_writer(io::stdout().lock(), &response)
        .map_err(|error| format!("unable to write response: {error}"))?;
    Ok(())
}
