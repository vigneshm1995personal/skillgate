"""Engine helpers, verdict logic, _run_task, and run_eval (no network)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

import skillgate_ai.engine as engine
from skillgate_ai.case_pack import MISSING_GOLDEN_REASON
from skillgate_ai.errors import HarnessError, SuiteError
from skillgate_ai.harness import HarnessResult
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.judge import SkipJudge
from skillgate_ai.judge_bank import (
    CHECK_CELL_ORDER,
    LOW_CONFIDENCE_WARNING,
    PASS_LOCK,
    UNUSABLE_ANSWER,
    canonical_choice,
)
from skillgate_ai.live import KILL, CheckAborted
from skillgate_ai.sandbox import LocalSandbox
from skillgate_ai.scorers import Score, TriggerEvidence
from skillgate_ai.suite import FileCopy, FileExpect, RubricCheck, ScorerSpec, SuiteSpec, TaskSpec

KILL_FAILURE = engine.KILL_FAILURE
SKIP_FAILURE = engine.SKIP_FAILURE


# --- fixtures and fakes ---


@pytest.fixture
def skill_dir(tmp_path: Path) -> Path:
    d = tmp_path / "skills" / "demo"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Demo skill for engine tests.\n---\n# demo\n",
        encoding="utf-8",
    )
    return d


def _skill(skill_dir: Path):
    return ingest_skill(skill_dir, strict=False)


def _task(id: str, prompt: str | None = None, expect: str = "demo", **kw: Any) -> TaskSpec:
    scorers = kw.pop("scorers", None)
    if scorers is None:
        scorers = [ScorerSpec(type="skill_trigger")]
    return TaskSpec(
        id=id,
        prompt=prompt or f"do {id}",
        expect_skill=expect,
        scorers=scorers,
        **kw,
    )


def _spec(*tasks: TaskSpec, timeout: int = 10) -> SuiteSpec:
    task_list = list(tasks) if tasks else [_task("_")]
    return SuiteSpec(suite="s", skill="demo", timeout_sec=timeout, tasks=task_list)


@pytest.fixture
def allow_trigger(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let short harness prompts satisfy skill_trigger overlap checks."""

    def _always_fits(prompt: str, skill: Any) -> bool:
        del prompt, skill
        return True

    monkeypatch.setattr("skillgate_ai.harness.description_fits_request", _always_fits)


def _rep(passed: bool | None, id: str = "t") -> engine.TaskReport:
    return engine.TaskReport(
        task_id=id,
        prompt="p",
        expect_skill=None,
        passed=passed,
        scores=[],
        selected_skill=None,
    )


class FakeHarness:
    name = "fake"
    supported_models = ()

    def __init__(
        self,
        name: str = "fake",
        picks: dict[str, str | None] | None = None,
        raises: BaseException | None = None,
        stderr: str = "",
        transcript: str = "t",
        on_run: Any = None,
    ) -> None:
        self.name = name
        self.picks = picks or {}
        self.raises = raises
        self.stderr = stderr
        self.transcript = transcript
        self.on_run = on_run
        self.calls: list[str] = []

    def run(self, sandbox: Any, prompt: str, skills: Any, timeout_sec: Any) -> HarnessResult:
        del sandbox, skills, timeout_sec
        self.calls.append(prompt)
        if self.raises is not None:
            raise self.raises
        if self.on_run is not None:
            self.on_run()
        pick = self.picks.get(prompt, "demo")
        return HarnessResult(
            trigger=TriggerEvidence(selected_skill=pick),
            stderr=self.stderr,
            transcript=self.transcript,
        )


class RecordingJudge:
    name = "openai"

    def __init__(self, verdict: dict[str, Any], why: str = "because") -> None:
        self.verdict = dict(verdict)
        self.why = why
        self.judge_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.why_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def judge(self, *a: Any, **k: Any) -> dict[str, Any]:
        self.judge_calls.append((a, k))
        return dict(self.verdict)

    def explain_fail(self, *a: Any, **k: Any) -> str:
        self.why_calls.append((a, k))
        return self.why


class ExplodingJudge:
    name = "openai"

    def judge(self, *a: Any, **k: Any) -> dict[str, Any]:
        del a, k
        raise AssertionError("judge must not run")

    def explain_fail(self, *a: Any, **k: Any) -> str:
        del a, k
        raise AssertionError("explain must not run")


class FakeControl:
    def __init__(self, kill_after_end: int | None = None) -> None:
        self.kill_requested = False
        self.skip_requested = False
        self.begun: list[str] = []
        self.ended = 0
        self.kill_after_end = kill_after_end

    def begin_task(self, id: str, prompt: str) -> None:
        del prompt
        self.begun.append(id)

    def end_task(self) -> None:
        self.ended += 1
        if self.kill_after_end is not None and self.ended == self.kill_after_end:
            self.kill_requested = True

    def note_usage(self, u: Any) -> None:
        del u

    def usage_dict(self) -> None:
        return None


