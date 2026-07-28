# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Modified with AI assistance.
# Responsibility: Verify cross-tool, Codex, and Junie execution reporting.
# Design: docs/design/components/CD-001-codex-rollout-metrics.md

from __future__ import annotations

import importlib.util
import json
import os
import re
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


def _write_codex_catalog_rollout(
    root: Path,
    *,
    thread_id: str,
    timestamp: str,
    request: str,
    workspace: str,
    parent_thread_id: str = "",
) -> Path:
    """Write one minimal native Codex rollout for catalog CLI tests."""
    rollout = root / f"rollout-{thread_id}.jsonl"
    rollout.parent.mkdir(parents=True, exist_ok=True)
    source: object = "user"
    if parent_thread_id:
        source = {
            "subagent": {
                "thread_spawn": {
                    "parent_thread_id": parent_thread_id,
                    "agent_path": f"/root/{thread_id}",
                }
            }
        }
    records = [
        {
            "timestamp": timestamp,
            "type": "session_meta",
            "payload": {
                "id": thread_id,
                "source": source,
                "cwd": workspace,
            },
        },
        {
            "timestamp": timestamp,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": request}],
            },
        },
        {
            "timestamp": timestamp,
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": f"{thread_id}-turn",
                "completed_at": timestamp,
                "duration_ms": 1,
            },
        },
    ]
    rollout.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return rollout


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
            "prompt": "Synthetic prompt API_TOKEN=PRIVATE",
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
            1_783_993_818_025,
            main,
            kind="AgentThoughtBlockUpdatedEvent",
            stepId="thought-1",
            text="Inspect the project before running the command.",
        ),
        agent_event(
            1_783_993_818_030,
            main,
            kind="TerminalBlockUpdatedEvent",
            stepId="terminal-1",
            status="IN_PROGRESS",
            command=(
                "sed -n '1,120p' /opt/codex/skills/python/SKILL.md && "
                "API_TOKEN=PRIVATE echo hello"
            ),
            output="",
        ),
        agent_event(
            1_783_993_818_040,
            main,
            kind="TerminalBlockUpdatedEvent",
            stepId="terminal-1",
            status="COMPLETED",
            command=(
                "sed -n '1,120p' /opt/codex/skills/python/SKILL.md && "
                "API_TOKEN=PRIVATE echo hello"
            ),
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
            1_783_993_818_055,
            custom,
            kind="AgentTaskNameUpdatedEvent",
            name="Review the implementation",
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


def _write_junie_ide_chain(root: Path) -> Path:
    issues = root / "issues"
    issues.mkdir()
    manifest = issues / "chain-test.json"
    chain = issues / "chain-test"
    chain.mkdir()
    manifest.write_text(
        json.dumps(
            {
                "id": {"id": "test-chain"},
                "name": "Synthetic Junie IDE chain",
                "created": "2026-07-15T13:26:49Z",
                "state": "Finished",
            }
        ),
        encoding="utf-8",
    )

    def observation(response_id: str, usage: dict[str, int], skill: str = ""):
        tool_uses = []
        if skill:
            tool_uses.append(
                {
                    "toolCallId": {"name": "agent_skill_read_doc"},
                    "input": {"rawJsonObject": {"name": skill}},
                }
            )
        return {
            "assistantRequest": {
                "answerChoiceId": response_id,
                "usage": usage,
                "toolUses": tool_uses,
            }
        }

    first_observation = observation(
        "response-0",
        {
            "inputTokens": 10,
            "cacheInputTokens": 5,
            "cacheCreateInputTokens": 2,
            "outputTokens": 3,
            "reasoningTokens": 1,
        },
        "typescript",
    )
    second_observation = observation(
        "response-1",
        {
            "inputTokens": 4,
            "cacheInputTokens": 6,
            "cacheCreateInputTokens": 1,
            "outputTokens": 2,
            "reasoningTokens": 2,
        },
    )
    task_specs = [
        {
            "index": 0,
            "created": "2026-07-15T13:26:49Z",
            "start": 1_784_122_009,
            "cost": 0.10,
            "description": "Synthetic prompt API_TOKEN=PRIVATE",
            "previous": [],
            "observations": [first_observation],
            "steps": [
                ("Prompt", "", "Synthetic prompt API_TOKEN=PRIVATE"),
                ("Info", "Thinking", "Inspect the project."),
                ("Info", "Open navbar.scss", "Opened the navbar stylesheet."),
                ("ChatResponse", "Analysis complete", "The stylesheet was inspected."),
            ],
        },
        {
            "index": 1,
            "created": "2026-07-15T13:26:59Z",
            "start": 1_784_122_019,
            "cost": 0.20,
            "description": "Apply the contrast fix",
            "previous": [first_observation],
            "observations": [first_observation, second_observation],
            "steps": [
                ("Prompt", "", "Apply the contrast fix"),
                ("Terminal", "Run tests", "Tests passed."),
                ("Edit", "Edit navbar.scss", "Updated the active navigation rule."),
                ("Report", "Fix complete", "The active navigation contrast was fixed."),
            ],
        },
    ]
    for task_spec in task_specs:
        index = task_spec["index"]
        task_path = chain / f"task-{index}.json"
        task_path.write_text(
            json.dumps(
                {
                    "id": {"index": index},
                    "created": task_spec["created"],
                    "cost": task_spec["cost"],
                    "context": {"description": task_spec["description"]},
                    "previousTasksInfo": {
                        "agentState": {"observations": task_spec["previous"]}
                    },
                    "finalAgentState": {
                        "isFinished": True,
                        "modelAndApiVersion": "gpt-5.6-terra",
                        "observations": task_spec["observations"],
                    },
                }
            ),
            encoding="utf-8",
        )
        steps = chain / f"task-{index}" / "steps"
        steps.mkdir(parents=True)
        for step_index, (step_type, command, description) in enumerate(task_spec["steps"]):
            step_path = steps / f"step-{step_index}.json"
            step_path.write_text(
                json.dumps(
                    {
                        "type": step_type,
                        "command": command,
                        "description": description,
                        "id": f"task-{index}-step-{step_index}",
                    }
                ),
                encoding="utf-8",
            )
            os.utime(step_path, (task_spec["start"] + step_index,) * 2)
        os.utime(task_path, (task_spec["start"] + 3,) * 2)
    os.utime(manifest, (1_784_122_022,) * 2)
    return manifest


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
    assert thread.skills_used == ["careful-coding", "python"]
    assert thread.turns[0].skills_used == ["careful-coding", "python"]
    assert thread.tool_intervals[0].argument_summary == (
        "sed -n '1,120p' /opt/codex/skills/careful-coding/SKILL.md "
        "/opt/codex/skills/python/SKILL.md && API_TOKEN=[redacted] python app.py"
    )


def test_native_codex_reports_mcp_calls_and_skill_load_sources(tmp_path):
    module = _load_module()
    assert module._is_bash_skill_loader(
        "functions.exec",
        "await tools.exec_command({cmd: 'sed SKILL.md'})",
        None,
    )
    assert not module._is_bash_skill_loader(
        "functions.exec",
        "await tools.mcp__mcp_agent_ops__skill_load({names: ['python']})",
        None,
    )
    rollout = tmp_path / "mcp-trace.jsonl"
    records = [
        {
            "timestamp": "2026-07-16T22:50:00Z",
            "type": "session_meta",
            "payload": {"id": "mcp-trace-thread", "source": "user"},
        },
        {
            "timestamp": "2026-07-16T22:50:00Z",
            "type": "turn_context",
            "payload": {"turn_id": "mcp-turn", "model": "gpt-5.4-mini"},
        },
        {
            "timestamp": "2026-07-16T22:50:00Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "mcp-turn",
                "started_at": "2026-07-16T22:50:00Z",
            },
        },
        {
            "timestamp": "2026-07-16T22:50:01Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "call_id": "shell-skill-load",
                "name": "exec",
                "input": "sed -n '1,220p' /opt/codex/skills/python/SKILL.md",
            },
        },
        {
            "timestamp": "2026-07-16T22:50:01.100Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "shell-skill-load",
                "output": '{"wall_time_seconds":0.1,"output":"loaded"}',
            },
        },
        {
            "timestamp": "2026-07-16T22:50:03Z",
            "type": "event_msg",
            "payload": {
                "type": "mcp_tool_call_end",
                "call_id": "exec-skill-load",
                "invocation": {
                    "server": "mcp-agent-ops",
                    "tool": "skill_load",
                    "arguments": {"names": ["structured-design", "python"]},
                },
                "duration": {"secs": 0, "nanos": 10_371_917},
                "result": {
                    "Ok": {
                        "content": [
                            {"type": "text", "text": "API_TOKEN=PRIVATE-MCP-CONTENT"}
                        ],
                        "structuredContent": {
                            "ok": True,
                            "catalog_revision": "af37d9acecca2823",
                            "skills": [
                                {
                                    "name": "structured-design",
                                    "content": "PRIVATE-SKILL-CONTENT",
                                },
                                {"name": "python", "content": "PRIVATE-PYTHON-CONTENT"},
                            ],
                            "errors": [],
                        },
                        "isError": False,
                    }
                },
            },
        },
        {
            "timestamp": "2026-07-16T22:50:04Z",
            "type": "event_msg",
            "payload": {
                "type": "mcp_tool_call_end",
                "call_id": "exec-claim-status",
                "invocation": {
                    "server": "mcp-agent-ops",
                    "tool": "claim_status",
                    "arguments": {"repository": "/work/agent-runner"},
                },
                "duration": {"secs": 0, "nanos": 5_000_000},
                "result": {
                    "Ok": {
                        "structuredContent": {
                            "exit_code": 0,
                            "result": {"outcome": "STATUS", "claims": []},
                        },
                        "isError": False,
                    }
                },
            },
        },
        {
            "timestamp": "2026-07-16T22:50:04.500Z",
            "type": "event_msg",
            "payload": {
                "type": "mcp_tool_call_end",
                "call_id": "exec-verify-failed",
                "invocation": {
                    "server": "mcp-agent-ops",
                    "tool": "verify_yaml",
                    "arguments": {
                        "repository_root": "/work/agent-runner",
                        "paths": ["broken.yaml"],
                    },
                },
                "duration": {"secs": 0, "nanos": 3_000_000},
                "result": {"Err": "connection failed"},
            },
        },
        {
            "timestamp": "2026-07-16T22:50:05Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "mcp-turn",
                "completed_at": "2026-07-16T22:50:05Z",
                "duration_ms": 5_000,
            },
        },
    ]
    rollout.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    run = module.build_codex_rollout_run("mcp-trace-thread", tmp_path)
    thread = run.threads[0]
    turn = thread.turns[0]

    assert run.parser_version == "1.19.0"
    assert thread.skills_used == ["python", "structured-design"]
    assert thread.mcp_skills_loaded == ["python", "structured-design"]
    assert thread.bash_skills_loaded == ["python"]
    assert turn.skills_used == ["python", "structured-design"]
    assert turn.mcp_skills_loaded == ["python", "structured-design"]
    assert turn.bash_skills_loaded == ["python"]
    assert turn.mcp_call_count == 3
    assert len(thread.mcp_calls) == 3
    assert thread.mcp_calls[0].duration_ms == 10
    assert thread.mcp_calls[0].argument_summary == (
        "skills: structured-design · python"
    )
    assert thread.mcp_calls[0].result_summary == (
        "OK · 2 skills · 0 errors · revision af37d9ac"
    )
    assert thread.mcp_calls[1].argument_summary == "repository: agent-runner"
    assert thread.mcp_calls[1].result_summary == "STATUS · exit 0"
    assert thread.mcp_calls[2].succeeded is False
    assert thread.mcp_calls[2].result_summary == "Error"

    html = module.render_codex_rollout_html(run)
    markdown = module.render_codex_rollout_markdown(run)
    agent_table = html.split('<table class="agent-table">', 1)[1].split(
        "</table>", 1
    )[0]
    overlay = html.split('id="turn-tool-call-list-1-1"', 1)[1].split(
        "</section>", 1
    )[0]

    assert '<div class="label">MCP calls</div><div class="value">3</div>' in html
    assert "<th>Turns<br><span class=\"column-detail\">(Tools/MCP)</span></th>" in agent_table
    assert '<th class="agent-timeline-header">Timeline</th>' in agent_table
    assert '<span class="cell-secondary">(1/3)</span>' in agent_table
    assert agent_table.count('class="timeline-bar agent-timeline-bar"') == 1
    assert "gpt-5.4-mini" in agent_table
    assert '<div class="label">Skills via MCP</div><div class="value">2</div>' in overlay
    assert '<div class="label">Skills via Bash</div><div class="value">1</div>' in overlay
    assert '<div class="label">Skills used</div>' not in overlay
    assert "mcp-agent-ops → skill_load" in overlay
    assert "skills: structured-design · python" in overlay
    assert "OK · 2 skills · 0 errors · revision af37d9ac" in overlay
    assert "MCP-recorded execution time" not in overlay

    thread.mcp_calls = thread.mcp_calls * 2
    turn.mcp_call_count = len(thread.mcp_calls)
    turn.mcp_skills_loaded = [f"mcp-skill-{index}" for index in range(1, 7)]
    turn.bash_skills_loaded = [f"bash-skill-{index}" for index in range(1, 7)]
    clamped_html = module.render_codex_rollout_html(run)
    clamped_overlay = clamped_html.split(
        'id="turn-tool-call-list-1-1"', 1
    )[1].split("</section>", 1)[0]

    assert (
        '<details class="clamped-disclosure turn-mcp-calls-disclosure">'
        in clamped_overlay
    )
    assert (
        '<details class="clamped-disclosure turn-mcp-skills-disclosure">'
        in clamped_overlay
    )
    assert (
        '<details class="clamped-disclosure turn-bash-skills-disclosure">'
        in clamped_overlay
    )
    assert clamped_overlay.count('class="clamped-toggle clamped-more"') == 3
    assert clamped_overlay.count('class="clamped-toggle clamped-less"') == 3
    assert "mcp-skill-6" in clamped_overlay
    assert "bash-skill-6" in clamped_overlay
    assert "- MCP calls: 3" in markdown
    assert "PRIVATE" not in html


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

    content = module._tool_argument_payload_content(
        {
            "input": (
                'const r = await tools.example({api_key:"PRIVATE-API-KEY",'
                'value:"visible"}); text(r);'
            )
        }
    )
    assert 'api_key:"[redacted]"' in content
    assert 'value:"visible"' in content
    assert "PRIVATE" not in content


