"""Direct-answer scoring. Chat and Responses completion models are refused."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from skillgate_ai.judge_bank import (
    CHECK_CELL_ORDER,
    PATH_NOT_AVAILABLE,
    SOFT_CELL_LABELS,
    SOFT_CELL_ORDER,
    UNUSABLE_ANSWER,
    canonical_choice,
    criteria_text,
    extract_choice,
    extract_confidence,
    extract_probabilities,
    extract_reason,
    unusable_answers,
)
from skillgate_ai.judge_context import workspace_files_for_judge
from skillgate_ai.judge_openai.backend import TRANSCRIPT_TAIL_CHARS
from skillgate_ai.judge_spec import (
    JudgeSpec,
    coerce_extra_answer,
)


def _tail(text: str, limit: int = TRANSCRIPT_TAIL_CHARS) -> str:
    if limit <= 0:
        return ""
    return (text or "")[-limit:]

def _cell_entry(key: str, answer: Any, labels: Mapping[str, str]) -> dict[str, Any]:
    choice = extract_choice(answer)
    cell: dict[str, Any] = {
        "label": labels[key],
        "choice": choice,
        "reason": extract_reason(answer) or criteria_text(key, choice),
    }
    confidence = extract_confidence(answer)
    if confidence is not None:
        cell["confidence"] = confidence
    return cell

def _user_content(text: str, images: list[dict[str, str]]) -> str | list[dict[str, Any]]:
    if images:
        return [{"type": "input_text", "text": text}, *images]
    return text

def _state_text(state: Mapping[str, Any]) -> str:
    artifacts = state.get("artifacts")
    payload = {
        "check_prompt": state.get("check_prompt"),
        "expect_skill": state.get("expect_skill"),
        "selected_skill": state.get("selected_skill"),
        "skill_instructions": state.get("skill_instructions"),
        "scorer_results": state.get("scorer_results"),
        "workspace_files": workspace_files_for_judge(
            artifacts if isinstance(artifacts, list) else None
        ),
        "artifacts": _artifacts_without_bodies(artifacts),
        "expected_outcome": _expected_outcome_text(state),
        "golden": _text_blob(state.get("golden")),
        "actual_output": _text_blob(state.get("actual_output")),
        "path": state.get("path"),
        "agent_trajectory": state.get("agent_trajectory"),
        "transcript_tail": state.get("transcript_tail"),
        "omitted_images": state.get("omitted_images"),
    }
    return json.dumps(payload, ensure_ascii=True, default=str)

def _artifacts_without_bodies(raw: Any) -> list[dict[str, Any]]:
    rows = raw if isinstance(raw, list) else []
    out: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, Mapping):
            continue
        snippet = item.get("extracted_text") or item.get("body")
        if isinstance(snippet, str) and len(snippet) > 4000:
            snippet = snippet[-4000:]
        out.append(
            {
                "path": item.get("path"),
                "present": item.get("present"),
                "kind": item.get("kind"),
                "magic": item.get("magic"),
                "mime": item.get("mime"),
                "size": item.get("size"),
                "extracted_text": snippet,
            }
        )
    return out

def _expected_outcome_text(state: Mapping[str, Any]) -> str | None:
    raw = state.get("expected_outcome")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if raw not in (None, "") and not isinstance(raw, Mapping):
        return str(raw)
    golden = state.get("golden")
    if not isinstance(golden, Mapping):
        return None
    bits: list[str] = []
    body = golden.get("body") or golden.get("extracted_text")
    if isinstance(body, str) and body.strip():
        bits.append(body.strip())
    contains = golden.get("contains")
    if isinstance(contains, list):
        needles = [str(item).strip() for item in contains if str(item).strip()]
        if needles:
            bits.append("Required: " + "; ".join(needles))
    return "\n".join(bits) or None

def _text_blob(raw: Any) -> Any:
    """Keep golden/actual text (`body`) for Decisions input. Drop raw bytes."""
    if not isinstance(raw, Mapping):
        return raw
    data = dict(raw)
    if isinstance(data.get("body"), bytes):
        data["body"] = None
    if data.get("body") is None and data.get("extracted_text"):
        data["body"] = data.get("extracted_text")
    return data

def _path_is_recorded(path: Any) -> bool:
    if not isinstance(path, Mapping):
        return False
    if path.get("had_path") is True:
        return True
    steps = path.get("steps")
    if isinstance(steps, bool) or not isinstance(steps, (int, float)):
        return False
    return int(steps) > 0

def _path_not_available_cell() -> dict[str, Any]:
    return {
        "label": SOFT_CELL_LABELS["path_efficiency"],
        "choice": None,
        "reason": PATH_NOT_AVAILABLE,
    }

def _finished_answers(
    answers: dict[str, dict[str, Any]],
    *,
    model: str,
    usage: Any = None,
) -> dict[str, Any]:
    if unusable_answers(answers):
        return {
            "status": "error",
            "reason": UNUSABLE_ANSWER,
            "model": model,
            "answers": answers,
            "usage": usage,
        }
    return {
        "status": "completed",
        "model": model,
        "answers": answers,
        "usage": usage,
    }

def _answer_row(key: str, item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        mapping: Mapping[str, Any] = {"choice": item}
    elif isinstance(item, Mapping):
        mapping = item
    else:
        mapping = {}
    raw_choice = extract_choice(mapping)
    row: dict[str, Any] = {"choice": canonical_choice(key, raw_choice) or raw_choice}
    confidence = extract_confidence(mapping)
    if confidence is not None:
        row["confidence"] = confidence
    reason = extract_reason(mapping)
    if reason:
        row["reason"] = reason
    probabilities = extract_probabilities(mapping)
    if probabilities:
        row["probabilities"] = probabilities
    return row

def _normalize_answers(
    raw: Mapping[str, Any],
    *,
    include_path: bool = True,
    spec: JudgeSpec | None = None,
) -> dict[str, Any]:
    answers: dict[str, Any] = {}
    for key in CHECK_CELL_ORDER:
        answers[key] = _answer_row(key, raw.get(key))
    if include_path:
        for key in SOFT_CELL_ORDER:
            if key in raw:
                answers[key] = _answer_row(key, raw.get(key))
    if spec is not None:
        for question in spec.extras:
            if question.id in raw:
                answers[question.id] = coerce_extra_answer(raw.get(question.id), kind=question.type)
    return answers

def _answers_from_decisions_list(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = payload.get("answers")
    mapped: dict[str, Any] = {}
    if isinstance(rows, list):
        for item in rows:
            if not isinstance(item, Mapping):
                continue
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                mapped[name] = _lift_decision_answer(item)
    elif isinstance(rows, Mapping):
        mapped = {str(key): _lift_decision_answer(item) for key, item in rows.items()}
    return mapped

def _lift_decision_answer(item: Any) -> Any:
    """Copy ``noul`` onto ``probability`` so predicate checks can read it."""
    if not isinstance(item, Mapping):
        return item
    data = dict(item)
    if "probability" not in data and "noul" in data:
        noul = data.get("noul")
        if isinstance(noul, bool):
            data["probability"] = 1.0 if noul else 0.0
        elif isinstance(noul, (int, float)):
            data["probability"] = float(noul)
    data.pop("noul", None)
    if data.get("type") == "noul":
        data["type"] = "predicate"
    return data

def _annotate_payload_too_large(
    result: Mapping[str, Any], state: Mapping[str, Any]
) -> dict[str, Any]:
    """Name the payload size only when the decision endpoint returns HTTP 413."""
    if int(result.get("http_status") or 0) != 413:
        return dict(result)
    artifacts = state.get("artifacts")
    files = len(artifacts) if isinstance(artifacts, list) else 0
    nbytes = len(_state_text(state).encode("utf-8"))
    size = f"The payload was {nbytes} bytes ({files} files)."
    reason = str(result.get("reason") or "").strip()
    if size in reason:
        return dict(result)
    joined = f"{reason} {size}".strip() if reason else size
    return {**result, "reason": joined}

