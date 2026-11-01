"""Customer-facing run details for history show and the local UI."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from skillgate_ai.errors import SkillGateError
from skillgate_ai.judge_bank import (
    UNSURE_REVIEW,
    choice_passed,
    is_rubric_reason,
    score_for_choice,
)
from skillgate_ai.openai_http import redact_secrets

_SK_TOKEN = re.compile(r"sk-[A-Za-z0-9_*\-]{8,}")
_BEARER = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-]+")
_ASSIGN = re.compile(
    r"(?i)(\b(?:api[_-]?key|access[_-]?token|secret|password|authorization"
    r"|token)\s*[=:]\s*)[^\s,;]+"
)
_AWS = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_SLACK = re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")

_BUILTIN_LABELS = {
    "task_completion": "Got the job done?",
    "correctness": "Got it right?",
    "instruction_adherence": "Followed the rules?",
    "evidence_action_validity": "Used the right evidence/actions?",
    "result_quality": "Delivered a good result?",
    "path_efficiency": "How it ran",
}
_PREDICATE_PASS = 0.8


def redact_run_text(text: str, secret: str | None = None) -> str:
    """Strip API keys and password-shaped values. Never print secrets."""
    if not text:
        return text
    out = redact_secrets(text, secret)
    out = _SK_TOKEN.sub("sk-***", out)
    out = _BEARER.sub(r"\1***", out)
    out = _ASSIGN.sub(r"\1***", out)
    out = _AWS.sub("AKIA***", out)
    out = _SLACK.sub("xox-***", out)
    return out


def redact_run_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_run_text(value)
    if isinstance(value, list):
        return [redact_run_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): redact_run_value(item) for key, item in value.items()}
    return value


def case_name(task: Mapping[str, Any] | None) -> str:
    if not isinstance(task, Mapping):
        return ""
    name = str(task.get("name") or "").strip()
    if name:
        return name
    return str(task.get("id") or task.get("task_id") or "").strip()


def case_scenario(task: Mapping[str, Any] | None) -> str:
    if not isinstance(task, Mapping):
        return ""
    for key in ("scenario", "setup"):
        value = str(task.get(key) or "").strip()
        if value:
            return value
    return str(task.get("prompt") or "").strip()


def source_label(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"text", "log/text", "from the log/text"}:
        return "from the log/text"
    if raw in {"log", "from the log"}:
        return "from the log"
    if raw in {"judge", "from the judge"}:
        return "from the judge"
    return ""


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _clamp_score(value: float) -> float:
    if value < 0:
        return 0.0
    if value > 1:
        if value <= 10:
            return value / 10.0
        return 1.0
    return value


def _row_score(
    key: str,
    choice: str,
    cell: Mapping[str, Any],
    answer: Mapping[str, Any] | None,
    listed: Mapping[str, Any] | None = None,
) -> float | None:
    for blob in (cell, answer or {}):
        num = _numeric(blob.get("probability"))
        if num is not None:
            return _clamp_score(num)
        num = _numeric(blob.get("score"))
        if num is not None:
            return _clamp_score(num)
    mapped = score_for_choice(key, choice)
    if mapped is not None:
        return mapped
    if listed:
        num = _numeric(listed.get("score"))
        if num is not None:
            return _clamp_score(num)
    passed = cell.get("passed")
    if not isinstance(passed, bool) and listed is not None:
        passed = listed.get("passed")
    if isinstance(passed, bool):
        return 1.0 if passed else 0.0
    guessed = choice_passed(key, choice)
    if guessed is not None:
        return 1.0 if guessed else 0.0
    return None


def _reason_repeats_prompt(label: str, choice: str, reason: str) -> bool:
    compact = " ".join(reason.split())
    ask = " ".join(label.split())
    if not compact:
        return True
    if ask and compact == ask:
        return True
    if choice and compact.lower() == choice.strip().lower():
        return True
    if ask and choice and compact == f"{ask} {choice}".strip():
        return True
    return bool(
        ask
        and compact.lower().startswith(ask.lower())
        and (not choice or compact.lower().endswith(choice.strip().lower()))
    )


def _run_specific_reason(task: Mapping[str, Any], choice: str) -> str:
    parts: list[str] = []
    numeric_choice = False
    if choice:
        try:
            float(choice)
            numeric_choice = True
        except ValueError:
            numeric_choice = False
    if choice and not numeric_choice:
        parts.append(f"{choice} on this run")
    calls = tool_calls(task)
    if calls:
        names: list[str] = []
        seen: set[str] = set()
        for call in calls:
            name = str(call.get("name") or "tool")
            if name in seen:
                continue
            seen.add(name)
            names.append(name)
        parts.append("Connector calls: " + ", ".join(names))
    reply = agent_reply(task)
    if reply:
        line = reply.strip().splitlines()[0].strip()
        if len(line) > 88:
            line = line[:85].rstrip() + "…"
        parts.append(f'Reply: "{line}"')
    happened = str(task.get("happened") or "").strip()
    if happened and happened.lower() not in {
        "unsure, needs review",
        "output matched what was expected.",
        "output matched what was expected",
    }:
        parts.append(happened)
    return ". ".join(parts)


def _row_reason(
    key: str,
    choice: str,
    label: str,
    cell: Mapping[str, Any],
    answer: Mapping[str, Any] | None,
    listed: Mapping[str, Any] | None,
    task: Mapping[str, Any],
) -> str:
    texts: list[str] = []
    for blob in (cell, answer or {}, listed or {}):
        for field in ("reason", "rationale", "explanation", "why", "evidence"):
            text = str(blob.get(field) or "").strip()
            if text:
                texts.append(text)
                break
    for text in texts:
        if is_rubric_reason(key, choice, text):
            continue
        if _reason_repeats_prompt(label, choice, text):
            continue
        return redact_run_text(text)
    return redact_run_text(_run_specific_reason(task, choice))


def check_rows(task: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """One row per judge or text/log check, with score, reason, and source."""
    if not isinstance(task, Mapping):
        return []
    judge = task.get("judge") if isinstance(task.get("judge"), Mapping) else {}
    cells = judge.get("cells") if isinstance(judge.get("cells"), Mapping) else {}
    answers = judge.get("answers") if isinstance(judge.get("answers"), Mapping) else {}
    questions = (
        judge.get("questions") if isinstance(judge.get("questions"), Mapping) else {}
    )
    listed = task.get("check_answers") if isinstance(task.get("check_answers"), list) else []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_row(key: str, cell: Mapping[str, Any] | None = None) -> None:
        if key in seen:
            return
        cell = cell if isinstance(cell, Mapping) else {}
        answer = answers.get(key) if isinstance(answers.get(key), Mapping) else {}
        question = questions.get(key) if isinstance(questions.get(key), Mapping) else {}
        listed_row = next(
            (
                item
                for item in listed
                if isinstance(item, Mapping)
                and (
                    str(item.get("id") or "") == key
                    or str(item.get("label") or "")
                    == str(cell.get("label") or question.get("instructions") or "")
                )
            ),
            {},
        )
        label = (
            str(cell.get("label") or "").strip()
            or str(question.get("instructions") or "").strip()
            or str(listed_row.get("label") or "").strip()
            or _BUILTIN_LABELS.get(key)
            or key
        )
        choice = str(
            cell.get("choice")
            or answer.get("choice")
            or listed_row.get("answer")
            or ""
        ).strip()
        source_raw = (
            cell.get("source")
            or answer.get("source")
            or listed_row.get("source")
            or listed_row.get("source_label")
            or ("judge" if key in _BUILTIN_LABELS else "")
        )
        src = source_label(source_raw) or (
            "from the judge" if key in _BUILTIN_LABELS else ""
        )
        score = _row_score(key, choice, cell, answer, listed_row)
        if score is None and choice:
            guessed = choice_passed(key, choice)
            if guessed is not None:
                score = 1.0 if guessed else 0.0
        reason = _row_reason(key, choice, label, cell, answer, listed_row, task)
        passed = cell.get("passed")
        if not isinstance(passed, bool):
            if listed_row.get("passed") is True or listed_row.get("passed") is False:
                passed = listed_row.get("passed")
            else:
                guessed = choice_passed(key, choice)
                if guessed is None and score is not None:
                    guessed = score >= _PREDICATE_PASS
                passed = guessed
        status = str(cell.get("status") or "").strip().lower()
        if status == "unsure":
            choice = UNSURE_REVIEW
            if passed is False and choice_passed(key, str(cell.get("choice") or "")) is True:
                passed = True
        seen.add(key)
        row: dict[str, Any] = {
            "id": key,
            "label": label,
            "answer": choice,
            "reason": reason,
            "source": str(source_raw or "").strip().lower() or None,
            "source_label": src,
            "passed": passed,
        }
        if score is not None:
            row["score"] = score
        rows.append(row)

    if isinstance(cells, Mapping):
        for key, cell in cells.items():
            if isinstance(cell, Mapping):
                add_row(str(key), cell)
    for key in answers:
        add_row(str(key), cells.get(key) if isinstance(cells, Mapping) else {})
    for index, item in enumerate(listed):
        if not isinstance(item, Mapping):
            continue
        label = str(item.get("label") or "").strip()
        if not label or any(row["label"] == label for row in rows):
            continue
        add_row(str(item.get("id") or f"listed-{index}"), item)

    scores = task.get("scores") if isinstance(task.get("scores"), list) else []
    if not rows:
        for index, score in enumerate(scores):
            if not isinstance(score, Mapping):
                continue
            title = str(score.get("headline") or score.get("detail") or "Check").strip()
            ok = bool(score.get("passed"))
            rows.append(
                {
                    "id": str(score.get("scorer") or f"score-{index}"),
                    "label": title,
                    "answer": "Yes" if ok else "No",
                    "reason": str(score.get("detail") or "").strip(),
                    "score": 1.0 if ok else 0.0,
                    "source": "log/text",
                    "source_label": "from the log/text",
                    "passed": ok,
                }
            )
    return rows


def _output_text(task: Mapping[str, Any], name: str) -> str:
    outputs = task.get("outputs")
    if isinstance(outputs, list):
        for item in outputs:
            if not isinstance(item, Mapping):
                continue
            path = str(item.get("path") or "").replace("\\", "/").lower()
            if path.endswith(name.lower()):
                return str(
                    item.get("body")
                    or item.get("content")
                    or item.get("extracted_text")
                    or ""
                )
    return ""


def agent_reply(task: Mapping[str, Any] | None) -> str:
    if not isinstance(task, Mapping):
        return ""
    stamped = str(task.get("reply") or "").strip()
    if stamped:
        return redact_run_text(stamped)
    for name in ("reply.txt", "answer.txt", "result.txt"):
        body = _output_text(task, name).strip()
        if body:
            return redact_run_text(body)
    reply = ""
    for span in task.get("spans") or []:
        if not isinstance(span, Mapping) or span.get("name") != "gen_ai.assistant":
            continue
        from skillgate_ai.spans import attr_map

        attrs = attr_map(dict(span))
        text = str(attrs.get("gen_ai.assistant.message") or "").strip()
        if text:
            reply = text
    transcript = str(task.get("transcript") or "")
    if transcript.strip():
        from skillgate_ai.workspace_outputs import harness_final_answer

        final = harness_final_answer(transcript)
        if final:
            return redact_run_text(final)
    if reply:
        return redact_run_text(reply)
    return ""


def _args_from_argv(argv: Sequence[Any]) -> dict[str, Any] | list[str]:
    parts = [str(item) for item in argv]
    if len(parts) <= 1:
        return {}
    rest = parts[1:]
    out: dict[str, Any] = {}
    index = 0
    while index < len(rest):
        token = rest[index]
        if token.startswith("--") and index + 1 < len(rest) and not rest[index + 1].startswith("-"):
            out[token[2:]] = rest[index + 1]
            index += 2
            continue
        if token.startswith("--"):
            out[token[2:]] = True
            index += 1
            continue
        out.setdefault("args", [])
        if isinstance(out["args"], list):
            out["args"].append(token)
        index += 1
    return out or rest


def tool_calls(task: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(task, Mapping):
        return []
    stamped = task.get("tool_calls")
    if isinstance(stamped, list) and stamped:
        return [redact_run_value(item) for item in stamped if isinstance(item, Mapping)]
    rows: list[dict[str, Any]] = []
    log = _output_text(task, "calls.log")
    for line in log.splitlines():
        blob = line.strip()
        if not blob:
            continue
        try:
            obj = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        argv = obj.get("argv")
        if isinstance(argv, str):
            argv = argv.split()
        if not isinstance(argv, Sequence) or not argv:
            name = str(obj.get("tool") or obj.get("name") or "tool")
            arguments = obj.get("arguments") or obj.get("args") or {}
        else:
            name = str(argv[0])
            arguments = _args_from_argv(argv)
        rows.append(
            redact_run_value(
                {
                    "name": name,
                    "arguments": arguments,
                    "response": obj.get("response") if obj.get("response") is not None else {},
                }
            )
        )
    if rows:
        return rows
    from skillgate_ai.spans import attr_map

    for span in task.get("spans") or []:
        if not isinstance(span, Mapping):
            continue
        name = str(span.get("name") or "")
        if not name.startswith("tool."):
            continue
        attrs = attr_map(dict(span))
        tool = str(attrs.get("gen_ai.tool.name") or name[5:] or "tool")
        arguments = attrs.get("gen_ai.tool.call.arguments") or {}
        response = attrs.get("gen_ai.tool.call.result") or {}
        rows.append(
            redact_run_value(
                {
                    "name": tool,
                    "arguments": arguments,
                    "response": response,
                }
            )
        )
    return rows


def task_detail(task: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalized case view. Missing fields stay empty so old history still renders."""
    task = task if isinstance(task, Mapping) else {}
    passed = task.get("passed")
    review = bool(task.get("review") or task.get("status") == "unsure")
    return redact_run_value(
        {
            "id": str(task.get("id") or task.get("task_id") or ""),
            "name": case_name(task),
            "scenario": case_scenario(task),
            "passed": passed,
            "review": review,
            "checks": check_rows(task),
            "reply": agent_reply(task),
            "tool_calls": tool_calls(task),
        }
    )