def test_native_codex_parser_retains_full_bounded_tool_argument_content(tmp_path):
    module = _load_module()
    rollout = tmp_path / "root.jsonl"
    plan_source = (
        'const r = await tools.update_plan({plan:['
        '{step:"Inspect memory",status:"completed"},'
        '{step:"Run required validation, review diff, and commit coherent changes",'
        'status:"pending"}'
        ']}); text(r);'
    )
    records = [
        {
            "timestamp": "2026-07-16T22:00:00Z",
            "type": "session_meta",
            "payload": {"id": "root", "source": "user"},
        },
        {
            "timestamp": "2026-07-16T22:00:00Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "turn-1",
                "started_at": "2026-07-16T22:00:00Z",
            },
        },
        {
            "timestamp": "2026-07-16T22:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "call_id": "call-1",
                "name": "exec",
                "input": plan_source,
            },
        },
        {
            "timestamp": "2026-07-16T22:00:02Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "call-1",
                "output": [{"type": "input_text", "text": "{}"}],
            },
        },
        {
            "timestamp": "2026-07-16T22:00:03Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "turn-1",
                "completed_at": "2026-07-16T22:00:03Z",
            },
        },
    ]
    rollout.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    run = module.build_codex_rollout_run("root", tmp_path)

    assert len(run.threads[0].tool_intervals) == 1
    tool = run.threads[0].tool_intervals[0]
    assert len(tool.argument_summary) <= module.CODEX_TOOL_ARGUMENT_SUMMARY_CHARS
    assert tool.argument_content == plan_source
    assert "Run required validation, review diff, and commit coherent changes" in (
        module._render_tool_argument(tool, module._load_tool_formatter_config())
    )


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
    repository_skill_sizing = module._format_tool_argument(
        "exec",
        'const r = await tools.exec_command({"cmd":"git status --short && '
        'git log -2 --oneline && wc -l '
        '/Users/example/.codex/skills/agent-claim/SKILL.md '
        '/Users/example/.codex/skills/detect-technology-skills/SKILL.md"}); '
        "text(r.output);",
        config,
    )
    skill_sizing = module._format_tool_argument(
        "exec",
        "wc -l /Users/example/.codex/skills/agent-claim/SKILL.md "
        "/Users/example/.codex/skills/code-discovery/SKILL.md",
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
    assert repository_skill_sizing.summary == (
        "Inspect repository · latest 2 commits · count skill-file lines"
    )
    assert repository_skill_sizing.rule_id == "repository-skill-sizing"
    assert skill_sizing.summary == "Count skill-file lines"
    assert skill_sizing.rule_id == "skill-sizing"


def test_native_codex_html_formats_tool_arguments_with_sanitized_raw_disclosure():
    module = _load_module()
    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)
    tool = run.threads[0].tool_intervals[0]
    tool.tool_name = "exec"
    tool.argument_summary = (
        'const patch = "*** Begin Patch\\n*** Add File: '
        '/tmp/docs/example.md\\n+# Example'
    )
    tool.argument_content = ""

    html = module.render_codex_rollout_html(run)

    assert '<div class="tool-argument-formatted">Patch · Add · example.md</div>' in html
    assert (
        ".tool-argument-formatted { font-family:var(--font-ui); font-size:1em; "
        "font-weight:400; line-height:1.35; color:#263238; white-space:normal; "
        "overflow-wrap:anywhere; }"
    ) in html
    assert '<code class="tool-name">exec</code>' in html
    assert (
        ".tool-arguments { display:block; max-width:720px; "
        "font-family:var(--font-code); font-size:.9em; font-weight:400;"
    ) in html
    assert (
        ".tool-result-summary { max-width:420px; font-family:var(--font-ui); "
        "font-size:1em; font-weight:400; line-height:1.35; color:#263238;"
    ) in html
    assert (
        ".tool-result-raw pre { max-width:720px; max-height:360px; "
        "margin:5px 0 0; padding:8px; overflow:auto; "
        "font-family:var(--font-code);"
    ) in html
    assert '<details class="tool-argument-raw"><summary>raw</summary>' in html
    assert "*** Add File: /tmp/docs/example.md" in html
    assert "<th>Result</th>" in html
    assert "<summary>raw result</summary>" in html
    assert "raw result (redacted)" not in html


def test_native_codex_html_formats_update_plan_as_complete_bulleted_plan():
    module = _load_module()
    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)
    tool = run.threads[0].tool_intervals[0]
    tool.tool_name = "exec"
    tool.argument_summary = (
        'const r = await tools.update_plan({plan:[{step:"Inspect memory",'
        'status:"in_progress"},{step:"Research Quarkus",status:"pending"},...'
    )
    tool.argument_content = (
        'const r = await tools.update_plan({explanation:"Current status",plan:['
        '{step:"Inspect memory",status:"in_progress"},'
        '{step:"Research Quarkus",status:"pending"},'
        '{step:"Author Quarkus skills",status:"pending"},'
        '{step:"Regenerate documentation",status:"pending"},'
        '{step:"Run required verification",status:"pending"}'
        "]}); text(r);"
    )

    rendered = module._render_tool_argument(tool, module._load_tool_formatter_config())

    assert "clamped-disclosure" not in rendered
    assert "tool-plan-preview" not in rendered
    assert rendered.count('<li class="tool-plan-item">') == 5
    assert rendered.count('<ul class="tool-plan">') == 1
    assert '<span class="state state-active">in progress</span>' in rendered
    assert '<span class="state">pending</span>' in rendered
    assert "Inspect memory" in rendered
    assert "Run required verification" in rendered
    assert '<details class="tool-argument-raw"><summary>raw</summary>' in rendered
    assert "tools.update_plan" in rendered


def test_native_codex_special_formatting_is_not_clamped_for_long_raw_source():
    module = _load_module()
    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)
    tool = run.threads[0].tool_intervals[0]
    tool.tool_name = "exec"
    tool.argument_summary = (
        'const patch = "*** Begin Patch\\n*** Update File: '
        '/tmp/docs/example.md\\n' + ("+detail\\n" * 50) + '*** End Patch"'
    )
    tool.argument_content = ""

    rendered = module._render_tool_argument(
        tool,
        module._load_tool_formatter_config(),
    )

    assert "clamped-disclosure" not in rendered
    assert '<div class="tool-argument-formatted">Patch · Update · example.md</div>' in rendered
    assert '<details class="tool-argument-raw"><summary>raw</summary>' in rendered
    assert "*** End Patch" in rendered


def test_native_codex_long_argument_cells_expand_to_full_bounded_content():
    module = _load_module()
    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)
    tool = run.threads[0].tool_intervals[0]
    tool.tool_name = "exec"
    config = module._load_tool_formatter_config()

    tool.argument_summary = '{"cmd":"short"}'
    tool.argument_content = ""
    short_rendered = module._render_tool_argument(tool, config)
    assert "tool-argument-disclosure" not in short_rendered

    tool.argument_summary = '{"cmd":"' + ("preview " * 50) + '..."}'
    tool.argument_content = '{"cmd":"' + ("full argument " * 80) + 'END"}'
    long_rendered = module._render_tool_argument(tool, config)

    assert '<details class="clamped-disclosure tool-argument-disclosure">' in long_rendered
    assert '<span class="clamped-preview">' in long_rendered
    assert '<div class="clamped-full">' in long_rendered
    assert "END" in long_rendered

    mcp_call = module.McpCallInterval(
        thread_id="root-thread",
        turn_id="root-turn-1",
        call_id="mcp-call-1",
        server_name="mcp-agent-ops",
        tool_name="claim_status",
        started_at="2026-07-14T00:00:01Z",
        completed_at="2026-07-14T00:00:02Z",
        duration_ms=1_000,
        argument_summary="repository: agent-runner",
        argument_content='{"scope":"' + ("full MCP argument " * 40) + 'END"}',
        result_summary="OK",
        result_content="",
        succeeded=True,
        source_path="fixture.jsonl",
        source_ordinal=1,
    )
    mcp_rendered = module._render_mcp_argument(mcp_call)
    assert '<details class="clamped-disclosure tool-argument-disclosure">' in mcp_rendered
    assert "END" in mcp_rendered


def test_native_junie_session_reports_agents_usage_tools_and_redacted_results(tmp_path):
    module = _load_module()
    session = _write_junie_session(tmp_path)

    document = module.load_report_document(session)
    run = document.codex_run

    assert run is not None
    assert run.runtime == "Junie"
    assert run.state == "complete"
    assert run.format_version == module.JUNIE_SESSION_FORMAT
    assert run.parser_version == "1.7.0"
    assert len(run.threads) == 2
    assert sum(len(thread.turns) for thread in run.threads) == 2
    assert sum(len(thread.responses) for thread in run.threads) == 2
    assert sum(len(thread.tool_intervals) for thread in run.threads) == 3
    assert run.usage_totals.input_tokens == 28
    assert run.usage_totals.cached_input_tokens == 11
    assert run.usage_totals.cache_create_input_tokens == 3
    assert run.usage_totals.uncached_input_tokens == 17
    assert run.usage_totals.direct_input_tokens == 14
    assert run.usage_totals.output_tokens == 5
    assert run.usage_totals.processed_tokens == 33
    assert run.cost.status == "recorded"
    assert run.cost.total_cost == pytest.approx(0.03)

    custom = next(thread for thread in run.threads if thread.agent_path.endswith("/reviewer"))
    assert custom.thread_name == "Review the implementation"
    assert custom.agent_role == "reviewer"
    assert custom.model == "claude-reviewer"
    assert custom.token_totals.processed_tokens == 13
    assert custom.recorded_cost_usd == pytest.approx(0.02)
    assert custom.responses[0].recorded_cost_usd == pytest.approx(0.02)
    assert custom.responses[0].model == "claude-reviewer"
    assert [activity.activity_type for activity in custom.activities] == ["input"]
    assert custom.activities[0].content == "Synthetic prompt API_TOKEN=[redacted]"

    main = next(thread for thread in run.threads if thread.agent_path == "/main")
    assert main.thread_name == "main"
    assert main.agent_role == ""
    assert main.responses[0].model == "gpt-main"
    assert main.skills_used == ["python"]
    assert main.turns[0].skills_used == ["python"]
    assert [activity.activity_type for activity in main.activities] == [
        "input",
        "reasoning",
    ]
    assert main.activities[0].content == "Synthetic prompt API_TOKEN=[redacted]"
    assert "Inspect the project" in main.activities[1].content
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
    markdown = module.render_codex_rollout_markdown(run)
    assert "Junie run" in html
    assert "Recorded cost: $0.03 USD" in html
    assert '<div class="label">Summed agent time</div>' not in html
    assert '<div class="label">Active interval union</div>' not in html
    assert "<summary>raw result</summary>" in html
    assert "raw result (redacted)" not in html
    assert "Thread names come from Junie's AgentTaskNameUpdatedEvent" in html
    assert (
        "<strong>Thread: Review the implementation · Agent: reviewer</strong>"
        in html
    )
    assert '<div id="timeline" class="agents-heading"><h2>Timeline</h2>' in html
    assert '<summary aria-label="About Timeline">ⓘ</summary>' in html
    assert '<div class="agent-note-popover" role="note">' in html
    assert (
        '<p class="execution-note">Thread names come from Junie'
        not in html
    )
    assert "Bars share a common run-wide time axis" in html
    assert html.count('class="agent-summary-row"') == 2
    assert html.count('class="agent-expanded-row" hidden') == 2
    assert "Cached input is part of input" not in html
    assert "Reasoning is part of output" not in html
    assert 'class="composition-output">output 5</span>' in html
    assert 'class="composition-reasoning">reasoning 0</span>' in html
    assert (
        '<span class="composition-fresh">Fresh input 14</span> · '
        '<span class="composition-cached">Cache read 11</span> · '
        '<span class="composition-cache-write">Cache write 3</span>'
        in html
    )
    assert 'class="token-segment reasoning"' not in html
    assert "View task spans and tool calls" not in html
    assert '.agent-row-toggle-icon::before { content:"+"; }' in html
    assert (
        '.agent-row-toggle[aria-expanded="true"] '
        '.agent-row-toggle-icon::before { content:"−"; }'
    ) in html
    assert '<div class="label">User tasks</div><div class="value">1</div>' in html
    assert '<div class="label">Agent task spans</div><div class="value">2</div>' in html
    assert '<div class="label">Model responses</div><div class="value">2</div>' in html
    assert "Turns / responses" not in html
    agent_table = html.split('<table class="agent-table">', 1)[1].split("</table>", 1)[0]
    assert '<td class="agent-skills-cell">python</td>' in agent_table
    assert "Subagents invoked" not in agent_table
    task_span_table = html.split('<table class="turn-table"', 1)[1].split("</table>", 1)[0]
    assert "<th>TTFT</th>" not in task_span_table
    assert "<th>State</th>" not in task_span_table
    assert "<th>Duration</th>" not in task_span_table
    assert "<th>Cost est.</th>" not in task_span_table
    assert (
        '<code>task-1</code></a> <span class="state state-complete">complete</span>'
        in task_span_table
    )
    assert (
        '<th>Task spans<br><span class="column-detail">(Tools)</span></th>'
        '<th>Agent time<br><span class="column-detail">(Cost)</span></th>'
        in task_span_table
    )
    assert (
        '<td class="turn-activity-cell"><span class="cell-primary">1</span>'
        '<span class="cell-secondary">(2)</span></td>'
        '<td class="turn-time-cell"><span class="cell-primary">100ms</span>'
        '<span class="cell-secondary">($0.01)</span></td>'
        in task_span_table
    )
    assert (
        "<th>Fresh Input</th><th>Cache read</th><th>Cache write</th>"
        in task_span_table
    )
    assert "<th>Input</th>" not in task_span_table
    assert "<th>Processed</th>" not in task_span_table
    assert "<th>Tools</th>" not in task_span_table
    assert '<th>Reasoning</th><th class="turn-timeline-header">Timeline</th>' in task_span_table
    assert "recorded" not in task_span_table.lower()
    assert task_span_table.count('class="timeline-bar turn-timeline-bar"') == 1
    assert (
        "<td>10</td><td>5</td><td>2</td><td>3</td><td>0</td>"
        in task_span_table
    )
    assert (
        "| Assignment | Skills used | Task spans | Tools | Agent time | "
        "Fresh Input | Cache read | Cache write | Output | Reasoning | Processed |"
        in markdown
    )
    assert "| Input |" not in markdown
    assert (
        '<th>Task spans<br><span class="column-detail">(Tools)</span></th>'
        in html
    )
    assert "Task span task-1" in html
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
        '<th>#</th><th>T+</th><th title="Cost of the model response on this row; '
        'tool execution has no separately recorded model cost">Cost</th>'
        '<th>Model</th><th>Activity</th>'
    ) in custom_tool_table
    assert "<td>$0.02</td>" in custom_tool_table
    assert '<span class="activity-name">input</span>' in custom_tool_table
    assert '<span class="activity-name">model</span>' in custom_tool_table
    assert '<span class="activity-name">output</span>' in custom_tool_table
    assert "claude-reviewer" in custom_tool_table
    assert "4 fresh-input · 6 cache-read · 1 cache-write" in custom_tool_table
    custom_input_row = custom_tool_table.split(
        '<tr class="turn-detail-lifecycle-row turn-detail-input-row">', 1
    )[1].split("</tr>", 1)[0]
    assert '<td><code class="model-name">claude-reviewer</code></td>' in custom_input_row
    assert "Initial prompt · 37 characters" in custom_input_row
    assert (
        '<summary>raw input</summary><pre>Synthetic prompt API_TOKEN=[redacted]</pre>'
        in custom_input_row
    )
    assert "model-input tokens" not in custom_input_row
    assert "cache-read" not in custom_input_row
    assert "cache-create" not in custom_input_row
    main_overlay = html.split('id="turn-tool-call-list-1-1"', 1)[1].split(
        "</section>", 1
    )[0]
    assert "Time to first token" not in main_overlay
    main_tool_table = main_overlay.split('<div class="table-scroll">', 1)[1]
    assert "<td>$0.01</td>" in main_tool_table
    main_input_row = main_tool_table.split(
        '<tr class="turn-detail-lifecycle-row turn-detail-input-row">', 1
    )[1].split("</tr>", 1)[0]
    assert '<td><code class="model-name">gpt-main</code></td>' in main_input_row
    assert "model-input tokens" not in main_input_row
    assert (
        '<summary>raw input</summary><pre>Synthetic prompt API_TOKEN=[redacted]</pre>'
        in main_tool_table
    )
    assert '<span class="activity-name">reasoning</span>' in main_tool_table
    assert '<summary>raw reasoning</summary>' in main_tool_table
    assert 'title="Attributed from the latest preceding model response in this task span">gpt-main' in main_tool_table
    assert "Output generation aggregate" in main_tool_table
    main_model_row = main_tool_table.split(
        '<tr class="turn-detail-lifecycle-row turn-detail-model-row">', 1
    )[1].split("</tr>", 1)[0]
    assert "<summary>raw arguments</summary>" in main_model_row
    assert '<div class="activity-summary">1 prompt fragment</div>' in main_model_row
    assert "Synthetic prompt API_TOKEN=[redacted]" in main_model_row
    assert "10 fresh-input · 5 cache-read · 2 cache-write" in main_model_row
    assert "<summary>raw result</summary>" in main_model_row
    assert '<div class="activity-summary">1 thinking fragment</div>' in main_model_row
    assert "Inspect the project before running the command." in main_model_row
    assert "recorded</td>" not in main_tool_table
    assert "Open model pricing" not in html
    assert "PRIVATE" not in html


