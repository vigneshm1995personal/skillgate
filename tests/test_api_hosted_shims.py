from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from skillgate_ai.api import create_app

ROOT = Path(__file__).resolve().parents[1]


def _client(tmp: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("SKILLGATE_MODE", "local")
    app = create_app(root=tmp)
    return TestClient(app, base_url="http://127.0.0.1:8765")


def test_hosted_shim_routes_return_stub_payloads(tmp_path: Path, monkeypatch) -> None:
    shutil.copytree(ROOT / "skills" / "pdf", tmp_path / "skills" / "pdf")
    client = _client(tmp_path, monkeypatch)
    assert client.post("/api/auth/signout").status_code == 200
    analytics = client.get("/api/analytics").json()
    assert analytics["totals"]["runs"] == 0
    baseline = client.post("/api/evals/baseline", json={"skill": "pdf", "run_id": "r1"}).json()
    assert baseline["skill"] == "pdf"
    assert baseline["baseline"]["source"] == "manual"
    promote = client.post(
        "/api/evals/promote-draft",
        json={"skill": "pdf", "task": {"id": "t1", "prompt": "hello", "files": []}},
    )
    assert promote.status_code == 200
    body = promote.json()
    assert body["check"]["id"] == "t1"
    assert body["skill"]["name"] == "pdf"
    suggest = client.post("/api/evals/suggest-skill-updates")
    assert suggest.status_code == 404
    assert "local app" in str(suggest.json().get("detail", "")).lower()
