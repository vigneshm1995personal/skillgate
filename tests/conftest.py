from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def plain_text(text: str) -> str:
    """Strip ANSI so help-text asserts work under GITHUB_ACTIONS/FORCE_COLOR."""
    return _ANSI_RE.sub("", text or "")

ROOT = Path(__file__).resolve().parents[1]

os.environ["AI_GATEWAY_API_KEY"] = ""
os.environ["CURSOR_API_KEY"] = ""
os.environ["CODEX_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["SKILLGATE_OPENAI_API_KEY"] = ""
os.environ["SKILLGATE_AI_GATEWAY_API_KEY"] = ""
os.environ["SKILLGATE_CURSOR_API_KEY"] = ""
os.environ["SKILLGATE_CODEX_API_KEY"] = ""
os.environ["SKILLGATE_ANTHROPIC_API_KEY"] = ""
os.environ["SKILLGATE_JEV_API_KEY"] = ""
os.environ["SKILLGATE_CLOUDFLARE_API_TOKEN"] = ""
os.environ["CLOUDFLARE_API_TOKEN"] = ""
os.environ["SKILLGATE_AWS_ACCESS_KEY_ID"] = ""
os.environ["SKILLGATE_AWS_SECRET_ACCESS_KEY"] = ""
os.environ["SKILLGATE_AWS_SESSION_TOKEN"] = ""
os.environ["JEV_API_KEY"] = ""
os.environ["AWS_ACCESS_KEY_ID"] = ""
os.environ["AWS_SECRET_ACCESS_KEY"] = ""
os.environ["AWS_SESSION_TOKEN"] = ""


@pytest.fixture(autouse=True)
def _no_live_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    from skillgate_ai.keys import reset_key_env_bindings

    reset_key_env_bindings()
    monkeypatch.setattr("skillgate_ai.harness._codex_session_ok", lambda cfg: False)
    monkeypatch.setattr("skillgate_ai.harness._cursor_session_ok", lambda cfg: False)
    monkeypatch.setattr("skillgate_ai.harness._claude_session_ok", lambda cfg: False)
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "")
    monkeypatch.setenv("CURSOR_API_KEY", "")
    monkeypatch.setenv("CODEX_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("SKILLGATE_OPENAI_API_KEY", "")
    monkeypatch.setenv("SKILLGATE_AI_GATEWAY_API_KEY", "")
    monkeypatch.setenv("SKILLGATE_CURSOR_API_KEY", "")
    monkeypatch.setenv("SKILLGATE_CODEX_API_KEY", "")
    monkeypatch.setenv("SKILLGATE_ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("SKILLGATE_JEV_API_KEY", "")
    monkeypatch.setenv("SKILLGATE_CLOUDFLARE_API_TOKEN", "")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "")
    monkeypatch.setenv("SKILLGATE_AWS_ACCESS_KEY_ID", "")
    monkeypatch.setenv("SKILLGATE_AWS_SECRET_ACCESS_KEY", "")
    monkeypatch.setenv("SKILLGATE_AWS_SESSION_TOKEN", "")
    monkeypatch.setenv("JEV_API_KEY", "")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "")
    monkeypatch.setenv("SKILLGATE_MODE", "local")
    monkeypatch.delenv("SKILLGATE_JUDGE", raising=False)
    monkeypatch.delenv("SKILLGATE_JUDGE_BACKEND", raising=False)
    monkeypatch.delenv("SKILLGATE_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("SKILLGATE_JUDGE_WHY", raising=False)


@pytest.fixture(autouse=True)
def _isolate_codex_home(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let pytest inherit or write the developer's ~/.codex/config.toml."""
    isolated = tmp_path_factory.mktemp("codex-home")
    monkeypatch.setenv("CODEX_HOME", str(isolated))


def enable_cursor_agent(monkeypatch: pytest.MonkeyPatch, root: Path | None = None) -> None:
    if root is not None:
        monkeypatch.setenv("SKILLGATE_ROOT", str(root))
    monkeypatch.setenv("SKILLGATE_CURSOR_API_KEY", "cur-test")
    monkeypatch.setattr("skillgate_ai.harness._resolve_agent_bin", lambda _preferred: "/bin/agent")
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _preferred: None)


@pytest.fixture
def project_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("SKILLGATE_ROOT", str(ROOT))
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(tmp_path / "cursor-skills"))
    monkeypatch.setenv("SKILLGATE_CODEX_SKILLS", str(tmp_path / "codex-skills"))
    monkeypatch.setenv("SKILLGATE_CLAUDE_SKILLS", str(tmp_path / "claude-skills"))
    monkeypatch.setenv("CURSOR_API_KEY", "")
    monkeypatch.setenv("CODEX_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.delenv("SKILLGATE_TASK_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("SKILLGATE_JUDGE", raising=False)
    monkeypatch.delenv("SKILLGATE_JUDGE_BACKEND", raising=False)
    monkeypatch.delenv("SKILLGATE_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("SKILLGATE_JUDGE_WHY", raising=False)
    monkeypatch.delenv("CODEX_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("CODEX_MODEL", raising=False)
    return ROOT
