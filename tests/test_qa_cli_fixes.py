"""Full-QA must-fixes: JSON scrub, seed lock, CLI gaps, friendly errors."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from conftest import plain_text
from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.engine import SuiteReport, TaskReport
from skillgate_ai.gate import CheckResult
from skillgate_ai.history import append_eval

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]


def _pdf(tmp_path: Path) -> Path:
    dest = tmp_path / "skills" / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    return dest


def _leaky_report() -> SuiteReport:
    judge = {
        "status": "completed",
        "provider": "openai",
        "backend": "decisions",
        "model": "openai/gpt-6-luna-decisions",
        "display_name": "the judge",
        "answers": {"task_completion": {"choice": "Fully completed"}},
    }
    return SuiteReport(
        suite="pdf",
        title="pdf",
        skill="pdf",
        harness="cursor-agent",
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


def test_check_json_scrubs_scorer_names(tmp_path: Path, monkeypatch) -> None:
    dest = _pdf(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    def fake_run(*_args, **_kwargs):
        return CheckResult(report=_leaky_report(), exit_code=0)

    monkeypatch.setattr("skillgate_ai.cli.run_check", fake_run)
    result = runner.invoke(app, ["check", str(dest), "--json"])
    out = result.stdout + result.stderr
    assert result.exit_code == 0, out
    blob = out.lower()
    assert "openai" not in blob
    assert "decisions" not in blob
    assert "gpt-6-luna" not in blob
    payload = json.loads(result.stdout)
    assert payload["passed"] is True


def test_run_json_scrubs_scorer_names(tmp_path: Path, monkeypatch) -> None:
    dest = _pdf(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    def fake_run(*_args, **_kwargs):
        return CheckResult(report=_leaky_report(), exit_code=0)

    monkeypatch.setattr("skillgate_ai.cli.run_check", fake_run)
    result = runner.invoke(app, ["run", str(dest), "--json"])
    blob = (result.stdout + result.stderr).lower()
    assert result.exit_code == 0, result.stdout
    assert "openai" not in blob
    assert '"backend": "decisions"' not in result.stdout
    assert "gpt-6-luna" not in blob


def test_case_edit_refuses_seed_check(tmp_path: Path, monkeypatch) -> None:
    dest = _pdf(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    before = (dest / "evals" / "cases.yaml").read_text(encoding="utf-8")
    result = runner.invoke(
        app,
        ["case", "edit", str(dest), "--id", "extract-hello", "--prompt", "hacked"],
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "original checks stay" in out.lower()
    assert "hacked" not in (dest / "evals" / "cases.yaml").read_text(encoding="utf-8")
    assert (dest / "evals" / "cases.yaml").read_text(encoding="utf-8") == before


def test_remove_question_refuses_builtin(tmp_path: Path, monkeypatch) -> None:
    dest = _pdf(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app, ["judge", "remove-question", str(dest), "--id", "correctness"]
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "removed" not in out.lower()
    assert "stay" in out.lower() or "built" in out.lower()


def test_remove_question_unknown_does_not_claim_removed(
    tmp_path: Path, monkeypatch
) -> None:
    dest = _pdf(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["judge", "remove-question", str(dest), "--id", "nope"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "removed nope" not in out.lower()


def test_tryout_suite_is_only_the_named_check(tmp_path: Path) -> None:
    dest = _pdf(tmp_path)
    from skillgate_ai.case_pack import checks_from_pack, load_case_pack, suite_from_checks

    pack = load_case_pack(dest)
    assert pack is not None
    rows = [row for row in checks_from_pack(pack, include_drafts=True) if row["id"] == "extract-hello"]
    spec = suite_from_checks(dest, rows, tryout=True)
    assert [task.id for task in spec.tasks] == ["extract-hello"]


def test_pin_refused_seed_edit_does_not_rewrite_fixtures(tmp_path: Path) -> None:
    dest = _pdf(tmp_path)
    hello = dest / "evals" / "fixtures" / "hello.pdf"
    before = hello.read_bytes()
    from skillgate_ai.case_pack import pin_checks
    from skillgate_ai.errors import SuiteError

    with pytest.raises(SuiteError, match="original checks stay"):
        pin_checks(
            dest,
            [
                {
                    "id": "extract-hello",
                    "prompt": "HACKED via API",
                    "should_trigger": True,
                    "files": [{"src": "evals/fixtures/hello.pdf", "content": "OVERWRITTEN FIXTURE"}],
                }
            ],
        )
    assert hello.read_bytes() == before


def test_pin_refuses_underscored_seed_id(tmp_path: Path) -> None:
    dest = _pdf(tmp_path)
    hello = dest / "evals" / "fixtures" / "hello.pdf"
    before = hello.read_bytes()
    from skillgate_ai.case_pack import pin_checks
    from skillgate_ai.errors import SuiteError

    with pytest.raises(SuiteError, match="original checks stay"):
        pin_checks(
            dest,
            [
                {
                    "id": "extract_hello",
                    "prompt": "HACKED via underscore id",
                    "should_trigger": True,
                    "files": [
                        {"src": "evals/fixtures/hello.pdf", "content": "OVERWRITTEN FIXTURE"}
                    ],
                }
            ],
        )
    assert hello.read_bytes() == before
    yaml_text = (dest / "evals" / "cases.yaml").read_text(encoding="utf-8")
    assert "HACKED via underscore id" not in yaml_text


def test_case_add_underscored_seed_id_is_locked(tmp_path: Path, monkeypatch) -> None:
    dest = _pdf(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["case", "add", str(dest), "--id", "extract_hello", "--prompt", "hacked"],
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "original checks stay" in out.lower()
    assert "hacked" not in (dest / "evals" / "cases.yaml").read_text(encoding="utf-8")


def test_tryout_does_not_rewrite_locked_fixtures(tmp_path: Path) -> None:
    dest = _pdf(tmp_path)
    hello = dest / "evals" / "fixtures" / "hello.pdf"
    before = hello.read_bytes()
    from skillgate_ai.case_pack import load_case_pack, suite_from_checks
    from skillgate_ai.errors import SuiteError

    pack = load_case_pack(dest)
    prompt = next(case.prompt for case in pack.cases if case.id == "extract-hello")
    with pytest.raises(SuiteError, match="original checks stay"):
        suite_from_checks(
            dest,
            [
                {
                    "id": "extract-hello",
                    "prompt": "HACKED via tryout",
                    "should_trigger": True,
                    "files": [{"src": "evals/fixtures/hello.pdf", "content": "OVERWRITTEN"}],
                }
            ],
            tryout=True,
        )
    spec = suite_from_checks(
        dest,
        [
            {
                "id": "extract-hello",
                "prompt": prompt,
                "should_trigger": True,
                "files": [{"src": "evals/fixtures/hello.pdf", "content": "OVERWRITTEN"}],
            }
        ],
        tryout=True,
    )
    assert [task.id for task in spec.tasks] == ["extract-hello"]
    assert hello.read_bytes() == before


def test_check_case_runs_single_tryout(tmp_path: Path, monkeypatch) -> None:
    dest = _pdf(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    captured: dict = {}

    def fake_run(*_args, **kwargs):
        captured.update(kwargs)
        return CheckResult(
            report=None,
            exit_code=2,
            error={"message": "No agent is available to run checks."},
        )

    monkeypatch.setattr("skillgate_ai.cli.run_check", fake_run)
    result = runner.invoke(app, ["check", str(dest), "--case", "extract-hello"])
    assert result.exit_code == 2, result.stdout + result.stderr
    assert captured.get("tryout") is True
    checks = captured.get("checks") or []
    assert [row.get("id") for row in checks] == ["extract-hello"]


def test_check_unknown_case_is_friendly(tmp_path: Path, monkeypatch) -> None:
    dest = _pdf(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["check", str(dest), "--case", "no-such-check"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "no-such-check" in out
    assert "traceback" not in out.lower()


def test_add_question_choices(tmp_path: Path, monkeypatch) -> None:
    dest = _pdf(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        [
            "judge",
            "add-question",
            str(dest),
            "--ask",
            "Which stamp is on the page?",
            "--type",
            "pick one",
            "--id",
            "stamp_kind",
            "--choices",
            "paid",
            "--choices",
            "draft",
        ],
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    from skillgate_ai.case_pack import load_case_pack

    pack = load_case_pack(dest)
    extra = next(
        q
        for q in (pack.judge.extra_questions if pack and pack.judge else [])
        if q.id == "stamp_kind"
    )
    assert extra.type == "choice"
    assert [row.get("value") for row in (extra.choices or [])] == ["paid", "draft"]


def test_import_only_selects_one_skill(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(tmp_path / "cursor-skills"))
    monkeypatch.chdir(tmp_path)
    cursor = tmp_path / "cursor-skills"
    for name in ("alpha-notes", "beta-notes"):
        dest = cursor / name
        dest.mkdir(parents=True)
        (dest / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Take notes from a meeting.\n---\n\n# {name}\n",
            encoding="utf-8",
        )
    result = runner.invoke(
        app, ["import", "--source", "cursor", "--only", "alpha-notes"]
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert (tmp_path / "skills" / "alpha-notes" / "SKILL.md").is_file()
    assert not (tmp_path / "skills" / "beta-notes").exists()


def test_history_show_prints_run(tmp_path: Path, monkeypatch) -> None:
    dest = _pdf(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    append_eval(
        dest,
        run_id="run-cli",
        passed=True,
        report={"skill": "pdf", "passed": True, "passed_count": 8, "task_count": 8},
    )
    result = runner.invoke(app, ["history", "show", "run-cli", "--pack", str(dest)])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert "run-cli" in out
    assert "pass" in out.lower() or "8" in out


def test_history_show_unknown_is_friendly(tmp_path: Path, monkeypatch) -> None:
    dest = _pdf(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["history", "show", "missing-run", "--pack", str(dest)])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "missing-run" in out
    assert "traceback" not in out.lower()


def test_init_bad_path_is_friendly(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init", "/proc/nope/x"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "traceback" not in out.lower()
    assert "permission" in out.lower() or "couldn" in out.lower() or "folder" in out.lower()


def test_skill_paste_missing_file_is_friendly(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["skill", "paste", "--file", "/nope.md"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "traceback" not in out.lower()
    assert "nope" in out.lower() or "couldn" in out.lower() or "not found" in out.lower()


def test_case_add_existing_id_needs_force(tmp_path: Path, monkeypatch) -> None:
    dest = _pdf(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    first = runner.invoke(
        app,
        ["case", "add", str(dest), "--id", "qa-summary", "--prompt", "Summarize the scan."],
    )
    assert first.exit_code == 0, first.stdout
    second = runner.invoke(
        app,
        ["case", "add", str(dest), "--id", "qa-summary", "--prompt", "Overwrite me."],
    )
    out = plain_text(second.stdout + second.stderr)
    assert second.exit_code != 0, out
    assert "--force" in out.lower() or "already" in out.lower()
    from skillgate_ai.case_pack import load_case_pack

    pack = load_case_pack(dest)
    row = next(case for case in pack.cases if case.id == "qa-summary")
    assert row.prompt == "Summarize the scan."
    forced = runner.invoke(
        app,
        [
            "case",
            "add",
            str(dest),
            "--id",
            "qa-summary",
            "--prompt",
            "Replaced prompt.",
            "--force",
        ],
    )
    assert forced.exit_code == 0, forced.stdout
    pack = load_case_pack(dest)
    row = next(case for case in pack.cases if case.id == "qa-summary")
    assert row.prompt == "Replaced prompt."


def test_case_add_empty_prompt_is_refused(tmp_path: Path, monkeypatch) -> None:
    dest = _pdf(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["case", "add", str(dest), "--prompt", "   "])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "prompt" in out.lower()


def test_skill_write_generate_does_not_write_fixture_skill_md(
    tmp_path: Path, monkeypatch
) -> None:
    dest = _pdf(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    original = (dest / "SKILL.md").read_text(encoding="utf-8")
    result = runner.invoke(
        app, ["skill", "write", str(dest), "--path", "SKILL.md", "--generate"]
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert not (dest / "evals" / "fixtures" / "SKILL.md").exists()
    assert (dest / "SKILL.md").read_text(encoding="utf-8") == original


def test_keys_clear_unset_does_not_claim_cleared(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["keys", "clear", "OPENAI_API_KEY"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "cleared" not in out.lower()