def test_native_junie_ide_chain_reports_finished_tasks_without_cumulative_double_counting(
    tmp_path,
):
    module = _load_module()
    manifest = _write_junie_ide_chain(tmp_path)

    document = module.load_report_document(manifest)
    run = document.codex_run

    assert run is not None
    assert run.runtime == "Junie"
    assert run.run_id == "test-chain"
    assert run.run_label == "Synthetic Junie IDE chain"
    assert run.root_thread_id == "test-chain"
    assert run.state == "complete"
    assert run.format_version == module.JUNIE_SESSION_FORMAT
    assert run.parser_version == "1.7.0"
    assert len(run.threads) == 1
    assert len(run.threads[0].turns) == 2
    assert len(run.threads[0].responses) == 2
    assert len(run.threads[0].tool_intervals) == 3
    assert run.usage_totals.input_tokens == 28
    assert run.usage_totals.cached_input_tokens == 11
    assert run.usage_totals.cache_create_input_tokens == 3
    assert run.usage_totals.uncached_input_tokens == 17
    assert run.usage_totals.direct_input_tokens == 14
    assert run.usage_totals.output_tokens == 5
    assert run.usage_totals.reasoning_tokens == 3
    assert run.usage_totals.processed_tokens == 33
    assert run.cost.status == "recorded"
    assert run.cost.total_cost == pytest.approx(0.30)
    assert run.wall_time_ms == 13_000
    assert run.active_time_ms == 6_000
    assert run.agent_time_ms == 6_000

    thread = run.threads[0]
    assert thread.agent_path == "/main"
    assert thread.model == "gpt-5.6-terra"
    assert thread.skills_used == ["typescript"]
    assert thread.turns[0].skills_used == ["typescript"]
    assert thread.recorded_cost_usd == pytest.approx(0.30)
    assert [turn.outcome for turn in thread.turns] == ["complete", "complete"]
    assert [tool.tool_name for tool in thread.tool_intervals] == [
        "read",
        "exec",
        "apply_patch",
    ]
    assert [activity.activity_type for activity in thread.activities] == [
        "input",
        "reasoning",
        "output",
        "input",
        "output",
    ]
    assert thread.activities[0].content == "Synthetic prompt API_TOKEN=[redacted]"

    html = module.render_html(document)
    assert "Junie run" in html
    assert "Recorded cost: $0.30 USD" in html
    assert '<div class="label">User tasks</div><div class="value">2</div>' in html
    assert "gpt-5.6-terra" in html
    assert "typescript" in html
    assert "This Junie IDE chain contains one main agent." in html
    assert '<summary aria-label="About Timeline">ⓘ</summary>' in html
    assert '<div class="agent-note-popover" role="note">' in html
    assert '<p class="run-label">Synthetic Junie IDE chain</p>' in html
    assert "Task costs come directly from Junie" in html
    assert "<td>$0.10</td>" in html
    assert "<td>$0.20</td>" in html
    assert "API_TOKEN=[redacted]" in html
    assert "PRIVATE" not in html


def test_native_junie_ide_chain_cli_generates_companion_reports(tmp_path):
    module = _load_module()
    manifest = _write_junie_ide_chain(tmp_path)
    output = tmp_path / "junie-ide-report.html"

    rc = module.main(
        [
            str(manifest),
            "--output",
            str(output),
            "--json-output",
            str(tmp_path / "junie-ide-report.json"),
            "--turn-csv-output",
            str(tmp_path / "junie-ide-report.turns.csv"),
            "--work-unit-csv-output",
            str(tmp_path / "junie-ide-report.work-units.csv"),
            "--markdown-output",
            str(tmp_path / "junie-ide-report.md"),
        ]
    )

    assert rc == 0
    assert "Junie run" in output.read_text(encoding="utf-8")
    assert (tmp_path / "junie-ide-report.json").exists()
    assert (tmp_path / "junie-ide-report.turns.csv").exists()
    assert (tmp_path / "junie-ide-report.work-units.csv").exists()
    assert "Runtime: `Junie`" in (tmp_path / "junie-ide-report.md").read_text(
        encoding="utf-8"
    )


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


def test_turn_model_tile_lists_mixed_models_and_tool_rows_show_event_order_model(tmp_path):
    module = _load_module()
    session = _write_junie_session(tmp_path)
    run = module.load_report_document(session).codex_run

    assert run is not None
    main = next(thread for thread in run.threads if thread.agent_path == "/main")
    second_response = module.deepcopy(main.responses[0])
    second_response.model = "gpt-helper"
    second_response.source_ordinal += 1
    second_response.recorded_cost_usd = 0.02
    main.responses.append(second_response)

    html = module.render_codex_rollout_html(run)
    overlay = html.split('id="turn-tool-call-list-1-1"', 1)[1].split(
        "</section>", 1
    )[0]

    assert 'mixed (2 models)<span class="metric-detail">gpt-main · gpt-helper</span>' in overlay
    assert '<th>Model</th><th>Activity</th>' in overlay
    assert '<td><code class="model-name">gpt-main</code></td>' in overlay
    assert '<td><code class="model-name">gpt-helper</code></td>' in overlay
    assert (
        'title="Attributed from the latest preceding model response in this task span">'
        "gpt-helper</code>"
    ) in overlay


def test_model_usage_section_groups_agents_under_model_before_timeline(tmp_path):
    module = _load_module()
    session = _write_junie_session(tmp_path)
    run = module.load_report_document(session).codex_run

    assert run is not None
    main = next(thread for thread in run.threads if thread.agent_path == "/main")
    reviewer = next(
        thread for thread in run.threads if thread.agent_path.endswith("/reviewer")
    )
    reviewer.model = main.model
    reviewer.responses[0].model = main.model

    html = module.render_codex_rollout_html(run)
    model_usage = html.split('<section id="model-usage"', 1)[1].split(
        '<div id="timeline"', 1
    )[0]

    assert html.index('<section id="model-usage"') < html.index('<div id="timeline"')
    assert "<h2>Usage by model</h2>" in model_usage
    assert model_usage.count('class="model-usage-group"') == 1
    assert (
        '<summary><span class="model-usage-toggle-icon" aria-hidden="true"></span>'
        '<span class="model-usage-parent">'
    ) in model_usage
    assert '.model-usage-group > summary::-webkit-details-marker { display:none; }' in html
    assert '.model-usage-toggle-icon::before { content:"+"; }' in html
    assert (
        '.model-usage-group[open] > summary .model-usage-toggle-icon::before '
        '{ content:"−"; }'
    ) in html
    assert f'<code class="model-name">{main.model}</code>' in model_usage
    assert 'class="model-effort"' not in model_usage
    assert "33 processed tokens" in model_usage
    assert "2 agents" in model_usage
    assert "Thread: main · Agent: main" in model_usage
    assert "Thread: Review the implementation · Agent: reviewer" in model_usage
    assert model_usage.count('class="model-usage-agent-row"') == 2
    assert (
        "<th>Agent</th><th>Fresh Input</th><th>Cache read</th>"
        "<th>Cache write</th><th>Output</th><th>Reasoning</th><th>Processed</th>"
        "<th>Model share</th>"
    ) in model_usage


def test_model_usage_separates_the_same_model_by_effort_level(tmp_path):
    module = _load_module()
    session = _write_junie_session(tmp_path)
    run = module.load_report_document(session).codex_run

    assert run is not None
    main = next(thread for thread in run.threads if thread.agent_path == "/main")
    reviewer = next(
        thread for thread in run.threads if thread.agent_path.endswith("/reviewer")
    )
    reviewer.model = main.model
    reviewer.responses[0].model = main.model
    main.effort = "max"
    main.responses[0].effort = "max"
    reviewer.effort = "medium"
    reviewer.responses[0].effort = "medium"

    html = module.render_codex_rollout_html(run)
    model_usage = html.split('<section id="model-usage"', 1)[1].split(
        '<div id="timeline"', 1
    )[0]

    assert model_usage.count('class="model-usage-group"') == 2
    assert model_usage.count(f'<code class="model-name">{main.model}</code>') == 2
    assert '<span class="model-effort">effort max</span>' in model_usage
    assert '<span class="model-effort">effort medium</span>' in model_usage
    assert "effort mixed" not in model_usage
    assert "Each model and effort combination is a separate group." in model_usage


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
    assert (
        '<details class="tool-argument-raw">'
        '<summary>raw source command (redacted)</summary>' in html
    )


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


def test_native_codex_completed_root_reports_failed_and_aborted_children_separately(tmp_path):
    module = _load_module()
    root = tmp_path / "root.jsonl"
    child = tmp_path / "child.jsonl"
    failed_child = tmp_path / "failed-child.jsonl"
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
    failed_child.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-07-14T10:00:00Z","type":"session_meta","payload":{"id":"failed-child","source":{"subagent":{"thread_spawn":{"parent_thread_id":"root","agent_path":"/root/reviewer"}}}}}',
                '{"timestamp":"2026-07-14T10:00:00Z","type":"event_msg","payload":{"type":"task_started","turn_id":"failed-child-turn","started_at":"2026-07-14T10:00:00Z"}}',
                '{"timestamp":"2026-07-14T10:00:01Z","type":"response_item","payload":{"type":"message","role":"assistant","phase":"final_answer","content":[{"type":"output_text","text":"**FAIL — required corrections remain.**"}]}}',
                '{"timestamp":"2026-07-14T10:00:02Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"failed-child-turn","completed_at":"2026-07-14T10:00:02Z","duration_ms":2000}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    run = module.build_codex_rollout_run("root", tmp_path)

    assert run.state == "complete-with-failed-and-aborted-children"
    assert {thread.terminal_state for thread in run.threads} == {
        "complete",
        "failed",
        "aborted",
    }


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
    assert "not an actual charge" in outputs[-1]
    assert "Critical path:" not in outputs[-1]


def test_native_codex_retains_redacted_lifecycle_content_and_exact_tool_model():
    module = _load_module()

    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)
    root = run.threads[0]

    assert run.parser_version == "1.19.0"
    assert [activity.activity_type for activity in root.activities] == [
        "input",
        "reasoning",
        "output",
    ]
    assert root.activities[0].content == "Inspect the project with API_TOKEN=[redacted]"
    assert root.activities[1].content == (
        "Check password=[redacted] before running the tool"
    )
    assert root.activities[1].model == "gpt-5.4-mini"
    assert root.activities[2].content == "Completed with client_secret=[redacted]"
    assert root.tool_intervals[0].model == "gpt-5.4-mini"

    html = module.render_codex_rollout_html(run)
    overlay = html.split('id="turn-tool-call-list-1-1"', 1)[1].split(
        "</section>", 1
    )[0]
    assert "<summary>raw input</summary>" in overlay
    assert "<summary>raw reasoning</summary>" in overlay
    assert "<summary>raw output</summary>" in overlay
    assert "Inspect the project with API_TOKEN=[redacted]" in overlay
    assert "Check password=[redacted] before running the tool" in overlay
    assert "Completed with client_secret=[redacted]" in overlay
    assert '<td><code class="model-name">gpt-5.4-mini</code></td>' in overlay
    assert "Attributed from the latest preceding model response" not in overlay
    model_row = overlay.split(
        '<tr class="turn-detail-lifecycle-row turn-detail-model-row">', 1
    )[1].split("</tr>", 1)[0]
    assert "<summary>raw arguments</summary>" in model_row
    assert '<div class="activity-summary">1 prompt fragment</div>' in model_row
    assert "Inspect the project with API_TOKEN=[redacted]" in model_row
    assert "<summary>raw result</summary>" in model_row
    assert (
        '<div class="activity-summary">1 thinking fragment · 1 response fragment</div>'
        in model_row
    )
    assert "Check password=[redacted] before running the tool" in model_row
    assert "Completed with client_secret=[redacted]" in model_row


def test_native_codex_identifies_encrypted_reasoning_without_exposing_it(tmp_path):
    module = _load_module()
    rollout = tmp_path / "encrypted.jsonl"
    rollout.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-07-14T10:00:00Z","type":"session_meta","payload":{"id":"encrypted-thread","source":"user"}}',
                '{"timestamp":"2026-07-14T10:00:00Z","type":"turn_context","payload":{"model":"gpt-5.6-sol","turn_id":"encrypted-turn"}}',
                '{"timestamp":"2026-07-14T10:00:00Z","type":"event_msg","payload":{"type":"task_started","turn_id":"encrypted-turn","started_at":"2026-07-14T10:00:00Z"}}',
                '{"timestamp":"2026-07-14T10:00:01Z","type":"response_item","payload":{"type":"reasoning","summary":[],"encrypted_content":"CIPHER-TEXT-MUST-NOT-APPEAR"}}',
                '{"timestamp":"2026-07-14T10:00:02Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":10,"cached_input_tokens":2,"output_tokens":3,"reasoning_output_tokens":1,"total_tokens":13}}}}',
                '{"timestamp":"2026-07-14T10:00:03Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"encrypted-turn","completed_at":"2026-07-14T10:00:03Z","duration_ms":3000}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    run = module.build_codex_rollout_run("encrypted-thread", tmp_path)
    activity = run.threads[0].activities[0]
    html = module.render_codex_rollout_html(run)

    assert activity.activity_type == "reasoning"
    assert activity.model == "gpt-5.6-sol"
    assert activity.content == ""
    assert "Encrypted reasoning" in activity.summary
    assert "plaintext unavailable" in html
    assert "CIPHER-TEXT-MUST-NOT-APPEAR" not in html


def test_native_codex_html_embeds_execution_drilldown_in_agent_rows():
    module = _load_module()
    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)

    html = module.render_codex_rollout_html(run)

    assert "Token composition" in html
    assert "Execution timeline" not in html
    assert "Work units and attribution" not in html
    assert "Phase and lane aggregates" not in html
    assert "Bars share a common run-wide time axis" in html
    assert "Turn activity" in html
    assert 'class="token-composition"' in html
    assert ".cached { background:var(--token-cached); }" in html
    assert ".reasoning { background:var(--token-reasoning); }" in html
    assert ".composition-cached { color:var(--token-cached); }" in html
    assert ".composition-reasoning { color:var(--token-reasoning); }" in html
    composition_legend = html.split('<div class="composition-legend">', 1)[1].split(
        "</div>", 1
    )[0]
    assert 'class="composition-fresh">Fresh input' in composition_legend
    assert 'class="composition-cached">Cache read' in composition_legend
    assert composition_legend.index("Fresh input") < composition_legend.index("Cache read")
    assert 'class="composition-cache-write"' not in composition_legend
    assert html.count('class="composition-output">') == 1
    assert html.count('class="composition-reasoning">') == 1
    assert 'class="composition-output">output 112</span>' in html
    assert 'class="composition-reasoning">reasoning 38</span>' in html
    assert 'class="token-segment output" style="width:14.000%"' in html
    assert 'class="token-segment reasoning" style="width:4.750%"' in html
    assert 'class="agent-summary-row"' in html
    assert 'class="agent-expanded-row" hidden' in html
    assert 'class="agent-row-toggle" aria-expanded="false"' in html
    assert (
        ".turn-table .turn-timeline-header, .turn-table .turn-timeline-cell "
        "{ width:25%; min-width:220px; }" in html
    )
    assert (
        ".agent-expanded-row .table-scroll { max-height:none; margin:0 -13px; }"
        in html
    )
    assert '.agent-row-toggle-icon::before { content:"+"; }' in html
    assert "document.querySelectorAll(\".agent-summary-row\")" in html
    assert 'href="#execution-timeline"' not in html
    assert 'href="#timeline"' in html
    assert "root-turn-1" in html
    assert "T+0s" in html
    assert "500ms" in html
    assert "exec × 1" in html
    assert "Cached input is part of input" not in html
    assert "Reasoning is part of output" not in html
    assert "% of input" not in html
    root_turn_table = html.split('<table class="turn-table"', 1)[1].split("</table>", 1)[0]
    assert "<th>Work unit</th>" in root_turn_table
    assert "<th>Activity</th>" in root_turn_table
    assert "<th>TTFT</th>" not in root_turn_table
    assert "<td>500ms</td>" not in root_turn_table
    assert "<th>Processed</th>" not in root_turn_table
    assert "<th>Tools</th>" not in root_turn_table
    assert "<th>State</th>" not in root_turn_table
    assert "<th>Duration</th>" not in root_turn_table
    assert "<th>Cost est.</th>" not in root_turn_table
    assert (
        '<code>root-turn-1</code></a> '
        '<span class="state state-complete">complete</span>'
        in root_turn_table
    )
    assert "<th>Input</th>" not in root_turn_table
    assert "<th>Cache write</th>" not in root_turn_table
    assert (
        '<th>Turns<br><span class="column-detail">(Tools/MCP)</span></th>'
        '<th>Agent time<br><span class="column-detail">(Cost)</span></th>'
        in root_turn_table
    )
    assert (
        '<td class="turn-activity-cell"><span class="cell-primary">1</span>'
        '<span class="cell-secondary">(1/0)</span></td>'
        '<td class="turn-time-cell"><span class="cell-primary">4s</span>'
        '<span class="cell-secondary">($0.00)</span></td>'
        in root_turn_table
    )
    assert "<th>Fresh Input</th><th>Cache read</th><th>Output</th>" in root_turn_table
    assert "<td>60</td><td>40</td><td>20</td><td>5</td>" in root_turn_table
    assert '<th>Reasoning</th><th class="turn-timeline-header">Timeline</th>' in root_turn_table
    assert (
        'class="timeline-bar turn-timeline-bar" '
        'style="left:0.000%;width:22.222%"' in root_turn_table
    )
    assert (
        'class="timeline-bar turn-timeline-bar" '
        'style="left:88.889%;width:11.111%"' in root_turn_table
    )
    model_usage = html.split('<section id="model-usage"', 1)[1].split(
        '<div id="timeline"', 1
    )[0]
    assert (
        "<th>Agent</th><th>Fresh Input</th><th>Cache read</th><th>Output</th>"
        in model_usage
    )
    assert "<th>Input</th>" not in model_usage
    assert "<th>Cache write</th>" not in model_usage
    assert "Codex telemetry does not report cache-write tokens" in model_usage
    root_overlay = html.split('id="turn-tool-call-list-1-1"', 1)[1].split(
        "</section>", 1
    )[0]
    assert "60 fresh-input · 40 cache-read" in root_overlay
    assert "cache-write</div>" not in root_overlay
    root_tool_overlay = html.split('id="turn-tool-call-list-1"', 1)[1].split(
        "</section>", 1
    )[0]
    assert "<th>State</th>" in root_tool_overlay


