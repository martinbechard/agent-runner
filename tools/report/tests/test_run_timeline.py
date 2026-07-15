# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Modified with AI assistance.
# Responsibility: Verify cross-tool, Codex, and Junie execution reporting.
# Design: docs/design/components/CD-001-codex-rollout-metrics.md

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


SPARK_PRICING_MODEL = "gpt-5.3-codex-spark"
SPARK_LOG_INPUT_TOKENS = 1000
SPARK_LOG_CACHED_INPUT_TOKENS = 500
SPARK_LOG_OUTPUT_TOKENS = 200
ZERO_COST_USD = 0.0
SPARK_ZERO_RATE_PER_MILLION = 0.0
CODEX_ROLLOUT_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "codex-rollouts"


def _load_module():
    tool_root = Path(__file__).resolve().parents[1]
    script_path = tool_root / "scripts" / "run-timeline.py"
    spec = importlib.util.spec_from_file_location("run_timeline", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_junie_session(root: Path) -> Path:
    session = root / "session-260714-000000-test"
    session.mkdir()
    main = {"id": "main-agent", "kind": "MainAgent", "name": "main"}
    custom = {"id": "custom-agent", "kind": "CustomAgent", "name": "reviewer"}

    def agent_event(timestamp: int, agent: dict[str, str], **event):
        return {
            "kind": "SessionA2uxEvent",
            "timestampMs": timestamp,
            "event": {"agentEvent": {"agent": agent, **event}},
        }

    records = [
        {
            "kind": "UserPromptEvent",
            "timestampMs": 1_783_993_818_000,
            "requestId": "request-1",
            "prompt": "Synthetic prompt",
        },
        {
            "kind": "TaskStartedEvent",
            "timestampMs": 1_783_993_818_010,
            "taskId": "task-1",
        },
        agent_event(
            1_783_993_818_020,
            main,
            kind="LlmResponseMetadataEvent",
            modelUsage=[
                {
                    "model": "gpt-main",
                    "inputTokens": 10,
                    "cacheInputTokens": 5,
                    "cacheCreateTokens": 2,
                    "outputTokens": 3,
                    "cost": 0.01,
                }
            ],
        ),
        agent_event(
            1_783_993_818_030,
            main,
            kind="TerminalBlockUpdatedEvent",
            stepId="terminal-1",
            status="IN_PROGRESS",
            command="API_TOKEN=PRIVATE echo hello",
            output="",
        ),
        agent_event(
            1_783_993_818_040,
            main,
            kind="TerminalBlockUpdatedEvent",
            stepId="terminal-1",
            status="COMPLETED",
            command="API_TOKEN=PRIVATE echo hello",
            output="password=PRIVATE\nhello",
        ),
        agent_event(
            1_783_993_818_045,
            main,
            kind="TerminalBlockUpdatedEvent",
            stepId="write-1",
            status="IN_PROGRESS",
            command=(
                "mkdir -p docs/architecture docs/wiki && "
                "cat > docs/architecture/example.md <<'DOC_EOF'\n"
                "# Example\n"
                "cat > ignored-example.md <<'NOT_A_COMMAND'\n"
                "DOC_EOF\n"
                "cat > docs/wiki/index.md <<'WIKI_EOF'\n"
                "# Wiki\n"
                "WIKI_EOF"
            ),
            output="",
        ),
        agent_event(
            1_783_993_818_046,
            main,
            kind="TerminalBlockUpdatedEvent",
            stepId="write-1",
            status="COMPLETED",
            command=(
                "mkdir -p docs/architecture docs/wiki && "
                "cat > docs/architecture/example.md <<'DOC_EOF'\n"
                "# Example\n"
                "cat > ignored-example.md <<'NOT_A_COMMAND'\n"
                "DOC_EOF\n"
                "cat > docs/wiki/index.md <<'WIKI_EOF'\n"
                "# Wiki\n"
                "WIKI_EOF"
            ),
            output="Created documentation",
        ),
        agent_event(
            1_783_993_818_050,
            main,
            kind="CustomAgentBlockUpdatedEvent",
            stepId="custom-1",
            status="STARTED",
            name="reviewer",
            model="claude-reviewer",
        ),
        agent_event(
            1_783_993_818_060,
            custom,
            kind="AgentCurrentStatusUpdatedEvent",
            status="working",
        ),
        agent_event(
            1_783_993_818_070,
            main,
            kind="LlmResponseMetadataEvent",
            modelUsage=[
                {
                    "model": "claude-reviewer",
                    "inputTokens": 4,
                    "cacheInputTokens": 6,
                    "cacheCreateTokens": 1,
                    "outputTokens": 2,
                    "cost": 0.02,
                }
            ],
        ),
        agent_event(
            1_783_993_818_080,
            custom,
            kind="ViewFilesBlockUpdatedEvent",
            stepId="read-1",
            status="COMPLETED",
            files=[{"relativePath": "src/example.py"}],
            details="Read one file",
        ),
        agent_event(
            1_783_993_818_090,
            main,
            kind="CustomAgentBlockUpdatedEvent",
            stepId="custom-1",
            status="FINISHED",
            name="reviewer",
            model="claude-reviewer",
        ),
        {
            "kind": "TaskState",
            "timestampMs": 1_783_993_818_100,
            "state": "COMPLETED",
        },
    ]
    (session / "events.jsonl").write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return session


def test_human_readable_durations_use_hours_at_sixty_minutes():
    module = _load_module()

    assert module._fmt_duration(59) == "59s"
    assert module._fmt_duration(3_599) == "59m59s"
    assert module._fmt_duration(3_600) == "1h00m00s"
    assert module._fmt_duration(67_513) == "18h45m13s"
    assert module._format_ms(67_513_000) == "18h45m13s"

    started = datetime(2026, 7, 14, tzinfo=timezone.utc)
    step = module.Step("long", started, started + timedelta(seconds=67_513))
    timeline = module.PhaseTimeline("phase", 1, steps=[step])
    assert step.duration_str == "18h45m13s"
    assert timeline.total_str == "18h45m13s"


def test_parse_native_codex_rollout_uses_exclusive_cumulative_deltas():
    module = _load_module()

    thread = module.parse_codex_rollout(CODEX_ROLLOUT_FIXTURES / "root.jsonl")

    assert thread.thread_id == "root-thread"
    assert thread.terminal_state == "complete"
    assert len(thread.responses) == 2
    assert thread.responses[0].usage.input_tokens == 100
    assert thread.responses[1].usage.input_tokens == 50
    assert thread.token_totals.input_tokens == 150
    assert thread.token_totals.cached_input_tokens == 60
    assert thread.token_totals.uncached_input_tokens == 90
    assert thread.token_totals.output_tokens == 30
    assert thread.token_totals.reasoning_tokens == 8
    assert thread.token_totals.processed_tokens == 180
    assert thread.unattributed_usage.processed_tokens == 0
    assert thread.tool_intervals[0].argument_summary == (
        "API_TOKEN=[redacted] python app.py"
    )


def test_native_codex_tool_argument_summary_redacts_sensitive_content():
    module = _load_module()

    summary = module._tool_argument_summary(
        {
            "arguments": json.dumps(
                {
                    "target": "reviewer",
                    "message": "PRIVATE-MESSAGE-CONTENT",
                    "api_key": "PRIVATE-API-KEY",
                    "max_tokens": 100,
                }
            )
        }
    )

    assert '"target":"reviewer"' in summary
    assert '"message":"[23 chars]"' in summary
    assert '"api_key":"[redacted]"' in summary
    assert '"max_tokens":100' in summary
    assert "PRIVATE" not in summary


def test_native_codex_send_message_argument_summary_includes_preview_and_length():
    module = _load_module()
    message = "0123456789" * 7

    summary = module._tool_argument_summary(
        {
            "name": "send_message",
            "arguments": json.dumps({"message": message, "target": "/root"}),
        }
    )

    assert summary == (
        '{"message":"01234567890123456789012345678901234567890123456789'
        '… [70 chars]","target":"/root"}'
    )
    assert message not in summary

    sensitive_summary = module._tool_argument_summary(
        {
            "name": "send_message",
            "arguments": json.dumps(
                {"message": "API_TOKEN=PRIVATE-SECRET " + message, "target": "/root"}
            ),
        }
    )
    assert "API_TOKEN=[redacted]" in sensitive_summary
    assert "PRIVATE-SECRET" not in sensitive_summary

    encrypted_message = "gAAAAA" + "A" * 754
    encrypted_summary = module._tool_argument_summary(
        {
            "name": "send_message",
            "arguments": json.dumps(
                {"message": encrypted_message, "target": "/root"}
            ),
        }
    )
    assert encrypted_summary == (
        '{"message":"[encrypted message, 760 chars]","target":"/root"}'
    )
    assert "gAAAAA" not in encrypted_summary


def test_default_tool_formatters_cover_common_run_patterns():
    module = _load_module()
    config = module._load_tool_formatter_config()

    patch = module._format_tool_argument(
        "exec",
        'const patch = "*** Begin Patch\\n*** Add File: '
        '/tmp/docs/frontend-password-reset.md\\n+# Frontend Password Reset Design',
        config,
    )
    claim = module._format_tool_argument(
        "exec",
        "python3 claim.py --repo . acquire --claim-id claim-123 --agent root",
        config,
    )
    message = module._format_tool_argument(
        "send_message",
        '{"message":"Review complete… [760 chars]","target":"/root"}',
        config,
    )
    wait = module._format_tool_argument(
        "wait_agent",
        '{"timeout_ms":30000}',
        config,
    )
    write = module._format_tool_argument(
        "write_files",
        '{"files":["docs/architecture.md","docs/wiki/index.md"],'
        '"operation":"Write 2 files"}',
        config,
    )

    assert patch.summary == "Patch · Add · frontend-password-reset.md"
    assert patch.rule_id == "apply-patch"
    assert claim.summary == "Claim · acquire · claim-123"
    assert message.summary == "Message → /root · Review complete… [760 chars]"
    assert wait.summary == "Wait for agent activity · 30000 ms"
    assert write.summary == (
        'Write 2 files · ["docs/architecture.md","docs/wiki/index.md"]'
    )
    assert write.rule_id == "write-files"


def test_native_codex_html_formats_tool_arguments_with_sanitized_raw_disclosure():
    module = _load_module()
    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)
    tool = run.threads[0].tool_intervals[0]
    tool.tool_name = "exec"
    tool.argument_summary = (
        'const patch = "*** Begin Patch\\n*** Add File: '
        '/tmp/docs/example.md\\n+# Example'
    )

    html = module.render_codex_rollout_html(run)

    assert '<div class="tool-argument-formatted">Patch · Add · example.md</div>' in html
    assert (
        ".tool-argument-formatted { font-weight:600; color:#243447; "
        "white-space:normal; overflow-wrap:anywhere; }"
    ) in html
    assert '<details class="tool-argument-raw"><summary>raw</summary>' in html
    assert "*** Add File: /tmp/docs/example.md" in html
    assert "<th>Result</th>" in html
    assert "raw result (redacted)" in html


