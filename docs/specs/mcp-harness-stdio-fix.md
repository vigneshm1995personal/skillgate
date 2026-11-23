# Spec: MCP stdio server dies during `cursor-agent` checks

Status: implemented on `cursor/mcp-server-a0f3` · MCP SDK pinned in venv: `mcp==1.30.0`

**Step 0 (Mini, pre-fix branch `e3dc1ba6`):** `scripts/mcp_stdio_repro.py` did not reproduce `ClosedResourceError` in 3 live cursor-agent runs (flaky bug), but code review confirmed **H1** (`agent status` probes inherit MCP fd 0) and **H2** (streaming harness shares the MCP process group). The fix closes both plus stdout guard **H3**.

---

## 1. Bug

An MCP stdio client calls `check_start` with `harness="cursor-agent"` (or `"auto"` that resolves to cursor-agent), then calls `check_poll` every 2 s. Roughly 6–13 s in, while `current_task_id == "extract-hello"`, the `skillgate mcp` server process dies. The client then gets `anyio.ClosedResourceError` on its next call. `harness="claude"` does not fail this way. The failure is flaky: the first repro attempts failed, and later manual runs passed.

Repro script (untracked, keep it for the step 0 confirmation): `scripts/mcp_stdio_repro.py --harness cursor-agent --runs 10 --poll-sec 2`.

---

## 2. Root cause analysis

All four hazards below are real in the current code. Step 0 (§5) decides which one actually fires on the maintainer's machine. **The fix closes all four whatever step 0 finds**, because each one alone can kill or corrupt the stdio transport.

### H1 (most likely primary): auth probes inherit the MCP JSON-RPC stdin

`src/skillgate_ai/harness/auth.py` has three status probes:

- `_probe_cursor_login_status` (line ~81)
- `_probe_codex_login_status` (line ~43)
- `_probe_claude_login_status` (line ~129)

Each calls `subprocess.run([...], capture_output=True, ...)` and **does not pass `stdin=`**, so the child inherits fd 0. In `skillgate mcp`, fd 0 is the client's JSON-RPC request pipe.

When there is no `CURSOR_API_KEY`, `auth._cursor_ready` → `cursor_auth_kind` → `_cursor_session_ok` → `_probe_cursor_login_status` runs `agent status`. That happens:

- on the run worker thread at the start of each task: `CursorAgentHarness.run` (`harness/agents.py:77`) calls `auth._cursor_ready(self.cfg)` first, which matches `current_task_id=extract-hello`;
- during `auto` resolution (`harness/resolve.py:22` and `:68`).

`agent` / `cursor-agent` is a Node CLI. A Node process that inherits a pipe on fd 0 can do either of the following:

- **(a)** set `O_NONBLOCK` on the shared open file description. The MCP server's blocking `stdin` reader (`mcp/server/stdio.py`, `async for line in stdin`) then gets `BlockingIOError`/EAGAIN. The reader task ends, `stdio_server` tears down, the process exits, and the client sees `ClosedResourceError`.
- **(b)** read bytes off the pipe, which steals or truncates a `check_poll` request.

Both are timing-dependent: it matters whether a poll is in flight while `agent status` is alive. That explains the flakiness. The claude path skips the probe when `ANTHROPIC_API_KEY` is set, and `claude auth status` does not touch stdin, so claude stays green.

### H2: the streaming harness child shares the MCP server's process group and session

Live checks (UI and MCP) set `sandbox.output_sink = control` (`engine/task.py:430`). `LocalSandbox.run` then takes `_run_streaming` (`sandbox.py:201`), whose `subprocess.Popen` (lines 213–222) has **no `start_new_session=True`**.

