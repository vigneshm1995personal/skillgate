from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from skillgate_ai import __version__
from skillgate_ai.api import create_app
from skillgate_ai.demo_files import ensure_demo_pdfs
from skillgate_ai.history import append_eval
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
    return TestClient(create_app(root=paths["root"]), base_url="http://127.0.0.1:8765")


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
    assert body["skills"] == []

    status = client.get("/api/status")
    assert status.status_code == 200
    assert status.json().get("version") == __version__
    hint = (status.json().get("missing_key_hint") or "").lower()
    message = (status.json().get("missing_key_message") or "").lower()
    assert "skillgate check" not in hint
    assert "skillgate check" not in message
    assert "skillgate" not in hint
    assert "keys set" not in hint
    assert "--key-env" not in hint
    assert "skillgate_" not in hint

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

    missing_choice = client.post("/api/skills/import", json={})
    assert missing_choice.status_code == 400

    cursor_only = client.post("/api/skills/import", json={"sources": ["cursor"]})
    assert cursor_only.status_code == 200
    assert (paths["root"] / "skills" / "pdf" / "SKILL.md").is_file()
    assert not (paths["root"] / "skills" / "idea-brainstorming").exists()
    assert not (paths["root"] / "skills" / "vercel-react-best-practices").exists()

    imported = client.post(
        "/api/skills/import",
        json={"sources": ["codex", "claude"]},
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
    listed_skills = after.json()["skills"]
    names = {item["name"] for item in listed_skills}
    slugs = {item.get("slug") or item["id"] for item in listed_skills}
    assert "Idea brainstorming" in names
    assert "pdf" in slugs
    assert "web-design-guidelines" in slugs
    assert "idea-brainstorming" in slugs
    assert "vercel-react-best-practices" in slugs
    broken = next(item for item in listed_skills if item.get("slug") == "broken-notes")
    assert broken.get("warning")
    first_count = len(listed_skills)

    again = client.post("/api/skills/import", json={"sources": ["cursor"]})
    assert again.status_code == 200
    assert again.json()["imported"] == []
    assert again.json()["skipped"]
    second = client.get("/api/skills")
    assert len(second.json()["skills"]) == first_count

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
        },
    )
    assert idea_run.status_code == 409
    idea_detail = idea_run.json().get("detail") or {}
    assert "No model key" in (idea_detail.get("message") or "")
    assert idea_detail.get("hint") == "Add a model key in Settings or run `skillgate keys set`"
    assert "SKILLGATE_" not in (idea_detail.get("hint") or "")
    assert "--key-env" not in (idea_detail.get("hint") or "")

    gen = client.post("/api/evals/generate", json={"skill": "pdf"})
    assert gen.status_code == 200
    checks = gen.json()["checks"]
    assert checks
    hello = [item for item in checks if item.get("id") == "extract-hello"]
    assert hello
    assert hello[0].get("golden_path")
    pin_hello = client.post(
        "/api/evals/pin",
        json={
            "skill": "pdf",
            "checks": [
                {
                    "id": "extract-hello",
                    "prompt": hello[0]["prompt"],
                    "should_trigger": True,
                    "output_path": hello[0].get("output_path") or "output/extracted.txt",
                    "golden_path": hello[0].get("golden_path"),
                }
            ],
        },
    )
    assert pin_hello.status_code == 200, pin_hello.text
    disk_pin = client.post(
        "/api/evals/pin",
        json={
            "skill": "pdf",
            "checks": [
                {
                    "id": "extract-hello",
                    "prompt": hello[0]["prompt"],
                    "should_trigger": True,
                    "output_path": "output/extracted.txt",
                }
            ],
        },
    )
    assert disk_pin.status_code == 200, disk_pin.text
    expected_pin = client.post(
        "/api/evals/pin",
        json={
            "skill": "pdf",
            "checks": [
                {
                    "id": "dataset-expected",
                    "prompt": "Extract the text from hello.pdf.",
                    "should_trigger": True,
                    "output_path": "output/extracted.txt",
                    "contains": "Hello Skill Gate",
                }
            ],
        },
    )
    assert expected_pin.status_code == 200, expected_pin.text
    run_checks = hello or checks[:1]
    started = client.post(
        "/api/runs",
        json={"skill": "pdf", "checks": run_checks},
    )
    assert started.status_code == 409
    pdf_detail = started.json().get("detail") or {}
    assert "No model key" in (pdf_detail.get("message") or "")

    append_eval(dest, run_id="green-pdf", passed=True)
    append_eval(idea, run_id="green-idea", passed=True)

    history = client.get("/api/history", params={"skill": "pdf"})
    assert history.status_code == 200
    hist = history.json()
    assert hist["runs"] or hist["timeline"]
    harness_blob = " ".join(
        str(item.get("config_label") or item.get("harness") or "")
        for item in (hist.get("timeline") or [])
    )
    assert "demo" not in harness_blob.lower()
    assert "built-in checker" not in harness_blob.lower()

    deploy = client.post(
        "/api/deploy",
        json={"target": "cursor", "skill": "pdf", "mode": "local"},
    )
    assert deploy.status_code == 200
    installed = paths["cursor"] / "pdf"
    assert (installed / "SKILL.md").is_file()
    assert (installed / "scripts" / "extract_text.py").is_file()
    assert not (installed / "evals" / "goldens" / "extract-hello.txt").is_file()
    after_deploy = client.get("/api/skills/pdf")
    assert after_deploy.status_code == 200
    skill_body = after_deploy.json()["skill"]
    assert skill_body["deploy_count"] >= 1
    assert skill_body["last_deploy"]
    assert skill_body["last_deploy"]["target"] == "cursor"
    hist_after = client.get("/api/history", params={"skill": "pdf"}).json()
    assert hist_after["deploys"]
    assert hist_after["last_deploy"]["target"] == "cursor"
    assert hist_after["deploys"][0]["status"] in {"installed", "ok"}
    deploy_labels = [
        item.get("label")
        for item in (hist_after.get("timeline") or [])
        if item.get("kind") == "deploy"
    ]
    assert "Install to Cursor" in deploy_labels
    assert "Install to cursor" not in deploy_labels

    idea_deploy = client.post(
        "/api/deploy",
        json={"target": "cursor", "skill": "idea-brainstorming", "mode": "local"},
    )
    assert idea_deploy.status_code == 200, idea_deploy.text
    idea_installed = paths["cursor"] / "idea-brainstorming"
    assert (idea_installed / "SKILL.md").is_file()
    assert "Idea brainstorming" in (idea_installed / "SKILL.md").read_text(encoding="utf-8")
    assert not (idea_installed / "evals").exists()


