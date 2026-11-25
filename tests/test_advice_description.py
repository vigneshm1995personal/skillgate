from __future__ import annotations

from pathlib import Path

import pytest

from skillgate_ai.advice import (
    _THIN_HINT,
    _VAGUE_HINT,
    _WHEN_HINT,
    _clip,
    _command_fail_snippet,
    _is_script_failure,
    _tighten_description,
    apply_description_fix,
    behavior_question_ids,
    description_from_paste,
    description_is_usable,
    rewrite_skill_description,
    synthesize_trigger_description,
)
from skillgate_ai.harness import select_skill_from_descriptions
from skillgate_ai.ingest import Skill
from skillgate_ai.judge_bank import CHECK_CELL_ORDER


def test_description_is_usable_rejects_short_text():
    assert description_is_usable("Edit PDFs.") == (False, _THIN_HINT)


def test_description_is_usable_rejects_repeated_char_padding():
    desc = "Extract text from aaaaaaaaaaaa files. Use when the user mentions a pdf invoice."
    assert description_is_usable(desc) == (False, _VAGUE_HINT)


def test_description_is_usable_requires_when_clause():
    desc = (
        "Extract text, merge pages, rotate scans and split large PDF "
        "invoices into separate documents quickly."
    )
    assert description_is_usable(desc) == (False, _WHEN_HINT)


def test_description_is_usable_accepts_concrete_when_clause():
    desc = (
        "Extract text and merge PDFs. Use when the user mentions a .pdf file, "
        "invoices, or combining documents."
    )
    assert description_is_usable(desc) == (True, "")


def test_description_is_usable_require_when_false_skips_clause():
    desc = (
        "Extract text, merge pages, rotate scans and split large PDF "
        "invoices into separate documents quickly."
    )
    assert description_is_usable(desc, require_when=False) == (True, "")


def test_description_from_paste_returns_trimmed_description():
    assert (
        description_from_paste("---\nname: pdf\ndescription: '  Extract PDFs.  '\n---")
        == "Extract PDFs."
    )


def test_description_from_paste_rejects_missing_frontmatter():
    with pytest.raises(ValueError, match="Paste a SKILL.md frontmatter block"):
        description_from_paste("no frontmatter")


def test_description_from_paste_rejects_empty_description():
    with pytest.raises(ValueError, match="has no description"):
        description_from_paste("---\nname: pdf\n---\n")


def test_rewrite_skill_description_preserves_name_and_body(tmp_path: Path):
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("---\nname: pdf\ndescription: old\n---\n# Body\n", encoding="utf-8")
    rewrite_skill_description(skill_md, "new desc")
    assert skill_md.read_text(encoding="utf-8") == (
        "---\nname: pdf\ndescription: new desc\n---\n# Body\n"
    )


def test_rewrite_skill_description_without_frontmatter_raises(tmp_path: Path):
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("# Body only\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no YAML frontmatter"):
        rewrite_skill_description(skill_md, "new")
    assert skill_md.read_text(encoding="utf-8") == "# Body only\n"


def test_apply_description_fix_copies_and_restores_scripts(tmp_path: Path):
    src = tmp_path / "src" / "demo"
    ref = tmp_path / "ref" / "demo"
    src.mkdir(parents=True)
    ref.mkdir(parents=True)
    (src / "SKILL.md").write_text("---\nname: demo\ndescription: old\n---\n", encoding="utf-8")
    (src / "scripts").mkdir()
    (src / "scripts" / "a.py").write_text("broken", encoding="utf-8")
    (ref / "scripts").mkdir(parents=True)
    (ref / "scripts" / "a.py").write_text("good", encoding="utf-8")
    dest = apply_description_fix(
        source=src,
        dest_root=tmp_path / "work",
        new_description="new",
        restore_scripts_from=ref,
    )
    assert dest == tmp_path / "work" / "demo"
    assert "description: new" in (dest / "SKILL.md").read_text(encoding="utf-8")
    assert (dest / "scripts" / "a.py").read_text(encoding="utf-8") == "good"
    assert "description: old" in (src / "SKILL.md").read_text(encoding="utf-8")


def test_apply_description_fix_rewrites_in_place_when_dest_is_source(tmp_path: Path):
    src = tmp_path / "demo"
    src.mkdir()
    (src / "SKILL.md").write_text("---\nname: demo\ndescription: old\n---\n", encoding="utf-8")
    out = apply_description_fix(source=src, dest_root=tmp_path, new_description="new")
    assert out == src
    assert "description: new" in (src / "SKILL.md").read_text(encoding="utf-8")


def test_behavior_question_ids_maps_cell_reason_to_id():
    judge = {
        "extra_failures": ["Cited? No"],
        "cells": {"cite": {"reason": "Cited? No"}},
    }
    assert behavior_question_ids(judge) == ["cite"]


def test_behavior_question_ids_matches_instructions_and_strips_no():
    judge = {
        "extra_failures": ["Asked first? No", "Loose text No"],
        "questions": {"ask_first": {"instructions": "Asked first?"}},
    }
    assert behavior_question_ids(judge) == ["ask_first", "Loose text"]


def test_behavior_question_ids_ignores_reserved_and_non_dict():
    assert behavior_question_ids(None) == []
    assert behavior_question_ids({"extra_failures": [CHECK_CELL_ORDER[0]]}) == []


def test_command_fail_snippet_prefers_error_line():
    assert _command_fail_snippet("usage: x\nerror: bad flag --y\n") == "bad flag --y"
    assert _command_fail_snippet("") == ""


def test_is_script_failure_ignores_json_stderr():
    assert _is_script_failure(1, '{"e":1}') is False
    assert _is_script_failure(2, "Traceback") is True
    assert _is_script_failure(0, "x") is False
    assert _is_script_failure(None, "x") is False


def test_clip_breaks_on_word_boundary():
    assert _clip("alpha beta gamma", 12) == "alpha..."
    assert _clip("  a   b ", 10) == "a b"


def test_tighten_description_is_idempotent():
    skill = Skill(
        path=Path("skills/pdf"),
        name="pdf",
        description="Edit PDFs.",
        body="",
    )
    first = _tighten_description(skill, "")
    second = _tighten_description(
        Skill(path=skill.path, name=skill.name, description=first, body=""), ""
    )
    assert first == second
    assert "unrelated questions" in first.lower()


def test_synthesize_trigger_description_retargets_from_pdf_reference(tmp_path: Path) -> None:
    skill = Skill(
        path=tmp_path / "pdf-lite",
        name="pdf-lite",
        description="Too short.",
        body="",
    )
    reference = Skill(
        path=tmp_path / "pdf-ref",
        name="pdf-ref",
        description="Work with PDF documents and extract text.",
        body="",
    )
    result = synthesize_trigger_description(
        skill,
        ["Please open quarterly-report.pdf and extract the tables"],
        reference,
    )
    assert "pdf" in result.lower()
    assert len(result) <= 1024


def test_synthesize_trigger_description_selects_skill_for_failed_prompt(tmp_path: Path):
    skill = Skill(
        path=tmp_path / "pdf-tool",
        name="pdf-tool",
        description="Unrelated.",
        body="",
    )
    prompt = "Extract the text from invoice.pdf"
    result = synthesize_trigger_description(skill, [prompt], None)
    assert len(result) <= 1024
    probe = Skill(path=skill.path, name=skill.name, description=result, body="")
    assert select_skill_from_descriptions(prompt, [probe]) == "pdf-tool"