def test_native_codex_report_uses_first_genuine_request_as_title():
    module = _load_module()
    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)

    html = module.render_codex_rollout_html(run)
    markdown = module.render_codex_rollout_markdown(run)

    assert run.run_label == '"Inspect the project" Agent Report'
    assert '<title>"Inspect the project" Agent Report</title>' in html
    assert '<h1>"Inspect the project" Agent Report</h1>' in html
    assert markdown.startswith('# "Inspect the project" Agent Report\n')
    assert "Codex Rollout Metrics" not in html
    assert "Codex Rollout Metrics" not in markdown


def test_native_codex_html_compacts_long_page_title_and_discloses_table_titles():
    module = _load_module()
    long_title = (
        "Investigate every recorded agent interaction across the complete execution "
        "archive and explain every relevant implementation decision before producing "
        "the final verified report"
    )
    run = module.build_codex_rollout_run(
        "root-thread",
        CODEX_ROLLOUT_FIXTURES,
        title=long_title,
    )
    root = next(thread for thread in run.threads if thread.thread_id == run.root_thread_id)
    root.task_title = long_title

    html = module.render_codex_rollout_html(run)
    full_report_title = f'"{long_title}" Agent Report'
    compact_report_title = module._compact_report_title(full_report_title)
    compact_agent_label = module._compact_agent_assignment_label(root)
    agent_table = html.split('<table class="agent-table">', 1)[1].split(
        "</table>", 1
    )[0]

    assert compact_report_title != full_report_title
    assert f"<title>{compact_report_title}</title>" in html
    assert (
        f'<h1 title="&quot;{long_title}&quot; Agent Report">'
        f"{compact_report_title}</h1>"
    ) in html
    assert '<details class="clamped-disclosure agent-title-disclosure">' in agent_table
    assert f'<span class="clamped-preview"><strong>{compact_agent_label}</strong></span>' in agent_table
    assert '<span class="clamped-toggle clamped-more">more</span>' in agent_table
    assert f'<div class="clamped-full"><strong>Thread: {long_title} · Agent: main</strong>' in agent_table
    assert full_report_title not in compact_report_title


@pytest.mark.parametrize(
    ("task_title", "expected"),
    [
        ("Create Quarkus Skills", '"Create Quarkus Skills" Agent Report'),
        ('"Create Quarkus Skills"', '"Create Quarkus Skills" Agent Report'),
        ("Create Quarkus Skills agent report", '"Create Quarkus Skills" Agent Report'),
        ('"Create Quarkus Skills" Agent Report', '"Create Quarkus Skills" Agent Report'),
        ("Agent Report", ""),
    ],
)
def test_report_title_uses_canonical_agent_report_form(task_title, expected):
    module = _load_module()

    assert module._report_title(task_title) == expected


def test_catalog_title_unwraps_delegation_envelope():
    module = _load_module()

    title = module._catalog_task_title(
        "<codex_delegation>"
        "<source_thread_id>parent-thread</source_thread_id>"
        "<input>Fix delegated report traversal.</input>"
        "</codex_delegation>"
    )

    assert title == "Fix delegated report traversal"


def test_native_codex_report_skips_host_context_when_deriving_title(tmp_path):
    module = _load_module()
    rollout = tmp_path / "host-context.jsonl"
    rollout.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-07-16T22:00:00Z","type":"session_meta","payload":{"id":"host-context-thread","source":"user"}}',
                '{"timestamp":"2026-07-16T22:00:01Z","type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"<recommended_plugins>\\nInjected catalog\\n</recommended_plugins>"},{"type":"input_text","text":"# AGENTS.md instructions for /work/project\\n\\n<INSTRUCTIONS>Injected</INSTRUCTIONS>"},{"type":"input_text","text":"<environment_context>Injected</environment_context>"}]}}',
                '{"timestamp":"2026-07-16T22:00:02Z","type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"<in-app-browser-context source=\\"ambient-ui-state\\">Injected</in-app-browser-context>\\n\\n## My request for Codex:\\nCreate Quarkus skills."}]}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    run = module.build_codex_rollout_run("host-context-thread", tmp_path)

    assert run.run_label == '"Create Quarkus skills" Agent Report'


def test_native_codex_report_prefers_explicit_title_over_derived_request():
    module = _load_module()

    run = module.build_codex_rollout_run(
        "root-thread",
        CODEX_ROLLOUT_FIXTURES,
        title="Stored task title",
    )

    assert run.run_label == '"Stored task title" Agent Report'
    html = module.render_codex_rollout_html(run)
    assert '<title>"Stored task title" Agent Report</title>' in html
    assert '<h1>"Stored task title" Agent Report</h1>' in html


def test_native_codex_report_prefers_recorded_metadata_title(tmp_path):
    module = _load_module()
    rollout = tmp_path / "recorded-title.jsonl"
    rollout.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-07-16T22:00:00Z","type":"session_meta","payload":{"id":"recorded-title-thread","thread_title":"Recorded task title","source":"user"}}',
                '{"timestamp":"2026-07-16T22:00:01Z","type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"Create a different fallback title."}]}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    run = module.build_codex_rollout_run("recorded-title-thread", tmp_path)

    assert run.run_label == '"Recorded task title" Agent Report'
    explicit = module.build_codex_rollout_run(
        "recorded-title-thread",
        tmp_path,
        title="Catalog task title",
    )
    assert explicit.run_label == '"Catalog task title" Agent Report'


def test_native_codex_html_links_to_privacy_safe_agent_and_turn_drilldowns():
    module = _load_module()
    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)

    html = module.render_codex_rollout_html(run)

    assert html.count('class="tool-call-overlay agent-tool-call-overlay"') == 3
    assert html.count('class="tool-call-overlay turn-detail-overlay"') == 4
    assert 'href="#turn-tool-call-list-1"' not in html
    assert 'href="#turn-tool-call-list-2"' not in html
    assert 'href="#turn-tool-call-list-3"' not in html
    assert "View turns and tool calls" not in html
    assert html.count('href="#turn-tool-call-list-1-1"') == 2
    assert "root — turns and tool calls" in html
    assert "module-a — turns and tool calls" in html
    assert "reviewer — turns and tool calls" in html
    assert "root — Turn root-turn-1" in html
    assert "All turns and tool calls" not in html
    tool_overlays = html.split('<section id="turn-tool-call-list-1"', 1)[1]
    assert "<th>Agent</th>" not in tool_overlays
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
    assert 'href="#timeline">close</a>' in root_turn_overlay
    assert 'href="#turn-tool-call-list-1"' not in root_turn_overlay
    assert '<div class="label">Start T+</div>' in root_turn_overlay
    assert '<div class="label">T+</div>' not in root_turn_overlay
    assert '<div class="metric turn-tools-metric"><div class="label">Tools used</div>' in root_turn_overlay
    assert '<div class="label">Tools used</div><div class="value">exec × 1</div>' in root_turn_overlay
    assert '<span class="metric-detail">1 call · 500ms</span>' in root_turn_overlay
    assert '<div class="label">Tool calls</div>' not in root_turn_overlay
    assert '<div class="label">Skills used</div>' not in root_turn_overlay
    assert (
        ".tool-call-panel { display:flex; flex-direction:column; "
        "box-sizing:border-box;"
    ) in html
    assert (
        ".tool-call-panel .table-scroll { flex:1 1 auto; min-height:0; "
        "max-height:none; }"
    ) in html
    assert ".turn-detail-panel .table-scroll" not in html
    assert "Time to first token" not in root_turn_overlay
    assert "Processed tokens" in root_turn_overlay
    assert (
        ".turn-detail-metrics { grid-template-columns:repeat(6,minmax(0,1fr)); }"
        in html
    )
    assert "turn-skills-metric" not in html
    assert ".turn-tools-metric { grid-column:span 6; }" in html
    assert "Arguments are compact, secret-redacted summaries" not in root_turn_overlay
    assert '<p class="execution-note">' not in root_turn_overlay
    tool_table = root_turn_overlay.split('<div class="table-scroll">', 1)[1].split(
        "</table>", 1
    )[0]
    assert '<table class="turn-detail-table">' in tool_table
    assert '<col class="turn-detail-arguments-column">' in tool_table
    assert '<col class="turn-detail-cost-column">' in tool_table
    assert '<col class="turn-detail-model-column">' in tool_table
    assert '<col class="turn-detail-result-column">' in tool_table
    assert 'turn-detail-timing-column' not in tool_table
    assert "<th>T+</th>" in tool_table
    assert '>Cost</th>' in tool_table
    assert '<th>Model</th><th>Activity</th>' in tool_table
    assert "Cost to T+" not in tool_table
    assert "<th>Duration</th>" not in tool_table
    assert "<th>Arguments</th>" in tool_table
    assert "<th>Result</th>" in tool_table
    assert "<th>Confidence</th>" not in tool_table
    assert "<th>Timing note</th>" not in tool_table
    assert '<tr class="turn-detail-tool-row"><td>1</td><td>T+3s</td>' in tool_table
    assert "API_TOKEN=[redacted] python app.py</code></td>" in tool_table
    assert "[20 chars]" in tool_table
    assert "tool-reported duration available" not in tool_table
    assert '<code>root-turn-1</code>' in html
    assert "PRIVATE-TOOL-PAYLOAD" not in html

    assert "MCP-recorded execution time" not in tool_table


def test_turn_modal_suppresses_empty_delegated_continuations_but_keeps_followups():
    module = _load_module()
    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)
    root = run.threads[0]
    turn_id = root.turns[0].turn_id
    empty_envelope = (
        "Message Type: MESSAGE\n"
        "Task name: /root/child\n"
        "Sender: /root\n"
        "Payload:\n"
    )
    followup_envelope = empty_envelope + "Continue with verification."
    next_ordinal = max(activity.source_ordinal for activity in root.activities) + 1
    for index in range(5):
        root.activities.append(
            module.AgentActivity(
                thread_id=root.thread_id,
                turn_id=turn_id,
                activity_type="input",
                event_timestamp=root.turns[0].started_at,
                source_path=root.source_path,
                source_ordinal=next_ordinal + index,
                summary="Delegated input from parent · 137 characters",
                content=empty_envelope,
            )
        )
    root.activities.append(
        module.AgentActivity(
            thread_id=root.thread_id,
            turn_id=turn_id,
            activity_type="input",
            event_timestamp=root.turns[0].started_at,
            source_path=root.source_path,
            source_ordinal=next_ordinal + 5,
            summary="Delegated input from parent · 164 characters",
            content=followup_envelope,
        )
    )

    assert module.codex_run_to_json(run).count(
        "Delegated input from parent · 137 characters"
    ) == 5
    html = module.render_codex_rollout_html(run)
    overlay = html.split('id="turn-tool-call-list-1-1"', 1)[1].split(
        "</section>", 1
    )[0]
    input_row = overlay.split(
        '<tr class="turn-detail-lifecycle-row turn-detail-input-row">', 1
    )[1].split("</tr>", 1)[0]

    assert "Delegated input from parent · 137 characters" not in input_row
    assert "Delegated input from parent · 164 characters" in input_row
    assert "Continue with verification." in input_row


def test_native_codex_turn_table_hides_constant_work_unit_and_empty_activity(tmp_path):
    module = _load_module()
    rollout = tmp_path / "constant-metadata.jsonl"
    rollout.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-07-14T12:00:00Z","type":"session_meta","payload":{"id":"reviewer-thread","agent_role":"wiki-topic-verifier","source":{"subagent":{"thread_spawn":{"parent_thread_id":"outside","agent_path":"/root/reviewer","agent_nickname":"Review","agent_role":"wiki-topic-verifier"}}}}}',
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
    assert run.threads[0].thread_name == "reviewer"
    assert run.threads[0].agent_role == "wiki-topic-verifier"

    html = module.render_codex_rollout_html(run)
    turn_table = html.split('<table class="turn-table"', 1)[1].split("</table>", 1)[0]

    assert "<th>Work unit</th>" not in turn_table
    assert "<th>Activity</th>" not in turn_table
    assert '<div class="thread-meta">' not in html
    assert "Work unit reviewer for all turns" not in html
    assert "Activity not recorded" not in html


def test_native_codex_agent_timeline_draws_separate_turn_segments(tmp_path):
    module = _load_module()
    rollout = tmp_path / "turn-gaps.jsonl"
    rollout.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-07-14T12:00:00Z","type":"session_meta","payload":{"id":"root-thread"}}',
                '{"timestamp":"2026-07-14T12:00:00Z","type":"event_msg","payload":{"type":"task_started","turn_id":"one","started_at":"2026-07-14T12:00:00Z"}}',
                '{"timestamp":"2026-07-14T12:00:02Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"one","completed_at":"2026-07-14T12:00:02Z","duration_ms":2000}}',
                '{"timestamp":"2026-07-14T12:00:10Z","type":"event_msg","payload":{"type":"task_started","turn_id":"two","started_at":"2026-07-14T12:00:10Z"}}',
                '{"timestamp":"2026-07-14T12:00:12Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"two","completed_at":"2026-07-14T12:00:12Z","duration_ms":2000}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    run = module.build_codex_rollout_run("root-thread", tmp_path)

    html = module.render_codex_rollout_html(run)
    agent_row = html.split('<tr class="agent-summary-row"', 1)[1].split("</tr>", 1)[0]

    assert agent_row.count('class="timeline-bar agent-timeline-bar"') == 2
    for turn in run.threads[0].turns:
        assert (
            'class="timeline-bar agent-timeline-bar" '
            f'style="{module._timeline_style(run, turn.started_at, turn.completed_at)}"'
            in agent_row
        )


