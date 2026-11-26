from __future__ import annotations

from pathlib import Path

import pytest
from _support import cli, example_pack, history_rows, make_workspace, new_pack

pytestmark = pytest.mark.integration


def test_init_creates_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_workspace(monkeypatch, tmp_path)
    code, out = cli(["init", str(root)])
    assert code == 0, out
    assert "Workspace ready at" in out
    assert (root / "skills").is_dir()


def test_new_scaffolds_pack_with_two_pinned_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_workspace(monkeypatch, tmp_path)
    pack = new_pack(root)
    assert (pack / "SKILL.md").is_file()
    cases = (pack / "evals" / "cases.yaml").read_text(encoding="utf-8")
    assert "should-trigger-1" in cases
    assert "no-trigger-unrelated" in cases
    assert history_rows(pack) == []


def test_new_then_ingest_strict_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_workspace(monkeypatch, tmp_path)
    pack = new_pack(root)
    code, out = cli(["ingest", str(pack)])
    assert code == 0, out
    assert "OK  memo" in out


def test_new_rejects_invalid_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_workspace(monkeypatch, tmp_path)
    code, _out = cli(["new", "Bad Name"])
    assert code != 0
    assert not (root / "skills" / "Bad Name").exists()


def test_example_pdf_writes_pack_and_fixtures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_workspace(monkeypatch, tmp_path)
    pack = example_pack(root)
    assert (pack / "SKILL.md").is_file()
    assert (pack / "evals" / "cases.yaml").is_file()
    assert (pack / "evals" / "goldens" / "extract-hello.txt").is_file()
    code, out = cli(["ingest", str(pack)])
    assert code == 0, out
    assert "OK  pdf" in out


def test_example_unknown_name_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_workspace(monkeypatch, tmp_path)
    code, _out = cli(["example", "nope-not-real", "--dest", str(root / "x")])
    assert code != 0
    assert not (root / "x" / "SKILL.md").exists()


def test_import_local_folder_copies_skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from skillgate_ai.allow_root import set_cli_allow_root

    root = make_workspace(monkeypatch, tmp_path)
    src = tmp_path / "src" / "notes"
    set_cli_allow_root(tmp_path)
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text(
        "---\nname: notes\n"
        "description: Summarize meeting notes into action items when the user pastes notes.\n"
        "---\n# notes\n",
        encoding="utf-8",
    )
    code, out = cli(["import", str(src)])
    assert code == 0, out
    assert "imported  notes" in out
    assert (root / "skills" / "notes" / "SKILL.md").is_file()
