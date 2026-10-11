from __future__ import annotations

import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

from skillgate_ai.api import create_app
from skillgate_ai.demo_files import ensure_demo_pdfs
from skillgate_ai.pack import copy_skill_pack

ROOT = Path(__file__).resolve().parents[1]


def _skill_md(name: str, description: str) -> str:
    return (
        f"---\nname: {name}\n"
        f"description: {description}\n"
        "---\n\n# Steps\n1. Read the request.\n2. Follow the skill.\n"
    )


def _write_skill(folder: Path, name: str, description: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        _skill_md(name, description),
        encoding="utf-8",
    )


def _fake_home(tmp_path: Path) -> dict[str, Path]:
    home = tmp_path / "home"
    cursor = home / ".cursor" / "skills"
    codex = home / ".codex" / "skills"
    claude = home / ".claude" / "skills"
    pdf = cursor / "pdf"
    shutil.copytree(
        ROOT / "skills" / "pdf",
        pdf,
        ignore=shutil.ignore_patterns("history"),
    )
    ensure_demo_pdfs(pdf / "evals" / "fixtures")
    _write_skill(
        cursor / "web-design-guidelines",
        "web-design-guidelines",
        "Apply web design guidelines when the user asks for UI or layout help.",
    )
    _write_skill(
        codex / "idea-brainstorming",
        "Idea brainstorming",
        "Brainstorm product ideas with the user when they ask for ideation.",
    )
    _write_skill(
        claude / "vercel-react-best-practices",
        "vercel-react-best-practices",
        "Apply Vercel React best practices when building React apps.",
    )
    _write_skill(
        cursor / "Design Tokens",
        "Design Tokens",
        "Apply design tokens when the user asks for color, type, or spacing.",
    )
    broken = cursor / "broken-notes"
    broken.mkdir(parents=True, exist_ok=True)
    (broken / "SKILL.md").write_text("# no header\n", encoding="utf-8")
    return {
        "home": home,
        "cursor": cursor,
        "codex": codex,
        "claude": claude,
        "root": tmp_path / "project",
    }


def _client(paths: dict[str, Path], monkeypatch) -> TestClient:
    paths["root"].mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SKILLGATE_MODE", "local")
    monkeypatch.setenv("HOME", str(paths["home"]))
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(paths["cursor"]))
    monkeypatch.setenv("SKILLGATE_CODEX_SKILLS", str(paths["codex"]))
    monkeypatch.setenv("SKILLGATE_CLAUDE_SKILLS", str(paths["claude"]))
    return TestClient(create_app(root=paths["root"]))


def _wait_run(client: TestClient, run_id: str, timeout: float = 120) -> dict:
    deadline = time.time() + timeout
    snapshot = None
    while time.time() < deadline:
        snapshot = client.get(f"/api/runs/{run_id}").json()
        if snapshot.get("status") != "running":
            return snapshot
        time.sleep(0.2)
    assert snapshot is not None
    return snapshot


def test_copy_skill_pack_keeps_goldens(tmp_path: Path) -> None:
    dest = tmp_path / "copied-pdf"
    copy_skill_pack(ROOT / "skills" / "pdf", dest, include_goldens=True)
    assert (dest / "evals" / "goldens" / "extract-hello.txt").is_file()
    assert (dest / "scripts" / "extract_text.py").is_file()


