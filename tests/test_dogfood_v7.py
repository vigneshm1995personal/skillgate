"""Dogfood v7 regressions from a live Claude Code Pro run."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from test_judge_providers import FakeResponse

from skillgate_ai.case_pack import _persist_golden, golden_state
from skillgate_ai.compare import (
    parse_arm_spec,
    run_models_compare,
    scrub_compare_payload,
    scrub_customer_compare_payload,
)
from skillgate_ai.eval_config import EvalRunConfig, with_model
from skillgate_ai.judge_context import parse_command_runs
from skillgate_ai.judge_openai import _state_text
from skillgate_ai.judge_providers.compatible import CompatibleBackend
from skillgate_ai.pack_files import GOLDEN_TAIL_CHARS, read_capped_text
from skillgate_ai.sandbox import _sandbox_env
from skillgate_ai.suite import TaskSpec
from skillgate_ai.workspace_outputs import collect_workspace_outputs


def test_parse_command_runs_from_claude_stream_json() -> None:
    transcript = "\n".join(
        [
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_bash",
                                "name": "Bash",
                                "input": {"command": "pytest -q output/test_slugify.py"},
                            }
                        ],
                    },
                }
            ),
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_bash",
                                "content": "1 passed in 0.12s",
                            }
                        ],
                    },
                }
            ),
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_read",
                                "name": "Read",
                                "input": {"file_path": "output/slugify.py"},
                            }
                        ],
                    },
                }
            ),
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_read",
                                "content": [
                                    {"type": "text", "text": "def slugify(text): ..."}
                                ],
                            }
                        ],
                    },
                }
            ),
        ]
    )
    runs = parse_command_runs(transcript)
    assert len(runs) >= 2
    bash = next(run for run in runs if "pytest" in str(run.get("command") or ""))
    assert "passed" in (bash.get("output") or "").lower()
    read = next(run for run in runs if str(run.get("tool") or "").lower() == "read")
    assert "slugify.py" in str(read.get("command") or "")
    assert "def slugify" in (read.get("output") or "")


def test_with_model_keeps_requested_alias() -> None:
    run = EvalRunConfig(harness="claude", model="sonnet", requested_model="sonnet")
    updated = with_model(run, "claude-sonnet-5-5")
    assert updated.model == "claude-sonnet-5-5"
    assert updated.requested_model == "sonnet"
    payload = updated.to_dict()
    assert payload["model"] == "claude-sonnet-5-5"
    assert payload["requested_model"] == "sonnet"


def test_run_check_stores_resolved_model_over_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    from skillgate_ai.demo_files import ensure_demo_pdfs
    from skillgate_ai.engine import SuiteReport, TaskReport
    from skillgate_ai.gate import run_check
    from skillgate_ai.judge import SkipJudge

    dest = tmp_path / "pdf"
    shutil.copytree(Path(__file__).resolve().parents[1] / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")

    class _Harness:
        name = "claude"

    def fake_run_eval(*args: object, **kwargs: object) -> SuiteReport:
        del args, kwargs
        return SuiteReport(
            suite="pdf",
            title="t",
            skill="pdf",
            harness="claude",
            sandbox="local",
            passed=True,
            tasks=[
                TaskReport(
                    task_id="extract-hello",
                    prompt="p",
                    expect_skill="pdf",
                    passed=True,
                    scores=[],
                    selected_skill="pdf",
                    model="claude-sonnet-5-5",
                )
            ],
            skill_path=str(dest),
            pack_fingerprint="fp-v7",
            pack_case_ids=("extract-hello",),
        )

    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr("skillgate_ai.gate.live_harness_or_error", lambda *a, **k: _Harness())
    monkeypatch.setattr("skillgate_ai.gate.resolve_judge", lambda *a, **k: SkipJudge())
    monkeypatch.setattr("skillgate_ai.gate.run_eval", fake_run_eval)
    result = run_check(
        dest, harness="claude", model="sonnet", source="test", root=tmp_path
    )
    assert result.report is not None
    assert result.report.config is not None
    assert result.report.config["model"] == "claude-sonnet-5-5"
    assert result.report.config["requested_model"] == "sonnet"


def test_with_model_promotes_stamped_alias_when_requested_missing() -> None:
    run = EvalRunConfig(harness="claude", model="sonnet")
    updated = with_model(run, "claude-sonnet-5-5")
    assert updated.model == "claude-sonnet-5-5"
    assert updated.requested_model == "sonnet"


def test_models_compare_json_includes_resolved_model_per_arm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = tmp_path / "pdf"
    src = Path(__file__).resolve().parents[1] / "skills" / "pdf"
    import shutil

    shutil.copytree(src, pack)
    from skillgate_ai.demo_files import ensure_demo_pdfs

    ensure_demo_pdfs(pack / "evals" / "fixtures")

    def fake_run_check(target, **kwargs):
        from skillgate_ai.engine import SuiteReport, TaskReport
        from skillgate_ai.gate import CheckResult

        del target
        model = "claude-sonnet-5-5" if kwargs.get("model") == "sonnet" else "claude-opus-5-5"
        requested = kwargs.get("model")
        report = SuiteReport(
            suite="pdf",
            title="t",
            skill="pdf",
            skill_description="d",
            harness="claude",
            sandbox="local",
            passed=True,
            tasks=[
                TaskReport(
                    task_id="extract-hello",
                    prompt="p",
                    expect_skill="pdf",
                    passed=True,
                    scores=[],
                    selected_skill="pdf",
                    model=model,
                )
            ],
            skill_path=str(pack),
            pack_fingerprint="fp-v7",
            pack_case_ids=("extract-hello",),
            config={
                "harness": "claude",
                "model": model,
                "requested_model": requested,
            },
        )
        return CheckResult(report=report, exit_code=0, run_id=kwargs.get("run_id") or "r1")

    monkeypatch.setattr("skillgate_ai.compare.run_check", fake_run_check)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = run_models_compare(
        pack,
        arms=[
            parse_arm_spec("A:claude:sonnet", arm_id="a", index=0),
            parse_arm_spec("B:claude:opus", arm_id="b", index=1),
        ],
        root=tmp_path,
        max_spend_usd=5.0,
    )
    assert result.payload["arms"][0]["model"] == "claude-sonnet-5-5"
    assert result.payload["arms"][1]["model"] == "claude-opus-5-5"
    customer = scrub_customer_compare_payload(result.payload)
    assert customer["arms"][0]["model"] == "claude-sonnet-5-5"
    assert customer["arms"][1]["model"] == "claude-opus-5-5"


def test_scrub_compare_keeps_resolved_arm_model() -> None:
    raw = {
        "compare_id": "c1",
        "arms": [
            {
                "arm_id": "a",
                "label": "Arm A",
                "model": "claude-sonnet-5-5",
                "requested_model": "sonnet",
                "config": {
                    "harness": "claude",
                    "model": "claude-sonnet-5-5",
                    "judge": {"provider": "openai", "model": "gpt-secret"},
                },
            }
        ],
        "cases": [],
    }
    scrubbed = scrub_compare_payload(raw)
    assert scrubbed["arms"][0]["model"] == "claude-sonnet-5-5"
    assert scrubbed["arms"][0].get("requested_model") == "sonnet"
    assert scrubbed["arms"][0]["config"].get("model") is None
    customer = scrub_customer_compare_payload(raw)
    assert customer["arms"][0]["model"] == "claude-sonnet-5-5"
    assert "gpt-secret" not in json.dumps(customer)


def test_compatible_ping_falls_back_to_responses() -> None:
    calls: list[str] = []

    def post(url, headers=None, json=None, timeout=None):
        del headers, json, timeout
        calls.append(url)
        if url.endswith("/decisions"):
            return FakeResponse(404, {"error": {"message": "missing"}})
        return FakeResponse(200, {"id": "resp_ok", "model": "compat"})

    backend = CompatibleBackend(
        api_key="gw-key",
        base_url="https://openrouter.ai/api/v1",
        post=post,
    )
    result = backend.ping()
    assert result["ok"] is True
    assert any(url.endswith("/decisions") for url in calls)
    assert any("/responses" in url for url in calls)


def test_compatible_404_fallback_does_not_warn_http_404(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from skillgate_ai.judge_openai import OutcomeJudge
    from skillgate_ai.judge_spec import resolve_judge_spec

    answers = json.dumps(
        {
            "task_completion": "Fully completed",
            "correctness": "Correct",
            "instruction_adherence": "Fully followed",
            "evidence_action_validity": "Fully supported",
            "result_quality": "Clear and complete",
            "path_efficiency": "Efficient",
        }
    )

    def post(url, headers=None, json=None, timeout=None):
        del headers, json, timeout
        if url.endswith("/decisions"):
            return FakeResponse(404, {"error": {"message": "missing"}})
        return FakeResponse(200, {"output_text": answers, "model": "compat"})

    backend = CompatibleBackend(
        api_key="gw-key",
        base_url="https://openrouter.ai/api/v1",
        post=post,
    )
    with caplog.at_level(logging.WARNING):
        judged = OutcomeJudge(
            backend,
            display_name="Other",
            provider="compatible",
            chosen=True,
            supports_why=True,
            supports_confidence=False,
        ).judge(
            "goal",
            [],
            "tail",
            spec=resolve_judge_spec(),
            path={"had_path": True, "steps": 1},
        )
    assert judged["status"] == "completed"
    assert "scoring HTTP 404" not in caplog.text


def test_contains_golden_is_substring_in_judge_prompt(tmp_path: Path) -> None:
    skill = tmp_path / "memo"
    (skill / "evals" / "goldens").mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: memo\n---\n", encoding="utf-8")
    golden = _persist_golden(
        skill,
        case_id="hello",
        output_path="output/letter.html",
        golden_path=None,
        contains_list=["Dear hiring manager"],
    )
    state = golden_state(golden, skill, contains=["Dear hiring manager"])
    assert state is not None
    assert state["match"] == "contains"
    assert state["contains"] == ["Dear hiring manager"]
    payload = json.loads(
        _state_text(
            {
                "check_prompt": "Write a cover letter",
                "golden": state,
                "actual_output": {
                    "path": "output/letter.html",
                    "body": "<html><body>Dear hiring manager, I am writing...</body></html>",
                },
            }
        )
    )
    golden_blob = json.dumps(payload["golden"]).lower()
    assert payload["golden"]["match"] == "contains"
    assert "substring" in golden_blob or "must include" in golden_blob


def test_sandbox_env_strips_skillgate_secret_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SKILLGATE_AI_GATEWAY_API_KEY", "gw-secret")
    monkeypatch.setenv("SKILLGATE_OPENAI_API_KEY", "sk-prefix-secret")
    monkeypatch.setenv("SKILLGATE_AWS_SECRET_ACCESS_KEY", "aws-prefix-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-bare-secret")
    monkeypatch.setenv("JEV_API_KEY", "jev-bare")
    monkeypatch.setenv("SKILLGATE_MODE", "local")
    env = _sandbox_env(None)
    assert "SKILLGATE_AI_GATEWAY_API_KEY" not in env
    assert "SKILLGATE_OPENAI_API_KEY" not in env
    assert "SKILLGATE_AWS_SECRET_ACCESS_KEY" not in env
    assert "OPENAI_API_KEY" not in env
    assert "JEV_API_KEY" not in env
    assert env.get("SKILLGATE_MODE") == "local"
    assert Path(env["HOME"]) == tmp_path / "home"


def test_saved_artifact_body_is_not_capped_at_8kb(tmp_path: Path) -> None:
    html = "<html>" + ("x" * 12_000) + "</html>"
    dest = tmp_path / "output" / "report.html"
    dest.parent.mkdir(parents=True)
    dest.write_text(html, encoding="utf-8")
    rows = collect_workspace_outputs(
        TaskSpec(id="t1", prompt="write html", expect_skill="web", scorers=[]),
        tmp_path,
    )
    row = next(item for item in rows if item["path"] == "output/report.html")
    assert row["body"] == html
    assert len(row["body"]) > 8000


def test_judge_and_golden_reads_stay_capped(tmp_path: Path) -> None:
    blob = "y" * 12_000
    dest = tmp_path / "evals" / "goldens" / "big.txt"
    dest.parent.mkdir(parents=True)
    dest.write_text(blob, encoding="utf-8")
    capped = read_capped_text(dest)
    assert capped is not None
    assert len(capped) == GOLDEN_TAIL_CHARS
    from skillgate_ai.judge_context import workspace_files_for_judge

    rows = workspace_files_for_judge(
        [{"path": "output/a.html", "present": True, "body": "z" * 10_000}]
    )
    assert len(rows[0]["content"]) <= 6000
