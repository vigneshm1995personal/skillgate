from __future__ import annotations

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
