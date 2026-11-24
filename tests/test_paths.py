from __future__ import annotations

import shutil
from pathlib import Path

from skillgate_ai.paths import nearest_skill_pack

ROOT = Path(__file__).resolve().parents[1]


def test_nearest_skill_pack_walks_up(tmp_path: Path) -> None:
    pack = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    nested = pack / "evals" / "fixtures"
    nested.mkdir(parents=True, exist_ok=True)
    assert nearest_skill_pack(nested) == pack.resolve()


def test_nearest_skill_pack_none_outside(tmp_path: Path) -> None:
    assert nearest_skill_pack(tmp_path) is None