def test_pin_without_expected_offers_dataset_fix(tmp_path: Path, monkeypatch) -> None:
    paths = _fake_home(tmp_path)
    client = _client(paths, monkeypatch)
    folder = paths["root"] / "skills" / "notes"
    _write_skill(folder, "notes", "Take notes when the user asks.")
    res = client.post(
        "/api/evals/pin",
        json={
            "skill": "notes",
            "checks": [
                {
                    "id": "needs-expected",
                    "prompt": "Summarize the notes.",
                    "should_trigger": True,
                    "output_path": "output/result.txt",
                }
            ],
        },
    )
    assert res.status_code == 400
    detail = res.json().get("detail") or {}
    blob = f"{detail.get('message') or ''} {detail.get('hint') or ''}".lower()
    assert "expected output" in blob
    assert "yaml" not in blob
    assert "golden" not in blob


def test_react_ui_customer_copy() -> None:
    web = ROOT / "web" / "src"
    forbidden = (
        "~/.cursor",
        "evals/goldens",
        "cases.yaml",
        "Power user",
        "pack fixtures",
        "semver + version fingerprint",
        "evals/fixtures/*",
        ">Harness<",
        ">Stamp<",
        "Pin as baseline",
        "Pinned as baseline",
        "Pack files",
        "SKILLGATE_TASK",
        "Harness default",
        "Harness step",
        "this harness",
        ">Pinned<",
    )
    hits: list[str] = []
    for path in web.rglob("*"):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(ROOT))
        if "landing-page" in rel or ".test." in rel:
            continue
        for needle in forbidden:
            if needle == "SKILLGATE_TASK" and (
                path.suffix != ".tsx" or "skill-pack-browser" in rel
            ):
                continue
            if needle in text:
                hits.append(f"{rel}: {needle}")
        if (
            path.suffix == ".tsx"
            and "skill-pack-browser" not in rel
            and ("evals/goldens" in text or "evals/fixtures" in text)
        ):
            hits.append(f"{rel}: raw evals path")
        if 'Badge' in text and ">eval<" in text.lower():
            hits.append(f"{rel}: bare eval badge")
    assert hits == []