def test_native_codex_html_identifies_agents_and_runtime_nicknames():
    module = _load_module()
    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)
    next(thread for thread in run.threads if thread.thread_id == "child-thread").agent_role = (
        "dev-coder"
    )
    next(thread for thread in run.threads if thread.thread_id == "nested-thread").agent_role = (
        "dev-code-reviewer"
    )
    run.threads = [run.threads[2], run.threads[0], run.threads[1]]

    html = module.render_codex_rollout_html(run)

    assert '<div class="label">Agents used</div>' in html
    assert '<div id="timeline" class="agents-heading"><h2>Timeline</h2>' in html
    assert '<div class="label">Summed agent time</div>' not in html
    assert '<div class="label">Active interval union</div>' not in html
    assert '<summary aria-label="About Timeline">ⓘ</summary>' in html
    assert '<div class="agent-note-popover" role="note">' in html
    assert "Assignment" in html
    assert "<th>Runtime nickname</th>" not in html
    assert (
        "<strong>Thread: module-a · Agent: dev-coder (module-a)</strong>" in html
    )
    assert (
        "<strong>Thread: reviewer · Agent: dev-code-reviewer (reviewer)</strong>"
        in html
    )
    assert "Nested rows are indented under their parent assignment" in html
    assert "Each identity separates the thread name, resolved agent type" in html
    assert "default is Codex's built-in role when a spawn omits agent_type" in html
    agent_table = html.split('<table class="agent-table">', 1)[1].split("</table>", 1)[0]
    agent_header = agent_table.split("</thead>", 1)[0]
    assert "<th>Parent assignment</th>" not in agent_header
    assert "<th>State</th>" not in agent_header
    assert "<th>Skills used</th>" in agent_header
    assert '<th>Turns<br><span class="column-detail">(Tools/MCP)</span></th>' in agent_header
    assert '<th>Agent time<br><span class="column-detail">(Cost)</span></th>' in agent_header
    assert "<th>Model</th>" not in agent_header
    assert "<th>Tools</th>" not in agent_header
    assert "<th>Run share</th>" not in agent_header
    assert "<th>Subagents invoked</th>" not in agent_header
    assert '<col class="agent-skills-column">' in agent_table
    assert '<col class="agent-timeline-column">' in agent_table
    assert ".agent-table { table-layout:fixed; min-width:1200px; }" in html
    assert ".agent-table .agent-assignment-column { width:30%; }" in html
    assert ".agent-table .agent-skills-column { width:15%; }" in html
    assert ".agent-table .agent-timeline-column { width:25%; }" in html
    assert ".agent-table .agent-skills-cell { font-size:.7em; }" in html
    assert (
        ".agent-assignment-heading { display:flex; align-items:center; gap:8px; "
        "flex-wrap:wrap; }"
    ) in html
    assert ".agent-model-metadata { white-space:nowrap; }" in html
    assert (
        ".agent-assignment-heading { display:flex; align-items:flex-start; "
        "justify-content:space-between; gap:8px; }"
    ) not in html
    assert "agent-subagents-column" not in html
    assert ".agent-table td { vertical-align:top; }" in html
    assert (
        ".agent-assignment-cell { --agent-indent:calc(var(--agent-depth) * 20px); "
        "padding-left:calc(7px + var(--agent-indent)); background:linear-gradient(to right,#0d47a1 0 var(--agent-indent),transparent var(--agent-indent)); }"
    ) in html
    agent_rows = [
        '<tr class="agent-summary-row"' + fragment.split("</tr>", 1)[0]
        for fragment in html.split('<tr class="agent-summary-row"')[1:]
    ]
    assert len(agent_rows) == 3
    assert 'class="agent-assignment-cell" data-depth="0" style="--agent-depth:0"' in agent_rows[0]
    assert '<span class="visually-hidden">Top-level assignment.</span>' in agent_rows[0]
    assert '<strong>Thread: root · Agent: main</strong>' in agent_rows[0]
    assert (
        '<div class="agent-assignment-heading"><strong>Thread: root · Agent: main</strong>'
        '<span class="state state-complete">complete</span>'
        '<span class="agent-model-metadata">'
        '<code class="model-name">gpt-5.4-mini</code></span></div>'
        in agent_rows[0]
    )
    assert '</div><code class="model-name">' not in agent_rows[0]
    assert "/root" not in agent_rows[0]
    assert '<td class="agent-skills-cell">careful-coding · python</td>' in agent_rows[0]
    assert '<span class="cell-secondary">(1/0)</span>' in agent_rows[0]
    assert '<span class="cell-secondary">(22.5%)</span>' in agent_rows[0]
    assert sum(
        row.count('class="timeline-bar agent-timeline-bar"') for row in agent_rows
    ) == sum(len(thread.turns) or 1 for thread in run.threads)
    for thread in run.threads:
        intervals = [
            (turn.started_at, turn.completed_at or thread.last_observed_at)
            for turn in thread.turns
            if turn.started_at
        ] or [(thread.started_at, thread.last_observed_at)]
        for started_at, ended_at in intervals:
            style = module._timeline_style(run, started_at, ended_at)
            assert (
                'class="timeline-bar agent-timeline-bar" '
                f'style="{style}"' in html
            )
    assert 'class="agent-assignment-cell" data-depth="1" style="--agent-depth:1"' in agent_rows[1]
    assert '<span class="visually-hidden">Nested assignment, depth 1.</span>' in agent_rows[1]
    assert (
        '<strong>Thread: module-a · Agent: dev-coder (module-a)</strong>'
        in agent_rows[1]
    )
    assert 'class="agent-assignment-cell" data-depth="2" style="--agent-depth:2"' in agent_rows[2]
    assert '<span class="visually-hidden">Nested assignment, depth 2.</span>' in agent_rows[2]
    assert (
        '<strong>Thread: reviewer · Agent: dev-code-reviewer (reviewer)</strong>'
        in agent_rows[2]
    )


def test_agent_identity_does_not_substitute_nickname_for_missing_thread_name():
    module = _load_module()
    thread = module.CodexThreadMetrics(
        thread_id="role-backed-child",
        parent_thread_id="root",
        agent_role="wiki-topic-verifier",
        agent_nickname="Aristotle",
    )

    assert module._agent_assignment_label(thread) == (
        "Thread: — · Agent: wiki-topic-verifier (Aristotle)"
    )


def test_agent_identity_resolves_implicit_codex_agent_types():
    module = _load_module()

    root = module.CodexThreadMetrics(thread_id="root", thread_name="root")
    child = module.CodexThreadMetrics(
        thread_id="child",
        parent_thread_id="root",
        thread_name="implementation_review",
        agent_nickname="Franklin",
    )

    assert module._agent_assignment_label(root) == "Thread: root · Agent: main"
    assert module._agent_assignment_label(child) == (
        "Thread: implementation_review · Agent: default (Franklin)"
    )


def test_native_codex_html_clamps_long_agent_skill_lists_with_disclosure():
    module = _load_module()
    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)
    root = next(thread for thread in run.threads if thread.thread_id == run.root_thread_id)
    root.skills_used = [f"skill-{index}" for index in range(1, 7)]

    html = module.render_codex_rollout_html(run)
    agent_table = html.split('<table class="agent-table">', 1)[1].split(
        "</table>", 1
    )[0]

    assert '<details class="clamped-disclosure agent-skills-disclosure">' in agent_table
    assert (
        '<span class="clamped-preview">skill-1 · skill-2 · skill-3 · '
        "skill-4 · skill-5 · skill-6</span>"
    ) in agent_table
    assert '<span class="clamped-toggle clamped-more">more</span>' in agent_table
    assert (
        '<div class="clamped-full">skill-1 · skill-2 · skill-3 · skill-4 · '
        'skill-5 · skill-6<button type="button" '
        'class="clamped-toggle clamped-less">less</button></div>'
    ) in agent_table
    assert '<span class="clamped-toggle clamped-less">' not in agent_table
    assert (
        ".clamped-preview { display:-webkit-box; -webkit-box-orient:vertical; "
        "-webkit-line-clamp:5; overflow:hidden; }"
    ) in html
    assert ".clamped-disclosure[open] > summary { display:none; }" in html
    assert 'document.querySelectorAll(".clamped-less")' in html


def test_compact_count_uses_thousands_and_millions():
    module = _load_module()

    assert module._format_compact_count(999) == "999"
    assert module._format_compact_count(1_000) == "1.0K"
    assert module._format_compact_count(12_345) == "12.3K"
    assert module._format_compact_count(1_000_000) == "1.0M"
    assert module._format_compact_count(12_345_678) == "12.3M"
    assert module._format_compact_count(1_234_567_890) == "1,234.6M"


def test_native_codex_markdown_includes_turn_and_tool_breakdown():
    module = _load_module()
    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)
    next(thread for thread in run.threads if thread.thread_id == "child-thread").agent_role = (
        "dev-coder"
    )
    next(thread for thread in run.threads if thread.thread_id == "nested-thread").agent_role = (
        "dev-code-reviewer"
    )

    markdown = module.render_codex_rollout_markdown(run)

    assert "- Turns: 4" in markdown
    assert "- Matched tool calls: 1" in markdown
    assert (
        "| Assignment | Skills used | "
        "Turns | Tools | Agent time |" in markdown
    )
    assert (
        "| Assignment | Skills used | Turns | Tools | Agent time | Fresh Input | "
        "Cache read | Output | Reasoning | Processed |"
        in markdown
    )
    assert "| Input |" not in markdown
    assert "| Cache write |" not in markdown
    assert "Codex telemetry does not report cache-write tokens" in markdown
    assert "Subagents invoked" not in markdown
    assert "Parent assignment" not in markdown
    assert "| Thread: root · Agent: main | careful-coding · python | 2 |" in markdown
    assert (
        "| ↳ Thread: module-a · Agent: dev-coder (module-a) | — | 1 |"
        in markdown
    )
    assert (
        "| ↳ ↳ Thread: reviewer · Agent: dev-code-reviewer (reviewer) | — | 1 |"
        in markdown
    )
    assert "| Work unit |" not in markdown
    assert "| Phase | Lane | Work units |" not in markdown
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
                '{"timestamp":"2026-07-14T02:00:00Z","type":"turn_context","payload":{"model":"internal-subscription-model","effort":"high","turn_id":"u1"}}',
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
    assert run.threads[0].effort == "high"
    assert run.threads[0].responses[0].effort == "high"

    html = module.render_codex_rollout_html(run)
    agent_table = html.split('<table class="agent-table">', 1)[1].split(
        "</table>", 1
    )[0]
    assert (
        '<span class="state state-complete">complete</span>'
        '<span class="agent-model-metadata">'
        '<code class="model-name">internal-subscription-model</code> · '
        '<span class="effort-level">effort high</span></span>'
        in agent_table
    )
    model_usage = html.split('<section id="model-usage"', 1)[1].split(
        '<div id="timeline"', 1
    )[0]
    assert '<span class="model-effort">effort high</span>' in model_usage


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
    assert cost.method == "API-equivalent token-price estimate; not an actual charge"


def test_native_codex_cost_display_is_compact_and_rounded():
    module = _load_module()
    cost = module.CostAssessment(
        status="estimated",
        total_cost=1.330343,
    )
    recorded_cost = module.CostAssessment(
        status="recorded",
        total_cost=1.330343,
    )

    assert module._cost_summary(cost) == (
        "API-equivalent estimate: $1.33 USD "
        "(estimate, not an actual charge or invoice)"
    )
    assert module._compact_cost_summary(cost) == "$1.33"
    assert module._compact_cost_summary(recorded_cost) == "$1.33"

    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)
    run.cost = module.CostAssessment(status="estimated", total_cost=917.35)
    run.observed_at = "2026-07-16T22:15:00+00:00"
    html = module.render_codex_rollout_html(run)
    assert (
        "· observed 2026-07-16T22:15:00+00:00 · "
        "API-equivalent estimate: $917.35 USD "
        "(estimate, not an actual charge or invoice).</p>"
    ) in html
    assert html.count("not an actual charge or invoice") == 1
    assert '<p class="notice">' not in html
    assert "<h2>Diagnostics</h2>" not in html
    assert "not an actual Codex charge or invoice" not in html
    assert "Critical path:" not in html
    assert "<th>Cost estimate</th>" in html
    assert "Codex rate-card estimate" not in html
    assert "credits" not in html.lower()
    markdown = module.render_codex_rollout_markdown(run)
    assert "credits" not in markdown.lower()


def test_native_codex_agent_details_use_agent_model_for_turn_and_agent_costs():
    module = _load_module()
    run = module.build_codex_rollout_run("root-thread", CODEX_ROLLOUT_FIXTURES)
    root = run.threads[0]
    root.model = "gpt-5.6-sol"
    for response in root.responses:
        response.model = root.model
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

    agent_table = html.split('<table class="agent-table">', 1)[1].split(
        "</table>", 1
    )[0]
    assert '<span class="cell-secondary">($40.50)</span>' in agent_table
    root_detail = html.split(
        'id="agent-detail-1" class="agent-expanded-row" hidden', 1
    )[1].split('data-agent-detail="agent-detail-2"', 1)[0]
    assert (
        '<th>Agent time<br><span class="column-detail">(Cost)</span></th>'
        in root_detail
    )
    assert "<th>Cost est.</th>" not in root_detail
    assert '<span class="cell-secondary">($35.50)</span>' in root_detail
    assert '<span class="cell-secondary">($5.00)</span>' in root_detail
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

    normal_flow_before_agents = html.split("<body>", 1)[1].split(
        '<div id="timeline" class="agents-heading"><h2>Timeline</h2>', 1
    )[0]
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
            "--title",
            "Stored task title",
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
    html = html_path.read_text(encoding="utf-8")
    assert "API-equivalent estimate" in html
    assert '<title>"Stored task title" Agent Report</title>' in html
    assert '<h1>"Stored task title" Agent Report</h1>' in html


def test_main_catalogs_filtered_codex_roots_without_generating_reports(tmp_path):
    module = _load_module()
    active_root = tmp_path / "sessions"
    archive_root = tmp_path / "archived_sessions"
    _write_codex_catalog_rollout(
        active_root,
        thread_id="quarkus-root",
        timestamp="2026-07-14T12:00:00Z",
        request="Create Quarkus skills.",
        workspace="/work/agent-runner",
    )
    _write_codex_catalog_rollout(
        active_root,
        thread_id="quarkus-child",
        parent_thread_id="quarkus-root",
        timestamp="2026-07-14T12:00:01Z",
        request="Review the implementation.",
        workspace="/work/agent-runner",
    )
    _write_codex_catalog_rollout(
        archive_root,
        thread_id="docs-root",
        timestamp="2026-07-15T12:00:00Z",
        request="Review the documentation.",
        workspace="/work/agent-runner",
    )
    _write_codex_catalog_rollout(
        archive_root,
        thread_id="old-root",
        timestamp="2026-07-13T23:59:59Z",
        request="Create Quarkus skills from old logs.",
        workspace="/work/agent-runner",
    )
    output = tmp_path / "catalog" / "index.html"

    rc = module.main(
        [
            "--codex-catalog",
            "--catalog-root",
            str(active_root),
            "--catalog-root",
            str(archive_root),
            "--from-date",
            "2026-07-14",
            "--to-date",
            "2026-07-15",
            "--title-contains",
            "quarkus",
            "--workspace-contains",
            "agent-runner",
            "--output",
            str(output),
        ]
    )

    assert rc == 0
    html = output.read_text(encoding="utf-8")
    assert "Available Codex Agent Reports" in html
    assert "quarkus-root" in html
    assert "Create Quarkus skills" in html
    assert "quarkus-child" not in html
    assert "docs-root" not in html
    assert "old-root" not in html
    assert not (output.parent / "reports").exists()


def test_main_codex_catalog_prefers_codex_app_task_title(tmp_path, monkeypatch):
    module = _load_module()
    sessions_root = tmp_path / "sessions"
    _write_codex_catalog_rollout(
        sessions_root,
        thread_id="renamed-root",
        timestamp="2026-07-14T12:00:00Z",
        request="This first prompt should only be a fallback.",
        workspace="/work/agent-runner",
    )
    state_path = tmp_path / ".codex" / "state_5.sqlite"
    state_path.parent.mkdir()
    connection = module.sqlite3.connect(state_path)
    try:
        connection.execute(
            "CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO threads (id, title) VALUES (?, ?)",
            ("renamed-root", "Use task titles in reports"),
        )
        connection.commit()
    finally:
        connection.close()
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: tmp_path))
    output = tmp_path / "catalog.html"

    rc = module.main(
        [
            "--codex-catalog",
            "--catalog-root",
            str(sessions_root),
            "--title-contains",
            "task titles",
            "--output",
            str(output),
        ]
    )

    assert rc == 0
    html = output.read_text(encoding="utf-8")
    assert "Use task titles in reports" in html
    assert "This first prompt should only be a fallback" not in html


