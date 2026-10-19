"""Each decision model accepts only the fields it scores with."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import plain_text
from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.errors import SkillGateError
from skillgate_ai.judge_settings import decision_judges, load_judge_settings
from skillgate_ai.keys import set_vault_key

runner = CliRunner()


def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)


def test_catalog_names_the_key_and_only_its_fields() -> None:
    rows = {row["id"]: row for row in decision_judges()}
    assert set(rows) == {"openai", "jev", "clef", "custom"}
    assert rows["openai"]["label"] == "OpenAI"
    assert rows["openai"]["detail"] == "Uses an OpenAI key."
    assert rows["openai"]["fields"] == ["key"]
    assert rows["openai"]["models"] == []
    assert rows["jev"]["label"] == "OpenRouter"
    assert rows["jev"]["detail"] == "Uses an OpenRouter key."
    assert rows["jev"]["fields"] == ["base_url", "model", "key"]
    assert rows["jev"]["advanced"] == ["base_url", "model"]
    assert rows["jev"]["defaults"] == {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "typesafe/jev-1.14",
    }
    assert rows["jev"]["models"] == ["typesafe/jev-1.14"]
    assert rows["clef"]["label"] == "Cloudflare"
    assert rows["clef"]["detail"] == "Uses a Cloudflare token."
    assert rows["clef"]["fields"] == ["account_id", "model", "key"]
    assert rows["clef"]["models"] == ["clef", "clef-flash"]
    assert "base_url" not in rows["clef"]["fields"]
    assert rows["custom"]["fields"] == ["base_url", "model", "key"]
    assert rows["custom"]["model_free"] is True
    blob = " ".join(f"{row['label']} {row['detail']}" for row in rows.values()).lower()
    for banned in ("anthropic", "bedrock", "gpt-", "aws"):
        assert banned not in blob


def test_set_jev_with_a_key_fills_openrouter_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _home(tmp_path, monkeypatch)
    saved = runner.invoke(app, ["judge", "provider", "set", "jev"])
    out = plain_text(saved.stdout + saved.stderr)
    assert saved.exit_code == 0, out
    settings = load_judge_settings(tmp_path)
    assert settings.provider == "jev"
    assert settings.base_url == "https://openrouter.ai/api/v1"
    assert settings.model == "typesafe/jev-1.14"
    assert settings.account_id is None


def test_set_rejects_flags_the_option_ignores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _home(tmp_path, monkeypatch)
    openai = runner.invoke(
        app,
        ["judge", "provider", "set", "openai", "--base-url", "https://openrouter.ai/api/v1"],
    )
    openai_out = plain_text(openai.stdout + openai.stderr)
    assert openai.exit_code == 2, openai_out
    assert "does not use a base URL" in openai_out
    assert "only needs an API key" in openai_out
    assert load_judge_settings(tmp_path).provider == "auto"

    model = runner.invoke(app, ["judge", "provider", "set", "openai", "--model", "clef"])
    assert model.exit_code == 2
    assert "does not use a model" in plain_text(model.stdout + model.stderr)

    account = runner.invoke(
        app, ["judge", "provider", "set", "jev", "--account-id", "abc123"]
    )
    account_out = plain_text(account.stdout + account.stderr)
    assert account.exit_code == 2, account_out
    assert "does not use an account id" in account_out

    url = runner.invoke(
        app,
        ["judge", "provider", "set", "clef", "--base-url", "https://example.com/v1", "--account-id", "abc"],
    )
    assert url.exit_code == 2
    assert "does not use a base URL" in plain_text(url.stdout + url.stderr)


def test_bad_model_names_the_valid_models_and_the_other_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _home(tmp_path, monkeypatch)
    clef = runner.invoke(
        app,
        [
            "judge",
            "provider",
            "set",
            "clef",
            "--account-id",
            "abc123",
            "--model",
            "typesafe/jev-1.14",
        ],
    )
    clef_out = plain_text(clef.stdout + clef.stderr)
    assert clef.exit_code == 2, clef_out
    assert "only scores with its decision models" not in clef_out.lower()
    assert "clef or clef-flash" in clef_out
    assert "OpenRouter" in clef_out
    assert "typesafe/jev-1.14" in clef_out

    jev = runner.invoke(app, ["judge", "provider", "set", "jev", "--model", "clef"])
    jev_out = plain_text(jev.stdout + jev.stderr)
    assert jev.exit_code == 2, jev_out
    assert "typesafe/jev-1.14" in jev_out
    assert "Cloudflare" in jev_out


def test_clef_backend_names_valid_models() -> None:
    from skillgate_ai.judge_providers.clef import ClefBackend

    with pytest.raises(SkillGateError) as caught:
        ClefBackend(api_key="cf-token", account_id="abc123", model="typesafe/jev-1.14")
    message = caught.value.message
    assert "only scores with its decision models" not in message.lower()
    assert "clef or clef-flash" in message
    assert "OpenRouter" in message


def test_judge_test_reports_rejected_key_and_hides_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _home(tmp_path, monkeypatch)
    secret = "sk-test-secret-value"
    set_vault_key(tmp_path, "OPENAI_API_KEY", secret)
    saved = runner.invoke(app, ["judge", "provider", "set", "openai"])
    assert saved.exit_code == 0, saved.stdout

    def post(url, headers=None, json=None, timeout=None):
        del url, headers, json, timeout

        class _Response:
            status_code = 401
            text = secret

            def json(self):
                return {"error": {"message": secret}}

        return _Response()

    monkeypatch.setattr("skillgate_ai.openai_http.httpx.post", post)
    result = runner.invoke(app, ["judge", "test"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 1, out
    assert "This API key was rejected." in out
    assert secret not in out


def test_judge_test_reports_works(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _home(tmp_path, monkeypatch)
    secret = "sk-test-secret-value"
    set_vault_key(tmp_path, "OPENAI_API_KEY", secret)
    assert runner.invoke(app, ["judge", "provider", "set", "openai"]).exit_code == 0

    def post(url, headers=None, json=None, timeout=None):
        del url, headers, json, timeout

        class _Response:
            status_code = 200
            text = "{}"

            def json(self):
                return {"model": "gpt-6-luna", "answers": []}

        return _Response()

    monkeypatch.setattr("skillgate_ai.openai_http.httpx.post", post)
    result = runner.invoke(app, ["judge", "test"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert "This decision model works." in out
    assert secret not in out


def test_judge_test_offers_switch_for_an_openrouter_key_on_openai(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _home(tmp_path, monkeypatch)
    secret = "sk-or-v1-example-key"
    set_vault_key(tmp_path, "OPENAI_API_KEY", secret)
    assert runner.invoke(app, ["judge", "provider", "set", "openai"]).exit_code == 0
    calls: list[str] = []

    def post(url, headers=None, json=None, timeout=None):
        del headers, json, timeout
        calls.append(str(url))
        raise AssertionError("format mismatch must not call the endpoint")

    monkeypatch.setattr("skillgate_ai.openai_http.httpx.post", post)
    result = runner.invoke(app, ["judge", "test"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 1, out
    assert "OpenRouter" in out
    assert "skillgate judge provider set jev" in out
    assert secret not in out
    assert calls == []


def test_judge_test_reports_out_of_credits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _home(tmp_path, monkeypatch)
    secret = "sk-test-secret-value"
    set_vault_key(tmp_path, "OPENAI_API_KEY", secret)
    assert runner.invoke(app, ["judge", "provider", "set", "openai"]).exit_code == 0

    def post(url, headers=None, json=None, timeout=None):
        del url, headers, json, timeout

        class _Response:
            status_code = 429
            text = ""

            def json(self):
                return {"error": {"code": "insufficient_quota", "message": "no credits"}}

        return _Response()

    monkeypatch.setattr("skillgate_ai.openai_http.httpx.post", post)
    result = runner.invoke(app, ["judge", "test"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 1, out
    assert "This account is out of credits." in out
    assert secret not in out
