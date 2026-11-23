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


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX sessions")
@pytest.mark.timeout(90)
def test_stdio_stays_valid_while_harness_abuses_stdio(tmp_path: Path) -> None:
    import asyncio
    import json
    import os
    import stat
    import textwrap

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    dest = tmp_path / "skills" / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    agent = bin_dir / "agent"
    agent.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import fcntl, os, select, signal, sys

            def abuse_fd0():
                try:
                    flags = fcntl.fcntl(0, fcntl.F_GETFL)
                    fcntl.fcntl(0, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                except OSError:
                    pass
                try:
                    select.select([0], [], [], 0.5)
                    os.read(0, 4096)
                except OSError:
                    pass

            if len(sys.argv) > 1 and sys.argv[1] == "status":
                abuse_fd0()
                print("Logged in as test@example.com")
                raise SystemExit(0)

            abuse_fd0()
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            os.killpg(0, signal.SIGHUP)
            os.killpg(0, signal.SIGTERM)
            os.write(1, b"NOT-JSON-RPC garbage\\n")
            os.write(2, b"NOT-JSON-RPC garbage\\n")
            print(
                '{{"type":"result","subtype":"success","duration_ms":1,'
                '"is_error":false,"session_id":"s1",'
                '"usage":{{"inputTokens":1,"outputTokens":1}}}}'
            )
            raise SystemExit(0)
            """
        ),
        encoding="utf-8",
    )
    agent.chmod(agent.stat().st_mode | stat.S_IEXEC)
    home = tmp_path / "home"
    home.mkdir()
    (home / ".skillgate").mkdir(parents=True)
    keys = home / ".skillgate" / "keys"
    keys.write_text("ANTHROPIC_API_KEY=sk-test-dummy\n", encoding="utf-8")

    env = {
        k: v
        for k, v in os.environ.items()
        if not any(
            k.startswith(prefix)
            for prefix in (
                "CURSOR_",
                "ANTHROPIC_",
                "OPENAI_",
                "CODEX_",
                "AI_GATEWAY_",
                "SKILLGATE_CURSOR",
            )
        )
        and k != "PYTHONPATH"
    }
    env["PYTHONPATH"] = str(ROOT / "src")
    env["HOME"] = str(home)
    env["CURSOR_AGENT_BIN"] = str(agent)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["ANTHROPIC_API_KEY"] = "sk-test-dummy"

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "skillgate_ai.cli", "mcp", "--root", str(tmp_path)],
        env=env,
    )

    async def _run() -> None:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            started = await session.call_tool(
                "check_start",
                {
                    "skill": "pdf",
                    "harness": "cursor-agent",
                    "case_ids": ["extract-hello"],
                    "no_judge": True,
                    "timeout_sec": 30,
                },
            )
            body = json.loads(started.content[0].text if started.content else "{}")
            run_id = body["id"]
            final = None
            for _ in range(300):
                await asyncio.sleep(0.2)
                polled = await session.call_tool("check_poll", {"run_id": run_id})
                final = json.loads(polled.content[0].text if polled.content else "{}")
                if final.get("status") in {"done", "error"}:
                    break
            assert final is not None
            assert "status" in final
            assert final["status"] in {"done", "error"}
            listed = await session.list_tools()
            assert {t.name for t in listed.tools} == EXPECTED_TOOLS

    asyncio.run(_run())
