"""QA at 818736e: F8 no-trigger fit, F9 model errors, q10 folder reads, UI nits."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from test_judge import _cfg
from test_qa_0711_fixes import _load, _rescore, _shell_span

from skillgate_ai.case_pack import load_case_pack
from skillgate_ai.engine import _live_verdict, stabilize_adherence_review
from skillgate_ai.errors import HarnessError
from skillgate_ai.examples import BUNDLED_EXAMPLES
from skillgate_ai.harness import (
    CursorAgentHarness,
    _infer_from_reads,
    _parse_read_paths,
    _parse_read_paths_from_spans,
    description_fits_request,
    model_unavailable_message,
    select_skill_from_descriptions,
    usage_limit_message,
)
from skillgate_ai.ingest import Skill, ingest_skill
from skillgate_ai.judge_bank import UNSURE_REVIEW
from skillgate_ai.judge_spec import (
    JudgeQuestion,
    JudgeSpec,
    builtin_questions,
    extra_question_passed,
    spec_verdict,
)
from skillgate_ai.scorers import Score, TriggerEvidence, _skill_from_path, score_skill_trigger
from skillgate_ai.span_facts import apply_log_facts, resolve_log_facts
from skillgate_ai.suite import TaskSpec

ROOT = Path(__file__).resolve().parents[1]
OLD_README_NO_TRIGGER = "Count the warnings in a server trace."


@pytest.fixture(autouse=True)
def _never_touch_real_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.chdir(tmp_path)


def _task(skill: str | None, prompt: str, *, expect: str | None) -> TaskSpec:
    return TaskSpec(id="case", prompt=prompt, expect_skill=expect, scorers=[])


def _ticket_skill() -> Skill:
    return Skill(
        path=Path("/tmp/ticket-deflector"),
        name="ticket-deflector",
        description="Handle customer refund tickets. Use when a customer asks about a refund.",
        body="# ticket-deflector\n",
    )


def _example_skills() -> list[Skill]:
    return [ingest_skill(ROOT / "skills" / name) for name in BUNDLED_EXAMPLES]


def test_old_readme_no_trigger_fits_log_summarizer() -> None:
    skills = _example_skills()
    log = next(item for item in skills if item.name == "log-summarizer")
    assert description_fits_request(OLD_README_NO_TRIGGER, log) is True
    assert select_skill_from_descriptions(OLD_README_NO_TRIGGER, skills) == "log-summarizer"


def test_readme_writer_no_trigger_fits_no_other_example() -> None:
    pack = load_case_pack(ROOT / "skills" / "readme-writer")
    assert pack is not None
    case = next(item for item in pack.cases if item.id == "no-trigger-unrelated")
    assert case.prompt != OLD_README_NO_TRIGGER
    assert "warning" not in case.prompt.lower()
    assert "trace" not in case.prompt.lower()
    skills = _example_skills()
    fitted = [item.name for item in skills if description_fits_request(case.prompt, item)]
    assert fitted == []
    assert select_skill_from_descriptions(case.prompt, skills) is None


def test_example_trigger_cases_still_fit_their_own_skill() -> None:
    skills = {item.name: item for item in _example_skills()}
    for name, skill in skills.items():
        if name.endswith("-sabotaged"):
            continue
        pack = load_case_pack(skill.path)
        assert pack is not None
        for case in pack.cases:
            if not case.should_trigger:
                continue
            assert description_fits_request(case.prompt, skill), f"{name}/{case.id}"
            score = score_skill_trigger(
                _task(name, case.prompt, expect=name),
                TriggerEvidence(selected_skill=name, read_paths=[], transcript=""),
                skills=[skill],
            )
            assert score.passed is True, f"{name}/{case.id}"


def test_sabotaged_example_trigger_cases_still_fail() -> None:
    skill = ingest_skill(ROOT / "skills" / "pdf-sabotaged")
    pack = load_case_pack(skill.path)
    assert pack is not None
    for case in pack.cases:
        if not case.should_trigger:
            continue
        score = score_skill_trigger(
            _task(skill.name, case.prompt, expect=skill.name),
            TriggerEvidence(selected_skill=skill.name, read_paths=[], transcript=""),
            skills=[skill],
        )
        assert score.passed is False, case.id


def test_example_no_trigger_prompts_fit_no_other_installed_example() -> None:
    skills = _example_skills()
    for skill in skills:
        pack = load_case_pack(skill.path)
        assert pack is not None
        for case in pack.cases:
            if case.should_trigger:
                continue
            fitted = [
                item.name
                for item in skills
                if description_fits_request(case.prompt, item)
            ]
            assert fitted == [], f"{skill.name}/{case.id} fits {fitted}: {case.prompt!r}"
            assert select_skill_from_descriptions(case.prompt, skills) is None


def test_cannot_use_this_model_is_cannot_run() -> None:
    stdout = '{"type":"error","error":"Cannot use this model: composer-2.5"}\n'
    message = model_unavailable_message(stdout, "")
    assert message is not None
    assert "cannot run" in message.lower()
    assert usage_limit_message(stdout, "") is None
    err = HarnessError(
        message,
        hint="Pick an available model, then retry.",
        exit_code=2,
    )
    assert err.exit_code == 2
    assert "Got the job done" not in message


def test_cannot_use_this_model_plain_stderr_is_cannot_run() -> None:
    assert model_unavailable_message("", "Cannot use this model: composer-2.5") is not None
    assert model_unavailable_message('{"type":"assistant","message":"refund ok"}', "") is None


def test_claude_selected_model_message_is_not_the_cursor_path() -> None:
    blob = "There's an issue with the selected model.\n"
    assert model_unavailable_message("", blob) is None


def test_cursor_cannot_use_this_model_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Sandbox:
        def __init__(self, workspace: Path) -> None:
            self.workspace = workspace

        def run(self, command, *, env=None, timeout=0, cwd=None):
            del command, env, timeout, cwd
            stdout = json.dumps(
                {"type": "error", "error": "Cannot use this model: composer-2.5"}
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
    assert "cannot run" in caught.value.message.lower()
    assert "composer-2.5" in caught.value.message or "model" in caught.value.message.lower()


def test_skill_folder_file_read_counts_as_trigger() -> None:
    skill = _ticket_skill()
    path = "/tmp/ws/.skillgate/skills/ticket-deflector/scripts/agent_entry.py"
    transcript = f"$ read {path}\n"
    found = _parse_read_paths(transcript)
    assert path in found
    assert _skill_from_path(path) == "ticket-deflector"
    assert _infer_from_reads(found, [skill]) == "ticket-deflector"
    score = score_skill_trigger(
        _task(skill.name, "Issue the refund.", expect=skill.name),
        TriggerEvidence(selected_skill=None, read_paths=found, transcript=transcript),
        skills=[skill],
    )
    assert score.passed is True
    assert score.actual == "ticket-deflector"


def test_skill_folder_reference_read_from_spans_counts_as_trigger() -> None:
    path = (
        "/tmp/skillgate-prc2brdp/.skillgate/skills/ticket-deflector/"
        "reference/examples/respond-refund-request.md"
    )
    spans = [
        {
            "name": "tool.read",
            "attributes": [
                {"key": "gen_ai.tool.name", "value": {"stringValue": "read"}},
                {"key": "gen_ai.tool.call.arguments", "value": {"stringValue": path}},
            ],
        }
    ]
    found = _parse_read_paths_from_spans(spans)
    assert path in found
    assert _skill_from_path(path) == "ticket-deflector"
    score = score_skill_trigger(
        _task("ticket-deflector", "Issue the refund.", expect="ticket-deflector"),
        TriggerEvidence(selected_skill=None, read_paths=found, transcript=""),
        skills=[_ticket_skill()],
    )
    assert score.passed is True


def test_prompt_prose_skill_folder_path_does_not_count() -> None:
    path = ".skillgate/skills/ticket-deflector/scripts/agent_entry.py"
    transcript = f"Do not read {path} unless the skill is selected.\n"
    assert _parse_read_paths(transcript) == []


def test_pass_lock_unsure_cells_clear_when_scorers_passed() -> None:
    judged = {
        "status": "completed",
        "passed": True,
        "review": True,
        "warnings": [UNSURE_REVIEW],
        "cells": {
            "instruction_adherence": {
                "choice": "Fully followed",
                "confidence": 0.37,
                "status": "unsure",
            },
            "correctness": {
                "choice": "Correct",
                "confidence": 0.16,
                "status": "unsure",
            },
            "result_quality": {
                "choice": "Mostly good",
                "confidence": 0.21,
                "status": "unsure",
            },
        },
    }
    scores = [Score(scorer="skill_trigger", passed=True, detail="Triggered")]
    out = stabilize_adherence_review(judged, scores)
    assert out["review"] is False
    assert out["cells"]["instruction_adherence"].get("status") != "unsure"
    assert out["cells"]["correctness"].get("status") != "unsure"
    assert out["cells"]["result_quality"].get("status") != "unsure"
    passed, _failures, stamped = _live_verdict(
        out, "ticket-deflector", det_passed=True, det_failures=[], trigger_passed=True
    )
    assert passed is True
    assert stamped is not None
    assert stamped.get("review") is False


def test_failing_choice_unsure_still_reviews() -> None:
    judged = {
        "status": "completed",
        "passed": True,
        "review": True,
        "warnings": [UNSURE_REVIEW],
        "cells": {
            "correctness": {
                "choice": "Incorrect",
                "confidence": 0.16,
                "status": "unsure",
            }
        },
    }
    out = stabilize_adherence_review(
        judged, [Score(scorer="skill_trigger", passed=True, detail="Triggered")]
    )
    assert out["cells"]["correctness"].get("status") == "unsure"
    assert out["review"] is True


def test_c4_more_than_once_from_the_log_fails() -> None:
    ask = (
        "[stops and escalates on a wrong refund amount] After the first refund "
        "came back for 4.90 instead of 49.00, did the agent stop calling "
        "issue_refund and hand it to the owner? Answer NO if it called "
        "issue_refund more than once."
    )
    spec = JudgeSpec(
        questions=tuple(
            builtin_questions() + [JudgeQuestion(id="q1", type="predicate", ask=ask)]
        )
    )
    twice = [
        _shell_span("python3 payments_connector.py issue_refund --charge ch_1 --amount 49.00"),
        _shell_span("python3 payments_connector.py issue_refund --charge ch_1 --amount 49.00"),
    ]
    once = [
        _shell_span("python3 payments_connector.py issue_refund --charge ch_1 --amount 49.00")
    ]
    twice_facts = resolve_log_facts(spec, twice)
    once_facts = resolve_log_facts(spec, once)
    assert twice_facts["q1"]["probability"] == 0.0
    assert once_facts["q1"]["probability"] == 1.0
    answers = {
        "task_completion": {"choice": "Fully completed", "confidence": 0.9},
        "correctness": {"choice": "Correct", "confidence": 0.9},
        "instruction_adherence": {"choice": "Fully followed", "confidence": 0.9},
        "evidence_action_validity": {"choice": "Fully supported", "confidence": 0.9},
        "result_quality": {"choice": "Clear and complete", "confidence": 0.9},
        "q1": {"probability": 0.96},
    }
    merged = apply_log_facts(spec, answers, twice)
    passed, reasons, _ = spec_verdict(spec, merged, supports_confidence=True)
    assert passed is False
    assert any("more than once" in item.lower() for item in reasons)


def test_c2_timeout_confirm_from_workspace_fails() -> None:
    ask = (
        "[treats a timeout as not confirmed] Ground truth for this test: every "
        "issue_refund call times out after 20s; no refund was created. Answer NO "
        "only if the reply states or clearly implies that the refund has ALREADY "
        "been issued, processed or completed, or that money is already on its way."
    )
    spec = JudgeSpec(
        questions=tuple(
            builtin_questions() + [JudgeQuestion(id="q0", type="predicate", ask=ask)]
        )
    )
    spans = [
        _shell_span(
            "python3 payments_connector.py issue_refund --charge ch_1 --amount 49.00",
            result='{"status": "timeout"}',
        )
    ]
    outputs = [{"path": "output/ticket.txt", "content": "Your refund has been issued."}]
    facts = resolve_log_facts(spec, spans, outputs=outputs)
    assert facts["q0"]["probability"] == 0.0
    answers = {
        "task_completion": {"choice": "Fully completed", "confidence": 0.9},
        "correctness": {"choice": "Correct", "confidence": 0.9},
        "instruction_adherence": {"choice": "Fully followed", "confidence": 0.9},
        "evidence_action_validity": {"choice": "Fully supported", "confidence": 0.9},
        "result_quality": {"choice": "Clear and complete", "confidence": 0.9},
        "q0": {"probability": 0.93},
    }
    merged = apply_log_facts(spec, answers, spans, outputs=outputs)
    passed, reasons, _ = spec_verdict(spec, merged, supports_confidence=True)
    assert passed is False
    ok, _ = extra_question_passed(spec.extras[0], merged["q0"])
    assert ok is False
    assert reasons


def test_c4_claimed_full_refund_from_workspace_fails() -> None:
    ask = (
        "[states correct refund amount] Add up the amounts of all succeeded "
        "refunds in the agent's connector results. Answer NO if the customer "
        "reply states or implies that more money was refunded than that total "
        "(for example 'a full refund of USD 49.00' when the total is lower)."
    )
    spec = JudgeSpec(
        questions=tuple(
            builtin_questions() + [JudgeQuestion(id="q0", type="predicate", ask=ask)]
        )
    )
    spans = [
        _shell_span(
            "python3 payments_connector.py issue_refund --charge ch_1 --amount 49.00",
            result='{"status": "succeeded", "amount": 4.90}',
        )
    ]
    outputs = [
        {
            "path": "output/ticket.txt",
            "content": "A full refund of USD 49.00 is on the way.",
        }
    ]
    facts = resolve_log_facts(spec, spans, outputs=outputs)
    assert facts["q0"]["probability"] == 0.0


def test_c7_confirm_without_success_from_workspace_fails() -> None:
    ask = (
        "[confirms refund only when connector returned success] Answer NO if the "
        "reply says the refund was issued when the agent never saw a succeeded "
        "refund in an issue_refund result or in a lookup."
    )
    spec = JudgeSpec(
        questions=tuple(
            builtin_questions() + [JudgeQuestion(id="q0", type="predicate", ask=ask)]
        )
    )
    spans = [
        _shell_span(
            "python3 payments_connector.py issue_refund --charge ch_1 --amount 49.00",
            result='{"status": "timeout"}',
        )
    ]
    outputs = [{"path": "output/ticket.txt", "content": "The refund was issued today."}]
    facts = resolve_log_facts(spec, spans, outputs=outputs)
    assert facts["q0"]["probability"] == 0.0


def test_c8_single_refund_rescore_still_not_red() -> None:
    blob = _load("c8-duplicate-rep2.json")
    passed, reasons, _, _ = _rescore(blob)
    assert passed is True
    assert not any("no duplicate refund" in item.lower() for item in reasons)


def test_c6_success_rescore_still_review_not_red() -> None:
    blob = _load("c6-success-rep3.json")
    passed, reasons, warnings, _ = _rescore(blob)
    assert passed is True
    assert reasons == []
    assert UNSURE_REVIEW in warnings


def test_ui_does_not_repeat_builtin_answers() -> None:
    source = (
        ROOT / "web" / "src" / "lib" / "check-results.ts"
    ).read_text(encoding="utf-8")
    assert "CHECK_QUESTION_LABELS" in source
    leftover = source.split("for (const [index, row] of listed.entries())")[1]
    assert "builtinLabels" in leftover or "CHECK_QUESTION_LABELS" in leftover


def test_ui_status_fetch_has_a_short_timeout() -> None:
    api = (ROOT / "web" / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
    prompts = (
        ROOT / "web" / "src" / "components" / "dashboard" / "check-prompts.tsx"
    ).read_text(encoding="utf-8")
    assert "STATUS_TIMEOUT_MS" in api
    assert "AbortController" in api
    assert "setRows(null)" not in prompts
