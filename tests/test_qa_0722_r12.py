"""0.7.14 r12: currency-marked amounts, billing.log, rescore stamps happened."""

from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest
from test_qa_0718_r8 import _pass_lock
from test_qa_0719_r9 import PACK_SRC
from test_qa_56_round6 import _scores
from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.history import append_eval
from skillgate_ai.judge_bank import AMOUNT_MISMATCH_NOTE, HONEST_PENDING_FEWSHOTS
from skillgate_ai.judge_context import attach_adherence_context
from skillgate_ai.judge_spec import builtin_spec, spec_decisions_questions
from skillgate_ai.rescore import find_history_run, rescore_saved_run
from skillgate_ai.run_details import format_run_show
from skillgate_ai.score import score_run
from skillgate_ai.span_facts import amount_mismatch

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "r12"
runner = CliRunner()
STALE_Q0 = "The agent's behavior failed this check: q0 → No. Review the run log below."
AMOUNT_PREFIX = AMOUNT_MISMATCH_NOTE.split("{", 1)[0].strip()


@pytest.fixture(autouse=True)
def _never_touch_real_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.chdir(tmp_path)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _blob(*parts: object) -> str:
    return " ".join(str(item) for item in parts)


def _score(task: dict, judged: dict | None = None) -> dict:
    return score_run(
        spec=builtin_spec(),
        judged=deepcopy(judged if judged is not None else task.get("judge") or {}),
        outputs=task.get("outputs") or [],
        scores=task.get("scores") or _scores(),
        expect_skill=task.get("expect_skill") or "desk",
    )


def _pack_with_row(tmp_path: Path, run_id: str, row: dict) -> Path:
    dest = tmp_path / "desk"
    shutil.copytree(PACK_SRC, dest)
    report = row.get("report") if isinstance(row.get("report"), dict) else {
        "gate": "red" if row.get("passed") is False else "green",
        "passed": row.get("passed"),
        "passed_count": 0 if row.get("passed") is False else 1,
        "task_count": 1,
        "skill": "desk",
        "tasks": [row],
    }
    append_eval(
        dest,
        run_id=run_id,
        passed=row.get("passed") if "passed" in row else report.get("passed"),
        report=report,
    )
    return dest


def test_c5_fixture_has_timestamp_in_guard_log_not_reply() -> None:
    task = _load("c5-retry-ok.json")
    texts = {
        str(item.get("path") or "").split("/")[-1]: str(item.get("content") or "")
        for item in task.get("outputs") or []
    }
    assert "1793530111.51" in texts.get(".guard_events.log", "")
    assert "USD 1793530111.51" not in texts.get("reply.txt", "")
    assert "USD 49.00" in texts.get("reply.txt", "")
    assert '"amount": "49.00"' in texts.get("calls.log", "")


def test_c5_timestamp_is_not_an_amount_mismatch() -> None:
    task = _load("c5-retry-ok.json")
    note = amount_mismatch(task.get("outputs"))
    assert note is None
    out = _score(task, _pass_lock())
    blob = _blob(out.get("extra_failures") or [], out.get("reasons") or [])
    assert "1793530111" not in blob
    assert AMOUNT_PREFIX not in blob
    assert out["passed"] is True
    cells = out.get("cells") or {}
    assert cells.get("correctness", {}).get("choice") == "Correct"
    assert cells.get("instruction_adherence", {}).get("choice") == "Fully followed"


def test_c6_timestamp_is_not_an_amount_mismatch() -> None:
    task = _load("c6-success.json")
    note = amount_mismatch(task.get("outputs"))
    assert note is None
    out = _score(task, _pass_lock())
    blob = _blob(out.get("extra_failures") or [], out.get("reasons") or [])
    assert "1793530124" not in blob
    assert AMOUNT_PREFIX not in blob
    assert out["passed"] is True


def test_c4_timestamp_is_not_the_amount_extra() -> None:
    task = _load("c4-partial.json")
    note = amount_mismatch(task.get("outputs"))
    assert note is None or "1793530093" not in str(note)
    out = _score(task)
    blob = _blob(out.get("extra_failures") or [], out.get("reasons") or [])
    assert "1793530093" not in blob
    assert out["passed"] is False
    cells = out.get("cells") or {}
    assert cells.get("correctness", {}).get("choice") == "Incorrect"


def test_adv_amt_billing_log_reds_copied_4_90_against_49() -> None:
    task = _load("adv-amt.json")
    texts = {
        str(item.get("path") or "").split("/")[-1]: str(item.get("content") or "")
        for item in task.get("outputs") or []
    }
    assert "amount=USD 49.00" in texts.get("billing.log", "")
    assert "USD 4.90" in texts.get("reply.txt", "")
    assert not texts.get("calls.log")
    note = amount_mismatch(task.get("outputs"))
    assert note is not None
    assert "4.90" in note
    assert "49.00" in note
    out = _score(task, _pass_lock())
    assert out["passed"] is False
    blob = _blob(out.get("extra_failures") or [], out.get("reasons") or [])
    assert "4.90" in blob and "49.00" in blob
    assert AMOUNT_PREFIX in blob
    cells = out.get("cells") or {}
    assert cells.get("correctness", {}).get("choice") == "Correct"


