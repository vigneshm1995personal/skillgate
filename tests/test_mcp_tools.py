from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from skillgate_ai.demo_files import ensure_demo_pdfs
from skillgate_ai.engine import SuiteReport, TaskReport
from skillgate_ai.errors import SkillGateError
from skillgate_ai.history import append_eval
from skillgate_ai.live import reset_controls
from skillgate_ai.mcp import tools as mcp_tools
from skillgate_ai.mcp.context import McpContext, resolve_pack
from skillgate_ai.scorers import Score

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _reset_live() -> None:
    reset_controls()


@pytest.fixture
def mcp_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from conftest import enable_cursor_agent

    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    dest = tmp_path / "skills" / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")
    enable_cursor_agent(monkeypatch, tmp_path)
    ctx = McpContext.for_root(tmp_path)
    yield ctx, dest


def _fake_suite(dest: Path) -> SuiteReport:
    task = TaskReport(
        task_id="should-trigger-1",
        prompt="demo",
        expect_skill="pdf",
        passed=True,
        scores=[
            Score(
                scorer="skill_trigger",
                passed=True,
                detail="Triggered `pdf`",
                expected="pdf",
                actual="pdf",
            )
        ],
        selected_skill="pdf",
        judge={"status": "skip", "provider": "skip", "passed": None},
    )
    return SuiteReport(
        suite="pdf-pack",
        title="Dataset",
        skill="pdf",
        harness="cursor-agent",
        sandbox="local",
        passed=True,
        tasks=[task],
        skill_path=str(dest),
        config={"judge": {"provider": "skip", "display_name": "Checks"}},
    )


def test_resolve_pack_accepts_skill_md_path(mcp_env) -> None:
    ctx, dest = mcp_env
    resolved = resolve_pack(ctx, str(dest / "SKILL.md"))
    assert resolved == dest.resolve()


def test_resolve_pack_accepts_name_and_dir(mcp_env) -> None:
    ctx, dest = mcp_env
    assert resolve_pack(ctx, "pdf") == dest.resolve()
    assert resolve_pack(ctx, str(dest)) == dest.resolve()


def test_resolve_pack_rejects_outside_root(mcp_env) -> None:
    ctx, _ = mcp_env
    with pytest.raises(SkillGateError):
        resolve_pack(ctx, "/etc/passwd")


def test_validate_skill_ok(mcp_env) -> None:
    ctx, _ = mcp_env
    out = mcp_tools.validate_skill(ctx, skill="pdf")
    assert out["ok"] is True
    assert out["name"] == "pdf"


def test_validate_skill_invalid_returns_ok_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    bad = tmp_path / "skills" / "bad"
    bad.mkdir(parents=True)
    (bad / "SKILL.md").write_text("not valid frontmatter\n", encoding="utf-8")
    ctx = McpContext.for_root(tmp_path)
    out = mcp_tools.validate_skill(ctx, skill="bad")
    assert out["ok"] is False
    assert "error" in out


def test_dataset_scaffold_new_name_creates_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    ctx = McpContext.for_root(tmp_path)
    out = mcp_tools.dataset_scaffold(ctx, name="fresh-skill")
    assert out["created"] is True
    assert (tmp_path / "skills" / "fresh-skill" / "SKILL.md").is_file()


def test_dataset_scaffold_refuses_existing_without_force(mcp_env) -> None:
    ctx, _ = mcp_env
    with pytest.raises(SkillGateError, match="already has cases"):
        mcp_tools.dataset_scaffold(ctx, skill="pdf")


def test_dataset_get_lists_cases(mcp_env) -> None:
    ctx, _ = mcp_env
    out = mcp_tools.dataset_get(ctx, skill="pdf")
    assert out["dataset"]["cases"]


def test_case_add_edit_remove_roundtrip(mcp_env) -> None:
    ctx, _ = mcp_env
    added = mcp_tools.case_add(ctx, skill="pdf", prompt="roundtrip prompt", case_id="rt-1")
    assert added["case_id"] == "rt-1"
    mcp_tools.case_edit(ctx, skill="pdf", case_id="rt-1", prompt="edited prompt")
    removed = mcp_tools.case_remove(ctx, skill="pdf", case_id="rt-1")
    assert removed["removed"] == "rt-1"


def test_case_edit_nothing_to_change_errors(mcp_env) -> None:
    ctx, _ = mcp_env
    with pytest.raises(SkillGateError, match="Nothing to change"):
        mcp_tools.case_edit(ctx, skill="pdf", case_id="should-trigger-1")


