"""Fresh-install QA regressions for 0.7.9. One test (or group) per reported bug."""

from __future__ import annotations

import shutil
import stat
from pathlib import Path

import pytest
from conftest import ROOT, plain_text
from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.errors import SuiteError
from skillgate_ai.harness import AUTH_API_KEY

runner = CliRunner()


def _skill(root: Path, name: str = "memo", *, skill_name: str | None = None) -> Path:
    declared = skill_name or name
    dest = root / name
    (dest / "evals").mkdir(parents=True)
    dest.joinpath("SKILL.md").write_text(
        f"---\nname: {declared}\ndescription: A {declared} skill.\n---\n\n# {declared}\n",
        encoding="utf-8",
    )
    dest.joinpath("evals", "cases.yaml").write_text(
        f"schema: 1\nskill: {name}\ncases:\n"
        "  - id: one\n    status: pinned\n    prompt: Write a memo.\n"
        "    should_trigger: false\n",
        encoding="utf-8",
    )
    return dest


def test_single_case_that_never_starts_is_not_saved_as_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = _skill(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = runner.invoke(app, ["check", str(pack), "--case", "one"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 2, out
    listed = runner.invoke(app, ["history", "--pack", str(pack)])
    text = plain_text(listed.stdout + listed.stderr)
    assert listed.exit_code == 0, text
    assert "No runs yet." in text
    assert "Scored by the judge" not in text
    from skillgate_ai.history import load_history

    assert load_history(pack) == []


def test_unscored_history_row_is_not_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = _skill(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    from skillgate_ai.history import append_eval

    append_eval(
        pack,
        run_id="never-started",
        passed=None,
        error={"message": "No agent is available to run checks."},
        tryout=True,
        gate_moved=False,
        config={"judge": {"provider": "openai", "display_name": "the judge"}},
    )
    listed = runner.invoke(app, ["history", "--pack", str(pack)])
    text = plain_text(listed.stdout + listed.stderr)
    assert "not run" in text.lower()
    assert "Not scored" in text
    assert "fail" not in text.lower()
    assert "Scored by the judge" not in text


def test_import_existing_skill_refuses_and_keeps_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    skill = workspace / "skills" / "ledger"
    skill.mkdir(parents=True)
    skill.joinpath("SKILL.md").write_text(
        "---\nname: ledger\ndescription: Ledger skill.\n---\n\n# Ledger\nkeep me\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SKILLGATE_ROOT", str(workspace))
    monkeypatch.chdir(workspace)
    result = runner.invoke(app, ["import", "skills/ledger"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "already in this project" in out.lower()
    text = skill.joinpath("SKILL.md").read_text(encoding="utf-8")
    assert "keep me" in text


def test_decision_keys_are_not_agent_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from skillgate_ai.config import get_llm_config
    from skillgate_ai.harness import codex_auth_kind, harness_auth_status
    from skillgate_ai.keys import set_vault_key

    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    for name in (
        "OPENAI_API_KEY",
        "JEV_API_KEY",
        "CLOUDFLARE_API_TOKEN",
        "CUSTOM_DECISION_API_KEY",
    ):
        set_vault_key(tmp_path, name, f"secret-{name}")
    cfg = get_llm_config(tmp_path)
    assert not cfg.codex_api_key
    assert codex_auth_kind(cfg) != AUTH_API_KEY
    for row in harness_auth_status(cfg):
        assert row["status"] != "API key"
        assert row["auth"] != AUTH_API_KEY
    doctor = runner.invoke(app, ["doctor"])
    login = runner.invoke(app, ["login", "--status"])
    blob = plain_text(doctor.stdout + login.stdout)
    assert "API key" not in blob


def test_random_agent_on_path_is_not_logged_in(tmp_path: Path) -> None:
    from skillgate_ai.harness import (
        _cursor_login_status_authenticated,
        _probe_cursor_login_status,
    )

    bindir = tmp_path / "bin"
    bindir.mkdir()
    agent = bindir / "agent"
    agent.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    agent.chmod(agent.stat().st_mode | stat.S_IEXEC)
    assert _cursor_login_status_authenticated(0, "", "") is False
    assert _cursor_login_status_authenticated(0, "usage: agent\n", "") is False
    assert _probe_cursor_login_status(str(agent)) is False


def test_judge_provider_show_and_set_name_option_model_and_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    saved = runner.invoke(app, ["judge", "provider", "set", "openai"])
    out = plain_text(saved.stdout + saved.stderr)
    assert saved.exit_code == 0, out
    for needle in ("openai", "gpt-6-luna", "https://api.openai.com/v1"):
        assert needle in out
    shown = runner.invoke(app, ["judge", "provider", "show"])
    show = plain_text(shown.stdout + shown.stderr)
    assert shown.exit_code == 0, show
    for needle in ("openai", "gpt-6-luna", "https://api.openai.com/v1"):
        assert needle in show
    jev = runner.invoke(app, ["judge", "provider", "set", "jev"])
    jev_out = plain_text(jev.stdout + jev.stderr)
    assert jev.exit_code == 0, jev_out
    assert "jev" in jev_out
    assert "typesafe/jev-1.14" in jev_out
    assert "https://openrouter.ai/api/v1" in jev_out
    clef = runner.invoke(
        app,
        ["judge", "provider", "set", "clef", "--account-id", "abc123", "--model", "clef"],
    )
    clef_out = plain_text(clef.stdout + clef.stderr)
    assert clef.exit_code == 0, clef_out
    assert "clef" in clef_out
    assert "abc123" in clef_out
    assert "api.cloudflare.com" in clef_out


def test_scoring_errors_hide_http_codes_and_name_the_mismatch() -> None:
    from skillgate_ai.judge_providers.clef import ClefBackend
    from skillgate_ai.judge_providers.jev import _public_failure
    from skillgate_ai.judge_setup import WRONG_ENDPOINT, classify_test_result
    from skillgate_ai.openai_http import user_message_for_status

    for status in (401, 405, 404, 500):
        message = user_message_for_status(status)
        assert "HTTP" not in message
        assert str(status) not in message
    assert user_message_for_status(404) == WRONG_ENDPOINT
    assert user_message_for_status(405) == WRONG_ENDPOINT
    assert "HTTP" not in _public_failure({"http_status": 405, "reason": ""})
    assert _public_failure({"http_status": 405, "reason": ""}) == WRONG_ENDPOINT

    def post(url, headers=None, json=None, timeout=None):
        del url, headers, json, timeout

        class Response:
            status_code = 404

            def json(self):
                return {"error": {"message": "account not found"}}

        return Response()

    clef = ClefBackend(api_key="token", account_id="missingacct", post=post)
    scored = clef.evaluate(state={}, images=[], timeout_sec=5)
    reason = str(scored.get("reason") or "")
    assert "wasn't found" in reason or "was not found" in reason
    assert "account" in reason.lower()
    assert "different endpoint" not in reason.lower()
    assert "HTTP" not in reason
    assert classify_test_result(False, reason) == reason


def test_bad_account_id_is_not_a_missing_account_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    bad = runner.invoke(
        app,
        ["judge", "provider", "set", "clef", "--account-id", "ab-cd", "--model", "clef"],
    )
    out = plain_text(bad.stdout + bad.stderr)
    assert bad.exit_code == 2, out
    assert "needs an account id" not in out.lower()
    assert "letter" in out.lower() or "digit" in out.lower()
    missing = runner.invoke(app, ["judge", "provider", "set", "clef", "--model", "clef"])
    missing_out = plain_text(missing.stdout + missing.stderr)
    assert "needs an account id" in missing_out.lower()


def test_chat_model_on_custom_endpoint_is_not_a_decision_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = runner.invoke(
        app,
        [
            "judge",
            "provider",
            "set",
            "custom",
            "--base-url",
            "https://example.com/v1",
            "--model",
            "gpt-4o",
        ],
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 2, out
    assert "isn't a decision model" in out


def test_clef_model_flag_is_stored_lowercase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from skillgate_ai.judge_settings import load_judge_settings

    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = runner.invoke(
        app,
        ["judge", "provider", "set", "clef", "--account-id", "abc123", "--model", "CLEF"],
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert load_judge_settings(tmp_path).model == "clef"


def test_keys_set_help_and_unknown_name_list_decision_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    help_result = runner.invoke(app, ["keys", "set", "--help"])
    help_text = plain_text(help_result.stdout + help_result.stderr)
    unknown = runner.invoke(app, ["keys", "set", "NOPE", "secret"])
    unknown_text = plain_text(unknown.stdout + unknown.stderr)
    for name in ("JEV_API_KEY", "CLOUDFLARE_API_TOKEN", "CUSTOM_DECISION_API_KEY"):
        assert name in help_text
        assert name in unknown_text


@pytest.mark.parametrize(
    ("name", "case_id"),
    [
        ("json-response", "flatten-orders"),
        ("json-response-sabotaged", "edge-empty"),
        ("readme-writer", "write-readme"),
        ("log-summarizer", "summarize-errors"),
        ("sql-writer", "open-orders"),
        ("receipt-extractor", "extract-total"),
    ],
)
def test_case_remove_refuses_bundled_example_seeds(
    name: str, case_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / name
    shutil.copytree(ROOT / "skills" / name, dest)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = runner.invoke(app, ["case", "remove", str(dest), "--id", case_id])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "original checks stay" in out.lower()
    assert case_id in dest.joinpath("evals", "cases.yaml").read_text(encoding="utf-8")


def test_add_question_without_pack_does_not_write_skills_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = tmp_path / "skills" / "pdf"
    (pdf / "evals").mkdir(parents=True)
    pdf.joinpath("SKILL.md").write_text(
        "---\nname: pdf\ndescription: Pdf skill.\n---\n\n# pdf\n",
        encoding="utf-8",
    )
    cases = (
        "schema: 1\nskill: pdf\ncases:\n"
        "  - id: one\n    prompt: Hi.\n    should_trigger: false\n"
    )
    cases_path = pdf / "evals" / "cases.yaml"
    cases_path.write_text(cases, encoding="utf-8")
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = runner.invoke(app, ["judge", "add-question", "--ask", "Did it cite a file?"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "skill pack" in out.lower()
    assert cases_path.read_text(encoding="utf-8") == cases


def test_missing_golden_errors_on_load(tmp_path: Path) -> None:
    pack = _skill(tmp_path, "memo")
    pack.joinpath("evals", "cases.yaml").write_text(
        "schema: 1\nskill: memo\ncases:\n"
        "  - id: one\n    status: pinned\n    prompt: Write a memo.\n"
        "    should_trigger: true\n"
        "    golden:\n"
        "      output_path: output/memo.txt\n"
        "      path: evals/goldens/one.txt\n"
        "      kind: text\n",
        encoding="utf-8",
    )
    from skillgate_ai.case_pack import load_case_pack

    with pytest.raises(SuiteError) as caught:
        load_case_pack(pack)
    assert "expected output" in caught.value.message.lower()


def test_ingest_rejects_cases_yaml_skill_mismatch(tmp_path: Path) -> None:
    pack = _skill(tmp_path, "ledger")
    text = pack.joinpath("evals", "cases.yaml").read_text(encoding="utf-8")
    pack.joinpath("evals", "cases.yaml").write_text(
        text.replace("skill: ledger", "skill: other"),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["ingest", str(pack)])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "other" in out
    assert "ledger" in out


def test_check_reports_skill_md_name_mismatch_before_no_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = _skill(tmp_path, "ledger", skill_name="other")
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = runner.invoke(app, ["check", str(pack)])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "must match" in out
    assert "No agent is available" not in out


def test_missing_pack_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = runner.invoke(app, ["check", str(tmp_path / "pack")])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 2, out


def test_example_help_states_skills_name_dest() -> None:
    result = runner.invoke(app, ["example", "--help"])
    text = plain_text(result.stdout + result.stderr)
    assert "skills/NAME" in text


def test_duplicate_case_ids_are_plain_language(tmp_path: Path) -> None:
    pack = _skill(tmp_path)
    pack.joinpath("evals", "cases.yaml").write_text(
        "schema: 1\nskill: memo\ncases:\n"
        "  - id: one\n    prompt: First.\n    should_trigger: false\n"
        "  - id: one\n    prompt: Second.\n    should_trigger: false\n",
        encoding="utf-8",
    )
    from skillgate_ai.case_pack import load_case_pack

    with pytest.raises(SuiteError) as caught:
        load_case_pack(pack)
    message = caught.value.message
    assert "same id" in message.lower()
    assert "[" not in message
    assert "one" in message


def test_removed_llm_harness_exit_matches_help(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = _skill(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    help_result = runner.invoke(app, ["check", "--help"])
    help_text = plain_text(help_result.stdout + help_result.stderr)
    assert "2 if it cannot run" in help_text
    for kind in ("llm", "byollm"):
        result = runner.invoke(app, ["check", str(pack), "--harness", kind])
        out = plain_text(result.stdout + result.stderr)
        assert result.exit_code == 2, out
        assert "removed" in out.lower()
