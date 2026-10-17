"""Collect output files from an eval sandbox workspace."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from skillgate_ai.case_pack import read_capped_text, sniff_output_bytes
from skillgate_ai.judge_context import enrich_output_row
from skillgate_ai.suite import TaskSpec

_SKIP_DIR_NAMES = frozenset(
    {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".next",
        "coverage",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        "target",
        ".skillgate",
        ".skillgate-git-home",
    }
)
_MAX_EXTRA_BYTES = 262_144
_EXTRA_TEXT_CAP = 16_000

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


def _skipped_rel(rel: str) -> bool:
    return any(part in _SKIP_DIR_NAMES for part in Path(rel).parts)


def _protected_output(rel: str, expected: set[str]) -> bool:
    return rel in expected or rel.startswith("output/")


def _git_env(workspace: Path) -> dict[str, str]:
    scratch = workspace / ".skillgate-git-home"
    scratch.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["HOME"] = str(scratch)
    env["GIT_CONFIG_GLOBAL"] = str(scratch / "no-gitconfig")
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_PAGER"] = "cat"
    return env


def _git_text_artifacts(workspace: Path) -> list[dict[str, Any]]:
    if not (workspace / ".git").exists():
        return []
    env = _git_env(workspace)
    commands = (
        ("git/log.txt", ["git", "log", "-n", "20", "--pretty=format:%h %s"]),
        ("git/diff.txt", ["git", "diff", "--no-ext-diff"]),
        ("git/status.txt", ["git", "status", "--short"]),
    )
    rows: list[dict[str, Any]] = []
    for rel, args in commands:
        try:
            proc = subprocess.run(
                args,
                cwd=workspace,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        text = (proc.stdout or "").strip()
        if not text and proc.returncode != 0:
            text = (proc.stderr or "").strip()
        rows.append(
            {
                "path": rel,
                "present": True,
                "kind": "text",
                "size": len(text),
                "body": text[:_EXTRA_TEXT_CAP],
            }
        )
    return rows


def snapshot_workspace(workspace: Path) -> dict[str, tuple[int, int]]:
    """Size and mtime for files present before the agent runs."""
    found: dict[str, tuple[int, int]] = {}
    if not workspace.is_dir():
        return found
    for path in workspace.rglob("*"):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(workspace).as_posix()
        except ValueError:
            continue
        if _skipped_rel(rel):
            continue
        stat = path.stat()
        found[rel] = (stat.st_size, stat.st_mtime_ns)
    return found


def _agent_changed(rel: str, path: Path, baseline: dict[str, tuple[int, int]] | None) -> bool:
    if baseline is None:
        return True
    previous = baseline.get(rel)
    if previous is None:
        return True
    stat = path.stat()
    return previous != (stat.st_size, stat.st_mtime_ns)


def collect_workspace_outputs(
    task: TaskSpec,
    workspace: Path,
    *,
    baseline: dict[str, tuple[int, int]] | None = None,
) -> list[dict[str, Any]]:
    """Named outputs, ``output/``, and files the agent created or changed."""
    expected = set(expected_output_paths(task))
    rel_paths: set[str] = set(expected)
    if workspace.is_dir():
        for path in workspace.rglob("*"):
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(workspace).as_posix()
            except ValueError:
                continue
            if _skipped_rel(rel):
                continue
            if _protected_output(rel, expected) or _agent_changed(rel, path, baseline):
                rel_paths.add(rel)
    rows: list[dict[str, Any]] = []
    for rel in sorted(rel_paths):
        dest = workspace / rel
        present = dest.is_file()
        row: dict[str, Any] = {"path": rel, "present": present}
        if present:
            size = dest.stat().st_size
            protected = _protected_output(rel, expected)
            if not protected and size > _MAX_EXTRA_BYTES:
                row.update({"kind": "text", "size": size, "body": None, "omitted": "size"})
            else:
                sniffed = sniff_output_bytes(dest.read_bytes())
                row.update(sniffed)
                if sniffed.get("kind") != "bytes":
                    limit = None if protected else _EXTRA_TEXT_CAP
                    row["body"] = read_capped_text(dest, limit=limit)
                row = enrich_output_row(row, dest)
        else:
            row["size"] = 0
        rows.append(row)
    rows.extend(_git_text_artifacts(workspace))
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
