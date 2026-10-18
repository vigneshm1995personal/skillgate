"""Regressions from live skillgate 0.7.1 runs (Claude Code + OpenRouter)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from conftest import plain_text
from test_judge import _cfg
from typer.testing import CliRunner

from skillgate_ai import __version__
from skillgate_ai.cli import app
from skillgate_ai.engine import SuiteReport, TaskReport
from skillgate_ai.harness import (
    AUTH_CLI_LOGIN,
    ClaudeCodeHarness,
    CursorAgentHarness,
    _cursor_login_status_authenticated,
    _jsonl_transcript,
)
from skillgate_ai.history import append_eval, load_history
from skillgate_ai.judge_bank import OUTCOME_SCORING_NOTES, decisions_questions
from skillgate_ai.judge_openai import DecisionsBackend, _state_text
from skillgate_ai.judge_spec import JudgeQuestion, extra_question_passed
from skillgate_ai.report import report_to_dict
from skillgate_ai.suite import FileExpect, ScorerSpec, TaskSpec
from skillgate_ai.usage import render_stream_line
from skillgate_ai.workspace_outputs import collect_workspace_outputs, snapshot_workspace

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "judge_072"

_RATE_LIMIT = json.dumps(
    {
        "type": "rate_limit_event",
        "rate_limit_info": {"status": "allowed", "utilization": 0.38},
    }
)
_SYSTEM_INIT = json.dumps(
    {
        "type": "system",
        "subtype": "init",
        "cwd": "/tmp/skillgate-ws",
        "model": "claude-sonnet-5-5",
    }
)


def _tool_pair() -> str:
    return "\n".join(
        [
            _SYSTEM_INIT,
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_bash",
                                "name": "Bash",
                                "input": {"command": "pytest -q output/test_slugify.py"},
                            }
                        ]
                    },
                }
            ),
            _RATE_LIMIT,
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_bash",
                                "content": "1 passed in 0.12s",
                            }
                        ]
                    },
                }
            ),
            _RATE_LIMIT,
        ]
    )


def test_render_drops_claude_rate_limit_and_system_events() -> None:
    assert render_stream_line(_RATE_LIMIT) is None
    assert render_stream_line(_SYSTEM_INIT) is None
    rendered = _jsonl_transcript(_tool_pair(), "")
    assert "rate_limit_event" not in rendered
    assert "utilization" not in rendered
    assert "subtype" not in rendered
    assert "pytest -q output/test_slugify.py" in rendered
    assert "1 passed in 0.12s" in rendered


def test_judge_transcript_and_history_omit_rate_limit_event(tmp_path: Path) -> None:
    from skillgate_ai.judge_context import build_agent_trajectory

    rendered = _jsonl_transcript(_tool_pair(), "")
    trajectory = build_agent_trajectory(
        spans=None,
        transcript=rendered,
        path={"had_path": True, "steps": 1},
        scores=[],
        command_log=_tool_pair(),
    )
    state = json.loads(
        _state_text(
            {
                "check_prompt": "Add a test",
                "transcript_tail": rendered,
                "agent_trajectory": trajectory,
            }
        )
    )
    blob = json.dumps(state)
    assert "rate_limit_event" not in blob
    assert "utilization" not in blob
    assert "pytest -q output/test_slugify.py" in blob
    pack = tmp_path / "memo"
    pack.mkdir()
    append_eval(
        pack,
        run_id="live-1",
        passed=False,
        report={"tasks": [{"id": "t", "transcript": rendered}]},
    )
    saved = json.dumps(load_history(pack))
    assert "rate_limit_event" not in saved
    assert "utilization" not in saved
    assert "pytest -q output/test_slugify.py" in saved


def test_check_answers_map_predicate_probability() -> None:
    payload = report_to_dict(
        SuiteReport(
            suite="s",
            title="t",
            skill="web",
            harness="claude",
            sandbox="local",
            passed=False,
            tasks=[
                TaskReport(
                    task_id="fetch",
                    prompt="avoid useEffect fetch",
                    expect_skill="web",
                    passed=False,
                    scores=[],
                    selected_skill="web",
                    failures=["avoids useEffect fetch No"],
                    judge={
                        "status": "completed",
                        "answers": {
                            "avoids_useeffect_fetch": {"probability": 1.0},
                            "commit_len": {"probability": 0.1},
                        },
                        "cells": {
                            "task_completion": {
                                "label": "Got the job done?",
                                "choice": "Fully completed",
                            },
                            "avoids_useeffect_fetch": {
                                "label": "avoids useEffect fetch",
                                "choice": None,
                                "reason": None,
                                "probability": 1.0,
                            },
                            "commit_len": {
                                "label": "commit subject is at most 100 characters",
                                "choice": None,
                                "reason": None,
                                "probability": 0.1,
                            },
                        },
                    },
                )
            ],
        )
    )
    answers = {item["label"]: item["answer"] for item in payload["tasks"][0]["check_answers"]}
    assert answers["avoids useEffect fetch"] == "Yes"
    assert answers["commit subject is at most 100 characters"] == "No"
    assert answers["Got the job done?"] == "Fully completed"
    assert "Not available" not in answers.values()


def test_not_applicable_extra_answer_passes_and_zero_still_fails() -> None:
    question = JudgeQuestion(
        id="avoids_useeffect_fetch",
        type="predicate",
        ask="avoids useEffect fetch",
        pass_if={"gte": 0.8},
    )
    ok, detail = extra_question_passed(question, {"choice": "not applicable"})
    assert ok is True
    assert detail is None
    failed, reason = extra_question_passed(question, {"probability": 0.0})
    assert failed is False
    assert reason


def test_golden_reference_is_an_example_unless_marked_required(tmp_path: Path) -> None:
    from skillgate_ai.case_pack import CaseGolden, golden_state

    skill = tmp_path / "sheet"
    (skill / "evals" / "goldens").mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: sheet\n---\n", encoding="utf-8")
    golden = CaseGolden(
        output_path="output/report.csv",
        path="evals/goldens/export.txt",
        kind="text",
    )
    (skill / golden.path).write_text("name,total\nAda,1\n", encoding="utf-8")
    state = golden_state(golden, skill, contains=[])
    assert state is not None
    note = str(state.get("note") or "").lower()
    assert "example" in note
    assert "not a full specification" in note or "not a full spec" in note
    assert "case prompt" in note
    blob = json.dumps(
        json.loads(_state_text({"check_prompt": "Export the sheet", "golden": state}))
    ).lower()
    assert "example" in blob
    marked = golden_state(golden, skill, contains=["Ada"])
    assert marked is not None
    marked_note = json.dumps(marked).lower()
    assert "substring" in marked_note or "must include" in marked_note
    assert marked["contains"] == ["Ada"]
    notes = OUTCOME_SCORING_NOTES.lower()
    assert "example" in notes
    assert "required" in notes


def test_judge_questions_require_concrete_evidence() -> None:
    questions = decisions_questions()
    instructions = " ".join(str(item.get("instructions") or "") for item in questions).lower()
    notes = OUTCOME_SCORING_NOTES.lower()
    blob = instructions + "\n" + notes
    assert "not applicable" in blob
    assert "file" in blob and "line" in blob
    assert "command" in blob
    assert "no violation" in blob
    captured: dict[str, object] = {}

    def post(url, headers=None, json=None, timeout=None):
        del headers, timeout
        captured["url"] = url
        captured["payload"] = json
        from test_judge_providers import FakeResponse

        return FakeResponse(200, {"answers": [], "model": "gpt-6-luna"})

    DecisionsBackend(api_key="sk-test", post=post).evaluate(
        state={"check_prompt": "grade"},
        images=[],
        timeout_sec=1,
    )
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert str(captured["url"]).endswith("/decisions")
    assert "/responses" not in str(captured["url"])
    assert isinstance(payload["questions"], list)
    assert payload["questions"]


def test_regression_fixture_no_useeffect_is_not_a_violation() -> None:
    fixture = json.loads((FIXTURES / "no_useeffect_fetch.json").read_text(encoding="utf-8"))
    assert "useeffect" not in fixture["source"].lower()
    question = JudgeQuestion(
        id=fixture["id"],
        type="predicate",
        ask=fixture["question"],
        pass_if={"gte": 0.8},
    )
    instructions = question.to_decisions()["instructions"].lower()
    assert "not applicable" in instructions
    assert "file" in instructions and "line" in instructions
    assert "command" in instructions
    assert "no violation" in instructions


def test_regression_fixture_same_commit_line_shares_evidence_rule() -> None:
    fixture = json.loads((FIXTURES / "commit_subject_length.json").read_text(encoding="utf-8"))
    assert len(fixture["line"]) > 100
    instructions = []
    for case in fixture["cases"]:
        question = JudgeQuestion(
            id=case["id"],
            type="predicate",
            ask=case["question"],
            pass_if={"gte": 0.8},
        )
        instructions.append(question.to_decisions()["instructions"])
    assert instructions[0] == instructions[1]
    lowered = instructions[0].lower()
    assert "same evidence" in lowered
    assert "not applicable" in lowered
    assert "file" in lowered and "line" in lowered


def test_collect_changed_workspace_files_skips_junk_and_saves_git(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    (ws / "output").mkdir(parents=True)
    (ws / "output" / "named.txt").write_text("named", encoding="utf-8")
    (ws / "node_modules" / "pkg").mkdir(parents=True)
    (ws / "node_modules" / "pkg" / "index.js").write_text("skip me", encoding="utf-8")
    (ws / "src").mkdir()
    (ws / "src" / "App.tsx").write_text("export const x = 1\n", encoding="utf-8")
    (ws / "big.txt").write_bytes(b"a" * 300_000)
    home = tmp_path / "home"
    home.mkdir()
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["GIT_CONFIG_GLOBAL"] = str(home / "no-gitconfig")
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    subprocess.run(["git", "init"], cwd=ws, env=env, check=True, capture_output=True)
    (ws / "src" / "App.tsx").write_text("export const x = 2\n", encoding="utf-8")
    task = TaskSpec(id="t1", prompt="edit the app", expect_skill="web", scorers=[])
    rows = collect_workspace_outputs(task, ws)
    paths = {row["path"] for row in rows}
    assert "output/named.txt" in paths
    assert "src/App.tsx" in paths
    assert not any("node_modules" in path for path in paths)
    assert not any(path.startswith(".git/") or "/.git/" in path for path in paths)
    assert any(path.startswith("git/") for path in paths)
    app = next(row for row in rows if row["path"] == "src/App.tsx")
    assert "export const x = 2" in str(app.get("body") or "")
    before = snapshot_workspace(ws)
    (ws / "src" / "New.tsx").write_text("export const created = true\n", encoding="utf-8")
    changed = collect_workspace_outputs(task, ws, baseline=before)
    changed_paths = {row["path"] for row in changed}
    assert "src/New.tsx" in changed_paths
    assert "src/App.tsx" not in changed_paths
    assert "output/named.txt" in changed_paths
    big = next(row for row in rows if row["path"] == "big.txt")
    body = big.get("body")
    assert body is None or len(str(body)) <= 16_000
    assert big.get("size") == 300_000


def test_workspace_capture_skips_envs_and_caps_judge_files(tmp_path: Path) -> None:
    from skillgate_ai.workspace_outputs import MAX_SCORED_BODY_BYTES, MAX_SCORED_FILES

    ws = tmp_path / "ws"
    (ws / "reports").mkdir(parents=True)
    (ws / "reports" / "final.txt").write_text("wanted", encoding="utf-8")
    venv = ws / ".venv" / "lib" / "site-packages" / "pkg"
    venv.mkdir(parents=True)
    (venv / "mod.py").write_text("venv", encoding="utf-8")
    (ws / ".venv" / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    odd = ws / "workenv" / "lib" / "python3.12" / "site-packages"
    odd.mkdir(parents=True)
    (ws / "workenv" / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    for index in range(30):
        (odd / f"m{index}.py").write_text("x", encoding="utf-8")
    vendor = ws / "vendor" / "site-packages"
    vendor.mkdir(parents=True)
    (vendor / "a.py").write_text("nope", encoding="utf-8")
    (ws / "__pycache__").mkdir()
    (ws / "__pycache__" / "a.pyc").write_bytes(b"pyc")
    (ws / ".cache" / "pip").mkdir(parents=True)
    (ws / ".cache" / "pip" / "wheel").write_text("cache", encoding="utf-8")
    (ws / "node_modules" / "pkg").mkdir(parents=True)
    (ws / "node_modules" / "pkg" / "index.js").write_text("js", encoding="utf-8")
    (ws / "dist").mkdir()
    (ws / "dist" / "bundle.js").write_text("js", encoding="utf-8")
    (ws / "build" / "out").mkdir(parents=True)
    (ws / "build" / "out" / "a.o").write_bytes(b"o")
    scratch = ws / "scratch"
    scratch.mkdir()
    for index in range(MAX_SCORED_FILES + 15):
        (scratch / f"n{index:02d}.txt").write_text("n" * 20_000, encoding="utf-8")
    task = TaskSpec(
        id="t",
        prompt="write the report",
        expect_skill="s",
        scorers=[
            ScorerSpec(
                type="task_completion",
                files=[FileExpect(path="reports/final.txt")],
            )
        ],
    )
    rows = collect_workspace_outputs(task, ws)
    paths = [str(row["path"]) for row in rows]
    blob = " ".join(paths)
    for banned in (
        ".venv",
        "workenv",
        "site-packages",
        "__pycache__",
        ".cache",
        "node_modules",
        "dist/",
        "build/",
    ):
        assert banned not in blob
    final = next(row for row in rows if row["path"] == "reports/final.txt")
    assert "wanted" in str(final.get("body") or "")
    scratch_rows = [row for row in rows if str(row["path"]).startswith("scratch/")]
    assert len(scratch_rows) < MAX_SCORED_FILES + 15
    assert len([path for path in paths if not path.startswith("git/")]) <= MAX_SCORED_FILES
    scratch_bytes = sum(len(str(row.get("body") or "")) for row in scratch_rows)
    assert scratch_bytes <= MAX_SCORED_BODY_BYTES
    assert MAX_SCORED_FILES <= 40
    assert MAX_SCORED_BODY_BYTES <= 256_000


def test_claude_harness_is_noninteractive_inside_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    class _Sandbox:
        def __init__(self, workspace: Path) -> None:
            self.workspace = workspace

        def run(self, command, *, env=None, timeout=0, cwd=None):
            seen["command"] = list(command)
            seen["cwd"] = cwd
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("skillgate_ai.harness._claude_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: "/bin/claude")
    monkeypatch.setattr("skillgate_ai.harness._read_selection", lambda _w: None)
    monkeypatch.setattr("skillgate_ai.harness._parse_selected", lambda *a: None)
    monkeypatch.setattr("skillgate_ai.harness._parse_read_paths", lambda _t: [])
    monkeypatch.setattr("skillgate_ai.harness._write_selection", lambda *a: None)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    ClaudeCodeHarness(_cfg(anthropic_api_key="ant-test")).run(
        _Sandbox(workspace),  # type: ignore[arg-type]
        "Write the tests and do not stop to ask.",
        [],
        timeout_sec=5,
    )
    command = seen["command"]
    assert isinstance(command, list)
    assert "--dangerously-skip-permissions" not in command
    assert "bypassPermissions" not in command
    assert command[command.index("--permission-mode") + 1] == "acceptEdits"
    assert command[command.index("--permission-prompts") + 1] == "none"
    tools_flag = "--allowedTools" if "--allowedTools" in command else "--allowed-tools"
    assert tools_flag in command
    assert "Bash" in command[command.index(tools_flag) + 1]
    prompt = command[-1]
    assert "Do not ask for confirmation" in prompt
    assert "Stay inside this workspace" in prompt
    assert seen["cwd"] in {None, workspace}


def test_judge_provider_test_accepts_key_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env-not-a-real-key")
    monkeypatch.delenv("SKILLGATE_OPENAI_API_KEY", raising=False)
    seen: dict[str, str] = {}

    def fake_ping(cfg):
        seen["key"] = cfg.openai_api_key or ""
        return {"ok": True, "message": "Connected via the Decisions API.", "scoring_endpoint": "decisions"}

    monkeypatch.setattr("skillgate_ai.judge.ping_judge", fake_ping)
    result = runner.invoke(app, ["judge", "provider", "test", "--key-env", "OPENAI_API_KEY"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert seen["key"] == "sk-from-env-not-a-real-key"
    assert "Decisions API" in out


def test_judge_provider_set_stores_key_env_name_not_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    secret = "sk-openrouter-secret-value"
    monkeypatch.setenv("OPENROUTER_API_KEY", secret)
    result = runner.invoke(
        app,
        [
            "judge",
            "provider",
            "set",
            "jev",
            "--base-url",
            "https://openrouter.ai/api/v1",
            "--model",
            "typesafe/jev-1.14",
            "--key-env",
            "OPENROUTER_API_KEY",
        ],
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert "No such option" not in out
    assert secret not in out
    raw = (tmp_path / ".skillgate" / "judge").read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY" in raw
    assert secret not in raw

    from skillgate_ai.config import get_llm_config
    from skillgate_ai.judge import resolve_judge

    from skillgate_ai.errors import MissingLLMKeyError

    cfg = get_llm_config(tmp_path)
    with pytest.raises(MissingLLMKeyError) as caught:
        resolve_judge(cfg, harness_name="cursor-agent")
    assert "API key" in caught.value.message
    assert "Jev" not in caught.value.message
    assert secret not in caught.value.message


def test_scoring_endpoint_recorded_for_decisions() -> None:
    from test_judge_providers import FakeResponse

    from skillgate_ai.judge_openai import OutcomeJudge
    from skillgate_ai.judge_spec import resolve_judge_spec

    def post(url, headers=None, json=None, timeout=None):
        del headers, json, timeout
        assert str(url).endswith("/decisions")
        answers = [
            {"name": "task_completion", "choice": "Fully completed"},
            {"name": "correctness", "choice": "Correct"},
            {"name": "instruction_adherence", "choice": "Fully followed"},
            {"name": "evidence_action_validity", "choice": "Fully supported"},
            {"name": "result_quality", "choice": "Clear and complete"},
        ]
        return FakeResponse(200, {"answers": answers, "model": "gpt-6-luna"})

    from skillgate_ai.judge_openai import ping_openai_backend

    backend = DecisionsBackend(api_key="sk-test", post=post)
    ping = ping_openai_backend(backend, display_name="the judge")
    assert ping["ok"] is True
    assert "Responses" not in str(ping.get("message") or "")
    judged = OutcomeJudge(
        backend,
        display_name="the judge",
        provider="openai",
        chosen=True,
        supports_why=False,
        supports_confidence=True,
    ).judge("goal", [], "tail", spec=resolve_judge_spec(), path={"had_path": False, "steps": 0})
    assert judged["scoring_endpoint"] == "decisions"
    payload = report_to_dict(
        SuiteReport(
            suite="s",
            title="t",
            skill="web",
            harness="claude",
            sandbox="local",
            passed=True,
            tasks=[
                TaskReport(
                    task_id="t",
                    prompt="p",
                    expect_skill="web",
                    passed=True,
                    scores=[],
                    selected_skill="web",
                    judge=judged,
                )
            ],
        )
    )
    assert payload["tasks"][0]["judge"]["scoring_endpoint"] == "decisions"
    assert payload.get("scoring_endpoint") == "decisions"


def test_cursor_unable_to_fetch_user_details_is_signed_out() -> None:
    assert not _cursor_login_status_authenticated(
        0, "Unable to fetch user details\n", ""
    )
    assert not _cursor_login_status_authenticated(
        0, "", "Error: unable to fetch user details"
    )
    assert _cursor_login_status_authenticated(0, "Authenticated\nAccount: you\n", "")


def test_auth_error_fails_fast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from skillgate_ai.errors import HarnessError

    class _Sandbox:
        def __init__(self, workspace: Path) -> None:
            self.workspace = workspace

        def run(self, command, *, env=None, timeout=0, cwd=None):
            del command, env, timeout, cwd
            stdout = json.dumps(
                {"type": "error", "message": "unable to fetch user details"}
            )
            return subprocess.CompletedProcess(["agent"], 1, stdout=stdout, stderr="")

    monkeypatch.setattr("skillgate_ai.harness._cursor_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_agent_bin", lambda _p: "/bin/agent")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    with pytest.raises(HarnessError) as caught:
        CursorAgentHarness(_cfg(cursor_api_key="cur-test")).run(
            _Sandbox(workspace),  # type: ignore[arg-type]
            "do the task",
            [],
            timeout_sec=30,
        )
    assert caught.value.exit_code == 2
    assert "signed in" in caught.value.message.lower()

    class _OkSandbox:
        def __init__(self, workspace: Path) -> None:
            self.workspace = workspace

        def run(self, command, *, env=None, timeout=0, cwd=None):
            del command, env, timeout, cwd
            stdout = json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [{"type": "text", "text": "The page says not logged in"}]
                    },
                }
            )
            return subprocess.CompletedProcess(["agent"], 0, stdout=stdout, stderr="")

    result = CursorAgentHarness(_cfg(cursor_api_key="cur-test")).run(
        _OkSandbox(workspace),  # type: ignore[arg-type]
        "do the task",
        [],
        timeout_sec=30,
    )
    assert "not logged in" in result.transcript


def test_red_check_exits_1_when_judge_errors(
    project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    from skillgate_ai.demo_files import ensure_demo_pdfs
    from skillgate_ai.gate import run_check

    dest = tmp_path / "pdf"
    shutil.copytree(project_root / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")

    def fake_run_eval(*_args, **_kwargs) -> SuiteReport:
        task = TaskReport(
            task_id="should-trigger-1",
            prompt="demo",
            expect_skill="pdf",
            passed=False,
            scores=[],
            selected_skill="pdf",
            failures=["Got it right? Incorrect"],
            judge={"status": "error", "provider": "openai", "reasons": ["HTTP 402"]},
        )
        return SuiteReport(
            suite="pdf-pack",
            title="Dataset",
            skill="pdf",
            harness="cursor-agent",
            sandbox="local",
            passed=False,
            tasks=[task],
            skill_path=str(dest),
            config={"judge": {"provider": "openai", "display_name": "the judge"}},
        )

    class StubHarness:
        name = "cursor-agent"

    monkeypatch.setattr("skillgate_ai.gate.live_harness_or_error", lambda *_a, **_k: StubHarness())
    monkeypatch.setattr("skillgate_ai.gate.run_eval", fake_run_eval)
    monkeypatch.setattr("skillgate_ai.gate.resolve_judge", lambda *_a, **_k: object())
    from conftest import enable_cursor_agent

    enable_cursor_agent(monkeypatch, tmp_path)
    result = run_check(dest, source="test", root=tmp_path)
    assert result.report is not None
    assert result.report.passed is False
    assert result.exit_code == 1


def test_login_cursor_says_already_signed_in(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    def fake_login(agent: str, cfg) -> dict:
        del cfg
        called.append(agent)
        return {"ok": True, "agent": agent, "installed": True, "message": "started"}

    monkeypatch.setattr("skillgate_ai.harness.cursor_auth_kind", lambda _c: AUTH_CLI_LOGIN)
    monkeypatch.setattr("skillgate_ai.harness.run_official_login", fake_login)
    result = runner.invoke(app, ["login", "cursor"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert "already signed in" in out.lower()
    assert called == []


def test_version_is_073() -> None:
    assert __version__ == "0.7.3"
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## 0.7.3" in changelog
    assert "## 0.7.2" in changelog
