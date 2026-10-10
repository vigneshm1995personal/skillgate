"""User-facing errors. Keep messages actionable; never dump traces as the primary UX."""

from __future__ import annotations

import re

SKILL_CHANGED_MESSAGE = (
    "This skill changed since it passed. Run the checks again, then install."
)

_HASH_MISMATCH = re.compile(
    r"hash|mismatch|skill_md|version mismatch",
    re.IGNORECASE,
)
_INTERNAL_LEAK = re.compile(r"skillgate_|/root/", re.IGNORECASE)
_HEX_DIGEST = re.compile(r"\b[0-9a-f]{8,64}\b", re.IGNORECASE)


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

    def __init__(self, message: str, hint: str | None = None):
        self.message = message
        self.hint = hint
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
    """Live harness requested but no BYOLLM key is configured."""

    exit_code = 2


class AuthorError(SkillGateError):
    """Unused in OSS; kept so private callers that share types still import."""


class HarnessError(SkillGateError):
    """Cursor Agent / Codex CLI / LLM / sandbox failed to start or finish."""


class SandboxError(SkillGateError):
    """Sandbox backend is unavailable or misconfigured."""


class DeployError(SkillGateError):
    """Deploy adapter failed to copy or validate a skill folder."""
