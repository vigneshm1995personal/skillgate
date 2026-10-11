"""OpenAI outcome judge: Decisions by default, Responses fallback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Protocol

from skillgate_ai.judge_bank import (
    CHECK_CELL_LABELS,
    CHECK_CELL_ORDER,
    DEFAULT_MIN_CONFIDENCE,
    PATH_NOT_AVAILABLE,
    SOFT_CELL_LABELS,
    SOFT_CELL_ORDER,
    UNUSABLE_ANSWER,
    all_questions,
    canonical_choice,
    criteria_text,
    extract_choice,
    extract_confidence,
    extract_probabilities,
    unusable_answers,
)
from skillgate_ai.judge_images import IMAGE_MAX_BYTES, IMAGE_MAX_COUNT, collect_images
from skillgate_ai.judge_spec import (
    JudgeSpec,
    builtin_spec,
    coerce_extra_answer,
    extra_question_passed,
    spec_decisions_questions,
    spec_structured_schema,
    spec_verdict,
)
from skillgate_ai.openai_http import (
    DEFAULT_BASE_URL,
    OUT_OF_CREDITS,
    PostFn,
    post_openai_json,
    redact_secrets,
    user_message_for_status,
)

DEFAULT_MODEL = "gpt-6-luna"
GATEWAY_DECISIONS_MODEL = "openai/gpt-6-luna-decisions"
DEFAULT_TIMEOUT_SEC = 20.0
WHY_TIMEOUT_SEC = 10.0
WHY_MAX_OUTPUT_TOKENS = 128
WHY_OUTPUT_CHARS = 1500
TRANSCRIPT_TAIL_CHARS = 4000
DISPLAY_NAME = "the judge"
GATEWAY_DISPLAY_NAME = "the judge"
CHOSEN_DISPLAY_NAME = "OpenAI"


def _decisions_model(model: str) -> str:
    slug = (model or "").strip() or DEFAULT_MODEL
    if slug == DEFAULT_MODEL or slug.endswith("-decisions"):
        return slug
    return DEFAULT_MODEL


def _responses_model(model: str) -> str:
    slug = (model or "").strip() or DEFAULT_MODEL
    if slug.endswith("-decisions"):
        return slug[: -len("-decisions")]
    return slug


def _model_supports_reasoning(model: str) -> bool:
    slug = (model or "").strip().lower().rsplit("/", 1)[-1]
    return slug.startswith(("o1", "o3", "o4", "gpt-5", "gpt-6"))


def _reasoning_field(model: str, effort: str) -> dict[str, Any]:
    if _model_supports_reasoning(model):
        return {"reasoning": {"effort": effort}}
    return {}


class JudgeBackend(Protocol):
    name: str
    model: str
    api_key: str

    def evaluate(
        self,
        *,
        state: Mapping[str, Any],
        images: list[dict[str, str]],
        timeout_sec: float,
        spec: JudgeSpec | None = None,
    ) -> dict[str, Any]:
        """Return status/model/answers. Never logs secrets."""
        ...

    def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout_sec: float,
        retries: bool = True,
    ) -> dict[str, Any]:
        """POST JSON to this backend's OpenAI base URL."""
        ...