def test_fake_home_import_list_open_run_deploy(tmp_path: Path, monkeypatch) -> None:
    paths = _fake_home(tmp_path)
    client = _client(paths, monkeypatch)

    listed = client.get("/api/skills")
    assert listed.status_code == 200
    body = listed.json()
    assert body.get("catalog_error") is None
    skills = body["skills"]
    names = {item["name"] for item in skills}
    slugs = {item.get("slug") or item["id"] for item in skills}
    assert "pdf" in slugs
    assert "web-design-guidelines" in slugs
    assert "idea-brainstorming" in slugs
    assert "Idea brainstorming" in names
    assert "vercel-react-best-practices" in slugs
    broken = next(item for item in skills if item.get("slug") == "broken-notes")
    assert broken.get("warning")
    assert listed.status_code == 200

    status = client.get("/api/status")
    assert status.status_code == 200
    assert "skillgate check" not in (status.json().get("missing_key_hint") or "").lower()
    assert "skillgate check" not in (status.json().get("missing_key_message") or "").lower()

    sources = client.get("/api/skills/import-sources")
    assert sources.status_code == 200
    by_id = {item["id"]: item for item in sources.json()["sources"]}
    assert by_id["cursor"]["found"] is True
    assert by_id["cursor"]["count"] >= 2
    assert "Cursor's skills folder" in by_id["cursor"]["folder_label"]
    assert by_id["codex"]["found"] is True
    assert by_id["codex"]["count"] >= 1
    assert by_id["claude"]["found"] is True
    assert "~/.cursor" not in str(sources.json())

    imported = client.post(
        "/api/skills/import",
        json={"sources": ["cursor", "codex", "claude"]},
    )
    assert imported.status_code == 200
    dest = paths["root"] / "skills" / "pdf"
    assert (dest / "SKILL.md").is_file()
    assert (dest / "evals" / "goldens" / "extract-hello.txt").is_file()
    assert (dest / "scripts" / "extract_text.py").is_file()
    idea = paths["root"] / "skills" / "idea-brainstorming"
    assert (idea / "SKILL.md").is_file()
    assert "Idea brainstorming" in (idea / "SKILL.md").read_text(encoding="utf-8")
    tokens = paths["root"] / "skills" / "design-tokens"
    assert tokens.is_dir()
    assert (tokens / "SKILL.md").is_file()
    assert not (paths["root"] / "skills" / "Design Tokens").exists()

    after = client.get("/api/skills")
    assert after.status_code == 200
    assert after.json().get("catalog_error") is None
    names = {item["name"] for item in after.json()["skills"]}
    assert "Idea brainstorming" in names

    opened = client.get("/api/skills/pdf")
    assert opened.status_code == 200
    detail = opened.json()
    assert detail["skill"]["body"]
    paths_in_pack = [item["path"] for item in detail["pack_files"]]
    assert "SKILL.md" in paths_in_pack
    preview = client.get("/api/skills/pdf/pack-file", params={"path": "SKILL.md"})
    assert preview.status_code == 200
    assert "name:" in (preview.json().get("text") or "")

    idea_open = client.get("/api/skills/idea-brainstorming")
    assert idea_open.status_code == 200
    assert idea_open.json()["skill"]["name"] == "Idea brainstorming"
    assert idea_open.json()["skill"]["slug"] == "idea-brainstorming"

    idea_gen = client.post("/api/evals/generate", json={"skill": "idea-brainstorming"})
    assert idea_gen.status_code == 200
    idea_checks = idea_gen.json()["checks"] or [
        {
            "id": "should-trigger-1",
            "prompt": "Brainstorm product ideas for a notes app.",
            "should_trigger": True,
        }
    ]
    idea_run = client.post(
        "/api/runs",
        json={
            "skill": "idea-brainstorming",
            "checks": idea_checks[:1],
            "live": False,
            "demo": True,
        },
    )
    assert idea_run.status_code == 200
    idea_snap = _wait_run(client, idea_run.json()["id"])
    assert idea_snap["status"] == "done"
    assert idea_snap.get("error") in (None, {})
    assert (idea_snap.get("skill") or idea_snap["report"]["skill"]) == "idea-brainstorming"
    assert idea_snap["passed"] in {True, False}
    assert idea_snap["gate_decision"] in {"cleared", "blocked", "pending"}

    gen = client.post("/api/evals/generate", json={"skill": "pdf"})
    assert gen.status_code == 200
    checks = gen.json()["checks"]
    assert checks
    hello = [item for item in checks if item.get("id") == "extract-hello"]
    run_checks = hello or checks[:1]
    started = client.post(
        "/api/runs",
        json={"skill": "pdf", "checks": run_checks, "live": False, "demo": True},
    )
    assert started.status_code == 200
    snapshot = _wait_run(client, started.json()["id"])
    assert snapshot["status"] == "done"
    assert snapshot.get("error") in (None, {})
    report = snapshot["report"]
    assert report
    assert report["tasks"]
    assert report.get("scored_by")
    assert "Built-in checker" in (report.get("scored_by") or "")
    assert snapshot["passed"] in {True, False}
    assert snapshot["gate_decision"] in {"cleared", "blocked", "pending"}

    history = client.get("/api/history", params={"skill": "pdf"})
    assert history.status_code == 200
    assert history.json()["runs"] or history.json()["timeline"]

    deploy = client.post(
        "/api/deploy",
        json={"target": "cursor", "skill": "pdf", "mode": "local"},
    )
    assert deploy.status_code == 200
    installed = paths["cursor"] / "pdf"
    assert (installed / "SKILL.md").is_file()
    assert (installed / "evals" / "goldens" / "extract-hello.txt").is_file()

    idea_deploy = client.post(
        "/api/deploy",
        json={"target": "cursor", "skill": "idea-brainstorming", "mode": "local"},
    )
    assert idea_deploy.status_code == 200, idea_deploy.text
    idea_installed = paths["cursor"] / "idea-brainstorming"
    assert (idea_installed / "SKILL.md").is_file()
    assert "Idea brainstorming" in (idea_installed / "SKILL.md").read_text(encoding="utf-8")

    golden = dest / "evals" / "goldens" / "extract-hello.txt"
    if hello and golden.is_file():
        golden.unlink()
        started = client.post(
            "/api/runs",
            json={"skill": "pdf", "checks": hello, "live": False, "demo": True},
        )
        assert started.status_code == 200
        missing = _wait_run(client, started.json()["id"])
        assert missing["status"] == "done"
        assert missing.get("error") in (None, {})
        task = missing["report"]["tasks"][0]
        assert task["passed"] is False
        blob = " ".join(task.get("failures") or [])
        assert "expected output" in blob.lower()
        assert "evals/goldens" not in blob