The harness tree (`agent` → node → tool shells) therefore lives in the MCP server's process group and session. Any `kill(0, sig)` / `process.kill(-pgid)`, any group-wide SIGHUP/SIGINT/SIGTERM that cursor-agent or one of its tool subprocesses sends during cleanup, or any job-control signal hits the MCP server too. The MCP client already starts the server with `start_new_session=True` (`mcp/client/stdio/__init__.py:256`), so the server is a group leader and the harness lands **in its group**.

### H3: in-process code on the worker thread could write to fd 1

`docs/specs/mcp-server.md` §2 says "no code a tool calls in-process may write to stdout". Nothing enforces it: a stray `print`, a Rich `Console()` defaulting to stdout, a C extension, or a child started with inherited stdout would put non-JSON bytes on the protocol stream. The client's reader then fails to parse, and some clients close the session.

### H4: the private protocol fds are not isolated from children

`close_fds=True` is Python's default and must stay that way. Nothing documents this, and nothing makes fd 0 and fd 1 harmless for children that inherit them.

### Why `RunRegistry` / `gate` are not the right place for a per-run guard

`contextlib.redirect_stdout` swaps `sys.stdout` for the whole process, not per thread. It does not touch fd 1, so C-level writes and children are not covered. It would also redirect the UI server's output when `source == "ui"`. The guard therefore goes in at the fd level, once, for the lifetime of `skillgate mcp` (§4.5). In that process every run is `source="mcp"`, so this is the same as "guard when source is mcp", without per-run global state.

---

## 3. Goals and non-goals

**Goals**

1. A harness child or auth-probe child can never read the MCP request pipe, write to the MCP response pipe, or signal the MCP server's process group.
2. While `skillgate mcp` serves, any stray in-process stdout write (Python or fd level) goes to stderr.
3. Skip, kill and timeout still tear down the **whole** harness process tree now that it lives in its own session.
4. A deterministic regression test that fails on today's code and passes after the fix.

**Non-goals**

- No change to CLI or web behaviour beyond subprocess I/O and session isolation.
- No change to harness argv, env allowlist, transcript parsing, report shape, or MCP tool schemas.

---

## 4. Design and exact changes

### 4.1 New module `src/skillgate_ai/child_io.py`

This module is the one place that defines isolation for external CLI children. It is stdlib-only, so `auth.py` can import it without a cycle.

    """Spawn flags for external CLI children: no inherited stdin, own session.

    Under `skillgate mcp`, fd 0/1 are the JSON-RPC pipes. A child that inherits
    fd 0 can steal requests or flip O_NONBLOCK on the shared pipe; a child in our
    process group can signal the server. Every harness / probe spawn uses these.
    """

    from __future__ import annotations

    import os
    import signal
    import subprocess
    import sys
    from typing import Any

    POSIX = sys.platform != "win32"


    def isolated_kwargs() -> dict[str, Any]:
        """stdin=DEVNULL, close_fds, and (POSIX) a new session / process group."""
        kwargs: dict[str, Any] = {"stdin": subprocess.DEVNULL, "close_fds": True}
        if POSIX:
            kwargs["start_new_session"] = True
        return kwargs


    def signal_group(proc: subprocess.Popen[Any], sig: int) -> None:
        """Signal the child's whole group (it is a session leader); fall back to the pid."""
        if proc.poll() is not None:
            return
        if POSIX:
            try:
                os.killpg(proc.pid, sig)
                return
            except (ProcessLookupError, PermissionError, OSError):
                pass
        try:
            proc.send_signal(sig)
        except (ProcessLookupError, OSError):
            pass


    def kill_group(proc: subprocess.Popen[Any]) -> None:
        signal_group(proc, signal.SIGKILL if POSIX else signal.SIGTERM)

Do not refactor `harness/login.py::_terminate_process_group` to use this module. It is out of scope (see DO-NOT-TOUCH).

### 4.2 `src/skillgate_ai/sandbox.py`

**`_run_streaming`** (lines 201–255):