def test_native_junie_session_reports_agents_usage_tools_and_redacted_results(tmp_path):
    module = _load_module()
    session = _write_junie_session(tmp_path)

    document = module.load_report_document(session)
    run = document.codex_run

    assert run is not None
    assert run.runtime == "Junie"
    assert run.state == "complete"
    assert run.format_version == module.JUNIE_SESSION_FORMAT
    assert run.parser_version == "1.2.0"
    assert len(run.threads) == 2
    assert sum(len(thread.turns) for thread in run.threads) == 2
    assert sum(len(thread.responses) for thread in run.threads) == 2
    assert sum(len(thread.tool_intervals) for thread in run.threads) == 3
    assert run.usage_totals.input_tokens == 28
    assert run.usage_totals.cached_input_tokens == 11
    assert run.usage_totals.uncached_input_tokens == 17
    assert run.usage_totals.output_tokens == 5
    assert run.usage_totals.processed_tokens == 33
    assert run.cost.status == "recorded"
    assert run.cost.total_cost == pytest.approx(0.03)

    custom = next(thread for thread in run.threads if thread.agent_path.endswith("/reviewer"))
    assert custom.model == "claude-reviewer"
    assert custom.token_totals.processed_tokens == 13
    assert custom.recorded_cost_usd == pytest.approx(0.02)
    assert custom.responses[0].recorded_cost_usd == pytest.approx(0.02)

    main = next(thread for thread in run.threads if thread.agent_path == "/main")
    terminal = main.tool_intervals[0]
    assert terminal.tool_name == "exec"
    assert "API_TOKEN=[redacted]" in terminal.argument_summary
    assert "API_TOKEN=[redacted]" in terminal.argument_content
    assert "PRIVATE" not in terminal.argument_summary
    assert "PRIVATE" not in terminal.argument_content
    assert "password=[redacted]" in terminal.result_content
    assert "PRIVATE" not in terminal.result_content
    write = main.tool_intervals[1]
    assert write.tool_name == "write_files"
    assert "docs/architecture/example.md" in write.argument_summary
    assert "docs/wiki/index.md" in write.argument_summary
    assert "ignored-example.md" not in write.argument_summary
    assert "cat > docs/architecture/example.md <<'DOC_EOF'" in write.argument_content
    assert "# Example" in write.argument_content
    assert "cat > ignored-example.md <<'NOT_A_COMMAND'" in write.argument_content

    html = module.render_html(document)
    assert "Junie run" in html
    assert "Recorded cost: $0.03 USD" in html
    assert "raw result (redacted)" in html
    assert "Agent path is reconstructed from Junie" in html
    assert '<div class="label">User tasks</div><div class="value">1</div>' in html
    assert '<div class="label">Agent task spans</div><div class="value">2</div>' in html
    assert '<div class="label">Model responses</div><div class="value">2</div>' in html
    assert "Turns / responses" not in html
    assert "<th>Task spans</th>" in html
    assert "task span task-1" in html
    assert "Write 2 files" in html
    assert "docs/architecture/example.md" in html
    assert "raw source command (redacted)" in html
    assert "cat &gt; docs/architecture/example.md &lt;&lt;'DOC_EOF'" in html
    assert "# Example" in html
    custom_overlay = html.split('id="turn-tool-call-list-2-1"', 1)[1].split(
        "</section>", 1
    )[0]
    custom_tool_table = custom_overlay.split('<div class="table-scroll">', 1)[1]
    assert (
        '<th>#</th><th>T+</th><th title="Cumulative model cost for this agent '
        'task span through the tool source event">Cost to T+</th><th>Tool</th>'
    ) in custom_tool_table
    assert '<td title="cumulative recorded model cost before tool call">$0.02 recorded</td>' in custom_tool_table
    assert "Open model pricing" not in html
    assert "PRIVATE" not in html


def test_native_junie_session_cli_generates_html_report(tmp_path):
    module = _load_module()
    session = _write_junie_session(tmp_path)
    output = tmp_path / "junie-report.html"
    json_output = tmp_path / "junie-report.json"
    turn_output = tmp_path / "junie-report.turns.csv"
    work_output = tmp_path / "junie-report.work-units.csv"
    markdown_output = tmp_path / "junie-report.md"

    rc = module.main(
        [
            str(session),
            "--output",
            str(output),
            "--json-output",
            str(json_output),
            "--turn-csv-output",
            str(turn_output),
            "--work-unit-csv-output",
            str(work_output),
            "--markdown-output",
            str(markdown_output),
        ]
    )

    assert rc == 0
    assert output.exists()
    assert "Junie run" in output.read_text(encoding="utf-8")
    assert json_output.exists()
    assert turn_output.exists()
    assert work_output.exists()
    assert markdown_output.exists()
    assert "Runtime: `Junie`" in markdown_output.read_text(encoding="utf-8")
    assert "## Model pricing" not in markdown_output.read_text(encoding="utf-8")


def test_tool_formatter_config_rejects_unsafe_regex():
    module = _load_module()

    with pytest.raises(ValueError, match="unsupported regex construct"):
        module._parse_tool_formatter_config(
            {
                "version": 1,
                "rules": [
                    {
                        "id": "unsafe",
                        "match": {"tool": "exec", "arguments_regex": "(?=secret)"},
                        "display": {"parts": ["Unsafe"]},
                    }
                ],
            }
        )