class RecordingSandbox:
    def __init__(self, inner: LocalSandbox) -> None:
        self._inner = inner
        self.closed = False

    @property
    def workspace(self) -> Path:
        return self._inner.workspace

    @property
    def output_sink(self) -> Any:
        return self._inner.output_sink

    @output_sink.setter
    def output_sink(self, value: Any) -> None:
        self._inner.output_sink = value

    def run(self, *a: Any, **k: Any) -> Any:
        return self._inner.run(*a, **k)

    def close(self) -> None:
        self.closed = True
        self._inner.close()


# --- pure helpers ---


def test_suite_passed_false_beats_none() -> None:
    assert engine._suite_passed([_rep(True), _rep(None), _rep(False)]) is False


def test_suite_passed_none_when_any_unscored() -> None:
    assert engine._suite_passed([_rep(True), _rep(None)]) is None


def test_suite_passed_true_when_all_pass() -> None:
    assert engine._suite_passed([_rep(True), _rep(True)]) is True
    assert engine._suite_passed([]) is True


def test_task_timeout_override_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLGATE_TASK_TIMEOUT_SEC", "30")
    task = _task("a", timeout_sec=20)
    spec = _spec(timeout=10)
    assert engine.task_timeout_sec(task, spec, timeout_override=5) == 5


def test_task_timeout_env_beats_task_and_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLGATE_TASK_TIMEOUT_SEC", "30")
    task = _task("a", timeout_sec=20)
    spec = _spec(timeout=10)
    assert engine.task_timeout_sec(task, spec) == 30


