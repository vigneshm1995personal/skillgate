"""LLM-harness RUN: lines → allowlisted shell + OTLP spans for the UI timeline."""

from __future__ import annotations

import secrets
import shlex

from skillgate_ai.spans import STATUS_ERROR, STATUS_OK, make_span


def llm_run_spans(selected: str | None, runs: list[tuple[list[str], int]]) -> list[dict]:
    trace_id = secrets.token_hex(16)
    spans: list[dict] = []
    if selected:
        spans.append(
            make_span(
                name="skill.select",
                trace_id=trace_id,
                attributes={"gen_ai.tool.name": "select", "file.name": selected},
            )
        )
    for command, code in runs:
        spans.append(
            make_span(
                name="tool.shell",
                trace_id=trace_id,
                status=STATUS_OK if code == 0 else STATUS_ERROR,
                attributes={
                    "gen_ai.tool.name": "shell",
                    "gen_ai.tool.call.arguments": " ".join(command),
                },
            )
        )
    return spans


def parse_run_lines(text: str) -> list[list[str]]:
    commands: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("RUN:"):
            payload = stripped[4:].strip()
            try:
                argv = shlex.split(payload)
            except ValueError:
                argv = payload.split()
            commands.append(argv)
    return commands


def command_allowed(command: list[str], skill_name: str) -> bool:
    if len(command) < 2:
        return False
    if command[0] not in {"python", "python3"}:
        return False
    script = command[1].replace("\\", "/")
    if script.startswith("-") or ".." in script:
        return False
    needle = f".skillgate/skills/{skill_name}/scripts/"
    return script.startswith(needle) and script.endswith(".py")
