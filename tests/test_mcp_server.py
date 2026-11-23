from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from skillgate_ai.demo_files import ensure_demo_pdfs
from skillgate_ai.mcp.context import McpContext
from skillgate_ai.mcp.server import build_server

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TOOLS = frozenset(
    {
        "validate_skill",
        "dataset_scaffold",
        "dataset_get",
        "case_add",
        "case_edit",
        "case_remove",
        "case_import",
        "check_start",
        "check_poll",
        "check_cancel",
        "report_latest",
        "report_get",
        "doctor",
    }
)


@pytest.fixture
def ctx(tmp_path: Path) -> McpContext:
    dest = tmp_path / "skills" / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")
    return McpContext.for_root(tmp_path)


def test_build_server_registers_thirteen_tools(ctx: McpContext) -> None:
    server = build_server(ctx)
    names = {tool.name for tool in server._tool_manager.list_tools()}
    assert names == EXPECTED_TOOLS


def test_tool_error_maps_skillgate_error_to_is_error(ctx: McpContext) -> None:
    import asyncio

    from mcp.server.fastmcp.exceptions import ToolError

    async def _run() -> str:
        server = build_server(ctx)
        try:
            await server._tool_manager.call_tool(
                "dataset_get",
                {"skill": "not-a-real-skill-ever"},
            )
        except ToolError as exc:
            return str(exc)
        raise AssertionError("expected tool error")

    msg = asyncio.run(_run())
    assert "skill" in msg.lower() or "Skill" in msg


def test_tool_schemas_have_descriptions(ctx: McpContext) -> None:
    server = build_server(ctx)
    for tool in server._tool_manager.list_tools():
        assert tool.description.strip(), tool.name
        assert tool.parameters


@pytest.mark.timeout(30)
def test_stdio_roundtrip_list_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio
    dest = tmp_path / "skills" / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")
    import os
    import site

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    py_path = os.pathsep.join([str(ROOT / "src"), site.getusersitepackages()])
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "skillgate_ai.cli", "mcp", "--root", str(tmp_path)],
        env={**os.environ, "PYTHONPATH": py_path},
    )
    async def _roundtrip() -> set[str]:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            return {t.name for t in listed.tools}

    names = asyncio.run(_roundtrip())
    assert names == EXPECTED_TOOLS