def hydrate_task(task: dict[str, Any]) -> dict[str, Any]:
    """Fill name/scenario/reply/tool_calls/check_answers on a stored task dict."""
    if not isinstance(task, dict):
        return task
    detail = task_detail(task)
    task.setdefault("id", detail["id"])
    task.setdefault("name", detail["name"])
    task.setdefault("scenario", detail["scenario"])
    if not task.get("reply"):
        task["reply"] = detail["reply"]
    if not task.get("tool_calls"):
        task["tool_calls"] = detail["tool_calls"]
    task["check_answers"] = [
        {
            "id": row.get("id"),
            "label": row.get("label"),
            "answer": row.get("answer"),
            "score": row.get("score"),
            "reason": row.get("reason"),
            "source": row.get("source"),
            "source_label": row.get("source_label"),
            "passed": row.get("passed"),
        }
        for row in detail["checks"]
    ]
    return task


def hydrate_report(report: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(report) if isinstance(report, Mapping) else {}
    tasks = payload.get("tasks")
    if isinstance(tasks, list):
        payload["tasks"] = [
            hydrate_task(dict(item)) if isinstance(item, Mapping) else item
            for item in tasks
        ]
    return payload


def _mark(task: Mapping[str, Any]) -> str:
    if task.get("passed") is True and (
        task.get("review") or task.get("status") == "unsure"
    ):
        return "review"
    if task.get("passed") is True:
        return "pass"
    if task.get("passed") is False:
        return "fail"
    return "not scored"


def _score_text(score: Any) -> str:
    num = _numeric(score)
    if num is None:
        return ""
    if abs(num - round(num)) < 1e-9:
        return f"{num:.0f}.00" if num in {0.0, 1.0} else f"{num:.2f}"
    return f"{num:.2f}"


def format_run_show(
    row: Mapping[str, Any],
    *,
    case_id: str | None = None,
    detail: bool = False,
) -> str:
    report = row.get("report") if isinstance(row.get("report"), Mapping) else {}
    report = hydrate_report(report)
    tasks = [item for item in (report.get("tasks") or []) if isinstance(item, Mapping)]
    if case_id:
        wanted = case_id.strip()
        tasks = [
            item
            for item in tasks
            if str(item.get("id") or item.get("task_id") or "") == wanted
            or str(item.get("name") or "") == wanted
        ]
        if not tasks:
            raise SkillGateError(f"No case named {wanted}.", exit_code=2)
        detail = True
    passed_flag = row.get("passed")
    err = row.get("error") if isinstance(row.get("error"), Mapping) else {}
    cannot_run = "cannot run" in str((err or {}).get("message") or "").lower()
    if passed_flag is True and str(report.get("gate") or "") == "needs review":
        gate = "review"
    elif passed_flag is True:
        gate = "pass"
    elif passed_flag is False:
        gate = "fail"
    elif cannot_run:
        gate = "cannot-run"
    elif report.get("tasks") or str(report.get("gate") or "") == "not scored":
        gate = "not scored"
    else:
        gate = "not run"
    passed = report.get("passed_count")
    total = report.get("task_count")
    counts = f"  {passed}/{total}" if passed is not None and total is not None else ""
    lines = [f"{row.get('run_id')}  {gate}{counts}"]
    err = row.get("error")
    if isinstance(err, Mapping):
        message = str(err.get("message") or "").strip()
        hint = str(err.get("hint") or "").strip()
        if message:
            lines.append(f"  {message}")
        if hint:
            lines.append(f"  {hint}")
    for task in tasks:
        detail_row = task_detail(task)
        name = detail_row["name"] or "case"
        mark = _mark(task)
        if not detail:
            reason = ""
            if mark == "review":
                reason = "  unsure, needs review"
            elif task.get("passed") is False:
                happened = str(task.get("happened") or "").strip()
                if happened:
                    reason = f"  {happened}"
                else:
                    failures = task.get("failures")
                    if isinstance(failures, list) and failures:
                        reason = f"  {failures[0]}"
            lines.append(f"  {name}  {mark}{reason}")
            continue
        lines.append("")
        lines.append(f"{name}  {mark.upper() if mark in {'pass', 'fail'} else mark}")
        scenario = detail_row["scenario"]
        if scenario:
            lines.append("  Setup")
            lines.append(f"  {scenario}")
        checks = detail_row["checks"]
        if checks:
            lines.append("  Checks")
            for item in checks:
                bit = "PASS" if item.get("passed") is True else (
                    "FAIL" if item.get("passed") is False else "—"
                )
                score = _score_text(item.get("score"))
                src = item.get("source_label") or ""
                reason = item.get("reason") or ""
                extra = "  ".join(part for part in (score, reason, f"({src})" if src else "") if part)
                label = item.get("label") or item.get("id") or "Check"
                lines.append(f"  {label}  {bit}" + (f"  {extra}" if extra else ""))
        reply = detail_row["reply"]
        if reply:
            lines.append("  Agent reply")
            for chunk in reply.splitlines() or [reply]:
                lines.append(f"  {chunk}")
        calls = detail_row["tool_calls"]
        if calls:
            lines.append("  Connector calls")
            for call in calls:
                args = call.get("arguments")
                if isinstance(args, (dict, list)):
                    args_text = json.dumps(args, ensure_ascii=True)
                else:
                    args_text = str(args or "")
                lines.append(f"  {call.get('name') or 'tool'}  {args_text}".rstrip())
                resp = call.get("response")
                if resp not in (None, "", {}, []):
                    if isinstance(resp, (dict, list)):
                        resp_text = json.dumps(resp, ensure_ascii=True)
                    else:
                        resp_text = str(resp)
                    lines.append(f"    {resp_text}")
    return "\n".join(lines)
