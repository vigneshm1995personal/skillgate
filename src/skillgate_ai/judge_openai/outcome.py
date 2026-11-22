"""Direct-answer scoring. Chat and Responses completion models are refused."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from skillgate_ai.judge_bank import (
    CHECK_CELL_LABELS,
    CHECK_CELL_ORDER,
    DEFAULT_MIN_CONFIDENCE,
    LOW_CONFIDENCE_MAX_ASKS,
    SOFT_CELL_LABELS,
    SOFT_CELL_ORDER,
    all_questions,
    answers_have_low_confidence,
    extract_choice,
    extract_confidence,
    majority_vote_answers,
    vote_round_summaries,
)
from skillgate_ai.judge_context import workspace_files_for_judge
from skillgate_ai.judge_images import collect_images
from skillgate_ai.judge_openai.backend import DEFAULT_TIMEOUT_SEC, DISPLAY_NAME
from skillgate_ai.judge_openai.payload import (
    _cell_entry,
    _expected_outcome_text,
    _path_is_recorded,
    _path_not_available_cell,
    _tail,
)
from skillgate_ai.judge_providers.decision import DecisionModel, require_decision_model
from skillgate_ai.judge_spec import (
    JudgeSpec,
    builtin_spec,
    extra_block_failures,
    spec_verdict,
)
from skillgate_ai.span_facts import resolve_log_facts


def _extra_cell(question: Any, raw: Any) -> tuple[dict[str, Any], dict[str, Any] | None]:
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
    source = "judge"
    if isinstance(raw, Mapping) and raw.get("source"):
        source = str(raw.get("source"))
    cell["source"] = source
    if cell.get("choice"):
        named = str(raw.get("reason") or "").strip() if isinstance(raw, Mapping) else ""
        cell["reason"] = named or f"{question.ask} {cell['choice']}"
    cleaned = None
    if isinstance(raw, Mapping):
        cleaned = dict(raw)
        cleaned.pop("noul", None)
        if cleaned.get("type") == "noul":
            cleaned["type"] = "predicate"
        cleaned.setdefault("source", source)
    return cell, cleaned


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
        backend_conf = getattr(backend, "supports_confidence", None)
        if supports_confidence is not None:
            self.supports_confidence = supports_confidence
        elif isinstance(backend_conf, bool):
            self.supports_confidence = backend_conf
        else:
            self.supports_confidence = getattr(backend, "name", "") == "decisions"

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
        files = workspace_files_for_judge(artifacts if isinstance(artifacts, list) else None)
        state["workspace_files"] = files
        trajectory = (
            kwargs.get("agent_trajectory")
            if isinstance(kwargs.get("agent_trajectory"), Mapping)
            else None
        )
        spans = kwargs.get("spans") if isinstance(kwargs.get("spans"), list) else None
        from skillgate_ai.wording_facts import attach_wording_questions

        skill_text = state.get("skill_instructions") if isinstance(state, Mapping) else None
        resolved = attach_wording_questions(
            resolved, skill_text if isinstance(skill_text, str) else None
        )
        facts = resolve_log_facts(
            resolved,
            spans,
            trajectory=trajectory,
            outputs=files,
            skill_instructions=skill_text if isinstance(skill_text, str) else None,
        )
        ask_spec = resolved
        if facts:
            ask_spec = resolved.with_questions(
                [question for question in resolved.questions if question.id not in facts]
            )
        evaluate = self.backend.evaluate
        try:
            evaluated = evaluate(
                state=state, images=images, timeout_sec=self.timeout_sec, spec=ask_spec
            )
        except TypeError:
            evaluated = evaluate(state=state, images=images, timeout_sec=self.timeout_sec)
        evaluated = self._majority_reask(
            evaluate, state=state, images=images, spec=ask_spec, first=evaluated
        )
        if facts and evaluated.get("status") == "completed":
            raw_answers = evaluated.get("answers")
            answers: dict[str, Any] = dict(raw_answers) if isinstance(raw_answers, dict) else {}
            answers.update(facts)
            evaluated = dict(evaluated)
            evaluated["answers"] = answers
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
        blobs = [row.get("answers") for row in rounds if isinstance(row.get("answers"), dict)]
        merged = majority_vote_answers([blob for blob in blobs if isinstance(blob, dict)])
        last = dict(rounds[-1])
        last["answers"] = merged
        if len(rounds) > 1:
            last["votes"] = vote_round_summaries([blob for blob in blobs if isinstance(blob, dict)])
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
            "review": False,
        }
        if scoring_endpoint:
            payload["scoring_endpoint"] = scoring_endpoint
        return payload

    def _stamp_error(
        self,
        evaluated: Mapping[str, Any],
        *,
        model: str,
        resolved: JudgeSpec,
        citations: dict[str, Any],
        soft_questions: dict[str, Any],
        extra_warnings: list[str],
    ) -> dict[str, Any]:
        reason = str(evaluated.get("reason") or "The judge couldn't score this check.")
        payload = self._finish_payload(
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
            confidence=bool(getattr(self.backend, "supports_confidence", self.supports_confidence)),
        )
        upstream = evaluated.get("upstream")
        if isinstance(upstream, str) and upstream.strip():
            payload["upstream"] = upstream.strip()
        return payload

    def _verdict_cells(
        self,
        pass_answers: dict[str, Any],
        soft_answers: dict[str, Any],
        *,
        include_path: bool,
        confidence: bool,
    ) -> dict[str, dict[str, Any]]:
        cells: dict[str, dict[str, Any]] = {}
        for key in CHECK_CELL_ORDER:
            cells[key] = _cell_entry(key, pass_answers.get(key), CHECK_CELL_LABELS)
            if confidence:
                conf = extract_confidence(pass_answers.get(key))
                if conf is not None and conf < self.min_confidence:
                    cells[key]["status"] = "unsure"
        for key in SOFT_CELL_ORDER:
            if include_path:
                cells[key] = _cell_entry(key, soft_answers.get(key), SOFT_CELL_LABELS)
            else:
                cells[key] = _path_not_available_cell()
        return cells

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
            str(item) for item in (evaluated.get("warnings") or []) if str(item).strip()
        ]
        if evaluated.get("status") != "completed":
            return self._stamp_error(
                evaluated,
                model=model,
                resolved=resolved,
                citations=citations,
                soft_questions=soft_questions,
                extra_warnings=extra_warnings,
            )
        raw_answers = evaluated.get("answers")
        answers: dict[str, Any] = raw_answers if isinstance(raw_answers, dict) else {}
        if not include_path:
            answers = {key: value for key, value in answers.items() if key not in SOFT_CELL_ORDER}
        confidence = bool(getattr(self.backend, "supports_confidence", self.supports_confidence))
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
        cells = self._verdict_cells(
            pass_answers, soft_answers, include_path=include_path, confidence=confidence
        )
        for question in resolved.extras:
            raw = extra_answers.get(question.id)
            cell, cleaned = _extra_cell(question, raw)
            cells[question.id] = cell
            if cleaned is not None:
                extra_answers[question.id] = cleaned
        merged_answers = {**pass_answers, **extra_answers}
        extra_questions = {q.id: {"instructions": q.ask, "type": q.type} for q in resolved.extras}
        extra_failures = extra_block_failures(resolved, answers, skipped=skipped)
        payload = self._finish_payload(
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
        payload["review"] = bool(passed) and any(
            isinstance(cell, dict) and cell.get("status") == "unsure" for cell in cells.values()
        )
        votes = evaluated.get("votes")
        if isinstance(votes, list) and votes:
            payload["votes"] = votes
        return payload

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