def test_native_codex_cli_accepts_custom_tool_formatter_config(tmp_path):
    module = _load_module()
    config_path = tmp_path / "custom-formatters.json"
    output_path = tmp_path / "report.html"
    config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "rules": [
                    {
                        "id": "custom-exec",
                        "match": {"tool": "exec"},
                        "display": {"parts": ["Custom exec summary"]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    rc = module.main(
        [
            str(CODEX_ROLLOUT_FIXTURES / "root.jsonl"),
            "--formatter-config",
            str(config_path),
            "--output",
            str(output_path),
        ]
    )

    assert rc == 0
    html = output_path.read_text(encoding="utf-8")
    assert "Custom exec summary" in html
    assert '<details class="tool-argument-raw"><summary>raw</summary>' in html


def test_discover_native_codex_run_aggregates_only_closed_descendant_set():
    module = _load_module()

    run = module.build_codex_rollout_run(
        "root-thread",
        CODEX_ROLLOUT_FIXTURES,
        observed_at=module._parse_iso_datetime("2026-07-14T00:00:20Z"),
    )

    assert [thread.thread_id for thread in run.threads] == [
        "root-thread",
        "child-thread",
        "nested-thread",
    ]
    assert run.usage_totals.processed_tokens == 800
    assert run.usage_totals.processed_tokens > run.threads[0].token_totals.processed_tokens
    assert "sibling-thread" not in {thread.thread_id for thread in run.threads}
    assert run.wall_time_ms == 18_000
    assert run.active_time_ms == 12_000
    assert run.agent_time_ms == 19_000
    assert run.peak_concurrency == 2
    child = next(thread for thread in run.threads if thread.thread_id == "child-thread")
    assert [turn.turn_id for turn in child.turns] == ["child-turn"]
    assert child.terminal_state == "complete"
    assert any("replayed session_meta ignored" in item for item in child.diagnostics)
    assert any("ignored replayed parent trigger" in item for item in child.diagnostics)
    phases = {(phase.phase_id, phase.lane_id): phase for phase in run.phase_lanes}
    assert phases[("module-design", "authoring")].usage.processed_tokens == 250
    assert phases[("module-design", "review")].usage.processed_tokens == 370
    assert phases[("module-design", "authoring")].active_time_ms == 7_000


def test_native_codex_work_units_prefer_explicit_ids_over_agent_path():
    module = _load_module()

    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)
    units = {unit.work_unit_id: unit for unit in run.work_units}

    assert "M-001" in units
    assert units["M-001"].phase_id == "module-design"
    assert units["M-001"].attribution_confidence == "exact"
    assert "module-a" not in units


def test_native_codex_numeric_epoch_turn_timestamps_drive_concurrency(tmp_path):
    module = _load_module()
    rollout = tmp_path / "numeric-timestamps.jsonl"
    rollout.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-07-14T07:29:14Z","type":"session_meta","payload":{"id":"numeric-thread","source":"user"}}',
                '{"timestamp":"2026-07-14T07:29:14Z","type":"event_msg","payload":{"type":"task_started","turn_id":"numeric-turn","started_at":1784004554}}',
                '{"timestamp":"2026-07-14T07:29:15Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":10,"cached_input_tokens":2,"output_tokens":3,"reasoning_output_tokens":1,"total_tokens":13}}}}',
                '{"timestamp":"2026-07-14T07:29:16Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"numeric-turn","completed_at":1784004556,"duration_ms":2000}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    run = module.build_codex_rollout_run("numeric-thread", tmp_path)

    assert run.active_time_ms == 2_000
    assert run.peak_concurrency == 1
    assert run.threads[0].turns[0].started_at == "2026-07-14T04:49:14+00:00"
    assert run.threads[0].turns[0].completed_at == "2026-07-14T04:49:16+00:00"


def test_native_codex_spawn_boundary_excludes_inherited_cumulative_usage(tmp_path):
    module = _load_module()
    rollout = tmp_path / "spawned.jsonl"
    rollout.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-07-14T08:00:00Z","type":"session_meta","payload":{"id":"spawned-thread","source":{"subagent":{"thread_spawn":{"parent_thread_id":"parent-thread","agent_path":"/root/project_bootstrapper/pass1_frontend_app","agent_nickname":"Tesla"}}}}}',
                '{"timestamp":"2026-07-14T08:00:00Z","type":"event_msg","payload":{"type":"task_started","turn_id":"parent-turn","started_at":1784006400}}',
                '{"timestamp":"2026-07-14T08:00:01Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":100,"cached_input_tokens":80,"output_tokens":20,"reasoning_output_tokens":5,"total_tokens":120}}}}',
                '{"timestamp":"2026-07-14T08:00:01Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"parent-turn","completed_at":1784006401,"duration_ms":1000}}',
                '{"timestamp":"2026-07-14T08:00:02Z","type":"event_msg","payload":{"type":"task_started","turn_id":"child-turn","started_at":1784006402}}',
                '{"timestamp":"2026-07-14T08:00:02Z","type":"inter_agent_communication_metadata","payload":{"trigger_turn":true}}',
                '{"timestamp":"2026-07-14T08:00:03Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":125,"cached_input_tokens":90,"output_tokens":25,"reasoning_output_tokens":7,"total_tokens":150}}}}',
                '{"timestamp":"2026-07-14T08:00:04Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"child-turn","completed_at":1784006404,"duration_ms":2000}}',
                '{"timestamp":"2026-07-14T08:00:05Z","type":"event_msg","payload":{"type":"task_started","turn_id":"child-turn-2","started_at":1784006405}}',
                '{"timestamp":"2026-07-14T08:00:05Z","type":"inter_agent_communication_metadata","payload":{"trigger_turn":true}}',
                '{"timestamp":"2026-07-14T08:00:06Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":140,"cached_input_tokens":100,"output_tokens":30,"reasoning_output_tokens":8,"total_tokens":170}}}}',
                '{"timestamp":"2026-07-14T08:00:07Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"child-turn-2","completed_at":1784006407,"duration_ms":2000}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    run = module.build_codex_rollout_run("spawned-thread", tmp_path)
    thread = run.threads[0]

    assert thread.token_totals.input_tokens == 40
    assert thread.token_totals.output_tokens == 10
    assert thread.token_totals.processed_tokens == 50
    assert thread.unattributed_usage.processed_tokens == 0
    assert [turn.turn_id for turn in thread.turns] == ["child-turn", "child-turn-2"]
    assert run.agent_time_ms == 4_000
    assert run.active_time_ms == 4_000
    assert {unit.work_unit_id for unit in run.work_units} == {"pass1_frontend_app"}
    assert sum(unit.usage.processed_tokens for unit in run.work_units) == 50
    assert any("excluded inherited cumulative token baseline" in item for item in thread.diagnostics)


def test_native_codex_unattributed_usage_reconciles_in_all_aggregates(tmp_path):
    module = _load_module()
    rollout = tmp_path / "unattributed.jsonl"
    rollout.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-07-14T09:00:00Z","type":"session_meta","payload":{"id":"unattributed-thread","source":"user"}}',
                '{"timestamp":"2026-07-14T09:00:00Z","type":"event_msg","payload":{"type":"task_started","turn_id":"one","started_at":"2026-07-14T09:00:00Z"}}',
                '{"timestamp":"2026-07-14T09:00:01Z","type":"event_msg","payload":{"type":"task_started","turn_id":"two","started_at":"2026-07-14T09:00:01Z"}}',
                '{"timestamp":"2026-07-14T09:00:02Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":20,"cached_input_tokens":5,"output_tokens":4,"reasoning_output_tokens":2,"total_tokens":24}}}}',
                '{"timestamp":"2026-07-14T09:00:03Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"one","completed_at":"2026-07-14T09:00:03Z","duration_ms":3000}}',
                '{"timestamp":"2026-07-14T09:00:04Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"two","completed_at":"2026-07-14T09:00:04Z","duration_ms":3000}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    run = module.build_codex_rollout_run("unattributed-thread", tmp_path)

    assert run.usage_totals.processed_tokens == 24
    assert run.threads[0].unattributed_usage.processed_tokens == 24
    assert sum(unit.usage.processed_tokens for unit in run.work_units) == 24
    assert sum(phase.usage.processed_tokens for phase in run.phase_lanes) == 24
    assert run.work_units[0].work_unit_id == "unattributed"


def test_native_codex_completed_root_reports_aborted_children_separately(tmp_path):
    module = _load_module()
    root = tmp_path / "root.jsonl"
    child = tmp_path / "child.jsonl"
    root.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-07-14T10:00:00Z","type":"session_meta","payload":{"id":"root","source":"user"}}',
                '{"timestamp":"2026-07-14T10:00:00Z","type":"event_msg","payload":{"type":"task_started","turn_id":"root-turn","started_at":"2026-07-14T10:00:00Z"}}',
                '{"timestamp":"2026-07-14T10:00:02Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"root-turn","completed_at":"2026-07-14T10:00:02Z","duration_ms":2000}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    child.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-07-14T10:00:00Z","type":"session_meta","payload":{"id":"child","source":{"subagent":{"thread_spawn":{"parent_thread_id":"root"}}}}}',
                '{"timestamp":"2026-07-14T10:00:00Z","type":"event_msg","payload":{"type":"task_started","turn_id":"child-turn","started_at":"2026-07-14T10:00:00Z"}}',
                '{"timestamp":"2026-07-14T10:00:01Z","type":"event_msg","payload":{"type":"turn_aborted","turn_id":"child-turn","completed_at":"2026-07-14T10:00:01Z","duration_ms":1000}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    run = module.build_codex_rollout_run("root", tmp_path)

    assert run.state == "complete-with-aborted-children"


def test_native_codex_outputs_are_privacy_safe_and_label_estimated_cost():
    module = _load_module()

    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)
    outputs = [
        module.codex_run_to_json(run),
        module.render_codex_rollout_markdown(run),
        module.render_codex_rollout_turn_csv(run),
        module.render_codex_rollout_work_unit_csv(run),
        module.render_codex_rollout_html(run),
    ]

    for output in outputs:
        assert "PRIVATE-PROMPT-CONTENT" not in output
        assert "PRIVATE-REASONING-CONTENT" not in output
        assert "PRIVATE-TOOL-PAYLOAD" not in output
        assert "PRIVATE-FINAL-CONTENT" not in output
    assert run.cost.status == "estimated"
    assert "API-equivalent estimate" in outputs[-1]
    assert "not an actual Codex charge" in outputs[-1]


def test_native_codex_html_reuses_methodology_style_execution_drilldown():
    module = _load_module()
    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)

    html = module.render_codex_rollout_html(run)

    assert "Token composition" in html
    assert "Execution timeline" in html
    assert "Turn activity" in html
    assert 'class="token-composition"' in html
    assert 'class="thread-detail"' in html
    assert "root-turn-1" in html
    assert "T+0s" in html
    assert "500ms" in html
    assert "exec × 1" in html
    assert "1 call · 500ms" in html
    assert "Cached input is part of input" in html
    assert "Reasoning is part of output" in html
    root_turn_table = html.split('<table class="turn-table"', 1)[1].split("</table>", 1)[0]
    assert "<th>Work unit</th>" in root_turn_table
    assert "<th>Activity</th>" in root_turn_table


def test_native_codex_report_uses_backend_neutral_title():
    module = _load_module()
    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)

    html = module.render_codex_rollout_html(run)
    markdown = module.render_codex_rollout_markdown(run)

    assert "<title>Agent Execution Metrics</title>" in html
    assert "<h1>Agent Execution Metrics</h1>" in html
    assert markdown.startswith("# Agent Execution Metrics\n")
    assert "Codex Rollout Metrics" not in html
    assert "Codex Rollout Metrics" not in markdown


