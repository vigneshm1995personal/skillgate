from __future__ import annotations

from pathlib import Path

import pytest

from skillgate_ai.config import (
    agent_label,
    load_env,
    merge_env_file,
    missing_key_error,
    normalize_codex_reasoning_effort,
)
from skillgate_ai.errors import MissingLLMKeyError


def test_normalize_codex_reasoning_effort_defaults_invalid() -> None:
    assert normalize_codex_reasoning_effort("bogus") == "medium"
    assert normalize_codex_reasoning_effort("HIGH") == "high"


def test_load_env_reads_dotenv_without_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SKILLGATE_TEST_MARKER", "from-env")
    (tmp_path / ".env").write_text("SKILLGATE_TEST_MARKER=from-file\n", encoding="utf-8")
    load_env(tmp_path)
    assert __import__("os").environ.get("SKILLGATE_TEST_MARKER") == "from-env"


def test_agent_label_humanizes_kind() -> None:
    assert agent_label("cursor-agent") == "Editor agent"
    assert agent_label(None) == "Agent"


def test_missing_key_error_message() -> None:
    err = missing_key_error(for_codex=True)
    assert isinstance(err, MissingLLMKeyError)
    assert "Terminal agent" in err.hint


def test_merge_env_file_updates_keys(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("OPENAI_API_KEY=old\n", encoding="utf-8")
    merge_env_file(path, {"OPENAI_API_KEY": "new", "CODEX_API_KEY": "c"})
    text = path.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=new" in text
    assert "CODEX_API_KEY=c" in text
