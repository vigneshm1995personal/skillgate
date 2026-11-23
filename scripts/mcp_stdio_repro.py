#!/usr/bin/env python3
"""Repro: MCP stdio client + check_start + poll until done or server death."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


async def run_once(harness: str, poll_sec: float) -> dict:
    from anyio import BrokenResourceError, ClosedResourceError
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = str(ROOT / "src")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "skillgate_ai.cli", "mcp", "--root", str(ROOT)],
        env=env,
    )
    t0 = time.monotonic()
    outcome: dict = {"harness": harness, "pass": False, "error": None, "duration": 0.0}
    try:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            started = await session.call_tool(
                "check_start",
                {
                    "skill": "pdf",
                    "case_ids": ["extract-hello"],
                    "harness": harness,
                },
            )
            text = started.content[0].text if started.content else "{}"
            run_id = json.loads(text).get("id")
            if not run_id:
                outcome["error"] = f"no run id: {text[:200]}"
                return outcome
            last = None
            while True:
                await asyncio.sleep(poll_sec)
                polled = await session.call_tool(
                    "check_poll",
                    {"run_id": run_id, "include_report": False},
                )
                body = json.loads(polled.content[0].text if polled.content else "{}")
                last = body
                status = body.get("status")
                if status in {"done", "error", "cancelled"}:
                    outcome["pass"] = status == "done"
                    outcome["status"] = status
                    outcome["current_task_id"] = body.get("current_task_id")
                    break
                elapsed = time.monotonic() - t0
                if elapsed > 600:
                    outcome["error"] = "timeout"
                    break
            outcome["last"] = last
    except (
        OSError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
        BrokenResourceError,
        ClosedResourceError,
    ) as exc:
        outcome["error"] = f"{type(exc).__name__}: {exc}"
    outcome["duration"] = round(time.monotonic() - t0, 1)
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--harness", default="cursor-agent")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--poll-sec", type=float, default=2.0)
    args = parser.parse_args()
    results = []
    for i in range(args.runs):
        print(f"run {i + 1}/{args.runs} harness={args.harness}", file=sys.stderr, flush=True)
        results.append(asyncio.run(run_once(args.harness, args.poll_sec)))
        print(json.dumps(results[-1]), file=sys.stderr, flush=True)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
