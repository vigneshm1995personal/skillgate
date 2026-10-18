"""`skillgate checks show` prints the judge prompt the engine sends."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from skillgate_ai.api import create_app
from skillgate_ai.case_pack import save_pack_judge
from skillgate_ai.checks_show import format_decisions_question, prompt_for_id
from skillgate_ai.cli import app
from skillgate_ai.judge_bank import decisions_questions
from skillgate_ai.judge_settings import decision_judges
from skillgate_ai.judge_spec import builtin_spec, parse_extra_question, spec_decisions_questions

ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


def _builtin_prompt(check_id: str) -> str:
    payload = next(row for row in decisions_questions() if row["name"] == check_id)
    return format_decisions_question(payload)


def test_builtin_prompt_is_the_decisions_question() -> None:
    text = prompt_for_id("task_completion")["prompt"]
    assert text == _builtin_prompt("task_completion")
    assert "Got the job done?" in text
    assert "Pick exactly one." in text
    assert "Fully completed:" in text
    assert "Did it finish the task?" not in text
    posted = spec_decisions_questions(builtin_spec())
    task = next(row for row in posted if row["name"] == "task_completion")
    assert text == format_decisions_question(task)


def test_cli_show_prints_the_same_prompt() -> None:
    expected = prompt_for_id("path_efficiency")["prompt"]
    result = runner.invoke(app, ["checks", "show", "path_efficiency"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert result.stdout == expected + "\n"


def test_cli_show_unknown_check_exits_2() -> None:
    result = runner.invoke(app, ["checks", "show", "not-a-check"])
    assert result.exit_code == 2
    assert "not-a-check" in result.stdout + result.stderr


def test_cli_show_custom_check_uses_the_saved_ask(tmp_path: Path) -> None:
    dest = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    save_pack_judge(
        dest,
        {
            "extra_questions": [
                {
                    "id": "fileexists",
                    "type": "predicate",
                    "ask": "Did the file exist?",
                    "on_fail": "block",
                    "pass_if": {"gte": 0.8},
                }
            ]
        },
    )
    shown = prompt_for_id("fileexists", pack=dest)
    result = runner.invoke(app, ["checks", "show", "fileexists", "--pack", str(dest)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert shown["prompt"].startswith("Did the file exist?")
    assert result.stdout == shown["prompt"] + "\n"


def test_api_show_matches_cli(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_MODE", "local")
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(tmp_path / "cursor"))
    monkeypatch.setenv("SKILLGATE_CODEX_SKILLS", str(tmp_path / "codex"))
    monkeypatch.setenv("SKILLGATE_CLAUDE_SKILLS", str(tmp_path / "claude"))
    client = TestClient(create_app(root=tmp_path), base_url="http://127.0.0.1:8765")
    shown = client.get("/api/checks/task_completion")
    assert shown.status_code == 200
    body = shown.json()
    assert body["builtin"] is True
    assert body["prompt"] == _builtin_prompt("task_completion")
    listed = client.get("/api/checks")
    assert listed.status_code == 200
    ids = [row["id"] for row in listed.json()["checks"]]
    assert ids[0] == "task_completion"
    assert "path_efficiency" in ids
    preview = client.post(
        "/api/checks/preview",
        json={
            "question": {
                "id": "tone",
                "type": "predicate",
                "ask": "Was the tone plain?",
                "on_fail": "block",
            }
        },
    )
    assert preview.status_code == 200
    raw = {
        "id": "tone",
        "type": "predicate",
        "ask": "Was the tone plain?",
        "on_fail": "block",
    }
    posted = format_decisions_question(parse_extra_question(raw).to_decisions())
    assert preview.json()["prompt"] == posted
    assert posted.startswith("Was the tone plain?")
    missing = client.get("/api/checks/not-a-check")
    assert missing.status_code == 404


def test_decision_judges_exclude_chat_models() -> None:
    rows = decision_judges()
    ids = {row["id"] for row in rows}
    assert "aws" not in ids
    assert "compatible" not in ids
    assert "auto" not in ids
    assert ids == {"openai", "jev", "clef", "custom"}
    # Key-source names (OpenAI, OpenRouter, Cloudflare) are the catalog copy.
    # Chat vendors stay out of that copy.
    for row in rows:
        text = f"{row['label']} {row['detail']}".lower()
        for banned in ("anthropic", "bedrock", "gpt-", "aws"):
            assert banned not in text


def test_decision_judges_follow_the_engine_allowlist(monkeypatch) -> None:
    import skillgate_ai.judge as judge
    import skillgate_ai.judge_providers.decision as decision
    import skillgate_ai.judge_settings as settings
    from skillgate_ai.judge_providers.decision import DecisionEndpoint

    monkeypatch.setattr(judge, "_builtins_ready", True)
    monkeypatch.setattr(
        decision,
        "_ENDPOINTS",
        {
            "clef": DecisionEndpoint("clef", lambda cfg: cfg),
            "zeta": DecisionEndpoint("zeta", lambda cfg: cfg),
        },
    )
    rows = settings.decision_judges()
    assert [row["id"] for row in rows] == ["clef", "zeta"]
    assert "Clef" not in rows[0]["label"]
    assert rows[1]["label"] == "Decision model"
    assert rows[1]["needs_endpoint"] is True
    assert rows[1]["key_name"] is None
