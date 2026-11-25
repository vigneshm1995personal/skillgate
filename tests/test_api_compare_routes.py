from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from skillgate_ai.api import create_app
from skillgate_ai.history import append_compare

ROOT = Path(__file__).resolve().parents[1]


def _client(tmp_path: Path, monkeypatch) -> tuple[TestClient, Path]:
    monkeypatch.setenv("SKILLGATE_MODE", "local")
    root = tmp_path / "ws"
    (root / "skills").mkdir(parents=True)
    pack = root / "skills" / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    monkeypatch.setenv("SKILLGATE_ROOT", str(root))
    app = create_app(root=root)
    return TestClient(app, base_url="http://127.0.0.1:8765"), pack


def test_get_compares_returns_saved_rows(tmp_path: Path, monkeypatch) -> None:
    client, pack = _client(tmp_path, monkeypatch)
    append_compare(
        pack,
        row={"compare_id": "c1", "status": "done", "skill": "pdf", "arms": []},
    )
    response = client.get("/api/compare", params={"skill": "pdf"})
    assert response.status_code == 200
    body = response.json()
    assert body["skill"] == "pdf"
    assert any(row.get("compare_id") == "c1" for row in body["compares"])


def test_get_unknown_compare_is_404(tmp_path: Path, monkeypatch) -> None:
    client, _pack = _client(tmp_path, monkeypatch)
    response = client.get("/api/compare/missing-id", params={"skill": "pdf"})
    assert response.status_code == 404


def test_post_compare_models_requires_skill_name(tmp_path: Path, monkeypatch) -> None:
    client, _pack = _client(tmp_path, monkeypatch)
    response = client.post("/api/compare/models", json={"arms": ["a", "b"]})
    assert response.status_code == 400
    assert "skill" in response.json()["detail"]["message"].lower()
