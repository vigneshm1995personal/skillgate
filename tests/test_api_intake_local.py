from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from skillgate_ai.api_intake import (
    extract_uploaded_skill,
    import_path_or_git_result,
    looks_like_git_url,
    write_pasted_skill,
)
from skillgate_ai.errors import SkillGateError


def test_looks_like_git_url() -> None:
    assert looks_like_git_url("https://github.com/org/repo.git") is True
    assert looks_like_git_url("/local/path") is False


def test_write_pasted_skill_creates_pack(tmp_path: Path) -> None:
    md = "---\nname: pasted\ndescription: pasted skill for intake tests.\n---\n\n# Body\n"
    dest = write_pasted_skill(tmp_path, md)
    assert (dest / "SKILL.md").is_file()


def test_extract_uploaded_skill_from_zip(tmp_path: Path) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "demo/SKILL.md",
            "---\nname: demo\ndescription: from zip\n---\n",
        )
    folder = extract_uploaded_skill(tmp_path, buf.getvalue(), filename="demo.zip")
    assert (folder / "SKILL.md").is_file()


def test_import_path_or_git_result_local_folder(tmp_path: Path) -> None:
    import shutil

    src = tmp_path / "pdf"
    shutil.copytree(
        Path(__file__).resolve().parents[1] / "skills" / "pdf",
        src,
    )
    result = import_path_or_git_result(tmp_path, str(src))
    assert result["imported"]


def test_import_path_or_git_result_rejects_empty(tmp_path: Path) -> None:
    with pytest.raises(SkillGateError, match="git URL"):
        import_path_or_git_result(tmp_path, "")
