from __future__ import annotations

import socket
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from conftest import plain_text
from skillgate_ai.api import create_app
from skillgate_ai.cli import app
from skillgate_ai.skill_md import write_skill_md

runner = CliRunner()


def _client(root: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("SKILLGATE_MODE", "local")
    app = create_app(root=root)
    return TestClient(app, base_url="http://127.0.0.1:8765")


def test_text_plain_post_is_forbidden(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    res = client.post(
        "/api/skills/import",
        content=b"{}",
        headers={"content-type": "text/plain"},
    )
    assert res.status_code == 403


def test_cross_site_origin_is_forbidden(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    res = client.post(
        "/api/skills/import",
        json={"sources": ["cursor"]},
        headers={"origin": "https://evil.example"},
    )
    assert res.status_code == 403


def test_empty_post_skip_is_allowed(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    res = client.post("/api/runs/missing/skip")
    assert res.status_code != 403


def test_json_loopback_post_is_allowed(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    res = client.post(
        "/api/skills/import",
        json={"sources": ["cursor"]},
        headers={"origin": "http://127.0.0.1:8765"},
    )
    assert res.status_code != 403


def test_bad_host_is_forbidden(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    res = client.get("/api/status", headers={"host": "evil.example"})
    assert res.status_code == 403


def test_pack_path_outside_project_is_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(tmp_path / "cursor-skills"))
    monkeypatch.setenv("SKILLGATE_CODEX_SKILLS", str(tmp_path / "codex-skills"))
    monkeypatch.setenv("SKILLGATE_CLAUDE_SKILLS", str(tmp_path / "claude-skills"))
    outside = tmp_path / "outside" / "pdf"
    write_skill_md(outside, name="pdf", description="Outside.", body="# Outside\n")
    workspace = tmp_path / "project"
    workspace.mkdir()
    client = _client(workspace, monkeypatch)
    res = client.get("/api/skills/pdf")
    assert res.status_code in {400, 404}
    escaped = client.get(
        "/api/skills/pdf/pack-file",
        params={"path": "../../outside/pdf/SKILL.md"},
    )
    assert escaped.status_code in {400, 404}


def test_ui_port_out_of_range_is_friendly() -> None:
    result = runner.invoke(app, ["ui", "--port", "99999", "--no-browser"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 2, out
    assert "Port must be between 1 and 65535" in out
    assert "Traceback" not in out


def test_ui_busy_port_is_friendly_before_url(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(5)
    port = sock.getsockname()[1]
    try:
        result = runner.invoke(
            app,
            ["ui", "--host", "127.0.0.1", "--port", str(port), "--no-browser", "--root", str(tmp_path)],
        )
        out = plain_text(result.stdout + result.stderr)
        assert result.exit_code != 0, out
        assert "in use" in out.lower()
        assert "--port" in out
        assert "at http" not in out.lower()
        assert "Skill Gate UI (local, no account) at" not in out
        assert "Traceback" not in out
    finally:
        sock.close()
