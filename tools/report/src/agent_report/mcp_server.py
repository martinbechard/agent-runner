# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Expose report generation and time-range queries through FastMCP.
# Design: docs/design/components/CD-001-codex-rollout-metrics.md

"""FastMCP server for local Codex reports and structured telemetry queries."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, TypeVar

from fastmcp import Context, FastMCP

from agent_report import cli
from agent_report.mcp_report import (
    BucketMinutes,
    ReportGenerator,
    TimeRangeMeasure,
    load_server_config,
    validate_startup,
    workspace_root_from_uri,
)

_T = TypeVar("_T")


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


async def _run_cancellable(
    operation: Callable[..., _T], /, **kwargs: object
) -> _T:
    """Run report work off-loop and ask it to stop when the MCP call is cancelled."""

    cancel_event = threading.Event()
    try:
        return await asyncio.to_thread(
            operation,
            cancelled=cancel_event.is_set,
            **kwargs,
        )
    except asyncio.CancelledError:
        cancel_event.set()
        raise


def create_server() -> FastMCP:
    """Create the agent report MCP server and register its public operations."""

    server = FastMCP(
        "mcp-agent-report",
        instructions=(
            "Generate a complete local report bundle or query bucketed execution "
            "telemetry for one Codex task. Range events include IDs that can be "
            "resolved through the event-detail operation."
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

    @server.tool
    async def query_time_range(
        ctx: Context,
        thread_id: str,
        from_time: str | None = None,
        to_time: str | None = None,
        bucket_minutes: BucketMinutes = 5,
        measure: TimeRangeMeasure = "wall_time",
        include_events: bool = False,
    ) -> dict[str, object]:
        """Retrieve bucketed telemetry; included events have IDs for detail lookup."""

        generator = ctx.lifespan_context["report_generator"]
        report_lock = ctx.lifespan_context["report_lock"]
        if not isinstance(generator, ReportGenerator):
            raise TypeError("Agent report server did not initialize correctly")
        if not isinstance(report_lock, asyncio.Lock):
            raise TypeError("Agent report server did not initialize correctly")
        async with report_lock:
            return await _run_cancellable(
                generator.query_time_range,
                thread_id=thread_id,
                from_time=from_time,
                to_time=to_time,
                bucket_minutes=bucket_minutes,
                measure=measure,
                include_events=include_events,
            )

    @server.tool
    async def get_event_details(
        ctx: Context,
        thread_id: str,
        event_id: str,
    ) -> dict[str, object]:
        """Retrieve the full privacy-safe record for an ID from query_time_range."""

        generator = ctx.lifespan_context["report_generator"]
        report_lock = ctx.lifespan_context["report_lock"]
        if not isinstance(generator, ReportGenerator):
            raise TypeError("Agent report server did not initialize correctly")
        if not isinstance(report_lock, asyncio.Lock):
            raise TypeError("Agent report server did not initialize correctly")
        async with report_lock:
            return await _run_cancellable(
                generator.get_event_details,
                thread_id=thread_id,
                event_id=event_id,
            )

    return server


mcp = create_server()


def main() -> None:
    """Run the installed server over FastMCP's default stdio transport."""

    mcp.run()


if __name__ == "__main__":
    main()
