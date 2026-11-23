"""FastMCP stdio server (only module that imports the MCP SDK)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, TypeVar

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from skillgate_ai.errors import SkillGateError
from skillgate_ai.mcp import tools as mcp_tools
from skillgate_ai.mcp.context import McpContext
from skillgate_ai.mcp.stdio_guard import ProtocolStreams

SERVER_INSTRUCTIONS = (
    "Local Skill Gate. Tools act on skill packs under the project root. "
    "Start a check with check_start, then poll check_poll until status is not 'running'. "
    "Then use report_get for the full report. One check at a time."
)

_F = TypeVar("_F", bound=Callable[..., dict[str, Any]])


def _render(exc: SkillGateError) -> str:
    if exc.hint:
        return f"{exc.message}\nHint: {exc.hint}"
    return exc.message


def _call(ctx: McpContext, fn: Callable[..., dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    try:
        return fn(ctx, **kwargs)
    except SkillGateError as exc:
        raise ToolError(_render(exc)) from exc


def build_server(ctx: McpContext) -> FastMCP:
    server = FastMCP("skillgate", instructions=SERVER_INSTRUCTIONS)

    @server.tool()
    def validate_skill(skill: str) -> dict[str, Any]:
        """Validate a skill pack (strict SKILL.md + cases)."""
        return _call(ctx, mcp_tools.validate_skill, skill=skill)

    @server.tool()
    def dataset_scaffold(
        skill: str | None = None,
        name: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Create starter cases for a skill or scaffold a new skill under skills/."""
        return _call(ctx, mcp_tools.dataset_scaffold, skill=skill, name=name, force=force)

    @server.tool()
    def dataset_get(skill: str) -> dict[str, Any]:
        """Return the eval dataset view for a skill pack."""
        return _call(ctx, mcp_tools.dataset_get, skill=skill)

    @server.tool()
    def case_add(
        skill: str,
        prompt: str,
        case_id: str | None = None,
        expected: str | None = None,
        output_path: str | None = None,
        should_trigger: bool = True,
        inputs: list[str] | None = None,
        output_optional: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        """Add one check case to a skill pack."""
        return _call(
            ctx,
            mcp_tools.case_add,
            skill=skill,
            prompt=prompt,
            case_id=case_id,
            expected=expected,
            output_path=output_path,
            should_trigger=should_trigger,
            inputs=inputs,
            output_optional=output_optional,
            force=force,
        )

    @server.tool()
    def case_edit(
        skill: str,
        case_id: str,
        prompt: str | None = None,
        expected: str | None = None,
        output_path: str | None = None,
        output_optional: bool | None = None,
    ) -> dict[str, Any]:
        """Edit fields on an existing check case."""
        return _call(
            ctx,
            mcp_tools.case_edit,
            skill=skill,
            case_id=case_id,
            prompt=prompt,
            expected=expected,
            output_path=output_path,
            output_optional=output_optional,
        )

    @server.tool()
    def case_remove(skill: str, case_id: str) -> dict[str, Any]:
        """Remove a check case from a skill pack."""
        return _call(ctx, mcp_tools.case_remove, skill=skill, case_id=case_id)

    @server.tool()
    def case_import(
        skill: str,
        content: str,
        format: Literal["csv", "jsonl", "yaml"] | None = None,
        filename: str | None = None,
        on_conflict: Literal["fail", "skip", "replace"] = "fail",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Bulk-import check cases from CSV, JSONL, or YAML."""
        return _call(
            ctx,
            mcp_tools.case_import,
            skill=skill,
            content=content,
            format=format,
            filename=filename,
            on_conflict=on_conflict,
            dry_run=dry_run,
        )

    @server.tool()
    def check_start(
        skill: str,
        harness: Literal["auto", "cursor-agent", "codex", "claude"] = "auto",
        case_ids: list[str] | None = None,
        tryout: bool = False,
        no_judge: bool = False,
        model: str | None = None,
        timeout_sec: int | None = None,
    ) -> dict[str, Any]:
        """Start a skill check run (one at a time). Requires login or an API key."""
        return _call(
            ctx,
            mcp_tools.check_start,
            skill=skill,
            harness=harness,
            case_ids=case_ids,
            tryout=tryout,
            no_judge=no_judge,
            model=model,
            timeout_sec=timeout_sec,
        )

    @server.tool()
    def check_poll(run_id: str, include_report: bool = False) -> dict[str, Any]:
        """Poll an in-flight or finished check run."""
        return _call(ctx, mcp_tools.check_poll, run_id=run_id, include_report=include_report)

    @server.tool()
    def check_cancel(
        run_id: str,
        mode: Literal["kill", "skip"] = "kill",
    ) -> dict[str, Any]:
        """Request kill or skip on a running check."""
        return _call(ctx, mcp_tools.check_cancel, run_id=run_id, mode=mode)

    @server.tool()
    def report_latest(skill: str) -> dict[str, Any]:
        """Return the latest saved eval run for a skill, if any."""
        return _call(ctx, mcp_tools.report_latest, skill=skill)

    @server.tool()
    def report_get(run_id: str, skill: str | None = None) -> dict[str, Any]:
        """Return one history run (same shape as skillgate history show --json)."""
        return _call(ctx, mcp_tools.report_get, run_id=run_id, skill=skill)

    @server.tool()
    def doctor() -> dict[str, Any]:
        """Report agents, keys (booleans only), and whether checks can start."""
        return _call(ctx, mcp_tools.doctor)

    return server


def serve(root: Path) -> None:
    import anyio

    from skillgate_ai.mcp.stdio_guard import install

    streams = install()
    server = build_server(McpContext.for_root(root))
    anyio.run(_run_stdio, server, streams)


async def _run_stdio(server: FastMCP, streams: ProtocolStreams) -> None:
    import anyio
    from mcp.server.stdio import stdio_server

    # FastMCP.run(transport="stdio") delegates to _mcp_server; pin checked in tests.
    low = server._mcp_server  # noqa: SLF001 - intentional mirror of FastMCP.run_stdio_async
    async with stdio_server(
        stdin=anyio.wrap_file(streams.stdin),
        stdout=anyio.wrap_file(streams.stdout),
    ) as (read_stream, write_stream):
        await low.run(read_stream, write_stream, low.create_initialization_options())