def test_c8_rescore_cli_names_violated_not_q0(tmp_path: Path) -> None:
    row = _load("c8-rescore-row.json")
    task = row["report"]["tasks"][0]
    assert task["happened"] == STALE_Q0
    pack = _pack_with_row(tmp_path, "qa-r12-c8", row)
    stored = find_history_run(pack, "qa-r12-c8")
    assert stored is not None
    scored = rescore_saved_run(pack, stored)
    c8 = scored["report"]["tasks"][0]
    happened = str(c8.get("happened") or "")
    assert "Violated" in happened or "Significant issues" in happened
    assert "q0" not in happened
    assert "q0 → No" not in happened
    assert "q0 -> No" not in happened
    compact = format_run_show(scored, detail=False)
    fail_line = next(
        line
        for line in compact.splitlines()
        if "duplicate" in line.lower() or ("fail" in line.lower() and "Violated" in line)
        or ("fail" in line.lower() and "Significant issues" in line)
    )
    assert "Violated" in fail_line or "Significant issues" in fail_line
    assert "q0" not in fail_line
    assert STALE_Q0 not in compact
    result = runner.invoke(app, ["rescore", "qa-r12-c8", "--pack", str(pack)])
    assert result.exit_code == 1
    assert "q0 → No" not in result.stdout
    assert "q0 -> No" not in result.stdout
    json_result = runner.invoke(
        app, ["rescore", "qa-r12-c8", "--pack", str(pack), "--json"]
    )
    payload = json.loads(json_result.stdout[json_result.stdout.find("{") :])
    json_happened = str(payload["report"]["tasks"][0].get("happened") or "")
    assert "Violated" in json_happened or "Significant issues" in json_happened
    assert "q0" not in json_happened


def test_c3_rescore_keeps_significant_issues_without_remap(tmp_path: Path) -> None:
    task = _load("c3-pending.json")
    assert (task.get("judge") or {}).get("cells", {}).get("result_quality", {}).get(
        "choice"
    ) == "Significant issues"
    pack = _pack_with_row(tmp_path, "qa-r12-c3", task)
    scored = rescore_saved_run(pack, find_history_run(pack, "qa-r12-c3"))
    out = scored["report"]["tasks"][0]
    cells = (out.get("judge") or {}).get("cells") or {}
    assert cells.get("result_quality", {}).get("choice") == "Significant issues"
    assert out["passed"] is False
    blob = _blob(out.get("failures") or [], (out.get("judge") or {}).get("reasons") or [])
    assert "Significant issues" in blob


def test_rescore_does_not_call_the_judge(tmp_path: Path) -> None:
    import inspect

    from skillgate_ai import rescore as rescore_mod

    source = inspect.getsource(rescore_mod.rescore_saved_run)
    assert "score_run" in source
    assert "evaluate_live" not in source
    assert "judge_openai" not in source
    assert "attach_adherence_context" not in source
    task = _load("c3-pending.json")
    pack = _pack_with_row(tmp_path, "qa-r12-c3b", task)
    scored = rescore_saved_run(pack, find_history_run(pack, "qa-r12-c3b"))
    assert scored["report"]["tasks"][0]["passed"] is False
    cells = (scored["report"]["tasks"][0].get("judge") or {}).get("cells") or {}
    assert cells.get("result_quality", {}).get("choice") == "Significant issues"


def test_live_judge_prompt_still_has_fewshots_rescore_reuses_cells() -> None:
    questions = attach_adherence_context(
        spec_decisions_questions(builtin_spec(), include_path=True),
        {
            "skill_instructions": "Nowhere in the reply use submitted.",
            "expected_outcome": "Honest pending / not-done reply.",
            "scorer_results": [{"scorer": "skill_trigger", "passed": True}],
        },
    )
    blob = json.dumps(questions).lower() + HONEST_PENDING_FEWSHOTS.lower()
    assert "few-shot" in blob or "example" in blob
    assert "not been submitted yet" in blob or "not submitted yet" in blob
    adherence = next(
        item
        for item in questions
        if isinstance(item, dict) and item.get("name") == "instruction_adherence"
    )
    assert "expected outcome" in str(adherence.get("instructions") or "").lower()
    live = _score(_load("c3-pending.json"))
    assert (live.get("cells") or {}).get("result_quality", {}).get("choice") == "Significant issues"


def test_notyet_stored_violated_stays_red_without_remap() -> None:
    task = _load("notyet.json")
    out = _score(task)
    assert (out.get("cells") or {}).get("instruction_adherence", {}).get("choice") == "Violated"
    assert out["passed"] is False


def test_dupx_guarded_stored_incorrect_stays_red_without_remap() -> None:
    task = _load("c8-guarded.json")
    out = _score(task)
    assert (out.get("cells") or {}).get("correctness", {}).get("choice") == "Incorrect"
    assert out["passed"] is False


def test_c5_rescore_cli_drops_timestamp_extra(tmp_path: Path) -> None:
    row = _load("c5-rescore-row.json")
    pack = _pack_with_row(tmp_path, "qa-r12-c5", row)
    result = runner.invoke(app, ["rescore", "qa-r12-c5", "--pack", str(pack), "--json"])
    payload = json.loads(result.stdout[result.stdout.find("{") :])
    task = payload["report"]["tasks"][0]
    blob = _blob(
        task.get("failures") or [],
        (task.get("judge") or {}).get("extra_failures") or [],
        task.get("happened") or "",
    )
    assert "1793530111" not in blob
    assert task["passed"] is True
    assert result.exit_code == 0
