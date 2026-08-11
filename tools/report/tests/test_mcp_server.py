# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Verify the caller-visible FastMCP tool and client-root contracts.
# Design: docs/design/components/CD-001-codex-rollout-metrics.md

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("fastmcp")

from agent_report.mcp_server import _client_workspace_root, mcp
from fastmcp import Client, Context, FastMCP


def test_generate_report_schema_hides_server_implementation_details() -> None:
    """Expose only task selection, output directory, and inline-delivery inputs."""

    async def inspect_schema() -> None:
        tools = await mcp.list_tools()
        assert [tool.name for tool in tools] == ["generate_report"]
        assert set(tools[0].parameters["properties"]) == {
            "thread_id",
            "from_time",
            "to_time",
            "name_contains",
            "output_path",
            "return_via_mcp",
            "return_format",
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
