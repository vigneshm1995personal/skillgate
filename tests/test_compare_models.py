from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from skillgate_ai.compare import (
    CompareError,
    arm_label_defaults,
    parse_arm_spec,
    run_models_compare,
    scrub_compare_payload,
    scrub_customer_compare_payload,
)
from skillgate_ai.history import append_compare, load_compares, load_history


def _mini_pack(tmp_path: Path) -> Path:
    pack = tmp_path / "pdf"
    src = Path(__file__).resolve().parents[1] / "skills" / "pdf"
    import shutil

    shutil.copytree(src, pack)
    from skillgate_ai.demo_files import ensure_demo_pdfs

    ensure_demo_pdfs(pack / "evals" / "fixtures")
    return pack


def _fake_report(passed: bool, fp: str, task_ids: list[str]) -> dict[str, Any]:
    tasks = [
        {
            "id": tid,
            "passed": passed,
            "usage": {"tokens_total": 1000, "cost_usd": 0.01},
            "judge": {"provider": "openai", "model": "gpt-secret", "display_name": "OpenAI"},
        }
        for tid in task_ids
    ]
    return {
        "skill": "pdf",
        "passed": passed,
        "task_count": len(task_ids),
        "passed_count": len(task_ids) if passed else 0,
        "pack_fingerprint": fp,
        "pack_case_ids": task_ids,
        "tasks": tasks,
        "usage": {"tokens_total": 1000 * len(task_ids), "cost_usd": 0.01 * len(task_ids)},
        "config": {
            "harness": "codex",
            "model": "gpt-hidden",
            "label": "Codex · gpt-hidden",
            "judge": {"provider": "openai", "model": "gpt-6-luna"},
        },
    }


def test_parse_arm_spec_shorthand() -> None:
    arm = parse_arm_spec("Cursor:cursor-agent", arm_id="a", index=0)
    assert arm.label == "Cursor"
    assert arm.harness_pref == "cursor-agent"
    assert arm.arm_id == "a"


def test_arm_label_defaults() -> None:
    assert arm_label_defaults(2) == ["Arm A", "Arm B"]


def test_models_compare_writes_run_and_compare_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = _mini_pack(tmp_path)
    fp = "fp-abc"
    calls: list[dict[str, Any]] = []

    def fake_run_check(target, **kwargs):
        from skillgate_ai.gate import CheckResult
        from skillgate_ai.engine import SuiteReport, TaskReport

        calls.append({"target": target, "harness": kwargs.get("harness"), "run_id": kwargs.get("run_id")})
        tasks = [
            TaskReport(
                task_id="extract-hello",
                prompt="p",
                expect_skill=True,
                passed=calls[-1]["harness"] != "codex",
                scores=[],
                selected_skill="pdf",
                failures=[],
            )
        ]
        report = SuiteReport(
            suite="pdf",
            title="t",
            skill="pdf",
            skill_description="d",
            harness=kwargs.get("harness") or "cursor-agent",
            sandbox="local",
            passed=tasks[0].passed,
            tasks=tasks,
            skill_path=str(pack),
            pack_fingerprint=fp,
            pack_case_ids=("extract-hello",),
            config={"harness": kwargs.get("harness"), "label": "Arm"},
        )
        return CheckResult(report=report, exit_code=0 if report.passed else 1, run_id=kwargs.get("run_id") or "r1")

    monkeypatch.setattr("skillgate_ai.compare.run_check", fake_run_check)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.setenv("SKILLGATE_OPENAI_API_KEY", "sk-test")

    result = run_models_compare(
        pack,
        arms=[
            parse_arm_spec("A:cursor-agent", arm_id="a", index=0),
            parse_arm_spec("B:codex", arm_id="b", index=1),
        ],
        root=tmp_path,
        max_spend_usd=5.0,
    )
    assert result.exit_code == 0
    assert result.payload["status"] == "done"
    assert len(result.payload["arms"]) == 2
    assert result.payload["cases"][0]["disagreement"] is True
    compares = load_compares(pack)
    assert len(compares) == 1
    assert compares[0]["kind"] == "compare"
    assert compares[0]["compare_id"] == result.payload["compare_id"]


def test_models_compare_fingerprint_mismatch_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = _mini_pack(tmp_path)

    def fake_run_check(target, **kwargs):
        from skillgate_ai.gate import CheckResult
        from skillgate_ai.engine import SuiteReport, TaskReport

        fp = "fp-one" if kwargs.get("harness") == "cursor-agent" else "fp-two"
        report = SuiteReport(
            suite="pdf",
            title="t",
            skill="pdf",
            skill_description="d",
            harness="cursor-agent",
            sandbox="local",
            passed=True,
            tasks=[
                TaskReport(
                    task_id="extract-hello",
                    prompt="p",
                    expect_skill=True,
                    passed=True,
                    scores=[],
                    selected_skill="pdf",
                    failures=[],
                )
            ],
            skill_path=str(pack),
            pack_fingerprint=fp,
            pack_case_ids=("extract-hello",),
        )
        return CheckResult(report=report, exit_code=0, run_id="x")

    monkeypatch.setattr("skillgate_ai.compare.run_check", fake_run_check)
    monkeypatch.setenv("SKILLGATE_OPENAI_API_KEY", "sk-test")

    with pytest.raises(CompareError) as exc:
        run_models_compare(
            pack,
            arms=[
                parse_arm_spec("A:cursor-agent", arm_id="a", index=0),
                parse_arm_spec("B:codex", arm_id="b", index=1),
            ],
            root=tmp_path,
        )
    assert exc.value.exit_code == 1


