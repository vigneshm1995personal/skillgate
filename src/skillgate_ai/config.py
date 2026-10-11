"""Model-key configuration from the Skill Gate key store and SKILLGATE_* env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from skillgate_ai.errors import MissingLLMKeyError
from skillgate_ai.judge_bank import DEFAULT_MIN_CONFIDENCE as DEFAULT_JUDGE_MIN_CONFIDENCE

ROOT_ENV_NAMES = (
    "CURSOR_API_KEY",
    "CODEX_API_KEY",
    "OPENAI_API_KEY",
    "AI_GATEWAY_API_KEY",
    "ANTHROPIC_API_KEY",
    "JEV_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
)

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"
DEFAULT_GATEWAY_MODEL = "openai/gpt-4o-mini"
DEFAULT_JUDGE_MODEL = "gpt-6-luna"
DEFAULT_JUDGE_BACKEND = "decisions"
DEFAULT_JUDGE_PREF = "auto"
DEFAULT_JUDGE_TIMEOUT_SEC = 20.0
DEFAULT_JUDGE_REASONING_EFFORT = "low"

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


def _base_url(keys: dict[str, str] | None = None) -> str:
    explicit = os.environ.get("AI_GATEWAY_BASE_URL", "").strip() or os.environ.get(
        "SKILLGATE_AI_GATEWAY_BASE_URL", ""
    ).strip()
    if explicit:
        return explicit.rstrip("/")
    if keys and keys.get("AI_GATEWAY_API_KEY"):
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
    judge_pref: str = DEFAULT_JUDGE_PREF
    judge_backend: str = DEFAULT_JUDGE_BACKEND
    judge_model: str = DEFAULT_JUDGE_MODEL
    judge_timeout_sec: float = DEFAULT_JUDGE_TIMEOUT_SEC
    judge_min_confidence: float = DEFAULT_JUDGE_MIN_CONFIDENCE
    judge_why: bool = True
    judge_reasoning_effort: str = DEFAULT_JUDGE_REASONING_EFFORT
    jev_api_key: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None
    judge_provider: str = "auto"
    judge_chosen: bool = False
    judge_region: str | None = None
    judge_endpoint: str | None = None
    judge_provider_model: str | None = None
    judge_decisions_path: str | None = None

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
            found.append("cursor-agent")
        if self.codex_api_key:
            found.append("codex")
        if self.gateway_api_key:
            found.append("OpenAI-compatible")
        elif self.openai_api_key:
            found.append("OpenAI-compatible")
        if self.anthropic_api_key:
            found.append("anthropic")
        return found

    @property
    def available_harnesses(self) -> list[str]:
        found = ["cursor-agent", "codex"]
        if self.anthropic_api_key or self.gateway_api_key or self.openai_api_key:
            found.append("llm")
        return found

    @property
    def default_harness(self) -> str:
        from skillgate_ai.harness import auto_live_harness_name

        return auto_live_harness_name(self)


def get_llm_config(root: Path | None = None) -> LLMConfig:
    from skillgate_ai.keys import resolve_provider_keys
    from skillgate_ai.paths import project_root

    keys = resolve_provider_keys(root if root is not None else project_root())
    openai_key = keys.get("OPENAI_API_KEY")
    from skillgate_ai.judge_settings import load_judge_settings

    settings = load_judge_settings(root if root is not None else project_root())
    return LLMConfig(
        cursor_api_key=keys.get("CURSOR_API_KEY"),
        gateway_api_key=keys.get("AI_GATEWAY_API_KEY"),
        openai_api_key=openai_key,
        gateway_base_url=_base_url(keys),
        gateway_model=os.environ.get("SKILLGATE_MODEL", DEFAULT_GATEWAY_MODEL),
        anthropic_api_key=keys.get("ANTHROPIC_API_KEY"),
        anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
        cursor_agent_bin=os.environ.get("CURSOR_AGENT_BIN", "agent"),
        codex_api_key=keys.get("CODEX_API_KEY") or openai_key,
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
        judge_pref=_judge_pref(),
        judge_backend=_judge_backend(),
        judge_model=_opt("SKILLGATE_JUDGE_MODEL") or DEFAULT_JUDGE_MODEL,
        judge_timeout_sec=_env_float("SKILLGATE_JUDGE_TIMEOUT_SEC", DEFAULT_JUDGE_TIMEOUT_SEC),
        judge_min_confidence=_env_float(
            "SKILLGATE_JUDGE_MIN_CONFIDENCE", DEFAULT_JUDGE_MIN_CONFIDENCE
        ),
        judge_why=_env_bool("SKILLGATE_JUDGE_WHY", True),
        judge_reasoning_effort=_opt("SKILLGATE_JUDGE_REASONING_EFFORT")
        or DEFAULT_JUDGE_REASONING_EFFORT,
        jev_api_key=keys.get("JEV_API_KEY"),
        aws_access_key_id=keys.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=keys.get("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=keys.get("AWS_SESSION_TOKEN"),
        judge_provider=settings.provider,
        judge_chosen=settings.chosen,
        judge_region=settings.region,
        judge_endpoint=settings.base_url,
        judge_provider_model=settings.model,
        judge_decisions_path=settings.decisions_path,
    )


def _judge_pref() -> str:
    raw = (os.environ.get("SKILLGATE_JUDGE") or DEFAULT_JUDGE_PREF).strip().lower()
    if raw in {"auto", "openai", "skip"}:
        return raw
    return DEFAULT_JUDGE_PREF


def _judge_backend() -> str:
    raw = (os.environ.get("SKILLGATE_JUDGE_BACKEND") or DEFAULT_JUDGE_BACKEND).strip().lower()
    if raw in {"structured", "responses"}:
        return "responses"
    if raw == "decisions":
        return "decisions"
    return DEFAULT_JUDGE_BACKEND


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


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


NO_KEY_MESSAGE = "No model key found."
NO_KEY_HINT = "Add a model key in Settings or run `skillgate keys set`"
UI_NO_KEY_HINT = "Add a key in Settings, then press Run."


def missing_key_error(*, live: bool = True, for_codex: bool = False) -> MissingLLMKeyError:
    del live
    if for_codex:
        hint = (
            "Codex CLI needs a key in Settings (`skillgate keys set`) "
            "or a ChatGPT login (`codex login`)."
        )
    else:
        hint = NO_KEY_HINT
    return MissingLLMKeyError(NO_KEY_MESSAGE, hint=hint)


def merge_env_file(path: Path, updates: dict[str, str]) -> None:
    """Write or clear known keys in a ``.env`` file. Empty value removes the key."""
    existing = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    written: set[str] = set()
    out: list[str] = []
    for line in existing:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates:
            value = updates[key]
            if value:
                out.append(f"{key}={value}")
            written.add(key)
            continue
        out.append(line)
    for key, value in updates.items():
        if key not in written and value:
            out.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(out)
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")
