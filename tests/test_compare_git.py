from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from skillgate_ai.compare import CompareError, run_versions_compare
from skillgate_ai.compare_git import find_git_root


def _git_repo_with_skill(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    pack = repo / "pdf"
    src = Path(__file__).resolve().parents[1] / "skills" / "pdf"
    import shutil

    shutil.copytree(src, pack)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "v1", "--allow-empty"],
        cwd=repo,
        check=True,
        capture_output=True,
        env={**__import__("os").environ, "GIT_AUTHOR_NAME": "t", "GIT_COMMITTER_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_EMAIL": "t@t"},
    )
    return pack


def test_find_git_root_rejects_non_repo(tmp_path: Path) -> None:
    pack = tmp_path / "pdf"
    pack.mkdir()
    with pytest.raises(CompareError, match="not inside a git"):
        find_git_root(pack)


def test_versions_git_invalid_ref_raises_compare_error(tmp_path: Path) -> None:
    pack = _git_repo_with_skill(tmp_path)
    with pytest.raises(CompareError, match="not valid"):
        run_versions_compare(
            pack,
            git_refs=["not-a-real-ref-xyz", "HEAD"],
            root=tmp_path,
        )


def test_versions_git_two_refs_uses_runner(tmp_path: Path) -> None:
    pack = _git_repo_with_skill(tmp_path)
    fp = "git-fp"

    def fake_run_check(target, **kwargs):
        from skillgate_ai.engine import SuiteReport, TaskReport
        from skillgate_ai.gate import CheckResult

        tasks = [TaskReport(task_id="c1", prompt="p", expect_skill=True, passed=True, scores=[], selected_skill="pdf", failures=[])]
        report = SuiteReport(
            suite="pdf",
            title="t",
            skill="pdf",
            skill_description="d",
            harness="llm",
            sandbox="local",
            passed=True,
            tasks=tasks,
            pack_fingerprint=fp,
            pack_case_ids=["c1"],
        )
        return CheckResult(exit_code=0, report=report)

    result = run_versions_compare(
        pack,
        git_refs=["HEAD", "HEAD"],
        root=tmp_path,
        run_check_fn=fake_run_check,
    )
    assert result.exit_code == 0
    assert result.payload["mode"] == "versions"
    assert len(result.payload["arms"]) == 2
