from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest
from conftest import plain_text
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from skillgate_ai.api import create_app
from skillgate_ai.cli import app
from skillgate_ai.skill_md import write_skill_md

runner = CliRunner()


def _client(root: Path, monkeypatch) -> TestClient:
    from skillgate_ai.allow_root import set_cli_allow_root

    set_cli_allow_root(None)
    (root / "skills").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SKILLGATE_ROOT", str(root))
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
            [
                "ui",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-browser",
                "--root",
                str(tmp_path),
            ],
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


def _symlink_or_skip(src: Path, dest: Path) -> None:
    try:
        os.symlink(src, dest)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported here")


def test_symlinked_skill_dir_outside_root_is_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(tmp_path / "cursor-skills"))
    monkeypatch.setenv("SKILLGATE_CODEX_SKILLS", str(tmp_path / "codex-skills"))
    monkeypatch.setenv("SKILLGATE_CLAUDE_SKILLS", str(tmp_path / "claude-skills"))
    outside = tmp_path / "outside" / "evil"
    write_skill_md(outside, name="evil", description="Outside.", body="# SECRET\n")
    (outside / "secret.txt").write_text("leak", encoding="utf-8")
    workspace = tmp_path / "project"
    (workspace / "skills").mkdir(parents=True)
    _symlink_or_skip(outside, workspace / "skills" / "evil")
    client = _client(workspace, monkeypatch)
    listing = client.get("/api/skills")
    assert listing.status_code == 200
    assert all(item.get("slug") != "evil" for item in listing.json()["skills"])
    detail = client.get("/api/skills/evil")
    assert detail.status_code in {400, 404}
    pack_file = client.get("/api/skills/evil/pack-file", params={"path": "secret.txt"})
    assert pack_file.status_code in {400, 404}
    pack_raw = client.get("/api/skills/evil/pack-raw", params={"path": "SKILL.md"})
    assert pack_raw.status_code in {400, 404}


def test_symlinked_skill_md_outside_root_is_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(tmp_path / "cursor-skills"))
    monkeypatch.setenv("SKILLGATE_CODEX_SKILLS", str(tmp_path / "codex-skills"))
    monkeypatch.setenv("SKILLGATE_CLAUDE_SKILLS", str(tmp_path / "claude-skills"))
    outside_md = tmp_path / "outside" / "SKILL.md"
    outside_md.parent.mkdir(parents=True)
    outside_md.write_text(
        "---\nname: evil\ndescription: Outside.\n---\n# SECRET\n",
        encoding="utf-8",
    )
    workspace = tmp_path / "project"
    evil = workspace / "skills" / "evil"
    evil.mkdir(parents=True)
    _symlink_or_skip(outside_md, evil / "SKILL.md")
    client = _client(workspace, monkeypatch)
    listing = client.get("/api/skills")
    assert listing.status_code == 200
    assert all(item.get("slug") != "evil" for item in listing.json()["skills"])
    detail = client.get("/api/skills/evil")
    assert detail.status_code in {400, 404}
    assert "SECRET" not in detail.text


def test_symlinked_skill_inside_root_is_allowed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(tmp_path / "cursor-skills"))
    monkeypatch.setenv("SKILLGATE_CODEX_SKILLS", str(tmp_path / "codex-skills"))
    monkeypatch.setenv("SKILLGATE_CLAUDE_SKILLS", str(tmp_path / "claude-skills"))
    workspace = tmp_path / "project"
    real = workspace / "shared" / "pdf-tools"
    write_skill_md(real, name="pdf-tools", description="Tools.", body="# PDF\n")
    (workspace / "skills").mkdir(parents=True)
    _symlink_or_skip(real, workspace / "skills" / "pdf-tools")
    client = _client(workspace, monkeypatch)
    listing = client.get("/api/skills")
    assert listing.status_code == 200
    assert any(item.get("slug") == "pdf-tools" for item in listing.json()["skills"])
    detail = client.get("/api/skills/pdf-tools")
    assert detail.status_code == 200
