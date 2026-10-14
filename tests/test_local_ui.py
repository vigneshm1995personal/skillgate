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
        assert payload["has_openai_key"] is False
        assert payload["judge_provider"] == "skip"
        assert payload["demo_default"] is False
        blob = json.dumps(payload)
        assert "sk-" not in blob
        assert "OPENAI_API_KEY" not in blob
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
        assert "Create skill" in js
        assert "Want to add your first skill?" in js
        assert "This is local" in js
        assert "No Skill Gate account" in js
        assert "Create a skill" in js
        assert "Try an example" in js
        assert "See a failing check" in js
        assert "Run live uses your API key" in js
        assert "Continue without a key" in js
        assert "Quality was not scored." in js
        assert "built-in checker" not in js.lower()
        assert "not a live model" not in js.lower()
        assert "report.scored_by" in js
        assert "Create and run check" not in js
        assert "Checking…" not in js
        assert "<p class=\"gate\">Checking</p>" in js
        assert "Evaluating" not in js
        assert "New skill" in html
        assert "Setup wizard" not in html
        assert "skillgate check" not in html.lower()
        assert "docker" not in html.lower()
        assert "SKILL.md frontmatter" not in js
        assert "Your API key (optional)" not in js
        assert "Add a key for live checks" not in js
        assert "function keyFieldsHtml" in js
        assert "function keyPayloadFrom" in js
        assert "<code>${esc(t.id)}</code>" not in js
        assert "function checkHeadline" in js
        assert "The skill should run for a matching request." in js
        assert "The skill should stay off for an unrelated request." in js
        assert "Paste an OpenAI key to run live checks and score them" in js
        assert "An OpenAI key scores live checks" in js
        assert "function scoredByLine" in js
        assert "function displayNameFromJudge" not in js
        assert "OpenAI couldn't score this run" not in js
        assert "The skill ran live. Quality was not scored." in js
        checking = js.split("function checkingLine")[1].split("function checkingPanel")[0]
        assert "not a live model" not in checking
        assert "The skill ran live. Quality was not scored." in checking
        assert "decisions" not in js.lower()
        assert "gpt-6-luna" not in js
        assert "OpenAI (your key)" not in js
        assert "function happenedLine" in js
        assert "Output matched what was expected." in js
        assert "What the checks recorded" in js
        assert "Not available" in js
        assert "function bindCheckRows" in js
        assert "why || warn" not in js
        assert "aria-expanded" in js
        assert "Show details" in js
    finally:
        server.shutdown()
        server.server_close()


def test_ui_wizard_motion_is_wired_not_just_class_names(project_root: Path) -> None:
    js = (project_root / "src/skillgate_ai/local_ui/static/app.js").read_text(encoding="utf-8")
    css = (project_root / "src/skillgate_ai/local_ui/static/app.css").read_text(encoding="utf-8")
    assert "function swapPanel" in js
    assert "panel-leave" in js
    assert "panel-enter" in js
    assert "void current.offsetWidth" in js
    assert "return sleep(MOTION_MS)" in js
    assert 'step: "local"' in js
    assert 'wizard.step = "keys"' in js
    assert 'wizard.step = "firstSkill"' in js
    create = js.split("async function createSkill")[1].split("function checksFromPack")[0]
    assert "/api/check" not in create
    assert 'api("POST", "/api/packs"' in create
    assert "location.hash = packHref(wizard.path)" in create
    keys = js.split('if (step === "keys")')[1].split('if (step === "firstSkill")')[0]
    assert "/api/check" not in keys
    assert 'id="skip"' in keys
    assert "PUT" in keys and "/api/env" in keys
    assert "--motion: 350ms" in css
    assert "@keyframes panel-out" in css
    assert "prefers-reduced-motion" in css
    assert "min-height: 1.4em" in css