def test_catalog_hour_boundaries_are_inclusive():
    module = _load_module()
    entries = [
        module._AgentCatalogEntry(
            run_id=run_id,
            parent_thread_id="",
            started_at=datetime.fromisoformat(timestamp),
            task_title=run_id,
            workspace="",
            source_path=Path(f"/logs/{run_id}.jsonl"),
            source_store="sessions",
        )
        for run_id, timestamp in (
            ("before", "2026-07-14T11:59:59+00:00"),
            ("inside", "2026-07-14T12:59:59+00:00"),
            ("after", "2026-07-14T13:00:00+00:00"),
        )
    ]

    selected = module._select_catalog_entries(
        entries,
        from_date="2026-07-14T12",
        to_date="2026-07-14T12",
    )

    assert [entry.run_id for entry in selected] == ["inside"]


def test_main_catalog_generates_reports_with_two_way_links(tmp_path):
    module = _load_module()
    active_root = tmp_path / "sessions"
    archive_root = tmp_path / "archived_sessions"
    _write_codex_catalog_rollout(
        active_root,
        thread_id="active-root",
        timestamp="2026-07-14T12:00:00Z",
        request="Build the active feature.",
        workspace="/work/active",
    )
    _write_codex_catalog_rollout(
        archive_root,
        thread_id="archived-root",
        timestamp="2026-07-15T12:00:00Z",
        request="Build the archived feature.",
        workspace="/work/archive",
    )
    output = tmp_path / "catalog" / "index.html"

    rc = module.main(
        [
            "--codex-catalog",
            "--catalog-root",
            str(active_root),
            "--catalog-root",
            str(archive_root),
            "--from-date",
            "2026-07-14",
            "--to-date",
            "2026-07-15",
            "--generate-batch",
            "--output",
            str(output),
        ]
    )

    assert rc == 0
    catalog_html = output.read_text(encoding="utf-8")
    active_report = output.parent / "reports" / "active-root.html"
    archived_report = output.parent / "reports" / "archived-root.html"
    assert 'href="reports/active-root.html"' in catalog_html
    assert 'href="reports/archived-root.html"' in catalog_html
    assert active_report.exists()
    assert archived_report.exists()
    assert 'href="../index.html">All reports</a>' in active_report.read_text(
        encoding="utf-8"
    )
    assert 'href="../index.html">All reports</a>' in archived_report.read_text(
        encoding="utf-8"
    )


def test_main_junie_catalog_generates_reports_with_two_way_links(tmp_path):
    module = _load_module()
    sessions_root = tmp_path / "junie-sessions"
    sessions_root.mkdir()
    session = _write_junie_session(sessions_root)
    output = tmp_path / "catalog" / "junie-index.html"

    rc = module.main(
        [
            "--junie-catalog",
            "--catalog-root",
            str(sessions_root),
            "--from-date",
            "2026-07-14",
            "--to-date",
            "2026-07-14",
            "--title-contains",
            "synthetic prompt",
            "--generate-batch",
            "--output",
            str(output),
        ]
    )

    assert rc == 0
    catalog_html = output.read_text(encoding="utf-8")
    report = output.parent / "reports" / f"{session.name}.html"
    assert "Available Junie Agent Reports" in catalog_html
    assert f'href="reports/{session.name}.html"' in catalog_html
    assert report.exists()
    assert 'href="../junie-index.html">All reports</a>' in report.read_text(
        encoding="utf-8"
    )


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
    assert run.threads[0].turns[0].abort_reason == "interrupted"
    assert run.threads[0].turns[0].abort_initiator_thread_id == ""
    assert run.threads[0].turns[0].abort_initiator_agent_path == ""
    assert run.threads[0].unattributed_usage.processed_tokens == 24


def test_native_codex_records_explicit_parent_interrupt_provenance(tmp_path):
    module = _load_module()
    root = tmp_path / "root.jsonl"
    coordinator = tmp_path / "coordinator.jsonl"
    worker = tmp_path / "worker.jsonl"
    root.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-07-14T03:00:00Z","type":"session_meta","payload":{"id":"root","source":"user"}}',
                '{"timestamp":"2026-07-14T03:00:00Z","type":"event_msg","payload":{"type":"task_started","turn_id":"root-turn","started_at":"2026-07-14T03:00:00Z"}}',
                '{"timestamp":"2026-07-14T03:00:04Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"root-turn","completed_at":"2026-07-14T03:00:04Z","duration_ms":4000}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    coordinator.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-07-14T03:00:00Z","type":"session_meta","payload":{"id":"coordinator","source":{"subagent":{"thread_spawn":{"parent_thread_id":"root","agent_path":"/root/coordinator"}}}}}',
                '{"timestamp":"2026-07-14T03:00:00Z","type":"event_msg","payload":{"type":"task_started","turn_id":"coordinator-turn","started_at":"2026-07-14T03:00:00Z"}}',
                '{"timestamp":"2026-07-14T03:00:00.900Z","type":"response_item","payload":{"type":"function_call","name":"interrupt_agent","arguments":"{\\"target\\":\\"/root/coordinator/worker\\"}","call_id":"interrupt-call","internal_chat_message_metadata_passthrough":{"turn_id":"coordinator-turn"}}}',
                '{"timestamp":"2026-07-14T03:00:01.100Z","type":"response_item","payload":{"type":"function_call_output","call_id":"interrupt-call","output":"{\\"previous_status\\":\\"running\\"}","internal_chat_message_metadata_passthrough":{"turn_id":"coordinator-turn"}}}',
                '{"timestamp":"2026-07-14T03:00:03Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"coordinator-turn","completed_at":"2026-07-14T03:00:03Z","duration_ms":3000}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    worker.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-07-14T03:00:00Z","type":"session_meta","payload":{"id":"worker","source":{"subagent":{"thread_spawn":{"parent_thread_id":"coordinator","agent_path":"/root/coordinator/worker"}}}}}',
                '{"timestamp":"2026-07-14T03:00:00Z","type":"event_msg","payload":{"type":"task_started","turn_id":"worker-turn","started_at":"2026-07-14T03:00:00Z"}}',
                '{"timestamp":"2026-07-14T03:00:01Z","type":"event_msg","payload":{"type":"turn_aborted","turn_id":"worker-turn","completed_at":"2026-07-14T03:00:01Z","duration_ms":1000,"reason":"interrupted"}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    run = module.build_codex_rollout_run("root", tmp_path)
    worker_thread = next(thread for thread in run.threads if thread.thread_id == "worker")
    turn = worker_thread.turns[0]

    assert turn.abort_reason == "interrupted"
    assert turn.abort_event_timestamp == "2026-07-14T03:00:01+00:00"
    assert turn.abort_initiator_thread_id == "coordinator"
    assert turn.abort_initiator_agent_path == "/root/coordinator"
    assert turn.abort_initiator_turn_id == "coordinator-turn"
    assert turn.abort_initiator_relationship == "parent"
    assert turn.abort_request_source_path == str(coordinator.resolve())
    assert turn.abort_request_source_ordinal == 3
    assert '"abort_initiator_relationship": "parent"' in module.codex_run_to_json(run)
    assert "abort_initiator_agent_path" in module.render_codex_rollout_turn_csv(run)
    html = module.render_codex_rollout_html(run)
    worker_overlay = html.split('id="turn-tool-call-list-3-1"', 1)[1].split(
        "</section>", 1
    )[0]
    assert '<div class="label">Abort provenance</div>' not in worker_overlay
    assert (
        '<div class="metric turn-state-metric"><div class="label">State</div>'
        in worker_overlay
    )
    assert "Parent interrupt · coordinator" in worker_overlay
    assert 'title="/root/coordinator"' in worker_overlay
    assert "turn coordinator-turn · interrupted" in worker_overlay
    assert ".turn-state-detail { font-size:.66em;" in html
    assert ".turn-state-source { display:block; margin-top:2px;" in html
    assert "font-size:.58em;" in html


def test_native_codex_completed_reviewer_findings_are_failed(tmp_path):
    module = _load_module()
    rollout = tmp_path / "failed-review.jsonl"
    rollout.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-07-14T03:00:00Z","type":"session_meta","payload":{"id":"reviewer-thread","source":{"subagent":{"thread_spawn":{"parent_thread_id":"parent-thread","agent_path":"/root/setup_artifact_reviewer","agent_nickname":"Review"}}}}}',
                '{"timestamp":"2026-07-14T03:00:00Z","type":"event_msg","payload":{"type":"task_started","turn_id":"findings-turn","started_at":"2026-07-14T03:00:00Z"}}',
                '{"timestamp":"2026-07-14T03:00:01Z","type":"response_item","payload":{"type":"message","role":"assistant","phase":"final_answer","content":[{"type":"output_text","text":"1. **HIGH — Required correction remains.**"}]}}',
                '{"timestamp":"2026-07-14T03:00:02Z","type":"event_msg","payload":{"type":"turn_aborted","turn_id":"findings-turn","completed_at":"2026-07-14T03:00:02Z","duration_ms":2000,"reason":"interrupted"}}',
                '{"timestamp":"2026-07-14T03:00:03Z","type":"event_msg","payload":{"type":"task_started","turn_id":"explicit-fail-turn","started_at":"2026-07-14T03:00:03Z"}}',
                '{"timestamp":"2026-07-14T03:00:04Z","type":"response_item","payload":{"type":"message","role":"assistant","phase":"final_answer","content":[{"type":"output_text","text":"**FAIL — required corrections remain.**"}]}}',
                '{"timestamp":"2026-07-14T03:00:05Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"explicit-fail-turn","completed_at":"2026-07-14T03:00:05Z","duration_ms":2000}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    thread = module.parse_codex_rollout(rollout)

    assert [turn.outcome for turn in thread.turns] == ["failed", "failed"]
    assert thread.terminal_state == "failed"


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


def _write_codex_sequence_graph(root: Path) -> None:
    """Write linked root threads plus one native child for sequence-view tests."""

    coordinator = [
        {
            "timestamp": "2026-07-14T04:00:00Z",
            "type": "session_meta",
            "payload": {"id": "coordinator", "source": "user"},
        },
        {
            "timestamp": "2026-07-14T04:00:00Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "coordinator-turn",
                "started_at": "2026-07-14T04:00:00Z",
            },
        },
        {
            "timestamp": "2026-07-14T04:00:07Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "<codex_delegation>\n"
                            "  <source_thread_id>orchestrator</source_thread_id>\n"
                            "  <input>Return final status</input>\n"
                            "</codex_delegation>"
                        ),
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-14T04:00:10Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "coordinator-turn",
                "completed_at": "2026-07-14T04:00:10Z",
                "duration_ms": 10_000,
            },
        },
    ]
    delegation = (
        "<codex_delegation>\n"
        "  <source_thread_id>coordinator</source_thread_id>\n"
        "  <input>Start backlog item API_TOKEN=PRIVATE.\n"
        "Keep the complete recorded instruction available when the compact arrow "
        "label is truncated.\n"
        "FULL-DELEGATION-TAIL</input>\n"
        "</codex_delegation>"
    )
    orchestrator = [
        {
            "timestamp": "2026-07-14T04:00:01Z",
            "type": "session_meta",
            "payload": {"id": "orchestrator", "source": "user"},
        },
        {
            "timestamp": "2026-07-14T04:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": delegation}],
            },
        },
        {
            "timestamp": "2026-07-14T04:00:01Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "orchestrator-turn",
                "started_at": "2026-07-14T04:00:01Z",
            },
        },
        {
            "timestamp": "2026-07-14T04:00:01.900Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "I am delegating the review to a worker now.",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-14T04:00:02.900Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "I am sending the worker the review request now.",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-14T04:00:02.950Z",
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "summary": [
                    {
                        "type": "summary_text",
                        "text": (
                            "**Compare the worker branch against every requested acceptance "
                            "criterion before deciding whether to continue. "
                            "password=PRIVATE-THOUGHT-SECRET**"
                        ),
                    },
                    {
                        "type": "summary_text",
                        "text": (
                            "Trace the decision through the surrounding timeline before "
                            "sending the next instruction."
                        ),
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-14T04:00:02.975Z",
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "summary": [
                    {"type": "summary_text", "text": "Send it now."}
                ],
            },
        },
        {
            "timestamp": "2026-07-14T04:00:03.200Z",
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "encrypted_content": "opaque-reasoning-payload",
            },
        },
    ]
    collaboration_calls = [
        (
            "2026-07-14T04:00:03Z",
            "2026-07-14T04:00:03.100Z",
            "send-call",
            "send_message",
            {"target": "/root/worker", "message": "gAAAAA" + "A" * 80},
        ),
        (
            "2026-07-14T04:00:04Z",
            "2026-07-14T04:00:04.100Z",
            "followup-call",
            "followup_task",
            {"target": "worker", "message": "Continue"},
        ),
        (
            "2026-07-14T04:00:05Z",
            "2026-07-14T04:00:05.100Z",
            "interrupt-call",
            "interrupt_agent",
            {"target": "/root/worker"},
        ),
    ]
    for started_at, completed_at, call_id, tool_name, arguments in collaboration_calls:
        orchestrator.extend(
            [
                {
                    "timestamp": started_at,
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "name": tool_name,
                        "arguments": json.dumps(arguments),
                        "call_id": call_id,
                    },
                },
                {
                    "timestamp": completed_at,
                    "type": "response_item",
                    "payload": {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps({"delivered": True}),
                    },
                },
            ]
        )
    orchestrator.append(
        {
            "timestamp": "2026-07-14T04:00:07Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "orchestrator-turn",
                "completed_at": "2026-07-14T04:00:07Z",
                "duration_ms": 6_000,
            },
        }
    )
    orchestrator.append(
        {
            "timestamp": "2026-07-14T04:00:07.250Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "orchestrator-turn-2",
                "started_at": "2026-07-14T04:00:07.250Z",
            },
        }
    )
    orchestrator.append(
        {
            "timestamp": "2026-07-14T04:00:07.500Z",
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "summary": [
                    {
                        "type": "summary_text",
                        "text": (
                            "Trace the decision through the surrounding timeline before "
                            "sending the next instruction."
                        ),
                    },
                    {
                        "type": "summary_text",
                        "text": (
                            "Document why the completed coordination sequence matters "
                            "to the overall timeline."
                        ),
                    }
                ],
            },
        }
    )
    orchestrator.append(
        {
            "timestamp": "2026-07-14T04:00:08Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "orchestrator-turn-2",
                "completed_at": "2026-07-14T04:00:08Z",
                "duration_ms": 750,
            },
        }
    )
    orchestrator.extend(
        [
            {
                "timestamp": "2026-07-14T04:00:08.250Z",
                "type": "event_msg",
                "payload": {
                    "type": "task_started",
                    "turn_id": "orchestrator-turn-3",
                    "started_at": "2026-07-14T04:00:08.250Z",
                },
            },
            {
                "timestamp": "2026-07-14T04:00:08.500Z",
                "type": "response_item",
                "payload": {
                    "type": "reasoning",
                    "summary": [
                        {
                            "type": "summary_text",
                            "text": (
                                "Connect the next decision to the outcome already visible "
                                "on the agent lifeline."
                            ),
                        }
                    ],
                },
            },
            {
                "timestamp": "2026-07-14T04:00:09Z",
                "type": "event_msg",
                "payload": {
                    "type": "task_complete",
                    "turn_id": "orchestrator-turn-3",
                    "completed_at": "2026-07-14T04:00:09Z",
                    "duration_ms": 750,
                },
            },
        ]
    )
    worker = [
        {
            "timestamp": "2026-07-14T04:00:02Z",
            "type": "session_meta",
            "payload": {
                "id": "worker",
                "source": {
                    "subagent": {
                        "thread_spawn": {
                            "parent_thread_id": "orchestrator",
                            "agent_path": "/root/worker",
                            "agent_nickname": "Ada",
                        }
                    }
                },
            },
        },
        {
            "timestamp": "2026-07-14T04:00:02.100Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "worker-turn",
                "started_at": "2026-07-14T04:00:02.100Z",
            },
        },
        {
            "timestamp": "2026-07-14T04:00:03.500Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": (
                            "I received the review request and will inspect the branch."
                        ),
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-14T04:00:05.500Z",
            "type": "event_msg",
            "payload": {
                "type": "turn_aborted",
                "turn_id": "worker-turn",
                "completed_at": "2026-07-14T04:00:05.500Z",
                "duration_ms": 3_400,
                "reason": "interrupted",
            },
        },
    ]
    unrelated = [
        {
            "timestamp": "2026-07-14T04:00:00Z",
            "type": "session_meta",
            "payload": {"id": "unrelated", "source": "user"},
        }
    ]
    for filename, records in (
        ("coordinator.jsonl", coordinator),
        ("orchestrator.jsonl", orchestrator),
        ("worker.jsonl", worker),
        ("unrelated.jsonl", unrelated),
    ):
        (root / filename).write_text(
            "\n".join(json.dumps(record) for record in records) + "\n",
            encoding="utf-8",
        )


