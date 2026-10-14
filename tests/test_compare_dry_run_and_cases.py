from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.compare import CompareError, parse_arm_spec, run_models_compare

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]


def _pack(tmp_path: Path) -> Path:
    pack = tmp_path / "pdf"
    import shutil

    shutil.copytree(ROOT / "skills" / "pdf", pack)
    return pack


def test_parse_arm_spec_requires_colon() -> None:
    with pytest.raises(CompareError, match="Label:harness"):
        parse_arm_spec("nocolon", arm_id="a", index=0)


def test_compare_models_cli_nocolon_arm(tmp_path: Path, monkeypatch) -> None:
    pack = _pack(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = runner.invoke(
        app,
        [
            "compare",
            "models",
            str(pack),
            "--arm",
            "nocolon",
            "--arm",
            "B:codex",
        ],
    )
    assert result.exit_code == 1
    assert "Traceback" not in (result.stdout + result.stderr)


def test_compare_models_dry_run_checks_row_not_none_slash(tmp_path: Path, monkeypatch) -> None:
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
            "B:llm",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "None/" not in result.stdout


def test_compare_models_negative_cap_does_not_print_started(tmp_path: Path, monkeypatch) -> None:
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
            "B:llm",
            "--max-spend-usd",
            "-1",
        ],
    )
    assert result.exit_code == 1
    assert "started" not in result.stdout


def test_compare_models_dry_run_shows_arms_and_case_count(tmp_path: Path, monkeypatch) -> None:
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
            "B:llm",
            "--cases",
            "extract-hello,merge-alpha-beta,rotate-hello",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "3 checks" in result.stdout
    assert "2 arms" in result.stdout
    assert "Arm A" in result.stdout or "A" in result.stdout


def test_compare_models_dry_run_rejects_invalid_harness(tmp_path: Path, monkeypatch) -> None:
    pack = _pack(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = runner.invoke(
        app,
        [
            "compare",
            "models",
            str(pack),
            "--arm",
            "A:bogus",
            "--arm",
            "B:codex",
            "--dry-run",
        ],
    )
    assert result.exit_code == 1


def test_compare_models_dry_run_rejects_negative_spend(tmp_path: Path, monkeypatch) -> None:
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
            "B:codex",
            "--max-spend-usd",
            "-1",
            "--dry-run",
        ],
    )
    assert result.exit_code == 1


def test_compare_models_cases_limits_run_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pack = _pack(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    case_ids = ["extract-hello", "merge-alpha-beta", "rotate-hello"]
    seen_checks: list[list[str]] = []

    def fake_run_check(target, **kwargs):
        from skillgate_ai.engine import SuiteReport, TaskReport
        from skillgate_ai.gate import CheckResult

        checks = kwargs.get("checks") or []
        seen_checks.append([str(c.get("id")) for c in checks])
        tasks = [
            TaskReport(
                task_id=cid,
                prompt="p",
                expect_skill=True,
                passed=True,
                scores=[],
                selected_skill="pdf",
                failures=[],
                usage={"tokens_total": 100, "cost_usd": 0.01},
            )
            for cid in [c.get("id") for c in checks]
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
        return CheckResult(exit_code=0, report=report)

    result = run_models_compare(
        pack,
        arms=[
            parse_arm_spec("A:llm", arm_id="a", index=0),
            parse_arm_spec("B:llm", arm_id="b", index=1),
        ],
        root=tmp_path,
        case_ids=case_ids,
        run_check_fn=fake_run_check,
        max_spend_usd=100.0,
    )
    assert result.exit_code == 0
    assert len(seen_checks) == 2
    assert seen_checks[0] == case_ids
    assert len(seen_checks[0]) == 3
    assert result.payload["cases"] and len(result.payload["cases"]) == 3
    usage = result.payload["arms"][0].get("usage") or {}
    assert usage.get("cost_usd") == pytest.approx(0.03)