def test_scrub_compare_payload_removes_judge_and_model() -> None:
    raw = {
        "compare_id": "c1",
        "arms": [{"label": "Arm A", "config": {"model": "secret", "judge": {"provider": "openai"}}}],
        "cases": [],
    }
    scrubbed = scrub_compare_payload(raw)
    blob = json.dumps(scrubbed)
    assert "openai" not in blob.lower()
    assert "secret" not in blob
    assert scrubbed["arms"][0]["config"].get("model") is None


def test_scrub_customer_compare_payload_applies_browser_scrub() -> None:
    raw = {
        "compare_id": "c1",
        "arms": [
            {
                "label": "My custom arm",
                "subtitle": "openai/gpt-4o-mini",
                "config": {
                    "harness": "llm",
                    "harness_pref": "cursor-agent",
                    "model": "openai/gpt-4o-mini",
                    "judge": {"provider": "openai", "model": "openai/gpt-6-luna-decisions"},
                },
            }
        ],
        "cases": [],
    }
    scrubbed = scrub_customer_compare_payload(raw)
    blob = json.dumps(scrubbed).lower()
    assert "openai/gpt" not in blob
    assert "gpt-6-luna" not in blob
    assert "provider" not in blob
    assert scrubbed["arms"][0]["label"] == "My custom arm"


def test_scrub_customer_compare_payload_fills_missing_label() -> None:
    raw = {
        "compare_id": "c1",
        "arms": [{"label": "", "config": {"harness": "codex", "harness_pref": "codex"}}],
        "cases": [],
    }
    scrubbed = scrub_customer_compare_payload(raw)
    assert scrubbed["arms"][0]["label"]


def test_append_compare_scrubs_leaks_on_disk(tmp_path: Path) -> None:
    pack = tmp_path / "pdf"
    pack.mkdir()
    leaky = {
        "compare_id": "abc123456789",
        "mode": "models",
        "skill": "pdf",
        "status": "done",
        "arms": [
            {
                "label": "Arm A",
                "config": {
                    "harness": "llm",
                    "model": "openai/gpt-secret",
                    "judge": {
                        "provider": "openai",
                        "model": "openai/gpt-6-luna-decisions",
                    },
                },
            }
        ],
        "cases": [],
    }
    append_compare(pack, row=leaky)
    files = list((pack / "evals" / "history").glob("*.jsonl"))
    assert files
    disk = files[0].read_text(encoding="utf-8").lower()
    assert "gpt-6-luna" not in disk
    assert "gpt-secret" not in disk
    assert "openai/gpt" not in disk
    loaded = load_compares(pack)[0]
    assert loaded["arms"][0]["label"] == "Arm A"


def test_spend_cap_stops_without_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = _mini_pack(tmp_path)

    def fake_run_check(target, **kwargs):
        from skillgate_ai.gate import CheckResult
        from skillgate_ai.engine import SuiteReport, TaskReport

        report = SuiteReport(
            suite="pdf",
            title="t",
            skill="pdf",
            skill_description="d",
            harness="cursor-agent",
            sandbox="local",
            passed=True,
            tasks=[
                TaskReport(
                    task_id="extract-hello",
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
            pack_case_ids=("extract-hello",),
            config={"label": "Arm"},
        )
        report.tasks[0].usage = {"tokens_total": 1, "cost_usd": 3.0}
        return CheckResult(report=report, exit_code=0, run_id=kwargs.get("run_id") or "r")

    monkeypatch.setattr("skillgate_ai.compare.run_check", fake_run_check)
    monkeypatch.setenv("SKILLGATE_OPENAI_API_KEY", "sk-test")

    result = run_models_compare(
        pack,
        arms=[
            parse_arm_spec("A:codex", arm_id="a", index=0),
            parse_arm_spec("B:codex", arm_id="b", index=1),
            parse_arm_spec("C:codex", arm_id="c", index=2),
        ],
        root=tmp_path,
        max_spend_usd=5.0,
    )
    assert result.exit_code == 0
    assert result.payload["spend"]["stopped_reason"] == "spend_cap"
    assert len(result.payload["arms"]) == 2


def test_append_compare_roundtrip(tmp_path: Path) -> None:
    pack = tmp_path / "skill"
    (pack / "evals" / "history").mkdir(parents=True)
    row = {"kind": "compare", "compare_id": "abc", "mode": "models"}
    dest = append_compare(pack, row=row)
    assert dest is not None
    assert load_compares(pack)[0]["compare_id"] == "abc"
    assert load_history(pack) == []