def test_ui_skill_page_run_motion_is_wired(project_root: Path) -> None:
    js = (project_root / "src/skillgate_ai/local_ui/static/app.js").read_text(encoding="utf-8")
    css = (project_root / "src/skillgate_ai/local_ui/static/app.css").read_text(encoding="utf-8")
    assert "const CHECKING_MIN_MS = 700" in js
    assert "function swapIn" in js
    assert 'id="run-stage"' in js
    assert "await showChecking(opts)" in js
    assert "check-pop" in js
    assert 'pop.classList.add("play")' in js
    assert "M24 24 L48 48 M48 24 L24 48" in js
    assert "replay: false" in js
    assert "replay: true" in js
    assert "let sawChecking = false" in js
    assert "sawChecking = true" in js
    assert "Evaluating" not in js
    assert 'wizard.step = "checking"' not in js
    assert "#run-stage" in css
    assert "check-pop.complete" in css
    assert "check-pop.fail" in css
    assert "@keyframes check-stroke" in css
    assert "400ms linear" in css
    start = js.split("async function startCheck")[1].split("async function pollRun")[0]
    assert 'api("POST", "/api/check"' in start
    assert "await showChecking(opts)" in start
    assert start.index('api("POST", "/api/check"') < start.index("await showChecking(opts)")
    poll = js.split("async function pollRun")[1].split("async function paintResult")[0]
    assert "CHECKING_MIN_MS" in poll
    reveal = js.split("async function revealResult")[1].split("async function renderPack")[0]
    assert reveal.index("sawChecking = false") < reveal.index("if (!stage) return")
    pack = js.split("async function renderPack")[1].split("async function startCheck")[0]
    assert "sawChecking = false" in pack
    assert pack.index("sawChecking = false") < pack.index("replay: false")
    assert "startCheck(path, { live: true })" in pack
    assert "demo: true" not in pack
    create = js.split("async function createSkill")[1].split("function checksFromPack")[0]
    assert "<p class=\"gate\">Checking</p>" not in create
    assert "/api/check" not in create
    keys = js.split('if (step === "keys")')[1].split('if (step === "firstSkill")')[0]
    assert "<p class=\"gate\">Checking</p>" not in keys
    assert "/api/check" not in keys
    setup = js.split("async function renderSetup")[1].split("async function renderNew")[0]
    assert "<p class=\"gate\">Checking</p>" not in setup
    assert "/api/check" not in setup
    assert "<p class=\"gate\">Checking</p>" in js
    show = js.split("async function showChecking")[1].split("function resultMarkHtml")[0]
    assert "is-covered" in show
    assert 'extra.innerHTML = ""' in show
    assert "checksTable(checksFromPack(pack))" in pack
    assert 'getElementById("run-rows")' in pack
    assert "stage.appendChild(idle)" not in pack
    assert "#run-stage:empty" in css
    assert ".run-panel.is-covered" in css
    assert "function happenedLine" in js
    assert "function bindCheckRows" in js
    paint = js.split("async function paintResult")[1]
    assert "happenedLine(t)" in paint
    assert "task.happened" in js
    assert "task.check_answers" in js
    assert "detailInnerHtml(t)" in paint
    assert "bindCheckRows(extra)" in paint
    bind = js.split("function bindCheckRows")[1].split("function setRunButtonsDisabled")[0]
    assert 'e.key !== "Enter"' in bind
    assert 'e.key !== " "' in bind


def test_ui_wizard_is_setup_only_then_skill_page(project_root: Path) -> None:
    js = (project_root / "src/skillgate_ai/local_ui/static/app.js").read_text(encoding="utf-8")
    assert "function keyFieldsHtml" in js
    assert "function keyPayloadFrom" in js
    assert "Your API key" in js
    assert "Want to add your first skill?" in js
    assert "Continue without a key" in js
    assert "You already have an API key. Live checks will use it." in js
    assert "This is not a live model." not in js
    assert "<label>OPENAI_API_KEY" not in js
    assert "<label>CURSOR_API_KEY" not in js
    assert "Your API key (optional)" not in js
    assert "<span class=\"label\">Local</span>" in js
    assert "<span class=\"label\">Key</span>" in js
    assert "data-node=\"3\"" not in js
    assert 'wizard.step = "checking"' not in js
    assert "Create and run check" not in js
    setup = js.split("async function renderSetup")[1].split("async function renderNew")[0]
    assert "/api/check" not in setup
    create = js.split("async function createSkill")[1].split("function checksFromPack")[0]
    assert "/api/check" not in create
    assert 'id="live"' in js
    assert ">Run</button>" in js
    assert "live: true" in js
    assert "function checksFromPack" in js
    assert "function checkHeadline" in js
    pack = js.split("async function renderPack")[1].split("async function startCheck")[0]
    assert "params.get(\"run\")" not in pack
    assert "params.get(\"live\")" not in pack
    assert "checksTable(checksFromPack(pack))" in pack
    assert 'id="live"' in pack
    assert ">Run</button>" in pack
    assert "SETUP_DONE_KEY" in js
    assert "skillgate-setup-done" in js
    paint = js.split("async function paintWizard")[1].split("function goFirstSkill")[0]
    assert 'wizard.step === "local" || wizard.step === "keys"' in paint


