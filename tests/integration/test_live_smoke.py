"""Live smoke: set SKILLGATE_LIVE_SMOKE=1 and SKILLGATE_LIVE_SMOKE_ROOT to a keyed workspace."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from _support import history_rows

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("SKILLGATE_LIVE_SMOKE") != "1",
        reason="set SKILLGATE_LIVE_SMOKE=1 to run the live smoke",
    ),
]

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.timeout(960)
def test_live_check_pdf_single_case(tmp_path: Path) -> None:
    raw = os.environ.get("SKILLGATE_LIVE_SMOKE_ROOT", "")
    if not raw or not Path(raw).is_dir():
        pytest.skip("set SKILLGATE_LIVE_SMOKE_ROOT to a workspace with keys")
    from skillgate_ai.config import get_llm_config

    if not get_llm_config(Path(raw)).has_any_key:
        pytest.skip("no agent key in SKILLGATE_LIVE_SMOKE_ROOT")
    skillgate = shutil.which("skillgate", path=str(Path(sys.executable).parent))
    if skillgate is None:
        pytest.skip("skillgate not installed in venv")
    pack = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    before = len(history_rows(pack))
    env = {k: v for k, v in os.environ.items() if v} | {"SKILLGATE_ROOT": raw}
    proc = subprocess.run(
        [skillgate, "check", str(pack), "--case", "extract-hello", "--json"],
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    assert proc.returncode in (0, 1), proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert [t["id"] for t in payload["tasks"]] == ["extract-hello"]
    assert len(history_rows(pack)) == before + 1
