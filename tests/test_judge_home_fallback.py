from __future__ import annotations

import json
import os
from pathlib import Path
from unittest import mock

import pytest
from conftest import plain_text
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from skillgate_ai.api import create_app
from skillgate_ai.cli import app
from skillgate_ai.config import get_llm_config
from skillgate_ai.errors import SkillGateError
from skillgate_ai.judge import resolve_judge
from skillgate_ai.judge_providers.decision import NEEDS_DECISION_MODEL, REMOVED_SETUP
from skillgate_ai.judge_settings import (
    _read_judge_file,
    load_judge_settings,
    load_project_judge_settings,
)
from skillgate_ai.keys import (
    bind_key_env,
    key_presence,
    read_vault,
    reset_key_env_bindings,
    resolve_provider_keys,
)

runner = CliRunner()


def _layout(tmp_path: Path) -> tuple[Path, Path]:
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()
    return home, proj


def _use_home_and_project(monkeypatch: pytest.MonkeyPatch, home: Path, proj: Path) -> None:
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("SKILLGATE_ROOT", str(proj))
    monkeypatch.chdir(proj)


def _write_home_judge(home: Path, payload: object, *, mode: int = 0o600) -> Path:
    dest = home / ".skillgate" / "judge"
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2) if not isinstance(payload, str) else payload
    dest.write_text(text, encoding="utf-8")
    os.chmod(dest, mode)
    return dest


def _write_project_judge(proj: Path, payload: object) -> Path:
    dest = proj / ".skillgate" / "judge"
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2) if not isinstance(payload, str) else payload
    dest.write_text(text, encoding="utf-8")
    os.chmod(dest, 0o600)
    return dest


def _write_home_keys(home: Path, lines: str) -> Path:
    dest = home / ".skillgate" / "keys"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(lines if lines.endswith("\n") else lines + "\n", encoding="utf-8")
    os.chmod(dest, 0o600)
    return dest


def _write_project_keys(proj: Path, lines: str) -> Path:
    dest = proj / ".skillgate" / "keys"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(lines if lines.endswith("\n") else lines + "\n", encoding="utf-8")
    os.chmod(dest, 0o600)
    return dest


def test_home_judge_used_when_project_has_no_skillgate_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home, proj = _layout(tmp_path)
    _use_home_and_project(monkeypatch, home, proj)
    _write_home_judge(home, {"provider": "openai"})
    settings = load_judge_settings(proj)
    assert settings.provider == "openai"
    assert settings.chosen
    cfg = get_llm_config(proj)
    assert cfg.judge_provider == "openai"
    assert cfg.judge_chosen is True
    assert load_project_judge_settings(proj).provider == "auto"


def test_home_judge_used_with_root_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home, proj = _layout(tmp_path)
    _use_home_and_project(monkeypatch, home, proj)
    _write_home_judge(home, {"provider": "openai"})
    assert load_judge_settings().provider == "openai"
    assert get_llm_config().judge_provider == "openai"


