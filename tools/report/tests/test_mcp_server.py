# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Verify the caller-visible FastMCP tool and client-root contracts.
# Design: docs/design/components/CD-001-codex-rollout-metrics.md

from __future__ import annotations

import asyncio
from datetime import timezone
from pathlib import Path

import pytest

pytest.importorskip("fastmcp")

from agent_report.mcp_server import _client_workspace_root, mcp
from agent_report import mcp_server as server_module
from agent_report.mcp_report import ReportGenerator, ReportServerConfig
from fastmcp import Client, Context, FastMCP


def test_generate_report_schema_hides_server_implementation_details() -> None:
    """Expose only task selection, output directory, and inline-delivery inputs."""

    assert mcp.name == "mcp-agent-report"

    async def inspect_schema() -> None:
        tools = await mcp.list_tools()
        assert [tool.name for tool in tools] == [
            "generate_report",
            "query_time_range",
            "get_event_details",
            "preflight_report",
            "open_snapshot",
            "get_summary",
            "list_agents",
            "list_turns",
            "list_events",
            "query_snapshot_time_range",
            "query_sequence",
            "query_coordination",
            "get_snapshot_event_details",
            "refresh_snapshot",
            "export_snapshot",
            "close_snapshot",
        ]
        generate, query, details, *snapshot_tools = tools
        assert set(generate.parameters["properties"]) == {
            "thread_id",
            "from_time",
            "to_time",
            "name_contains",
            "output_path",
            "return_via_mcp",
            "return_format",
        }
        assert set(query.parameters["properties"]) == {
            "thread_id",
            "from_time",
            "to_time",
            "bucket_minutes",
            "measure",
            "include_events",
        }
        assert query.parameters["required"] == ["thread_id"]
        assert query.parameters["properties"]["bucket_minutes"]["enum"] == [
            1,
            5,
            15,
            30,
            60,
        ]
        assert query.parameters["properties"]["measure"]["enum"] == [
            "wall_time",
            "uncached_input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "cost_usd",
        ]
        assert set(details.parameters["properties"]) == {"thread_id", "event_id"}
        assert details.parameters["required"] == ["thread_id", "event_id"]
        by_name = {tool.name: tool for tool in snapshot_tools}
        assert set(by_name["open_snapshot"].parameters["properties"]) == {
            "root_thread_id",
            "preflight_token",
            "source_revision",
            "include_children",
            "include_collaborators",
        }
        assert set(by_name["query_snapshot_time_range"].parameters["properties"]) == {
            "snapshot_id",
            "from_time",
            "to_time",
            "measure",
            "group_by",
            "requested_resolution_minutes",
            "maximum_rows",
        }
        assert set(by_name["get_snapshot_event_details"].parameters["properties"]) == {
            "snapshot_id",
            "event_id",
        }

    asyncio.run(inspect_schema())


def test_client_workspace_root_uses_advertised_local_file_root(tmp_path: Path) -> None:
    """Read a supported client root without exposing it as a tool parameter."""

    server = FastMCP("workspace-root-test")

    @server.tool
    async def workspace(ctx: Context) -> str:
        selected = await _client_workspace_root(ctx)
        return str(selected) if selected is not None else ""

    async def call_tool() -> None:
        async with Client(server, roots=[tmp_path.as_uri()]) as client:
            result = await client.call_tool("workspace", {})
            assert result.data == str(tmp_path.resolve())

    asyncio.run(call_tool())


def test_server_lifespan_does_not_open_snapshot_cache_for_classic_tools(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Keep classic MCP startup available when additive cache creation would fail."""

    runtime = object()
    config = ReportServerConfig(
        (tmp_path,), tmp_path / "reports", timezone.utc, "UTC", 65_536
    )
    calls: list[str] = []
    monkeypatch.setattr(server_module, "load_server_config", lambda: config)
    monkeypatch.setattr(server_module.cli, "_load_report_module", lambda: runtime)
    monkeypatch.setattr(
        server_module.cli, "_native_engine_path", lambda: tmp_path / "engine"
    )
    monkeypatch.setattr(server_module, "validate_startup", lambda *_args: None)

    def unavailable_service(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        calls.append("create")
        raise OSError("cache is unwritable")

    monkeypatch.setattr(
        server_module, "create_production_application_service", unavailable_service
    )

    async def inspect_lifespan() -> None:
        async with server_module._server_lifespan(FastMCP("test")) as state:
            assert isinstance(state["report_generator"], ReportGenerator)
            assert calls == []

    asyncio.run(inspect_lifespan())