def test_ui_only_start_check_posts_check(project_root: Path) -> None:
    js = (project_root / "src/skillgate_ai/local_ui/static/app.js").read_text(encoding="utf-8")
    assert js.count('api("POST", "/api/check"') == 1
    start = js.split("async function startCheck")[1].split("async function pollRun")[0]
    assert 'api("POST", "/api/check"' in start
    assert "live: true" in start
    assert "startCheck(" not in start
    keys = js.split('if (step === "keys")')[1].split('if (step === "firstSkill")')[0]
    assert "/api/check" not in keys
    assert 'id="skip"' in keys
    first = js.split('if (step === "firstSkill")')[1].split('if (step === "name")')[0]
    assert "/api/check" not in first
    assert "location.hash = packHref(pdf)" in first
    pack = js.split("async function renderPack")[1].split("async function startCheck")[0]
    assert "/api/check" not in pack
    assert "startCheck(path, { live: true })" in pack
    paint = js.split("function paintResult")[1]
    error_branch = paint.split("if (snap.error && !snap.report)")[1].split("const gate")[0]
    assert "startCheck" not in error_branch
    assert "demo: true" not in error_branch


def test_ui_env_writes_only_supplied_keys(tmp_path: Path) -> None:
    server, base, _state = start_background(root=tmp_path, host="127.0.0.1", port=0)
    try:
        status, payload = _request(
            "PUT",
            f"{base}/api/env",
            {"OPENAI_API_KEY": "sk-test-not-a-real-key"},
        )
        assert status == 200, payload
        assert payload["ok"] is True
        vault = (tmp_path / ".skillgate" / "keys").read_text(encoding="utf-8")
        assert "OPENAI_API_KEY=sk-test-not-a-real-key" in vault
        assert "CURSOR_API_KEY" not in vault
        assert "ANTHROPIC_API_KEY" not in vault
        assert not (tmp_path / ".env").exists() or "sk-test-not-a-real-key" not in (
            tmp_path / ".env"
        ).read_text(encoding="utf-8")
        status, meta = _request("GET", f"{base}/api/meta")
        assert status == 200
        assert "sk-test-not-a-real-key" not in json.dumps(meta)
    finally:
        server.shutdown()
        server.server_close()


def test_ui_wizard_first_run_opens_skill_page_without_check(
    project_root: Path, tmp_path: Path
) -> None:
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
        cases = (created.get("dataset") or {}).get("cases") or []
        assert cases, created
        assert all("id" in row and "prompt" in row for row in cases)
        js = (
            project_root / "src" / "skillgate_ai" / "local_ui" / "static" / "app.js"
        ).read_text(encoding="utf-8")
        create = js.split("async function createSkill")[1].split("function checksFromPack")[0]
        assert "/api/check" not in create
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
        vault = tmp_path / ".skillgate" / "keys"
        assert not vault.exists() or "MALICIOUS" not in vault.read_text(encoding="utf-8")
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


