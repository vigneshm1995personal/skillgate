from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path

from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.compare import run_models_compare, parse_arm_spec
from skillgate_ai.compare_control import request_cancel_compare
from skillgate_ai.history import append_eval, load_compares

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]


def _pack(tmp_path: Path) -> Path:
    dest = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    return dest


def test_compare_models_dry_run(tmp_path: Path, monkeypatch) -> None:
    pack = _pack(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = runner.invoke(
        app,
        [
            "compare",
            "models",
            str(pack),
            "--arm",
            "A:codex",
            "--arm",
            "B:cursor-agent",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "dry_run" in result.stdout or "Compare" in result.stdout


def test_compare_models_arm_file_and_spend_cap(tmp_path: Path, monkeypatch) -> None:
    pack = _pack(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    arm_path = tmp_path / "arm.json"
    arm_path.write_text(
        json.dumps({"label": "File arm", "harness_pref": "codex", "model": ""}),
        encoding="utf-8",
    )

    def fake_run_check(target, **kwargs):
        from skillgate_ai.gate import CheckResult
        from skillgate_ai.engine import SuiteReport, TaskReport

        report = SuiteReport(
            suite="pdf",
            title="t",
            skill="pdf",
            skill_description="d",
            harness="codex",
            sandbox="local",
            passed=True,
            tasks=[
                TaskReport(
                    task_id="c1",
                    prompt="p",
                    expect_skill=True,
                    passed=True,
                    scores=[],
                    selected_skill="pdf",
                    failures=[],
                )
            ],
            skill_path=str(pack),
            pack_fingerprint="fp",
            pack_case_ids=("c1",),
        )
        return CheckResult(report=report, exit_code=0, run_id=kwargs.get("run_id") or "r")

    monkeypatch.setattr("skillgate_ai.compare.run_check", fake_run_check)
    monkeypatch.setenv("SKILLGATE_OPENAI_API_KEY", "sk-test")

    result = runner.invoke(
        app,
        [
            "compare",
            "models",
            str(pack),
            "--arm",
            "A:cursor-agent",
            "--arm-file",
            str(arm_path),
            "--max-spend-usd",
            "5",
            "--json",
        ],
    )
    assert result.exit_code == 0
    assert "File arm" in result.stdout or "arms" in result.stdout


def test_compare_versions_history(tmp_path: Path, monkeypatch) -> None:
    pack = _pack(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    fp = "fp"
    append_eval(
        pack,
        run_id="r1",
        passed=True,
        report={
            "pack_fingerprint": fp,
            "pack_case_ids": ["c1"],
            "tasks": [{"id": "c1", "passed": True}],
        },
    )
    append_eval(
        pack,
        run_id="r2",
        passed=False,
        report={
            "pack_fingerprint": fp,
            "pack_case_ids": ["c1"],
            "tasks": [{"id": "c1", "passed": False}],
        },
    )
    result = runner.invoke(
        app,
        ["compare", "versions", str(pack), "--run", "r1", "--run", "r2", "--json"],
    )
    assert result.exit_code == 0
    assert "disagreement" in result.stdout


def test_compare_list_and_show(tmp_path: Path, monkeypatch) -> None:
    pack = _pack(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    fp = "fp"
    append_eval(
        pack,
        run_id="r1",
        passed=True,
        report={"pack_fingerprint": fp, "pack_case_ids": ["c1"], "tasks": [{"id": "c1", "passed": True}]},
    )
    append_eval(
        pack,
        run_id="r2",
        passed=True,
        report={"pack_fingerprint": fp, "pack_case_ids": ["c1"], "tasks": [{"id": "c1", "passed": True}]},
    )
    versions = runner.invoke(
        app, ["compare", "versions", str(pack), "--run", "r1", "--run", "r2", "--json"]
    )
    assert versions.exit_code == 0
    compare_id = json.loads(versions.stdout)["compare_id"]
    listed = runner.invoke(app, ["compare", "list", str(pack), "--json"])
    assert listed.exit_code == 0
    assert compare_id in listed.stdout
    shown = runner.invoke(app, ["compare", "show", compare_id, "--skill", str(pack), "--json"])
    assert shown.exit_code == 0
    assert shown.stdout.strip().startswith("{")


def test_compare_cancel_cli_writes_flag(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    compare_id = "abc123def456"
    result = runner.invoke(app, ["compare", "cancel", compare_id])
    assert result.exit_code == 0
    flag = tmp_path / ".skillgate" / "cancel" / compare_id
    assert flag.is_file()


def test_compare_cancel_unknown_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = runner.invoke(app, ["compare", "cancel", "nope"])
    assert result.exit_code == 1
    assert "Unknown compare" in result.stdout


def test_compare_list_empty(tmp_path: Path, monkeypatch) -> None:
    pack = _pack(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = runner.invoke(app, ["compare", "list", str(pack)])
    assert result.exit_code == 0
    assert "No compares yet" in result.stdout


def test_compare_models_arm_nocolon_no_traceback(tmp_path: Path, monkeypatch) -> None:
    pack = _pack(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = runner.invoke(
        app,
        ["compare", "models", str(pack), "--arm", "nocolon", "--arm", "B:codex", "--dry-run"],
    )
    assert result.exit_code == 1
    assert "Traceback" not in result.stdout
    assert "Label:harness" in result.stdout


def test_compare_models_prints_id_at_start(tmp_path: Path, monkeypatch) -> None:
    pack = _pack(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.setenv("SKILLGATE_OPENAI_API_KEY", "sk-test")

    def fake_run_check(target, **kwargs):
        from skillgate_ai.gate import CheckResult
        from skillgate_ai.engine import SuiteReport, TaskReport

        report = SuiteReport(
            suite="pdf",
            title="t",
            skill="pdf",
            skill_description="d",
            harness="codex",
            sandbox="local",
            passed=True,
            tasks=[
                TaskReport(
                    task_id="c1",
                    prompt="p",
                    expect_skill=True,
                    passed=True,
                    scores=[],
                    selected_skill="pdf",
                    failures=[],
                )
            ],
            skill_path=str(pack),
            pack_fingerprint="fp",
            pack_case_ids=("c1",),
        )
        return CheckResult(report=report, exit_code=0, run_id=kwargs.get("run_id") or "r")

    monkeypatch.setattr("skillgate_ai.compare.run_check", fake_run_check)
    result = runner.invoke(
        app,
        [
            "compare",
            "models",
            str(pack),
            "--arm",
            "A:codex",
            "--arm",
            "B:codex",
        ],
    )
    assert result.exit_code == 0
    assert "Compare " in result.stdout and "started" in result.stdout


def test_compare_models_cancel_stops_next_arm(tmp_path: Path, monkeypatch) -> None:
    pack = _pack(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.setenv("SKILLGATE_OPENAI_API_KEY", "sk-test")
    calls = {"n": 0}
    compare_id_holder: dict[str, str] = {}

    def fake_run_check(target, **kwargs):
        from skillgate_ai.gate import CheckResult
        from skillgate_ai.engine import SuiteReport, TaskReport

        calls["n"] += 1
        if calls["n"] == 1:
            threading.Timer(
                0.05,
                lambda: request_cancel_compare(tmp_path, compare_id_holder["id"]),
            ).start()
            time.sleep(0.08)
        report = SuiteReport(
            suite="pdf",
            title="t",
            skill="pdf",
            skill_description="d",
            harness="codex",
            sandbox="local",
            passed=True,
            tasks=[
                TaskReport(
                    task_id="c1",
                    prompt="p",
                    expect_skill=True,
                    passed=True,
                    scores=[],
                    selected_skill="pdf",
                    failures=[],
                )
            ],
            skill_path=str(pack),
            pack_fingerprint="fp",
            pack_case_ids=("c1",),
        )
        return CheckResult(report=report, exit_code=0, run_id=kwargs.get("run_id") or "r")

    monkeypatch.setattr("skillgate_ai.compare.run_check", fake_run_check)

    def run():
        compare_id_holder["id"] = "abcd12345678"
        return run_models_compare(
            pack,
            arms=[
                parse_arm_spec("A:codex", arm_id="a", index=0),
                parse_arm_spec("B:cursor-agent", arm_id="b", index=1),
            ],
            root=tmp_path,
            compare_id="abcd12345678",
        )

    result = run()
    assert result.payload["status"] == "cancelled"
    assert len(result.payload["arms"]) == 1
    assert load_compares(pack)[-1]["status"] == "cancelled"
