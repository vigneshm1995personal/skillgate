from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from skillgate_ai.paths import (
    PathTraversalError,
    contained_path,
    nearest_skill_pack,
    require_under,
)

ROOT = Path(__file__).resolve().parents[1]


def test_nearest_skill_pack_walks_up(tmp_path: Path) -> None:
    pack = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    nested = pack / "evals" / "fixtures"
    nested.mkdir(parents=True, exist_ok=True)
    assert nearest_skill_pack(nested) == pack.resolve()


def test_nearest_skill_pack_none_outside(tmp_path: Path) -> None:
    assert nearest_skill_pack(tmp_path) is None


def test_contained_path_rejects_escape(tmp_path: Path) -> None:
    root = (tmp_path / "ws").resolve()
    root.mkdir()
    with pytest.raises(PathTraversalError):
        contained_path(root, "..", "etc", "passwd")


def test_require_under_rejects_outside(tmp_path: Path) -> None:
    root = (tmp_path / "ws").resolve()
    root.mkdir()
    outside = (tmp_path / "other").resolve()
    outside.mkdir()
    with pytest.raises(PathTraversalError):
        require_under(root, outside)


def test_contained_path_rejects_symlink_escape(tmp_path: Path) -> None:
    root = (tmp_path / "ws").resolve()
    root.mkdir()
    outside = (tmp_path / "outside").resolve()
    outside.mkdir()
    secret = outside / "leak.txt"
    secret.write_text("secret", encoding="utf-8")
    link = root / "escape"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported here")
    with pytest.raises(PathTraversalError):
        contained_path(root, "escape", "leak.txt")


def test_contained_fs_rejects_prefix_sibling_after_realpath(tmp_path: Path) -> None:
    """``/tmp/a`` must not absorb ``/tmp/ab`` (separator-aware containment)."""
    from skillgate_ai.contained_fs import isfile_at

    root = (tmp_path / "a").resolve()
    root.mkdir()
    sibling = (tmp_path / "ab").resolve()
    sibling.mkdir()
    leak = sibling / "leak.txt"
    leak.write_text("secret", encoding="utf-8")
    try:
        os.symlink(sibling, root / "escape")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported here")
    assert not isfile_at(root, "escape", "leak.txt")


def test_contained_fs_roundtrip_under_root(tmp_path: Path) -> None:
    from skillgate_ai.contained_fs import (
        file_size,
        glob_files,
        isdir_at,
        isfile_at,
        list_names,
        read_bytes_at,
        read_text,
        resolved_relative,
        write_bytes_at,
        write_text,
    )
    from skillgate_ai.paths import filesystem_path_under

    root = (tmp_path / "pack").resolve()
    root.mkdir()
    nested = root / "nested"
    nested.mkdir()
    rel = write_text(root, "nested", "note.txt", text="hello")
    assert filesystem_path_under(root, "nested", "note.txt") == rel
    assert resolved_relative(root, "nested/note.txt") == rel
    assert isfile_at(root, "nested", "note.txt")
    assert isdir_at(root, "nested")
    assert read_text(root, "nested", "note.txt") == "hello"
    assert file_size(root, "nested", "note.txt") > 0
    write_bytes_at(root, "nested", "bin.dat", data=b"\x01\x02")
    assert read_bytes_at(root, "nested", "bin.dat") == b"\x01\x02"
    assert "note.txt" in list_names(root, "nested")
    assert "nested/note.txt" in glob_files(root, "nested", "*.txt")
