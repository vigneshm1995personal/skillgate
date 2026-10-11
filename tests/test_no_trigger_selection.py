"""No-trigger checks must not pin a skill; the model chooses from the catalog."""

from __future__ import annotations

import json
from pathlib import Path

from skillgate_ai.case_pack import load_case_pack, suite_from_pack
from skillgate_ai.engine import SuiteReport, _run_task, _seed_skill_selection, _why_expected_output
from skillgate_ai.harness import Completion, HarnessResult, LLMHarness, _read_selection, _MISSING
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.report import report_to_dict
from skillgate_ai.sandbox import LocalSandbox
from skillgate_ai.scorers import RunArtifacts, TriggerEvidence, score_task
from skillgate_ai.suite import ScorerSpec, TaskSpec
from skillgate_ai.usage import Usage
from test_judge import _cfg

PDF_PACK = Path(__file__).resolve().parents[1] / "skills" / "pdf"


def test_no_trigger_does_not_write_selected_json(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    gate = workspace / ".skillgate"
    gate.mkdir()
    (gate / "selected.json").write_text('{"skill": "pdf"}', encoding="utf-8")
    _seed_skill_selection(workspace, None)
    assert not (gate / "selected.json").is_file()
    assert _read_selection(workspace) is _MISSING


def test_trigger_still_pins_selected_json(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _seed_skill_selection(workspace, "pdf")
    data = json.loads((workspace / ".skillgate" / "selected.json").read_text(encoding="utf-8"))
    assert data == {"skill": "pdf"}


def test_llm_harness_discovers_from_catalog_when_nothing_is_pinned(
    monkeypatch, tmp_path: Path
) -> None:
    pack = tmp_path / "pdf"
    import shutil

    shutil.copytree(Path(__file__).resolve().parents[1] / "skills" / "pdf", pack)
    skill = ingest_skill(pack, strict=False)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".skillgate").mkdir()

    harness = LLMHarness(_cfg(openai_api_key="sk-test"))
    prompts: list[str] = []

    def fake_complete(prompt, timeout_sec):
        del timeout_sec
        prompts.append(prompt)
        return Completion(text='{"skill": null}', usage=Usage())

    monkeypatch.setattr(harness, "_complete", fake_complete)
    result = harness.run(
        LocalSandbox(workspace),
        "Write a pytest for a FastAPI /health endpoint. Do not touch any PDFs.",
        [skill],
        timeout_sec=5,
    )
    assert prompts, "router must run against the catalog"
    assert "skill router" in prompts[0].lower()
    assert "Gate pre-selected" not in result.transcript
    assert "skip catalog discovery" not in result.transcript
    assert result.trigger.selected_skill is None


def test_llm_harness_still_skips_discovery_when_a_skill_is_pinned(
    monkeypatch, tmp_path: Path
) -> None:
    pack = tmp_path / "pdf"
    import shutil

    shutil.copytree(Path(__file__).resolve().parents[1] / "skills" / "pdf", pack)
    scripts = pack / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / "create_pdf.py").write_text("print('ok')\n", encoding="utf-8")
    skill = ingest_skill(pack, strict=False)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    dest = workspace / ".skillgate" / "skills" / "pdf"
    dest.mkdir(parents=True)
    shutil.copytree(pack, dest, dirs_exist_ok=True)
    (workspace / ".skillgate" / "selected.json").write_text(
        '{"skill": "pdf"}', encoding="utf-8"
    )

    harness = LLMHarness(_cfg(openai_api_key="sk-test"))
    prompts: list[str] = []

    def fake_complete(prompt, timeout_sec):
        del timeout_sec
        prompts.append(prompt)
        return Completion(
            text="RUN: python3 .skillgate/skills/pdf/scripts/create_pdf.py output/out.pdf",
            usage=Usage(tokens_in=1, tokens_out=1),
        )

    monkeypatch.setattr(harness, "_complete", fake_complete)
    result = harness.run(LocalSandbox(workspace), "Make a PDF", [skill], timeout_sec=5)
    assert len(prompts) == 1
    assert "skill router" not in prompts[0].lower()
    assert result.trigger.selected_skill == "pdf"


def test_no_trigger_cursor_prompt_reads_the_catalog() -> None:
    from skillgate_ai.harness import _cursor_discover_prompt
    from skillgate_ai.ingest import Skill

    skill = Skill(
        path=Path("."),
        name="pdf",
        description="Extract, merge, and create PDFs.",
        body="# pdf",
    )
    prompt = _cursor_discover_prompt("Write a pytest for /health", [skill])
    assert "catalog" in prompt.lower()
    assert "pdf" in prompt
    assert "Do **not** browse `.skillgate/catalog.md`" not in prompt


