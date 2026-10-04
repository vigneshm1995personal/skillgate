"""BYOLLM configuration from `.env` / process env. No vault, no db-creds."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from skillgate_ai.errors import MissingLLMKeyError

ROOT_ENV_NAMES = (
    "CURSOR_API_KEY",
    "CODEX_API_KEY",
    "OPENAI_API_KEY",
    "AI_GATEWAY_API_KEY",
    "ANTHROPIC_API_KEY",
)

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"
DEFAULT_GATEWAY_MODEL = "openai/gpt-4o-mini"

CODEX_REASONING_EFFORTS = frozenset({"low", "medium", "high", "ultra"})
DEFAULT_CODEX_REASONING_EFFORT = "medium"


def normalize_codex_reasoning_effort(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if raw in CODEX_REASONING_EFFORTS:
        return raw
    return DEFAULT_CODEX_REASONING_EFFORT


def load_env(project_root: Path | None = None) -> None:
    """Load `.env` without overriding real env. Does not load db-creds.env."""
    roots: list[Path] = []
    if project_root:
        roots.append(project_root)
    roots.append(Path.cwd())
    seen: set[Path] = set()
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            resolved = root
        if resolved in seen:
            continue
        seen.add(resolved)
        path = resolved / ".env"
        if path.is_file():
            load_dotenv(path, override=False)


def _opt(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def _base_url() -> str:
    explicit = os.environ.get("AI_GATEWAY_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    if _opt("AI_GATEWAY_API_KEY"):
        return DEFAULT_GATEWAY_BASE_URL
    return DEFAULT_OPENAI_BASE_URL


@dataclass(frozen=True)
class LLMConfig:
    cursor_api_key: str | None
    gateway_api_key: str | None
    gateway_base_url: str
    gateway_model: str
    anthropic_api_key: str | None
    anthropic_model: str
    cursor_agent_bin: str
    codex_api_key: str | None
    codex_bin: str
    harness_pref: str
    sandbox_pref: str
    docker_image: str
    codex_reasoning_effort: str = DEFAULT_CODEX_REASONING_EFFORT
    codex_model: str | None = None
    cursor_model: str | None = None
    openai_api_key: str | None = None
    temperature: float = 0.0

    @property
    def has_any_key(self) -> bool:
        return bool(
            self.cursor_api_key
            or self.codex_api_key
            or self.gateway_api_key
            or self.openai_api_key
            or self.anthropic_api_key
        )

    @property
    def live_backends(self) -> list[str]:
        found = []
        if self.cursor_api_key:
            found.append("cursor-agent (CURSOR_API_KEY)")
        if self.codex_api_key:
            found.append("codex (CODEX_API_KEY or OPENAI_API_KEY)")
        if self.gateway_api_key:
            found.append("OpenAI-compatible (AI_GATEWAY_API_KEY)")
        elif self.openai_api_key:
            found.append("OpenAI-compatible (OPENAI_API_KEY)")
        if self.anthropic_api_key:
            found.append("anthropic (ANTHROPIC_API_KEY)")
        return found

    @property
    def available_harnesses(self) -> list[str]:
        found = ["cursor-agent", "codex"]
        if self.anthropic_api_key:
            found.append("llm")
        return found

    @property
    def default_harness(self) -> str:
        from skillgate_ai.harness import auto_live_harness_name

        return auto_live_harness_name(self)


def get_llm_config() -> LLMConfig:
    openai_key = _opt("OPENAI_API_KEY")
    return LLMConfig(
        cursor_api_key=_opt("CURSOR_API_KEY"),
        gateway_api_key=_opt("AI_GATEWAY_API_KEY"),
        openai_api_key=openai_key,
        gateway_base_url=_base_url(),
        gateway_model=os.environ.get("SKILLGATE_MODEL", DEFAULT_GATEWAY_MODEL),
        anthropic_api_key=_opt("ANTHROPIC_API_KEY"),
        anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
        cursor_agent_bin=os.environ.get("CURSOR_AGENT_BIN", "agent"),
        codex_api_key=_opt("CODEX_API_KEY") or openai_key,
        codex_bin=os.environ.get("CODEX_BIN", "codex"),
        harness_pref=os.environ.get("SKILLGATE_HARNESS", "auto").strip().lower() or "auto",
        sandbox_pref=os.environ.get("SKILLGATE_SANDBOX", "local").strip().lower() or "local",
        docker_image=os.environ.get("SKILLGATE_DOCKER_IMAGE", "skillgate-sandbox:v0"),
        codex_reasoning_effort=normalize_codex_reasoning_effort(
            os.environ.get("CODEX_REASONING_EFFORT")
        ),
        codex_model=_opt("CODEX_MODEL"),
        cursor_model=_opt("CURSOR_MODEL"),
        temperature=_env_temperature(),
    )


def _env_temperature() -> float:
    raw = os.environ.get("SKILLGATE_TEMPERATURE", "").strip()
    if not raw:
        return 0.0
    try:
        value = float(raw)
    except ValueError:
        return 0.0
    if value < 0.0 or value > 2.0:
        return 0.0
    return value


def missing_key_error(*, live: bool = True, for_codex: bool = False) -> MissingLLMKeyError:
    del live
    if for_codex:
        hint = (
            "Codex CLI needs a key or a ChatGPT login (`codex login`).\n"
            "  CODEX_API_KEY        Codex CLI harness (preferred)\n"
            "  OPENAI_API_KEY       used when CODEX_API_KEY is unset\n"
            "  or run `codex login` and confirm `codex login status` says Logged in.\n"
            "Skill Gate does not read Codex auth files. Auto still requires an env key.\n"
            "See `.env.example`. For offline checks with no key, the demo harness is default."
        )
    else:
        hint = (
            "Add one of these in `.env` or GitHub Actions secrets:\n"
            "  CURSOR_API_KEY      Cursor Agent harness\n"
            "  CODEX_API_KEY       Codex CLI harness\n"
            "  OPENAI_API_KEY      OpenAI-compatible BYO chat / Codex fallback\n"
            "  AI_GATEWAY_API_KEY  optional OpenAI-compatible HTTP base\n"
            "  ANTHROPIC_API_KEY   Anthropic BYOLLM\n"
            "See `.env.example`. Deterministic fixture checks need no key (`skillgate check`).\n"
            "Live harnesses require a key you own — Skill Gate does not ship a model."
        )
    return MissingLLMKeyError(
        "No model key found. Skill Gate is BYOLLM — it does not ship a hosted model.",
        hint=hint,
    )
