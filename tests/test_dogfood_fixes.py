"""Regression tests from real-skills dogfood (Claude Code harness)."""

from __future__ import annotations

from pathlib import Path

from conftest import plain_text
from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.gate import prepare_pack_fixtures
from skillgate_ai.harness import select_skill_from_descriptions
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.scorers import RunArtifacts, TriggerEvidence, score_answer_contains, score_skill_trigger
from skillgate_ai.suite import TaskSpec
from skillgate_ai.usage import parse_usage_line
from skillgate_ai.workspace_outputs import collect_workspace_outputs

runner = CliRunner()


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


def test_ingest_cli_prints_loaded_warning(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: None)
    pack = tmp_path / "doc"
    pack.mkdir()
    (pack / "SKILL.md").write_text(
        "---\nname: doc\ndescription: Convert docs with pandoc.\n---\n\n# doc\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["ingest", str(pack)])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert "warning" in out.lower()
    assert "pandoc" in out.lower()


def test_parse_claude_result_total_cost_usd() -> None:
    line = (
        '{"type":"result","subtype":"success","total_cost_usd":0.0421,'
        '"usage":{"inputTokens":100,"outputTokens":50}}'
    )
    usage = parse_usage_line(line)
    assert usage is not None
    assert usage.cost_usd == 0.0421
    assert usage.tokens_in == 100
    assert usage.tokens_out == 50


def test_answer_contains_matches_result_json(tmp_path: Path) -> None:
    transcript = (
        '{"type":"result","subtype":"success","result":"The total is 40.00 USD."}\n'
    )
    artifacts = RunArtifacts(
        workspace=tmp_path,
        trigger=TriggerEvidence(selected_skill="x", transcript=transcript),
    )
    score = score_answer_contains(["40.00"], artifacts)
    assert score.passed
