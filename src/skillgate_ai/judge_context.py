"""Judge-facing context: extracted file text, agent trajectory, skill instructions."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from skillgate_ai.document_text import extract_document_text
from skillgate_ai.judge_bank import (
    CHECK_CELL_ORDER,
    OUTCOME_SCORING_NOTES,
    SOFT_CELL_ORDER,
    WHY_SUFFIX,
)
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
    pending: dict[str, dict[str, Any]] = {}
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
            continue
        if kind in {"assistant", "user", "tool_use", "tool_result"}:
            _ingest_claude_stream_event(runs, pending, obj)
    return _trim_command_runs(runs)


def _claude_message_parts(obj: dict[str, Any]) -> list[dict[str, Any]]:
    if obj.get("type") in {"tool_use", "tool_result"}:
        return [obj]
    message = obj.get("message")
    if not isinstance(message, dict):
        return []
    parts = message.get("content")
    if isinstance(parts, list):
        return [part for part in parts if isinstance(part, dict)]
    return []


def _claude_tool_command(part: dict[str, Any]) -> str:
    name = str(part.get("name") or "tool").strip() or "tool"
    args = part.get("input") or part.get("args") or part.get("arguments")
    if not isinstance(args, dict):
        args = {}
    detail = ""
    for key in ("command", "cmd", "script", "file_path", "path", "pattern", "query"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            detail = value.strip()
            break
    if name.lower() in {"bash", "shell", "run"} and detail:
        return detail
    return f"{name} {detail}".strip()


def _claude_tool_output(part: dict[str, Any]) -> str:
    raw = part.get("content")
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, list):
        bits: list[str] = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                bits.append(item.strip())
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str) and text.strip():
                    bits.append(text.strip())
        return "\n".join(bits)
    for key in ("output", "result", "stdout"):
        value = part.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _ingest_claude_stream_event(
    runs: list[dict[str, Any]],
    pending: dict[str, dict[str, Any]],
    obj: dict[str, Any],
) -> None:
    for part in _claude_message_parts(obj):
        kind = part.get("type")
        if kind == "tool_use":
            command = _claude_tool_command(part)
            call_id = str(part.get("id") or "").strip()
            row = {
                "command": command[:500],
                "output": None,
                "tool": str(part.get("name") or "").strip() or None,
            }
            if call_id:
                pending[call_id] = row
            runs.append(row)
            continue
        if kind != "tool_result":
            continue
        output = _claude_tool_output(part)
        call_id = str(part.get("tool_use_id") or part.get("id") or "").strip()
        row = pending.pop(call_id, None) if call_id else None
        if row is not None:
            row["output"] = output[:_COMMAND_OUTPUT_CAP] if output else None
            continue
        runs.append(
            {
                "command": "",
                "output": output[:_COMMAND_OUTPUT_CAP] if output else None,
            }
        )


def _is_shell_evidence(run: dict[str, Any]) -> bool:
    tool = str(run.get("tool") or "").strip().lower()
    if tool in {"bash", "shell", "run"}:
        return True
    command = str(run.get("command") or "")
    output = str(run.get("output") or "")
    if _TEST_LINE_RE.search(command) or _PYTEST_RESULT_RE.search(output):
        return True
    return not tool and bool(command)


def _trim_command_runs(runs: list[dict[str, Any]], *, limit: int = 30) -> list[dict[str, Any]]:
    """Keep shell/test evidence when a long trajectory would drop the last pytest."""
    if len(runs) <= limit:
        return runs
    kept = list(runs)
    index = 0
    while len(kept) > limit and index < len(kept):
        if _is_shell_evidence(kept[index]):
            index += 1
        else:
            kept.pop(index)
    if len(kept) > limit:
        return kept[-limit:]
    return kept


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
    command_log: str | None = None,
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
    command_runs = parse_command_runs(command_log if command_log else transcript)
    if command_log and not command_runs:
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


_RULES_CAP = 2500
_EVIDENCE_CAP = 1500
_ADHERENCE_NOTE = (
    "Grade only against the listed rules and the evidence below. "
    "When the listed rules show no violation and the deterministic scorers passed, "
    "answer Fully followed with high confidence (0.9 or above). Use Minor deviation "
    "only when a listed rule was skipped in a small way. Do not hedge or split "
    "confidence between Fully followed and Minor deviation when no listed rule was "
    "broken. Style, tool choice, or extra steps that are not listed rules are not a "
    "deviation and must not lower confidence."
)


_WHY_NONE = "none"
_REASON_CELLS = frozenset((*CHECK_CELL_ORDER, *SOFT_CELL_ORDER))


def _clip_reason_line(text: str, limit: int = 88) -> str:
    line = text.strip().splitlines()[0].strip() if text.strip() else ""
    if len(line) > limit:
        return line[: limit - 1].rstrip() + "…"
    return line


def _state_reply(state: Mapping[str, Any] | None) -> str:
    if not isinstance(state, Mapping):
        return ""
    actual = state.get("actual_output")
    if isinstance(actual, Mapping):
        actual = actual.get("body") or actual.get("content") or actual.get("text")
    if isinstance(actual, str) and actual.strip():
        return actual.strip()
    files = state.get("workspace_files") or state.get("artifacts")
    if isinstance(files, list):
        for row in files:
            if not isinstance(row, Mapping):
                continue
            path = str(row.get("path") or "").replace("\\", "/").lower()
            if path.endswith("reply.txt"):
                body = row.get("content") or row.get("body") or row.get("extracted_text")
                if isinstance(body, str) and body.strip():
                    return body.strip()
    return ""


def _state_call_names(state: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(state, Mapping):
        return []
    names: list[str] = []
    seen: set[str] = set()

    def add(raw: Any) -> None:
        name = str(raw or "").strip()
        if not name or name in seen:
            return
        seen.add(name)
        names.append(name)

    trajectory = state.get("agent_trajectory")
    if isinstance(trajectory, Mapping):
        for key in ("commands", "command_runs"):
            rows = trajectory.get(key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, Mapping):
                    argv = row.get("argv")
                    if isinstance(argv, list) and argv:
                        add(argv[0])
                    else:
                        add(row.get("name") or row.get("tool") or row.get("command"))
                elif isinstance(row, str):
                    add(row.split()[0] if row.split() else row)
    path = state.get("path")
    if isinstance(path, Mapping):
        tools = path.get("tools") or path.get("tool_names")
        if isinstance(tools, list):
            for item in tools:
                add(item)
    return names


def evidence_reason_choices(state: Mapping[str, Any] | None) -> list[dict[str, str]]:
    """Short evidence lines the judge can pick as the per-check reason."""
    rows: list[dict[str, str]] = []
    reply = _state_reply(state)
    if reply:
        rows.append(
            {
                "value": "reply",
                "description": f'The agent replied: "{_clip_reason_line(reply)}"',
            }
        )
    calls = _state_call_names(state)
    if calls:
        rows.append(
            {
                "value": "calls",
                "description": "Connector calls: " + ", ".join(calls),
            }
        )
    expected = ""
    if isinstance(state, Mapping):
        raw = state.get("expected_outcome")
        if isinstance(raw, str):
            expected = raw.strip()
    if expected:
        rows.append(
            {
                "value": "expected",
                "description": f"Expected outcome: {_clip_reason_line(expected)}",
            }
        )
    rows.append(
        {
            "value": _WHY_NONE,
            "description": "No short evidence line from this run.",
        }
    )
    return rows


def with_run_reason_questions(
    questions: list[dict[str, Any]],
    state: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Ask the judge to pick a this-run evidence line for each scored check."""
    choices = evidence_reason_choices(state)
    if len(choices) < 2:
        return questions
    extra: list[dict[str, Any]] = []
    seen: set[str] = set()
    for question in questions:
        if not isinstance(question, dict):
            continue
        name = str(question.get("name") or "").strip()
        if not name or name.endswith(WHY_SUFFIX) or name in seen:
            continue
        if name not in _REASON_CELLS:
            continue
        seen.add(name)
        label = str(question.get("instructions") or name).split(" Pick exactly one.")[0]
        extra.append(
            {
                "type": "choice",
                "name": f"{name}{WHY_SUFFIX}",
                "instructions": (
                    f"Why that answer for {label}? Pick the evidence line from this run. "
                    "Do not pick a rubric definition."
                ),
                "choices": [dict(row) for row in choices],
            }
        )
    return [*questions, *extra]


