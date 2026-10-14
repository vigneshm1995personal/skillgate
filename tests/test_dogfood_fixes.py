"""Regression tests from real-skills dogfood (Claude Code harness)."""

from __future__ import annotations

from pathlib import Path

from skillgate_ai.gate import prepare_pack_fixtures
from skillgate_ai.harness import select_skill_from_descriptions
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.scorers import TriggerEvidence, score_skill_trigger
from skillgate_ai.suite import TaskSpec
from skillgate_ai.workspace_outputs import collect_workspace_outputs


def test_correct_skill_passes_even_if_description_would_not_match() -> None:
    from skillgate_ai.ingest import Skill

    skill = Skill(
        path=Path("/tmp/x"),
        name="memo",
        description="Only for unrelated meal planning.",
        body="# memo\n",
    )
    task = TaskSpec(
        id="t1",
        prompt="Write output/memo.docx with meeting notes.",
        expect_skill="memo",
        scorers=[],
    )
    evidence = TriggerEvidence(selected_skill="memo", read_paths=[], transcript="")
    score = score_skill_trigger(task, evidence, skills=[skill])
    assert score.passed
    assert select_skill_from_descriptions(task.prompt, [skill]) != "memo"


def test_prepare_pack_fixtures_skips_user_imported_skills(tmp_path: Path) -> None:
    pack = tmp_path / "memo"
    pack.mkdir()
    (pack / "SKILL.md").write_text(
        "---\nname: memo\ndescription: Notes skill.\n---\n\n# memo\n",
        encoding="utf-8",
    )
    (pack / "evals" / "fixtures").mkdir(parents=True)
    prepare_pack_fixtures(pack)
    assert not (pack / "evals" / "fixtures" / "invoice.pdf").exists()


def test_collect_workspace_outputs_finds_output_dir(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    out = ws / "output" / "memo.docx"
    out.parent.mkdir(parents=True)
    out.write_bytes(b"docx-bytes")
    task = TaskSpec(
        id="t1",
        prompt="write memo",
        expect_skill="memo",
        scorers=[],
    )
    rows = collect_workspace_outputs(task, ws)
    assert any(row["path"] == "output/memo.docx" and row["present"] for row in rows)


def test_ingest_warns_when_pandoc_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: None)
    pack = tmp_path / "doc"
    pack.mkdir()
    (pack / "SKILL.md").write_text(
        "---\nname: doc\ndescription: Convert docs with pandoc.\n---\n\n# doc\n",
        encoding="utf-8",
    )
    skill = ingest_skill(pack, strict=False)
    assert skill.warning and "pandoc" in skill.warning.lower()