def _append_codex_delegation_record(path: Path, source_thread_id: str) -> None:
    record = {
        "timestamp": "2026-07-14T04:00:09Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "<codex_delegation>\n"
                        f"  <source_thread_id>{source_thread_id}</source_thread_id>\n"
                        "  <input>Open the linked task</input>\n"
                        "</codex_delegation>"
                    ),
                }
            ],
        },
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def test_native_codex_discovery_index_reuses_unchanged_metadata(
    tmp_path,
):
    module = _load_module()
    _write_codex_sequence_graph(tmp_path)
    index_path = tmp_path / "rollout-discovery.sqlite3"
    candidates = sorted(path.resolve() for path in tmp_path.glob("*.jsonl"))

    first_discovery = module._native_rollout_discovery(candidates, index_path)
    assert first_discovery.stats["scanned_files"] == len(candidates)
    assert first_discovery.stats["cached_files"] == 0

    first = module.build_codex_rollout_run(
        "coordinator",
        tmp_path,
        include_delegations=True,
        discovery_index_path=index_path,
    )
    assert [thread.thread_id for thread in first.threads] == [
        "coordinator",
        "orchestrator",
        "worker",
    ]
    warm_discovery = module._native_rollout_discovery(candidates, index_path)
    assert warm_discovery.stats["scanned_files"] == 0
    assert warm_discovery.stats["cached_files"] == len(candidates)
    second = module.build_codex_rollout_run(
        "coordinator",
        tmp_path,
        include_delegations=True,
        discovery_index_path=index_path,
    )
    assert [thread.thread_id for thread in second.threads] == [
        "coordinator",
        "orchestrator",
        "worker",
    ]


def test_native_codex_discovery_index_preserves_normalized_report(tmp_path):
    module = _load_module()
    _write_codex_sequence_graph(tmp_path)
    observed_at = datetime(2026, 7, 14, 4, 1, tzinfo=timezone.utc)

    uncached = module.build_codex_rollout_run(
        "coordinator",
        tmp_path,
        include_delegations=True,
        observed_at=observed_at,
    )
    indexed = module.build_codex_rollout_run(
        "coordinator",
        tmp_path,
        include_delegations=True,
        observed_at=observed_at,
        discovery_index_path=tmp_path / "rollout-discovery.sqlite3",
    )

    assert module.codex_run_to_json(indexed) == module.codex_run_to_json(uncached)


def test_native_codex_discovery_index_invalidates_appended_and_truncated_log(
    tmp_path,
):
    module = _load_module()
    _write_codex_sequence_graph(tmp_path)
    index_path = tmp_path / "rollout-discovery.sqlite3"
    unrelated_path = tmp_path / "unrelated.jsonl"
    candidates = sorted(path.resolve() for path in tmp_path.glob("*.jsonl"))
    module._native_rollout_discovery(candidates, index_path)

    _append_codex_delegation_record(unrelated_path, "coordinator")
    appended_discovery = module._native_rollout_discovery(candidates, index_path)
    assert appended_discovery.stats["scanned_files"] == 1
    assert appended_discovery.stats["cached_files"] == len(candidates) - 1
    appended = module.build_codex_rollout_run(
        "coordinator",
        tmp_path,
        include_delegations=True,
        discovery_index_path=index_path,
    )
    assert "unrelated" in {thread.thread_id for thread in appended.threads}

    unrelated_path.write_text(
        json.dumps(
            {
                "timestamp": "2026-07-14T04:00:00Z",
                "type": "session_meta",
                "payload": {"id": "unrelated", "source": "user"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    truncated_discovery = module._native_rollout_discovery(candidates, index_path)
    assert truncated_discovery.stats["scanned_files"] == 1
    assert truncated_discovery.stats["cached_files"] == len(candidates) - 1
    truncated = module.build_codex_rollout_run(
        "coordinator",
        tmp_path,
        include_delegations=True,
        discovery_index_path=index_path,
    )
    assert "unrelated" not in {thread.thread_id for thread in truncated.threads}


def test_native_codex_discovery_index_invalidates_replaced_identity(
    tmp_path,
):
    module = _load_module()
    original_path = _write_codex_catalog_rollout(
        tmp_path,
        thread_id="original",
        timestamp="2026-07-14T04:00:00Z",
        request="Original task",
        workspace=str(tmp_path),
    )
    index_path = tmp_path / "rollout-discovery.sqlite3"
    module.build_codex_rollout_run(
        "original",
        tmp_path,
        discovery_index_path=index_path,
    )
    replacement = {
        "timestamp": "2026-07-14T04:00:00Z",
        "type": "session_meta",
        "payload": {"id": "replacement", "source": "user"},
    }
    original_path.write_text(json.dumps(replacement) + "\n", encoding="utf-8")
    discovery = module._native_rollout_discovery([original_path.resolve()], index_path)
    assert discovery.stats["scanned_files"] == 1
    assert discovery.stats["cached_files"] == 0

    run = module.build_codex_rollout_run(
        "replacement",
        tmp_path,
        discovery_index_path=index_path,
    )
    assert [thread.thread_id for thread in run.threads] == ["replacement"]


def test_native_codex_discovery_index_failure_is_explicit(tmp_path):
    module = _load_module()
    _write_codex_sequence_graph(tmp_path)
    unavailable_index = tmp_path / "rollout-discovery.sqlite3"
    unavailable_index.mkdir()

    with pytest.raises(RuntimeError, match="discovery index"):
        module.build_codex_rollout_run(
            "coordinator",
            tmp_path,
            include_delegations=True,
            discovery_index_path=unavailable_index,
        )


def test_native_codex_discovery_rejects_missing_engine(tmp_path, monkeypatch):
    module = _load_module()
    rollout = _write_codex_catalog_rollout(
        tmp_path,
        thread_id="root",
        timestamp="2026-07-14T04:00:00Z",
        request="Root task",
        workspace=str(tmp_path),
    )
    missing_engine = tmp_path / "missing-agent-report-engine"
    monkeypatch.setattr(module, "_native_discovery_engine_path", lambda: missing_engine)

    with pytest.raises(RuntimeError, match="Unable to start required native discovery engine"):
        module._native_rollout_discovery([rollout.resolve()], None)


def test_native_codex_discovery_rejects_missing_configured_engine(
    tmp_path,
    monkeypatch,
):
    module = _load_module()
    configured = tmp_path / "missing-agent-report-engine"
    monkeypatch.setenv("AGENT_REPORT_ENGINE", str(configured))

    with pytest.raises(RuntimeError, match="Configured native discovery engine"):
        module._native_discovery_engine_path()


def test_native_codex_linked_delegations_expand_sequence_scope(tmp_path):
    module = _load_module()
    _write_codex_sequence_graph(tmp_path)

    hierarchy_only = module.build_codex_rollout_run("coordinator", tmp_path)
    linked = module.build_codex_rollout_run(
        "coordinator",
        tmp_path,
        include_delegations=True,
    )

    assert [thread.thread_id for thread in hierarchy_only.threads] == ["coordinator"]
    assert [thread.thread_id for thread in linked.threads] == [
        "coordinator",
        "orchestrator",
        "worker",
    ]

    events = module._codex_sequence_events(linked)
    assert [event.kind for event in events] == [
        "delegation",
        "spawn",
        "message",
        "followup",
        "interrupt",
        "aborted",
        "delegation",
    ]
    assert [(event.source_thread_id, event.target_thread_id) for event in events] == [
        ("coordinator", "orchestrator"),
        ("orchestrator", "worker"),
        ("orchestrator", "worker"),
        ("orchestrator", "worker"),
        ("orchestrator", "worker"),
        ("worker", "orchestrator"),
        ("orchestrator", "coordinator"),
    ]


def test_delegated_subagent_report_keeps_one_parent_context_without_parent_tree(
    tmp_path,
    monkeypatch,
):
    module = _load_module()
    parent = tmp_path / "parent.jsonl"
    child = tmp_path / "child.jsonl"
    grandchild = tmp_path / "grandchild.jsonl"
    sibling = tmp_path / "sibling.jsonl"
    parent.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-07-22T01:00:00Z",
                        "type": "session_meta",
                        "payload": {"id": "parent", "source": "user"},
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-07-22T01:00:00Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": "Coordinate the backlog.",
                                }
                            ],
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-07-22T01:00:01Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": (
                                        "<codex_delegation>"
                                        "<source_thread_id>child</source_thread_id>"
                                        "<input>Child status response</input>"
                                        "</codex_delegation>"
                                    ),
                                }
                            ],
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    child.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-07-22T01:01:00Z",
                        "type": "session_meta",
                        "payload": {
                            "id": "child",
                            "source": "vscode",
                            "thread_source": "subagent",
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-07-22T01:01:00Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": "<recommended_plugins></recommended_plugins>",
                                }
                            ],
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-07-22T01:01:01Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": (
                                        "<codex_delegation>"
                                        "<source_thread_id>parent</source_thread_id>"
                                        "<input>Fix delegated report traversal.</input>"
                                        "</codex_delegation>"
                                    ),
                                }
                            ],
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-07-22T01:01:02Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "task_started",
                            "turn_id": "child-turn",
                            "started_at": "2026-07-22T01:01:02Z",
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-07-22T01:01:03Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "task_complete",
                            "turn_id": "child-turn",
                            "completed_at": "2026-07-22T01:01:03Z",
                            "duration_ms": 1_000,
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write_codex_catalog_rollout(
        tmp_path,
        thread_id="grandchild",
        timestamp="2026-07-22T01:01:04Z",
        request="Verify the child fix",
        workspace=str(tmp_path),
        parent_thread_id="child",
    )
    _write_codex_catalog_rollout(
        tmp_path,
        thread_id="sibling",
        timestamp="2026-07-22T01:01:05Z",
        request="Unrelated active sibling",
        workspace=str(tmp_path),
        parent_thread_id="parent",
    )
    state_database = tmp_path / ".codex" / "state_5.sqlite"
    state_database.parent.mkdir(parents=True)
    connection = module.sqlite3.connect(state_database)
    try:
        connection.execute("CREATE TABLE threads (id TEXT, title TEXT)")
        connection.execute(
            "INSERT INTO threads VALUES (?, ?)",
            (
                "child",
                "<codex_delegation>"
                "<source_thread_id>parent</source_thread_id>"
                "<input>Fix delegated report traversal.</input>"
                "</codex_delegation>",
            ),
        )
        connection.commit()
    finally:
        connection.close()
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: tmp_path))

    run = module.build_codex_rollout_run(
        "child",
        tmp_path,
        include_delegations=True,
    )

    assert [thread.thread_id for thread in run.threads] == ["child", "grandchild"]
    assert run.state == "complete"
    assert run.run_label == '"Fix delegated report traversal" Agent Report'
    assert run.parent_context.thread_id == "parent"
    assert run.parent_context.task_title == "Coordinate the backlog"
    assert run.parent_context.source_path == str(parent.resolve())
    html = module.render_codex_rollout_html(run)
    assert 'class="parent-context"' in html
    assert "Parent task" in html
    assert "View parent report" in html
    assert "agent-report://view-parent-report?" in html
    assert "sibling" not in {thread.thread_id for thread in run.threads}


def test_native_codex_sealed_linked_delegations_reprocess(tmp_path):
    module = _load_module()
    _write_codex_sequence_graph(tmp_path)
    run = module.build_codex_rollout_run(
        "coordinator",
        tmp_path,
        seal=True,
        allow_aborted=True,
        include_delegations=True,
    )
    manifest = tmp_path / "sealed.json"
    manifest.write_text(module.codex_run_to_json(run), encoding="utf-8")

    reproduced = module.reprocess_sealed_codex_run(manifest)

    assert [thread.thread_id for thread in reproduced.threads] == [
        "coordinator",
        "orchestrator",
        "worker",
    ]
    assert [event.kind for event in module._codex_sequence_events(reproduced)] == [
        "delegation",
        "spawn",
        "message",
        "followup",
        "interrupt",
        "aborted",
        "delegation",
    ]


def test_native_codex_sequence_uses_local_catalog_display_titles(
    tmp_path,
    monkeypatch,
):
    module = _load_module()
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    _write_codex_sequence_graph(sessions)
    desktop_database = tmp_path / ".codex" / "sqlite" / "codex-dev.db"
    desktop_database.parent.mkdir(parents=True)
    connection = module.sqlite3.connect(desktop_database)
    try:
        connection.execute(
            "CREATE TABLE local_thread_catalog ("
            "thread_id TEXT, display_title TEXT, missing_candidate INTEGER, "
            "observation_sequence INTEGER)"
        )
        connection.execute(
            "INSERT INTO local_thread_catalog VALUES (?, ?, 0, 1)",
            ("orchestrator", "Process Backlog Items"),
        )
        connection.commit()
    finally:
        connection.close()
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: tmp_path))

    run = module.build_codex_rollout_run(
        "coordinator",
        sessions,
        include_delegations=True,
    )

    orchestrator = next(
        thread for thread in run.threads if thread.thread_id == "orchestrator"
    )
    assert orchestrator.task_title == "Process Backlog Items"
    assert "Process Backlog Items" in module.render_codex_rollout_html(run)


def test_native_codex_html_renders_offline_agent_sequence_view(tmp_path):
    module = _load_module()
    _write_codex_sequence_graph(tmp_path)
    run = module.build_codex_rollout_run(
        "coordinator",
        tmp_path,
        include_delegations=True,
        thread_titles={
            "coordinator": "List unmerged branches",
            "orchestrator": "Process Backlog Items",
        },
    )

    html = module.render_codex_rollout_html(run)

    assert '<section id="agent-sequence"' in html
    assert '<svg class="agent-sequence-diagram"' in html
    assert 'class="sequence-event sequence-event-delegation"' in html
    assert 'class="sequence-event sequence-event-interrupt"' in html
    assert (
        '<summary data-sequence-ledger-summary>Event ledger · '
        '7 recorded events</summary>'
        in html
    )
    assert '<a href="#timeline">Timeline</a>' in html
    assert (
        '<a href="?view=sequence#agent-sequence" target="_blank" rel="noopener" '
        'data-sequence-window>Sequence window</a>'
        in html
    )
    assert "Sequence tab" not in html
    assert "#agent-sequence { display:none; scroll-margin-top:12px; }" in html
    assert html.index('<div id="timeline"') < html.index('<section id="agent-sequence"')
    timeline = html.split('<div id="timeline"', 1)[1].split(
        '<section id="agent-sequence"', 1
    )[0]
    assert "Thread: List unmerged branches · Agent: main" in timeline
    assert "Thread: Process Backlog Items · Agent: main" in timeline
    assert 'class="sequence-sticky-header"' in html
    assert ".sequence-sticky-header { position:sticky; top:0;" in html
    assert 'class="sequence-event-link" href="#sequence-event-' in html
    assert 'class="tool-call-overlay sequence-event-overlay"' in html
    sequence = html.split('<section id="agent-sequence"', 1)[1]
    participant_header = sequence.split(
        '<svg class="sequence-participant-header"', 1
    )[1].split("</svg>", 1)[0]
    assert "<title>" not in participant_header
    assert "List unmerged branches" in sequence
    assert "Process Backlog Items" in sequence
    assert "message · recipient update" in sequence
    assert "Recorded event" in sequence
    assert "message · [encrypted message, 86 chars]" in sequence
    assert "Recipient's next recorded update" in sequence
    assert "I received the review request and will inspect the branch." in sequence
    assert "Recipient updates are context, not recovered message plaintext." in sequence
    assert "<script src=" not in html
    assert 'rel="stylesheet"' not in html
    assert "Start backlog item API_TOKEN=[redacted]" in html
    assert "API_TOKEN=PRIVATE" not in html
    selected_event = html.split('<section id="sequence-event-1"', 1)[1].split(
        "</section>", 1
    )[0]
    assert '<pre class="sequence-event-full" tabindex="0">' in selected_event
    assert "FULL-DELEGATION-TAIL" in selected_event
    assert ".sequence-event-full { max-height:7.5em;" in html
    assert "overflow:auto; white-space:pre-wrap;" in html
    opaque_message = html.split('<section id="sequence-event-3"', 1)[1].split(
        "</section>", 1
    )[0]
    sender_text = "I am sending the worker the review request now."
    recipient_text = "I received the review request and will inspect the branch."
    assert "Sender's preceding recorded update" in opaque_message
    assert "Sender updates are context, not recovered message plaintext." in opaque_message
    assert 'class="sequence-context-arrow" role="img"' in opaque_message
    assert (
        'aria-label="Encrypted message from Process Backlog Items to worker"'
        in opaque_message
    )
    assert opaque_message.index(sender_text) < opaque_message.index(
        'class="sequence-context-arrow"'
    ) < opaque_message.index(recipient_text)
    spawn_event = html.split('<section id="sequence-event-2"', 1)[1].split(
        "</section>", 1
    )[0]
    parent_text = "I am delegating the review to a worker now."
    assert "Parent's preceding recorded update" in spawn_event
    assert "Spawned agent's next recorded update" in spawn_event
    assert 'aria-label="Spawn from Process Backlog Items to worker"' in spawn_event
    assert "encrypted message" not in spawn_event
    assert spawn_event.index(parent_text) < spawn_event.index(
        'class="sequence-context-arrow"'
    ) < spawn_event.index(recipient_text)