1. Replace the explicit `stdin=subprocess.DEVNULL` in the `Popen` call with `**isolated_kwargs()`. Keep `stdout=subprocess.PIPE` and `stderr=subprocess.PIPE` explicit. Never inherit either.
2. Register the live group right after the `Popen` call (`_LIVE.add(proc)`) and remove it in `finally` (`_LIVE.discard(proc)`).
3. Timeout branch: replace `proc.kill()` with `kill_group(proc)`, then `proc.wait()`.
4. Add `except BaseException:` after the timeout branch that calls `kill_group(proc)`, then `proc.wait(timeout=_PIPE_JOIN_SEC)` (ignore `TimeoutExpired`), then re-raise. This covers `KeyboardInterrupt` and `CheckAborted`. Without it, a Ctrl-C in `skillgate ui` would no longer reach the child, now that the child has its own session.
5. Add a module-level `_LIVE: set[subprocess.Popen[str]]` guarded by a `threading.Lock`. Add `atexit.register(_kill_live_groups)`, where `_kill_live_groups` calls `kill_group` on every entry. That way, when `skillgate mcp` exits (the client closed stdin) or `skillgate ui` shuts down, the in-flight harness tree goes with it. Worker threads are daemons, so step 4 alone does not run at interpreter exit.

**`LocalSandbox.run` non-streaming branch** (lines 105–117): **no change to session behaviour.**

- This path runs only when `output_sink is None`, which today means CLI `skillgate check` with no `RunControl`. MCP never takes it.
- The CLI relies on the terminal's Ctrl-C reaching the foreground process group, harness included. A new session would orphan the harness on Ctrl-C, because `subprocess.run` kills only the direct child.
- It already has `stdin=DEVNULL` and `capture_output=True`. Add one comment line saying it deliberately stays in the caller's group, and why.

**`DockerSandbox.run`**: no direct change. Its streaming branch goes through `_run_streaming` and inherits the fix. Its non-streaming branch stays as it is, for the same reason as above.

### 4.3 `src/skillgate_ai/harness/auth.py`

Change the three probes `_probe_codex_login_status`, `_probe_cursor_login_status` and `_probe_claude_login_status`: add `**isolated_kwargs()` to each `subprocess.run(...)` call. Keep `capture_output=True`, `text=True`, `timeout` and `check=False` unchanged.

These probes are short-lived (5 s timeout) and exit on their own, so the new session cannot orphan anything meaningful. They run from MCP/UI worker threads, where H1 applies.

### 4.4 `src/skillgate_ai/live.py`, `RunControl._terminate` (line ~368)

The harness child is now a session leader, so `process.terminate()` alone would leave node and its tool shells running.

- Replace `process.terminate()` with `signal_group(process, signal.SIGTERM)`.
- Replace `process.kill()` in `hard_kill` with `kill_group(process)`.
- Keep the `getattr(process, "poll", None)` guard. Tests pass fakes that are not `Popen`. `signal_group` calls `proc.poll()` and `proc.pid`, so wrap the call: if the object has no `pid`, fall back to today's `process.terminate()` / `process.kill()`.

### 4.5 MCP stdio guard: `src/skillgate_ai/mcp/stdio_guard.py` (new) and `mcp/server.py::serve`

New module (stdlib only, no SDK import):

    """Own fd 0/1 for the MCP protocol; point the real fd 0/1 at devnull/stderr.

    After install(): fd 1 -> stderr, fd 0 -> /dev/null, sys.stdout -> sys.stderr,
    sys.stdin -> devnull. The protocol uses private dup'd fds that children never
    inherit (close_fds=True default; os.dup fds are non-inheritable by default).
    """

    @dataclass(frozen=True)
    class ProtocolStreams:
        stdin: TextIO   # TextIOWrapper(os.fdopen(proto_in, "rb"), encoding="utf-8", errors="replace")
        stdout: TextIO  # TextIOWrapper(os.fdopen(proto_out, "wb"), encoding="utf-8", line_buffering=False)

    def install() -> ProtocolStreams:
        sys.stdout.flush()
        proto_in = os.dup(0)
        proto_out = os.dup(1)
        devnull = os.open(os.devnull, os.O_RDONLY)
        os.dup2(devnull, 0)
        os.close(devnull)
        os.dup2(2, 1)
        sys.stdin = open(os.devnull, encoding="utf-8")
        sys.stdout = sys.stderr
        return ProtocolStreams(...)

