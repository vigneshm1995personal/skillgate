"""No-trigger checks must not pin a skill; the model chooses from the catalog."""

from __future__ import annotations

import json
from pathlib import Path

from skillgate_ai.case_pack import (
    CaseGolden,
    CaseInput,
    CasePack,
    PackCase,
    checks_from_pack,
    load_case_pack,
    suite_from_pack,
    task_missing_golden,
)
from skillgate_ai.engine import SuiteReport, _run_task, _seed_skill_selection, _why_expected_output
from skillgate_ai.harness import HarnessResult, _read_selection, _MISSING
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.report import report_to_dict
from skillgate_ai.sandbox import LocalSandbox
from skillgate_ai.scorers import RunArtifacts, TriggerEvidence, score_task
from skillgate_ai.suite import FileExpect, ScorerSpec, TaskSpec
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
        name = "cursor-agent"
        supported_models = ("composer-2.5",)

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
        harness="cursor-agent",
        sandbox="local",
        passed=True,
        tasks=[report],
    )
    row = report_to_dict(suite)["tasks"][0]
    assert row["happened"] == "No skill was picked, as expected."
    answers = {item["label"]: item["answer"] for item in row["check_answers"]}
    assert answers
    assert all(value == "Correctly skipped" for value in answers.values())


def _older_imported_no_trigger_with_notes_output() -> PackCase:
    """Leftover output from an older pdf pack that copied extract-notes onto no-trigger."""
    return PackCase(
        id="no-trigger-unrelated",
        status="pinned",
        prompt="Write a pytest for a FastAPI /health endpoint. Do not touch any PDFs.",
        should_trigger=False,
        input=CaseInput(files=[]),
        golden=CaseGolden(
            output_path="output/notes.txt",
            path="evals/goldens/trigger-notes-pdf.txt",
            kind="text",
        ),
        contains=["Meeting notes"],
    )


def test_older_imported_no_trigger_notes_output_is_ignored() -> None:
    pack = CasePack(
        schema_version=1,
        skill="pdf",
        cases=[_older_imported_no_trigger_with_notes_output()],
    )
    spec = suite_from_pack(pack, "pdf")
    task = spec.tasks[0]
    assert task.expect_skill is None
    scores = score_task(
        task,
        RunArtifacts(
            workspace=Path("."),
            trigger=TriggerEvidence(selected_skill=None),
        ),
    )
    assert scores and all(item.passed for item in scores)
    blob = " ".join(f"{item.detail} {item.headline}" for item in scores)
    assert "missing file" not in blob
    assert "output/notes.txt" not in blob


def test_score_task_ignores_leftover_output_scorers_on_no_trigger() -> None:
    task = TaskSpec(
        id="no-trigger-unrelated",
        prompt="Write a pytest for a FastAPI /health endpoint. Do not touch any PDFs.",
        expect_skill=None,
        scorers=[
            ScorerSpec(type="skill_trigger"),
            ScorerSpec(
                type="task_completion",
                files=[FileExpect(path="output/notes.txt", exists=True)],
            ),
        ],
    )
    scores = score_task(
        task,
        RunArtifacts(
            workspace=Path("."),
            trigger=TriggerEvidence(selected_skill=None),
        ),
    )
    assert scores and all(item.passed for item in scores)
    assert all(item.scorer == "skill_trigger" for item in scores)
    picked = score_task(
        task,
        RunArtifacts(
            workspace=Path("."),
            trigger=TriggerEvidence(selected_skill="pdf"),
        ),
    )
    assert picked and not all(item.passed for item in picked)
    assert not any("missing file" in (item.detail or "") for item in picked)


def test_no_trigger_leftover_output_warns_in_plain_words() -> None:
    pack = CasePack(
        schema_version=1,
        skill="pdf",
        cases=[_older_imported_no_trigger_with_notes_output()],
    )
    row = next(
        item for item in checks_from_pack(pack) if item["id"] == "no-trigger-unrelated"
    )
    warning = str(row.get("warning") or "")
    assert warning
    assert "no-trigger" in warning.lower() or "not trigger" in warning.lower()
    assert "ignored" in warning.lower()
    assert "output_path" not in warning
    assert "golden" not in warning
    assert "contains" not in warning


def test_older_imported_no_trigger_notes_run_passes(
    tmp_path: Path,
) -> None:
    import shutil

    pack_dir = tmp_path / "pdf"
    shutil.copytree(PDF_PACK, pack_dir)
    cases = (pack_dir / "evals" / "cases.yaml").read_text(encoding="utf-8")
    leftover = (
        "  - id: no-trigger-unrelated\n"
        "    status: pinned\n"
        "    prompt: Write a pytest for a FastAPI /health endpoint. Do not touch any PDFs.\n"
        "    should_trigger: false\n"
        "    input:\n"
        "      files: []\n"
        "    golden:\n"
        "      output_path: output/notes.txt\n"
        "      path: evals/goldens/trigger-notes-pdf.txt\n"
        "      kind: text\n"
        "    contains:\n"
        "      - Meeting notes\n"
    )
    marker = "  - id: no-trigger-unrelated\n"
    start = cases.index(marker)
    end = cases.index("  - id: extract-invoice\n")
    (pack_dir / "evals" / "cases.yaml").write_text(
        cases[:start] + leftover + cases[end:], encoding="utf-8"
    )
    assert not task_missing_golden(pack_dir, "no-trigger-unrelated")

    skill = ingest_skill(pack_dir, strict=False)
    pack = load_case_pack(pack_dir)
    assert pack is not None
    spec = suite_from_pack(pack, str(pack_dir))
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

    report = _run_task(
        task=task,
        spec=spec,
        skills=[skill],
        harness=QuietHarness(),
        sandbox=LocalSandbox(workspace),
        root=pack_dir,
        suite_dir=pack_dir / "evals",
        judge=None,
    )
    assert report.passed is True
    assert report.failures == []
    assert report.selected_skill is None
    assert not any("missing file" in item for item in report.failures)
    assert not any("notes.txt" in item for item in (report.failures or []))
