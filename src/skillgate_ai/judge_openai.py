"""Direct-answer scoring. Chat and Responses completion models are refused."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Protocol

from skillgate_ai.judge_context import workspace_files_for_judge
from skillgate_ai.judge_bank import (
    CHECK_CELL_LABELS,
    CHECK_CELL_ORDER,
    DEFAULT_MIN_CONFIDENCE,
    LOW_CONFIDENCE_MAX_ASKS,
    PATH_NOT_AVAILABLE,
    SOFT_CELL_LABELS,
    SOFT_CELL_ORDER,
    UNUSABLE_ANSWER,
    all_questions,
    answers_have_low_confidence,
    canonical_choice,
    criteria_text,
    extract_choice,
    extract_confidence,
    extract_probabilities,
    extract_reason,
    majority_vote_answers,
    unusable_answers,
)
from skillgate_ai.judge_images import IMAGE_MAX_BYTES, IMAGE_MAX_COUNT, collect_images
from skillgate_ai.judge_spec import (
    JudgeSpec,
    builtin_spec,
    coerce_extra_answer,
    extra_block_failures,
    spec_decisions_questions,
    spec_verdict,
)
from skillgate_ai.judge_providers.decision import DecisionModel, require_decision_model
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
CHOSEN_DISPLAY_NAME = DISPLAY_NAME


def _decisions_model(model: str) -> str:
    slug = (model or "").strip() or DEFAULT_MODEL
    if slug == DEFAULT_MODEL or slug.endswith("-decisions"):
        return slug
    return DEFAULT_MODEL



class JudgeBackend(Protocol):
    """HTTP client for one decisions endpoint. A judge implements DecisionModel."""

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
                answers[question.id] = coerce_extra_answer(
                    raw.get(question.id), kind=question.type
                )
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
    if "probability" in data or "noul" not in data:
        return data
    noul = data.get("noul")
    if isinstance(noul, bool):
        data["probability"] = 1.0 if noul else 0.0
    elif isinstance(noul, (int, float)):
        data["probability"] = float(noul)
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
            return _annotate_payload_too_large(result, state)
        data = result["data"]
        from skillgate_ai.usage import normalize_judge_api_usage

        model_name = str(data.get("model") or self.model)
        usage = normalize_judge_api_usage(data, model=model_name)
        finished = _finished_answers(
            _normalize_answers(
                _answers_from_decisions_list(data),
                include_path=include_path,
                spec=resolved,
            ),
            model=model_name,
            usage=usage,
        )
        finished["scoring_endpoint"] = "decisions"
        return finished

    def ping(self, *, timeout_sec: float = DEFAULT_TIMEOUT_SEC) -> dict[str, Any]:
        result = self.post_json(
            self.decisions_path,
            {
                "model": self.model,
                "input": "ping",
                "questions": [
                    {
                        "type": "predicate",
                        "name": "connection_test",
                        "instructions": "Is this a connection test?",
                    }
                ],
            },
            timeout_sec=timeout_sec,
            retries=False,
        )
        if result.get("status") == "ok":
            return {
                "ok": True,
                "message": "Connected to the judge.",
                "scoring_endpoint": "decisions",
            }
        return {"ok": False, "message": str(result.get("reason") or "Could not connect.")}


class OutcomeJudge:
    """Applies the Pass lock. HTTP stays on the backend. Why-call is a follow-up."""

    name = "openai"

    def __init__(
        self,
        backend: DecisionModel,
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
        require_decision_model(backend)
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
            "skill_instructions": kwargs.get("skill_instructions"),
            "scorer_results": scores,
            "artifacts": artifacts,
            "golden": golden,
            "actual_output": actual,
            "path": path,
            "agent_trajectory": kwargs.get("agent_trajectory"),
            "transcript_tail": _tail(transcript_tail),
            "omitted_images": omitted,
        }
        spec = kwargs.get("spec")
        resolved = spec if isinstance(spec, JudgeSpec) else builtin_spec()
        expected = kwargs.get("expected_outcome")
        if isinstance(expected, str) and expected.strip():
            state["expected_outcome"] = expected.strip()
        elif state.get("expected_outcome") in (None, ""):
            derived = _expected_outcome_text(state)
            if derived:
                state["expected_outcome"] = derived
        evaluate = self.backend.evaluate
        try:
            evaluated = evaluate(
                state=state, images=images, timeout_sec=self.timeout_sec, spec=resolved
            )
        except TypeError:
            evaluated = evaluate(state=state, images=images, timeout_sec=self.timeout_sec)
        evaluated = self._majority_reask(
            evaluate, state=state, images=images, spec=resolved, first=evaluated
        )
        return self._stamp(
            evaluated,
            artifacts=artifacts,
            omitted=omitted,
            include_path=_path_is_recorded(path),
            spec=resolved,
        )

    def _majority_reask(
        self,
        evaluate: Any,
        *,
        state: Mapping[str, Any],
        images: list[dict[str, str]],
        spec: JudgeSpec,
        first: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not self.supports_confidence:
            return dict(first)
        if first.get("status") != "completed":
            return dict(first)
        answers = first.get("answers") if isinstance(first.get("answers"), dict) else {}
        blocking = [q.id for q in spec.questions if q.on_fail == "block"]
        if not answers_have_low_confidence(
            answers, min_confidence=self.min_confidence, keys=blocking
        ):
            return dict(first)
        rounds: list[Mapping[str, Any]] = [first]
        while len(rounds) < LOW_CONFIDENCE_MAX_ASKS:
            try:
                again = evaluate(
                    state=state, images=images, timeout_sec=self.timeout_sec, spec=spec
                )
            except TypeError:
                again = evaluate(state=state, images=images, timeout_sec=self.timeout_sec)
            if again.get("status") != "completed":
                break
            rounds.append(again)
        blobs = [
            row.get("answers")
            for row in rounds
            if isinstance(row.get("answers"), dict)
        ]
        merged = majority_vote_answers(
            [blob for blob in blobs if isinstance(blob, dict)]
        )
        last = dict(rounds[-1])
        last["answers"] = merged
        usage = _sum_judge_usage(rounds)
        if usage is not None:
            last["usage"] = usage
        return last

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
        scoring_endpoint: str | None = None,
    ) -> dict[str, Any]:
        payload = {
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
        if scoring_endpoint:
            payload["scoring_endpoint"] = scoring_endpoint
        return payload

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
                    scoring_endpoint=_scoring_endpoint(evaluated),
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
        skipped = [str(i) for i in (evaluated.get("skipped") or []) if str(i).strip()]
        passed, reasons, warnings = spec_verdict(
            resolved,
            answers,
            supports_confidence=confidence,
            include_path=include_path,
            skipped=skipped,
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
            probability = None
            if isinstance(raw, Mapping) and isinstance(raw.get("probability"), (int, float)):
                if not isinstance(raw.get("probability"), bool):
                    probability = float(raw["probability"])
            elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
                probability = float(raw)
            if probability is not None:
                cell["probability"] = probability
                threshold = 0.8
                if isinstance(question.pass_if, Mapping) and "gte" in question.pass_if:
                    try:
                        threshold = float(question.pass_if["gte"])
                    except (TypeError, ValueError):
                        threshold = 0.8
                cell["choice"] = "Yes" if probability >= threshold else "No"
            elif isinstance(raw, Mapping) and raw.get("score") is not None:
                cell["score"] = raw.get("score")
                cell["choice"] = str(raw.get("score"))
            if cell.get("choice"):
                cell["reason"] = f"{question.ask} {cell['choice']}"
            cells[question.id] = cell
        merged_answers = {**pass_answers, **extra_answers}
        extra_questions = {q.id: {"instructions": q.ask, "type": q.type} for q in resolved.extras}
        extra_failures = extra_block_failures(resolved, answers, skipped=skipped)
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
                scoring_endpoint=_scoring_endpoint(evaluated),
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
        """Decision scoring does not make a follow-up chat call."""
        del reasons, judged, check, transcript_tail, expected_output, actual_output
        return None


def _scoring_endpoint(evaluated: Mapping[str, Any]) -> str | None:
    raw = evaluated.get("scoring_endpoint")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _sum_judge_usage(rounds: list[Mapping[str, Any]]) -> dict[str, Any] | None:
    from skillgate_ai.usage import usage_from_mapping

    tokens_in = tokens_out = tokens_total = cost = None
    known = False
    for row in rounds:
        parsed = usage_from_mapping(row.get("usage") if isinstance(row, Mapping) else None)
        if parsed is None:
            continue
        known = True
        if parsed.tokens_in is not None:
            tokens_in = (tokens_in or 0) + parsed.tokens_in
        if parsed.tokens_out is not None:
            tokens_out = (tokens_out or 0) + parsed.tokens_out
        if parsed.tokens_total is not None:
            tokens_total = (tokens_total or 0) + parsed.tokens_total
        if parsed.cost_usd is not None:
            cost = (cost or 0.0) + parsed.cost_usd
    if not known:
        return None
    return {
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens_total": tokens_total,
        "cost_usd": cost,
    }


def _as_path(value: Any) -> Path | None:
    if isinstance(value, Path):
        return value
    if isinstance(value, str) and value.strip():
        return Path(value)
    return None


def ping_openai_backend(backend: JudgeBackend, *, display_name: str = DISPLAY_NAME) -> dict[str, Any]:
    del display_name
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
        return {
            "ok": True,
            "message": "Connected to the judge.",
            "scoring_endpoint": "decisions",
        }
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
    from skillgate_ai.errors import SkillGateError

    del why_enabled
    name = (backend or "decisions").strip().lower()
    if name in {"structured", "responses", "chat", "completions"}:
        from skillgate_ai.judge_providers.decision import CHAT_NOT_A_JUDGE

        raise SkillGateError(CHAT_NOT_A_JUDGE, exit_code=2)
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
        why_enabled=False,
        reasoning_effort=reasoning_effort,
        timeout_sec=timeout_sec,
        display_name=display_name,
        provider="openai",
        chosen=chosen,
        supports_why=False,
        supports_confidence=True,
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
    "collect_images",
    "make_openai_judge",
    "redact_secrets",
    "user_message_for_status",
]
