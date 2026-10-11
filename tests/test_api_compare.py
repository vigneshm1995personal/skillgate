from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from skillgate_ai.api import create_app
from skillgate_ai.history import append_eval

ROOT = Path(__file__).resolve().parents[1]


def test_api_compare_cancel_endpoint(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_MODE", "local")
    root = tmp_path / "ws"
    skills = root / "skills"
    skills.mkdir(parents=True)
    pack = skills / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    monkeypatch.setenv("SKILLGATE_ROOT", str(root))
    app = create_app(root=root)
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    fp = "fp"
    append_eval(
        pack,
        run_id="r1",
        passed=True,
        report={"pack_fingerprint": fp, "pack_case_ids": ["c1"], "tasks": [{"id": "c1", "passed": True}]},
    )
    append_eval(
        pack,
        run_id="r2",
        passed=True,
        report={"pack_fingerprint": fp, "pack_case_ids": ["c1"], "tasks": [{"id": "c1", "passed": True}]},
    )
    started = client.post(
        "/api/compare/versions",
        json={"skill": "pdf", "run_ids": ["r1", "r2"]},
    )
    assert started.status_code == 200
    compare_id = started.json()["compare_id"]
    cancelled = client.post(f"/api/compare/{compare_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["ok"] is True