def test_native_codex_sequence_tooltips_only_truncated_participant_titles(tmp_path):
    module = _load_module()
    _write_codex_sequence_graph(tmp_path)
    long_title = (
        "There's been work done on various feature branches never committed to main. "
        "List those branches"
    )
    run = module.build_codex_rollout_run(
        "coordinator",
        tmp_path,
        include_delegations=True,
        thread_titles={
            "coordinator": long_title,
            "orchestrator": "Process Backlog Items",
        },
    )

    html = module.render_codex_rollout_html(run)

    sequence = html.split('<section id="agent-sequence"', 1)[1]
    long_participant = sequence.split(
        '<g class="sequence-participant"', 1
    )[1].split("</g>", 1)[0]
    assert "<title>" not in long_participant
    assert f'data-participant-name="{long_title}"' in sequence
    assert 'tabindex="0"' in long_participant
    assert module._sequence_compact_text(long_title, 24) in long_participant
    assert "<title>Process Backlog Items</title>" not in sequence
    assert "<title>worker</title>" not in sequence
    assert "data-sequence-inspect-detail" in sequence
    assert "showInspectDetail(participant.dataset.participantName);" in html
    assert ".sequence-focus-target:focus-visible rect," in html


def test_native_codex_sequence_supports_standalone_window_mode(tmp_path):
    module = _load_module()
    _write_codex_sequence_graph(tmp_path)
    run = module.build_codex_rollout_run(
        "coordinator",
        tmp_path,
        include_delegations=True,
    )

    html = module.render_codex_rollout_html(run)

    assert (
        '<a href="?view=sequence#agent-sequence" target="_blank" rel="noopener" '
        'data-sequence-window>Sequence window</a>'
    ) in html
    sequence = html.split('<section id="agent-sequence"', 1)[1]
    assert "Open in new tab" not in sequence
    assert "Open in window" not in sequence
    assert "body.sequence-only > :not(#agent-sequence) { display:none; }" in html
    assert "body.sequence-only #agent-sequence { display:flex;" in html
    assert ".sequence-only .sequence-scroll { flex:1 1 auto;" in html
    assert (
        'new URLSearchParams(window.location.search).get("view") === "sequence"'
        in html
    )
    assert 'document.body.classList.add("sequence-only");' in html
    assert 'document.querySelectorAll("[data-sequence-window]")' in html
    assert "window.open(" in html
    assert "popup=yes" in html


def test_codex_output_writer_splits_sequence_into_companion_file(tmp_path):
    module = _load_module()
    _write_codex_sequence_graph(tmp_path)
    run = module.build_codex_rollout_run(
        "coordinator",
        tmp_path,
        include_delegations=True,
    )
    output = tmp_path / "process-backlog-items.html"

    module._write_codex_outputs(run, output)

    sequence_output = tmp_path / "process-backlog-items-sequence.html"
    main_html = output.read_text(encoding="utf-8")
    sequence_html = sequence_output.read_text(encoding="utf-8")
    assert '<section id="agent-sequence"' not in main_html
    assert (
        'href="process-backlog-items-sequence.html?view=sequence#agent-sequence"'
        in main_html
    )
    assert '<section id="agent-sequence"' in sequence_html
    assert 'document.body.classList.contains("sequence-only")' in sequence_html
    assert '<svg class="agent-sequence-diagram"' in sequence_html
    assert '<div id="timeline"' not in sequence_html
    assert 'class="agent-table"' not in sequence_html
    assert '<div class="metrics">' not in sequence_html


def test_native_codex_sequence_exposes_large_diagram_controls(tmp_path):
    module = _load_module()
    _write_codex_sequence_graph(tmp_path)
    run = module.build_codex_rollout_run(
        "coordinator",
        tmp_path,
        include_delegations=True,
    )

    html = module.render_codex_rollout_html(run)

    sequence = html.split('<section id="agent-sequence"', 1)[1]
    assert (
        '<div class="sequence-controls" aria-label="Agent sequence view controls">'
        in sequence
    )
    assert 'data-sequence-zoom-out aria-label="Zoom out"' in sequence
    assert 'data-sequence-zoom-value aria-live="polite">100%</output>' in sequence
    assert 'data-sequence-zoom-in aria-label="Zoom in"' in sequence
    assert 'data-sequence-fit>Fit</button>' in sequence
    assert 'data-sequence-collapse-all>Collapse all</button>' in sequence
    assert 'data-sequence-expand-all>Expand all</button>' in sequence
    assert 'data-sequence-clear-focus disabled>Clear focus</button>' in sequence
    assert (
        'data-sequence-group-repeats aria-pressed="true">Group repeats</button>'
        in sequence
    )
    assert 'data-sequence-reset>Reset view</button>' in sequence
    for category in ("delegation", "message", "followup", "interrupt", "complete"):
        assert f'data-sequence-event-filter="{category}" checked' in sequence
    assert 'data-thread-id="orchestrator"' in sequence
    assert 'data-parent-thread-id=""' in sequence
    assert 'class="sequence-focus-target" role="button" tabindex="0"' in sequence
    assert 'class="sequence-hierarchy-toggle" role="button" tabindex="0"' in sequence
    assert 'data-source-thread-id="coordinator"' in sequence
    assert 'data-target-thread-id="orchestrator"' in sequence
    assert 'data-event-category="delegation"' in sequence
    assert "function initializeAgentSequence(section)" in html
    assert "var collapsedThreadIds = new Set();" in html
    assert 'var focusedThreadId = "";' in html
    assert "var groupRepeats = true;" in html
    assert "function fitSequence()" in html
    assert "function revealFirstActivity()" in html
    assert "firstVisibleActivity.getBoundingClientRect()" in html
    assert "scroll.scrollLeft + activityCenter - scrollCenter" in html
    assert "layoutSequence();\n  requestAnimationFrame(revealFirstActivity);" in html
    assert "function layoutSequence()" in html
    assert ".sequence-controls {" in html
    assert ".sequence-hidden { display:none; }" in html
    assert (
        ".sequence-filter-fieldset legend { padding:0 4px; color:#546e7a;"
        in html
    )
    assert ".sequence-view-status { margin-left:auto; color:#546e7a;" in html


def test_native_codex_sequence_arrow_hover_target_spans_start_line_and_head(
    tmp_path,
):
    module = _load_module()
    _write_codex_sequence_graph(tmp_path)
    run = module.build_codex_rollout_run(
        "coordinator",
        tmp_path,
        include_delegations=True,
    )

    html = module.render_codex_rollout_html(run)
    sequence = html.split('<section id="agent-sequence"', 1)[1]
    first_event = sequence.split('<a class="sequence-event-link"', 1)[1].split(
        "</a>", 1
    )[0]
    visible_line = re.search(
        r'<line class="sequence-line" x1="([^"]+)" y1="([^"]+)" '
        r'x2="([^"]+)" y2="([^"]+)"',
        first_event,
    )
    hover_line = re.search(
        r'<line class="sequence-event-hit" x1="([^"]+)" y1="([^"]+)" '
        r'x2="([^"]+)" y2="([^"]+)"',
        first_event,
    )

    assert visible_line is not None
    assert hover_line is not None
    assert hover_line.groups() == visible_line.groups()
    assert (
        ".sequence-event-link .sequence-event > .sequence-event-hit { "
        "pointer-events:stroke; fill:none; stroke:transparent; stroke-width:24px; "
        "stroke-linecap:round; cursor:pointer; }"
    ) in html
    assert ".sequence-event-link:has(.sequence-event-hit:hover) .sequence-line," in html


def test_native_codex_sequence_renders_toggleable_plaintext_conversation_bubbles(
    tmp_path,
):
    module = _load_module()
    _write_codex_sequence_graph(tmp_path)
    run = module.build_codex_rollout_run(
        "coordinator",
        tmp_path,
        include_delegations=True,
    )

    html = module.render_codex_rollout_html(run)
    sequence = html.split('<section id="agent-sequence"', 1)[1]
    sanitized_thought = (
        "Compare the worker branch against every requested acceptance criterion "
        "before deciding whether to continue. password=[redacted]"
    )
    timeline_thought = (
        "Document why the completed coordination sequence matters to the overall "
        "timeline."
    )
    successive_thought = (
        "Connect the next decision to the outcome already visible on the agent "
        "lifeline."
    )
    repeated_thought = (
        "Trace the decision through the surrounding timeline before sending the "
        "next instruction."
    )

    assert (
        '<label><input type="checkbox" data-sequence-event-filter="thinking" '
        'checked>Thinking</label>'
        in sequence
    )
    assert sequence.count('class="sequence-conversation-bubble"') == 5
    assert 'data-thread-id="orchestrator"' in sequence
    assert 'data-thought-index="0"' in sequence
    assert (
        sequence.count(
            f'<pre class="sequence-thought-full">{repeated_thought}</pre>'
        )
        == 1
    )
    assert f'<pre class="sequence-thought-full">{sanitized_thought}</pre>' in sequence
    assert f'<pre class="sequence-thought-full">{timeline_thought}</pre>' in sequence
    assert f'<pre class="sequence-thought-full">{successive_thought}</pre>' in sequence
    for line in module._sequence_chat_lines(sanitized_thought):
        assert f'>{line}</tspan>' in sequence
    for line in module._sequence_chat_lines(timeline_thought):
        assert f'>{line}</tspan>' in sequence
    assert "Send it now." in sequence
    assert "<title>Encrypted reasoning" not in sequence
    first_bubble = sequence.split(
        '<g class="sequence-conversation-bubble"', 1
    )[1].split("</g>", 1)[0]
    assert "<title>" not in first_bubble
    sequence_document = sequence.split("<!-- agent-sequence:end -->", 1)[0]
    assert "**" not in sequence_document
    assert 'class="sequence-conversation-tail"' in sequence
    assert '<rect x="-98" y="-18" width="196" height="40" rx="10">' in sequence
    assert 'd="M -8 22 L 0 30 L 8 22 Z"' in sequence
    assert '<tspan class="sequence-thinking-line"' in sequence
    assert 'class="sequence-conversation-link" href="#sequence-thought-1"' in sequence
    assert 'class="tool-call-overlay sequence-thought-overlay"' in sequence
    assert "sequence-thinking-tail-large" not in sequence
    assert "sequence-thinking-tail-small" not in sequence
    assert 'data-sequence-thinking-count="5"' in sequence
    assert "var thoughtNodes = Array.from(" in html
    assert "var visibleThoughts = [];" in html
    assert "var visibleTimelineRows = visibleEvents.map" in html
    assert "visibleTimelineRows.forEach(function(entry, index)" in html
    assert "visibleThoughtGroups" not in html
    assert "visibleRows" not in html
    assert "bubbleOnRight" not in html
    assert 'enabledCategories.has("thinking")' in html
    assert ".sequence-conversation-bubble { cursor:pointer; }" in html
    assert ".sequence-event-link .sequence-event > * { pointer-events:none; }" in html
    assert (
        ".sequence-event-link .sequence-event > .sequence-event-hit { "
        "pointer-events:stroke;"
    ) in html
    assert ".sequence-event-link:has(.sequence-event-hit:hover) .sequence-line," in html
    assert 'class="sequence-event-hit"' in sequence
    assert 'link.addEventListener("pointerenter", showThought);' in html

    event_row_indexes = [
        int(value)
        for value in re.findall(
            r'class="sequence-event-link"[^>]*data-row-index="(\d+)"',
            sequence,
        )
    ]
    timeline_positions = sorted(
        (int(order), float(y))
        for order, y in re.findall(
            r'class="sequence-(?:event-link|conversation-bubble)"[^>]*'
            r'data-sequence-order="(\d+)"[^>]*data-base-y="([^"]+)"',
            sequence,
        )
    )
    assert event_row_indexes == list(range(len(event_row_indexes)))
    assert [order for order, _ in timeline_positions] == list(
        range(len(timeline_positions))
    )
    assert all(
        later_y - earlier_y >= 64
        for (_, earlier_y), (_, later_y) in zip(
            timeline_positions,
            timeline_positions[1:],
        )
    )
    assert '<line class="sequence-line"' in sequence


def test_native_codex_sequence_marks_consecutive_repetitive_messages(
    tmp_path,
    monkeypatch,
):
    module = _load_module()
    _write_codex_sequence_graph(tmp_path)
    run = module.build_codex_rollout_run(
        "coordinator",
        tmp_path,
        include_delegations=True,
    )
    repeated = [
        module.AgentSequenceEvent(
            event_timestamp=f"2026-07-14T04:00:0{second}Z",
            kind="message",
            source_thread_id="orchestrator",
            target_thread_id="worker",
            label="message · repeated status",
            source_ordinal=second,
        )
        for second in (3, 4, 5)
    ]
    monkeypatch.setattr(module, "_codex_sequence_events", lambda _run: repeated)

    html = module.render_codex_rollout_html(run)
    sequence = html.split('<section id="agent-sequence"', 1)[1]

    assert sequence.count('data-repeat-count="3"') == 6
    assert sequence.count('data-repeat-index="0"') == 2
    assert sequence.count('data-repeat-index="1"') == 2
    assert sequence.count('data-repeat-index="2"') == 2
    assert '<tspan class="sequence-repeat-count" dx="4">×3</tspan>' in sequence
    assert 'data-event-category="message"' in sequence


def test_main_sequence_view_scans_repeated_codex_session_roots(tmp_path, monkeypatch):
    module = _load_module()
    staging = tmp_path / "staging"
    active = tmp_path / "sessions"
    archived = tmp_path / "archived_sessions"
    staging.mkdir()
    active.mkdir()
    archived.mkdir()
    _write_codex_sequence_graph(staging)
    (staging / "coordinator.jsonl").rename(active / "coordinator.jsonl")
    for filename in ("orchestrator.jsonl", "worker.jsonl", "unrelated.jsonl"):
        (staging / filename).rename(archived / filename)
    output = tmp_path / "sequence-report.html"
    discovery_index = tmp_path / "rollout-discovery.sqlite3"
    monkeypatch.setattr(
        module,
        "_default_codex_discovery_index_path",
        lambda: discovery_index,
    )

    rc = module.main(
        [
            "--codex-thread",
            "coordinator",
            "--sessions-root",
            str(active),
            "--sessions-root",
            str(archived),
            "--include-delegations",
            "--thread-title",
            "coordinator=List unmerged branches",
            "--thread-title",
            "orchestrator=Process Backlog Items",
            "--live",
            "--output",
            str(output),
        ]
    )

    assert rc == 0
    html = (tmp_path / "sequence-report-sequence.html").read_text(encoding="utf-8")
    assert (
        '<summary data-sequence-ledger-summary>Event ledger · '
        '7 recorded events</summary>'
        in html
    )
    assert "List unmerged branches" in html
    assert "Process Backlog Items" in html
    assert "worker" in html
    assert discovery_index.is_file()


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