def test_native_codex_html_links_to_privacy_safe_agent_and_turn_drilldowns():
    module = _load_module()
    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)

    html = module.render_codex_rollout_html(run)

    assert html.count('class="tool-call-overlay agent-tool-call-overlay"') == 3
    assert html.count('class="tool-call-overlay turn-detail-overlay"') == 4
    assert 'href="#turn-tool-call-list-1"' in html
    assert 'href="#turn-tool-call-list-2"' in html
    assert 'href="#turn-tool-call-list-3"' in html
    assert html.count('href="#turn-tool-call-list-1-1"') == 2
    assert "root — turns and tool calls" in html
    assert "module-a — turns and tool calls" in html
    assert "reviewer — turns and tool calls" in html
    assert "root — turn root-turn-1" in html
    assert "All turns and tool calls" not in html
    assert "<th>Agent</th>" not in html
    assert html.count('class="turn-tool-row"') == 4
    module_overlay = html.split('id="turn-tool-call-list-2"', 1)[1].split(
        "</section>", 1
    )[0]
    assert module_overlay.count('class="turn-tool-row"') == 1
    assert "child-turn" in module_overlay
    assert "root-turn-1" not in module_overlay
    root_turn_overlay = html.split('id="turn-tool-call-list-1-1"', 1)[1].split(
        "</section>", 1
    )[0]
    assert 'href="#execution-timeline">close</a>' in root_turn_overlay
    assert 'href="#turn-tool-call-list-1"' not in root_turn_overlay
    assert "Time to first token" in root_turn_overlay
    assert "Processed tokens" in root_turn_overlay
    assert "Arguments are compact, secret-redacted summaries" not in root_turn_overlay
    assert '<p class="execution-note">' not in root_turn_overlay
    tool_table = root_turn_overlay.split('<div class="table-scroll">', 1)[1].split(
        "</table>", 1
    )[0]
    assert '<table class="turn-detail-table has-timing">' in tool_table
    assert '<col class="turn-detail-arguments-column">' in tool_table
    assert '<col class="turn-detail-cost-column">' in tool_table
    assert '<col class="turn-detail-result-column">' in tool_table
    assert '<col class="turn-detail-timing-column">' in tool_table
    assert "<th>T+</th>" in tool_table
    assert "Cost to T+" in tool_table
    assert "<th>Duration</th>" not in tool_table
    assert "<th>Arguments</th>" in tool_table
    assert "<th>Result</th>" in tool_table
    assert "<th>Confidence</th>" not in tool_table
    assert "<th>Timing note</th>" in tool_table
    assert '<tr class="turn-detail-tool-row"><td>1</td><td>T+3s</td>' in tool_table
    assert "API_TOKEN=[redacted] python app.py</code></td>" in tool_table
    assert "[20 chars]" in tool_table
    assert "tool-reported duration available</td></tr>" in tool_table
    assert '<code>root-turn-1</code>' in html
    assert "PRIVATE-TOOL-PAYLOAD" not in html

    run.threads[0].tool_intervals[0].attribution_confidence = "bounded"
    bounded_html = module.render_codex_rollout_html(run)
    bounded_overlay = bounded_html.split(
        'id="turn-tool-call-list-1-1"', 1
    )[1].split("</section>", 1)[0]
    bounded_tool_table = bounded_overlay.split(
        '<div class="table-scroll">', 1
    )[1].split("</table>", 1)[0]
    assert '<table class="turn-detail-table">' in bounded_tool_table
    assert "has-timing" not in bounded_tool_table
    assert "turn-detail-timing-column" not in bounded_tool_table
    assert "<th>Timing note</th>" not in bounded_tool_table
    assert "bounded" not in bounded_tool_table


def test_native_codex_turn_table_hides_constant_work_unit_and_empty_activity(tmp_path):
    module = _load_module()
    rollout = tmp_path / "constant-metadata.jsonl"
    rollout.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-07-14T12:00:00Z","type":"session_meta","payload":{"id":"reviewer-thread","source":{"subagent":{"thread_spawn":{"parent_thread_id":"outside","agent_path":"/root/reviewer","agent_nickname":"Review"}}}}}',
                '{"timestamp":"2026-07-14T12:00:00Z","type":"event_msg","payload":{"type":"task_started","turn_id":"one","started_at":"2026-07-14T12:00:00Z"}}',
                '{"timestamp":"2026-07-14T12:00:01Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":10,"cached_input_tokens":2,"output_tokens":2,"reasoning_output_tokens":1,"total_tokens":12}}}}',
                '{"timestamp":"2026-07-14T12:00:02Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"one","completed_at":"2026-07-14T12:00:02Z","duration_ms":2000}}',
                '{"timestamp":"2026-07-14T12:00:03Z","type":"event_msg","payload":{"type":"task_started","turn_id":"two","started_at":"2026-07-14T12:00:03Z"}}',
                '{"timestamp":"2026-07-14T12:00:04Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":20,"cached_input_tokens":4,"output_tokens":4,"reasoning_output_tokens":2,"total_tokens":24}}}}',
                '{"timestamp":"2026-07-14T12:00:05Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"two","completed_at":"2026-07-14T12:00:05Z","duration_ms":2000}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    run = module.build_codex_rollout_run("reviewer-thread", tmp_path)

    html = module.render_codex_rollout_html(run)
    turn_table = html.split('<table class="turn-table"', 1)[1].split("</table>", 1)[0]

    assert "<th>Work unit</th>" not in turn_table
    assert "<th>Activity</th>" not in turn_table
    assert "Work unit reviewer for all turns" in html
    assert "Activity not recorded" in html


def test_native_codex_html_identifies_agents_and_runtime_nicknames():
    module = _load_module()
    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)

    html = module.render_codex_rollout_html(run)

    assert "Agents used" in html
    assert "Assignment" in html
    assert "<th>Runtime nickname</th>" not in html
    assert "<strong>module-a (module-a)</strong>" in html
    assert "<strong>reviewer (reviewer)</strong>" in html
    assert "Agent path is the recorded assignment hierarchy" in html
    assert "Runtime nicknames appear in parentheses" in html


def test_native_codex_markdown_includes_turn_and_tool_breakdown():
    module = _load_module()
    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)

    markdown = module.render_codex_rollout_markdown(run)

    assert "- Turns: 4" in markdown
    assert "- Matched tool calls: 1" in markdown
    assert "| Assignment | Parent assignment | State | Turns | Tools | Agent time |" in markdown
    assert "| module-a (module-a) | root | complete |" in markdown
    assert "| Work unit | Turns | Agent time | Tools | Input | Cached | Fresh | Output | Reasoning | Processed |" in markdown
    assert "PRIVATE-TOOL-PAYLOAD" not in markdown


def test_native_codex_live_parser_tolerates_partial_final_line(tmp_path):
    module = _load_module()
    source = CODEX_ROLLOUT_FIXTURES / "active-partial.jsonl"
    target = tmp_path / source.name
    target.write_bytes(source.read_bytes())

    first = module.build_codex_rollout_run("active-thread", tmp_path)

    assert first.state == "live"
    assert first.threads[0].terminal_state == "active"
    assert first.threads[0].token_totals.processed_tokens == 12
    assert any("incomplete final JSONL line" in item for item in first.diagnostics)

    with target.open("a", encoding="utf-8") as stream:
        stream.write(
            '\n{"timestamp":"2026-07-14T01:00:03Z","type":"event_msg",'
            '"payload":{"type":"task_complete","turn_id":"active-turn",'
            '"completed_at":"2026-07-14T01:00:03Z","duration_ms":3000,'
            '"time_to_first_token_ms":250,"last_agent_message":"PRIVATE-FINAL-CONTENT"}}\n'
        )

    second = module.build_codex_rollout_run("active-thread", tmp_path)
    assert second.state == "complete"
    assert second.threads[0].terminal_state == "complete"
    assert second.usage_totals.processed_tokens == 12


def test_sealed_native_codex_run_reproduces_from_source_manifest(tmp_path):
    module = _load_module()
    sealed = module.build_codex_rollout_run(
        "root-thread",
        CODEX_ROLLOUT_FIXTURES,
        seal=True,
        observed_at=module._parse_iso_datetime("2026-07-14T00:00:20Z"),
    )
    manifest_path = tmp_path / "sealed.json"
    manifest_path.write_text(module.codex_run_to_json(sealed), encoding="utf-8")

    reproduced = module.reprocess_sealed_codex_run(manifest_path)

    assert reproduced.state == "sealed"
    assert module.codex_run_to_json(reproduced) == module.codex_run_to_json(sealed)
    assert all(source.sha256 for source in reproduced.source_manifest)
    assert reproduced.pricing_digest


def test_native_codex_unsupported_subscription_model_has_no_monetary_estimate(tmp_path):
    module = _load_module()
    rollout = tmp_path / "unsupported.jsonl"
    rollout.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-07-14T02:00:00Z","type":"session_meta","payload":{"id":"unsupported-thread","source":"user"}}',
                '{"timestamp":"2026-07-14T02:00:00Z","type":"turn_context","payload":{"model":"internal-subscription-model","turn_id":"u1"}}',
                '{"timestamp":"2026-07-14T02:00:00Z","type":"event_msg","payload":{"type":"task_started","turn_id":"u1","started_at":"2026-07-14T02:00:00Z"}}',
                '{"timestamp":"2026-07-14T02:00:01Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":10,"cached_input_tokens":2,"output_tokens":3,"reasoning_output_tokens":1,"total_tokens":13}},"rate_limits":{"plan_type":"pro","credits":null}}}',
                '{"timestamp":"2026-07-14T02:00:02Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"u1","completed_at":"2026-07-14T02:00:02Z","duration_ms":2000,"time_to_first_token_ms":100}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    run = module.build_codex_rollout_run("unsupported-thread", tmp_path)

    assert run.cost.status == "subscription-no-charge-data"
    assert run.cost.total_cost is None


def test_pricing_registry_contains_current_codex_and_claude_rates():
    module = _load_module()
    pricing = json.loads(module.PRICING_FILE.read_text(encoding="utf-8"))
    models = pricing["models"]

    assert pricing["_updated_at"] == "2026-07-14"
    assert models["gpt-5.6-sol"]["input_per_million"] == 5.0
    assert models["gpt-5.6-sol"]["cached_input_per_million"] == 0.5
    assert models["gpt-5.6-sol"]["output_per_million"] == 30.0
    assert models["gpt-5.6-sol"]["codex_credits_input_per_million"] == 125.0
    assert models["gpt-5.6-terra"]["codex_credits_output_per_million"] == 375.0
    assert models["gpt-5.6-luna"]["codex_credits_cached_input_per_million"] == 2.5
    assert models["claude-opus-4-8"]["output_per_million"] == 25.0
    assert models["claude-sonnet-5"]["input_per_million"] == 2.0
    assert models["claude-haiku-4-5"]["cached_input_per_million"] == 0.1


def test_native_codex_cost_uses_api_usd_without_credit_estimates():
    module = _load_module()
    usage = module.UsageTotals(
        input_tokens=2_000_000,
        cached_input_tokens=1_000_000,
        uncached_input_tokens=1_000_000,
        output_tokens=1_000_000,
        processed_tokens=3_000_000,
    )

    cost = module._cost_for_usage(
        usage,
        {"gpt-5.6-sol": usage},
        plan_types={"pro"},
    )

    assert cost.status == "estimated"
    assert cost.total_cost == 35.5
    assert not hasattr(cost, "estimated_credits")
    assert cost.method == "API-equivalent token-price estimate; not an actual Codex charge"