Notes for the implementer:

- `os.dup` returns non-inheritable fds (PEP 446). `os.dup2` targets 0/1 stay inheritable, which is what we want: children inherit `/dev/null` and stderr.
- Call `install()` once, **before** anything else in `serve()`.
- Add a `SKILLGATE_MCP_NO_STDIO_GUARD=1` escape hatch only if a test needs it. Default is the guard on. Do not document the hatch for users.

`mcp/server.py::serve` becomes:

    def serve(root: Path) -> None:
        streams = stdio_guard.install()
        server = build_server(McpContext.for_root(root))
        anyio.run(_run_stdio, server, streams)


    async def _run_stdio(server: FastMCP, streams: ProtocolStreams) -> None:
        from mcp.server.stdio import stdio_server

        async with stdio_server(
            stdin=anyio.wrap_file(streams.stdin),
            stdout=anyio.wrap_file(streams.stdout),
        ) as (read_stream, write_stream):
            low = server._mcp_server  # SDK 1.30: FastMCP.run_stdio_async does exactly this
            await low.run(read_stream, write_stream, low.create_initialization_options())

- This mirrors `FastMCP.run_stdio_async` from `mcp==1.30.0` (`fastmcp/server.py:769-776`), but with explicit streams. `stdio_server(stdin=, stdout=)` has been a public parameter since 1.x.
- `_mcp_server` is private. Add a comment that pins it to the SDK version, and add the unit test `test_serve_uses_private_protocol_streams` (§6) so an SDK bump that renames it fails loudly.
- `cli/cmd_mcp.py`: no logic change. Its error paths already use `typer.echo(..., err=True)`. A `SkillGateError` raised after `install()` still lands on stderr, because fd 1 now *is* stderr.

### 4.6 Docs

- `docs/specs/mcp-server.md` §2 "Rules", stdout bullet. Append: "Enforced by `mcp/stdio_guard.install()`: the protocol runs on private dup'd fds; fd 1 → stderr, fd 0 → /dev/null for the server's lifetime. Every external CLI child (harness, auth probe) is spawned via `child_io.isolated_kwargs()` (stdin DEVNULL, own session on POSIX, close_fds)."
- `docs/mcp.md` § "Claude Code" (after the `claude mcp add` block). Add:

  > **Headless (`claude -p`)**: non-interactive runs cannot answer permission prompts, so allow the Skill Gate tools up front:
  >
  >     claude -p "Run skillgate check_start on skills/pdf, poll until done, summarize" \
  >       --allowedTools "mcp__skillgate"
  >
  > `mcp__skillgate` allows every tool from the server named `skillgate`. Allow single tools with names like `mcp__skillgate__check_start`. Use `--mcp-config <file>` (plus `--strict-mcp-config` to ignore other configured servers) when the server is not registered via `claude mcp add`.

  **Verify before merging:** run `claude --help` locally and confirm that the flag spelling `--allowedTools` / `--allowed-tools` (both listed in current help), `--mcp-config` and `--strict-mcp-config` are present. Also confirm whether the installed version accepts the `mcp__skillgate__*` wildcard form. If it does, mention it as equivalent; if not, document only `mcp__skillgate`. Do not guess: the server-level rule `mcp__<server>` is the documented form.

---

## 5. Step order for the implementer

Follow the repo skills (`test-driven-vibe`, `error-driven-debugger`): red tests before fixes.

