"""OpenAI outcome judge: Decisions by default, Responses fallback."""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

import httpx

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

_LOG = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-6-luna"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TIMEOUT_SEC = 20.0
WHY_TIMEOUT_SEC = 10.0
WHY_MAX_OUTPUT_TOKENS = 128
TRANSCRIPT_TAIL_CHARS = 4000
IMAGE_MAX_BYTES = 4 * 1024 * 1024
IMAGE_MAX_COUNT = 3
INLINE_MAGICS = {"jpeg": "image/jpeg", "png": "image/png"}
DISPLAY_NAME = "OpenAI (your key)"
_TRANSIENT = frozenset({429, 502, 503, 504})
_QUOTA_CODES = frozenset({"insufficient_quota", "credit_balance_exhausted"})
_RETRY_BACKOFF_SEC = (0.05, 0.1)
_MAX_ATTEMPTS = 3
_SK_TOKEN = re.compile(r"sk-[A-Za-z0-9_*\-]{2,}")
OUT_OF_CREDITS = (
    "Your OpenAI account is out of credits. Add credits at platform.openai.com "
    "billing, then try again."
)

PostFn = Callable[..., httpx.Response]


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


def redact_secrets(text: str, secret: str | None = None) -> str:
    """Strip the configured key and any sk-… token (full or masked) from text."""
    if not text:
        return text
    out = text
    if secret:
        out = out.replace(secret, "***")
    return _SK_TOKEN.sub("sk-***", out)


def openai_error_code(response: httpx.Response) -> str | None:
    try:
        data = response.json()
    except ValueError:
        return None
    if not isinstance(data, Mapping):
        return None
    err = data.get("error")
    if not isinstance(err, Mapping):
        return None
    for key in ("code", "type"):
        value = err.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def is_quota_exhausted(response: httpx.Response) -> bool:
    return response.status_code == 429 and openai_error_code(response) in _QUOTA_CODES


def user_message_for_status(status: int, *, error_code: str | None = None) -> str:
    if status == 401:
        return "OpenAI did not accept this API key. Check OPENAI_API_KEY."
    if status == 403:
        return "OpenAI scoring is not enabled for this key."
    if status == 404:
        return "OpenAI has no scoring endpoint for this key."
    if status == 429 and error_code in _QUOTA_CODES:
        return OUT_OF_CREDITS
    if status == 429:
        return "OpenAI rate limit or quota. Wait and retry, or check billing."
    if status == 400:
        return "OpenAI rejected this scoring request."
    return f"OpenAI scoring failed (HTTP {status})."


def _status_error(response: httpx.Response, *, model: str) -> dict[str, Any]:
    code = openai_error_code(response)
    reason = user_message_for_status(response.status_code, error_code=code)
    _LOG.warning("OpenAI scoring HTTP %s", response.status_code)
    return {"status": "error", "reason": reason, "model": model}


def post_openai(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_sec: float,
    post: PostFn | None = None,
    retries: bool = True,
) -> httpx.Response:
    sender = post or httpx.post
    attempts = _MAX_ATTEMPTS if retries else 1
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            response = sender(url, headers=headers, json=payload, timeout=timeout_sec)
        except httpx.TimeoutException:
            raise
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt >= attempts - 1:
                raise
            _LOG.warning(
                "OpenAI scoring transport error (attempt %s/%s): %s",
                attempt + 1,
                attempts,
                type(exc).__name__,
            )
            time.sleep(_RETRY_BACKOFF_SEC[min(attempt, len(_RETRY_BACKOFF_SEC) - 1)])
            continue
        if (
            response.status_code in _TRANSIENT
            and attempt < attempts - 1
            and not is_quota_exhausted(response)
        ):
            _LOG.warning(
                "OpenAI scoring HTTP %s (attempt %s/%s)",
                response.status_code,
                attempt + 1,
                attempts,
            )
            time.sleep(_RETRY_BACKOFF_SEC[min(attempt, len(_RETRY_BACKOFF_SEC) - 1)])
            continue
        return response
    assert last_exc is not None
    raise last_exc


