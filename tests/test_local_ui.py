from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from skillgate_ai.demo_files import ensure_demo_pdfs
from skillgate_ai.local_ui.server import start_background


def _request(method: str, url: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            parsed: dict | str
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = raw
            return resp.status, parsed
    except urllib.error.HTTPError as orig:
        raw = orig.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = raw
        return orig.code, parsed


def _poll_run(base: str, run_id: str, *, timeout: float = 120.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status, payload = _request("GET", f"{base}/api/runs/{run_id}")
        assert status == 200, payload
        assert isinstance(payload, dict)
        if payload.get("exit_code") is not None:
            return payload
        time.sleep(0.2)
    raise AssertionError(f"run {run_id} did not finish")


def test_app_js_is_valid_javascript() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "skillgate_ai"
        / "local_ui"
        / "static"
        / "app.js"
    )
    node = shutil.which("node")
    assert node, "node is required to syntax-check local_ui/static/app.js"
    proc = subprocess.run([node, "--check", str(path)], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    text = path.read_text(encoding="utf-8")
    assert "function route()" in text


def test_ui_meta_no_account(project_root: Path) -> None:
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        status, payload = _request("GET", f"{base}/api/meta")
        assert status == 200
        assert payload["account"] is False
        assert payload["has_any_key"] is False
        assert payload["demo_default"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_ui_pack_display_path_is_relative(project_root: Path) -> None:
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        status, payload = _request("GET", f"{base}/api/pack?path=skills/pdf")
        assert status == 200, payload
        assert payload["display_path"] == "skills/pdf"
        assert not str(payload["display_path"]).startswith("/")
        assert "oss-qa" not in payload["display_path"]
        status, meta = _request("GET", f"{base}/api/meta")
        assert status == 200
        assert "root" not in meta or not str(meta.get("root", "")).startswith("/")
    finally:
        server.shutdown()
        server.server_close()


def test_ui_copy_has_no_internal_jargon(project_root: Path) -> None:
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        bodies: dict[str, str] = {}
        for name in ("/", "/static/app.js", "/static/index.html", "/static/app.css"):
            req = urllib.request.Request(base + name)
            with urllib.request.urlopen(req, timeout=10) as resp:
                text = resp.read().decode("utf-8")
            bodies[name] = text
            lower = text.lower()
            assert "byollm" not in lower, name
            assert "oss-qa" not in lower, name
            assert "demo harness" not in lower, name
            assert "frontmatter" not in lower, name
            assert "evals/cases.yaml" not in lower, name
            assert "trigger-only" not in lower, name
            assert "/workspace" not in lower, name
            assert "pack schema" not in lower, name
            assert "jev" not in lower.split(), name
            assert "scaffold: false" not in lower, name
        js = bodies["/static/app.js"]
        html = bodies["/static/index.html"]
        css = bodies["/static/app.css"]
        assert "Name your skill" in js
        assert "What should it do?" in js
        assert "Create and run check" in js
        assert "See the checks" in js
        assert "Built-in checker. No API key needed." in js
        assert "Create a skill" in js
        assert "Try an example" in js
        assert "See a failing check" in js
        assert "Use your own API key (optional)" in js
        assert "live: false" in js
        assert "New skill" in html
        assert "Setup wizard" not in html
        assert "skillgate check" not in html.lower()
        assert "docker" not in html.lower()
        assert "SKILL.md frontmatter" not in js
        assert "Optional API key" not in js
        assert "<code>${esc(t.id)}</code>" not in js
        assert "function checkHeadline" in js
        assert "The skill should run for a matching request." in js
        assert "The skill should stay off for an unrelated request." in js
    finally:
        server.shutdown()
        server.server_close()


def test_ui_wizard_motion_is_wired_not_just_class_names(project_root: Path) -> None:
    js = (project_root / "src/skillgate_ai/local_ui/static/app.js").read_text(encoding="utf-8")
    css = (project_root / "src/skillgate_ai/local_ui/static/app.css").read_text(encoding="utf-8")
    assert "function swapPanel" in js
    assert "panel-leave" in js
    assert "panel-enter" in js
    assert "requestAnimationFrame" in js
    assert 'wizard.step = "checking"' in js
    create = js.split("async function createAndRun")[1].split("async function pollWizard")[0]
    assert create.index('wizard.step = "checking"') < create.index('"/api/packs"')
    assert create.index("await paintWizard()") < create.index('"/api/packs"')
    packs = __import__("re").search(r'api\("POST", "/api/packs", \{([^}]+)\}', js)
    assert packs, "wizard must POST /api/packs"
    assert "scaffold" not in packs.group(1)
    assert 'api("POST", "/api/check", { path: wizard.path, live: false })' in js
    assert "--motion: 300ms" in css
    assert "@keyframes panel-out" in css
    assert "@keyframes check-stroke" in css
    assert "@keyframes bar-slide" in css
    assert "prefers-reduced-motion" in css
    assert "min-height: 1.4em" in css


def test_ui_wizard_first_run_sequence_is_green(project_root: Path, tmp_path: Path) -> None:
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        status, created = _request(
            "POST",
            f"{base}/api/packs",
            {
                "parent": str(tmp_path),
                "name": "invoice-notes",
                "description": (
                    "Produce invoice-notes notes, extracts, and local file outputs. "
                    "Use when the user asks for invoice-notes, mentions invoices or documents, "
                    "or wants the documented invoice-notes workflow."
                ),
            },
        )
        assert status == 201, created
        assert "scaffold" not in created.get("skill", {})
        pack_path = Path(created["path"])
        assert (pack_path / "evals" / "cases.yaml").is_file()
        status, started = _request(
            "POST", f"{base}/api/check", {"path": created["path"], "live": False}
        )
        assert status == 202, started
        done = _poll_run(base, started["run_id"])
        assert done["exit_code"] == 0, done
        assert done["report"]["gate"] == "green"
        assert done["report"]["harness"] == "demo"
        notice = (done.get("demo_notice") or "").lower()
        assert "built-in checker" in notice
    finally:
        server.shutdown()
        server.server_close()


def test_ui_static_index(project_root: Path) -> None:
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        req = urllib.request.Request(base + "/")
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8")
        assert resp.status == 200
        assert "no account" in html.lower()
        assert "Skill Gate" in html
    finally:
        server.shutdown()
        server.server_close()


def test_ui_rejects_dotdot_and_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    (root / "skills").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "SKILL.md").write_text(
        "---\nname: outside\ndescription: not a workspace pack\n---\n",
        encoding="utf-8",
    )
    (root / "skills" / "escape").symlink_to(outside)
    server, base, _state = start_background(root=root, host="127.0.0.1", port=0)
    try:
        status, payload = _request("GET", f"{base}/api/pack?path=../outside")
        assert status == 400, payload
        blob = json.dumps(payload)
        assert "workspace" in blob.lower()
        assert "/outside" not in blob

        status, payload = _request("GET", f"{base}/api/pack?path=skills/escape")
        assert status == 400, payload
        assert "workspace" in json.dumps(payload).lower()
    finally:
        server.shutdown()
        server.server_close()


def test_ui_env_rejects_newlines(tmp_path: Path) -> None:
    server, base, _state = start_background(root=tmp_path, host="127.0.0.1", port=0)
    try:
        status, payload = _request(
            "PUT",
            f"{base}/api/env",
            {"OPENAI_API_KEY": "sk-line1\nMALICIOUS=1"},
        )
        assert status == 400, payload
        assert "line break" in str(payload).lower()
        env = tmp_path / ".env"
        assert not env.exists() or "MALICIOUS" not in env.read_text(encoding="utf-8")
    finally:
        server.shutdown()
        server.server_close()


def test_ui_name_mismatch_400(project_root: Path, tmp_path: Path) -> None:
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        status, payload = _request(
            "POST",
            f"{base}/api/packs",
            {"parent": str(tmp_path), "name": "my-skill", "folder": "other"},
        )
        assert status == 400, payload
        assert "must match" in str(payload).lower()
        assert "rename the folder or the `name` field so they match" in str(payload).lower()
    finally:
        server.shutdown()
        server.server_close()


def test_ui_check_sabotaged_json(project_root: Path, tmp_path: Path) -> None:
    dest = tmp_path / "pdf-sabotaged"
    shutil.copytree(project_root / "skills" / "pdf-sabotaged", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        status, started = _request("POST", f"{base}/api/check", {"path": str(dest)})
        assert status == 202, started
        assert started["exit_code"] is None
        done = _poll_run(base, started["run_id"])
        report = done["report"]
        assert done["exit_code"] == 1
        assert report["gate"] == "red"
        assert report["passed_count"] == 1
        paste = (report.get("advice") or {}).get("paste") or ""
        assert "grocery" not in paste.lower()
        assert "dinner" not in paste.lower()
        assert "pdf" in paste.lower()
    finally:
        server.shutdown()
        server.server_close()


def test_ui_apply_fix_then_green(project_root: Path, tmp_path: Path) -> None:
    dest = tmp_path / "pdf-sabotaged"
    shutil.copytree(project_root / "skills" / "pdf-sabotaged", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        _, started = _request("POST", f"{base}/api/check", {"path": str(dest)})
        red = _poll_run(base, started["run_id"])
        advice = (red["report"] or {}).get("advice") or {}
        description = advice.get("description") or advice.get("paste")
        status, applied = _request(
            "POST",
            f"{base}/api/pack/apply-advice",
            {"path": str(dest), "description": description},
        )
        assert status == 200, applied
        _, started2 = _request("POST", f"{base}/api/check", {"path": str(dest)})
        green = _poll_run(base, started2["run_id"])
        assert green["exit_code"] == 0, green
        assert green["report"]["gate"] == "green"
    finally:
        server.shutdown()
        server.server_close()


def test_ui_default_check_pdf_green_with_gateway_and_openai_keys(
    project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "gw-test-not-a-real-key")
    dest = tmp_path / "pdf"
    shutil.copytree(project_root / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        status, started = _request("POST", f"{base}/api/check", {"path": str(dest)})
        assert status == 202, started
        done = _poll_run(base, started["run_id"])
        report = done["report"] or {}
        assert done["exit_code"] == 0, done
        assert report.get("gate") == "green"
        assert report.get("harness") == "demo"
        assert report.get("task_count") == 8
        assert report.get("passed_count") == 8
        notice = (done.get("demo_notice") or "").lower()
        assert "built-in checker" in notice
    finally:
        server.shutdown()
        server.server_close()


def test_ui_new_pack_no_key_green(project_root: Path, tmp_path: Path) -> None:
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        status, created = _request(
            "POST",
            f"{base}/api/packs",
            {"parent": str(tmp_path), "name": "doc-notes"},
        )
        assert status == 201, created
        _, started = _request("POST", f"{base}/api/check", {"path": created["path"]})
        done = _poll_run(base, started["run_id"])
        assert done["exit_code"] == 0, done
        assert done["report"]["gate"] == "green"
    finally:
        server.shutdown()
        server.server_close()
