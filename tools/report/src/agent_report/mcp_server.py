# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Expose agent report generation as one FastMCP operation.
# Design: docs/design/components/CD-001-codex-rollout-metrics.md

"""FastMCP server for local Codex agent report generation."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastmcp import Context, FastMCP

from agent_report import cli
from agent_report.mcp_report import (
    ReportGenerator,
    load_server_config,
    validate_startup,
    workspace_root_from_uri,
)


@asynccontextmanager
async def _server_lifespan(_server: FastMCP) -> AsyncIterator[dict[str, object]]:
    """Validate the installed runtime once before accepting tool calls."""

    config = load_server_config()
    runtime = cli._load_report_module()
    validate_startup(runtime, cli._native_engine_path())
    yield {
        "report_generator": ReportGenerator(runtime, config),
        "report_lock": asyncio.Lock(),
    }


async def _client_workspace_root(ctx: Context) -> Path | None:
    """Return the first local workspace root advertised by the MCP client."""

    request_context = ctx.request_context
    session = getattr(request_context, "session", None) if request_context else None
    if session is None:
        return None
    try:
        response = await session.list_roots()
    except Exception:  # noqa: BLE001 - client roots are optional across MCP hosts
        return None
    for root in getattr(response, "roots", []):
        path = workspace_root_from_uri(getattr(root, "uri", None))
        if path is not None:
            return path
    return None


def create_server() -> FastMCP:
    """Create the agent report MCP server and register its public operation."""

    server = FastMCP(
        "Agent Report",
        instructions=(
            "Generate a complete local report bundle for one Codex task, selected "
            "by exact thread ID or by time and task-name filters."
        ),
        lifespan=_server_lifespan,
    )

    @server.tool
    async def generate_report(
        ctx: Context,
        thread_id: str | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
        name_contains: list[str] | None = None,
        output_path: str | None = None,
        return_via_mcp: bool = False,
        return_format: Literal["html", "markdown", "json"] = "html",
    ) -> dict[str, object]:
        """Generate one Codex task report without exposing runtime internals."""

        generator = ctx.lifespan_context["report_generator"]
        report_lock = ctx.lifespan_context["report_lock"]
        if not isinstance(generator, ReportGenerator):
            raise TypeError("Agent report server did not initialize correctly")
        if not isinstance(report_lock, asyncio.Lock):
            raise TypeError("Agent report server did not initialize correctly")
        workspace_root = await _client_workspace_root(ctx)
        async with report_lock:
            return await asyncio.to_thread(
                generator.generate_report,
                thread_id=thread_id,
                from_time=from_time,
                to_time=to_time,
                name_contains=name_contains,
                output_path=output_path,
                return_via_mcp=return_via_mcp,
                return_format=return_format,
                workspace_root=workspace_root,
            )

    return server


mcp = create_server()


def main() -> None:
    """Run the installed server over FastMCP's default stdio transport."""

    mcp.run()


if __name__ == "__main__":
    main()
