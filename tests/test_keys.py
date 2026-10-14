from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import plain_text
from skillgate_ai.cli import app
from skillgate_ai.config import get_llm_config
from skillgate_ai.keys import (
    bind_key_env,
    clear_vault_key,
    key_presence,
    list_key_names,
    read_vault,
    reset_key_env_bindings,
    resolve_provider_keys,
    set_vault_key,
)

runner = CliRunner()


def test_ambient_aws_key_is_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAAAMBIENT")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "ambient-secret")
    reset_key_env_bindings()
    assert "AWS_ACCESS_KEY_ID" not in resolve_provider_keys(tmp_path)
    cfg = get_llm_config(tmp_path)
    assert cfg.aws_access_key_id is None
    assert cfg.aws_secret_access_key is None


def test_ambient_openai_key_is_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-ambient-must-be-ignored")
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "gw-ambient-must-be-ignored")
    reset_key_env_bindings()
    assert resolve_provider_keys(tmp_path) == {}
    cfg = get_llm_config(tmp_path)
    assert cfg.has_any_key is False
    assert cfg.openai_api_key is None
    assert cfg.gateway_api_key is None


def test_vault_key_is_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-ambient-must-be-ignored")
    set_vault_key(tmp_path, "OPENAI_API_KEY", "sk-from-vault")
    dest = tmp_path / ".skillgate" / "keys"
    assert dest.is_file()
    assert oct(dest.stat().st_mode & 0o777) == "0o600"
    assert "sk-from-vault" in dest.read_text(encoding="utf-8")
    cfg = get_llm_config(tmp_path)
    assert cfg.openai_api_key == "sk-from-vault"
    assert cfg.has_any_key is False


def test_skillgate_prefix_overrides_ambient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-ambient-must-be-ignored")
    monkeypatch.setenv("SKILLGATE_OPENAI_API_KEY", "sk-from-prefix")
    cfg = get_llm_config(tmp_path)
    assert cfg.openai_api_key == "sk-from-prefix"
    presence = key_presence(tmp_path)["OPENAI_API_KEY"]
    assert presence["set"] is True
    assert presence["from_vault"] is False
    assert presence["from_env"] is True


def test_key_env_binding_reads_ambient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-via-flag")
    reset_key_env_bindings()
    bind_key_env(["OPENAI_API_KEY"])
    cfg = get_llm_config(tmp_path)
    assert cfg.openai_api_key == "sk-via-flag"


def test_project_dotenv_openai_key_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-from-dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    from skillgate_ai.config import load_env

    load_env(tmp_path)
    reset_key_env_bindings()
    cfg = get_llm_config(tmp_path)
    assert cfg.openai_api_key is None
    assert cfg.has_any_key is False


def test_keys_list_never_prints_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    set_vault_key(tmp_path, "OPENAI_API_KEY", "sk-secret-value-do-not-print")
    result = runner.invoke(app, ["keys", "list"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert "OPENAI_API_KEY" in out
    assert "sk-secret-value-do-not-print" not in out
    assert list_key_names(tmp_path) == ["OPENAI_API_KEY"]


def test_keys_set_prompts_hidden_when_value_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("skillgate_ai.cli._stdin_is_tty", lambda: True)
    monkeypatch.setattr("skillgate_ai.cli.getpass.getpass", lambda prompt="": "sk-hidden-prompt")
    result = runner.invoke(app, ["keys", "set", "OPENAI_API_KEY"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert read_vault(tmp_path)["OPENAI_API_KEY"] == "sk-hidden-prompt"
    assert "sk-hidden-prompt" not in out


def test_keys_set_reads_stdin_when_value_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("skillgate_ai.cli._stdin_is_tty", lambda: False)
    result = runner.invoke(app, ["keys", "set", "OPENAI_API_KEY"], input="sk-from-stdin\n")
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert read_vault(tmp_path)["OPENAI_API_KEY"] == "sk-from-stdin"
    assert "sk-from-stdin" not in out


def test_keys_set_and_clear_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    saved = runner.invoke(app, ["keys", "set", "OPENAI_API_KEY", "sk-cli-saved"])
    assert saved.exit_code == 0, saved.stdout
    assert read_vault(tmp_path)["OPENAI_API_KEY"] == "sk-cli-saved"
    cleared = runner.invoke(app, ["keys", "clear", "OPENAI_API_KEY"])
    assert cleared.exit_code == 0, cleared.stdout
    assert "OPENAI_API_KEY" not in read_vault(tmp_path)


def test_clear_vault_key_leaves_others(tmp_path: Path) -> None:
    set_vault_key(tmp_path, "OPENAI_API_KEY", "sk-one")
    set_vault_key(tmp_path, "CURSOR_API_KEY", "cursor-one")
    clear_vault_key(tmp_path, "OPENAI_API_KEY")
    vault = read_vault(tmp_path)
    assert "OPENAI_API_KEY" not in vault
    assert vault["CURSOR_API_KEY"] == "cursor-one"
