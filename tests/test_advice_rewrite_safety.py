from __future__ import annotations

from pathlib import Path

import pytest

from skillgate_ai.advice.rewrite import rewrite_skill_description


def test_rewrite_skill_description_requires_skill_md_under_pack(tmp_path: Path) -> None:
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "evals").mkdir()
    with pytest.raises(ValueError, match="SKILL.md not found"):
        rewrite_skill_description(pack / "SKILL.md", "new")