def test_case_import_dry_run_does_not_write(mcp_env) -> None:
    ctx, dest = mcp_env
    before = (dest / "evals" / "cases.yaml").read_text(encoding="utf-8")
    out = mcp_tools.case_import(
        ctx,
        skill="pdf",
        content="id,prompt\nimported-1,hello import\n",
        format="csv",
        dry_run=True,
    )
    assert out["dry_run"] is True
    assert out["applied"] == 0
    assert (dest / "evals" / "cases.yaml").read_text(encoding="utf-8") == before


def test_case_import_conflict_fail_lists_rows(mcp_env) -> None:
    ctx, _ = mcp_env
    mcp_tools.case_import(
        ctx,
        skill="pdf",
        content="id,prompt,input\nfirst-custom,One,evals/fixtures/hello.pdf\n",
        format="csv",
        on_conflict="fail",
    )
    with pytest.raises(SkillGateError):
        mcp_tools.case_import(
            ctx,
            skill="pdf",
            content="id,prompt,input\nfirst-custom,Duplicate,evals/fixtures/hello.pdf\n",
            format="csv",
            on_conflict="fail",
        )


def test_check_start_refuses_without_key_or_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "skills" / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    class _NoKey:
        has_any_key = False

    monkeypatch.setattr("skillgate_ai.mcp.tools.get_llm_config", lambda _r: _NoKey())
    ctx = McpContext.for_root(tmp_path)
    from skillgate_ai.errors import MissingLLMKeyError

    with pytest.raises(MissingLLMKeyError):
        mcp_tools.check_start(ctx, skill="pdf", no_judge=True)
    assert ctx.registry.runs == {}


def test_check_start_busy_in_process(mcp_env) -> None:
    ctx, dest = mcp_env
    ctx.registry.runs["live"] = {"status": "running"}
    with pytest.raises(SkillGateError, match="already running"):
        mcp_tools.check_start(ctx, skill="pdf", no_judge=True)


def test_check_start_busy_when_project_lock_held(mcp_env, monkeypatch: pytest.MonkeyPatch) -> None:
    from skillgate_ai.run_lock import project_run_lock

    ctx, _ = mcp_env
    holder = project_run_lock(ctx.root)
    holder.__enter__()
    try:
        with pytest.raises(SkillGateError, match="already running"):
            mcp_tools.check_start(ctx, skill="pdf", no_judge=True)
    finally:
        holder.__exit__(None, None, None)


def test_check_start_case_ids_forces_tryout(mcp_env, monkeypatch: pytest.MonkeyPatch) -> None:
    from skillgate_ai.run_registry import RunRegistry, RunRequest

    ctx, dest = mcp_env
    seen: dict = {}

    def capture_start(self: RunRegistry, request: RunRequest) -> dict[str, str]:
        seen["tryout"] = request.tryout
        seen["checks"] = request.checks
        return {"id": "t1", "status": "running"}

    monkeypatch.setattr(RunRegistry, "start", capture_start)
    out = mcp_tools.check_start(ctx, skill="pdf", case_ids=["extract-hello"], no_judge=True)
    assert seen["tryout"] is True
    assert seen["checks"]
    assert out["tryout"] is True