0. **Confirm the cause (no commit).** Run `python scripts/mcp_stdio_repro.py --harness cursor-agent --runs 10` with `CURSOR_API_KEY` **unset** (CLI login), then again with it **set**.
   - Expected under H1: failures cluster in the unset run, because the probe runs only without the key.
   - For more evidence, temporarily log `fcntl.fcntl(0, fcntl.F_GETFL) & os.O_NONBLOCK` to stderr before and after `_probe_cursor_login_status` in a scratch branch. Also capture the server's exit status: the repro's server stderr plus a negative returncode means it was killed by a signal (H2). EAGAIN or a traceback in the stdin reader means H1.
   - Record the findings in the PR description. Proceed with the full fix either way.
1. Add `tests/test_child_io.py` and the new `tests/test_sandbox.py` cases (§6.1, §6.2). Run them and see them **red**.
2. Implement `child_io.py` (§4.1) and the `sandbox.py` changes (§4.2). Make §6.2 green.
3. Add the `live.py` group-kill (§4.4). Make `test_run_control_kill_terminates_process_group` green.
4. Add the auth probe test (§6.3), red, then the `auth.py` change (§4.3), green.
5. Add `tests/test_mcp_stdio_guard.py` (§6.4) and the regression e2e (§6.5). Run them and see the e2e **red** on today's `serve`.
6. Implement `mcp/stdio_guard.py` and the `serve()` rewrite (§4.5). Everything green.
7. Make the doc edits (§4.6). Run `claude --help` to verify the flags.
8. Run the full local gate: `pytest -q`, `ruff check`, `ruff format --check`, `mypy src`, `skillgate check skills/pdf`, `skillgate check skills/pdf-sabotaged --expect-fail`.
9. Re-run `scripts/mcp_stdio_repro.py --harness cursor-agent --runs 10` with the key unset and with it set. Expect 20/20 terminal statuses and zero `ClosedResourceError`. Paste the summary into the PR.

---

## 6. Tests

All POSIX-only cases use `@pytest.mark.skipif(sys.platform == "win32", reason="POSIX sessions")`. Child scripts run with `sys.executable`. Any case that spawns `skillgate mcp` carries `@pytest.mark.timeout(60)`.

Use a `_RecordingSink` test double that implements `OutputSink` (`on_line` appends; `attach_process` stores; `detach_process`; `should_abort` returns `None`). If `tests/helpers.py` already has one, reuse it.

### 6.1 `tests/test_child_io.py` (new)

- `test_isolated_kwargs_posix`: on POSIX, assert `isolated_kwargs() == {"stdin": subprocess.DEVNULL, "close_fds": True, "start_new_session": True}`.
- `test_signal_group_kills_grandchild`:
  - Start `Popen([sys.executable, "-c", <spawn grandchild `sleep 60`, write its pid to a tmp file, then sleep 60>], **isolated_kwargs())`.
  - Wait for the pid file, then call `kill_group(proc)`.
  - Assert `proc.wait(5)` returns, and that within 3 s `os.kill(grandchild_pid, 0)` raises `ProcessLookupError`. Poll in 0.1 s steps; the grandchild is not our child, so poll only.
- `test_signal_group_noop_after_exit`: for a finished proc, `kill_group` raises nothing.

### 6.2 `tests/test_sandbox.py` (additions)

- `test_streaming_child_runs_in_new_session`:
  - Create `LocalSandbox(tmp_path)` with `output_sink = _RecordingSink()`.
  - Run `["python3", "-c", "import os; print(os.getsid(0), os.getpgrp(), os.getpid())"]`.
  - Parse stdout and assert `sid == pgrp == child_pid`, `sid != os.getsid(0)`, and `pgrp != os.getpgrp()`.
