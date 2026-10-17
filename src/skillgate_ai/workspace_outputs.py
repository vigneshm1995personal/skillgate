"""Collect output files from an eval sandbox workspace."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from skillgate_ai.case_pack import read_capped_text, sniff_output_bytes
from skillgate_ai.judge_context import enrich_output_row
from skillgate_ai.suite import TaskSpec

_NARRATION_LINE = re.compile(
    r"^(i['’]ll |i will |let me |i am going to |i['’]m going to |first[, ]|i need to )",
    re.IGNORECASE,
)


def expected_output_paths(task: TaskSpec) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for spec in task.scorers:
        if spec.type != "task_completion":
            continue
        for item in spec.files:
            rel = str(item.path or "").replace("\\", "/").strip()
            if rel and rel not in seen:
                seen.add(rel)
                paths.append(rel)
    return paths


def harness_final_answer(stdout: str) -> str | None:
    """Last Codex agent_message or Cursor/Claude final answer, without narration."""
    last_codex: str | None = None
    last_after_tool: str | None = None
    last_assistant: str | None = None
    result_text: str | None = None
    saw_tool = False
    for line in (stdout or "").splitlines():
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        kind = obj.get("type")
        if kind == "item.completed":
            item = obj.get("item")
            if not isinstance(item, dict):
                continue
            itype = item.get("type")
            if itype == "agent_message":
                body = str(item.get("text") or "").strip()
                if body:
                    last_codex = body
            elif itype in {"command_execution", "file_change"}:
                saw_tool = True
        elif kind == "tool_call":
            saw_tool = True
        elif kind == "assistant":
            if _is_partial_assistant(obj):
                continue
            body = _cursor_assistant_text(obj)
            if not body:
                continue
            last_assistant = body
            if saw_tool:
                last_after_tool = body
        elif kind == "result":
            body = str(obj.get("result") or "").strip()
            if body:
                result_text = body
    if last_codex:
        return last_codex
    if last_after_tool:
        return last_after_tool
    if result_text:
        cleaned = _without_narration(result_text)
        if cleaned:
            return cleaned
    return last_assistant


def persist_harness_answer(workspace: Path, stdout: str) -> Path | None:
    """Write Codex/Cursor final text to output/answer.txt when output/ is empty."""
    output_dir = workspace / "output"
    if output_dir.is_dir() and any(path.is_file() for path in output_dir.rglob("*")):
        return None
    text = harness_final_answer(stdout)
    if not text:
        return None
    dest = output_dir / "answer.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return dest


def collect_workspace_outputs(task: TaskSpec, workspace: Path) -> list[dict[str, Any]]:
    """Paths from the check plus anything under ``output/`` in the workspace."""
    rel_paths: set[str] = set(expected_output_paths(task))
    output_dir = workspace / "output"
    if output_dir.is_dir():
        for path in output_dir.rglob("*"):
            if path.is_file():
                try:
                    rel_paths.add(path.relative_to(workspace).as_posix())
                except ValueError:
                    continue
    rows: list[dict[str, Any]] = []
    for rel in sorted(rel_paths):
        dest = workspace / rel
        present = dest.is_file()
        row: dict[str, Any] = {"path": rel, "present": present}
        if present:
            sniffed = sniff_output_bytes(dest.read_bytes())
            row.update(sniffed)
            if sniffed.get("kind") != "bytes":
                row["body"] = read_capped_text(dest)
            row = enrich_output_row(row, dest)
        else:
            row["size"] = 0
        rows.append(row)
    return rows


def _cursor_assistant_text(obj: dict[str, Any]) -> str | None:
    message = obj.get("message")
    if not isinstance(message, dict):
        return None
    parts = message.get("content")
    if not isinstance(parts, list):
        return None
    texts = [
        str(part.get("text") or "").strip()
        for part in parts
        if isinstance(part, dict) and part.get("type") == "text"
    ]
    joined = "\n".join(text for text in texts if text).strip()
    return joined or None


def _is_partial_assistant(obj: dict[str, Any]) -> bool:
    return "timestamp_ms" in obj and "model_call_id" not in obj


def _without_narration(text: str) -> str:
    blob = (text or "").strip()
    if not blob:
        return ""
    parts = [part.strip() for part in re.split(r"\n\s*\n", blob) if part.strip()]
    while parts and _NARRATION_LINE.match(parts[0]):
        parts.pop(0)
    if parts:
        return "\n\n".join(parts).strip()
    lines = [line.strip() for line in blob.splitlines() if line.strip()]
    while lines and _NARRATION_LINE.match(lines[0]):
        lines.pop(0)
    return "\n".join(lines).strip()
