"""Judge-facing context: extracted file text, agent trajectory, skill instructions."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from skillgate_ai.document_text import extract_document_text
from skillgate_ai.judge_bank import OUTCOME_SCORING_NOTES
from skillgate_ai.pack_files import GOLDEN_TAIL_CHARS, read_capped_text
from skillgate_ai.scorers import Score
from skillgate_ai.spans import attr_map, spans_from_jsonl

_TEST_LINE_RE = re.compile(
    r"\b(pytest|vitest|pnpm test|npm test|cargo test|go test|unittest)\b",
    re.IGNORECASE,
)
_PYTEST_RESULT_RE = re.compile(
    r"\b(\d+\s+passed|passed in|PASSED|FAILED|===+\s+\d+ passed)\b",
    re.IGNORECASE,
)
_FILE_CONTENT_CAP = 6000
_COMMAND_OUTPUT_CAP = 2500


def enrich_output_row(row: dict[str, Any], dest: Path) -> dict[str, Any]:
    """Attach extracted text for binary office/PDF outputs."""
    if not row.get("present"):
        return row
    extracted = extract_document_text(dest)
    if not extracted:
        return row
    row["extracted_text"] = extracted
    if row.get("body") is None or row.get("kind") == "bytes":
        row["body"] = extracted
    return row


def skill_instructions_text(skill_root: Path | None, *, fallback: str | None = None) -> str | None:
    body = fallback if fallback and str(fallback).strip() else None
    if body is None and skill_root is not None:
        skill_md = skill_root / "SKILL.md"
        if skill_md.is_file():
            body = read_capped_text(skill_md) or ""
    cleaned = str(body or "").strip()
    if not cleaned:
        return OUTCOME_SCORING_NOTES
    return f"{OUTCOME_SCORING_NOTES}\n\n--- SKILL.md ---\n{_cap_instructions(cleaned)}"


def workspace_files_for_judge(artifacts: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in artifacts or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        content = item.get("body") or item.get("extracted_text")
        if isinstance(content, str) and len(content) > _FILE_CONTENT_CAP:
            content = content[-_FILE_CONTENT_CAP:]
        rows.append(
            {
                "path": path,
                "present": bool(item.get("present")),
                "kind": item.get("kind"),
                "content": content if isinstance(content, str) else None,
            }
        )
    return rows


def parse_command_runs(transcript: str) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for line in (transcript or "").splitlines():
        text = line.strip()
        if not text.startswith("{"):
            if _PYTEST_RESULT_RE.search(text):
                runs.append({"source": "transcript_line", "output": text[:_COMMAND_OUTPUT_CAP]})
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
            if isinstance(item, dict) and item.get("type") == "command_execution":
                _append_command_run(runs, item)
            continue
        if kind == "tool_call":
            tool = obj.get("tool_call")
            if isinstance(tool, dict):
                for key, value in tool.items():
                    if not str(key).endswith("ToolCall"):
                        continue
                    if isinstance(value, dict):
                        args = value.get("args") or value.get("arguments")
                        command = ""
                        if isinstance(args, dict):
                            command = str(
                                args.get("command") or args.get("cmd") or args.get("script") or ""
                            ).strip()
                        runs.append(
                            {
                                "command": command[:500],
                                "output": str(value.get("result") or value.get("output") or "")[
                                    :_COMMAND_OUTPUT_CAP
                                ],
                            }
                        )
    return runs[:30]


def _append_command_run(runs: list[dict[str, Any]], item: dict[str, Any]) -> None:
    command = str(item.get("command") or "").strip()
    output = ""
    for key in (
        "aggregated_output",
        "output",
        "stdout",
        "stderr",
        "combined_output",
        "result",
    ):
        chunk = item.get(key)
        if isinstance(chunk, str) and chunk.strip():
            output = chunk.strip()
            break
    exit_code = item.get("exit_code")
    if exit_code is None:
        exit_code = item.get("exitCode")
    runs.append(
        {
            "command": command[:500],
            "exit_code": exit_code,
            "output": output[:_COMMAND_OUTPUT_CAP] if output else None,
        }
    )


def build_agent_trajectory(
    *,
    spans: list[dict[str, Any]] | None,
    transcript: str,
    path: dict[str, Any] | None,
    scores: list[Score] | list[dict[str, Any]] | None,
    artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    records = list(spans or [])
    if not any(str(span.get("name") or "").startswith(("tool.", "skill.")) for span in records):
        rebuilt = spans_from_jsonl(transcript or "")
        if rebuilt:
            records = rebuilt
    commands: list[dict[str, Any]] = []
    for span in records:
        name = str(span.get("name") or "")
        if not (name.startswith("tool.") or name == "skill.select"):
            continue
        attrs = attr_map(span)
        commands.append(
            {
                "kind": name,
                "tool": attrs.get("gen_ai.tool.name"),
                "args": str(attrs.get("gen_ai.tool.call.arguments") or "")[:500],
                "file": attrs.get("file.path"),
            }
        )
    command_runs = parse_command_runs(transcript)
    test_mentions: list[str] = []
    for line in (transcript or "").splitlines():
        if _TEST_LINE_RE.search(line) or _PYTEST_RESULT_RE.search(line):
            test_mentions.append(line.strip()[:500])
    for run in command_runs:
        output = str(run.get("output") or "")
        if _PYTEST_RESULT_RE.search(output):
            test_mentions.append(output[:500])
    scorer_rows: list[dict[str, Any]] = []
    for item in scores or []:
        if isinstance(item, Score):
            scorer_rows.append(
                {
                    "scorer": item.scorer,
                    "passed": item.passed,
                    "headline": item.headline,
                    "detail": item.detail,
                }
            )
        elif isinstance(item, dict):
            scorer_rows.append(
                {
                    "scorer": item.get("scorer"),
                    "passed": item.get("passed"),
                    "headline": item.get("headline"),
                    "detail": item.get("detail"),
                }
            )
    path_info = path if isinstance(path, dict) else {}
    return {
        "had_path": path_info.get("had_path"),
        "step_count": path_info.get("steps"),
        "error_count": path_info.get("errors"),
        "commands": commands[:40],
        "command_runs": command_runs,
        "test_mentions": test_mentions[:20],
        "scorer_results": scorer_rows,
        "transcript_chars": len(transcript or ""),
        "workspace_file_paths": [
            str(row.get("path"))
            for row in (artifacts or [])
            if isinstance(row, dict) and row.get("present")
        ][:40],
    }


def _cap_instructions(text: str) -> str | None:
    cleaned = str(text or "").strip()
    if not cleaned:
        return None
    if len(cleaned) <= GOLDEN_TAIL_CHARS:
        return cleaned
    return cleaned[:GOLDEN_TAIL_CHARS]