- `test_streaming_child_stdin_is_devnull`: with the streaming sink, run `python3 -c "import sys; print(repr(sys.stdin.read()))"` and assert `stdout.strip() == "''"`.
- `test_nonstreaming_child_stays_in_caller_group`: with `output_sink=None` and the same script as the first case, assert `pgrp == os.getpgrp()`. This locks in the deliberate CLI non-change.
- `test_streaming_child_group_signal_cannot_reach_parent`:
  - Run a wrapper **in a subprocess** (`sys.executable -c`) so a regression cannot kill pytest. The wrapper builds a `LocalSandbox` with a minimal sink and runs a child that does `signal.signal(SIGTERM, SIG_IGN); os.killpg(0, signal.SIGTERM); print("sent")`.
  - The wrapper then prints `"survived"`.
  - Assert the wrapper exits 0 and its stdout contains `survived`.
  - This is red on today's code: the wrapper and child share a group, so the wrapper dies with returncode `-15`.
- `test_streaming_timeout_kills_process_group`:
  - Use the streaming sink. The child spawns a `sleep 60` grandchild, writes its pid to `tmp_path / "gc.pid"`, then sleeps 60.
  - Call `LocalSandbox.run(..., timeout=1)` and expect it to raise the `agent_timeout_error` `SkillGateError`.
  - Assert the grandchild is gone within 3 s.
- `test_run_control_kill_terminates_process_group`:
  - Create a `RunControl("t")` with `begin_task("x")` and use it as the sink.
  - Run the grandchild script on a thread through `LocalSandbox.run`. Once `gc.pid` exists, call `control.request_kill()`.
  - Assert the run raises or returns within 5 s, and that the grandchild is gone within 3 s.
