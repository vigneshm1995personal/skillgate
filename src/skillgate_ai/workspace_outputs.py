"""Collect output files from an eval sandbox workspace."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from skillgate_ai.case_pack import read_capped_text, sniff_output_bytes
from skillgate_ai.judge_context import enrich_output_row
from skillgate_ai.suite import TaskSpec


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
    """Last Codex agent_message or Cursor/Claude `result` text."""
    last: str | None = None
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
            if isinstance(item, dict) and item.get("type") == "agent_message":
                body = str(item.get("text") or "").strip()
                if body:
                    last = body
        elif kind == "result":
            body = str(obj.get("result") or "").strip()
            if body:
                last = body
    return last


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
