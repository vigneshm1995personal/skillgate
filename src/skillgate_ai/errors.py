"""User-facing errors. Keep messages actionable; never dump traces as the primary UX."""

from __future__ import annotations

import errno
import re
from typing import Any

SKILL_CHANGED_MESSAGE = (
    "This skill changed since it passed. Run the checks again, then install."
)

_HASH_MISMATCH = re.compile(
    r"hash|mismatch|skill_md|version mismatch",
    re.IGNORECASE,
)
_INTERNAL_LEAK = re.compile(r"skillgate_|/root/", re.IGNORECASE)
_HEX_DIGEST = re.compile(r"\b[0-9a-f]{8,64}\b", re.IGNORECASE)

OFFLINE_MESSAGE = "Couldn't reach the model service. Check your internet connection."
BAD_OPENAI_KEY_MESSAGE = "OpenAI did not accept this API key."


def customer_job_error(message: str | None) -> str:
    """Customer-facing install error. Hashes and internal words stay in logs."""
    text = (message or "").strip()
    if not text:
        return text
    if _HASH_MISMATCH.search(text):
        return SKILL_CHANGED_MESSAGE
    if _INTERNAL_LEAK.search(text) or _HEX_DIGEST.search(text):
        return "Couldn't install this skill."
    return text


class SkillGateError(Exception):
    """Base error with a short, human-readable message."""

    exit_code = 1

    def __init__(
        self,
        message: str,
        hint: str | None = None,
        *,
        exit_code: int | None = None,
    ):
        self.message = message
        self.hint = hint
        if exit_code is not None:
            self.exit_code = exit_code
        super().__init__(message)

    def render(self) -> str:
        lines = [self.message]
        if self.hint:
            lines.append(self.hint)
        return "\n".join(lines)


class IngestError(SkillGateError):
    """SKILL.md / agentskills folder failed strict validation."""


class SuiteError(SkillGateError):
    """Eval suite YAML is missing or invalid."""


class MissingLLMKeyError(SkillGateError):
    """Live check requested but no model key is configured."""

    exit_code = 2


class AuthorError(SkillGateError):
    """Unused in OSS; kept so private callers that share types still import."""


class HarnessError(SkillGateError):
    """Cursor Agent / Codex CLI / LLM / sandbox failed to start or finish."""


class SandboxError(SkillGateError):
    """Sandbox backend is unavailable or misconfigured."""


class DeployError(SkillGateError):
    """Deploy adapter failed to copy or validate a skill folder."""


def friendly_os_error(exc: BaseException, *, what: str) -> str:
    """Permission / IO failure without errno text, paths, or a traceback."""
    err = getattr(exc, "errno", None)
    if isinstance(exc, PermissionError) or err in {
        errno.EACCES,
        errno.EPERM,
        errno.EROFS,
    }:
        return f"Couldn't {what}: the folder isn't writable."
    if err in {errno.ENOENT, errno.ENOTDIR}:
        return f"Couldn't {what}: the folder was not found."
    if err in {errno.ENOSPC, errno.EDQUOT}:
        return f"Couldn't {what}: the disk is full."
    return f"Couldn't {what}."


def harness_http_error(status: int, *, openai: bool = True) -> HarnessError:
    if status == 401:
        if openai:
            return HarnessError(
                BAD_OPENAI_KEY_MESSAGE,
                hint="Check OPENAI_API_KEY or AI_GATEWAY_API_KEY and SKILLGATE_MODEL in `.env`.",
            )
        return HarnessError(
            "Anthropic did not accept this API key.",
            hint="Check ANTHROPIC_API_KEY in `.env`.",
        )
    return HarnessError(friendly_http_status(status, openai=openai))


def friendly_http_status(status: int, *, openai: bool = True) -> str:
    if status == 401:
        return (
            BAD_OPENAI_KEY_MESSAGE if openai else "The model service did not accept this API key."
        )
    if status == 403:
        return (
            "OpenAI scoring is not enabled for this key."
            if openai
            else "The model service refused this request."
        )
    if status == 404:
        return (
            "OpenAI has no scoring endpoint for this key."
            if openai
            else "The model service has no matching endpoint."
        )
    if status == 429:
        return "The model service rate-limited this request. Wait and retry, or check billing."
    if status == 400:
        return "The model service rejected this request."
    return "The model service returned an error."


def friendly_validation_error(
    exc: BaseException,
    *,
    kind: str = "Case pack",
    raw: dict[str, Any] | None = None,
) -> str:
    """Plain schema/case error. Never include pydantic.dev URLs or dumps."""
    errors = getattr(exc, "errors", None)
    items = []
    if callable(errors):
        try:
            items = list(errors())
        except Exception:  # noqa: BLE001 - fall through to a generic line
            items = []
    if not items:
        return f"{kind} is invalid."
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        loc = tuple(item.get("loc") or ())
        msg = _plain_pydantic_msg(item.get("msg"))
        inp = item.get("input")
        label = _loc_label(loc, raw=raw, inp=inp)
        if label:
            parts.append(f"{label}: {msg}" if msg else label)
        elif msg:
            parts.append(msg)
    if not parts:
        return f"{kind} is invalid."
    if len(parts) == 1:
        return f"{kind} is invalid: {parts[0]}"
    return f"{kind} is invalid: " + "; ".join(parts)


def _plain_pydantic_msg(msg: object) -> str:
    text = str(msg or "").strip()
    for prefix in ("Value error, ", "Assertion failed, "):
        text = text.removeprefix(prefix)
    if "should be 1" in text.lower() or text.lower() == "input should be 1":
        return "Skill Gate supports schema 1"
    return text.rstrip(".")


def _loc_label(
    loc: tuple[Any, ...],
    *,
    raw: dict[str, Any] | None,
    inp: object,
) -> str:
    if not loc:
        return ""
    if loc[0] in {"schema", "schema_version"}:
        shown = inp if inp is not None else (raw or {}).get("schema")
        if shown is not None:
            return f"schema {shown}"
        return "schema"
    if loc[0] == "cases" and len(loc) >= 2 and isinstance(loc[1], int):
        idx = loc[1]
        case_id = _case_id_at(raw, idx)
        if case_id is None and isinstance(inp, str) and loc[-1] == "id":
            case_id = inp
        if case_id:
            field = loc[-1] if len(loc) > 2 and loc[-1] != "id" else None
            if field and field != "id":
                return f"case {case_id} ({field})"
            return f"case {case_id}"
        return f"case #{idx + 1}"
    if loc[0] == "tasks" and len(loc) >= 2 and isinstance(loc[1], int):
        idx = loc[1]
        task_id = _task_id_at(raw, idx)
        if task_id:
            return f"task {task_id}"
        return f"task #{idx + 1}"
    return ""


def _case_id_at(raw: dict[str, Any] | None, index: int) -> str | None:
    if not raw:
        return None
    cases = raw.get("cases")
    if not isinstance(cases, list) or index >= len(cases):
        return None
    item = cases[index]
    if isinstance(item, dict):
        value = item.get("id")
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _task_id_at(raw: dict[str, Any] | None, index: int) -> str | None:
    if not raw:
        return None
    tasks = raw.get("tasks")
    if not isinstance(tasks, list) or index >= len(tasks):
        return None
    item = tasks[index]
    if isinstance(item, dict):
        value = item.get("id")
        if value is not None and str(value).strip():
            return str(value).strip()
    return None