def test_check_start_poll_until_done_with_mocked_run_eval(
    mcp_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, dest = mcp_env
    monkeypatch.setattr("skillgate_ai.gate.run_eval", lambda *_a, **_k: _fake_suite(dest))
    started = mcp_tools.check_start(ctx, skill="pdf", no_judge=True)
    run_id = started["id"]
    ctx.registry.join(run_id, timeout=30.0)
    polled = mcp_tools.check_poll(ctx, run_id=run_id, include_report=True)
    assert polled["status"] == "done"


def test_check_poll_omits_report_when_done_unless_requested(
    mcp_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, dest = mcp_env
    monkeypatch.setattr("skillgate_ai.gate.run_eval", lambda *_a, **_k: _fake_suite(dest))
    run_id = mcp_tools.check_start(ctx, skill="pdf", no_judge=True)["id"]
    ctx.registry.join(run_id, timeout=30.0)
    polled = mcp_tools.check_poll(ctx, run_id=run_id, include_report=False)
    assert polled.get("report_omitted") is True
    assert polled.get("report") is None


def test_check_poll_falls_back_to_history(mcp_env) -> None:
    ctx, dest = mcp_env
    append_eval(dest, run_id="hist42", passed=True, report={"passed": True, "suite": "pdf"})
    polled = mcp_tools.check_poll(ctx, run_id="hist42")
    assert polled["id"] == "hist42"


def test_check_poll_unknown_run_errors(mcp_env) -> None:
    ctx, _ = mcp_env
    with pytest.raises(SkillGateError, match="Unknown run"):
        mcp_tools.check_poll(ctx, run_id="missing-run")


def test_check_cancel_unknown_run_errors(mcp_env) -> None:
    ctx, _ = mcp_env
    with pytest.raises(SkillGateError, match="not running"):
        mcp_tools.check_cancel(ctx, run_id="missing-run")


def test_report_latest_none_when_never_run(mcp_env) -> None:
    ctx, _ = mcp_env
    mcp_tools.dataset_scaffold(ctx, name="never-run")
    latest = mcp_tools.report_latest(ctx, skill="never-run")
    assert latest["run"] is None


def test_report_get_matches_history_show_json(mcp_env) -> None:
    from typer.testing import CliRunner

    from skillgate_ai.cli import app

    ctx, dest = mcp_env
    append_eval(
        dest,
        run_id="rep99",
        passed=True,
        report={"passed": True, "suite": "pdf", "skill": "pdf", "task_count": 1},
        config={"harness": "cursor-agent", "judge": {"provider": "skip"}},
    )
    tool_out = mcp_tools.report_get(ctx, run_id="rep99", skill="pdf")
    cli = CliRunner().invoke(app, ["history", "show", "rep99", "--pack", str(dest), "--json"])
    assert cli.exit_code == 0, cli.output
    assert cli.stdout == json.dumps(tool_out, indent=2, ensure_ascii=True) + "\n"


def test_report_get_unknown_run_errors(mcp_env) -> None:
    ctx, _ = mcp_env
    with pytest.raises(SkillGateError, match="No run named"):
        mcp_tools.report_get(ctx, run_id="nope")


def test_doctor_reports_bools_only(mcp_env) -> None:
    ctx, _ = mcp_env
    out = mcp_tools.doctor(ctx)

    def walk(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)
        else:
            if obj is not None and not isinstance(obj, (bool, str, int, float)):
                raise AssertionError(f"non-json leaf: {type(obj)}")

    walk(out["keys"])
    for meta in out["keys"].values():
        for v in meta.values():
            assert isinstance(v, bool)


def test_no_key_values_in_any_tool_output(mcp_env, monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = "sk-test-SENTINEL-123"
    monkeypatch.setenv("OPENAI_API_KEY", sentinel)
    monkeypatch.setenv("SKILLGATE_OPENAI_API_KEY", sentinel)
    ctx, dest = mcp_env
    monkeypatch.setattr("skillgate_ai.gate.run_eval", lambda *_a, **_k: _fake_suite(dest))
    outputs = [
        mcp_tools.validate_skill(ctx, skill="pdf"),
        mcp_tools.dataset_get(ctx, skill="pdf"),
        mcp_tools.report_latest(ctx, skill="pdf"),
        mcp_tools.doctor(ctx),
    ]
    started = mcp_tools.check_start(ctx, skill="pdf", no_judge=True)
    outputs.append(started)
    run_id = started["id"]
    ctx.registry.join(run_id, timeout=30.0)
    outputs.append(mcp_tools.check_poll(ctx, run_id=run_id, include_report=True))
    blob = json.dumps(outputs)
    assert sentinel not in blob


def test_tools_write_nothing_to_stdout(mcp_env, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    ctx, dest = mcp_env
    monkeypatch.setattr("skillgate_ai.gate.run_eval", lambda *_a, **_k: _fake_suite(dest))
    mcp_tools.doctor(ctx)
    mcp_tools.validate_skill(ctx, skill="pdf")
    mcp_tools.dataset_get(ctx, skill="pdf")
    out, err = capsys.readouterr()
    assert out == ""
    assert err == ""


def test_tools_import_without_fastapi_or_mcp_sdk(tmp_path: Path) -> None:
    code = (
        "import sys\n"
        "class B:\n"
        "    def find_spec(self, n, p=None, t=None):\n"
        "        top = n.split('.', 1)[0]\n"
        "        if top in ('fastapi', 'mcp'):\n"
        "            raise ModuleNotFoundError('blocked')\n"
        "        return None\n"
        "sys.meta_path.insert(0, B())\n"
        "import skillgate_ai.mcp.tools\n"
        "import skillgate_ai.mcp.context\n"
        "print('ok')\n"
    )
    import os
    import site

    py_path = os.pathsep.join([str(ROOT / "src"), site.getusersitepackages()])
    env = {**os.environ, "PYTHONPATH": py_path}
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout
