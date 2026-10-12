"""0.6 QA blockers: history scrub, score payload, /pack lookup, REG-13..22 minors."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from conftest import plain_text
from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.engine import SuiteReport, TaskReport
from skillgate_ai.errors import SandboxError, SkillGateError, SuiteError
from skillgate_ai.gate import persist_eval
from skillgate_ai.history import append_eval, load_history
from skillgate_ai.judge_spec import resolve_judge_spec, spec_decisions_questions

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]


def _pdf(tmp_path: Path) -> Path:
    dest = tmp_path / "skills" / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    return dest


def _leaky_report() -> dict:
    judge = {
        "status": "completed",
        "provider": "openai",
        "backend": "decisions",
        "model": "openai/gpt-6-luna-decisions",
        "display_name": "the judge",
        "check_kind": "openai",
        "answers": {"task_completion": {"choice": "Fully completed"}},
    }
    report = SuiteReport(
        suite="pdf",
        title="pdf",
        skill="pdf",
        harness="llm",
        sandbox="local",
        passed=True,
        tasks=[
            TaskReport(
                task_id="extract-hello",
                prompt="p",
                expect_skill="pdf",
                passed=True,
                scores=[],
                selected_skill="pdf",
                judge=judge,
            )
        ],
        config={
            "judge": {
                "provider": "openai",
                "backend": "decisions",
                "model": "openai/gpt-6-luna-decisions",
                "display_name": "the judge",
            }
        },
    )
    from skillgate_ai.report import report_to_dict

    payload = report_to_dict(report)
    payload["tasks"][0]["check_kind"] = "openai"
    return payload


def _assert_no_scorer_leak(blob: str) -> None:
    lower = blob.lower()
    assert "openai" not in lower
    assert "decisions" not in lower
    assert "gpt-6-luna" not in lower
    assert "check_kind" not in lower


def test_persist_eval_stores_neutral_scorer_fields(tmp_path: Path) -> None:
    pack = tmp_path / "pdf"
    pack.mkdir()
    persist_eval(
        pack_root=pack,
        run_id="leaky-run",
        passed=True,
        report=_leaky_report(),
        config={
            "judge": {
                "provider": "openai",
                "backend": "decisions",
                "model": "openai/gpt-6-luna-decisions",
                "display_name": "the judge",
            }
        },
    )
    files = list((pack / "evals" / "history").glob("*.jsonl"))
    assert files, "history jsonl was not written"
    disk = files[0].read_text(encoding="utf-8")
    _assert_no_scorer_leak(disk)
    row = json.loads(disk.splitlines()[0])
    judge = ((row.get("config") or {}).get("judge")) or {}
    assert judge.get("display_name") == "the judge"


def test_history_json_scrubs_legacy_leaky_rows(tmp_path: Path, monkeypatch) -> None:
    dest = _pdf(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    append_eval(
        dest,
        run_id="old-leak",
        passed=True,
        report=_leaky_report(),
        config={
            "judge": {
                "provider": "openai",
                "backend": "decisions",
                "model": "openai/gpt-6-luna-decisions",
            }
        },
    )
    listed = runner.invoke(app, ["history", "--pack", str(dest), "--json"])
    blob = listed.stdout + listed.stderr
    assert listed.exit_code == 0, blob
    _assert_no_scorer_leak(blob)
    payload = json.loads(listed.stdout)
    assert payload
    human = runner.invoke(app, ["history", "--pack", str(dest)])
    text = plain_text(human.stdout)
    assert human.exit_code == 0, text
    assert "old-leak" in text
    assert "8/8" in text or "1/" in text
    assert "T" in text or "202" in text


def test_history_missing_pack_is_an_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["history", "--pack", "/nope"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "no runs yet" not in out.lower()


def test_score_extra_decisions_levels_are_label_objects() -> None:
    spec = resolve_judge_spec(
        pack={
            "extra_questions": [
                {
                    "id": "clarity",
                    "type": "score",
                    "ask": "Clarity 1-5",
                    "on_fail": "block",
                }
            ]
        }
    )
    extra = next(row for row in spec_decisions_questions(spec) if row["name"] == "clarity")
    assert extra["type"] == "score"
    levels = extra["levels"]
    assert isinstance(levels, list) and len(levels) >= 2
    assert all(isinstance(item, dict) and str(item.get("label") or "").strip() for item in levels)
    assert not any(isinstance(item, str) for item in levels)


def test_score_extra_is_posted_as_label_objects() -> None:
    from skillgate_ai.judge_openai import DecisionsBackend
    from skillgate_ai.judge_spec import builtin_spec

    spec = resolve_judge_spec(
        pack={
            "extra_questions": [
                {
                    "id": "clarity",
                    "type": "score",
                    "ask": "Clarity 1-5",
                    "on_fail": "block",
                }
            ]
        }
    )
    posted: list[dict] = []

    def post_json(path, payload, timeout_sec=None):
        del path, timeout_sec
        posted.append(payload)
        names = [row["name"] for row in payload.get("questions") or []]
        answers = []
        for name in names:
            if name == "clarity":
                answers.append({"name": name, "score": 4})
            elif name == "path_efficiency":
                answers.append({"name": name, "choice": "Efficient"})
            else:
                mapping = {
                    "task_completion": "Fully completed",
                    "correctness": "Correct",
                    "instruction_adherence": "Fully followed",
                    "evidence_action_validity": "Fully supported",
                    "result_quality": "Clear and complete",
                }
                answers.append({"name": name, "choice": mapping[name]})
        return {"status": "ok", "data": {"answers": answers, "model": "gpt-6-luna"}}

    backend = DecisionsBackend(api_key="sk-test", model="gpt-6-luna")
    backend.post_json = post_json  # type: ignore[method-assign]
    result = backend.evaluate(
        state={"goal": "extract", "stdout": "Hello", "path": {"had_path": True, "steps": 1}},
        images=[],
        timeout_sec=5,
        spec=spec,
    )
    del builtin_spec
    assert posted, "Decisions request was not sent"
    extra = next(row for row in posted[0]["questions"] if row["name"] == "clarity")
    assert extra["type"] == "score"
    assert all(isinstance(item, dict) and "label" in item for item in extra["levels"])
    assert result.get("status") == "completed"


def test_canonical_skill_matches_generic_mount_folder() -> None:
    from skillgate_ai.ingest import canonical_skill_name, ingest_skill

    src = ROOT / "skills" / "pdf"
    # Simulate docker -v pdf:/pack: folder name pack, SKILL.md name pdf.
    skill = ingest_skill(src, strict=False)
    mounted = skill.__class__(
        path=Path("/pack"),
        name=skill.name,
        description=skill.description,
        body=skill.body,
    )
    assert canonical_skill_name("pack", [mounted]) == "pdf"
    assert canonical_skill_name("pdf", [mounted]) == "pdf"


def test_llm_harness_does_not_crash_when_selected_is_mount_folder(
    tmp_path: Path, monkeypatch
) -> None:
    from test_judge import _cfg

    from skillgate_ai.harness import Completion, LLMHarness
    from skillgate_ai.ingest import ingest_skill
    from skillgate_ai.sandbox import LocalSandbox, prepare_workspace
    from skillgate_ai.usage import Usage

    pack = tmp_path / "pack"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    skill = ingest_skill(pack, strict=False)
    assert skill.name == "pdf"
    assert pack.name == "pack"
    workspace = tmp_path / "ws"
    workspace.mkdir()
    prepare_workspace(workspace, [skill], [])
    (workspace / ".skillgate" / "selected.json").write_text(
        '{"skill": "pack"}', encoding="utf-8"
    )
    harness = LLMHarness(_cfg(openai_api_key="sk-test"))

    def fake_complete(prompt, timeout_sec):
        del prompt, timeout_sec
        return Completion(text="ok", usage=Usage(tokens_in=1, tokens_out=1))

    monkeypatch.setattr(harness, "_complete", fake_complete)
    sandbox = LocalSandbox(workspace)
    result = harness.run(sandbox, "Extract hello.pdf", [skill], timeout_sec=5)
    assert result.trigger.selected_skill == "pdf"


def test_docker_sandbox_fails_before_run_when_image_missing(monkeypatch) -> None:
    from skillgate_ai.sandbox import DockerSandbox

    monkeypatch.setattr("skillgate_ai.sandbox.shutil.which", lambda _name: "/usr/bin/docker")

    def fake_run(cmd, **_kwargs):
        del _kwargs
        if cmd[:3] == ["docker", "image", "inspect"] or (
            len(cmd) >= 3 and cmd[0] == "docker" and "inspect" in cmd
        ):
            class Proc:
                returncode = 1
                stdout = ""
                stderr = "Error: No such image: skillgate-sandbox:v0"

            return Proc()

        class Info:
            returncode = 0
            stdout = ""
            stderr = ""

        return Info()

    monkeypatch.setattr("skillgate_ai.sandbox.subprocess.run", fake_run)
    with pytest.raises(SandboxError, match="not installed|not found|image") as caught:
        DockerSandbox("skillgate-sandbox:v0")
    blob = f"{caught.value.message} {caught.value.hint or ''}".lower()
    assert "125" not in blob
    assert "sandbox local" in blob or "--sandbox local" in blob


def test_docker_sandbox_fails_clearly_when_daemon_down(monkeypatch) -> None:
    from skillgate_ai.sandbox import DockerSandbox

    monkeypatch.setattr("skillgate_ai.sandbox.shutil.which", lambda _name: "/usr/bin/docker")

    def fake_run(cmd, **_kwargs):
        del cmd, _kwargs

        class Proc:
            returncode = 1
            stdout = ""
            stderr = "Cannot connect to the Docker daemon. Is the docker daemon running?"

        return Proc()

    monkeypatch.setattr("skillgate_ai.sandbox.subprocess.run", fake_run)
    with pytest.raises(SandboxError, match="Docker") as caught:
        DockerSandbox("skillgate-sandbox:v0")
    blob = f"{caught.value.message} {caught.value.hint or ''}".lower()
    assert "125" not in blob
    assert "daemon" in blob or "reach docker" in blob or "start docker" in blob


def test_skill_write_generate_refuses_skill_md(tmp_path: Path, monkeypatch) -> None:
    dest = _pdf(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    before = (dest / "SKILL.md").read_text(encoding="utf-8")
    result = runner.invoke(
        app,
        ["skill", "write", str(dest), "--path", "SKILL.md", "--generate"],
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "---" in (dest / "SKILL.md").read_text(encoding="utf-8")
    assert (dest / "SKILL.md").read_text(encoding="utf-8") == before
    assert "name: pdf" in before


def test_cli_deploy_writes_deploys_jsonl(tmp_path: Path, monkeypatch) -> None:
    dest = _pdf(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.setenv("SKILLGATE_OPENAI_API_KEY", "sk-test")
    monkeypatch.chdir(tmp_path)
    skills_home = tmp_path / "agent-skills"
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(skills_home))
    append_eval(dest, run_id="green", passed=True, report={"passed": True, "skill": "pdf"})

    class Adapter:
        id = "cursor"

        def install(self, **_kwargs):
            return {"status": "installed", "message": "Installed pdf", "file_count": 3}

    monkeypatch.setattr("skillgate_ai.deploy.get_adapter", lambda _name: Adapter())
    result = runner.invoke(app, ["deploy", str(dest), "--target", "cursor"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    log = dest / "evals" / "deploys.jsonl"
    assert log.is_file(), "CLI deploy must append evals/deploys.jsonl"
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[-1]["target"] == "cursor"
    assert rows[-1]["status"] == "installed"


def test_keys_found_from_pack_parent_and_cwd_pack(tmp_path: Path, monkeypatch) -> None:
    dest = _pdf(tmp_path)
    vault = tmp_path / ".skillgate"
    vault.mkdir()
    (vault / "keys").write_text("AI_GATEWAY_API_KEY=gw-from-parent\n", encoding="utf-8")
    monkeypatch.delenv("SKILLGATE_ROOT", raising=False)
    monkeypatch.delenv("SKILLGATE_AI_GATEWAY_API_KEY", raising=False)
    monkeypatch.chdir(dest)
    from skillgate_ai.keys import resolve_provider_keys
    from skillgate_ai.paths import config_root_for, project_root

    assert project_root() == tmp_path.resolve()
    assert config_root_for(dest) == tmp_path.resolve()
    keys = resolve_provider_keys(config_root_for(dest))
    assert keys.get("AI_GATEWAY_API_KEY") == "gw-from-parent"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert config_root_for(dest) == tmp_path.resolve()


def test_config_root_for_docker_pack_mount(tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "pack"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    monkeypatch.delenv("SKILLGATE_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    from skillgate_ai.paths import config_root_for

    assert config_root_for(dest) == dest.resolve()


def test_run_lock_unwritable_is_not_fatal(tmp_path: Path, monkeypatch) -> None:
    from skillgate_ai.run_lock import project_run_lock

    lock = project_run_lock(tmp_path)

    def boom(*_args, **_kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr("builtins.open", boom)
    with lock:
        pass


def test_cli_one_run_at_a_time(tmp_path: Path) -> None:
    import subprocess
    import sys
    import textwrap

    from skillgate_ai.run_lock import project_run_lock

    with project_run_lock(tmp_path):
        code = textwrap.dedent(
            f"""
            from pathlib import Path
            from skillgate_ai.errors import SkillGateError
            from skillgate_ai.run_lock import project_run_lock
            try:
                with project_run_lock(Path({str(tmp_path)!r})):
                    print("GOT")
            except SkillGateError as exc:
                print(exc.message)
                raise SystemExit(2)
            """
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=False,
        )
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 2, blob
        assert "already running" in blob.lower()


def test_version_flag(tmp_path: Path, monkeypatch) -> None:
    from skillgate_ai import __version__

    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = runner.invoke(app, ["--version"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert __version__ in out


def test_import_empty_source_is_not_silent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SKILLGATE_CLAUDE_SKILLS", str(tmp_path / "missing-claude"))
    result = runner.invoke(app, ["import", "--source", "claude"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert out.strip()


def test_judge_show_unknown_case_errors(tmp_path: Path, monkeypatch) -> None:
    dest = _pdf(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["judge", "show", str(dest), "--case", "nope"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "nope" in out.lower()


def test_case_add_refuses_non_pack(tmp_path: Path, monkeypatch) -> None:
    empty = tmp_path / "not-a-pack"
    empty.mkdir()
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["case", "add", str(empty), "--prompt", "Do a thing", "--id", "x"],
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert not (empty / "evals" / "cases.yaml").exists()


def test_case_add_force_prints_replaced_id(tmp_path: Path, monkeypatch) -> None:
    dest = _pdf(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    first = runner.invoke(
        app,
        ["case", "add", str(dest), "--prompt", "Summarize this", "--id", "qa-summary"],
    )
    assert first.exit_code == 0, first.stdout
    result = runner.invoke(
        app,
        [
            "case",
            "add",
            str(dest),
            "--prompt",
            "Summarize again",
            "--id",
            "qa-summary",
            "--force",
        ],
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert "qa-summary" in out
    assert "qa-notrig" not in out


def test_example_defaults_to_skills_folder(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    (tmp_path / "skills").mkdir()
    result = runner.invoke(app, ["example", "pdf"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert (tmp_path / "skills" / "pdf" / "SKILL.md").is_file()
    assert not (tmp_path / "pdf" / "SKILL.md").exists()


def test_catalog_does_not_list_root_level_duplicate(tmp_path: Path) -> None:
    from skillgate_ai.catalog import catalog_entries

    skills = tmp_path / "skills" / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", skills)
    stray = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", stray)
    rows = catalog_entries(tmp_path)
    paths = [row["absolute"] for row in rows]
    assert str(skills.resolve()) in paths
    assert str(stray.resolve()) not in paths


def test_duplicate_extra_id_is_refused(tmp_path: Path, monkeypatch) -> None:
    dest = _pdf(tmp_path)
    from skillgate_ai.case_pack import save_pack_judge

    save_pack_judge(
        dest,
        {
            "extra_questions": [
                {
                    "id": "fileexists",
                    "type": "predicate",
                    "ask": "Did the file exist?",
                    "on_fail": "block",
                    "pass_if": {"gte": 0.8},
                }
            ]
        },
    )
    with pytest.raises(SuiteError, match="already"):
        save_pack_judge(
            dest,
            {
                "extra_questions": [
                    {
                        "id": "fileexists",
                        "type": "predicate",
                        "ask": "Did the file exist?",
                        "on_fail": "block",
                        "pass_if": {"gte": 0.8},
                    },
                    {
                        "id": "fileexists",
                        "type": "score",
                        "ask": "Clarity 1-5",
                        "on_fail": "block",
                    },
                ]
            },
        )


def test_create_pack_long_name_does_not_leave_folder(tmp_path: Path) -> None:
    from skillgate_ai.scaffold import create_pack

    name = "a" * 71
    with pytest.raises(SkillGateError):
        create_pack(tmp_path, name)
    assert not (tmp_path / name).exists()


def test_progress_done_task_keeps_expect_skill() -> None:
    from skillgate_ai.engine import TaskProgress
    from skillgate_ai.report import _progress_task_to_dict

    payload = _progress_task_to_dict(
        TaskProgress(
            task_id="extract-hello",
            prompt="Extract",
            status="done",
            passed=True,
            expect_skill="pdf",
            selected_skill="pdf",
        )
    )
    assert payload["expect_skill"] == "pdf"
    assert payload["happened"] != "No skill was picked, as expected."


def test_deploy_refuses_without_key_even_after_green(tmp_path: Path, monkeypatch) -> None:
    dest = _pdf(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SKILLGATE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SKILLGATE_AI_GATEWAY_API_KEY", raising=False)
    skills_home = tmp_path / "agent-skills"
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(skills_home))
    append_eval(dest, run_id="green", passed=True, report={"passed": True, "skill": "pdf"})
    result = runner.invoke(app, ["deploy", str(dest), "--target", "cursor"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 2, out
    assert "no model key" in out.lower()
    assert "keys set" in out.lower()
    assert not (skills_home / "pdf").exists()
    forced = runner.invoke(app, ["deploy", str(dest), "--target", "cursor", "--force"])
    forced_out = plain_text(forced.stdout + forced.stderr)
    assert forced.exit_code == 2, forced_out
    assert "keys set" in forced_out.lower()
    assert not (skills_home / "pdf").exists()
    log = dest / "evals" / "deploys.jsonl"
    assert not log.exists()


def test_deploy_accepts_skillgate_prefix_without_vault(tmp_path: Path, monkeypatch) -> None:
    dest = _pdf(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SKILLGATE_OPENAI_API_KEY", "sk-ci-prefix")
    skills_home = tmp_path / "agent-skills"
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(skills_home))
    append_eval(dest, run_id="green", passed=True, report={"passed": True, "skill": "pdf"})
    result = runner.invoke(app, ["deploy", str(dest), "--target", "cursor"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert (skills_home / "pdf" / "SKILL.md").is_file()


def test_cli_empty_checks_copy_names_the_file(tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "skills" / "empty-skill"
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text(
        "---\nname: empty-skill\ndescription: Empty skill for copy checks.\n---\n\n# Empty\n",
        encoding="utf-8",
    )
    (dest / "evals").mkdir()
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    from skillgate_ai.gate import run_check

    result = run_check(dest, source="cli", root=tmp_path)
    blob = f"{(result.error or {}).get('message') or ''} {(result.error or {}).get('hint') or ''}"
    assert "press run" not in blob.lower()
    assert "no checks" in blob.lower() or "add a check" in blob.lower()
    assert "evals/" not in blob
