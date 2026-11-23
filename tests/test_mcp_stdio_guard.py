from __future__ import annotations

import errno
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


def test_guard_protocol_fds_not_inherited() -> None:
    proc = _run_guard_program(
        """
        import errno, subprocess, sys
        s = install()
        fd = s.stdout.fileno()
        child = subprocess.run(
            [
                sys.executable,
                "-c",
                "import os, sys\\n"
                "try:\\n"
                "    os.fstat(int(sys.argv[1]))\\n"
                "    print('inherited')\\n"
                "except OSError as exc:\\n"
                "    print(exc.errno)\\n",
                str(fd),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        print(child.stdout.strip(), file=sys.stderr)
        """
    )
    assert proc.returncode == 0, proc.stderr
    assert int(proc.stderr.strip().splitlines()[-1]) == errno.EBADF


def test_serve_uses_private_protocol_streams(tmp_path: Path, monkeypatch) -> None:
    import asyncio
    import io
    from contextlib import asynccontextmanager

    from skillgate_ai.mcp import stdio_guard
    from skillgate_ai.mcp.server import build_server, serve

    stub_streams = stdio_guard.ProtocolStreams(io.StringIO(), io.StringIO())
    captured: dict[str, object] = {}
    install_calls: list[stdio_guard.ProtocolStreams] = []

    def fake_install() -> stdio_guard.ProtocolStreams:
        install_calls.append(stub_streams)
        return stub_streams

    @asynccontextmanager
    async def fake_stdio_server(*, stdin=None, stdout=None):
        captured["stdin"] = stdin
        captured["stdout"] = stdout
        yield (None, None)

    async def noop_run(*_a, **_k) -> None:
        return None

    def fake_anyio_run(fn, server, streams) -> None:
        assert streams is stub_streams
        asyncio.run(fn(server, streams))

    monkeypatch.setattr("skillgate_ai.mcp.stdio_guard.install", fake_install)
    monkeypatch.setattr("mcp.server.stdio.stdio_server", fake_stdio_server)
    monkeypatch.setattr("anyio.run", fake_anyio_run)

    _original_build = build_server

    def _build_with_noop_run(ctx):
        server = _original_build(ctx)
        server._mcp_server.run = noop_run  # noqa: SLF001
        return server

    monkeypatch.setattr("skillgate_ai.mcp.server.build_server", _build_with_noop_run)

    serve(tmp_path)
    assert install_calls == [stub_streams]
    assert captured.get("stdin") is not None
    assert captured.get("stdout") is not None
