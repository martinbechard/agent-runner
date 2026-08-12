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
from agent_report import application_service as service_types
from agent_report.mcp_report import (
    BucketMinutes,
    ReportGenerator,
    TimeRangeMeasure,
    application_service_config,
    create_production_application_service,
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
    application_service = create_production_application_service(
        runtime, application_service_config(runtime, config.session_roots)
    )
    generator = ReportGenerator(
        runtime, config, application_service=application_service
    )
    try:
        yield {
            "report_generator": generator,
            "report_lock": asyncio.Lock(),
        }
    finally:
        generator.close()


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


async def _run_cancellable(operation: Callable[..., _T], /, **kwargs: object) -> _T:
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

    async def snapshot_call(
        ctx: Context, method_name: str, /, **kwargs: object
    ) -> dict[str, object]:
        generator = ctx.lifespan_context["report_generator"]
        report_lock = ctx.lifespan_context["report_lock"]
        if not isinstance(generator, ReportGenerator) or not isinstance(
            report_lock, asyncio.Lock
        ):
            raise TypeError("Agent report server did not initialize correctly")
        operation = getattr(generator, method_name)
        async with report_lock:
            return await _run_cancellable(operation, **kwargs)

    @server.tool
    async def preflight_report(
        ctx: Context,
        root_thread_id: str,
        include_children: bool = False,
        include_collaborators: bool = False,
    ) -> dict[str, object]:
        """Inspect one exact scope before opening a coherent snapshot."""

        return await snapshot_call(
            ctx,
            "preflight_report",
            root_thread_id=root_thread_id,
            include_children=include_children,
            include_collaborators=include_collaborators,
        )

    @server.tool
    async def open_snapshot(
        ctx: Context,
        root_thread_id: str,
        preflight_token: str,
        source_revision: str,
        include_children: bool = False,
        include_collaborators: bool = False,
    ) -> dict[str, object]:
        """Open a revision-bound snapshot from an accepted preflight."""

        return await snapshot_call(
            ctx,
            "open_snapshot",
            root_thread_id=root_thread_id,
            preflight_token=preflight_token,
            source_revision=source_revision,
            include_children=include_children,
            include_collaborators=include_collaborators,
        )

    @server.tool
    async def get_summary(ctx: Context, snapshot_id: str) -> dict[str, object]:
        """Return the bounded summary for an open snapshot."""

        return await snapshot_call(ctx, "get_summary", snapshot_id=snapshot_id)

    @server.tool
    async def list_agents(
        ctx: Context,
        snapshot_id: str,
        query: str = "",
        agent_ids: list[str] | None = None,
        roles: list[str] | None = None,
        states: list[str] | None = None,
        sort_key: service_types.AgentSortKey = "last_activity_at",
        sort_direction: service_types.SortDirection = "descending",
        cursor: str | None = None,
        page_size: int = service_types.DEFAULT_PAGE_SIZE,
    ) -> dict[str, object]:
        """Return one canonical page of agents."""

        return await snapshot_call(
            ctx,
            "list_agents",
            snapshot_id=snapshot_id,
            query=query,
            agent_ids=agent_ids,
            roles=roles,
            states=states,
            sort_key=sort_key,
            sort_direction=sort_direction,
            cursor=cursor,
            page_size=page_size,
        )

    @server.tool
    async def list_turns(
        ctx: Context,
        snapshot_id: str,
        turn_ids: list[str] | None = None,
        agent_ids: list[str] | None = None,
        states: list[str] | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
        sort_key: service_types.TurnSortKey = "started_at",
        sort_direction: service_types.SortDirection = "ascending",
        cursor: str | None = None,
        page_size: int = service_types.DEFAULT_PAGE_SIZE,
    ) -> dict[str, object]:
        """Return one canonical page of turns."""

        return await snapshot_call(
            ctx,
            "list_turns",
            snapshot_id=snapshot_id,
            turn_ids=turn_ids,
            agent_ids=agent_ids,
            states=states,
            from_time=from_time,
            to_time=to_time,
            sort_key=sort_key,
            sort_direction=sort_direction,
            cursor=cursor,
            page_size=page_size,
        )

    @server.tool
    async def list_events(
        ctx: Context,
        snapshot_id: str,
        event_ids: list[str] | None = None,
        agent_ids: list[str] | None = None,
        turn_ids: list[str] | None = None,
        kinds: list[str] | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
        sort_key: service_types.EventSortKey = "occurred_at",
        sort_direction: service_types.SortDirection = "ascending",
        cursor: str | None = None,
        page_size: int = service_types.DEFAULT_PAGE_SIZE,
    ) -> dict[str, object]:
        """Return one canonical page of events."""

        return await snapshot_call(
            ctx,
            "list_events",
            snapshot_id=snapshot_id,
            event_ids=event_ids,
            agent_ids=agent_ids,
            turn_ids=turn_ids,
            kinds=kinds,
            from_time=from_time,
            to_time=to_time,
            sort_key=sort_key,
            sort_direction=sort_direction,
            cursor=cursor,
            page_size=page_size,
        )

    @server.tool
    async def query_snapshot_time_range(
        ctx: Context,
        snapshot_id: str,
        from_time: str,
        to_time: str,
        measure: service_types.TimeMeasure,
        group_by: service_types.HeatmapGroupBy,
        requested_resolution_minutes: int,
        maximum_rows: int = 100,
    ) -> dict[str, object]:
        """Return a grouped heatmap for an open snapshot."""

        return await snapshot_call(
            ctx,
            "query_snapshot_time_range",
            snapshot_id=snapshot_id,
            from_time=from_time,
            to_time=to_time,
            measure=measure,
            group_by=group_by,
            requested_resolution_minutes=requested_resolution_minutes,
            maximum_rows=maximum_rows,
        )

    @server.tool
    async def query_sequence(
        ctx: Context,
        snapshot_id: str,
        focus_agent_id: str | None = None,
        event_ids: list[str] | None = None,
        agent_ids: list[str] | None = None,
        turn_ids: list[str] | None = None,
        kinds: list[str] | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
        grouping: service_types.SequenceGrouping = "none",
        include_reasoning: bool = False,
        cursor: str | None = None,
        page_size: int = service_types.DEFAULT_PAGE_SIZE,
    ) -> dict[str, object]:
        """Return a sequence page and hierarchy for an open snapshot."""

        return await snapshot_call(
            ctx,
            "query_sequence",
            snapshot_id=snapshot_id,
            focus_agent_id=focus_agent_id,
            event_ids=event_ids,
            agent_ids=agent_ids,
            turn_ids=turn_ids,
            kinds=kinds,
            from_time=from_time,
            to_time=to_time,
            grouping=grouping,
            include_reasoning=include_reasoning,
            cursor=cursor,
            page_size=page_size,
        )

    @server.tool
    async def query_coordination(
        ctx: Context,
        snapshot_id: str,
        work_item_id: str | None = None,
        delegated_root_id: str | None = None,
        agent_id: str | None = None,
        operation: str | None = None,
        evidence: service_types.EvidenceKind | None = None,
        cursor: str | None = None,
        page_size: int = service_types.DEFAULT_PAGE_SIZE,
    ) -> dict[str, object]:
        """Return evidence-labeled coordination rows for an open snapshot."""

        return await snapshot_call(
            ctx,
            "query_coordination",
            snapshot_id=snapshot_id,
            work_item_id=work_item_id,
            delegated_root_id=delegated_root_id,
            agent_id=agent_id,
            operation=operation,
            evidence=evidence,
            cursor=cursor,
            page_size=page_size,
        )

    @server.tool
    async def get_snapshot_event_details(
        ctx: Context, snapshot_id: str, event_id: str
    ) -> dict[str, object]:
        """Return bounded event detail from an open snapshot."""

        return await snapshot_call(
            ctx,
            "get_snapshot_event_details",
            snapshot_id=snapshot_id,
            event_id=event_id,
        )

    @server.tool
    async def refresh_snapshot(ctx: Context, snapshot_id: str) -> dict[str, object]:
        """Refresh an open snapshot and report whether its revision changed."""

        return await snapshot_call(ctx, "refresh_snapshot", snapshot_id=snapshot_id)

    @server.tool
    async def export_snapshot(
        ctx: Context,
        snapshot_id: str,
        target: str,
        replace: bool = False,
        report_mode: Literal["directory", "summary"] | None = None,
        include_sqlite_archive: bool = False,
    ) -> dict[str, object]:
        """Publish an open snapshot to an MCP-authorized target."""

        return await snapshot_call(
            ctx,
            "export_snapshot",
            snapshot_id=snapshot_id,
            target=target,
            replace=replace,
            report_mode=report_mode,
            include_sqlite_archive=include_sqlite_archive,
        )

    @server.tool
    async def close_snapshot(ctx: Context, snapshot_id: str) -> dict[str, object]:
        """Close an open snapshot and release its process-local resources."""

        generator = ctx.lifespan_context["report_generator"]
        report_lock = ctx.lifespan_context["report_lock"]
        if not isinstance(generator, ReportGenerator) or not isinstance(
            report_lock, asyncio.Lock
        ):
            raise TypeError("Agent report server did not initialize correctly")
        async with report_lock:
            return await asyncio.to_thread(
                generator.close_snapshot, snapshot_id=snapshot_id
            )

    return server


mcp = create_server()


def main() -> None:
    """Run the installed server over FastMCP's default stdio transport."""

    mcp.run()


if __name__ == "__main__":
    main()