def test_no_trigger_why_expected_is_this_check_not_a_sibling_golden() -> None:
    task = TaskSpec(
        id="no-trigger-unrelated",
        prompt="Write a pytest for a FastAPI /health endpoint. Do not touch any PDFs.",
        expect_skill=None,
        scorers=[ScorerSpec(type="skill_trigger")],
    )
    expected = _why_expected_output(
        task,
        {"body": "Hello Skill Gate", "kind": "text", "path": "evals/goldens/extract-hello.txt"},
        skill_name="pdf",
    )
    blob = expected if isinstance(expected, str) else json.dumps(expected)
    assert "Hello Skill Gate" not in blob
    assert "pdf" in blob.lower()
    assert "skill" in blob.lower()


def test_trigger_why_expected_keeps_this_check_golden() -> None:
    task = TaskSpec(
        id="extract-hello",
        prompt="Extract the text from hello.pdf",
        expect_skill="pdf",
        scorers=[ScorerSpec(type="skill_trigger")],
    )
    golden = {"body": "Hello Skill Gate", "kind": "text"}
    expected = _why_expected_output(task, golden, skill_name="pdf")
    assert expected == golden


def test_pdf_pack_no_trigger_is_skill_trigger_only() -> None:
    pack = load_case_pack(PDF_PACK)
    assert pack is not None
    spec = suite_from_pack(pack, str(PDF_PACK))
    task = next(item for item in spec.tasks if item.id == "no-trigger-unrelated")
    assert task.expect_skill is None
    assert [item.type for item in task.scorers] == ["skill_trigger"]


def test_pdf_pack_no_trigger_passes_without_output() -> None:
    pack = load_case_pack(PDF_PACK)
    assert pack is not None
    spec = suite_from_pack(pack, str(PDF_PACK))
    task = next(item for item in spec.tasks if item.id == "no-trigger-unrelated")
    scores = score_task(
        task,
        RunArtifacts(
            workspace=Path("."),
            trigger=TriggerEvidence(selected_skill=None),
        ),
    )
    assert scores and all(item.passed for item in scores)
    assert scores[0].headline == "Correctly did not trigger"
    assert "Correctly skipped" in scores[0].detail


def test_no_trigger_skips_judge_and_passes_when_nothing_is_selected(
    tmp_path: Path,
) -> None:
    skill = ingest_skill(PDF_PACK, strict=False)
    pack = load_case_pack(PDF_PACK)
    assert pack is not None
    spec = suite_from_pack(pack, str(PDF_PACK))
    task = next(item for item in spec.tasks if item.id == "no-trigger-unrelated")
    workspace = tmp_path / "ws"
    workspace.mkdir()

    class QuietHarness:
        name = "llm"
        supported_models = ("openai/gpt-4o-mini",)

        def run(self, sandbox, prompt, skills, timeout_sec):
            del sandbox, prompt, skills, timeout_sec
            text = "No skill was picked, as expected"
            return HarnessResult(
                trigger=TriggerEvidence(selected_skill=None, transcript=text),
                transcript=text,
            )

    class ExplodingJudge:
        name = "openai"

        def judge(self, *args, **kwargs):
            del args, kwargs
            raise AssertionError("judge must not run on a no-trigger check")

        def explain_fail(self, *args, **kwargs):
            del args, kwargs
            raise AssertionError("why-call must not run on a no-trigger check")

    report = _run_task(
        task=task,
        spec=spec,
        skills=[skill],
        harness=QuietHarness(),
        sandbox=LocalSandbox(workspace),
        root=PDF_PACK,
        suite_dir=PDF_PACK / "evals",
        judge=ExplodingJudge(),
    )
    assert report.passed is True
    assert report.failures == []
    assert report.selected_skill is None
    judged = report.judge or {}
    blob = json.dumps(judged)
    assert "Correctly skipped" in blob
    assert judged.get("why") in (None, "")
    suite = SuiteReport(
        suite=spec.suite,
        title=spec.title or spec.suite,
        skill="pdf",
        harness="llm",
        sandbox="local",
        passed=True,
        tasks=[report],
    )
    row = report_to_dict(suite)["tasks"][0]
    assert row["happened"] == "No skill was picked, as expected."
    answers = {item["label"]: item["answer"] for item in row["check_answers"]}
    assert answers
    assert all(value == "Correctly skipped" for value in answers.values())


def test_llm_harness_transcript_is_plain_when_nothing_is_picked(
    monkeypatch, tmp_path: Path
) -> None:
    pack = tmp_path / "pdf"
    import shutil

    shutil.copytree(PDF_PACK, pack)
    skill = ingest_skill(pack, strict=False)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".skillgate").mkdir()
    harness = LLMHarness(_cfg(openai_api_key="sk-test"))

    def fake_complete(prompt, timeout_sec):
        del timeout_sec
        assert "skill router" in prompt.lower()
        return Completion(text='{"skill": null}', usage=Usage())

    monkeypatch.setattr(harness, "_complete", fake_complete)
    result = harness.run(
        LocalSandbox(workspace),
        "Write a pytest for a FastAPI /health endpoint. Do not touch any PDFs.",
        [skill],
        timeout_sec=5,
    )
    assert result.trigger.selected_skill is None
    assert "router:" not in result.transcript
    assert '{"skill": null}' not in result.transcript
    assert "No skill was picked, as expected" in result.transcript
