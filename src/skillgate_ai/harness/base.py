"""Agent harnesses: Cursor Agent, Codex CLI, and Claude Code in the sandbox workspace."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Protocol

from skillgate_ai.ingest import Skill
from skillgate_ai.sandbox import Sandbox
from skillgate_ai.scorers import TriggerEvidence
from skillgate_ai.usage import (
    Usage,
    merge_usage,
    parse_usage_line,
)

AUTH_API_KEY = "api_key"

AUTH_CLI_LOGIN = "cli_login"

AUTH_NONE = "none"

LOGIN_AGENTS = ("cursor", "codex", "claude")

LOGIN_TIMEOUT_SEC = 600

LOGIN_TIMEOUT_ENV = "SKILLGATE_LOGIN_TIMEOUT"


def _login_timeout_sec() -> float:
    """Official-login timeout (seconds), overridable via SKILLGATE_LOGIN_TIMEOUT."""
    raw = os.environ.get(LOGIN_TIMEOUT_ENV, "").strip()
    if raw:
        try:
            value = float(raw)
        except ValueError:
            value = LOGIN_TIMEOUT_SEC
        if value > 0:
            return value
    return float(LOGIN_TIMEOUT_SEC)


_AGENT_INSTALL = {
    "cursor": "curl https://cursor.com/install -fsS | bash",
    "codex": "npm install -g @openai/codex",
    "claude": "npm install -g @anthropic-ai/claude-code",
}


@dataclass
class HarnessResult:
    trigger: TriggerEvidence
    stdout: str = ""
    stderr: str = ""
    transcript: str = ""
    duration_note: str = ""
    returncode: int | None = None
    usage: Usage | None = None
    spans: list[dict] | None = None
    auth_mode: str = AUTH_API_KEY
    model: str | None = None


def harness_usage(stdout: str) -> Usage | None:
    """Monotonic usage from every JSONL line a harness printed, or None.

    The same parser the live `RunControl` uses, so an off-stream harness
    (MagicMock sandbox, tests, CLI without a sink) reports identical numbers.
    """
    usage = Usage()
    for line in stdout.splitlines():
        update = parse_usage_line(line)
        if update is not None:
            usage = merge_usage(usage, update)
    return usage if usage.known else None


class Harness(Protocol):
    name: str
    supported_models: tuple[str, ...]

    def run(
        self,
        sandbox: Sandbox,
        prompt: str,
        skills: list[Skill],
        timeout_sec: int,
    ) -> HarnessResult: ...


_STOP = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "to",
    "of",
    "for",
    "in",
    "on",
    "at",
    "from",
    "with",
    "this",
    "that",
    "user",
    "wants",
    "use",
    "when",
    "into",
    "file",
    "files",
    "output",
    "write",
    "it",
    "its",
    "is",
    "be",
    "as",
    "by",
}


def tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOP and len(t) > 1}


def rank_skills(prompt: str, skills: list[Skill]) -> list[tuple[Skill, float]]:
    task_tokens = tokenize(prompt)
    ranked: list[tuple[Skill, float]] = []
    for skill in skills:
        # Description is the trigger surface. Do not split the folder name into
        # keywords (otherwise `pdf-sabotaged` would still fire on PDF tasks).
        desc_tokens = tokenize(skill.description)
        if not task_tokens or not desc_tokens:
            ranked.append((skill, 0.0))
            continue
        overlap = task_tokens & desc_tokens
        score = len(overlap) / max(len(task_tokens), 1)
        if "pdf" in task_tokens and "pdf" in desc_tokens:
            score += 0.35
        if skill.name in prompt.lower() or skill.name.replace("-", " ") in prompt.lower():
            score += 0.1
        ranked.append((skill, score))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked


def select_skill_from_descriptions(prompt: str, skills: list[Skill]) -> str | None:
    ranked = rank_skills(prompt, skills)
    if not ranked:
        return None
    best, score = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    if score < 0.22:
        return None
    if len(ranked) > 1 and score - second < 0.05 and score < 0.45:
        return None
    return best.name


def description_fits_request(prompt: str, skill: Skill) -> bool:
    """True unless the description is a different job (no meaningful overlap).

    Ranking uses overlap / prompt length, so a long legitimate prompt (a SQL
    refusal, a refund success) can score below the 0.22 pick threshold. Trigger
    scoring only vetoes a selected skill when the description has no content
    overlap with the request — meal-planner vs a PDF, not a correct refusal.
    """
    task_tokens = tokenize(prompt)
    desc_tokens = tokenize(skill.description)
    if not task_tokens or not desc_tokens:
        return False
    if task_tokens & desc_tokens:
        return True
    return "pdf" in task_tokens and "pdf" in desc_tokens


LIVE_HARNESS_NAMES = frozenset({"cursor-agent", "codex", "claude", "claude-code"})


def is_live_harness(name: str | None) -> bool:
    """True when a stored/resolved harness can clear Gate and unlock Deploy."""
    return (name or "").strip().lower() in LIVE_HARNESS_NAMES


CODEX_CHATGPT_DEFAULT = "gpt-5.6-luna"

_CODEX_REJECTED_MODEL = re.compile(
    r"The ['\"]([^'\"]+)['\"] model is not supported",
    re.IGNORECASE,
)

_CODEX_SUPPORTED_MODELS = re.compile(
    r"(?:supported models|accepted)\s*[:=]\s*(.+)",
    re.IGNORECASE,
)
