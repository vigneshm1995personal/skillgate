"""User-facing errors. Keep messages actionable; never dump traces as the primary UX."""


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
