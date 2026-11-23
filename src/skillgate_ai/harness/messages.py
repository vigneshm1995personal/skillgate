"""Agent harnesses: Cursor Agent, Codex CLI, and Claude Code in the sandbox workspace."""

from __future__ import annotations

import json
import re

from skillgate_ai.errors import HarnessError
from skillgate_ai.harness.base import (
    _CODEX_REJECTED_MODEL,
    _CODEX_SUPPORTED_MODELS,
    CODEX_CHATGPT_DEFAULT,
)

_MODEL_ACCESS_ERROR = re.compile(
    r"(?:"
    r"there's an issue with the selected model"
    r"|model not found"
    r"|does not have access to (?:the )?model"
    r"|not available on your plan"
    r"|is not supported when using Codex"
    r"|model is not supported"
    r")",
    re.IGNORECASE,
)


def _claude_model_access_error(stdout: str, stderr: str) -> bool:
    """True when Claude Code refused the chosen/default model on the first request."""
    blob = f"{stdout}\n{stderr}"
    return bool(_MODEL_ACCESS_ERROR.search(blob))


def _claude_model_access_message(model: str | None) -> str:
    named = (model or "").strip()
    if named:
        return f"The agent couldn't use the selected model {named!r}."
    return "The agent couldn't use its default model."


_CLAUDE_MODEL_ACCESS_HINT = "Pass --model with an available alias (for example, --model sonnet)."


def _codex_rejected_chatgpt_model(stdout: str, stderr: str) -> bool:
    blob = f"{stdout}\n{stderr}"
    return "is not supported when using Codex" in blob or bool(_CODEX_REJECTED_MODEL.search(blob))


def _codex_rejected_model(stdout: str, stderr: str) -> tuple[str | None, list[str]]:
    blob = f"{stdout}\n{stderr}"
    match = _CODEX_REJECTED_MODEL.search(blob)
    rejected = match.group(1).strip() if match else None
    accepted: list[str] = []
    listed = _CODEX_SUPPORTED_MODELS.search(blob)
    if listed:
        raw = listed.group(1).strip()
        for part in re.split(r"[,/]| and ", raw):
            name = part.strip().strip(".")
            if name.startswith("gpt-") and name not in accepted:
                accepted.append(name)
    return rejected, accepted


def codex_chatgpt_model_hint(
    model: str | None,
    *,
    accepted: list[str] | None = None,
) -> str:
    rejected = (model or "").strip()
    catalog = [item for item in (accepted or []) if item and item != rejected]
    if not catalog:
        from skillgate_ai.harness.agents import CodexCliHarness

        catalog = [item for item in CodexCliHarness.supported_models if item != rejected]
    models = ", ".join(catalog) if catalog else CODEX_CHATGPT_DEFAULT
    return (
        "CLI login rejected that model. "
        f"Pass --model with a supported id ({models}), "
        f"or change model in ~/.codex/config.toml."
    )


_AUTH_FAILURE_RE = re.compile(
    r"unable to fetch user details"
    r"|not logged in"
    r"|not authenticated"
    r"|authentication required"
    r"|please (?:re-?)?log ?in"
    r"|invalid api key",
    re.IGNORECASE,
)

USAGE_LIMIT_MESSAGE = "The agent hit a usage limit. This check cannot run."

MODEL_UNAVAILABLE_MESSAGE = "The agent couldn't use this model. This check cannot run."

_USAGE_LIMIT_RE = re.compile(
    r"ActionRequiredError|Weekly usage limit reached|usage limit reached|"
    r"You've hit your session limit|hit your session limit|session limit\b",
    re.IGNORECASE,
)

_MODEL_UNAVAILABLE_RE = re.compile(
    r"cannot use this model(?:\s*:\s*\S+)?",
    re.IGNORECASE,
)