- `test_streaming_registers_and_clears_live_group`: during a run, `proc in sandbox._LIVE` (check from the sink's `attach_process`). After the run, `_LIVE` is empty.

### 6.3 `tests/test_harness_auth.py` (addition)

- `test_login_status_probes_isolate_stdio`:
  - Monkeypatch `skillgate_ai.harness.auth.subprocess.run` with a recorder that returns `CompletedProcess(args, 0, stdout="Logged in", stderr="")`.
  - Call `_probe_cursor_login_status("/x/agent")`, `_probe_codex_login_status("/x/codex")` and `_probe_claude_login_status("/x/claude")`.
  - For each recorded call, assert `kwargs["stdin"] is subprocess.DEVNULL`, `kwargs["capture_output"] is True`, `kwargs["close_fds"] is True`, and on POSIX `kwargs["start_new_session"] is True`.

### 6.4 `tests/test_mcp_stdio_guard.py` (new; `pytest.importorskip("mcp")` only for the last case)

Each guard case runs a short Python program in a subprocess. `dup2` on pytest's own fds would corrupt capture. The program receives the guard via `from skillgate_ai.mcp.stdio_guard import install`.

- `test_guard_routes_stray_stdout_to_stderr`:
  - The program calls `s = install()`, then `print("stray-print")`, `os.write(1, b"stray-fd\n")`, `subprocess.run(["sh", "-c", "echo stray-child"])`, then `s.stdout.write("PROTO\n"); s.stdout.flush()`.
  - Assert `proc.stdout == "PROTO\n"` **exactly**, and `proc.stderr` contains `stray-print`, `stray-fd` and `stray-child`.
- `test_guard_children_see_devnull_stdin_and_protocol_keeps_bytes`:
  - Feed `input='{"jsonrpc":"2.0"}\n'`. The program does `s = install()`, runs `subprocess.run([sys.executable, "-c", "import sys; print(repr(sys.stdin.read()), file=sys.stderr)"])` with **no** `stdin=` (deliberately inherited), then `print(s.stdin.readline().strip(), file=sys.stderr)`.
  - Assert stderr contains `''` (the child got EOF) **and** `{"jsonrpc":"2.0"}` (the protocol line was not stolen).
- `test_guard_protocol_fds_not_inherited`: after `install()`, the program spawns a child that tries `os.fstat(<proto_out fd number passed via argv>)`. Assert the child reports `OSError` (EBADF).
- `test_serve_uses_private_protocol_streams`:
  - Monkeypatch `mcp.server.stdio.stdio_server` with an async context manager that records its `stdin`/`stdout` kwargs and yields dummy streams.
  - Monkeypatch `FastMCP._mcp_server.run` with a no-op coroutine, and `stdio_guard.install` with a stub that returns `ProtocolStreams(io.StringIO(), io.StringIO())`.
  - Call `serve(tmp_path)` and assert both kwargs are non-None and wrap the stub streams. This guards the private `_mcp_server` attribute against SDK drift.

### 6.5 Regression e2e: `tests/test_mcp_server.py` (addition)

`test_stdio_stays_valid_while_harness_abuses_stdio`, with `@pytest.mark.timeout(90)` and POSIX-only.

**Setup**

- Copy `skills/pdf` into `tmp_path/skills/pdf` and call `ensure_demo_pdfs(...)`, same as the existing `ctx` fixture.
- Write a fake cursor CLI `tmp_path/bin/agent` with shebang `#!{sys.executable}`, mode 0o755.
  - **When `argv[1] == "status"`**:
    1. Set `O_NONBLOCK` on fd 0 (`fcntl`). Wrap the attempt in `try`; it fails harmlessly on `/dev/null`.
    2. Try `os.read(0, 4096)` after `select.select([0], [], [], 0.5)`.
    3. Print `Logged in as test@example.com`, exit 0.
  - **Otherwise (the task run)**:
    1. Repeat the same `O_NONBLOCK` + read on fd 0.
    2. `signal.signal(SIGHUP, SIG_IGN); signal.signal(SIGTERM, SIG_IGN); os.killpg(0, signal.SIGHUP); os.killpg(0, signal.SIGTERM)`.
    3. Write `"NOT-JSON-RPC garbage\n"` to fd 1 and to fd 2.
    4. Print one minimal cursor stream-json line. Copy the shape from `tests/fixtures/cursor_stream_partial_run.jsonl`, first `{"type":"result",...}` row.
    5. Exit 0.
    - The check outcome (pass/fail) is irrelevant. Only transport survival is asserted.
- Build the server env from scratch: start from `os.environ` and drop every `*_API_KEY`, `CURSOR_*`, `ANTHROPIC_*`, `OPENAI_*` and `CODEX_*` var.
  - Set `PYTHONPATH` the same way `test_stdio_roundtrip_list_tools` does.
  - Set `CURSOR_AGENT_BIN=<tmp_path/bin/agent>`, put `tmp_path/bin` first on `PATH`, and set `HOME=tmp_path/home`. Keep `~/.skillgate` judge fallback and real CLI logins out.
  - Set **`ANTHROPIC_API_KEY=sk-test-dummy`** so `check_start`'s `has_any_key` gate passes, while cursor still has **no** API key. `_cursor_ready` must then run the fake `status` probe, which exercises H1.
- Run `skillgate mcp --root tmp_path` via `StdioServerParameters`, exactly as in `test_stdio_roundtrip_list_tools`.

**Body (async)**

1. `initialize()`.
2. `call_tool("check_start", {"skill": "pdf", "harness": "cursor-agent", "case_ids": ["extract-hello"], "no_judge": True, "timeout_sec": 30})`. Assert `isError` is false and parse `id`.
3. Every 0.2 s (fast polling widens the race window that H1 needs), `call_tool("check_poll", {"run_id": id})` until `status in {"done", "error"}`, with a 60 s cap.
4. Afterwards, `list_tools()` still returns `EXPECTED_TOOLS`.

**Assertions**

- No exception escapes the `async with`. In particular, neither `anyio.ClosedResourceError` nor `McpError`/`BrokenResourceError`.
- Every `check_poll` result parses as JSON with a `status` key.
- The final status is `"done"` or `"error"`, **not** a transport failure.
- `list_tools()` succeeds after completion.

**Red/green expectation:** on today's code the SIGHUP/SIGTERM to group 0 hits the MCP server (H2), and the probe shares fd 0 (H1), so the test fails deterministically. After the fix it passes. If this is not red before the fix, the fake script is not reaching the hazards: fix the test, not the threshold.

### 6.6 Existing tests that must stay green unchanged

`tests/test_mcp_server.py::test_stdio_roundtrip_list_tools`, `tests/test_mcp_tools.py` (including `test_tools_write_nothing_to_stdout`), `tests/test_run_registry.py`, `tests/test_live_only.py`, `tests/test_harness_agents.py`, `tests/test_mcp_cli.py`, `tests/integration/*`.

---

## 7. Acceptance criteria

1. `scripts/mcp_stdio_repro.py --harness cursor-agent --runs 10` reaches a terminal status 10/10 with `CURSOR_API_KEY` unset (CLI login), and 10/10 with it set. Zero `ClosedResourceError`.
2. The same script with `--harness claude --runs 5` reaches 5/5 (no regression).
3. Every harness `Popen` on the streaming path has `stdin=DEVNULL`, `stdout=PIPE`, `stderr=PIPE`, `close_fds=True` and, on POSIX, `start_new_session=True`. Every auth status probe has `stdin=DEVNULL`, `capture_output=True`, `close_fds=True` and, on POSIX, `start_new_session=True`.
4. Skip, kill and timeout on a live check leave **no** surviving descendant of the harness (`test_run_control_kill_terminates_process_group`, `test_streaming_timeout_kills_process_group`).
5. Under `skillgate mcp`, bytes on real stdout are exactly the JSON-RPC frames. Stray Python prints, raw fd 1 writes and inherited-stdout children all land on stderr (§6.4).
6. CLI `skillgate check` keeps today's process-group behaviour (`test_nonstreaming_child_stays_in_caller_group`), and Ctrl-C still stops the harness.
7. `pytest -q`, `ruff check`, `ruff format --check` and `mypy src` are all clean. `skillgate check skills/pdf` exits 0, and `skillgate check skills/pdf-sabotaged --expect-fail` behaves as today.
8. `docs/mcp.md` has the headless `claude -p` note, with flags verified against the local `claude --help`. `docs/specs/mcp-server.md` §2 names the enforcement mechanism.

---

## 8. DO-NOT-TOUCH

- Harness argv builders: `_cursor_exec_command`, `_codex_exec_command`, `_claude_code_exec_command` in `harness/commands.py`, and `_sandbox_run` (it already delegates to `sandbox.run`, so no change is needed).
- `harness/agents.py`: no changes. The fix reaches it through `sandbox.run` and `auth`.
- `_sandbox_env` / `_SANDBOX_ENV_ALLOW`, `with_running_python`, `prepare_workspace`.
- `LocalSandbox.run` and `DockerSandbox.run` non-streaming `subprocess.run` calls: comment only, no new kwargs.
- `harness/login.py` (`_run_inherited`, `_terminate_process_group`): it already uses `start_new_session=True` and must keep the user's TTY. Do not merge it into `child_io`.
- Non-check `subprocess` callers: `sync.py`, `compare_git.py`, `api.py`, `workspace_outputs.py`, the example `agent_entry.py` scripts.
- `run_registry.py`, `gate.py` and `engine/task.py`: no changes. No per-run stdout redirection, and the `source` plumbing stays as it is.
- MCP tool names, schemas, return shapes and `SERVER_INSTRUCTIONS` in `mcp/server.py`. Only `serve()` changes.
- The UI server (`server.py`, `api*.py`) and the React app (`web/`). Their only behaviour change is that live harness children now run in their own session, and the atexit cleanup kills them on shutdown.
- No dependency bumps (`mcp` stays at the current pin), and no unrelated ruff or format churn.
