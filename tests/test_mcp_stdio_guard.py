from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("mcp")

ROOT = Path(__file__).resolve().parents[1]
SRC = str(ROOT / "src")


def _run_guard_program(body: str, *, input_text: str = "") -> subprocess.CompletedProcess[str]:
    program = textwrap.dedent(
        f"""
        import os, subprocess, sys
        sys.path.insert(0, {SRC!r})
        from skillgate_ai.mcp.stdio_guard import install
        {body}
        """
    )
    env = {k: v for k, v in os.environ.items() if k != "SKILLGATE_MCP_NO_STDIO_GUARD"}
    return subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        input=input_text,
        env=env,
        timeout=30,
        check=False,
    )


def test_guard_routes_stray_stdout_to_stderr() -> None:
    proc = _run_guard_program(
        """
        s = install()
        print("stray-print")
        os.write(1, b"stray-fd\\n")
        subprocess.run(["sh", "-c", "echo stray-child"], check=False)
        s.stdout.write("PROTO\\n")
        s.stdout.flush()
        """
    )
    assert proc.stdout == "PROTO\n", proc.stderr
    assert "stray-print" in proc.stderr
    assert "stray-fd" in proc.stderr
    assert "stray-child" in proc.stderr


def test_guard_children_see_devnull_stdin_and_protocol_keeps_bytes() -> None:
    proc = _run_guard_program(
        """
        s = install()
        subprocess.run(
            [sys.executable, "-c", "import sys; print(repr(sys.stdin.read()), file=sys.stderr)"],
            check=False,
        )
        line = s.stdin.readline().strip()
        print(line, file=sys.stderr)
        """,
        input_text='{"jsonrpc":"2.0"}\n',
    )
    assert "''" in proc.stderr
    assert '{"jsonrpc":"2.0"}' in proc.stderr


def test_serve_uses_private_protocol_streams(tmp_path: Path, monkeypatch) -> None:
    import asyncio
    import io
    from contextlib import asynccontextmanager

    from skillgate_ai.mcp import stdio_guard
    from skillgate_ai.mcp.context import McpContext
    from skillgate_ai.mcp.server import _run_stdio, build_server

    captured: dict[str, object] = {}

    @asynccontextmanager
    async def fake_stdio_server(*, stdin=None, stdout=None):
        captured["stdin"] = stdin
        captured["stdout"] = stdout
        yield (None, None)

    async def noop_run(*_a, **_k) -> None:
        return None

    async def _exercise() -> None:
        monkeypatch.setattr("mcp.server.stdio.stdio_server", fake_stdio_server)
        streams = stdio_guard.ProtocolStreams(io.StringIO(), io.StringIO())
        server = build_server(McpContext.for_root(tmp_path))
        server._mcp_server.run = noop_run  # noqa: SLF001
        await _run_stdio(server, streams)

    asyncio.run(_exercise())
    assert captured.get("stdin") is not None
    assert captured.get("stdout") is not None