def _post_openai_json(
    url: str,
    *,
    api_key: str,
    payload: dict[str, Any],
    timeout_sec: float,
    model: str,
    post: PostFn | None = None,
    retries: bool = True,
) -> dict[str, Any]:
    """POST JSON. Transport/HTTP/parse failures return ``status=error``."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        response = post_openai(
            url,
            headers=headers,
            payload=payload,
            timeout_sec=timeout_sec,
            post=post,
            retries=retries,
        )
    except httpx.TimeoutException:
        return {"status": "error", "reason": "OpenAI scoring timed out.", "model": model}
    except httpx.HTTPError:
        return {"status": "error", "reason": "OpenAI scoring failed.", "model": model}
    if response.status_code >= 400:
        return _status_error(response, model=model)
    try:
        data = response.json()
    except ValueError:
        return {"status": "error", "reason": UNUSABLE_ANSWER, "model": model}
    if not isinstance(data, Mapping):
        return {"status": "error", "reason": UNUSABLE_ANSWER, "model": model}
    return {"status": "ok", "data": data}


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
                magic = _magic_of(header)
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


def _magic_of(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    return None


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


def _mismatch_reason(
    state: Mapping[str, Any],
    artifacts: list[dict[str, Any]],
) -> str | None:
    from skillgate_ai.engine import expected_output_mismatch_reason

    golden = state.get("golden")
    actual = state.get("actual_output")
    return expected_output_mismatch_reason(
        golden=golden if isinstance(golden, dict) else None,
        actual=actual if isinstance(actual, dict) else None,
        artifacts=artifacts,
    )


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
        if images:
            content: list[dict[str, Any]] = [{"type": "input_text", "text": text}, *images]
            payload_input: str | list[dict[str, Any]] = [
                {"role": "user", "content": content}
            ]
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
        result = _post_openai_json(
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
        raw = _answers_from_decisions_list(data)
        answers = _normalize_answers(raw)
        if unusable_answers(answers):
            return {
                "status": "error",
                "reason": UNUSABLE_ANSWER,
                "model": str(data.get("model") or self.model),
                "answers": answers,
                "usage": data.get("usage") if isinstance(data.get("usage"), dict) else None,
            }
        return {
            "status": "completed",
            "model": str(data.get("model") or self.model),
            "answers": answers,
            "usage": data.get("usage") if isinstance(data.get("usage"), dict) else None,
        }


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
        user_content: str | list[dict[str, Any]]
        if images:
            user_content = [{"type": "input_text", "text": text}, *images]
        else:
            user_content = text
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
        result = _post_openai_json(
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
        answers = _normalize_answers(parsed)
        if unusable_answers(answers):
            return {
                "status": "error",
                "reason": UNUSABLE_ANSWER,
                "model": str(data.get("model") or self.model),
                "answers": answers,
            }
        return {
            "status": "completed",
            "model": str(data.get("model") or self.model),
            "answers": answers,
            "usage": data.get("usage") if isinstance(data.get("usage"), dict) else None,
        }


class OutcomeJudge:
    """Applies the Pass lock. HTTP stays on the backend."""

    name = "openai"

    def __init__(
        self,
        backend: JudgeBackend,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        why_enabled: bool = True,
        reasoning_effort: str = "low",
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
        post: PostFn | None = None,
    ) -> None:
        self.backend = backend
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.min_confidence = min_confidence
        self.why_enabled = why_enabled
        self.reasoning_effort = reasoning_effort
        self.timeout_sec = timeout_sec
        self._post = post

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
        return self._stamp(evaluated, artifacts=artifacts, omitted=omitted, state=state)

    def _stamp(
        self,
        evaluated: Mapping[str, Any],
        *,
        artifacts: list[dict[str, Any]],
        omitted: list[dict[str, Any]],
        state: Mapping[str, Any],
    ) -> dict[str, Any]:
        model = str(evaluated.get("model") or self.model)
        citations = {"artifacts": list(artifacts), "omitted_images": omitted}
        mismatch = _mismatch_reason(state, artifacts)
        if evaluated.get("status") != "completed":
            reason = str(evaluated.get("reason") or "OpenAI scoring failed.")
            why = None
            if self.why_enabled and reason == UNUSABLE_ANSWER:
                why_reasons = [reason]
                if mismatch and mismatch not in why_reasons:
                    why_reasons.append(mismatch)
                why = self._why_call(state, why_reasons)
            return {
                "status": "error",
                "provider": "openai",
                "backend": self.backend.name,
                "display_name": DISPLAY_NAME,
                "model": model,
                "passed": False,
                "reasons": [reason],
                "why": why,
                "answers": evaluated.get("answers") or {},
                "soft_answers": {},
                "questions": all_questions(),
                "soft_questions": {k: all_questions()[k] for k in SOFT_CELL_ORDER},
                "cells": {},
                "citations": citations,
                "usage": evaluated.get("usage"),
                "warnings": [],
                "min_confidence": self.min_confidence,
                "blocks_deploy": True,
            }
        answers = evaluated.get("answers") if isinstance(evaluated.get("answers"), dict) else {}
        passed, reasons = outcome_verdict(answers)
        if mismatch:
            passed = False
            if mismatch not in reasons:
                reasons = [mismatch, *reasons]
        warnings = low_confidence_warnings(
            answers,
            min_confidence=self.min_confidence,
            expect_confidence=self.backend.name == "decisions",
        )
        if not passed:
            warnings = []
        pass_answers = {key: answers[key] for key in CHECK_CELL_ORDER if key in answers}
        soft_answers = {key: answers[key] for key in SOFT_CELL_ORDER if key in answers}
        cells: dict[str, dict[str, Any]] = {}
        for key in CHECK_CELL_ORDER:
            cells[key] = _cell_entry(key, pass_answers.get(key), CHECK_CELL_LABELS)
        for key in SOFT_CELL_ORDER:
            cells[key] = _cell_entry(key, soft_answers.get(key), SOFT_CELL_LABELS)
        why = None
        no_trigger = state.get("expect_skill") is None
        if not passed and self.why_enabled and (not no_trigger or mismatch):
            why = self._why_call(state, reasons)
        return {
            "status": "completed",
            "provider": "openai",
            "backend": self.backend.name,
            "display_name": DISPLAY_NAME,
            "model": model,
            "passed": passed,
            "reasons": reasons,
            "why": why,
            "answers": pass_answers,
            "soft_answers": soft_answers,
            "questions": {k: all_questions()[k] for k in CHECK_CELL_ORDER},
            "soft_questions": {k: all_questions()[k] for k in SOFT_CELL_ORDER},
            "cells": cells,
            "citations": citations,
            "usage": evaluated.get("usage"),
            "warnings": warnings,
            "min_confidence": self.min_confidence,
            "blocks_deploy": True,
        }

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
        result = _post_openai_json(
            f"{self.base_url}/responses",
            api_key=self.api_key,
            payload=payload,
            timeout_sec=WHY_TIMEOUT_SEC,
            model=self.model,
            post=self._post,
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
            return redact_secrets(why.strip(), self.api_key)
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
        api_key=api_key,
        base_url=base_url,
        model=model,
        min_confidence=min_confidence,
        why_enabled=why_enabled,
        reasoning_effort=reasoning_effort,
        timeout_sec=timeout_sec,
        post=post,
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