def test_native_codex_cost_display_is_compact_and_rounded():
    module = _load_module()
    cost = module.CostAssessment(
        status="estimated",
        total_cost=1.330343,
    )

    assert module._cost_summary(cost) == (
        "API-equivalent estimate: $1.33 USD "
        "(estimate, not an actual Codex charge or invoice)"
    )
    assert module._compact_cost_summary(cost) == "$1.33"

    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)
    html = module.render_codex_rollout_html(run)
    assert html.count("not an actual Codex charge or invoice") == 1
    assert "<th>Cost estimate</th>" in html
    assert "Codex rate-card estimate" not in html
    assert "credits" not in html.lower()
    markdown = module.render_codex_rollout_markdown(run)
    assert "credits" not in markdown.lower()


def test_native_codex_execution_timeline_uses_agent_model_for_turn_and_agent_costs():
    module = _load_module()
    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)
    root = run.threads[0]
    root.model = "gpt-5.6-sol"
    root.plan_type = "pro"
    root.turns[0].usage = module.UsageTotals(
        input_tokens=2_000_000,
        cached_input_tokens=1_000_000,
        uncached_input_tokens=1_000_000,
        output_tokens=1_000_000,
        processed_tokens=3_000_000,
    )
    root.turns[1].usage = module.UsageTotals(
        input_tokens=1_000_000,
        uncached_input_tokens=1_000_000,
        processed_tokens=1_000_000,
    )
    root.token_totals = root.turns[0].usage + root.turns[1].usage

    html = module.render_codex_rollout_html(run)

    root_detail = html.split('<details class="thread-detail">', 1)[1].split(
        "</details>", 1
    )[0]
    assert 'title="Agent cost estimate">cost $40.50' in root_detail
    assert "<th>Cost estimate</th>" in root_detail
    assert "$35.50" in root_detail
    assert "$5.00" in root_detail
    root_turn_overlay = html.split('id="turn-tool-call-list-1-1"', 1)[1].split(
        "</section>", 1
    )[0]
    assert "Model" in root_turn_overlay
    assert "gpt-5.6-sol" in root_turn_overlay
    assert "Cost estimate" in root_turn_overlay
    assert "$35.50" in root_turn_overlay


def test_native_codex_html_opens_model_pricing_in_new_tab():
    module = _load_module()
    run = module.build_codex_rollout_run(
        "root-thread",
        CODEX_ROLLOUT_FIXTURES,
        observed_at=module._parse_iso_datetime("2026-07-14T00:00:20Z"),
    )

    html = module.render_codex_rollout_html(run)

    normal_flow_before_agents = html.split("<body>", 1)[1].split("<h2>Agents used</h2>", 1)[0]
    assert "<h2>Model pricing</h2>" not in normal_flow_before_agents
    assert 'href="#model-pricing" target="_blank" rel="noopener"' in html
    assert "Open model pricing" in html
    assert 'id="model-pricing" class="model-pricing-overlay"' in html
    assert '<h2 id="model-pricing-title">Model pricing</h2>' in html
    assert "API USD / 1M tokens" in html
    assert "Codex credits / 1M tokens" not in html
    assert "GPT-5.6 Sol" in html
    assert "Claude Sonnet 5" in html
    assert "Long-context and fast-mode multipliers are not inferred" in html


def test_main_writes_native_codex_machine_outputs_and_sealed_manifest(tmp_path):
    module = _load_module()
    html_path = tmp_path / "report.html"

    rc = module.main(
        [
            "--codex-thread",
            "root-thread",
            "--sessions-root",
            str(CODEX_ROLLOUT_FIXTURES),
            "--seal",
            "--output",
            str(html_path),
        ]
    )

    assert rc == 0
    assert html_path.exists()
    assert html_path.with_suffix(".json").exists()
    assert html_path.with_suffix(".turns.csv").exists()
    assert html_path.with_suffix(".work-units.csv").exists()
    assert html_path.with_suffix(".md").exists()
    assert "API-equivalent estimate" in html_path.read_text(encoding="utf-8")


def test_native_codex_interrupted_resumed_and_stale_turns_remain_bounded(tmp_path):
    module = _load_module()
    rollout = tmp_path / "interrupted.jsonl"
    rollout.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-07-14T03:00:00Z","type":"session_meta","payload":{"id":"interrupted-thread","source":"user"}}',
                '{"timestamp":"2026-07-14T03:00:00Z","type":"turn_context","payload":{"model":"gpt-5.4-mini","turn_id":"t1"}}',
                '{"timestamp":"2026-07-14T03:00:00Z","type":"event_msg","payload":{"type":"task_started","turn_id":"t1","started_at":"2026-07-14T03:00:00Z"}}',
                '{"timestamp":"2026-07-14T03:00:01Z","type":"event_msg","payload":{"type":"task_started","turn_id":"t2","started_at":"2026-07-14T03:00:01Z","work_unit_id":"RECOVERY","activity":"correct"}}',
                '{"timestamp":"2026-07-14T03:00:02Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":20,"cached_input_tokens":5,"output_tokens":4,"reasoning_output_tokens":2,"total_tokens":24}}}}',
                '{"timestamp":"2026-07-14T03:00:03Z","type":"event_msg","payload":{"type":"turn_aborted","turn_id":"t1","completed_at":"2026-07-14T03:00:03Z","duration_ms":3000,"reason":"interrupted"}}',
                '{"timestamp":"2026-07-14T03:00:04Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"t2","completed_at":"2026-07-14T03:00:04Z","duration_ms":3000,"time_to_first_token_ms":200}}',
                '{"timestamp":"2026-07-14T03:00:05Z","type":"event_msg","payload":{"type":"task_started","turn_id":"stale","started_at":"2026-07-14T03:00:05Z"}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    run = module.build_codex_rollout_run("interrupted-thread", tmp_path)

    assert run.state == "live"
    assert run.usage_totals.processed_tokens == 24
    assert run.threads[0].responses[0].turn_id is None
    assert [turn.outcome for turn in run.threads[0].turns] == ["aborted", "complete", "active"]
    assert run.threads[0].unattributed_usage.processed_tokens == 24


