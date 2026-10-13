"""Regression tests for 0.6.1 fresh-env bug fixes."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from conftest import plain_text
from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.compare import parse_arm_spec, run_models_compare
from skillgate_ai.history import append_compare, load_history
from skillgate_ai.keys import set_vault_key

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]


def _pdf_pack(tmp_path: Path) -> Path:
    skills = tmp_path / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    pack = skills / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    return pack


def test_compare_models_cases_limits_history_task_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = _pdf_pack(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    case_ids = ["extract-hello", "rotate-hello"]
    seen_task_counts: list[int] = []

    def fake_run_check(target, **kwargs):
        from skillgate_ai.engine import SuiteReport, TaskReport
        from skillgate_ai.gate import CheckResult, persist_eval
        from skillgate_ai.report import report_to_dict

        checks = kwargs.get("checks") or []
        seen_task_counts.append(len(checks))
        tasks = [
            TaskReport(
                task_id=str(c.get("id")),
                prompt="p",
                expect_skill=True,
                passed=True,
                scores=[],
                selected_skill="pdf",
                failures=[],
                usage={"tokens_total": 50, "cost_usd": 0.01},
            )
            for c in checks
        ]
        report = SuiteReport(
            suite="pdf",
            title="t",
            skill="pdf",
            skill_description="d",
            harness=kwargs.get("harness") or "llm",
            sandbox="local",
            passed=True,
            tasks=tasks,
            pack_fingerprint="fp",
            pack_case_ids=[c.get("id") for c in checks],
        )
        rid = kwargs.get("run_id") or "hist061a"
        persist_eval(
            pack_root=pack,
            run_id=rid,
            passed=True,
            report=report_to_dict(report),
            config={"harness": "llm"},
        )
        return CheckResult(exit_code=0, report=report)

    result = run_models_compare(
        pack,
        arms=[
            parse_arm_spec("A:llm", arm_id="a", index=0),
            parse_arm_spec("B:llm:gpt-4o-mini", arm_id="b", index=1),
        ],
        root=tmp_path,
        case_ids=case_ids,
        run_check_fn=fake_run_check,
        max_spend_usd=100.0,
        compare_id="abc123456789",
    )
    assert result.exit_code == 0
    assert seen_task_counts == [2, 2]
    assert result.payload["arms"][0]["task_count"] == 2
    assert result.payload["pack_case_ids"] == case_ids
    history = load_history(pack, limit=2)
    assert len(history) >= 2
    for row in history[:2]:
        report = row.get("report") or {}
        assert report.get("task_count") == 2
        assert list(report.get("pack_case_ids") or []) == case_ids


def test_compare_models_arm_model_override_reaches_run_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = _pdf_pack(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    seen_models: list[str | None] = []

    def fake_run_check(target, **kwargs):
        from skillgate_ai.engine import SuiteReport, TaskReport
        from skillgate_ai.gate import CheckResult

        seen_models.append(kwargs.get("model"))
        checks = kwargs.get("checks") or []
        tasks = [
            TaskReport(
                task_id=str(c.get("id")),
                prompt="p",
                expect_skill=True,
                passed=True,
                scores=[],
                selected_skill="pdf",
                failures=[],
                usage={"tokens_total": 10, "cost_usd": 0.0},
            )
            for c in checks[:1]
        ]
        report = SuiteReport(
            suite="pdf",
            title="t",
            skill="pdf",
            skill_description="d",
            harness="llm",
            sandbox="local",
            passed=True,
            tasks=tasks,
            pack_fingerprint="fp",
            pack_case_ids=[tasks[0].task_id],
        )
        return CheckResult(exit_code=0, report=report)

    run_models_compare(
        pack,
        arms=[
            parse_arm_spec("A:llm", arm_id="a", index=0),
            parse_arm_spec("B:llm:gpt-4o-mini", arm_id="b", index=1),
        ],
        root=tmp_path,
        case_ids=["extract-hello"],
        run_check_fn=fake_run_check,
        max_spend_usd=100.0,
    )
    assert seen_models == [None, "gpt-4o-mini"]


def test_compare_versions_unknown_run_errors_before_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = _pdf_pack(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["compare", "versions", str(pack), "--run", "nope-a", "--run", "nope-b"],
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "started" not in out.lower()
    assert "Unknown run" in out


def test_compare_cancel_on_finished_job_reports_already_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = _pdf_pack(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    compare_id = "abcdef123456"
    append_compare(
        pack,
        row={
            "kind": "compare",
            "compare_id": compare_id,
            "mode": "versions",
            "status": "done",
            "arms": [],
            "cases": [],
        },
    )
    result = runner.invoke(app, ["compare", "cancel", compare_id])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert "already done" in out.lower()
    assert "Cancel requested" not in out


def test_compare_cli_table_separates_case_from_pass(tmp_path: Path) -> None:
    from skillgate_ai.compare_format import format_compare_cli

    payload = {
        "mode": "models",
        "skill": "pdf",
        "arms": [
            {"arm_id": "a", "label": "A"},
            {"arm_id": "b", "label": "B"},
        ],
        "cases": [
            {
                "case_id": "merge-alpha-beta",
                "results": {"a": {"passed": True}, "b": {"passed": True}},
            }
        ],
    }
    text = format_compare_cli(payload)
    assert "merge-alpha-beta" in text
    assert "| Pass" in text
    assert "merge-alpha-betaPass" not in text.replace(" ", "")


def test_keys_list_labels_ai_gateway_api_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    set_vault_key(tmp_path, "AI_GATEWAY_API_KEY", "gw-test")
    listed = runner.invoke(app, ["keys", "list"])
    out = plain_text(listed.stdout + listed.stderr)
    assert listed.exit_code == 0, out
    assert "AI_GATEWAY_API_KEY" in out
    assert "Other (Settings)" not in out


def test_ui_startup_omits_docker_image_line(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    from skillgate_ai.server import serve_ui

    messages: list[str] = []

    def capture(msg: str, **kwargs) -> None:
        messages.append(msg)

    monkeypatch.setattr("builtins.print", capture)
    monkeypatch.setattr("skillgate_ai.server._ensure_port_free", lambda *_a, **_k: None)
    monkeypatch.setattr("uvicorn.run", lambda *_args, **_kwargs: None)
    serve_ui(root=tmp_path, host="127.0.0.1", port=8765, open_browser=False)
    blob = "\n".join(messages)
    assert "Docker image" not in blob


def test_import_targets_nearest_nested_workspace(tmp_path: Path, monkeypatch) -> None:
    parent = tmp_path / "ws"
    nested = parent / "imp"
    parent.mkdir()
    nested.mkdir()
    monkeypatch.chdir(parent)
    runner.invoke(app, ["init"])
    monkeypatch.chdir(nested)
    runner.invoke(app, ["init"])
    agent_skill = tmp_path / "agent-skills" / "my-skill"
    agent_skill.mkdir(parents=True)
    (agent_skill / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: d\n---\n# my-skill\n",
        encoding="utf-8",
    )
    cursor_parent = tmp_path / "cursor-skills"
    cursor_parent.mkdir(parents=True)
    cursor_skills = cursor_parent / "my-skill"
    shutil.copytree(agent_skill, cursor_skills, dirs_exist_ok=True)
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(cursor_parent))
    monkeypatch.delenv("SKILLGATE_ROOT", raising=False)
    monkeypatch.chdir(nested)
    result = runner.invoke(app, ["import", "--source", "cursor", "--only", "my-skill"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert (nested / "skills" / "my-skill" / "SKILL.md").is_file()
    assert not (parent / "skills" / "my-skill" / "SKILL.md").exists()


def test_judge_provider_cli_uses_neutral_copy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    saved = runner.invoke(app, ["judge", "provider", "set", "jev", "--base-url", "https://jev.example"])
    out = plain_text(saved.stdout + saved.stderr)
    assert saved.exit_code == 0, out
    assert "Jev" not in out
    assert "the judge" in out.lower()
    shown = runner.invoke(app, ["judge", "provider", "show"])
    assert "Jev" not in plain_text(shown.stdout)
    assert "the judge" in plain_text(shown.stdout).lower()