@pytest.mark.parametrize("bad", ["", "  ", "abc", "0", "-5"])
def test_task_timeout_env_ignored_when_invalid(monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
    monkeypatch.setenv("SKILLGATE_TASK_TIMEOUT_SEC", bad)
    assert engine.env_task_timeout_sec() is None
    task = _task("a", timeout_sec=20)
    spec = _spec(timeout=10)
    assert engine.task_timeout_sec(task, spec) == 20


def test_task_timeout_task_beats_suite_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SKILLGATE_TASK_TIMEOUT_SEC", raising=False)
    task = _task("a", timeout_sec=20)
    spec = _spec(timeout=10)
    assert engine.task_timeout_sec(task, spec) == 20
    task_default = _task("b", timeout_sec=None)
    assert engine.task_timeout_sec(task_default, spec) == 10


def test_apply_mismatch_noop_without_mismatch() -> None:
    assert engine._apply_mismatch(True, ["a"], None) == (True, ["a"])
    assert engine._apply_mismatch(True, ["a"], "") == (True, ["a"])


def test_apply_mismatch_prepends_once() -> None:
    assert engine._apply_mismatch(True, ["a"], "m") == (False, ["m", "a"])
    assert engine._apply_mismatch(True, ["m"], "m") == (False, ["m"])


def test_resolve_path_absolute_passthrough(tmp_path: Path) -> None:
    abs_p = tmp_path / "abs.txt"
    abs_p.touch()
    root = tmp_path / "root"
    suite = tmp_path / "suite"
    assert engine._resolve_path(root, suite, str(abs_p)) == abs_p


def test_resolve_path_first_existing_base(tmp_path: Path) -> None:
    root = tmp_path / "root"
    suite_dir = tmp_path / "suite"
    root.mkdir()
    suite_dir.mkdir()
    rel = "data/foo.txt"
    only_suite = suite_dir / rel
    only_suite.parent.mkdir(parents=True)
    only_suite.write_text("s", encoding="utf-8")
    assert engine._resolve_path(root, suite_dir, rel) == only_suite.resolve()
    # both exist: root wins
    both_root = root / rel
    both_root.parent.mkdir(parents=True)
    both_root.write_text("r", encoding="utf-8")
    assert engine._resolve_path(root, suite_dir, rel) == both_root.resolve()


def test_resolve_path_falls_back_to_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    suite_dir = tmp_path / "suite"
    root.mkdir()
    suite_dir.mkdir()
    rel = "missing/foo.txt"
    assert engine._resolve_path(root, suite_dir, rel) == (root / rel).resolve()


def test_resolve_pack_stamp_fingerprint_defaults_ids_to_tasks() -> None:
    tasks = [_task("a"), _task("b")]
    spec = _spec(*tasks)
    assert engine._resolve_pack_stamp(None, spec, pack_fingerprint="fp", pack_case_ids=None) == (
        "fp",
        ("a", "b"),
    )
    assert engine._resolve_pack_stamp(None, spec, pack_fingerprint="fp", pack_case_ids=["x"]) == (
        "fp",
        ("x",),
    )


def test_resolve_pack_stamp_none_without_skill_path() -> None:
    spec = _spec(_task("a"))
    assert engine._resolve_pack_stamp(None, spec, pack_fingerprint=None, pack_case_ids=None) == (
        None,
        None,
    )


def test_why_expected_no_trigger_short_name_uppercased() -> None:
    task = _task("x", expect=None)
    assert engine._why_expected_output(task, None, skill_name="pdf") == "No PDF skill triggered"
    assert (
        engine._why_expected_output(task, None, skill_name="longname")
        == "No longname skill triggered"
    )
    assert engine._why_expected_output(task, None, skill_name=None) == "No skill triggered"


def test_why_expected_golden_dict_wins() -> None:
    task = _task("x", expect="demo")
    golden = {"body": "x"}
    assert engine._why_expected_output(task, golden) is golden


def test_why_expected_file_then_check_contains() -> None:
    task_files = _task(
        "f",
        expect="demo",
        scorers=[
            ScorerSpec(
                type="task_completion",
                files=[FileExpect(path="o", contains="F")],
            )
        ],
    )
    assert engine._why_expected_output(task_files, None) == "F"
    task_checks = _task(
        "c",
        expect="demo",
        scorers=[
            ScorerSpec(
                type="rubric",
                checks=[RubricCheck(id="c", contains="C")],
            )
        ],
    )
    assert engine._why_expected_output(task_checks, None) == "C"


def test_why_expected_none_when_nothing_declared() -> None:
    task = _task("x", expect="demo")
    assert engine._why_expected_output(task, None) is None


def test_usage_totals_none_without_usage() -> None:
    report = engine.SuiteReport(
        suite="s",
        title="s",
        skill="demo",
        harness="fake",
        sandbox="local",
        passed=True,
        tasks=[_rep(True)],
    )
    assert report.usage_totals is None


def test_usage_totals_sums_and_rounds_cost() -> None:
    t1 = _rep(True, "t1")
    t1.usage = {"tokens_in": 1, "cost_usd": 0.1234567}
    t2 = _rep(True, "t2")
    t2.usage = {"tokens_in": 2, "cost_usd": 0.1}
    report = engine.SuiteReport(
        suite="s",
        title="s",
        skill="demo",
        harness="fake",
        sandbox="local",
        passed=True,
        tasks=[t1, t2],
    )
    totals = report.usage_totals
    assert totals is not None
    assert totals["tokens_in"] == 3
    assert totals["cost_usd"] == round(0.2234567, 6)
    assert "tokens_out" not in totals


def test_usage_totals_single_label_propagates() -> None:
    t1 = _rep(True, "t1")
    t1.usage = {"tokens_in": 1, "agent_cost_label": "sub"}
    t2 = _rep(True, "t2")
    t2.usage = {"tokens_in": 2, "agent_cost_label": "sub"}
    report = engine.SuiteReport(
        suite="s",
        title="s",
        skill="demo",
        harness="fake",
        sandbox="local",
        passed=True,
        tasks=[t1, t2],
    )
    assert report.usage_totals is not None
    assert report.usage_totals.get("agent_cost_label") == "sub"
    t2.usage = {"tokens_in": 2, "agent_cost_label": "other"}
    report2 = engine.SuiteReport(
        suite="s",
        title="s",
        skill="demo",
        harness="fake",
        sandbox="local",
        passed=True,
        tasks=[t1, t2],
    )
    assert "agent_cost_label" not in (report2.usage_totals or {})


def test_usage_totals_flags_cost_unknown() -> None:
    t = _rep(True)
    t.usage = {"tokens_total": 5}
    report = engine.SuiteReport(
        suite="s",
        title="s",
        skill="demo",
        harness="fake",
        sandbox="local",
        passed=True,
        tasks=[t],
    )
    assert report.usage_totals is not None
    assert report.usage_totals.get("cost_unknown") is True
    t.usage = {"tokens_total": 5, "agent_cost_label": "sub"}
    report2 = engine.SuiteReport(
        suite="s",
        title="s",
        skill="demo",
        harness="fake",
        sandbox="local",
        passed=True,
        tasks=[t],
    )
    assert "cost_unknown" not in (report2.usage_totals or {})


def test_eval_progress_done_running_queued() -> None:
    spec = _spec(_task("t1"), _task("t2"), _task("t3"))
    harness = FakeHarness()
    progress = engine._eval_progress(
        spec=spec,
        skill="demo",
        harness=harness,
        reports=[_rep(True, "t1")],
        pack_case_ids=["a"],
    )
    statuses = [t.status for t in progress.tasks]
    assert statuses == ["done", "running", "queued"]
    assert progress.current_task_id == "t2"
    assert progress.completed_count == 1
    assert progress.task_count == 3
    assert progress.pack_case_ids == ("a",)


def test_eval_progress_forced_running_task() -> None:
    spec = _spec(_task("t1"), _task("t2"), _task("t3"))
    harness = FakeHarness()
    progress = engine._eval_progress(
        spec=spec,
        skill="demo",
        harness=harness,
        reports=[_rep(True, "t1")],
        running_task=_task("t3"),
        running_transcript="tx",
    )
    assert progress.tasks[1].status == "queued"
    assert progress.tasks[2].status == "running"
    assert progress.tasks[2].transcript == "tx"
    assert progress.current_task_id == "t3"


# --- verdict logic ---


def test_live_verdict_trigger_fail_forces_red_and_clears_review() -> None:
    judge = {"passed": True, "review": True}
    passed, failures, stamped = engine._live_verdict(
        judge,
        "demo",
        det_passed=True,
        det_failures=["x"],
        trigger_passed=False,
    )
    assert passed is False
    assert failures == ["x"]
    assert stamped is not None
    assert stamped["passed"] is False
    assert stamped["review"] is False


def test_live_verdict_trigger_fail_default_reason() -> None:
    passed, failures, stamped = engine._live_verdict(
        None,
        "demo",
        det_passed=True,
        det_failures=[],
        trigger_passed=False,
    )
    assert passed is False
    assert failures == ["Did not trigger (description does not match this request)"]
    assert stamped is None


def test_live_verdict_non_dict_judge_keeps_det() -> None:
    passed, failures, stamped = engine._live_verdict(None, "demo", det_passed=True, det_failures=[])
    assert passed is True
    assert failures == []
    assert stamped is None


def test_live_verdict_extra_failures_fail() -> None:
    judge = {"extra_failures": [" e ", ""], "passed": True}
    passed, failures, stamped = engine._live_verdict(
        judge, "demo", det_passed=True, det_failures=[]
    )
    assert passed is False
    assert failures == ["e"]
    assert stamped is not None
    assert stamped["passed"] is False


def test_live_verdict_error_unusable_answer_is_red() -> None:
    judge = {"status": "error", "reason": UNUSABLE_ANSWER}
    passed, failures, stamped = engine._live_verdict(
        judge, "demo", det_passed=True, det_failures=[]
    )
    assert passed is False
    assert failures == [UNUSABLE_ANSWER]
    assert stamped is not None
    assert stamped["passed"] is False
    assert stamped.get("quality_unscored") is True


def test_live_verdict_error_reason_fallback_chain() -> None:
    judge_r2 = {"status": "error", "reasons": ["r2"]}
    passed, failures, stamped = engine._live_verdict(
        judge_r2, "demo", det_passed=True, det_failures=[]
    )
    assert passed is None
    assert failures == ["r2"]
    assert stamped is not None
    judge_bare = {"status": "error"}
    passed2, failures2, _ = engine._live_verdict(
        judge_bare, "demo", det_passed=True, det_failures=[]
    )
    assert passed2 is None
    assert failures2 == ["Quality was not scored."]


def test_live_verdict_judge_pass_overrides_det() -> None:
    judge = {"passed": True, "reasons": []}
    passed, failures, _ = engine._live_verdict(
        judge, "demo", det_passed=False, det_failures=["det"]
    )
    assert passed is True


def test_live_verdict_judge_fail_without_reasons_uses_det_or_default() -> None:
    judge = {"passed": False, "reasons": []}
    passed, failures, _ = engine._live_verdict(judge, "demo", det_passed=False, det_failures=["d"])
    assert failures == ["d"]
    passed2, failures2, _ = engine._live_verdict(judge, "demo", det_passed=True, det_failures=[])
    assert passed2 is False
    assert failures2 == ["The judge couldn't score this check."]


def test_live_verdict_filters_blank_warnings() -> None:
    judge = {"passed": True, "reasons": [], "warnings": ["w", " "]}
    _, _, stamped = engine._live_verdict(judge, "demo", det_passed=True, det_failures=[])
    assert stamped is not None
    assert stamped["warnings"] == ["w"]


def test_stabilize_passthrough_non_dict() -> None:
    assert engine.stabilize_adherence_review(None, []) is None


def test_stabilize_unchanged_when_scorer_failed() -> None:
    judged: dict[str, Any] = {"cells": {"task_completion": {"status": "unsure"}}, "review": True}
    scores = [Score(scorer="skill_trigger", passed=False, detail="nope", headline="fail")]
    assert engine.stabilize_adherence_review(judged, scores) is judged


def test_stabilize_clears_unsure_pass_lock_cell() -> None:
    key = CHECK_CELL_ORDER[0]
    choice = sorted(PASS_LOCK[key])[0]
    assert canonical_choice(key, choice) is not None
    assert canonical_choice(key, choice).strip().lower() in PASS_LOCK[key]
    judged = {
        "cells": {key: {"status": "unsure", "choice": choice}},
        "warnings": [LOW_CONFIDENCE_WARNING],
        "review": True,
        "passed": True,
        "reasons": [],
    }
    scores = [Score(scorer="skill_trigger", passed=True, detail="ok")]
    out = engine.stabilize_adherence_review(judged, scores)
    assert out is not None
    assert "status" not in out["cells"][key]
    assert out["review"] is False
    assert LOW_CONFIDENCE_WARNING not in out["warnings"]


def test_stabilize_keeps_unsure_failing_choice_without_extras() -> None:
    key = CHECK_CELL_ORDER[0]
    judged = {
        "cells": {key: {"status": "unsure", "choice": "zzz-not-a-choice"}},
        "review": True,
    }
    scores = [Score(scorer="skill_trigger", passed=True, detail="ok")]
    assert engine.stabilize_adherence_review(judged, scores) is judged


def test_explain_fail_skipped_when_passed() -> None:
    judged = {"status": "completed", "passed": False}
    recording = RecordingJudge(verdict={"passed": False})
    out = engine._maybe_explain_fail(recording, True, ["x"], judged, check="c", transcript_tail="")
    assert out is judged
    assert recording.why_calls == []


def test_explain_fail_skipped_on_error_or_unscored() -> None:
    recording = RecordingJudge(verdict={})
    err = {"status": "error"}
    assert (
        engine._maybe_explain_fail(recording, False, ["x"], err, check="c", transcript_tail="")
        is err
    )
    unscored = {"quality_unscored": True}
    assert (
        engine._maybe_explain_fail(recording, False, ["x"], unscored, check="c", transcript_tail="")
        is unscored
    )
    assert recording.why_calls == []


def test_explain_fail_attaches_stripped_why() -> None:
    recording = RecordingJudge(verdict={"passed": False}, why="  w  ")
    judged = {"status": "completed", "passed": False}
    out = engine._maybe_explain_fail(recording, False, ["x"], judged, check="c", transcript_tail="")
    assert out is not None
    assert out["why"] == "w"
    assert len(recording.why_calls) == 1
    out2 = engine._maybe_explain_fail(recording, None, ["x"], judged, check="c", transcript_tail="")
    assert out2 is not None
    assert "why" in out2


def test_explain_fail_blank_why_ignored() -> None:
    recording = RecordingJudge(verdict={}, why="  ")
    judged = {"status": "completed", "passed": False}
    out = engine._maybe_explain_fail(recording, False, ["x"], judged, check="c", transcript_tail="")
    assert out is not None
    assert "why" not in out


# --- _run_task ---


def test_run_task_missing_golden_short_circuits(
    tmp_path: Path, skill_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import skillgate_ai.case_pack as case_pack

    monkeypatch.setattr(case_pack, "task_missing_golden", lambda *a, **k: True)
    harness = FakeHarness()
    report = engine._run_task(
        task=_task("a"),
        spec=_spec(_task("a")),
        skills=[_skill(skill_dir)],
        harness=harness,
        sandbox=LocalSandbox(tmp_path / "ws"),
        root=tmp_path,
        suite_dir=tmp_path,
        judge=SkipJudge(),
    )
    assert report.failures == [MISSING_GOLDEN_REASON]
    assert report.passed is False
    assert harness.calls == []


def test_run_task_missing_input_file_raises_suite_error(tmp_path: Path, skill_dir: Path) -> None:
    task = _task(
        "a",
        files=[FileCopy(src="evals/fixtures/nope.pdf", dest="in.pdf")],
    )
    with pytest.raises(SuiteError) as caught:
        engine._run_task(
            task=task,
            spec=_spec(task),
            skills=[_skill(skill_dir)],
            harness=FakeHarness(),
            sandbox=LocalSandbox(tmp_path / "ws"),
            root=tmp_path,
            suite_dir=tmp_path,
            judge=SkipJudge(),
        )
    assert "nope.pdf" in caught.value.message


def test_run_task_golden_input_files_are_skipped(
    tmp_path: Path, skill_dir: Path, allow_trigger: None
) -> None:
    task = _task(
        "a",
        files=[FileCopy(src="evals/goldens/x.txt", dest="x")],
    )
    report = engine._run_task(
        task=task,
        spec=_spec(task),
        skills=[_skill(skill_dir)],
        harness=FakeHarness(),
        sandbox=LocalSandbox(tmp_path / "ws"),
        root=tmp_path,
        suite_dir=tmp_path,
        judge=SkipJudge(),
    )
    assert report.passed is True


@pytest.mark.parametrize(
    ("reason", "expected"),
    [(KILL, KILL_FAILURE), ("skip", SKIP_FAILURE)],
)
def test_run_task_check_aborted_maps_reason(
    tmp_path: Path,
    skill_dir: Path,
    reason: str,
    expected: str,
) -> None:
    report = engine._run_task(
        task=_task("a"),
        spec=_spec(_task("a")),
        skills=[_skill(skill_dir)],
        harness=FakeHarness(raises=CheckAborted(reason)),
        sandbox=LocalSandbox(tmp_path / "ws"),
        root=tmp_path,
        suite_dir=tmp_path,
        judge=SkipJudge(),
    )
    assert report.skipped is True
    assert report.failures == [expected]


def test_run_task_timeout_is_mapped(tmp_path: Path, skill_dir: Path) -> None:
    with pytest.raises(HarnessError):
        engine._run_task(
            task=_task("a"),
            spec=_spec(_task("a")),
            skills=[_skill(skill_dir)],
            harness=FakeHarness(raises=subprocess.TimeoutExpired(["x"], 5)),
            sandbox=LocalSandbox(tmp_path / "ws"),
            root=tmp_path,
            suite_dir=tmp_path,
            judge=SkipJudge(),
        )


def test_run_task_other_exception_reraised_unchanged(tmp_path: Path, skill_dir: Path) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        engine._run_task(
            task=_task("a"),
            spec=_spec(_task("a")),
            skills=[_skill(skill_dir)],
            harness=FakeHarness(raises=RuntimeError("boom")),
            sandbox=LocalSandbox(tmp_path / "ws"),
            root=tmp_path,
            suite_dir=tmp_path,
            judge=SkipJudge(),
        )


@pytest.mark.parametrize(
    ("stderr", "hint"),
    [
        ("Weekly usage limit reached", "Wait until the agent quota resets, then retry."),
        ("Cannot use this model: x", "Pick an available model, then retry."),
    ],
)
def test_run_task_quota_raises_harness_error_exit_2(
    tmp_path: Path,
    skill_dir: Path,
    stderr: str,
    hint: str,
) -> None:
    with pytest.raises(HarnessError) as caught:
        engine._run_task(
            task=_task("a"),
            spec=_spec(_task("a")),
            skills=[_skill(skill_dir)],
            harness=FakeHarness(stderr=stderr),
            sandbox=LocalSandbox(tmp_path / "ws"),
            root=tmp_path,
            suite_dir=tmp_path,
            judge=SkipJudge(),
        )
    assert caught.value.exit_code == 2
    assert caught.value.hint == hint


@pytest.mark.parametrize(
    ("attr", "expected"),
    [("kill_requested", KILL_FAILURE), ("skip_requested", SKIP_FAILURE)],
)
def test_run_task_kill_or_skip_after_run_returns_skipped(
    tmp_path: Path,
    skill_dir: Path,
    attr: str,
    expected: str,
) -> None:
    control = FakeControl()

    def flip() -> None:
        setattr(control, attr, True)

    report = engine._run_task(
        task=_task("a"),
        spec=_spec(_task("a")),
        skills=[_skill(skill_dir)],
        harness=FakeHarness(on_run=flip),
        sandbox=LocalSandbox(tmp_path / "ws"),
        root=tmp_path,
        suite_dir=tmp_path,
        control=control,
        judge=SkipJudge(),
    )
    assert report.failures == [expected]
    assert control.ended == 1


def test_run_task_non_live_harness_is_deterministic(
    tmp_path: Path, skill_dir: Path, allow_trigger: None
) -> None:
    report_ok = engine._run_task(
        task=_task("a"),
        spec=_spec(_task("a")),
        skills=[_skill(skill_dir)],
        harness=FakeHarness(picks={"do a": "demo"}),
        sandbox=LocalSandbox(tmp_path / "ws"),
        root=tmp_path,
        suite_dir=tmp_path,
        judge=ExplodingJudge(),
    )
    assert report_ok.passed is True
    assert report_ok.judge is None
    report_bad = engine._run_task(
        task=_task("b"),
        spec=_spec(_task("b")),
        skills=[_skill(skill_dir)],
        harness=FakeHarness(picks={"do b": "other"}),
        sandbox=LocalSandbox(tmp_path / "ws"),
        root=tmp_path,
        suite_dir=tmp_path,
        judge=ExplodingJudge(),
    )
    assert report_bad.passed is False
    assert report_bad.failures != []


def test_run_task_live_pass_sets_review_from_judge(
    tmp_path: Path, skill_dir: Path, allow_trigger: None
) -> None:
    verdict = {
        "status": "done",
        "passed": True,
        "reasons": [],
        "review": True,
        "cells": {},
    }
    judge = RecordingJudge(verdict)
    report = engine._run_task(
        task=_task("a"),
        spec=_spec(_task("a")),
        skills=[_skill(skill_dir)],
        harness=FakeHarness(name="cursor-agent", picks={"do a": "demo"}),
        sandbox=LocalSandbox(tmp_path / "ws"),
        root=tmp_path,
        suite_dir=tmp_path,
        judge=judge,
    )
    assert report.passed is True
    assert report.review is True
    assert len(judge.judge_calls) == 1
    assert judge.why_calls == []


def test_run_task_live_fail_calls_explain_fail_once(
    tmp_path: Path, skill_dir: Path, allow_trigger: None
) -> None:
    judge = RecordingJudge({"status": "done", "passed": False, "reasons": ["bad"], "cells": {}})
    report = engine._run_task(
        task=_task("a"),
        spec=_spec(_task("a")),
        skills=[_skill(skill_dir)],
        harness=FakeHarness(name="cursor-agent", picks={"do a": "demo"}),
        sandbox=LocalSandbox(tmp_path / "ws"),
        root=tmp_path,
        suite_dir=tmp_path,
        judge=judge,
    )
    assert report.failures == ["bad"]
    assert len(judge.why_calls) == 1
    assert report.judge is not None
    assert report.judge["why"] == "because"


def test_run_task_no_trigger_live_skips_judge(tmp_path: Path, skill_dir: Path) -> None:
    report = engine._run_task(
        task=_task("a", expect=None),
        spec=_spec(_task("a", expect=None)),
        skills=[_skill(skill_dir)],
        harness=FakeHarness(name="cursor-agent", picks={"do a": None}),
        sandbox=LocalSandbox(tmp_path / "ws"),
        root=tmp_path,
        suite_dir=tmp_path,
        judge=ExplodingJudge(),
    )
    assert report.passed is True
    assert report.judge is not None
    assert report.judge["status"] == "skip"


def test_run_task_resets_sink_and_ends_control_on_error(tmp_path: Path, skill_dir: Path) -> None:
    control = FakeControl()
    sandbox = LocalSandbox(tmp_path / "ws")
    with pytest.raises(RuntimeError, match="boom"):
        engine._run_task(
            task=_task("a"),
            spec=_spec(_task("a")),
            skills=[_skill(skill_dir)],
            harness=FakeHarness(raises=RuntimeError("boom")),
            sandbox=sandbox,
            root=tmp_path,
            suite_dir=tmp_path,
            control=control,
            judge=SkipJudge(),
        )
    assert sandbox.output_sink is None
    assert control.ended == 1
    assert control.begun == ["a"]


def test_run_eval_halts_after_transcript_session_limit(
    tmp_path: Path,
    skill_dir: Path,
    allow_trigger: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil

    from skillgate_ai.demo_files import ensure_demo_pdfs
    from skillgate_ai.gate import run_check
    from skillgate_ai.history import load_history

    transcript = "You've hit your session limit · resets at noon"
    harness = FakeHarness(transcript=transcript)
    spec = _spec(_task("t1"), _task("t2"))
    with pytest.raises(HarnessError):
        engine.run_eval(
            harness=harness,
            sandbox_kind="local",
            docker_image="x",
            project_root=tmp_path,
            skill_override=str(skill_dir),
            spec=spec,
            judge=SkipJudge(),
            strict_ingest=False,
        )
    assert len(harness.calls) == 1

    pack = tmp_path / "pdf"
    shutil.copytree(Path(__file__).resolve().parents[1] / "skills" / "pdf", pack)
    ensure_demo_pdfs(pack / "evals" / "fixtures")
    gate_harness = FakeHarness(transcript=transcript)
    monkeypatch.setattr("skillgate_ai.harness.auth._cursor_ready", lambda _c: True)
    monkeypatch.setattr(
        "skillgate_ai.gate.live_harness_or_error", lambda *a, **k: gate_harness
    )
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = run_check(pack, source="cli", root=tmp_path, harness="cursor-agent", no_judge=True)
    assert result.exit_code == 2, result.error
    assert len(gate_harness.calls) == 1
    row = load_history(pack, limit=1)[-1]
    assert row["passed"] is None
    assert row.get("gate") is None


def test_run_task_harness_error_propagates(tmp_path: Path, skill_dir: Path) -> None:
    report = engine._run_task(
        task=_task("a"),
        spec=_spec(_task("a")),
        skills=[_skill(skill_dir)],
        harness=FakeHarness(),
        sandbox=LocalSandbox(tmp_path / "ws"),
        root=tmp_path,
        suite_dir=tmp_path,
        judge=SkipJudge(),
    )
    assert report.task_id == "a"
    with pytest.raises(RuntimeError, match="boom"):
        engine._run_task(
            task=_task("b"),
            spec=_spec(_task("b")),
            skills=[_skill(skill_dir)],
            harness=FakeHarness(raises=RuntimeError("boom")),
            sandbox=LocalSandbox(tmp_path / "ws"),
            root=tmp_path,
            suite_dir=tmp_path,
            judge=SkipJudge(),
        )


# --- run_eval ---


def test_run_eval_requires_suite_or_spec(tmp_path: Path) -> None:
    with pytest.raises(SuiteError) as caught:
        engine.run_eval(
            harness=FakeHarness(),
            sandbox_kind="local",
            docker_image="x",
            project_root=tmp_path,
            judge=SkipJudge(),
            strict_ingest=False,
        )
    assert "No eval suite given." in caught.value.message


def test_run_eval_red_when_any_task_fails(
    tmp_path: Path, skill_dir: Path, allow_trigger: None
) -> None:
    spec = _spec(_task("t1"), _task("t2"))
    r = engine.run_eval(
        harness=FakeHarness(picks={"do t2": "other"}),
        sandbox_kind="local",
        docker_image="x",
        project_root=tmp_path,
        skill_override=str(skill_dir),
        spec=spec,
        judge=SkipJudge(),
        strict_ingest=False,
    )
    assert r.passed is False
    assert [t.passed for t in r.tasks] == [True, False]


def test_run_eval_green_when_all_pass(tmp_path: Path, skill_dir: Path, allow_trigger: None) -> None:
    spec = _spec(_task("t1"), _task("t2"))
    r = engine.run_eval(
        harness=FakeHarness(),
        sandbox_kind="local",
        docker_image="x",
        project_root=tmp_path,
        skill_override=str(skill_dir),
        spec=spec,
        judge=SkipJudge(),
        strict_ingest=False,
    )
    assert r.passed is True
    assert r.incomplete is False
    assert r.timeout_effective == 10


def test_run_eval_max_tasks_slices(tmp_path: Path, skill_dir: Path, allow_trigger: None) -> None:
    spec = _spec(_task("t1"), _task("t2"), _task("t3"))
    r = engine.run_eval(
        harness=FakeHarness(),
        sandbox_kind="local",
        docker_image="x",
        project_root=tmp_path,
        skill_override=str(skill_dir),
        spec=spec,
        max_tasks=1,
        judge=SkipJudge(),
        strict_ingest=False,
    )
    assert r.incomplete is True
    assert r.next_task_index == 1
    assert r.passed is False
    assert r.advice is None
    assert len(r.tasks) == 1


def test_run_eval_start_index_keeps_prior_reports(
    tmp_path: Path, skill_dir: Path, allow_trigger: None
) -> None:
    spec = _spec(_task("t1"), _task("t2"), _task("t3"))
    harness = FakeHarness()
    r = engine.run_eval(
        harness=harness,
        sandbox_kind="local",
        docker_image="x",
        project_root=tmp_path,
        skill_override=str(skill_dir),
        spec=spec,
        start_index=1,
        prior_reports=[_rep(True, "t1")],
        judge=SkipJudge(),
        strict_ingest=False,
    )
    assert [t.task_id for t in r.tasks] == ["t1", "t2", "t3"]
    assert harness.calls == ["do t2", "do t3"]


def test_run_eval_kill_marks_remaining_skipped_in_order(
    tmp_path: Path, skill_dir: Path, allow_trigger: None
) -> None:
    spec = _spec(_task("t1"), _task("t2"), _task("t3"))
    control = FakeControl(kill_after_end=1)
    r = engine.run_eval(
        harness=FakeHarness(),
        sandbox_kind="local",
        docker_image="x",
        project_root=tmp_path,
        skill_override=str(skill_dir),
        spec=spec,
        control=control,
        judge=SkipJudge(),
        strict_ingest=False,
    )
    assert [t.task_id for t in r.tasks] == ["t1", "t2", "t3"]
    assert r.tasks[0].skipped is False
    for task in r.tasks[1:]:
        assert task.skipped is True
        assert task.failures == [KILL_FAILURE]


def test_run_eval_emits_progress_once_plus_per_task(
    tmp_path: Path, skill_dir: Path, allow_trigger: None
) -> None:
    events: list[engine.EvalProgress] = []

    def on_progress(ev: engine.EvalProgress) -> None:
        events.append(ev)

    spec = _spec(_task("t1"), _task("t2"))
    engine.run_eval(
        harness=FakeHarness(),
        sandbox_kind="local",
        docker_image="x",
        project_root=tmp_path,
        skill_override=str(skill_dir),
        spec=spec,
        on_progress=on_progress,
        judge=SkipJudge(),
        strict_ingest=False,
    )
    assert len(events) == 3
    assert [e.completed_count for e in events] == [0, 1, 2]


def test_run_eval_closes_sandbox_even_when_task_raises(
    tmp_path: Path, skill_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    boxed: list[RecordingSandbox] = []

    def open_rec(kind: str, image: str) -> RecordingSandbox:
        del kind, image
        sb = RecordingSandbox(LocalSandbox(tmp_path / "ws"))
        boxed.append(sb)
        return sb

    monkeypatch.setattr("skillgate_ai.engine.run.open_sandbox", open_rec)
    spec = _spec(_task("t1"))
    with pytest.raises(RuntimeError, match="boom"):
        engine.run_eval(
            harness=FakeHarness(raises=RuntimeError("boom")),
            sandbox_kind="local",
            docker_image="x",
            project_root=tmp_path,
            skill_override=str(skill_dir),
            spec=spec,
            judge=SkipJudge(),
            strict_ingest=False,
        )
    assert boxed and boxed[0].closed is True


def test_run_eval_explicit_fingerprint_stamped(
    tmp_path: Path, skill_dir: Path, allow_trigger: None
) -> None:
    spec = _spec(_task("t1"), _task("t2"))
    r = engine.run_eval(
        harness=FakeHarness(),
        sandbox_kind="local",
        docker_image="x",
        project_root=tmp_path,
        skill_override=str(skill_dir),
        spec=spec,
        pack_fingerprint="fp",
        judge=SkipJudge(),
        strict_ingest=False,
    )
    assert r.pack_fingerprint == "fp"
    assert r.pack_case_ids == ("t1", "t2")
