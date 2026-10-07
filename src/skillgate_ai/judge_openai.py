"""OpenAI outcome judge: Decisions by default, Responses fallback."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Mapping, Protocol

from skillgate_ai.judge_bank import (
    CHECK_CELL_LABELS,
    CHECK_CELL_ORDER,
    DEFAULT_MIN_CONFIDENCE,
    SOFT_CELL_LABELS,
    SOFT_CELL_ORDER,
    UNUSABLE_ANSWER,
    all_questions,
    canonical_choice,
    criteria_text,
    decisions_questions,
    extract_choice,
    extract_confidence,
    extract_probabilities,
    low_confidence_warnings,
    outcome_verdict,
    structured_output_schema,
    unusable_answers,
)
from skillgate_ai.case_pack import sniff_output_bytes
from skillgate_ai.openai_http import (
    DEFAULT_BASE_URL,
    OUT_OF_CREDITS,
    PostFn,
    post_openai_json,
    redact_secrets,
    user_message_for_status,
)

DEFAULT_MODEL = "gpt-6-luna"
DEFAULT_TIMEOUT_SEC = 20.0
WHY_TIMEOUT_SEC = 10.0
WHY_MAX_OUTPUT_TOKENS = 128
TRANSCRIPT_TAIL_CHARS = 4000
IMAGE_MAX_BYTES = 4 * 1024 * 1024
IMAGE_MAX_COUNT = 3
INLINE_MAGICS = {"jpeg": "image/jpeg", "png": "image/png"}
DISPLAY_NAME = "OpenAI (your key)"


class JudgeBackend(Protocol):
    name: str

    def evaluate(
        self,
        *,
        state: Mapping[str, Any],
        images: list[dict[str, str]],
        timeout_sec: float,
    ) -> dict[str, Any]:
        """Return status/model/answers. Never logs secrets."""
        ...


def _tail(text: str, limit: int = TRANSCRIPT_TAIL_CHARS) -> str:
    if limit <= 0:
        return ""
    return (text or "")[-limit:]


def _cell_entry(key: str, answer: Any, labels: Mapping[str, str]) -> dict[str, Any]:
    choice = extract_choice(answer)
    cell: dict[str, Any] = {
        "label": labels[key],
        "choice": choice,
        "reason": criteria_text(key, choice),
    }
    confidence = extract_confidence(answer)
    if confidence is not None:
        cell["confidence"] = confidence
    return cell


def _resolved_under(path: Path, root: Path) -> Path | None:
    """Return path if it resolves inside root. Blocks `..` and absolute escapes."""
    try:
        resolved = path.resolve()
        root_resolved = root.resolve()
        resolved.relative_to(root_resolved)
    except (OSError, ValueError):
        return None
    return resolved


def collect_images(
    *,
    artifacts: list[dict[str, Any]],
    golden: Mapping[str, Any] | None,
    actual: Mapping[str, Any] | None,
    workspace: Path | None,
    skill_root: Path | None,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """JPEG/PNG data URLs only. Caps: 4 MiB each, 3 images. Never logs bytes."""
    candidates: list[tuple[Path, str]] = []
    seen: set[Path] = set()

    def consider(path: Path, label: str, root: Path | None) -> None:
        if root is None:
            return
        resolved = _resolved_under(path, root)
        if resolved is None or resolved in seen or not resolved.is_file():
            return
        seen.add(resolved)
        candidates.append((resolved, label))

    if workspace is not None:
        for row in artifacts:
            if not isinstance(row, Mapping) or not row.get("present"):
                continue
            magic = str(row.get("magic") or "")
            if magic not in INLINE_MAGICS:
                continue
            rel = str(row.get("path") or "").strip()
            if rel:
                consider(workspace / rel, rel, workspace)
        if actual and actual.get("present") and str(actual.get("magic") or "") in INLINE_MAGICS:
            rel = str(actual.get("path") or "").strip()
            if rel:
                consider(workspace / rel, rel, workspace)
    if golden and skill_root is not None:
        rel = str(golden.get("path") or "").strip()
        magic = str(golden.get("magic") or "")
        if rel and (not magic or magic in INLINE_MAGICS):
            consider(skill_root / rel, rel, skill_root)

    images: list[dict[str, str]] = []
    omitted: list[dict[str, Any]] = []
    for path, label in candidates:
        try:
            size = path.stat().st_size
        except OSError:
            omitted.append({"path": label, "reason": "unreadable"})
            continue
        if size > IMAGE_MAX_BYTES:
            omitted.append({"path": label, "size": size, "reason": "too large"})
            continue
        if len(images) >= IMAGE_MAX_COUNT:
            omitted.append({"path": label, "size": size, "reason": "over cap"})
            continue
        try:
            with path.open("rb") as handle:
                header = handle.read(16)
                magic = sniff_output_bytes(header).get("magic")
                if magic not in INLINE_MAGICS:
                    continue
                data = header + handle.read()
        except OSError:
            omitted.append({"path": label, "reason": "unreadable"})
            continue
        if len(data) > IMAGE_MAX_BYTES:
            omitted.append({"path": label, "size": len(data), "reason": "too large"})
            continue
        b64 = base64.b64encode(data).decode("ascii")
        images.append(
            {
                "type": "input_image",
                "image_url": f"data:{INLINE_MAGICS[magic]};base64,{b64}",
            }
        )
    return images, omitted


def _user_content(text: str, images: list[dict[str, str]]) -> str | list[dict[str, Any]]:
    if images:
        return [{"type": "input_text", "text": text}, *images]
    return text


def _state_text(state: Mapping[str, Any]) -> str:
    payload = {
        "check_prompt": state.get("check_prompt"),
        "expect_skill": state.get("expect_skill"),
        "selected_skill": state.get("selected_skill"),
        "scorer_results": state.get("scorer_results"),
        "artifacts": _artifacts_without_bodies(state.get("artifacts")),
        "golden": _text_blob(state.get("golden")),
        "actual_output": _text_blob(state.get("actual_output")),
        "path": state.get("path"),
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
        out.append(
            {
                "path": item.get("path"),
                "present": item.get("present"),
                "kind": item.get("kind"),
                "magic": item.get("magic"),
                "mime": item.get("mime"),
                "size": item.get("size"),
            }
        )
    return out


def _text_blob(raw: Any) -> Any:
    """Keep golden/actual text (`body`) for Decisions input. Drop raw bytes."""
    if not isinstance(raw, Mapping):
        return raw
    data = dict(raw)
    if isinstance(data.get("body"), bytes):
        data["body"] = None
    return data


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
    probabilities = extract_probabilities(mapping)
    if probabilities:
        row["probabilities"] = probabilities
    return row


def _normalize_answers(raw: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    answers: dict[str, dict[str, Any]] = {}
    for key in CHECK_CELL_ORDER:
        answers[key] = _answer_row(key, raw.get(key))
    for key in SOFT_CELL_ORDER:
        if key in raw:
            answers[key] = _answer_row(key, raw.get(key))
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
                mapped[name] = dict(item)
    elif isinstance(rows, Mapping):
        mapped = dict(rows)
    return mapped


def _output_text(payload: Mapping[str, Any]) -> tuple[str | None, bool]:
    """Return (text, refused)."""
    refused = False
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct, False
    output = payload.get("output")
    chunks: list[str] = []
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, Mapping):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, Mapping):
                    continue
                kind = str(part.get("type") or "")
                if kind == "refusal":
                    refused = True
                    continue
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text)
    if refused and not chunks:
        return None, True
    if chunks:
        return "".join(chunks), refused
    return None, refused


class DecisionsBackend:
    name = "decisions"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        post: PostFn | None = None,
    ) -> None:
        del model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        # Decisions documents gpt-6-luna only. Do not send a Responses override.
        self.model = DEFAULT_MODEL
        self._post = post

    def evaluate(
        self,
        *,
        state: Mapping[str, Any],
        images: list[dict[str, str]],
        timeout_sec: float,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/decisions"
        text = _state_text(state)
        content = _user_content(text, images)
        payload_input: str | list[dict[str, Any]]
        if images:
            payload_input = [{"role": "user", "content": content}]
        else:
            payload_input = text
        payload = {
            "model": self.model,
            "input": payload_input,
            "questions": decisions_questions(),
        }
        return self._send(url, payload, timeout_sec)

    def _send(
        self,
        url: str,
        payload: dict[str, Any],
        timeout_sec: float,
    ) -> dict[str, Any]:
        result = post_openai_json(
            url,
            api_key=self.api_key,
            payload=payload,
            timeout_sec=timeout_sec,
            model=self.model,
            post=self._post,
        )
        if result.get("status") != "ok":
            return result
        data = result["data"]
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
        return _finished_answers(
            _normalize_answers(_answers_from_decisions_list(data)),
            model=str(data.get("model") or self.model),
            usage=usage,
        )


class StructuredOutputsBackend:
    name = "responses"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        reasoning_effort: str = "low",
        post: PostFn | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.reasoning_effort = reasoning_effort
        self._post = post

    def evaluate(
        self,
        *,
        state: Mapping[str, Any],
        images: list[dict[str, str]],
        timeout_sec: float,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/responses"
        text = _state_text(state)
        user_content = _user_content(text, images)
        payload: dict[str, Any] = {
            "model": self.model,
            "reasoning": {"effort": self.reasoning_effort},
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Score this skill check. Pick exactly one allowed answer "
                        "for each field. Use only the evidence in the user message."
                    ),
                },
                {"role": "user", "content": user_content},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "skill_gate_check",
                    "strict": True,
                    "schema": structured_output_schema(),
                }
            },
        }
        result = post_openai_json(
            url,
            api_key=self.api_key,
            payload=payload,
            timeout_sec=timeout_sec,
            model=self.model,
            post=self._post,
        )
        if result.get("status") != "ok":
            return result
        data = result["data"]
        text_out, refused = _output_text(data)
        if refused:
            return {
                "status": "error",
                "reason": "OpenAI declined to score this check.",
                "model": str(data.get("model") or self.model),
            }
        if not text_out:
            return {"status": "error", "reason": UNUSABLE_ANSWER, "model": self.model}
        try:
            parsed = json.loads(text_out)
        except json.JSONDecodeError:
            return {"status": "error", "reason": UNUSABLE_ANSWER, "model": self.model}
        if not isinstance(parsed, Mapping):
            return {"status": "error", "reason": UNUSABLE_ANSWER, "model": self.model}
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
        return _finished_answers(
            _normalize_answers(parsed),
            model=str(data.get("model") or self.model),
            usage=usage,
        )


class OutcomeJudge:
    """Applies the Pass lock. HTTP stays on the backend. Why-call is a follow-up."""

    name = "openai"

    def __init__(
        self,
        backend: JudgeBackend,
        *,
        model: str = DEFAULT_MODEL,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        why_enabled: bool = True,
        reasoning_effort: str = "low",
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    ) -> None:
        self.backend = backend
        self.model = model
        self.min_confidence = min_confidence
        self.why_enabled = why_enabled
        self.reasoning_effort = reasoning_effort
        self.timeout_sec = timeout_sec
        self._last_state: Mapping[str, Any] | None = None
        self._last_status: str | None = None
        self._last_reason: str | None = None

    def judge(
        self,
        goal: str,
        artifacts: list[dict[str, Any]],
        transcript_tail: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        workspace = _as_path(kwargs.get("workspace"))
        skill_root = _as_path(kwargs.get("skill_root"))
        golden = kwargs.get("golden") if isinstance(kwargs.get("golden"), Mapping) else None
        actual = (
            kwargs.get("actual_output")
            if isinstance(kwargs.get("actual_output"), Mapping)
            else None
        )
        scores = kwargs.get("scores") if isinstance(kwargs.get("scores"), list) else []
        path = kwargs.get("path") if isinstance(kwargs.get("path"), Mapping) else None
        images, omitted = collect_images(
            artifacts=artifacts,
            golden=golden,
            actual=actual,
            workspace=workspace,
            skill_root=skill_root,
        )
        state = {
            "check_prompt": goal,
            "expect_skill": kwargs.get("expect_skill"),
            "selected_skill": kwargs.get("selected_skill"),
            "scorer_results": scores,
            "artifacts": artifacts,
            "golden": golden,
            "actual_output": actual,
            "path": path,
            "transcript_tail": _tail(transcript_tail),
            "omitted_images": omitted,
        }
        evaluated = self.backend.evaluate(
            state=state, images=images, timeout_sec=self.timeout_sec
        )
        self._last_state = state
        self._last_status = str(evaluated.get("status") or "")
        reason = evaluated.get("reason")
        self._last_reason = str(reason) if isinstance(reason, str) and reason.strip() else None
        return self._stamp(evaluated, artifacts=artifacts, omitted=omitted)

    def _payload(
        self,
        *,
        status: str,
        model: str,
        passed: bool,
        reasons: list[str],
        why: str | None,
        answers: Any,
        soft_answers: dict[str, Any],
        cells: dict[str, Any],
        citations: dict[str, Any],
        usage: Any,
        warnings: list[str],
        questions: dict[str, Any],
        soft_questions: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "status": status,
            "provider": "openai",
            "backend": self.backend.name,
            "display_name": DISPLAY_NAME,
            "model": model,
            "passed": passed,
            "reasons": reasons,
            "why": why,
            "answers": answers,
            "soft_answers": soft_answers,
            "questions": questions,
            "soft_questions": soft_questions,
            "cells": cells,
            "citations": citations,
            "usage": usage,
            "warnings": warnings,
            "min_confidence": self.min_confidence,
        }

    def _stamp(
        self,
        evaluated: Mapping[str, Any],
        *,
        artifacts: list[dict[str, Any]],
        omitted: list[dict[str, Any]],
    ) -> dict[str, Any]:
        model = str(evaluated.get("model") or self.model)
        citations = {"artifacts": list(artifacts), "omitted_images": omitted}
        if evaluated.get("status") != "completed":
            reason = str(evaluated.get("reason") or "OpenAI scoring failed.")
            return self._payload(
                status="error",
                model=model,
                passed=False,
                reasons=[reason],
                why=None,
                answers=evaluated.get("answers") or {},
                soft_answers={},
                cells={},
                citations=citations,
                usage=evaluated.get("usage"),
                warnings=[],
                questions=all_questions(),
                soft_questions={k: all_questions()[k] for k in SOFT_CELL_ORDER},
            )
        answers = evaluated.get("answers") if isinstance(evaluated.get("answers"), dict) else {}
        passed, reasons = outcome_verdict(answers)
        warnings = low_confidence_warnings(
            answers,
            min_confidence=self.min_confidence,
            expect_confidence=self.backend.name == "decisions",
        )
        pass_answers = {key: answers[key] for key in CHECK_CELL_ORDER if key in answers}
        soft_answers = {key: answers[key] for key in SOFT_CELL_ORDER if key in answers}
        cells: dict[str, dict[str, Any]] = {}
        for key in CHECK_CELL_ORDER:
            cells[key] = _cell_entry(key, pass_answers.get(key), CHECK_CELL_LABELS)
        for key in SOFT_CELL_ORDER:
            cells[key] = _cell_entry(key, soft_answers.get(key), SOFT_CELL_LABELS)
        return self._payload(
            status="completed",
            model=model,
            passed=passed,
            reasons=reasons,
            why=None,
            answers=pass_answers,
            soft_answers=soft_answers,
            cells=cells,
            citations=citations,
            usage=evaluated.get("usage"),
            warnings=warnings,
            questions={k: all_questions()[k] for k in CHECK_CELL_ORDER},
            soft_questions={k: all_questions()[k] for k in SOFT_CELL_ORDER},
        )

    def explain_fail(self, reasons: list[str]) -> str | None:
        """One Fail sentence after the engine has the gate verdict."""
        if not self.why_enabled or self._last_state is None:
            return None
        if self._last_status == "error" and self._last_reason != UNUSABLE_ANSWER:
            return None
        return self._why_call(self._last_state, reasons)

    def _why_call(self, state: Mapping[str, Any], reasons: list[str]) -> str | None:
        payload = {
            "model": self.model,
            "max_output_tokens": WHY_MAX_OUTPUT_TOKENS,
            "reasoning": {"effort": self.reasoning_effort},
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Explain in one or two short sentences why this check failed. "
                        "Use everyday words. Do not mention APIs, schemas, or internal field names."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "check": state.get("check_prompt"),
                            "what_failed": reasons,
                            "transcript_tail": state.get("transcript_tail"),
                        },
                        ensure_ascii=True,
                        default=str,
                    ),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "check_fail_why",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {"why": {"type": "string"}},
                        "required": ["why"],
                        "additionalProperties": False,
                    },
                }
            },
        }
        api_key = str(getattr(self.backend, "api_key", "") or "")
        base_url = str(getattr(self.backend, "base_url", DEFAULT_BASE_URL) or DEFAULT_BASE_URL).rstrip(
            "/"
        )
        result = post_openai_json(
            f"{base_url}/responses",
            api_key=api_key,
            payload=payload,
            timeout_sec=WHY_TIMEOUT_SEC,
            model=self.model,
            post=getattr(self.backend, "_post", None),
            retries=False,
        )
        if result.get("status") != "ok":
            return None
        data = result["data"]
        text_out, refused = _output_text(data)
        if refused or not text_out:
            return None
        try:
            parsed = json.loads(text_out)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, Mapping):
            return None
        why = parsed.get("why")
        if isinstance(why, str) and why.strip():
            return redact_secrets(why.strip(), api_key)
        return None


def _as_path(value: Any) -> Path | None:
    if isinstance(value, Path):
        return value
    if isinstance(value, str) and value.strip():
        return Path(value)
    return None


def make_openai_judge(
    *,
    api_key: str,
    backend: str = "decisions",
    model: str = DEFAULT_MODEL,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    why_enabled: bool = True,
    reasoning_effort: str = "low",
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    base_url: str = DEFAULT_BASE_URL,
    post: PostFn | None = None,
) -> OutcomeJudge:
    name = (backend or "decisions").strip().lower()
    if name in {"structured", "responses"}:
        impl: JudgeBackend = StructuredOutputsBackend(
            api_key=api_key,
            base_url=base_url,
            model=model,
            reasoning_effort=reasoning_effort,
            post=post,
        )
    else:
        impl = DecisionsBackend(
            api_key=api_key,
            base_url=base_url,
            model=model,
            post=post,
        )
    return OutcomeJudge(
        impl,
        model=model,
        min_confidence=min_confidence,
        why_enabled=why_enabled,
        reasoning_effort=reasoning_effort,
        timeout_sec=timeout_sec,
    )


# Re-export for tests
__all__ = [
    "DISPLAY_NAME",
    "IMAGE_MAX_BYTES",
    "IMAGE_MAX_COUNT",
    "OUT_OF_CREDITS",
    "DecisionsBackend",
    "OutcomeJudge",
    "StructuredOutputsBackend",
    "collect_images",
    "make_openai_judge",
    "redact_secrets",
    "user_message_for_status",
]
