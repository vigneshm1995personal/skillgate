from __future__ import annotations

import io
import json
import shutil
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from skillgate_ai.api import create_app
from skillgate_ai.api_payloads import history_row_to_run, local_gate, scrub_config
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
    return TestClient(app, base_url="http://127.0.0.1:8765")


def test_status_missing_key_hint_is_ui_wording(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    data = client.get("/api/status").json()
    assert data["has_key"] is False
    hint = (data.get("missing_key_hint") or "").lower()
    assert "settings" in hint
    assert "skillgate" not in hint
    assert "skillgate ui" not in hint
    assert "keys set" not in hint
    assert "skillgate_openai" not in hint
    assert "--key-env" not in hint
    assert "openai_api_key" not in hint


def test_pack_file_outside_skill_is_400(tmp_path: Path, monkeypatch) -> None:
    _copy_pack(tmp_path)
    client = _client(tmp_path, monkeypatch)
    escaped = client.post(
        "/api/skills/pack-file",
        json={"skill": "pdf", "path": "../../outside.txt", "content": "nope"},
    )
    assert escaped.status_code == 400, escaped.text
    detail = escaped.json()["detail"]
    message = detail.get("message") if isinstance(detail, dict) else str(detail)
    assert message
    assert "traceback" not in str(escaped.json()).lower()
    assert not (tmp_path / "outside.txt").exists()


def test_status_includes_build_for_qa(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_BUILD", "deadbeefcafebabe")
    client = _client(tmp_path, monkeypatch)
    data = client.get("/api/status").json()
    from skillgate_ai import __version__

    assert data["version"] == __version__
    assert data["build"] == "deadbeefcafe"


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


def test_run_without_key_is_conflict(tmp_path: Path, monkeypatch) -> None:
    _copy_pack(tmp_path)
    client = _client(tmp_path, monkeypatch)
    gen = client.post("/api/evals/generate", json={"skill": "pdf"})
    checks = gen.json()["checks"]
    started = client.post(
        "/api/runs",
        json={"skill": "pdf", "checks": checks},
    )
    assert started.status_code == 409
    detail = started.json()["detail"]
    assert "No agent is available" in (detail.get("message") or "")
    assert "skillgate keys set" in (detail.get("hint") or "")
    hint = detail.get("hint") or ""
    assert "SKILLGATE_" not in hint
    assert "--key-env" not in hint
    assert "skillgate ui" not in hint


def test_settings_keys_write_vault(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    listed = client.get("/api/settings/keys")
    assert listed.status_code == 200
    assert listed.json()["keys"]["OPENAI_API_KEY"]["set"] is False
    saved = client.put("/api/settings/keys/OPENAI_API_KEY", json={"value": "sk-test-local"})
    assert saved.status_code == 200
    assert saved.json()["keys"]["OPENAI_API_KEY"]["from_vault"] is True
    vault = (tmp_path / ".skillgate" / "keys").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-test-local" in vault
    assert not (tmp_path / ".env").exists() or "sk-test-local" not in (
        tmp_path / ".env"
    ).read_text(encoding="utf-8")
    cleared = client.delete("/api/settings/keys/OPENAI_API_KEY")
    assert cleared.status_code == 200
    assert "sk-test-local" not in (tmp_path / ".skillgate" / "keys").read_text(encoding="utf-8")


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
    from skillgate_ai.history import append_eval

    append_eval(pack, run_id="green", passed=True)
    cursor_root = tmp_path / "cursor-skills"
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(cursor_root))
    from conftest import enable_cursor_agent

    enable_cursor_agent(monkeypatch, tmp_path)
    client = _client(tmp_path, monkeypatch)
    res = client.post("/api/deploy", json={"target": "cursor", "skill": "pdf", "mode": "local"})
    assert res.status_code == 200
    assert res.json()["mode"] == "local"
    assert (cursor_root / "pdf" / "SKILL.md").is_file()
    assert not (cursor_root / "pdf" / "evals").exists()
    assert pack.is_dir()


def test_deploy_never_checked_without_key_names_missing_check(
    tmp_path: Path, monkeypatch
) -> None:
    _copy_pack(tmp_path)
    client = _client(tmp_path, monkeypatch)
    res = client.post("/api/deploy", json={"target": "cursor", "skill": "pdf", "mode": "local"})
    assert res.status_code == 400, res.text
    blob = json.dumps(res.json()).lower()
    assert "run the checks first" in blob
    assert "no model key found" not in blob
    assert not (tmp_path / "cursor-skills" / "pdf").exists()


def test_deploy_without_key_is_409_even_after_green(tmp_path: Path, monkeypatch) -> None:
    pack = _copy_pack(tmp_path)
    append_eval(pack, run_id="green", passed=True)
    client = _client(tmp_path, monkeypatch)
    res = client.post("/api/deploy", json={"target": "cursor", "skill": "pdf", "mode": "local"})
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    blob = json.dumps(detail).lower()
    assert "no model key" in blob or "key" in blob
    assert "keys set" in blob or "settings" in blob
    assert not (tmp_path / "cursor-skills" / "pdf").exists()


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
    client = TestClient(app, base_url="http://127.0.0.1:8765")
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


_LEAKY_JUDGE = {
    "provider": "openai",
    "backend": "decisions",
    "display_name": "OpenAI Decisions via Vercel AI Gateway (your key)",
    "model": "gpt-6-luna",
    "chosen": "false",
}
_LEAKY_CONFIG = {
    "harness": "llm",
    "model": "openai/gpt-4o-mini",
    "label": (
        "LLM · openai/gpt-4o-mini via gateway · 300s · "
        "OpenAI Decisions via Vercel AI Gateway (your key)"
    ),
    "applied": {"via_gateway": True, "model": False},
    "judge": _LEAKY_JUDGE,
}
_LEAKY_REPORT = {
    "skill": "pdf",
    "harness": "llm",
    "task_count": 1,
    "passed": True,
    "scored_by": "Scored by OpenAI Decisions",
    "config": _LEAKY_CONFIG,
    "tasks": [
        {
            "id": "extract-hello",
            "passed": True,
            "check_kind": "openai",
            "judge": dict(_LEAKY_JUDGE),
        }
    ],
}


def _assert_browser_payload_is_scrubbed(payload: object) -> None:
    blob = json.dumps(payload)
    lower = blob.lower()
    assert "config_label_raw" not in blob
    assert "check_kind" not in blob
    assert "gpt-6-luna" not in lower
    assert "openai decisions" not in lower
    assert "vercel ai gateway" not in lower
    assert "openai/gpt-4o-mini" not in lower
    assert "via_gateway" not in lower
    assert '"provider": "openai"' not in blob
    assert '"provider": "compatible"' not in blob
    assert '"backend": "decisions"' not in blob
    assert '"display_name": "openai"' not in lower
    assert '"display_name": "compatible"' not in lower


def test_browser_api_scrubs_provider_model_names(tmp_path: Path, monkeypatch) -> None:
    pack = _copy_pack(tmp_path)
    hist_dir = pack / "evals" / "history"
    for path in hist_dir.glob("*.jsonl"):
        path.unlink()
    append_eval(
        pack,
        run_id="auto-judge",
        passed=True,
        report=_LEAKY_REPORT,
        config=_LEAKY_CONFIG,
    )
    append_eval(
        pack,
        run_id="chosen-jev",
        passed=True,
        report={
            "skill": "pdf",
            "harness": "llm",
            "task_count": 1,
            "passed": True,
            "config": {
                "harness": "llm",
                "label": "LLM · 300s · Jev",
                "judge": {
                    "provider": "jev",
                    "display_name": "Jev",
                    "model": "jev-hidden-model",
                    "chosen": True,
                },
            },
            "tasks": [
                {
                    "id": "extract-hello",
                    "passed": True,
                    "check_kind": "openai",
                    "judge": {
                        "provider": "jev",
                        "display_name": "Jev",
                        "model": "jev-hidden-model",
                        "chosen": True,
                    },
                }
            ],
        },
        config={
            "harness": "llm",
            "label": "LLM · 300s · Jev",
            "judge": {
                "provider": "jev",
                "display_name": "Jev",
                "model": "jev-hidden-model",
                "chosen": True,
            },
        },
    )
    append_eval(
        pack,
        run_id="chosen-other",
        passed=True,
        report={
            "skill": "pdf",
            "harness": "llm",
            "task_count": 1,
            "passed": True,
            "config": {
                "harness": "llm",
                "model": "gpt-4o-mini",
                "label": "LLM · Other",
                "judge": {
                    "provider": "compatible",
                    "backend": "decisions",
                    "display_name": "Other",
                    "model": "hidden-compatible-model",
                    "chosen": True,
                },
            },
            "tasks": [
                {
                    "id": "extract-hello",
                    "passed": True,
                    "check_kind": "openai",
                    "judge": {
                        "provider": "compatible",
                        "backend": "decisions",
                        "display_name": "Other",
                        "model": "hidden-compatible-model",
                        "chosen": True,
                    },
                }
            ],
        },
        config={
            "harness": "llm",
            "model": "gpt-4o-mini",
            "judge": {
                "provider": "compatible",
                "backend": "decisions",
                "display_name": "Other",
                "model": "hidden-compatible-model",
                "chosen": True,
            },
        },
    )
    disk = "".join(path.read_text(encoding="utf-8") for path in hist_dir.glob("*.jsonl"))
    assert "gpt-6-luna" in disk
    assert "check_kind" in disk
    assert "OpenAI Decisions" in disk
    assert "jev-hidden-model" in disk
    assert '"provider": "compatible"' in disk

    client = _client(tmp_path, monkeypatch)
    hist = client.get("/api/history", params={"skill": "pdf"}).json()
    skill = client.get("/api/skills/pdf").json()
    listed = client.get("/api/skills").json()
    auto_run = client.get("/api/runs/auto-judge").json()
    jev_run = client.get("/api/runs/chosen-jev").json()
    other_run = client.get("/api/runs/chosen-other").json()
    _assert_browser_payload_is_scrubbed(hist)
    _assert_browser_payload_is_scrubbed(skill)
    _assert_browser_payload_is_scrubbed(listed)
    _assert_browser_payload_is_scrubbed(auto_run)
    _assert_browser_payload_is_scrubbed(jev_run)
    _assert_browser_payload_is_scrubbed(other_run)
    assert "jev-hidden-model" not in json.dumps(jev_run)
    auto_row = next(item for item in hist["runs"] if item["id"] == "auto-judge")
    auto_skill = next(
        item
        for item in (skill.get("runs") or [skill.get("last_run")])
        if item and item.get("id") == "auto-judge"
    )
    assert auto_skill["report"]["scored_by"] == "Scored by the judge"
    assert auto_row["report"]["scored_by"] == "Scored by the judge"
    assert hist["last_run"]["config_label"] == "Scored by Other"
    assert auto_row["config_label"] == "Scored by the judge"
    assert auto_row["config"]["label"] == "Scored by the judge"
    assert auto_row["config"]["judge"]["display_name"] == "the judge"
    assert "model" not in auto_row["config"]["judge"]
    assert "provider" not in auto_row["config"]["judge"]
    assert "backend" not in auto_row["config"]["judge"]
    assert "model" not in auto_row["config"]
    assert jev_run["config"]["judge"]["display_name"] == "Jev"
    assert "provider" not in jev_run["config"]["judge"]
    assert jev_run["config_label"] == "Scored by Jev"
    assert other_run["config"]["judge"]["display_name"] == "Other"
    assert "provider" not in other_run["config"]["judge"]
    assert other_run["config_label"] == "Scored by Other"


def test_scrub_config_keeps_live_agent_model(tmp_path: Path, monkeypatch) -> None:
    del tmp_path, monkeypatch
    live = scrub_config(
        {
            "harness": "claude",
            "model": "claude-opus-5-5",
            "applied": {"model": False},
            "judge": {
                "provider": "openai",
                "backend": "decisions",
                "display_name": "OpenAI (your key)",
                "model": "gpt-6-luna",
            },
        }
    )
    assert live["model"] == "claude-opus-5-5"
    assert "gpt-6-luna" not in json.dumps(live)
    assert "model" not in live["judge"]
    assert "provider" not in live["judge"]

    legacy = scrub_config({"harness": "llm", "model": "openai/gpt-4o-mini"})
    assert "model" not in legacy


def test_browser_api_keeps_couldnt_score_copy(tmp_path: Path, monkeypatch) -> None:
    pack = _copy_pack(tmp_path)
    hist_dir = pack / "evals" / "history"
    for path in hist_dir.glob("*.jsonl"):
        path.unlink()
    append_eval(
        pack,
        run_id="failed-score",
        passed=False,
        report={
            **_LEAKY_REPORT,
            "passed": False,
            "scored_by": "OpenAI couldn't score this run. Your OpenAI account is out of credits.",
        },
        config=_LEAKY_CONFIG,
    )
    client = _client(tmp_path, monkeypatch)
    run = client.get("/api/runs/failed-score").json()
    line = run["report"]["scored_by"]
    assert "couldn't score this run" in line.lower()
    assert "openai decisions" not in line.lower()
    assert line.startswith("The judge couldn't score this run.")


def test_settings_keys_label_ai_gateway_api_key(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    listed = client.get("/api/settings/keys")
    blob = json.dumps(listed.json())
    assert "AI_GATEWAY_API_KEY" in blob
    saved = client.put("/api/settings/keys/AI_GATEWAY_API_KEY", json={"value": "gw-test-local"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["keys"]["AI_GATEWAY_API_KEY"]["from_vault"] is True
    vault = (tmp_path / ".skillgate" / "keys").read_text(encoding="utf-8")
    assert "AI_GATEWAY_API_KEY=gw-test-local" in vault
    judge = client.get("/api/settings/judge").json()["judge"]
    assert "decisions_path" not in judge


def test_import_dataset_preview_and_commit(tmp_path: Path, monkeypatch) -> None:
    pack = _copy_pack(tmp_path)
    client = _client(tmp_path, monkeypatch)
    sample = (ROOT / "docs" / "samples" / "dataset-import.csv").read_bytes()
    preview = client.post(
        "/api/evals/import-dataset",
        data={
            "skill": "pdf",
            "dry_run": "true",
            "confirm": "false",
            "on_conflict": "fail",
        },
        files={"file": ("rows.csv", sample, "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["format"] == "csv"
    assert body["imported_count"] == 1
    assert body["dry_run"] is True
    before = (pack / "evals" / "cases.yaml").read_text(encoding="utf-8")
    commit = client.post(
        "/api/evals/import-dataset",
        data={
            "skill": "pdf",
            "dry_run": "false",
            "confirm": "true",
            "on_conflict": "fail",
        },
        files={"file": ("rows.csv", sample, "text/csv")},
    )
    assert commit.status_code == 200, commit.text
    after = (pack / "evals" / "cases.yaml").read_text(encoding="utf-8")
    assert after != before
    assert "csv-smoke" in after


def test_pin_refuses_seed_prompt_rewrite(tmp_path: Path, monkeypatch) -> None:
    pack = _copy_pack(tmp_path)
    before = (pack / "evals" / "cases.yaml").read_text(encoding="utf-8")
    client = _client(tmp_path, monkeypatch)
    res = client.post(
        "/api/evals/pin",
        json={
            "skill": "pdf",
            "checks": [
                {
                    "id": "extract-hello",
                    "prompt": "HACKED via API",
                    "should_trigger": True,
                }
            ],
        },
    )
    assert res.status_code == 400, res.text
    detail = res.json()["detail"]
    message = detail.get("message") if isinstance(detail, dict) else str(detail)
    assert "original checks stay" in message.lower()
    after = (pack / "evals" / "cases.yaml").read_text(encoding="utf-8")
    assert after == before
    assert "HACKED via API" not in after


def test_pin_validates_judge_before_writing_cases(tmp_path: Path, monkeypatch) -> None:
    pack = _copy_pack(tmp_path)
    before = (pack / "evals" / "cases.yaml").read_text(encoding="utf-8")
    client = _client(tmp_path, monkeypatch)
    res = client.post(
        "/api/evals/pin",
        json={
            "skill": "pdf",
            "checks": [
                {
                    "id": "brand-new-check",
                    "prompt": "A new check that must not be saved.",
                    "should_trigger": True,
                }
            ],
            "pack_judge": {
                "extra_questions": [
                    {
                        "id": "bad_fail",
                        "type": "predicate",
                        "ask": "Broken?",
                        "on_fail": "nope",
                    }
                ]
            },
        },
    )
    assert res.status_code == 400, res.text
    detail = res.json()["detail"]
    message = detail.get("message") if isinstance(detail, dict) else str(detail)
    assert "input should be" not in message.lower()
    assert "block or warn" not in message.lower()
    assert "Fail the check" in message or "Warn only" in message
    after = (pack / "evals" / "cases.yaml").read_text(encoding="utf-8")
    assert after == before
    assert "brand-new-check" not in after


def test_pin_merges_pack_judge_extras(tmp_path: Path, monkeypatch) -> None:
    pack = _copy_pack(tmp_path)
    from skillgate_ai.case_pack import load_case_pack, save_pack_judge

    save_pack_judge(
        pack,
        {
            "extra_questions": [
                {
                    "id": "cli_extra",
                    "type": "predicate",
                    "ask": "CLI question?",
                    "on_fail": "block",
                    "pass_if": {"gte": 0.8},
                }
            ]
        },
    )
    client = _client(tmp_path, monkeypatch)
    res = client.post(
        "/api/evals/pin",
        json={
            "skill": "pdf",
            "checks": [
                {
                    "id": "extract-hello",
                    "prompt": "Extract the text from hello.pdf and save it to output/extracted.txt",
                    "should_trigger": True,
                }
            ],
            "pack_judge": {
                "extra_questions": [
                    {
                        "id": "ui_extra",
                        "type": "predicate",
                        "ask": "UI question?",
                        "on_fail": "block",
                        "pass_if": {"gte": 0.8},
                    }
                ]
            },
        },
    )
    assert res.status_code == 200, res.text
    loaded = load_case_pack(pack)
    assert loaded is not None
    ids = [q.id for q in (loaded.judge.extra_questions if loaded.judge else [])]
    assert "cli_extra" in ids
    assert "ui_extra" in ids
    removed = client.post(
        "/api/evals/pin",
        json={
            "skill": "pdf",
            "checks": [
                {
                    "id": "extract-hello",
                    "prompt": "Extract the text from hello.pdf and save it to output/extracted.txt",
                    "should_trigger": True,
                }
            ],
            "pack_judge": {
                "extra_questions": [
                    {
                        "id": "ui_extra",
                        "type": "predicate",
                        "ask": "UI question?",
                        "on_fail": "block",
                        "pass_if": {"gte": 0.8},
                    }
                ],
                "removed_extra_ids": ["cli_extra"],
            },
        },
    )
    assert removed.status_code == 200, removed.text
    loaded = load_case_pack(pack)
    ids = [q.id for q in (loaded.judge.extra_questions if loaded and loaded.judge else [])]
    assert "cli_extra" not in ids
    assert "ui_extra" in ids


def test_status_hides_gateway_fields(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    data = client.get("/api/status").json()
    assert "has_gateway_key" not in data
    assert "live_backends" not in data
    assert "OpenAI-compatible" not in json.dumps(data.get("available_harnesses"))
    harness_auth = data.get("harness_auth") or {}
    assert "has_gateway_api_key" not in harness_auth
    assert data["has_key"] is False


def test_pack_file_cannot_wipe_seed_cases(tmp_path: Path, monkeypatch) -> None:
    pack = _copy_pack(tmp_path)
    original = (pack / "evals" / "cases.yaml").read_text(encoding="utf-8")
    client = _client(tmp_path, monkeypatch)
    res = client.post(
        "/api/skills/pack-file",
        json={"skill": "pdf", "path": "evals/cases.yaml", "content": "schema: 1\nskill: pdf\ncases: []\n"},
    )
    assert res.status_code == 400, res.text
    detail = res.json()["detail"]
    message = detail.get("message") if isinstance(detail, dict) else str(detail)
    assert "original checks stay" in message.lower()
    assert "seed checks cannot be removed" not in message.lower()
    assert (pack / "evals" / "cases.yaml").read_text(encoding="utf-8") == original


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


def test_root_level_example_pack_is_listed_and_history_shows_cli_runs(
    tmp_path: Path, monkeypatch
) -> None:
    pack = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    append_eval(
        pack,
        run_id="cli-1",
        passed=True,
        report={"skill": "pdf", "harness": "llm", "task_count": 1, "passed": True},
        config={"harness": "llm", "model": "openai/gpt-4o-mini"},
    )
    client = _client(tmp_path, monkeypatch)
    names = {item["name"] for item in client.get("/api/skills").json()["skills"]}
    assert "pdf" in names
    hist = client.get("/api/history").json()
    ids = [item.get("id") for item in hist.get("timeline") or []]
    assert "cli-1" in ids


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
