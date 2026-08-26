# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Adapted from the verified token-ledger tests.
# Responsibility: Verify audit-grade Codex token-ledger generation.
# Design: docs/design/components/CD-001-codex-rollout-metrics.md

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "token_ledger.py"
SPEC = importlib.util.spec_from_file_location("render_token_ledger", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RolloutLedgerTests(unittest.TestCase):
    def write_rollout(self, records: list[dict[str, object]]) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "rollout.jsonl"
        path.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )
        return path

    def test_rollout_generation_preserves_ledger_column_order_and_usage(self) -> None:
        path = self.write_rollout(
            [
                {
                    "timestamp": "2026-08-16T14:41:05.813Z",
                    "type": "turn_context",
                    "payload": {"id": "thread-1", "model": "gpt-5.6-sol"},
                },
                {
                    "timestamp": "2026-08-16T14:41:15.239Z",
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call",
                        "name": "exec",
                        "call_id": "call-1",
                        "input": (
                            "const values = await Promise.all(["
                            "tools.exec_command({cmd: 'pwd'}), "
                            "tools.update_plan({plan: []})]); "
                            "const names = ALL_TOOLS.filter(x => "
                            "/thread|task/.test(x.name));"
                        ),
                    },
                },
                {
                    "timestamp": "2026-08-16T14:41:15.375Z",
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call_output",
                        "call_id": "call-1",
                        "output": [{"type": "input_text", "text": "tool schemas"}],
                    },
                },
                {
                    "timestamp": "2026-08-16T14:41:15.376Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "model_context_window": 1_000,
                            "last_token_usage": {
                                "input_tokens": 100,
                                "cached_input_tokens": 40,
                                "cache_write_input_tokens": 3,
                                "output_tokens": 20,
                                "reasoning_output_tokens": 5,
                                "total_tokens": 120,
                            },
                            "total_token_usage": {
                                "input_tokens": 100,
                                "cached_input_tokens": 40,
                                "cache_write_input_tokens": 3,
                                "output_tokens": 20,
                                "reasoning_output_tokens": 5,
                                "total_tokens": 120,
                            },
                        },
                        "rate_limits": {
                            "primary": {
                                "used_percent": 75.0,
                                "window_minutes": 60,
                                "resets_at": 1_787_196_624,
                            },
                            "credits": {
                                "has_credits": False,
                                "unlimited": False,
                                "balance": "0",
                            },
                            "plan_type": "pro",
                            "spend_control_reached": False,
                        },
                    },
                },
                {
                    "timestamp": "2026-08-16T14:41:16.000Z",
                    "type": "event_msg",
                    "payload": {"type": "agent_message", "message": "duplicate"},
                },
                {
                    "timestamp": "2026-08-16T14:41:17.000Z",
                    "type": "response_item",
                    "payload": {
                        "type": "reasoning",
                        "encrypted_content": "encrypted",
                    },
                },
                {
                    "timestamp": "2026-08-16T14:41:18.000Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "last_token_usage": {
                                "input_tokens": 140,
                                "cached_input_tokens": 80,
                                "cache_write_input_tokens": 0,
                                "output_tokens": 10,
                                "reasoning_output_tokens": 5,
                                "total_tokens": 150,
                            },
                            "total_token_usage": {
                                "input_tokens": 240,
                                "cached_input_tokens": 120,
                                "cache_write_input_tokens": 3,
                                "output_tokens": 30,
                                "reasoning_output_tokens": 10,
                                "total_tokens": 270,
                            },
                        },
                    },
                },
            ]
        )

        headers, rows = MODULE.build_ledger_from_rollout(path, Path("ledger.csv"))

        self.assertEqual(MODULE.LEDGER_HEADERS, headers)
        self.assertEqual(
            [
                "row",
                "time_utc",
                "event",
                "model",
                "evidence_summary",
                "skills",
            ],
            headers[:6],
        )
        snapshot = rows[0]
        snapshot_two = rows[1]
        self.assertEqual("Exec cycle", snapshot["event"])
        self.assertEqual("Reasoning cycle", snapshot_two["event"])
        self.assertEqual("40", snapshot["cache_read_tokens"])
        self.assertEqual("100", snapshot["input_tokens"])
        self.assertEqual("60", snapshot["total_uncached_input_tokens"])
        self.assertEqual("5", snapshot["reasoning_tokens"])
        self.assertEqual("20", snapshot["output_tokens"])
        self.assertEqual("15", snapshot["visible_output_tokens_derived"])
        self.assertEqual("120", snapshot["total_tokens"])
        self.assertEqual("120", snapshot["cumulative_total_tokens"])
        self.assertEqual("120", snapshot["system_total_tokens"])
        self.assertEqual("270", snapshot_two["cumulative_total_tokens"])
        self.assertEqual("270", snapshot_two["system_total_tokens"])
        self.assertEqual("3", snapshot["cache_write_tokens"])
        self.assertEqual("40", snapshot["cumulative_cache_read_tokens"])
        self.assertNotIn("cached_read_cost_usd", headers)
        self.assertNotIn("output_cost_usd", headers)
        self.assertNotIn("input_cost_usd", headers)
        self.assertEqual("$0.000920", snapshot["total_cost_usd"])
        self.assertEqual("184", snapshot["model_input_equivalent_tokens"])
        self.assertEqual("184", snapshot["cumulative_model_input_equivalent_tokens"])
        self.assertEqual("184", snapshot["sol_input_equivalent_tokens"])
        self.assertEqual("184", snapshot["cumulative_sol_input_equivalent_tokens"])
        self.assertEqual("$0.000920", snapshot["cumulative_cost_usd"])
        self.assertEqual("$0.001560", snapshot_two["cumulative_cost_usd"])
        self.assertEqual("312", snapshot_two["cumulative_model_input_equivalent_tokens"])
        self.assertEqual("312", snapshot_two["cumulative_sol_input_equivalent_tokens"])
        self.assertNotIn("usage", headers)
        self.assertEqual("25% remaining", snapshot["_usage"])
        self.assertNotIn("Budget remaining", snapshot["evidence_summary"])
        self.assertNotIn("raw lines", snapshot["evidence_summary"])
        self.assertNotIn("context headroom", snapshot["evidence_summary"])
        self.assertIn("exec_command", snapshot["evidence_summary"])
        self.assertIn("update_plan", snapshot["evidence_summary"])
        self.assertNotIn("load call", snapshot["skills"])
        self.assertNotIn("load result", snapshot["skills"])
        self.assertEqual(2, len(rows))
        self.assertEqual("1", snapshot["_source_line"])
        snapshot["_source_href"] = "ledger-raw.html#L1"
        rendered_time = MODULE.render_cell("time_utc", snapshot)
        self.assertIn('href="ledger-raw.html#L1"', rendered_time)
        self.assertIn(snapshot["time_utc"], rendered_time)
        self.assertIn("raw lines 1–4", rendered_time)
        self.assertIn("Usage: 25% remaining", rendered_time)
        self.assertLess(rendered_time.index("raw lines 1–4"), rendered_time.index("Usage: 25% remaining"))

        raw_html = MODULE.render_raw_rollout_html(path)
        self.assertIn('id="L2"', raw_html)
        self.assertIn("ALL_TOOLS", raw_html)

    def test_rollout_generation_correlates_skill_load_calls_and_results(self) -> None:
        path = self.write_rollout(
            [
                {
                    "timestamp": "2026-08-16T14:41:20.000Z",
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call",
                        "name": "exec",
                        "call_id": "skill-call",
                        "input": "sed -n '1,200p' skills/python/SKILL.md",
                    },
                },
                {
                    "timestamp": "2026-08-16T14:41:20.100Z",
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call_output",
                        "call_id": "skill-call",
                        "output": [{"type": "input_text", "text": "# Python\nRules"}],
                    },
                },
            ]
        )

        _, rows = MODULE.build_ledger_from_rollout(path, Path("ledger.csv"))

        self.assertEqual(1, len(rows))
        pattern = rows[0]
        self.assertEqual("Unmeasured trailing events", pattern["event"])
        self.assertIn("python", pattern["skills"])
        self.assertNotIn("load call", pattern["skills"])
        self.assertNotIn("load result", pattern["skills"])
        self.assertIn("read skill: python", pattern["evidence_summary"])
        self.assertIn("skill content: python", pattern["evidence_summary"])

    def test_forked_rollout_excludes_parent_telemetry_and_normalizes_counters(self) -> None:
        path = self.write_rollout(
            [
                {
                    "timestamp": "2026-08-16T14:44:16.703Z",
                    "type": "session_meta",
                    "payload": {
                        "id": "01a00b07-child",
                        "parent_thread_id": "01a00b04-parent",
                    },
                },
                {
                    "timestamp": "2026-08-16T14:44:16.706Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "last_token_usage": {"total_tokens": 120},
                            "total_token_usage": {
                                "total_tokens": 500,
                                "cached_input_tokens": 300,
                                "cache_write_input_tokens": 10,
                            },
                        },
                    },
                },
                {
                    "timestamp": "2026-08-16T14:44:16.746Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "task_started",
                        "turn_id": "01a00b07-turn",
                    },
                },
                {
                    "timestamp": "2026-08-16T14:44:23.425Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "last_token_usage": {
                                "input_tokens": 25,
                                "cached_input_tokens": 5,
                                "cache_write_input_tokens": 2,
                                "output_tokens": 5,
                                "reasoning_output_tokens": 1,
                                "total_tokens": 30,
                            },
                            "total_token_usage": {
                                "total_tokens": 530,
                                "cached_input_tokens": 305,
                                "cache_write_input_tokens": 12,
                            },
                        },
                    },
                },
            ]
        )

        _, rows = MODULE.build_ledger_from_rollout(path, Path("ledger.csv"))

        self.assertEqual(1, len(rows))
        self.assertEqual("30", rows[0]["system_total_tokens"])
        self.assertEqual("5", rows[0]["cumulative_cache_read_tokens"])
        self.assertEqual("2", rows[0]["cumulative_cache_write_tokens"])
        self.assertEqual("20", rows[0]["uncached_new_tokens_inferred"])

    def test_html_uses_the_concise_column_set_and_vertical_calculations(self) -> None:
        visible = MODULE.display_headers(MODULE.LEDGER_HEADERS)

        self.assertEqual(
            ["previous_call_total_tokens"],
            [header for header in visible if header.startswith("previous_")],
        )
        for omitted in (
            "cumulative_cache_activity_tokens",
            "notes",
            "included_in_snapshot",
            "evidence_type",
        ):
            self.assertNotIn(omitted, visible)
        self.assertNotIn("agent_report_context_tokens", MODULE.LEDGER_HEADERS)
        self.assertEqual("System total tokens", MODULE.display_name("system_total_tokens"))
        self.assertEqual(
            ["model", "evidence_summary", "skills"],
            visible[3:6],
        )
        self.assertEqual(
            [
                "previous_call_total_tokens",
                "cache_read_tokens",
                "cumulative_cache_read_tokens",
                "uncached_old_history_tokens_inferred",
                "input_tokens",
                "uncached_new_tokens_inferred",
                "total_uncached_input_tokens",
                "reasoning_tokens",
                "visible_output_tokens_derived",
                "output_tokens",
                "total_tokens",
                "cumulative_total_tokens",
                "system_total_tokens",
                "cache_write_tokens",
                "cumulative_cache_write_tokens",
                "total_cost_usd",
                "cumulative_cost_usd",
                "model_input_equivalent_tokens",
                "cumulative_model_input_equivalent_tokens",
                "sol_input_equivalent_tokens",
                "cumulative_sol_input_equivalent_tokens",
            ],
            visible[6:],
        )
        self.assertEqual(
            "Reasoning", MODULE.readable_display_name("reasoning_tokens")
        )

        row = MODULE.empty_ledger_row()
        row.update(
            {
                "uncached_old_history_tokens_inferred": "1250",
                "previous_call_total_tokens": "27618",
                "cache_read_tokens": "26368",
            }
        )
        rendered = MODULE.render_cell("uncached_old_history_tokens_inferred", row)
        self.assertIn('<span class="calculation-line">27618</span>', rendered)
        self.assertIn('<span class="calculation-line">- 26368</span>', rendered)
        self.assertNotIn("= 1250", rendered)
        row.update({"input_tokens": "30389", "total_uncached_input_tokens": "4021"})
        self.assertNotIn("cell-calculation", MODULE.render_cell("input_tokens", row))

        html_output = MODULE.render_html(
            MODULE.LEDGER_HEADERS,
            [row],
            title="Ledger",
            source_name="rollout.jsonl",
            explanation_html="",
            explanation_name=None,
        )
        self.assertIn("Field relationships", html_output)
        self.assertIn('<header class="ledger-header">', html_output)
        self.assertIn("Agent Report · thread ledger", html_output)
        self.assertIn(
            "© 2026 Martin.Bechard@DevConsult.ca · MIT License", html_output
        )
        self.assertIn('class="eyebrow"', html_output)
        self.assertIn('font:600 clamp(36px,6vw,68px)/1', html_output)
        self.assertIn("Total tokens this call", html_output)
        self.assertIn("Cumulative total tokens", html_output)
        self.assertNotIn("API total this call", html_output)
        self.assertNotIn('<nav aria-label="Report sections">', html_output)
        self.assertNotIn('href="#explanation"', html_output)
        self.assertIn("Request input [raw]", html_output)
        self.assertIn("Uncached old history = Previous call total − Cache read", html_output)
        self.assertLess(
            html_output.index("Field relationships"),
            html_output.index("<dl>"),
        )

    def test_rollout_generation_tracks_model_changes_per_snapshot(self) -> None:
        path = self.write_rollout(
            [
                {
                    "timestamp": "2026-08-18T12:00:00Z",
                    "type": "turn_context",
                    "payload": {"model": "gpt-5.5"},
                },
                {
                    "timestamp": "2026-08-18T12:00:01Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "last_token_usage": {
                                "input_tokens": 100,
                                "cached_input_tokens": 40,
                                "output_tokens": 20,
                                "total_tokens": 120,
                            },
                            "total_token_usage": {
                                "input_tokens": 100,
                                "cached_input_tokens": 40,
                                "output_tokens": 20,
                                "total_tokens": 120,
                            },
                        },
                    },
                },
                {
                    "timestamp": "2026-08-18T12:00:02Z",
                    "type": "turn_context",
                    "payload": {"model": "gpt-5.4"},
                },
                {
                    "timestamp": "2026-08-18T12:00:03Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "last_token_usage": {
                                "input_tokens": 150,
                                "cached_input_tokens": 80,
                                "output_tokens": 30,
                                "total_tokens": 180,
                            },
                            "total_token_usage": {
                                "input_tokens": 250,
                                "cached_input_tokens": 120,
                                "output_tokens": 50,
                                "total_tokens": 300,
                            },
                        },
                    },
                },
            ]
        )

        _, rows = MODULE.build_ledger_from_rollout(path, Path("ledger.csv"))

        self.assertEqual(["gpt-5.5", "gpt-5.4"], [row["model"] for row in rows])


if __name__ == "__main__":
    unittest.main()
