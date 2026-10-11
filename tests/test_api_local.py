from __future__ import annotations

import io
import shutil
import time
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from skillgate_ai.api import create_app
from skillgate_ai.api_payloads import history_row_to_run, local_gate
from skillgate_ai.demo_files import ensure_demo_pdfs
from skillgate_ai.history import append_eval
from skillgate_ai.skill_md import write_skill_md

ROOT = Path(__file__).resolve().parents[1]


def _copy_pack(tmp: Path, name: str = "pdf") -> Path:
    dest = tmp / "skills" / name
    shutil.copytree(ROOT / "skills" / name, dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")
    return dest


def _client(tmp: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("SKILLGATE_MODE", "local")
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(tmp / "cursor-skills"))
    monkeypatch.setenv("SKILLGATE_CODEX_SKILLS", str(tmp / "codex-skills"))
    monkeypatch.setenv("SKILLGATE_CLAUDE_SKILLS", str(tmp / "claude-skills"))
    app = create_app(root=tmp)
    return TestClient(app)


def test_status_local_hides_paid_slots(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "local"
    assert data["auth_required"] is False
    assert data["slots"]["signIn"] is False
    assert data["slots"]["billing"] is False
    assert data["slots"]["generateChecks"] is False
    assert data["slots"]["gitPublish"] is False
    assert data["ci"]["url"] == ""
    assert data["ci"]["badge"] == ""
    me = client.get("/api/auth/me")
    assert me.json()["user"] is None
    assert me.json()["auth_required"] is False


def test_catalog_and_skill_page_include_skill_md(tmp_path: Path, monkeypatch) -> None:
    _copy_pack(tmp_path)
    client = _client(tmp_path, monkeypatch)
    listed = client.get("/api/skills")
    assert listed.status_code == 200
    names = {item["name"] for item in listed.json()["skills"]}
    assert "pdf" in names
    detail = client.get("/api/skills/pdf")
    assert detail.status_code == 200
    body = detail.json()
    assert body["skill"]["name"] == "pdf"
    paths = [item["path"] for item in body["pack_files"]]
    assert "SKILL.md" in paths
    preview = client.get("/api/skills/pdf/pack-file", params={"path": "SKILL.md"})
    assert preview.status_code == 200
    assert "name:" in (preview.json().get("text") or "")


def test_generate_does_not_start_a_run(tmp_path: Path, monkeypatch) -> None:
    _copy_pack(tmp_path)
    client = _client(tmp_path, monkeypatch)
    before = client.get("/api/skills")
    gen = client.post("/api/evals/generate", json={"skill": "pdf"})
    assert gen.status_code == 200
    payload = gen.json()
    assert payload["source"] == "pack"
    assert payload["checks"]
    assert client.app.state.ui.runs == {}
    after = client.get("/api/skills")
    assert after.status_code == 200
    assert len(after.json()["skills"]) == len(before.json()["skills"])


def test_run_is_explicit_and_uses_built_in_checker(tmp_path: Path, monkeypatch) -> None:
    _copy_pack(tmp_path)
    client = _client(tmp_path, monkeypatch)
    gen = client.post("/api/evals/generate", json={"skill": "pdf"})
    checks = gen.json()["checks"]
    started = client.post(
        "/api/runs",
        json={"skill": "pdf", "checks": checks, "live": False, "demo": True},
    )
    assert started.status_code == 200
    run_id = started.json()["id"]
    deadline = time.time() + 120
    snapshot = None
    while time.time() < deadline:
        snapshot = client.get(f"/api/runs/{run_id}").json()
        if snapshot.get("status") != "running":
            break
        time.sleep(0.2)
    assert snapshot is not None
    assert snapshot["status"] == "done"
    assert snapshot["passed"] is True
    assert snapshot["gate_decision"] == "cleared"
    report = snapshot["report"]
    assert report["gate"] == "green"
    task = report["tasks"][0]
    assert "happened" in task
    assert "check_answers" in task or task.get("passed") is True


def test_settings_keys_write_dotenv(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    listed = client.get("/api/settings/keys")
    assert listed.status_code == 200
    assert listed.json()["keys"]["OPENAI_API_KEY"]["set"] is False
    saved = client.put("/api/settings/keys/OPENAI_API_KEY", json={"value": "sk-test-local"})
    assert saved.status_code == 200
    assert saved.json()["keys"]["OPENAI_API_KEY"]["from_vault"] is True
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-test-local" in env_text
    cleared = client.delete("/api/settings/keys/OPENAI_API_KEY")
    assert cleared.status_code == 200
    assert "sk-test-local" not in (tmp_path / ".env").read_text(encoding="utf-8")


def test_import_from_cursor_skills(tmp_path: Path, monkeypatch) -> None:
    cursor = tmp_path / "cursor-skills" / "imported-skill"
    write_skill_md(
        cursor,
        name="imported-skill",
        description="Imported skill for local catalog tests. Use when the user asks for imported-skill notes.",
    )
    client = _client(tmp_path, monkeypatch)
    listed = client.get("/api/skills")
    names = {item["name"] for item in listed.json()["skills"]}
    assert "imported-skill" not in names
    imported = client.post("/api/skills/import", json={"sources": ["cursor"]})
    assert imported.status_code == 200
    dest = tmp_path / "skills" / "imported-skill"
    assert (dest / "SKILL.md").is_file()


def test_deploy_copies_into_agent_folder(tmp_path: Path, monkeypatch) -> None:
    pack = _copy_pack(tmp_path)
    cursor_root = tmp_path / "cursor-skills"
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(cursor_root))
    client = _client(tmp_path, monkeypatch)
    res = client.post("/api/deploy", json={"target": "cursor", "skill": "pdf", "mode": "local"})
    assert res.status_code == 200
    assert res.json()["mode"] == "local"
    assert (cursor_root / "pdf" / "SKILL.md").is_file()
    assert pack.is_dir()


def test_git_deploy_hidden_not_present(tmp_path: Path, monkeypatch) -> None:
    _copy_pack(tmp_path)
    client = _client(tmp_path, monkeypatch)
    res = client.post("/api/deploy", json={"target": "git", "skill": "pdf", "mode": "git"})
    assert res.status_code == 404


def test_ui_static_attaches_without_fastapi_error(tmp_path: Path, monkeypatch) -> None:
    from skillgate_ai.server import attach_static, web_static_dir

    monkeypatch.setenv("SKILLGATE_MODE", "local")
    app = create_app(root=tmp_path)
    attach_static(app)
    client = TestClient(app)
    status = client.get("/api/status")
    assert status.status_code == 200
    assert status.json()["mode"] == "local"
    assert status.json()["auth_required"] is False
    page = client.get("/")
    dist = web_static_dir()
    if dist is not None and (dist / "index.html").is_file():
        assert page.status_code == 200
        assert "<html" in page.text.lower()
        spa = client.get("/skills/pdf")
        assert spa.status_code == 200
        assert "<html" in spa.text.lower()
    else:
        assert page.status_code == 503
        assert "pnpm build" in page.text


def _skill_md(name: str) -> str:
    return (
        f"---\nname: {name}\n"
        "description: Intake path tests. Use when the user asks for intake path coverage.\n"
        "---\n\n# Steps\n1. Read input\n"
    )


def test_paste_display_name_uses_folder_slug(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    res = client.post("/api/skills/paste", json={"markdown": _skill_md("Idea brainstorming")})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["slug"] == "idea-brainstorming"
    assert data["id"] == "idea-brainstorming"
    assert data["name"] == "Idea brainstorming"
    dest = tmp_path / "skills" / "idea-brainstorming"
    assert dest.is_dir()
    assert (dest / "SKILL.md").is_file()
    assert (dest / "evals" / "cases.yaml").is_file()
    listed = client.get("/api/skills")
    assert listed.status_code == 200
    names = {item["name"] for item in listed.json()["skills"]}
    assert "Idea brainstorming" in names


def test_paste_rejects_names_that_escape_skills(tmp_path: Path, monkeypatch) -> None:
    marker = tmp_path / "keep-me.txt"
    marker.write_text("safe\n", encoding="utf-8")
    client = _client(tmp_path, monkeypatch)
    for name in ("/tmp/pwn", "..", "../escape", "foo/bar"):
        res = client.post("/api/skills/paste", json={"markdown": _skill_md(name)})
        assert res.status_code == 400, name
        detail = res.json()["detail"]
        message = detail["message"] if isinstance(detail, dict) else str(detail)
        assert "lowercase" in message.lower() or "name" in message.lower()
    assert marker.is_file()
    assert marker.read_text(encoding="utf-8") == "safe\n"
    assert not Path("/tmp/pwn").exists() or not (Path("/tmp/pwn") / "SKILL.md").is_file()
    skills = tmp_path / "skills"
    if skills.is_dir():
        assert ".." not in {child.name for child in skills.iterdir()}


def test_zip_skips_dotdot_and_absolute_members(tmp_path: Path, monkeypatch) -> None:
    marker = tmp_path / "keep-me.txt"
    marker.write_text("safe\n", encoding="utf-8")
    client = _client(tmp_path, monkeypatch)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(
            "../SKILL.md",
            _skill_md("pwn"),
        )
        archive.writestr("/tmp/pwn/SKILL.md", _skill_md("pwn"))
        archive.writestr("../../outside.txt", "nope\n")
    res = client.post(
        "/api/skills/upload",
        files={"file": ("evil.zip", buf.getvalue(), "application/zip")},
    )
    assert res.status_code == 400
    assert marker.is_file()
    assert marker.read_text(encoding="utf-8") == "safe\n"
    assert not (tmp_path / "outside.txt").is_file()
    assert not (tmp_path.parent / "outside.txt").is_file()


def test_zip_keeps_valid_skill_and_drops_traversal_members(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("safe-skill/SKILL.md", _skill_md("safe-skill"))
        archive.writestr("safe-skill/../../outside.txt", "pwn\n")
        archive.writestr("../escape.txt", "no\n")
    res = client.post(
        "/api/skills/upload",
        files={"file": ("safe-skill.zip", buf.getvalue(), "application/zip")},
    )
    assert res.status_code == 200
    dest = tmp_path / "skills" / "safe-skill"
    assert (dest / "SKILL.md").is_file()
    assert "safe-skill" in (dest / "SKILL.md").read_text(encoding="utf-8")
    assert not (tmp_path / "outside.txt").is_file()
    assert not (tmp_path / "escape.txt").is_file()
    assert not (tmp_path.parent / "outside.txt").is_file()
    assert list(dest.rglob("outside.txt")) == []


def test_local_gate_tryout_stays_pending() -> None:
    assert local_gate(True, status="done", tryout=True) == (
        "pending",
        "Single-check runs do not unlock Deploy.",
    )
    row = history_row_to_run(
        {"run_id": "try-1", "passed": True, "report": {"tryout": True, "task_count": 1}},
        Path("/tmp/pdf"),
    )
    assert row["tryout"] is True
    assert row["gate_decision"] == "pending"


def test_tryout_history_does_not_unlock_deploy(tmp_path: Path, monkeypatch) -> None:
    pack = _copy_pack(tmp_path)
    hist_dir = pack / "evals" / "history"
    for path in hist_dir.glob("*.jsonl"):
        path.unlink()
    append_eval(
        pack,
        run_id="try-pass",
        passed=True,
        report={"tryout": True, "skill": "pdf", "task_count": 1},
    )
    client = _client(tmp_path, monkeypatch)
    hist = client.get("/api/history", params={"skill": "pdf"}).json()
    assert hist["gate"] == "pending"
    assert hist["last_run"] is None
    skill = client.get("/api/skills/pdf").json()["skill"]
    assert skill["gate"] == "pending"
    assert skill["last_run"] is None

    append_eval(
        pack,
        run_id="full-pass",
        passed=True,
        report={"skill": "pdf", "task_count": 8},
    )
    hist = client.get("/api/history", params={"skill": "pdf"}).json()
    assert hist["gate"] == "cleared"
    assert hist["last_run"]["id"] == "full-pass"

    append_eval(
        pack,
        run_id="try-later",
        passed=True,
        report={"tryout": True, "skill": "pdf", "task_count": 1},
    )
    hist = client.get("/api/history", params={"skill": "pdf"}).json()
    assert hist["gate"] == "cleared"
    assert hist["last_run"]["id"] == "full-pass"
    skill = client.get("/api/skills/pdf").json()["skill"]
    assert skill["gate"] == "cleared"
    assert skill["last_run"]["id"] == "full-pass"


def test_generate_sample_writes_fixture(tmp_path: Path, monkeypatch) -> None:
    _copy_pack(tmp_path)
    client = _client(tmp_path, monkeypatch)
    res = client.post(
        "/api/skills/pack-file",
        json={"skill": "pdf", "generate": True, "prompt": "Extract notes from a text file"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["file"]
    written = tmp_path / "skills" / "pdf" / body["file"]["src"]
    assert written.is_file()
    photo = client.post(
        "/api/skills/pack-file",
        json={"skill": "pdf", "generate": True, "prompt": "Read the photo scan of the invoice"},
    )
    assert photo.status_code == 200
    assert photo.json()["needs_upload"] is True
    assert photo.json()["file"] is None