def test_cli_show_sees_home_judge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home, proj = _layout(tmp_path)
    _use_home_and_project(monkeypatch, home, proj)
    _write_home_judge(home, {"provider": "openai"})
    result = runner.invoke(app, ["judge", "provider", "show"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert "openai" in out
    assert "Pick a decision model" not in out


def test_project_judge_overrides_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home, proj = _layout(tmp_path)
    _use_home_and_project(monkeypatch, home, proj)
    _write_home_judge(home, {"provider": "openai"})
    _write_project_judge(proj, {"provider": "jev", "base_url": "https://jev.example"})
    assert load_judge_settings(proj).provider == "jev"
    assert get_llm_config(proj).judge_provider == "jev"
    shown = runner.invoke(app, ["judge", "provider", "show"])
    assert "jev" in plain_text(shown.stdout)


@pytest.mark.parametrize(
    "project_payload",
    [
        {"provider": "auto"},
        {"provider": ""},
        {"provider": "skip"},
        "not-json",
        [],
    ],
)
def test_project_auto_falls_through_to_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project_payload: object
) -> None:
    home, proj = _layout(tmp_path)
    _use_home_and_project(monkeypatch, home, proj)
    _write_home_judge(home, {"provider": "openai"})
    _write_project_judge(proj, project_payload)
    assert load_judge_settings(proj).provider == "openai"


def test_project_removed_id_does_not_fall_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home, proj = _layout(tmp_path)
    _use_home_and_project(monkeypatch, home, proj)
    _write_home_judge(home, {"provider": "openai"})
    _write_project_judge(proj, {"provider": "aws"})
    assert load_judge_settings(proj).provider == "aws"
    _write_home_keys(home, "OPENAI_API_KEY=sk-home")
    monkeypatch.setenv("SKILLGATE_OPENAI_API_KEY", "sk-home")
    with pytest.raises(SkillGateError) as caught:
        resolve_judge(get_llm_config(proj), harness_name="cursor-agent")
    assert REMOVED_SETUP in caught.value.message


def test_neither_selects_still_needs_decision_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home, proj = _layout(tmp_path)
    _use_home_and_project(monkeypatch, home, proj)
    assert load_judge_settings(proj).provider == "auto"
    with pytest.raises(SkillGateError) as caught:
        resolve_judge(get_llm_config(proj), harness_name="cursor-agent")
    assert caught.value.message == NEEDS_DECISION_MODEL
    assert caught.value.exit_code == 2
    shown = runner.invoke(app, ["judge", "provider", "show"])
    assert shown.exit_code == 2
    assert "Pick a decision model" in plain_text(shown.stdout)


def test_home_auto_not_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home, proj = _layout(tmp_path)
    _use_home_and_project(monkeypatch, home, proj)
    _write_home_judge(home, {"provider": "auto"})
    assert load_judge_settings(proj).provider == "auto"


def test_env_pref_overrides_home_judge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home, proj = _layout(tmp_path)
    _use_home_and_project(monkeypatch, home, proj)
    _write_home_judge(home, {"provider": "jev", "base_url": "https://jev.example"})
    monkeypatch.setenv("SKILLGATE_JUDGE", "openai")
    monkeypatch.setenv("SKILLGATE_OPENAI_API_KEY", "sk-x")
    judge = resolve_judge(get_llm_config(proj), harness_name="cursor-agent")
    assert judge.name == "openai"
    monkeypatch.setenv("SKILLGATE_JUDGE", "skip")
    with pytest.raises(SkillGateError) as caught:
        resolve_judge(get_llm_config(proj), harness_name="cursor-agent")
    assert caught.value.message == NEEDS_DECISION_MODEL


def test_home_legacy_decisions_path_not_rewritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home, proj = _layout(tmp_path)
    _use_home_and_project(monkeypatch, home, proj)
    home_path = _write_home_judge(home, {"provider": "openai", "decisions_path": "x"})
    before = home_path.read_bytes()
    mtime = home_path.stat().st_mtime
    load_judge_settings(proj)
    assert home_path.read_bytes() == before
    assert home_path.stat().st_mtime == mtime

    proj_path = _write_project_judge(proj, {"provider": "openai", "decisions_path": "x"})
    load_judge_settings(proj)
    assert "decisions_path" not in proj_path.read_text(encoding="utf-8")


def test_home_bad_account_id_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home, proj = _layout(tmp_path)
    _use_home_and_project(monkeypatch, home, proj)
    _write_home_judge(home, {"provider": "clef", "account_id": "bad id!"})
    assert load_judge_settings(proj).provider == "auto"


def test_project_root_is_home_reads_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home, _ = _layout(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("SKILLGATE_ROOT", str(home))
    _write_home_judge(home, {"provider": "openai"})
    calls = 0
    real = _read_judge_file

    def counting(path: Path, *, migrate: bool, ignore_account_errors: bool = False):
        nonlocal calls
        calls += 1
        return real(path, migrate=migrate, ignore_account_errors=ignore_account_errors)

    with mock.patch("skillgate_ai.judge_settings._read_judge_file", side_effect=counting):
        assert load_judge_settings(home).provider == "openai"
    assert calls == 1


def test_set_writes_project_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home, proj = _layout(tmp_path)
    _use_home_and_project(monkeypatch, home, proj)
    home_path = _write_home_judge(home, {"provider": "openai"})
    before = home_path.read_bytes()
    result = runner.invoke(app, ["judge", "provider", "set", "jev"])
    assert result.exit_code == 0
    assert (proj / ".skillgate" / "judge").read_text(encoding="utf-8")
    assert "jev" in (proj / ".skillgate" / "judge").read_text(encoding="utf-8")
    assert home_path.read_bytes() == before


def test_project_key_wins_over_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home, proj = _layout(tmp_path)
    _use_home_and_project(monkeypatch, home, proj)
    _write_home_keys(home, "OPENAI_API_KEY=home-k")
    _write_project_keys(proj, "OPENAI_API_KEY=proj-k")
    assert resolve_provider_keys(proj)["OPENAI_API_KEY"] == "proj-k"


def test_home_fills_missing_keys_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home, proj = _layout(tmp_path)
    _use_home_and_project(monkeypatch, home, proj)
    _write_home_keys(home, "OPENAI_API_KEY=home-k\nJEV_API_KEY=home-j\n")
    _write_project_keys(proj, "JEV_API_KEY=proj-j\n")
    resolved = resolve_provider_keys(proj)
    assert resolved["OPENAI_API_KEY"] == "home-k"
    assert resolved["JEV_API_KEY"] == "proj-j"
    assert get_llm_config(proj).openai_api_key == "home-k"


def test_env_overlay_beats_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home, proj = _layout(tmp_path)
    _use_home_and_project(monkeypatch, home, proj)
    _write_home_keys(home, "OPENAI_API_KEY=home-k\n")
    monkeypatch.setenv("SKILLGATE_OPENAI_API_KEY", "env-k")
    assert resolve_provider_keys(proj)["OPENAI_API_KEY"] == "env-k"
    monkeypatch.delenv("SKILLGATE_OPENAI_API_KEY", raising=False)
    reset_key_env_bindings()
    monkeypatch.setenv("OPENAI_API_KEY", "amb-k")
    bind_key_env(["OPENAI_API_KEY"])
    assert resolve_provider_keys(proj)["OPENAI_API_KEY"] == "amb-k"


def test_key_presence_from_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home, proj = _layout(tmp_path)
    _use_home_and_project(monkeypatch, home, proj)
    _write_home_keys(home, "OPENAI_API_KEY=home-k\n")
    meta = key_presence(proj)["OPENAI_API_KEY"]
    assert meta == {"set": True, "from_vault": False, "from_env": False, "from_home": True}
    _write_project_keys(proj, "OPENAI_API_KEY=proj-k\n")
    meta = key_presence(proj)["OPENAI_API_KEY"]
    assert meta["from_vault"] is True
    assert meta["from_home"] is False
    (proj / ".skillgate" / "keys").unlink(missing_ok=True)
    monkeypatch.setenv("SKILLGATE_OPENAI_API_KEY", "env-k")
    meta = key_presence(proj)["OPENAI_API_KEY"]
    assert meta["from_env"] is True
    assert meta["from_home"] is False


def test_keys_list_labels_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home, proj = _layout(tmp_path)
    _use_home_and_project(monkeypatch, home, proj)
    _write_home_keys(home, "OPENAI_API_KEY=home-k\n")
    result = runner.invoke(app, ["keys", "list"])
    out = plain_text(result.stdout)
    assert "OPENAI_API_KEY" in out
    assert "~/.skillgate/keys" in out


def test_keys_set_does_not_copy_home_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home, proj = _layout(tmp_path)
    _use_home_and_project(monkeypatch, home, proj)
    home_keys = _write_home_keys(home, "OPENAI_API_KEY=home-k\n")
    before = home_keys.read_bytes()
    result = runner.invoke(app, ["keys", "set", "JEV_API_KEY", "j"])
    assert result.exit_code == 0
    text = read_vault(proj)
    assert text == {"JEV_API_KEY": "j"}
    assert home_keys.read_bytes() == before


def test_keys_clear_home_only_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home, proj = _layout(tmp_path)
    _use_home_and_project(monkeypatch, home, proj)
    home_keys = _write_home_keys(home, "OPENAI_API_KEY=home-k\n")
    before = home_keys.read_bytes()
    result = runner.invoke(app, ["keys", "clear", "OPENAI_API_KEY"])
    assert result.exit_code == 1
    assert "No OPENAI_API_KEY in Settings." in plain_text(result.stdout)
    assert home_keys.read_bytes() == before


def test_api_get_judge_returns_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home, proj = _layout(tmp_path)
    _use_home_and_project(monkeypatch, home, proj)
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(proj / "cursor-skills"))
    monkeypatch.setenv("SKILLGATE_CODEX_SKILLS", str(proj / "codex-skills"))
    monkeypatch.setenv("SKILLGATE_CLAUDE_SKILLS", str(proj / "claude-skills"))
    home_path = _write_home_judge(home, {"provider": "openai"})
    home_before = home_path.read_bytes()
    client = TestClient(create_app(root=proj), base_url="http://127.0.0.1:8765")
    data = client.get("/api/settings/judge").json()["judge"]
    assert data["provider"] == "openai"
    assert data["chosen"] is True
    client.put("/api/settings/judge", json={"provider": "jev", "base_url": "https://jev.example"})
    assert (proj / ".skillgate" / "judge").is_file()
    assert home_path.read_bytes() == home_before