def apply_why_reasons(
    cells: Mapping[str, Any],
    answers: Mapping[str, Any],
    questions: list[dict[str, Any]] | None = None,
) -> None:
    """Copy the judge's evidence-line pick onto each cell that has no written reason."""
    lookup: dict[str, dict[str, str]] = {}
    for question in questions or []:
        if not isinstance(question, dict):
            continue
        name = str(question.get("name") or "")
        if not name.endswith(WHY_SUFFIX):
            continue
        mapping: dict[str, str] = {}
        for row in question.get("choices") or []:
            if not isinstance(row, Mapping):
                continue
            value = str(row.get("value") or "").strip()
            description = str(row.get("description") or "").strip()
            if value:
                mapping[value] = description or value
        lookup[name] = mapping
    from skillgate_ai.judge_bank import extract_choice

    for key, cell in cells.items():
        if not isinstance(cell, dict) or str(cell.get("reason") or "").strip():
            continue
        why_key = f"{key}{WHY_SUFFIX}"
        why = answers.get(why_key)
        choice = extract_choice(why) if why is not None else None
        if not choice or choice == _WHY_NONE:
            continue
        reason = (lookup.get(why_key) or {}).get(choice) or ""
        if not reason and isinstance(why, Mapping):
            reason = str(why.get("reason") or why.get("description") or "").strip()
        if (
            not reason
            and choice not in {_WHY_NONE, "reply", "calls", "expected"}
            and not choice.lower().startswith("no short evidence")
        ):
            reason = choice
        if not reason or reason.lower().startswith("no short evidence"):
            continue
        cell["reason"] = reason
        blob = answers.get(key)
        if isinstance(blob, dict) and not str(blob.get("reason") or "").strip():
            blob["reason"] = reason
        if isinstance(why, dict) and not str(why.get("reason") or "").strip():
            why["reason"] = reason


