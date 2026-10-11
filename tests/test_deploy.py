from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.deploy import latest_check_passed
from skillgate_ai.errors import friendly_os_error
from skillgate_ai.history import append_eval
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.pack import copy_skill_pack

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]


def _wipe_history(pack: Path) -> None:
    hist = pack / "evals" / "history"
    if hist.is_dir():
        for path in hist.glob("*.jsonl"):
            path.unlink()


def _pdf_pack(tmp_path: Path) -> Path:
    dest = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    _wipe_history(dest)
    return dest


def test_copy_skill_pack_failed_copy_leaves_existing_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _pdf_pack(tmp_path / "src")
    dest = tmp_path / "skills" / "pdf"
    dest.mkdir(parents=True)
    marker = dest / "KEEP.txt"
    marker.write_text("old-install", encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr("skillgate_ai.pack.shutil.copytree", boom)
    with pytest.raises(PermissionError):
        copy_skill_pack(source, dest)
    assert marker.is_file()
    assert marker.read_text(encoding="utf-8") == "old-install"
    leftovers = [p for p in dest.parent.iterdir() if ".skillgate-tmp-" in p.name]
    assert leftovers == []


def test_copy_skill_pack_swap_replaces_without_nesting(tmp_path: Path) -> None:
    source = _pdf_pack(tmp_path / "src")
    dest = tmp_path / "skills" / "pdf"
    dest.mkdir(parents=True)
    (dest / "stale.txt").write_text("gone", encoding="utf-8")
    copied = copy_skill_pack(source, dest)
    assert Path(copied["dest_path"]) == dest.resolve()
    assert (dest / "SKILL.md").is_file()
    assert not (dest / "stale.txt").exists()
    assert not (dest / "pdf").exists()


def test_deploy_readonly_parent_friendly_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = _pdf_pack(tmp_path / "pack")
    skills_root = tmp_path / "cursor-skills"
    skills_root.mkdir()
    existing = skills_root / "pdf"
    existing.mkdir()
    (existing / "KEEP.txt").write_text("old", encoding="utf-8")
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(skills_root))
    append_eval(pack, run_id="green", passed=True)

    def boom(*_args, **_kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr("skillgate_ai.pack.shutil.copytree", boom)
    result = runner.invoke(app, ["deploy", str(pack)])
    assert result.exit_code == 1, result.stdout
    combined = result.stdout + result.stderr
    assert "isn't writable" in combined
    assert "PermissionError" not in combined
    assert "Errno" not in combined
    assert "Traceback" not in combined
    assert (existing / "KEEP.txt").read_text(encoding="utf-8") == "old"


def test_friendly_os_error_has_no_errno() -> None:
    exc = PermissionError(13, "Permission denied")
    text = friendly_os_error(exc, what="install into Cursor")
    assert "isn't writable" in text
    assert "13" not in text
    assert "Permission denied" not in text


def test_deploy_refuses_failed_latest_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = tmp_path / "pdf-sabotaged"
    shutil.copytree(ROOT / "skills" / "pdf-sabotaged", pack)
    _wipe_history(pack)
    skills_root = tmp_path / "cursor-skills"
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(skills_root))
    append_eval(pack, run_id="red", passed=False)
    result = runner.invoke(app, ["deploy", str(pack)])
    assert result.exit_code == 1, result.stdout
    assert "did not pass" in result.stdout
    assert "--force" in result.stdout
    assert not (skills_root / "pdf-sabotaged").exists()


def test_deploy_uses_newer_ts_not_later_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = tmp_path / "pdf-sabotaged"
    shutil.copytree(ROOT / "skills" / "pdf-sabotaged", pack)
    _wipe_history(pack)
    hist = pack / "evals" / "history"
    hist.mkdir(parents=True, exist_ok=True)
    (hist / "20261011.jsonl").write_text(
        '{"ts":"2026-10-11T01:00:00+00:00","run_id":"old-utc","passed":true,"gate":"green"}\n',
        encoding="utf-8",
    )
    (hist / "20261010.jsonl").write_text(
        '{"ts":"2026-10-11T01:30:00+00:00","run_id":"new-local","passed":false,"gate":"red"}\n',
        encoding="utf-8",
    )
    skills_root = tmp_path / "cursor-skills"
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(skills_root))
    assert latest_check_passed(pack) is False
    result = runner.invoke(app, ["deploy", str(pack)])
    assert result.exit_code == 1, result.stdout
    assert "did not pass" in result.stdout
    assert not (skills_root / "pdf-sabotaged").exists()


def test_deploy_force_installs_failed_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = tmp_path / "pdf-sabotaged"
    shutil.copytree(ROOT / "skills" / "pdf-sabotaged", pack)
    _wipe_history(pack)
    skills_root = tmp_path / "cursor-skills"
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(skills_root))
    append_eval(pack, run_id="red", passed=False)
    result = runner.invoke(app, ["deploy", str(pack), "--force"])
    assert result.exit_code == 0, result.stdout
    assert (skills_root / "pdf-sabotaged" / "SKILL.md").is_file()
    assert "Installed pdf-sabotaged" in result.stdout


def test_deploy_runs_check_when_no_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pack = _pdf_pack(tmp_path / "pack")
    skills_root = tmp_path / "cursor-skills"
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(skills_root))
    assert latest_check_passed(pack) is None
    result = runner.invoke(app, ["deploy", str(pack)])
    assert result.exit_code == 0, result.stdout
    assert (skills_root / "pdf" / "SKILL.md").is_file()
    assert latest_check_passed(pack) is True


def test_deploy_reads_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proj = tmp_path / "proj"
    pack = proj / "skills" / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    _wipe_history(pack)
    cursor_dest = tmp_path / "from-dotenv"
    (proj / ".env").write_text(
        f"SKILLGATE_CURSOR_SKILLS={cursor_dest}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(proj)
    monkeypatch.delenv("SKILLGATE_CURSOR_SKILLS", raising=False)
    monkeypatch.delenv("SKILLGATE_ROOT", raising=False)
    append_eval(pack, run_id="green", passed=True)
    result = runner.invoke(app, ["deploy", str(pack)])
    assert result.exit_code == 0, result.stdout
    assert (cursor_dest / "pdf" / "SKILL.md").is_file()


def test_deploy_help_labels_force() -> None:
    result = runner.invoke(app, ["deploy", "--help"])
    assert result.exit_code == 0, result.stdout
    assert "--force" in result.stdout
    assert "even if the latest check did not pass" in result.stdout.lower() or (
        "did not pass" in result.stdout
    )


def test_ingest_then_install_uses_atomic_copy(tmp_path: Path) -> None:
    pack = _pdf_pack(tmp_path / "pack")
    dest = tmp_path / "installed" / "pdf"
    dest.mkdir(parents=True)
    (dest / "KEEP.txt").write_text("old", encoding="utf-8")
    copy_skill_pack(pack, dest)
    ingest_skill(dest)
    assert (dest / "SKILL.md").is_file()
    assert not (dest / "KEEP.txt").exists()