def usage_limit_message(stdout: str, stderr: str = "", transcript: str = "") -> str | None:
    """Agent quota / usage-limit text is cannot-run, not a quality red."""
    blob = "\n".join(part for part in (stdout, stderr, transcript) if part)
    if not blob or not _USAGE_LIMIT_RE.search(blob):
        return None
    if _USAGE_LIMIT_RE.search(stderr or ""):
        return USAGE_LIMIT_MESSAGE
    if "ActionRequiredError" in blob:
        return USAGE_LIMIT_MESSAGE
    for line in blob.splitlines():
        text = line.strip()
        if not text.startswith("{"):
            if _USAGE_LIMIT_RE.search(text):
                return USAGE_LIMIT_MESSAGE
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        kind = str(obj.get("type") or "")
        errored = kind == "error" or (kind == "result" and obj.get("is_error") is True)
        payload = " ".join(str(obj.get(key) or "") for key in ("message", "error", "result"))
        if (errored or kind == "error") and _USAGE_LIMIT_RE.search(payload):
            return USAGE_LIMIT_MESSAGE
    if re.search(r"Weekly usage limit reached", blob, re.IGNORECASE):
        return USAGE_LIMIT_MESSAGE
    return None


def model_unavailable_message(stdout: str, stderr: str = "", transcript: str = "") -> str | None:
    """Cursor 'Cannot use this model' is cannot-run, not a quality red.

    Claude's 'There's an issue with the selected model' stays on the
    Claude-specific handler so that message is unchanged.
    """
    blob = "\n".join(part for part in (stdout, stderr, transcript) if part)
    if not blob or not _MODEL_UNAVAILABLE_RE.search(blob):
        return None
    if _MODEL_UNAVAILABLE_RE.search(stderr or ""):
        return MODEL_UNAVAILABLE_MESSAGE
    for line in blob.splitlines():
        text = line.strip()
        if not text.startswith("{"):
            if _MODEL_UNAVAILABLE_RE.search(text):
                return MODEL_UNAVAILABLE_MESSAGE
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        kind = str(obj.get("type") or "")
        errored = kind == "error" or (kind == "result" and obj.get("is_error") is True)
        payload = " ".join(str(obj.get(key) or "") for key in ("message", "error", "result"))
        if (errored or kind == "error") and _MODEL_UNAVAILABLE_RE.search(payload):
            return MODEL_UNAVAILABLE_MESSAGE
    if _MODEL_UNAVAILABLE_RE.search(blob):
        return MODEL_UNAVAILABLE_MESSAGE
    return None


def cannot_run_message(stdout: str, stderr: str = "", transcript: str = "") -> str | None:
    return (
        usage_limit_message(stdout, stderr, transcript)
        or auth_failure_message(stdout, stderr, transcript)
        or model_unavailable_message(stdout, stderr, transcript)
    )


def _raise_if_cannot_run(stdout: str, stderr: str, transcript: str = "") -> None:
    _raise_if_auth_failed(stdout, stderr, transcript)
    quota = usage_limit_message(stdout, stderr, transcript)
    if quota:
        raise HarnessError(
            quota,
            hint="Wait until the agent quota resets, then retry.",
            exit_code=2,
        )
    blocked = model_unavailable_message(stdout, stderr, transcript)
    if blocked is None:
        return
    raise HarnessError(
        blocked,
        hint="Pick an available model, then retry.",
        exit_code=2,
    )


def auth_failure_message(stdout: str, stderr: str, transcript: str = "") -> str | None:
    """Auth failure in harness stderr, transcript, or an error event. Not assistant prose."""
    if _AUTH_FAILURE_RE.search(stderr or ""):
        return "The agent is not signed in."
    sources = (stdout or "", transcript or "")
    for source in sources:
        for line in source.splitlines():
            text = line.strip()
            if not text.startswith("{") and _AUTH_FAILURE_RE.search(text):
                return "The agent is not signed in."
    for line in (stdout or "").splitlines():
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        kind = str(obj.get("type") or "")
        errored = kind == "error" or (kind == "result" and obj.get("is_error") is True)
        if not errored:
            continue
        blob = " ".join(str(obj.get(key) or "") for key in ("message", "error", "result"))
        if _AUTH_FAILURE_RE.search(blob):
            return "The agent is not signed in."
    return None


def _raise_if_auth_failed(stdout: str, stderr: str, transcript: str = "") -> None:
    message = auth_failure_message(stdout, stderr, transcript)
    if message is None:
        return
    raise HarnessError(
        message,
        hint="Run `skillgate login`.",
        exit_code=2,
    )