def test_ui_check_without_key_is_409(project_root: Path, tmp_path: Path) -> None:
    dest = tmp_path / "pdf-sabotaged"
    shutil.copytree(project_root / "skills" / "pdf-sabotaged", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        status, started = _request("POST", f"{base}/api/check", {"path": str(dest)})
        assert status == 409, started
        blob = json.dumps(started).lower()
        assert "no agent" in blob or "api key" in blob
        assert "skillgate keys set" in blob
    finally:
        server.shutdown()
        server.server_close()


def test_ui_apply_advice_does_not_run_without_key(
    project_root: Path, tmp_path: Path
) -> None:
    dest = tmp_path / "pdf-sabotaged"
    shutil.copytree(project_root / "skills" / "pdf-sabotaged", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        status, applied = _request(
            "POST",
            f"{base}/api/pack/apply-advice",
            {
                "path": str(dest),
                "description": (
                    "Extract text from PDFs when the user asks to read or parse a PDF."
                ),
            },
        )
        assert status == 200, applied
        status, started = _request("POST", f"{base}/api/check", {"path": str(dest)})
        assert status == 409, started
    finally:
        server.shutdown()
        server.server_close()


def test_ui_live_without_key_is_409(project_root: Path) -> None:
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        status, payload = _request(
            "POST", f"{base}/api/check", {"path": "skills/pdf", "live": True}
        )
        assert status == 409, payload
        blob = json.dumps(payload).lower()
        assert "no agent" in blob or "api key" in blob
        assert "skillgate keys set" in blob
        assert status != 202
    finally:
        server.shutdown()
        server.server_close()


def test_ui_live_with_key_does_not_use_builtin(
    project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conftest import enable_cursor_agent

    enable_cursor_agent(monkeypatch, project_root)
    dest = tmp_path / "pdf"
    shutil.copytree(project_root / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")

    class LiveStub:
        name = "cursor-agent"

        def run(self, *args, **kwargs):
            from skillgate_ai.errors import HarnessError

            raise HarnessError("live stub")

    monkeypatch.setattr(
        "skillgate_ai.gate.live_harness_or_error", lambda *a, **k: LiveStub()
    )
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        status, started = _request(
            "POST",
            f"{base}/api/check",
            {"path": str(dest), "live": True, "demo": True},
        )
        assert status == 202, started
        done = _poll_run(base, started["run_id"])
        assert done.get("report") is None
        assert done.get("demo_notice") is None
        assert done["exit_code"] == 1
        err = json.dumps(done.get("error") or {}).lower()
        assert "built-in" not in err
        assert "demo" not in err
    finally:
        server.shutdown()
        server.server_close()


def test_ui_demo_flag_still_runs_live(
    project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conftest import enable_cursor_agent

    enable_cursor_agent(monkeypatch, project_root)
    dest = tmp_path / "pdf"
    shutil.copytree(project_root / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")

    class LiveStub:
        name = "cursor-agent"

        def run(self, *args, **kwargs):
            from skillgate_ai.errors import HarnessError

            raise HarnessError("live stub")

    monkeypatch.setattr(
        "skillgate_ai.gate.live_harness_or_error", lambda *a, **k: LiveStub()
    )
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        status, started = _request(
            "POST", f"{base}/api/check", {"path": str(dest), "live": False, "demo": True}
        )
        assert status == 202, started
        done = _poll_run(base, started["run_id"])
        assert done.get("report") is None
        assert done.get("demo_notice") is None
        assert done["exit_code"] == 1
        err = json.dumps(done.get("error") or {}).lower()
        assert "built-in" not in err
        assert "demo" not in err
        assert (done.get("report") or {}).get("harness") != "demo"
    finally:
        server.shutdown()
        server.server_close()


def test_ui_new_pack_no_key_is_409(project_root: Path, tmp_path: Path) -> None:
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        status, created = _request(
            "POST",
            f"{base}/api/packs",
            {"parent": str(tmp_path), "name": "doc-notes"},
        )
        assert status == 201, created
        status, started = _request("POST", f"{base}/api/check", {"path": created["path"]})
        assert status == 409, started
        blob = json.dumps(started).lower()
        assert "no agent" in blob or "api key" in blob
    finally:
        server.shutdown()
        server.server_close()


def test_app_js_check_detail_helpers_run_in_node(project_root: Path, tmp_path: Path) -> None:
    js = (project_root / "src/skillgate_ai/local_ui/static/app.js").read_text(encoding="utf-8")
    esc = js[js.index("function esc(") : js.index("function packHref")]
    helpers = js[js.index("function happenedLine") : js.index("function setRunButtonsDisabled")]
    script = (
        esc
        + helpers
        + """
const pass = happenedLine({passed: true, happened: "Output matched what was expected."});
if (pass !== "Output matched what was expected.") process.exit(2);
const warned = happenedLine({
  passed: true,
  happened: "The judge wasn't very sure about this one."
});
if (warned !== "The judge wasn't very sure about this one.") process.exit(3);
const fail = happenedLine({passed: false, happened: "Wrong file."});
if (fail !== "Wrong file.") process.exit(4);
const blankFail = happenedLine({passed: false});
if (blankFail !== "This check did not pass.") process.exit(5);
const html = detailInnerHtml({
  passed: true,
  check_kind: "openai",
  check_answers: [
    {label: "Got the job done?", answer: "Fully completed"},
    {label: "Path", answer: "Not available"}
  ],
  judge: {warnings: ["The judge wasn't very sure about this one."]}
});
if (!html.includes("Got the job done?")) process.exit(7);
if (!html.includes("Fully completed")) process.exit(8);
if (!html.includes(">Path<")) process.exit(9);
if (!html.includes("Not available")) process.exit(10);
if (!html.includes("wasn't very sure")) process.exit(11);
const builtin = detailInnerHtml({
  passed: true,
  check_kind: "builtin",
  check_answers: [{label: "Task completed", answer: "Yes — All expected outputs present"}]
});
if (!builtin.includes("What the checks recorded")) process.exit(12);
if (!builtin.includes("Task completed")) process.exit(13);
const failWhy = detailInnerHtml({
  passed: false,
  check_kind: "openai",
  check_answers: [{label: "Got it right?", answer: "Incorrect"}],
  judge: {why: "Missed the output."}
});
if (!failWhy.includes("Missed the output.")) process.exit(14);
if (detailInnerHtml({
  passed: true,
  check_kind: "openai",
  check_answers: [],
  judge: {why: "should not show"}
}).includes("should not show")) {
  process.exit(15);
}
process.stdout.write("ok");
"""
    )
    node_path = tmp_path / "check-helpers.js"
    node_path.write_text(script, encoding="utf-8")
    node = shutil.which("node")
    assert node, "node is required to run local UI helper checks"
    proc = subprocess.run([node, str(node_path)], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert proc.stdout == "ok"