def stamp_why_on_answers(
    answers: Mapping[str, Any],
    questions: list[dict[str, Any]] | None = None,
) -> None:
    cells = {
        str(key): blob
        for key, blob in answers.items()
        if isinstance(blob, dict) and not str(key).endswith(WHY_SUFFIX)
    }
    apply_why_reasons(cells, answers, questions)


def attach_adherence_context(
    questions: list[dict[str, Any]],
    state: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Put the skill's rules and the run evidence on Followed the rules?"""
    if not questions or not isinstance(state, Mapping):
        return questions
    extra = _adherence_extra(state)
    if not extra:
        return questions
    out: list[dict[str, Any]] = []
    for question in questions:
        if not isinstance(question, dict) or question.get("name") != "instruction_adherence":
            out.append(question)
            continue
        item = dict(question)
        instructions = str(item.get("instructions") or "Followed the rules?").rstrip()
        if instructions.endswith("Pick exactly one."):
            instructions = instructions[: -len("Pick exactly one.")].rstrip()
        item["instructions"] = f"{instructions} {extra} Pick exactly one."
        choices = item.get("choices")
        if isinstance(choices, list):
            item["choices"] = [
                _enrich_adherence_choice(choice) if isinstance(choice, dict) else choice
                for choice in choices
            ]
        out.append(item)
    return out


def _adherence_extra(state: Mapping[str, Any]) -> str:
    rules = _excerpt(state.get("skill_instructions"), _RULES_CAP)
    evidence = _evidence_excerpt(state)
    if not rules and not evidence:
        return ""
    parts = [_ADHERENCE_NOTE]
    if rules:
        parts.append(f"Rules:\n{rules}")
    if evidence:
        parts.append(f"Evidence:\n{evidence}")
    return "\n\n".join(parts)


def _evidence_excerpt(state: Mapping[str, Any]) -> str:
    bits: list[str] = []
    scores = state.get("scorer_results")
    if isinstance(scores, list):
        for item in scores:
            if not isinstance(item, Mapping):
                continue
            name = str(item.get("scorer") or "").strip()
            detail = str(item.get("detail") or item.get("headline") or "").strip()
            if name:
                mark = "passed" if item.get("passed") else "failed"
                bits.append(f"{name} {mark}" + (f" — {detail}" if detail else ""))
    expected = state.get("expected_outcome")
    if isinstance(expected, str) and expected.strip():
        bits.append(f"expected outcome: {expected.strip()}")
    files = state.get("workspace_files") or state.get("artifacts")
    if isinstance(files, list):
        names = [
            str(row.get("path"))
            for row in files
            if isinstance(row, Mapping) and row.get("path")
        ]
        if names:
            bits.append("workspace files: " + ", ".join(names[:12]))
    return _excerpt("\n".join(bits), _EVIDENCE_CAP)


def _excerpt(raw: Any, cap: int) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    return text if len(text) <= cap else text[:cap]


def _enrich_adherence_choice(choice: dict[str, Any]) -> dict[str, Any]:
    value = str(choice.get("value") or "")
    if value != "Fully followed":
        return choice
    item = dict(choice)
    description = str(item.get("description") or "").rstrip()
    note = "When listed rules show no violation, pick this with high confidence."
    if note.lower() not in description.lower():
        item["description"] = f"{description} {note}".strip()
    return item
