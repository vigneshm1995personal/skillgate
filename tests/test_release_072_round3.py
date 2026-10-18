"""Round-3 regressions for compare, trigger mode, prompts, and Codex isolation."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from conftest import plain_text
from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.compare import CompareResult, run_versions_compare
from skillgate_ai.engine import SuiteReport, TaskReport, _run_task
from skillgate_ai.harness import HarnessResult, _cursor_prompt
from skillgate_ai.history import append_eval, load_history
from skillgate_ai.ingest import Skill, ingest_skill
from skillgate_ai.sandbox import LocalSandbox
from skillgate_ai.scorers import TriggerEvidence
from skillgate_ai.suite import ScorerSpec, SuiteSpec, TaskSpec

runner = CliRunner()


def _git_env(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["GIT_CONFIG_GLOBAL"] = str(home / "no-gitconfig")
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_AUTHOR_NAME"] = "t"
    env["GIT_AUTHOR_EMAIL"] = "t@example.com"
    env["GIT_COMMITTER_NAME"] = "t"
    env["GIT_COMMITTER_EMAIL"] = "t@example.com"
    return env


def _git_pack(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    pack = repo / "reviewer"
    pack.mkdir(parents=True)
    (pack / "SKILL.md").write_text(
        "---\nname: reviewer\ndescription: Review diffs.\n---\n# reviewer\n",
        encoding="utf-8",
    )
    (pack / "evals").mkdir()
    env = _git_env(home)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(
        ["git", "commit", "-m", "v1"],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )
    return pack


def _red_report() -> SuiteReport:
    task = TaskReport(
        task_id="review-notes",
        prompt="Write the review to reviews/notes.md",
        expect_skill="reviewer",
        passed=False,
        scores=[],
        selected_skill="reviewer",
        failures=["missing file reviews/notes.md"],
        transcript="Wrote the review in the wrong folder.",
    )
    return SuiteReport(
        suite="reviewer",
        title="Dataset",
        skill="reviewer",
        harness="claude",
        sandbox="local",
        passed=False,
        tasks=[task],
        pack_fingerprint="fp",
        pack_case_ids=["review-notes"],
    )


def _check_result(report: SuiteReport):
    from skillgate_ai.gate import CheckResult

    return CheckResult(exit_code=1, report=report, run_id="arm-run")


def test_compare_versions_git_defaults_harness_from_history(tmp_path: Path) -> None:
    pack = _git_pack(tmp_path)
    append_eval(
        pack,
        run_id="hist-claude",
        passed=True,
        report={"harness": "claude", "passed": True, "tasks": []},
        config={"harness": "claude", "harness_pref": "claude"},
    )
    seen: list[str | None] = []

    def fake_run_check(target, **kwargs):
        del target
        seen.append(kwargs.get("harness"))
        return _check_result(_red_report())

    run_versions_compare(
        pack,
        git_refs=["HEAD", "HEAD"],
        root=tmp_path,
        run_check_fn=fake_run_check,
    )
    assert seen == ["claude", "claude"]

    seen.clear()
    run_versions_compare(
        pack,
        git_refs=["HEAD", "HEAD"],
        root=tmp_path,
        run_check_fn=fake_run_check,
        harness="codex",
    )
    assert seen == ["codex", "codex"]


def test_compare_versions_cli_accepts_harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pack = tmp_path / "reviewer"
    pack.mkdir()
    (pack / "SKILL.md").write_text("---\nname: reviewer\ndescription: d\n---\n", encoding="utf-8")
    (pack / "evals").mkdir()
    captured: dict[str, object] = {}

    def fake_run(path, **kwargs):
        captured["harness"] = kwargs.get("harness")
        captured["git_refs"] = kwargs.get("git_refs")
        return CompareResult(
            exit_code=0,
            payload={
                "compare_id": "c1",
                "mode": "versions",
                "status": "dry_run",
                "skill": "reviewer",
                "arms": [],
                "cases": [],
            },
        )

    monkeypatch.setattr("skillgate_ai.compare.run_versions_compare", fake_run)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    help_text = plain_text(runner.invoke(app, ["compare", "versions", "--help"]).stdout)
    assert "--harness" in help_text
    result = runner.invoke(
        app,
        [
            "compare",
            "versions",
            str(pack),
            "--git",
            "HEAD",
            "--git",
            "HEAD",
            "--harness",
            "claude",
            "--dry-run",
        ],
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert captured["harness"] == "claude"


def test_git_compare_saves_arm_runs_on_the_pack(tmp_path: Path) -> None:
    pack = _git_pack(tmp_path)

    def fake_run_check(target, **kwargs):
        del target, kwargs
        return _check_result(_red_report())

    run_versions_compare(
        pack,
        git_refs=["HEAD", "HEAD"],
        root=tmp_path,
        run_check_fn=fake_run_check,
        harness="claude",
    )
    saved = json.dumps(load_history(pack))
    assert "missing file reviews/notes.md" in saved
    assert "Wrote the review in the wrong folder." in saved
    assert "review-notes" in saved


def test_task_prompt_does_not_steer_files_into_output(tmp_path: Path) -> None:
    skill = Skill(
        path=tmp_path,
        name="reviewer",
        description="Review diffs.",
        body="# reviewer",
    )
    prompt = _cursor_prompt(
        "Save the review to reviews/notes.md",
        [skill],
        pinned_skill="reviewer",
    )
    assert "usually `output/`" not in prompt
    assert "reviews/notes.md" in prompt


def test_trigger_mode_installs_skill_without_naming_it(tmp_path: Path) -> None:
    skill_dir = tmp_path / "reviewer"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: reviewer\ndescription: Review diffs.\n---\n# reviewer\n",
        encoding="utf-8",
    )
    skill = ingest_skill(skill_dir, strict=False)
    task = TaskSpec(
        id="should-trigger",
        prompt="Review the diff.",
        expect_skill="reviewer",
        scorers=[ScorerSpec(type="skill_trigger")],
        trigger_mode=True,
    )
    spec = SuiteSpec(
        suite="reviewer-pack",
        skill=str(skill_dir),
        title="Dataset",
        tasks=[task],
    )
    workspace = tmp_path / "ws"
    seen: dict[str, object] = {}

    class Probe:
        name = "cursor-agent"

        def run(self, sandbox, prompt, skills, timeout_sec):
            del prompt, skills, timeout_sec
            gate = sandbox.workspace / ".skillgate"
            selected = gate / "selected.json"
            seen["selected_before"] = selected.is_file()
            seen["installed"] = (gate / "skills" / "reviewer" / "SKILL.md").is_file()
            seen["prompt_names_skill"] = "reviewer" in (gate / "catalog.md").read_text(
                encoding="utf-8"
            )
            return HarnessResult(
                trigger=TriggerEvidence(selected_skill=None, read_paths=[], transcript="did nothing"),
                transcript="did nothing",
            )

    report = _run_task(
        task=task,
        spec=spec,
        skills=[skill],
        harness=Probe(),
        sandbox=LocalSandbox(workspace),
        root=skill_dir,
        suite_dir=skill_dir,
    )
    assert seen["installed"] is True
    assert seen["selected_before"] is False
    assert report.passed is False
    assert report.selected_skill is None
    assert any("trigger" in failure.lower() for failure in report.failures)

    class Loaded:
        name = "cursor-agent"

        def run(self, sandbox, prompt, skills, timeout_sec):
            del sandbox, prompt, skills, timeout_sec
            path = ".skillgate/skills/reviewer/SKILL.md"
            return HarnessResult(
                trigger=TriggerEvidence(
                    selected_skill="reviewer",
                    read_paths=[path],
                    transcript=f"$ read {path}",
                ),
                transcript=f"$ read {path}",
            )

    loaded = _run_task(
        task=task,
        spec=spec,
        skills=[skill],
        harness=Loaded(),
        sandbox=LocalSandbox(tmp_path / "ws2"),
        root=skill_dir,
        suite_dir=skill_dir,
    )
    assert loaded.passed is True
    assert loaded.selected_skill == "reviewer"


def test_trigger_mode_prompt_does_not_name_the_skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from skillgate_ai.harness import CursorAgentHarness
    from test_judge import _cfg

    workspace = tmp_path / "ws"
    workspace.mkdir()
    gate = workspace / ".skillgate"
    gate.mkdir()
    (gate / "mode").write_text("trigger\n", encoding="utf-8")
    skill = Skill(
        path=tmp_path / "reviewer",
        name="reviewer",
        description="Review diffs.",
        body="# reviewer",
    )

    class Sandbox:
        def __init__(self) -> None:
            self.workspace = workspace
            self.command: list[str] = []

        def run(self, command, *, env=None, timeout=0, cwd=None):
            del env, timeout, cwd
            self.command = list(command)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("skillgate_ai.harness._cursor_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_agent_bin", lambda _p: "/bin/agent")
    sandbox = Sandbox()
    CursorAgentHarness(_cfg(cursor_api_key="cur-test")).run(
        sandbox,  # type: ignore[arg-type]
        "Review the diff.",
        [skill],
        timeout_sec=5,
    )
    prompt = sandbox.command[-1]
    assert "reviewer" not in prompt.lower()
    assert ".skillgate/skills" in prompt


def test_codex_login_disables_user_skills_without_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Subscription login stays put. User skills are disabled by session config."""
    from skillgate_ai.harness import AUTH_CLI_LOGIN, CodexCliHarness
    from test_judge import _cfg

    user_home = tmp_path / "home"
    foreign = user_home / ".codex" / "skills" / "other-skill"
    foreign.mkdir(parents=True)
    (foreign / "SKILL.md").write_text(
        "---\nname: other-skill\ndescription: not this test\n---\nsecret-other\n",
        encoding="utf-8",
    )
    nested = user_home / ".agents" / "skills" / 'odd"name' / "nested"
    nested.mkdir(parents=True)
    (nested / "SKILL.md").write_text(
        "---\nname: nested-skill\ndescription: nested\n---\nsecret-nested\n",
        encoding="utf-8",
    )
    hidden = user_home / ".codex" / "skills" / ".system" / "imagegen"
    hidden.mkdir(parents=True)
    (hidden / "SKILL.md").write_text("# system\n", encoding="utf-8")
    auth = user_home / ".codex" / "auth.json"
    auth.write_text('{"token":"sekret-token"}\n', encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: user_home))
    monkeypatch.delenv("CODEX_HOME", raising=False)

    skill_dir = tmp_path / "reviewer"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: reviewer\ndescription: Review diffs.\n---\n# reviewer\n",
        encoding="utf-8",
    )
    skill = ingest_skill(skill_dir, strict=False)
    workspace = tmp_path / "ws"
    workspace.mkdir()

    class Sandbox:
        def __init__(self) -> None:
            self.workspace = workspace
            self.env: dict[str, str] = {}
            self.command: list[str] = []

        def run(self, command, *, env=None, timeout=0, cwd=None):
            del timeout, cwd
            self.command = list(command)
            self.env = dict(env or {})
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("skillgate_ai.harness._codex_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _p: "/bin/codex")
    monkeypatch.setattr("skillgate_ai.harness._read_selection", lambda _w: None)
    monkeypatch.setattr("skillgate_ai.harness._parse_selected", lambda *a: None)
    monkeypatch.setattr("skillgate_ai.harness._parse_read_paths", lambda _t: [])
    monkeypatch.setattr("skillgate_ai.harness._write_selection", lambda *a: None)
    sandbox = Sandbox()
    result = CodexCliHarness(_cfg(codex_api_key=None)).run(
        sandbox,  # type: ignore[arg-type]
        "Review the diff.",
        [skill],
        timeout_sec=5,
    )
    assert "CODEX_HOME" not in sandbox.env
    assert "CODEX_API_KEY" not in sandbox.env
    assert not (workspace / ".skillgate" / "codex-home").exists()
    assert auth.read_text(encoding="utf-8") == '{"token":"sekret-token"}\n'
    blob = json.dumps({"env": sandbox.env, "argv": sandbox.command})
    assert "sekret-token" not in blob
    assert "secret-other" not in blob
    assert "secret-nested" not in blob
    overrides = [sandbox.command[i + 1] for i, arg in enumerate(sandbox.command) if arg == "-c"]
    assert "skills.include_instructions=false" in overrides
    assert "skills.bundled.enabled=false" in overrides
    disabled = next(item for item in overrides if item.startswith("skills.config="))
    assert str(foreign / "SKILL.md") in disabled
    nested_md = str(nested / "SKILL.md").replace("\\", "\\\\").replace('"', '\\"')
    assert nested_md in disabled
    assert "enabled=false" in disabled
    assert ".system" not in disabled
    assert "auth.json" not in disabled
    assert "reviewer" not in disabled
    assert result.auth_mode == AUTH_CLI_LOGIN


def test_codex_custom_home_disables_that_skills_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from skillgate_ai.harness import CodexCliHarness
    from test_judge import _cfg

    user_home = tmp_path / "home"
    user_home.mkdir()
    login_home = tmp_path / "login-home"
    custom = login_home / "skills" / "from-home"
    custom.mkdir(parents=True)
    (custom / "SKILL.md").write_text("# from home\nsecret-home\n", encoding="utf-8")
    ignored = user_home / ".codex" / "skills" / "ignored-skill"
    ignored.mkdir(parents=True)
    (ignored / "SKILL.md").write_text("# ignored\n", encoding="utf-8")
    agents = user_home / ".agents" / "skills" / "agents-skill"
    agents.mkdir(parents=True)
    (agents / "SKILL.md").write_text("# agents\n", encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: user_home))
    monkeypatch.setenv("CODEX_HOME", str(login_home))
    workspace = tmp_path / "ws"
    workspace.mkdir()

    class Sandbox:
        def __init__(self) -> None:
            self.workspace = workspace
            self.command: list[str] = []
            self.env: dict[str, str] = {}

        def run(self, command, *, env=None, timeout=0, cwd=None):
            del timeout, cwd
            self.command = list(command)
            self.env = dict(env or {})
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("skillgate_ai.harness._codex_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _p: "/bin/codex")
    monkeypatch.setattr("skillgate_ai.harness._read_selection", lambda _w: None)
    monkeypatch.setattr("skillgate_ai.harness._parse_selected", lambda *a: None)
    monkeypatch.setattr("skillgate_ai.harness._parse_read_paths", lambda _t: [])
    monkeypatch.setattr("skillgate_ai.harness._write_selection", lambda *a: None)
    sandbox = Sandbox()
    CodexCliHarness(_cfg(codex_api_key=None)).run(
        sandbox,  # type: ignore[arg-type]
        "task",
        [],
        timeout_sec=5,
    )
    assert "CODEX_HOME" not in sandbox.env
    overrides = [sandbox.command[i + 1] for i, arg in enumerate(sandbox.command) if arg == "-c"]
    disabled = next(item for item in overrides if item.startswith("skills.config="))
    assert str(custom / "SKILL.md") in disabled
    assert str(agents / "SKILL.md") in disabled
    assert "ignored-skill" not in disabled
    assert "secret-home" not in disabled


def test_round3_custom_answer_and_rate_limit_repros(tmp_path: Path) -> None:
    """The 0.7.2 display and transcript fixes cover the live repro shapes."""
    from skillgate_ai.harness import _jsonl_transcript
    from skillgate_ai.judge_context import build_agent_trajectory
    from skillgate_ai.judge_openai import _state_text
    from skillgate_ai.report import report_to_dict

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
                    task_id="q",
                    prompt="p",
                    expect_skill="web",
                    passed=False,
                    scores=[],
                    selected_skill="web",
                    failures=["avoids useEffect fetch No"],
                    judge={
                        "status": "completed",
                        "answers": {"avoids_useeffect_fetch": {"probability": 1.0}},
                        "cells": {
                            "avoids_useeffect_fetch": {
                                "label": "avoids useEffect fetch",
                                "choice": None,
                                "reason": None,
                            }
                        },
                    },
                )
            ],
        )
    )
    answers = {item["label"]: item["answer"] for item in payload["tasks"][0]["check_answers"]}
    assert answers["avoids useEffect fetch"] == "Yes"

    rate = json.dumps(
        {"type": "rate_limit_event", "rate_limit_info": {"utilization": 0.38}}
    )
    tool = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Bash",
                        "input": {"command": "git diff"},
                    }
                ]
            },
        }
    )
    result = json.dumps(
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_1", "content": "reviews/notes.md"}
                ]
            },
        }
    )
    rendered = _jsonl_transcript("\n".join([tool, rate, result, rate]), "")
    assert "rate_limit_event" not in rendered
    assert "utilization" not in rendered
    assert "git diff" in rendered
    assert "reviews/notes.md" in rendered
    state = json.loads(
        _state_text(
            {
                "transcript_tail": rendered,
                "agent_trajectory": build_agent_trajectory(
                    spans=None,
                    transcript=rendered,
                    path=None,
                    scores=[],
                    command_log="\n".join([tool, rate, result]),
                ),
            }
        )
    )
    blob = json.dumps(state)
    assert "rate_limit_event" not in blob
    assert "0.38" not in blob
    pack = tmp_path / "pack"
    pack.mkdir()
    append_eval(pack, run_id="r", passed=False, report={"tasks": [{"transcript": rendered}]})
    assert "rate_limit_event" not in json.dumps(load_history(pack))
