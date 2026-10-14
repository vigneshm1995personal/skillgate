"""Collect output files from an eval sandbox workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from skillgate_ai.case_pack import read_capped_text, sniff_output_bytes
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
        else:
            row["size"] = 0
        rows.append(row)
    return rows