def test_native_codex_hierarchy_rejects_cycles(tmp_path):
    module = _load_module()
    for thread_id, parent_id in (("cycle-a", "cycle-b"), ("cycle-b", "cycle-a")):
        (tmp_path / f"{thread_id}.jsonl").write_text(
            json.dumps(
                {
                    "timestamp": "2026-07-14T04:00:00Z",
                    "type": "session_meta",
                    "payload": {
                        "id": thread_id,
                        "source": {
                            "subagent": {
                                "thread_spawn": {"parent_thread_id": parent_id}
                            }
                        },
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

    try:
        module.build_codex_rollout_run("cycle-a", tmp_path)
    except ValueError as exc:
        assert "Cycle detected" in str(exc)
    else:
        raise AssertionError("expected cycle rejection")


def test_native_codex_prefers_complete_direct_cost_telemetry(tmp_path):
    module = _load_module()
    rollout = tmp_path / "recorded.jsonl"
    rollout.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-07-14T05:00:00Z","type":"session_meta","payload":{"id":"recorded-thread","source":"user"}}',
                '{"timestamp":"2026-07-14T05:00:00Z","type":"turn_context","payload":{"model":"internal-model","turn_id":"r1"}}',
                '{"timestamp":"2026-07-14T05:00:00Z","type":"event_msg","payload":{"type":"task_started","turn_id":"r1","started_at":"2026-07-14T05:00:00Z"}}',
                '{"timestamp":"2026-07-14T05:00:01Z","type":"event_msg","payload":{"type":"token_count","info":{"total_cost_usd":0.125,"total_token_usage":{"input_tokens":10,"cached_input_tokens":2,"output_tokens":3,"reasoning_output_tokens":1,"total_tokens":13}}}}',
                '{"timestamp":"2026-07-14T05:00:02Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"r1","completed_at":"2026-07-14T05:00:02Z","duration_ms":2000,"time_to_first_token_ms":100}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    run = module.build_codex_rollout_run("recorded-thread", tmp_path)

    assert run.cost.status == "recorded"
    assert run.cost.total_cost == 0.125
    assert "Recorded cost" in module.render_codex_rollout_html(run)


def test_detect_log_backend_codex():
    module = _load_module()
    path = Path(__file__).resolve().parent / "fixtures" / "codex-json-generator.stdout.jsonl"
    assert module.detect_log_backend(path) == "codex"


def test_parse_codex_log_extracts_usage_and_activity():
    module = _load_module()
    path = Path(__file__).resolve().parent / "fixtures" / "codex-json-generator.stdout.jsonl"
    detail = module.parse_log(path)
    assert detail.backend == "codex"
    assert detail.input_tokens == 78640
    assert detail.cache_read_tokens == 75520
    assert detail.output_tokens == 716
    assert detail.subagent_count == 1
    assert len(detail.turns) >= 2
    assert detail.num_turns == len(detail.turns)
    tool_names = [tc.name for turn in detail.turns for tc in turn.tool_calls]
    assert any(turn.text_chars > 0 for turn in detail.turns)
    assert "Bash" in tool_names
    assert "spawn_agent" in tool_names
    assert "wait" in tool_names
    assert "FileChange" in tool_names


def test_render_codex_log_structured_shows_usage():
    module = _load_module()
    path = Path(__file__).resolve().parent / "fixtures" / "codex-json-generator.stdout.jsonl"
    detail = module.parse_log(path)
    html = module._render_log_structured(path, "popup-1", prompt_text="do the thing", detail=detail, step_duration_seconds=15)
    assert "THREAD" in html
    assert "Turn 1" in html
    assert "T+0000s" in html
    assert "CMD" in html
    assert "AGT" in html
    assert "DONE" in html
    assert "cached=75,520" in html


def test_render_codex_log_structured_treats_prompt_as_part_of_turn_one(tmp_path):
    module = _load_module()
    log_path = tmp_path / "codex.stdout.log"
    log_path.write_text(
        "\n".join(
            [
                '{"type":"thread.started","thread_id":"abc"}',
                '{"type":"turn.started"}',
                '{"type":"item.completed","item":{"id":"m1","type":"agent_message","text":"first"}}',
                '{"type":"item.completed","item":{"id":"c1","type":"command_execution","command":"pwd","aggregated_output":"/tmp\\n","exit_code":0,"status":"completed"}}',
                '{"type":"item.completed","item":{"id":"m2","type":"agent_message","text":"second"}}',
                '{"type":"turn.completed","usage":{"input_tokens":10,"cached_input_tokens":0,"output_tokens":4}}',
            ]
        ) + "\n",
        encoding="utf-8",
    )
    detail = module.parse_log(log_path)
    html = module._render_log_structured(log_path, "popup-2", prompt_text="do the thing", detail=detail, step_duration_seconds=5)
    assert "── Turn 1 — T+0000s ──" in html
    assert "PROMPT" in html
    assert "── Turn 2" in html


def test_render_detail_for_codex_uses_fresh_input_and_backend_label():
    module = _load_module()
    path = Path(__file__).resolve().parent / "fixtures" / "codex-json-generator.stdout.jsonl"
    detail = module.parse_log(path)
    html = module._render_detail(detail, step_id="step-1", popups=[])
    assert "CODEX" in html
    assert "fresh-input: 3,120" in html


def test_parse_log_estimates_codex_cost_from_pricing_table():
    module = _load_module()
    path = Path(__file__).resolve().parent / "fixtures" / "codex-json-generator.stdout.jsonl"
    detail = module.parse_log(path)
    detail.model = "gpt-5.4-mini"
    detail = module._finalize_detail(detail)
    assert detail.cost_estimated is True
    assert detail.cost_usd > 0


def test_parse_log_estimates_zero_cost_for_spark_token_bucket(tmp_path):
    module = _load_module()
    pricing = json.loads(module.PRICING_FILE.read_text(encoding="utf-8"))
    assert pricing["models"][SPARK_PRICING_MODEL]["input_per_million"] == SPARK_ZERO_RATE_PER_MILLION
    assert pricing["models"][SPARK_PRICING_MODEL]["cached_input_per_million"] == SPARK_ZERO_RATE_PER_MILLION
    assert pricing["models"][SPARK_PRICING_MODEL]["output_per_million"] == SPARK_ZERO_RATE_PER_MILLION

    log_path = tmp_path / "spark.stdout.log"
    log_path.write_text(
        "\n".join(
            [
                '{"type":"thread.started","thread_id":"abc"}',
                (
                    '{"type":"turn.completed","usage":{'
                    f'"input_tokens":{SPARK_LOG_INPUT_TOKENS},'
                    f'"cached_input_tokens":{SPARK_LOG_CACHED_INPUT_TOKENS},'
                    f'"output_tokens":{SPARK_LOG_OUTPUT_TOKENS}'
                    "}}"
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    log_path.with_suffix(".meta.json").write_text(
        json.dumps({"model": SPARK_PRICING_MODEL}),
        encoding="utf-8",
    )

    detail = module.parse_log(log_path)

    assert detail.model == SPARK_PRICING_MODEL
    assert detail.cost_estimated is True
    assert detail.cost_usd == ZERO_COST_USD


def test_parse_log_uses_metadata_sidecar_for_model(tmp_path):
    module = _load_module()
    log_path = tmp_path / "selector.stdout.log"
    log_path.write_text(
        '\n'.join(
            [
                '{"type":"thread.started","thread_id":"abc"}',
                '{"type":"item.completed","item":{"id":"m1","type":"agent_message","text":"selector_model: \\"gpt-5.4-mini\\""}}',
                '{"type":"turn.completed","usage":{"input_tokens":1000,"cached_input_tokens":500,"output_tokens":200}}',
            ]
        ) + "\n",
        encoding="utf-8",
    )
    log_path.with_suffix(".meta.json").write_text(
        json.dumps({"model": "gpt-5.4-mini", "role": "skill-selector"}),
        encoding="utf-8",
    )

    detail = module.parse_log(log_path)

    assert detail.model == "gpt-5.4-mini"
    assert detail.cost_estimated is True
    assert detail.cost_usd > 0


def test_render_log_structured_falls_back_for_plaintext(tmp_path):
    module = _load_module()
    log_path = tmp_path / "selector.stdout.log"
    log_path.write_text('phase_id: "PH-000"\nselector_model: "gpt-5"\n', encoding="utf-8")
    html = module._render_log_structured(log_path, "popup-plain")
    assert "phase_id" in html
    assert "selector_model" in html
    assert "log-unknown" not in html


def test_parse_prompt_runner_run_backfills_prompt_from_manifest_source(tmp_path):
    module = _load_module()
    run_dir = tmp_path / "run"
    prompt_dir = run_dir / "logs" / "prompt-01-generator-only"
    prompt_dir.mkdir(parents=True)

    fixture_log = Path(__file__).resolve().parent / "fixtures" / "codex-json-generator.stdout.jsonl"
    stdout_log = prompt_dir / "iter-01-generator.stdout.log"
    stderr_log = prompt_dir / "iter-01-generator.stderr.log"
    stdout_log.write_text(fixture_log.read_text(encoding="utf-8"), encoding="utf-8")
    stderr_log.write_text("", encoding="utf-8")

    source_file = tmp_path / "source.md"
    source_file.write_text(
        """## Prompt 1: Generator only

```
Write docs/output.txt with RESULT: success.
```

```
VERDICT: pass
```
""",
        encoding="utf-8",
    )
    (run_dir / "manifest.json").write_text(
        json.dumps({"source_file": str(source_file)}),
        encoding="utf-8",
    )

    shared_steps, fork_sections = module.parse_prompt_runner_run(run_dir)
    assert not fork_sections
    assert len(shared_steps) == 1
    assert "RESULT: success" in shared_steps[0].detail.prompt_text


def test_parse_prompt_runner_run_uses_manifest_start_for_sequential_step_timing(tmp_path):
    module = _load_module()
    run_dir = tmp_path / "run"
    prompt1 = run_dir / "logs" / "prompt-01-first"
    prompt2 = run_dir / "logs" / "prompt-02-second"
    prompt1.mkdir(parents=True)
    prompt2.mkdir(parents=True)

    fixture_log = Path(__file__).resolve().parent / "fixtures" / "codex-json-generator.stdout.jsonl"
    gen1 = prompt1 / "iter-01-generator.stdout.log"
    err1 = prompt1 / "iter-01-generator.stderr.log"
    gen2 = prompt2 / "iter-01-generator.stdout.log"
    err2 = prompt2 / "iter-01-generator.stderr.log"
    gen1.write_text(fixture_log.read_text(encoding="utf-8"), encoding="utf-8")
    err1.write_text("", encoding="utf-8")
    gen2.write_text(fixture_log.read_text(encoding="utf-8"), encoding="utf-8")
    err2.write_text("", encoding="utf-8")

    source_file = tmp_path / "source.md"
    source_file.write_text(
        """## Prompt 1: First

```
Write docs/one.txt.
```

```
VERDICT: pass
```

## Prompt 2: Second

```
Write docs/two.txt.
```

```
VERDICT: pass
```
""",
        encoding="utf-8",
    )
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "source_file": str(source_file),
                "started_at": "2026-04-12T02:10:11Z",
            }
        ),
        encoding="utf-8",
    )

    first_end = 1775959989
    second_end = 1775960248
    gen1.touch()
    err1.touch()
    gen2.touch()
    err2.touch()
    import os
    os.utime(gen1, (first_end, first_end))
    os.utime(err1, (first_end, first_end))
    os.utime(gen2, (second_end, second_end))
    os.utime(err2, (second_end, second_end))

    shared_steps, _ = module.parse_prompt_runner_run(run_dir)

    assert len(shared_steps) == 2
    assert shared_steps[0].started.isoformat() == "2026-04-12T02:10:11+00:00"
    assert shared_steps[0].ended.isoformat() == "2026-04-12T02:13:09+00:00"
    assert shared_steps[1].started == shared_steps[0].ended
    assert shared_steps[1].ended.isoformat() == "2026-04-12T02:17:28+00:00"


def _write_codex_run(run_dir: Path, source_file: Path, step_name: str, prompt_text: str, output_text: str):
    prompt_dir = run_dir / "logs" / step_name
    prompt_dir.mkdir(parents=True)
    log = prompt_dir / "iter-01-generator.stdout.log"
    stderr = prompt_dir / "iter-01-generator.stderr.log"
    log.write_text(
        "\n".join(
            [
                '{"type":"thread.started","thread_id":"abc"}',
                '{"type":"turn.started"}',
                f'{{"type":"item.completed","item":{{"id":"item_0","type":"agent_message","text":{json.dumps(output_text)} }}}}',
                '{"type":"turn.completed","usage":{"input_tokens":100,"cached_input_tokens":40,"output_tokens":20}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    stderr.write_text("", encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps({"source_file": str(source_file)}),
        encoding="utf-8",
    )


def _write_current_module_run(module_dir: Path, prompt_slug: str = "prompt-01-demo-step") -> None:
    fixture_log = Path(__file__).resolve().parent / "fixtures" / "codex-json-generator.stdout.jsonl"
    module_dir.mkdir(parents=True, exist_ok=True)
    (module_dir / "module.log").write_text("", encoding="utf-8")
    prompt_id = "-".join(prompt_slug.split("-")[:2])

    (module_dir / f"{prompt_slug}.final-verdict.txt").write_text("VERDICT: pass\n", encoding="utf-8")
    (module_dir / f"{prompt_slug}.files-created.txt").write_text("docs/out.txt\n", encoding="utf-8")
    (module_dir / f"{prompt_id}.iter-01-generator.stdout.log").write_text(
        fixture_log.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (module_dir / f"{prompt_id}.iter-01-generator.stderr.log").write_text("", encoding="utf-8")
    (module_dir / f"{prompt_id}.iter-01-deterministic-validation.stdout.log").write_text(
        json.dumps({"validator": "demo", "overall_status": "pass"}) + "\n",
        encoding="utf-8",
    )
    (module_dir / f"{prompt_id}.iter-01-deterministic-validation.stderr.log").write_text("", encoding="utf-8")
    (module_dir / f"{prompt_id}.iter-01-deterministic-validation.proc.json").write_text(
        json.dumps({"exit_code": 0}),
        encoding="utf-8",
    )
    (module_dir / f"{prompt_id}.iter-01-judge.stdout.log").write_text(
        fixture_log.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (module_dir / f"{prompt_id}.iter-01-judge.stderr.log").write_text("", encoding="utf-8")

    history_dir = module_dir / "history" / prompt_id
    history_dir.mkdir(parents=True, exist_ok=True)
    (history_dir / "iter-01-prompt.md").write_text("Generator prompt body", encoding="utf-8")
    (history_dir / "iter-01-validation-prompt.md").write_text("Judge prompt body", encoding="utf-8")


def _write_selection_module_run(module_dir: Path) -> None:
    fixture_log = Path(__file__).resolve().parent / "fixtures" / "codex-json-generator.stdout.jsonl"
    module_dir.mkdir(parents=True, exist_ok=True)
    (module_dir / "module.log").write_text("", encoding="utf-8")

    selector_log = module_dir / "prompt-01.iter-01-judge.stdout.log"
    selector_log.write_text(
        "\n".join(
            [
                '{"type":"thread.started","thread_id":"selector"}',
                '{"type":"turn.started"}',
                '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"VERDICT: select\\nSELECTED_VARIANT: B\\nRATIONALE: Variant B is cleaner."}}',
                '{"type":"turn.completed","usage":{"input_tokens":1000,"cached_input_tokens":200,"output_tokens":55}}',
            ]
        ) + "\n",
        encoding="utf-8",
    )
    selector_log.with_name("prompt-01.iter-01-judge.stderr.log").write_text("", encoding="utf-8")
    (module_dir / "history" / "prompt-01").mkdir(parents=True, exist_ok=True)
    (module_dir / "history" / "prompt-01" / "iter-01-validation-prompt.md").write_text(
        "Select the best variant.",
        encoding="utf-8",
    )
    (module_dir / "prompt-01.selected-variant.txt").write_text("B\n", encoding="utf-8")
    (module_dir / "prompt-01.selector-decision.md").write_text(
        "VERDICT: select\n"
        "SELECTED_VARIANT: B\n"
        "RATIONALE: Variant B is cleaner.\n",
        encoding="utf-8",
    )

    selection_dir = module_dir / "prompt-01.selection"
    selection_dir.mkdir(parents=True, exist_ok=True)
    (selection_dir / "selection-summary.md").write_text(
        "Selected variant: B\nRationale: Variant B is cleaner.\n",
        encoding="utf-8",
    )

    for variant_name, variant_title in (("A", "Bold layout"), ("B", "Quiet layout")):
        variant_root = selection_dir / "variants" / variant_name.lower()
        variant_root.mkdir(parents=True, exist_ok=True)
        (variant_root / "result.json").write_text(
            json.dumps(
                {
                    "variant_name": variant_name,
                    "variant_title": variant_title,
                }
            ),
            encoding="utf-8",
        )
        child_run_files = variant_root / "workspace" / ".run-files"
        child_module = child_run_files / "choose-ui"
        _write_current_module_run(
            child_module,
            prompt_slug=f"prompt-01-{variant_title.lower().replace(' ', '-')}",
        )

    _write_current_module_run(
        module_dir,
        prompt_slug="prompt-02-record-selected-design",
    )


def test_parse_comparison_manifest_collapses_shared_prefix(tmp_path):
    module = _load_module()
    source_file_a = tmp_path / "source-a.md"
    source_file_b = tmp_path / "source-b.md"
    source_file_a.write_text(
        """## Prompt 1: Setup

```
Shared setup prompt.
```

```
VERDICT: pass
```

## Prompt 2: Variant work

```
Variant-specific prompt.
```

```
VERDICT: pass
```
""",
        encoding="utf-8",
    )
    source_file_b.write_text(
        """## Prompt 1: Setup

```
Shared setup prompt.
```

```
VERDICT: pass
```

## Prompt 2: Variant work

```
Different variant-specific prompt.
```

```
VERDICT: pass
```
""",
        encoding="utf-8",
    )
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_codex_run(run_a, source_file_a, "prompt-01-setup", "Shared setup prompt.", "setup ok")
    _write_codex_run(run_a, source_file_a, "prompt-02-variant-work", "Variant-specific prompt.", "run a result")
    _write_codex_run(run_b, source_file_b, "prompt-01-setup", "Shared setup prompt.", "setup ok")
    _write_codex_run(run_b, source_file_b, "prompt-02-variant-work", "Different variant-specific prompt.", "run b result")

    manifest = tmp_path / "compare.json"
    manifest.write_text(
        json.dumps(
            {
                "title": "My Compare",
                "mode": "comparison",
                "runs": [
                    {"label": "A", "path": str(run_a)},
                    {"label": "B", "path": str(run_b)},
                ],
            }
        ),
        encoding="utf-8",
    )

    shared_steps, fork_sections, title = module.parse_comparison_manifest(manifest)
    assert title == "My Compare"
    assert len(shared_steps) == 1
    assert shared_steps[0].name == "prompt-01-setup / iter 01 generator"
    assert len(fork_sections) == 1
    assert sorted(fork_sections[0].variants) == ["variant-a", "variant-b"]
    assert all(len(steps) == 1 for steps in fork_sections[0].variants.values())


def test_parse_comparison_manifest_diagnostic_keeps_all_steps(tmp_path):
    module = _load_module()
    source_file = tmp_path / "source.md"
    source_file.write_text(
        """## Prompt 1: Setup

```
Shared setup prompt.
```

```
VERDICT: pass
```
""",
        encoding="utf-8",
    )
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_codex_run(run_a, source_file, "prompt-01-setup", "Shared setup prompt.", "setup ok")
    _write_codex_run(run_b, source_file, "prompt-01-setup", "Shared setup prompt.", "setup ok")

    manifest = tmp_path / "compare.json"
    manifest.write_text(
        json.dumps(
            {
                "title": "Diagnostic",
                "mode": "diagnostic",
                "runs": [
                    {"label": "A", "path": str(run_a)},
                    {"label": "B", "path": str(run_b)},
                ],
            }
        ),
        encoding="utf-8",
    )

    shared_steps, fork_sections, title = module.parse_comparison_manifest(manifest)
    assert title == "Diagnostic"
    assert shared_steps == []
    assert len(fork_sections) == 1
    assert all(len(steps) == 1 for steps in fork_sections[0].variants.values())


def test_load_report_document_uses_comparison_adapter(tmp_path):
    module = _load_module()
    source_file = tmp_path / "source.md"
    source_file.write_text(
        """## Prompt 1: Setup

```
Shared setup prompt.
```

```
VERDICT: pass
```
""",
        encoding="utf-8",
    )
    run_a = tmp_path / "run-a"
    _write_codex_run(run_a, source_file, "prompt-01-setup", "Shared setup prompt.", "setup ok")
    manifest = tmp_path / "compare.json"
    manifest.write_text(
        json.dumps(
            {
                "title": "Adapter Check",
                "mode": "comparison",
                "runs": [{"label": "A", "path": str(run_a)}],
            }
        ),
        encoding="utf-8",
    )
    doc = module.load_report_document(manifest)
    assert doc.run_title == "Adapter Check"
    assert len(doc.fork_sections) == 1


def test_parse_prompt_runner_module_includes_selection_fork_and_selected_variant(tmp_path):
    module = _load_module()
    module_dir = tmp_path / "choose-ui"
    _write_selection_module_run(module_dir)

    shared_steps, fork_sections = module.parse_prompt_runner_run(module_dir)

    assert len(shared_steps) == 3
    assert all(step.name.startswith("prompt-02-record-selected-design") for step in shared_steps)
    assert len(fork_sections) == 1
    fork = fork_sections[0]
    assert fork.fork_index == 1
    assert fork.selected_variant == "B"
    assert fork.selector_rationale == "Variant B is cleaner."
    assert len(fork.selector_steps) == 1
    assert fork.selector_steps[0].name.startswith("prompt-01 / iter 01 judge")
    assert sorted(fork.variants) == ["variant-a", "variant-b"]
    assert fork.variant_titles["variant-a"] == "Bold layout"
    assert fork.variant_titles["variant-b"] == "Quiet layout"


def test_render_html_shows_selector_and_selected_variant_for_selection_fork(tmp_path):
    module = _load_module()
    module_dir = tmp_path / "choose-ui"
    _write_selection_module_run(module_dir)

    doc = module.load_report_document(module_dir)
    html = module.render_html(doc)

    assert "selected=B" in html
    assert "Variant B is cleaner." in html
    assert "<strong>Selector</strong>" in html
    assert "select</span>" in html
    assert "Variant B: Quiet layout (selected)" in html
    assert "toggleGroup('fork-01'" in html
    assert "toggleGroup('fork-01-selector'" in html
    assert "toggleGroup('fork-01-variant-a'" in html
    assert 'data-groups="fork-01"' in html
    assert 'data-groups="fork-01 fork-01-variant-a"' in html


def test_render_html_includes_elapsed_start_and_links_columns(tmp_path):
    module = _load_module()
    started = module._parse_iso_datetime("2026-04-12T02:10:11Z")
    ended = module._parse_iso_datetime("2026-04-12T02:13:09Z")
    assert started is not None
    assert ended is not None
    step = module.Step(
        name="prompt-01-build / iter 01 generator",
        started=started,
        ended=ended,
        size_bytes=1024,
        detail=module.CallDetail(
            backend="codex",
            output_tokens=20,
            prompt_text="Write docs/out.txt",
            output_text="done",
        ),
        log_path=tmp_path / "iter-01-generator.stdout.log",
    )
    step.log_path.write_text('{"type":"thread.started","thread_id":"abc"}\n', encoding="utf-8")
    doc = module.ReportDocument(
        run_title="Demo",
        workspace=tmp_path,
        shared_steps=[step],
    )

    html = module.render_html(doc)

    assert "<th>T+</th>" in html
    assert "<th>Start</th>" in html
    assert "<th>Links</th>" in html
    assert "0000s" in html
    assert module._fmt_clock(started) in html
    assert "prompt</a>" in html
    assert "output</a>" in html
    assert "log</a>" in html
    assert "toggleStepDetail(" in html
    assert 'style="display:none"' in html
    assert 'step-toggle' in html


def test_backfill_prompts_from_file_sets_model_and_estimates_cost(tmp_path):
    module = _load_module()
    prompt_file = tmp_path / "prompt-file.md"
    prompt_file.write_text(
        """## Prompt 1: Demo Step [MODEL:gpt-5.4-mini]

```
Write docs/out.txt
```

```
VERDICT: pass
```
""",
        encoding="utf-8",
    )
    detail = module.CallDetail(
        backend="codex",
        input_tokens=1000,
        cache_read_tokens=500,
        output_tokens=200,
    )
    step = module.Step(
        name="prompt-01-demo-step / iter 01 generator",
        started=module._parse_iso_datetime("2026-04-12T02:10:11Z"),
        ended=module._parse_iso_datetime("2026-04-12T02:10:12Z"),
        detail=detail,
    )
    tl = module.PhaseTimeline(phase_id="PH-000", phase_number=0, steps=[step])

    module._backfill_prompts_from_file(tl, prompt_file)

    assert step.detail.prompt_text == "Write docs/out.txt"
    assert step.detail.model == "gpt-5.4-mini"
    assert step.detail.cost_estimated is True
    assert step.detail.cost_usd > 0


def test_parse_comparison_manifest_reports_missing_run_path(tmp_path):
    module = _load_module()
    manifest = tmp_path / "compare.json"
    manifest.write_text(
        json.dumps(
            {
                "title": "Missing",
                "mode": "comparison",
                "runs": [{"label": "A", "path": str(tmp_path / "nope")}],
            }
        ),
        encoding="utf-8",
    )
    try:
        module.parse_comparison_manifest(manifest)
    except ValueError as exc:
        assert "run path not found" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_parse_prompt_runner_run_supports_current_module_layout(tmp_path):
    module = _load_module()
    run_dir = tmp_path / "requirements-inventory"
    agents_dir = tmp_path / ".codex" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "prompt-runner-generator.toml").write_text(
        'model = "gpt-5.4"\nmodel_reasoning_effort = "medium"\n',
        encoding="utf-8",
    )
    (agents_dir / "prompt-runner-judge.toml").write_text(
        'model = "gpt-5.4"\nmodel_reasoning_effort = "medium"\n',
        encoding="utf-8",
    )
    _write_current_module_run(run_dir, prompt_slug="prompt-01-produce-requirements-inventory")

    shared_steps, fork_sections = module.parse_prompt_runner_run(run_dir)

    assert not fork_sections
    assert [step.name for step in shared_steps] == [
        "prompt-01-produce-requirements-inventory / iter 01 generator",
        "prompt-01-produce-requirements-inventory / iter 01 deterministic validation",
        "prompt-01-produce-requirements-inventory / iter 01 judge",
    ]
    assert shared_steps[0].detail is not None
    assert shared_steps[0].detail.prompt_text == "Generator prompt body"
    assert shared_steps[0].detail.model == "gpt-5.4"
    assert shared_steps[0].detail.cost_estimated is True
    assert shared_steps[0].detail.cost_usd > 0
    assert shared_steps[2].detail is not None
    assert shared_steps[2].detail.prompt_text == "Judge prompt body"
    assert shared_steps[2].detail.model == "gpt-5.4"
    assert shared_steps[2].detail.cost_estimated is True
    assert shared_steps[2].detail.cost_usd > 0


def test_load_report_document_supports_current_methodology_workspace_layout(tmp_path):
    module = _load_module()
    workspace = tmp_path / "workspace"
    phase_module_dir = workspace / ".run-files" / "requirements-inventory"
    _write_current_module_run(phase_module_dir, prompt_slug="prompt-01-produce-requirements-inventory")

    cross_ref_dir = workspace / ".run-files" / "PH-000-requirements-inventory"
    cross_ref_dir.mkdir(parents=True, exist_ok=True)
    cross_ref_path = cross_ref_dir / "cross-ref-result.json"
    cross_ref_path.write_text(json.dumps({"passed": True, "issues": []}), encoding="utf-8")

    state_dir = workspace / ".methodology-runner"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "state.json").write_text(
        json.dumps(
            {
                "phases": [
                    {
                        "phase_id": "PH-000-requirements-inventory",
                        "status": "completed",
                        "started_at": "2026-04-19T05:11:51.338212+00:00",
                        "completed_at": "2026-04-19T05:14:23.049138+00:00",
                        "cross_ref_result_path": str(cross_ref_path),
                    }
                ],
                "lifecycle_phases": [
                    {
                        "phase_id": "LC-001-methodology-execution",
                        "phase_name": "Methodology Execution",
                        "status": "completed",
                        "started_at": "2026-04-19T05:11:00.000000+00:00",
                        "completed_at": "2026-04-19T05:14:23.049138+00:00",
                        "execution_kind": "automated",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    document = module.load_report_document(workspace)

    assert document.run_title == "Methodology Runner Timeline"
    assert len(document.timelines) == 1
    timeline = document.timelines[0]
    assert timeline.phase_id == "PH-000-requirements-inventory"
    assert timeline.lifecycle_phase_id == "LC-001-methodology-execution"
    assert [step.name for step in timeline.steps] == [
        "prompt-01-produce-requirements-inventory / iter 01 generator",
        "prompt-01-produce-requirements-inventory / iter 01 deterministic validation",
        "prompt-01-produce-requirements-inventory / iter 01 judge",
        "Cross-reference verification",
    ]


def test_render_html_collapses_phases_by_default(tmp_path):
    module = _load_module()
    started = module._parse_iso_datetime("2026-04-12T02:10:11Z")
    ended = module._parse_iso_datetime("2026-04-12T02:13:09Z")
    assert started is not None
    assert ended is not None
    step = module.Step(
        name="prompt-01-build / iter 01 generator",
        started=started,
        ended=ended,
        size_bytes=1024,
        detail=module.CallDetail(
            backend="codex",
            output_tokens=20,
            prompt_text="Write docs/out.txt",
            output_text="done",
        ),
    )
    timeline = module.PhaseTimeline(
        phase_id="PH-000-requirements-inventory",
        phase_number=0,
        steps=[step],
    )
    doc = module.ReportDocument(
        run_title="Demo",
        workspace=tmp_path,
        timelines=[timeline],
    )

    html = module.render_html(doc)

    assert "toggleGroup(" in html
    assert 'phase-toggle' in html
    assert 'data-groups="phase-000"' in html


def test_main_writes_parent_and_child_reports_for_ph006_nested_run(tmp_path):
    module = _load_module()
    workspace = tmp_path / "workspace"

    phase6_module_dir = workspace / ".run-files" / "incremental-implementation"
    _write_current_module_run(phase6_module_dir, prompt_slug="prompt-01-produce-incremental-implementation-workflow")

    child_module_dir = workspace / ".run-files" / "implementation-workflow"
    _write_current_module_run(child_module_dir, prompt_slug="prompt-01-first-executable-slice")

    cross_ref_dir = workspace / ".run-files" / "PH-006-incremental-implementation"
    cross_ref_dir.mkdir(parents=True, exist_ok=True)
    cross_ref_path = cross_ref_dir / "cross-ref-result.json"
    cross_ref_path.write_text(json.dumps({"passed": True, "issues": []}), encoding="utf-8")

    state_dir = workspace / ".methodology-runner"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "state.json").write_text(
        json.dumps(
            {
                "phases": [
                    {
                        "phase_id": "PH-006-incremental-implementation",
                        "status": "completed",
                        "started_at": "2026-04-19T05:39:58.354173+00:00",
                        "completed_at": "2026-04-19T05:54:23.386282+00:00",
                        "cross_ref_result_path": str(cross_ref_path),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    impl_docs = workspace / "docs" / "implementation"
    impl_docs.mkdir(parents=True, exist_ok=True)
    (impl_docs / "implementation-run-report.yaml").write_text(
        "\n".join(
            [
                "child_prompt_path: docs/implementation/implementation-workflow.md",
                f"child_run_dir: {workspace}",
                "completion_status: completed",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    output = workspace / "timeline.html"
    rc = module.main([str(workspace), "--output", str(output)])

    assert rc == 0
    assert output.exists()
    child_output = workspace / "timeline-implementation-workflow.html"
    assert child_output.exists()
    parent_html = output.read_text(encoding="utf-8")
    child_html = child_output.read_text(encoding="utf-8")
    assert 'drill down' in parent_html
    assert 'timeline-implementation-workflow.html' in parent_html
    assert 'bubble up' in child_html
    assert 'timeline.html' in child_html