class _OpenAIPosted:
    """HTTP for one OpenAI key/base/model. Backends own evaluate; why uses post_json."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        post: PostFn | None = None,
        who: str = DISPLAY_NAME,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._post = post
        self.who = who or DISPLAY_NAME

    def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout_sec: float,
        retries: bool = True,
    ) -> dict[str, Any]:
        suffix = path if path.startswith("/") else f"/{path}"
        return post_openai_json(
            f"{self.base_url}{suffix}",
            api_key=self.api_key,
            payload=payload,
            timeout_sec=timeout_sec,
            model=self.model,
            post=self._post,
            retries=retries,
            who=self.who,
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
        "reason": criteria_text(key, choice),
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


def _path_is_recorded(path: Any) -> bool:
    if not isinstance(path, Mapping):
        return False
    if path.get("had_path") is True:
        return True
    steps = path.get("steps")
    if isinstance(steps, bool) or not isinstance(steps, (int, float)):
        return False
    return int(steps) > 0


def _why_output_text(raw: Any, *, secret: str) -> str | None:
    """Size-capped, redacted expected/actual for the Fail why-call."""
    if raw is None:
        return None
    if isinstance(raw, str):
        text = raw
    elif isinstance(raw, Mapping):
        if raw.get("present") is False:
            return redact_secrets("(missing)", secret)
        body = raw.get("body")
        if isinstance(body, bytes) or body is None:
            kind = raw.get("kind") or raw.get("magic")
            if isinstance(kind, str) and kind.strip():
                return f"(binary {kind})"
            return None
        text = str(body)
    else:
        return None
    if WHY_OUTPUT_CHARS > 0 and len(text) > WHY_OUTPUT_CHARS:
        text = text[-WHY_OUTPUT_CHARS:]
    return redact_secrets(text, secret)


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
                answers[question.id] = coerce_extra_answer(raw.get(question.id))
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


class DecisionsBackend(_OpenAIPosted):
    name = "decisions"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        post: PostFn | None = None,
        who: str = DISPLAY_NAME,
        decisions_path: str = "/decisions",
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=_decisions_model(model),
            post=post,
            who=who,
        )
        path = (decisions_path or "/decisions").strip() or "/decisions"
        self.decisions_path = path if path.startswith("/") else f"/{path}"

    def evaluate(
        self,
        *,
        state: Mapping[str, Any],
        images: list[dict[str, str]],
        timeout_sec: float,
        spec: JudgeSpec | None = None,
    ) -> dict[str, Any]:
        text = _state_text(state)
        content = _user_content(text, images)
        payload_input: str | list[dict[str, Any]]
        if images:
            payload_input = [{"role": "user", "content": content}]
        else:
            payload_input = text
        include_path = _path_is_recorded(state.get("path"))
        resolved = spec or builtin_spec()
        result = self.post_json(
            self.decisions_path,
            {
                "model": self.model,
                "input": payload_input,
                "questions": spec_decisions_questions(resolved, include_path=include_path),
            },
            timeout_sec=timeout_sec,
        )
        if result.get("status") != "ok":
            return result
        data = result["data"]
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
        return _finished_answers(
            _normalize_answers(
                _answers_from_decisions_list(data),
                include_path=include_path,
                spec=resolved,
            ),
            model=str(data.get("model") or self.model),
            usage=usage,
        )


class StructuredOutputsBackend(_OpenAIPosted):
    name = "responses"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        reasoning_effort: str = "low",
        post: PostFn | None = None,
        who: str = DISPLAY_NAME,
    ) -> None:
        super().__init__(
            api_key=api_key, base_url=base_url, model=model, post=post, who=who
        )
        self.reasoning_effort = reasoning_effort

    def evaluate(
        self,
        *,
        state: Mapping[str, Any],
        images: list[dict[str, str]],
        timeout_sec: float,
        spec: JudgeSpec | None = None,
    ) -> dict[str, Any]:
        text = _state_text(state)
        user_content = _user_content(text, images)
        include_path = _path_is_recorded(state.get("path"))
        resolved = spec or builtin_spec()
        result = self.post_json(
            "/responses",
            {
                "model": self.model,
                **_reasoning_field(self.model, self.reasoning_effort),
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
                        "schema": spec_structured_schema(resolved, include_path=include_path),
                    }
                },
            },
            timeout_sec=timeout_sec,
        )
        if result.get("status") != "ok":
            return result
        data = result["data"]
        text_out, refused = _output_text(data)
        if refused:
            return {
                "status": "error",
                "reason": "The judge declined to score this check.",
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
            _normalize_answers(parsed, include_path=include_path, spec=resolved),
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
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        why_enabled: bool = True,
        reasoning_effort: str = "low",
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
        display_name: str = DISPLAY_NAME,
        provider: str = "openai",
        chosen: bool = False,
        supports_why: bool | None = None,
        supports_confidence: bool | None = None,
    ) -> None:
        self.backend = backend
        self.min_confidence = min_confidence
        self.why_enabled = why_enabled
        self.reasoning_effort = reasoning_effort
        self.timeout_sec = timeout_sec
        self.display_name = display_name
        self.name = provider
        self.chosen = chosen
        self.supports_why = True if supports_why is None else supports_why
        default_conf = getattr(backend, "name", "") == "decisions"
        self.supports_confidence = default_conf if supports_confidence is None else supports_confidence

    @property
    def model(self) -> str:
        return self.backend.model

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
        spec = kwargs.get("spec")
        resolved = spec if isinstance(spec, JudgeSpec) else builtin_spec()
        evaluate = self.backend.evaluate
        try:
            evaluated = evaluate(
                state=state, images=images, timeout_sec=self.timeout_sec, spec=resolved
            )
        except TypeError:
            evaluated = evaluate(state=state, images=images, timeout_sec=self.timeout_sec)
        return self._stamp(
            evaluated,
            artifacts=artifacts,
            omitted=omitted,
            include_path=_path_is_recorded(path),
            spec=resolved,
        )

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
            "provider": self.name,
            "backend": self.backend.name,
            "display_name": self.display_name,
            "chosen": self.chosen,
            "score_no_trigger": False,
            "extra_failures": [],
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
            "supports_confidence": self.supports_confidence,
        }

    def _stamp(
        self,
        evaluated: Mapping[str, Any],
        *,
        artifacts: list[dict[str, Any]],
        omitted: list[dict[str, Any]],
        include_path: bool,
        spec: JudgeSpec | None = None,
    ) -> dict[str, Any]:
        resolved = spec or builtin_spec()
        model = str(evaluated.get("model") or self.backend.model)
        citations = {"artifacts": list(artifacts), "omitted_images": omitted}
        soft_questions = {k: all_questions()[k] for k in SOFT_CELL_ORDER}
        extra_warnings = [
            str(item)
            for item in (evaluated.get("warnings") or [])
            if str(item).strip()
        ]
        if evaluated.get("status") != "completed":
            reason = str(evaluated.get("reason") or "The judge couldn't score this check.")
            return self._finish_payload(
                self._payload(
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
                    warnings=extra_warnings,
                    questions=all_questions(),
                    soft_questions=soft_questions,
                ),
                spec=resolved,
                confidence=bool(
                    getattr(self.backend, "supports_confidence", self.supports_confidence)
                ),
            )
        answers = evaluated.get("answers") if isinstance(evaluated.get("answers"), dict) else {}
        if not include_path:
            answers = {key: value for key, value in answers.items() if key not in SOFT_CELL_ORDER}
        confidence = bool(
            getattr(self.backend, "supports_confidence", self.supports_confidence)
        )
        passed, reasons, warnings = spec_verdict(
            resolved,
            answers,
            supports_confidence=confidence,
            include_path=include_path,
        )
        warnings = extra_warnings + warnings
        pass_answers = {key: answers[key] for key in CHECK_CELL_ORDER if key in answers}
        soft_answers = {key: answers[key] for key in SOFT_CELL_ORDER if key in answers}
        extra_answers = {q.id: answers[q.id] for q in resolved.extras if q.id in answers}
        cells: dict[str, dict[str, Any]] = {}
        for key in CHECK_CELL_ORDER:
            cells[key] = _cell_entry(key, pass_answers.get(key), CHECK_CELL_LABELS)
        for key in SOFT_CELL_ORDER:
            if include_path:
                cells[key] = _cell_entry(key, soft_answers.get(key), SOFT_CELL_LABELS)
            else:
                cells[key] = _path_not_available_cell()
        for question in resolved.extras:
            raw = extra_answers.get(question.id)
            cell: dict[str, Any] = {
                "label": question.ask,
                "choice": extract_choice(raw),
                "reason": None,
            }
            if isinstance(raw, Mapping) and raw.get("probability") is not None:
                cell["probability"] = raw.get("probability")
            elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
                cell["probability"] = float(raw)
            cells[question.id] = cell
        merged_answers = {**pass_answers, **extra_answers}
        extra_questions = {q.id: {"instructions": q.ask, "type": q.type} for q in resolved.extras}
        extra_failures: list[str] = []
        for question in resolved.extras:
            if question.on_fail != "block":
                continue
            ok, detail = extra_question_passed(question, answers.get(question.id))
            if not ok and detail:
                extra_failures.append(detail)
        return self._finish_payload(
            self._payload(
                status="completed",
                model=model,
                passed=passed,
                reasons=reasons,
                why=None,
                answers=merged_answers,
                soft_answers=soft_answers,
                cells=cells,
                citations=citations,
                usage=evaluated.get("usage"),
                warnings=warnings,
                questions={**{k: all_questions()[k] for k in CHECK_CELL_ORDER}, **extra_questions},
                soft_questions=soft_questions,
            ),
            spec=resolved,
            confidence=confidence,
            extra_failures=extra_failures,
        )

    def _finish_payload(
        self,
        payload: dict[str, Any],
        *,
        spec: JudgeSpec,
        confidence: bool,
        extra_failures: list[str] | None = None,
    ) -> dict[str, Any]:
        payload["supports_confidence"] = confidence
        payload["score_no_trigger"] = spec.score_no_trigger
        payload["extra_failures"] = list(extra_failures or [])
        return payload

    def explain_fail(
        self,
        reasons: list[str],
        *,
        judged: Mapping[str, Any] | None = None,
        check: str = "",
        transcript_tail: str = "",
        expected_output: Any = None,
        actual_output: Any = None,
    ) -> str | None:
        """One Fail sentence after the engine has the gate verdict."""
        if not self.why_enabled or not self.supports_why:
            return None
        blob = judged or {}
        if blob.get("status") == "error":
            cell_reasons = [str(item) for item in (blob.get("reasons") or [])]
            if UNUSABLE_ANSWER not in cell_reasons:
                return None
        if hasattr(self.backend, "explain_fail_payload"):
            user_blob = self._why_user_blob(
                check,
                reasons,
                transcript_tail,
                expected_output=expected_output,
                actual_output=actual_output,
            )
            try:
                why = self.backend.explain_fail_payload(user_blob, timeout_sec=WHY_TIMEOUT_SEC)
            except Exception:
                return None
            return why.strip() if isinstance(why, str) and why.strip() else None
        if not hasattr(self.backend, "post_json"):
            return None
        return self._why_call(
            check,
            reasons,
            transcript_tail,
            expected_output=expected_output,
            actual_output=actual_output,
        )

    def _why_user_blob(
        self,
        check: str,
        reasons: list[str],
        transcript_tail: str,
        *,
        expected_output: Any = None,
        actual_output: Any = None,
    ) -> dict[str, Any]:
        secret = self.backend.api_key
        user_blob: dict[str, Any] = {
            "check": check,
            "what_failed": reasons,
            "transcript_tail": _tail(transcript_tail),
        }
        expected = _why_output_text(expected_output, secret=secret)
        actual = _why_output_text(actual_output, secret=secret)
        if expected is not None:
            user_blob["expected_output"] = expected
        if actual is not None:
            user_blob["actual_output"] = actual
        return user_blob

    def _why_call(
        self,
        check: str,
        reasons: list[str],
        transcript_tail: str,
        *,
        expected_output: Any = None,
        actual_output: Any = None,
    ) -> str | None:
        user_blob = self._why_user_blob(
            check,
            reasons,
            transcript_tail,
            expected_output=expected_output,
            actual_output=actual_output,
        )
        why_model = _responses_model(self.backend.model)
        payload = {
            "model": why_model,
            "max_output_tokens": WHY_MAX_OUTPUT_TOKENS,
            **_reasoning_field(why_model, self.reasoning_effort),
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Explain in one or two short sentences why this check failed. "
                        "Use everyday words. Do not mention APIs, schemas, or internal field names. "
                        "If expected and actual output differ, say what was expected and what was produced."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        user_blob,
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
        result = self.backend.post_json(
            "/responses",
            payload,
            timeout_sec=WHY_TIMEOUT_SEC,
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
            return redact_secrets(why.strip(), self.backend.api_key)
        return None


def _as_path(value: Any) -> Path | None:
    if isinstance(value, Path):
        return value
    if isinstance(value, str) and value.strip():
        return Path(value)
    return None


def ping_openai_backend(backend: JudgeBackend, *, display_name: str = DISPLAY_NAME) -> dict[str, Any]:
    result = backend.post_json(
        "/decisions",
        {
            "model": backend.model,
            "input": "ping",
            "questions": [
                {
                    "type": "predicate",
                    "name": "connection_test",
                    "instructions": "Is this a connection test?",
                }
            ],
        },
        timeout_sec=DEFAULT_TIMEOUT_SEC,
        retries=False,
    )
    if result.get("status") == "ok":
        return {"ok": True, "message": f"Connected to {display_name}."}
    return {"ok": False, "message": str(result.get("reason") or "Could not connect.")}


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
    display_name: str = DISPLAY_NAME,
    chosen: bool = False,
) -> OutcomeJudge:
    name = (backend or "decisions").strip().lower()
    if name in {"structured", "responses"}:
        impl: JudgeBackend = StructuredOutputsBackend(
            api_key=api_key,
            base_url=base_url,
            model=model,
            reasoning_effort=reasoning_effort,
            post=post,
            who=display_name,
        )
    else:
        impl = DecisionsBackend(
            api_key=api_key,
            base_url=base_url,
            model=model,
            post=post,
            who=display_name,
        )
    return OutcomeJudge(
        impl,
        min_confidence=min_confidence,
        why_enabled=why_enabled,
        reasoning_effort=reasoning_effort,
        timeout_sec=timeout_sec,
        display_name=display_name,
        provider="openai",
        chosen=chosen,
        supports_why=True,
        supports_confidence=impl.name == "decisions",
    )


# Re-export for tests
__all__ = [
    "DISPLAY_NAME",
    "GATEWAY_DISPLAY_NAME",
    "IMAGE_MAX_BYTES",
    "IMAGE_MAX_COUNT",
    "OUT_OF_CREDITS",
    "WHY_OUTPUT_CHARS",
    "DecisionsBackend",
    "OutcomeJudge",
    "StructuredOutputsBackend",
    "collect_images",
    "make_openai_judge",
    "redact_secrets",
    "user_message_for_status",
]
