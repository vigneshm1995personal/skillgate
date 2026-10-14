from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from skillgate_ai.harness import Completion, LLMHarness
from skillgate_ai.harness_llm_run import command_allowed
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.sandbox import LocalSandbox
from skillgate_ai.usage import Usage

ROOT = Path(__file__).resolve().parents[1]


def test_write_commit_script_is_allowlisted() -> None:
    cmd = [
        "python3",
        ".skillgate/skills/sample-skill/scripts/write_commit.py",
        "feat: add csv export for orders",
    ]
    assert command_allowed(cmd, "sample-skill")


def test_write_commit_persists_model_authored_subject(tmp_path: Path) -> None:
    pack = tmp_path / "sample-skill"
    shutil.copytree(ROOT / "skills" / "sample-skill", pack)
    script = pack / "scripts" / "write_commit.py"
    env = {
        **dict(__import__("os").environ),
        "SKILLGATE_TASK": "save to output/commit.txt",
    }
    proc = subprocess.run(
        [sys.executable, str(script), "feat: add csv export for orders"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    text = (tmp_path / "output" / "commit.txt").read_text(encoding="utf-8")
    assert text.strip() == "feat: add csv export for orders"


def test_llm_harness_runs_write_commit_when_model_emits_run(monkeypatch, tmp_path: Path) -> None:
    from test_judge import _cfg

    pack = tmp_path / "sample-skill"
    shutil.copytree(ROOT / "skills" / "sample-skill", pack)
    skill = ingest_skill(pack, strict=False)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    dest_skill = workspace / ".skillgate" / "skills" / "sample-skill"
    dest_skill.mkdir(parents=True)
    shutil.copytree(pack, dest_skill, dirs_exist_ok=True)
    (workspace / ".skillgate" / "selected.json").write_text(
        '{"skill": "sample-skill"}', encoding="utf-8"
    )
    harness = LLMHarness(_cfg(openai_api_key="sk-test"))
    subject = "feat: add csv export for orders"
    run_line = (
        "RUN: python3 .skillgate/skills/sample-skill/scripts/write_commit.py "
        f"{subject}"
    )

    def fake_complete(act_prompt, timeout_sec):
        del act_prompt, timeout_sec
        return Completion(text=run_line, usage=Usage(tokens_in=1, tokens_out=1))

    monkeypatch.setattr(harness, "_complete", fake_complete)
    sandbox = LocalSandbox(workspace)
    harness.run(sandbox, "Write output/commit.txt for export csv diff", [skill], timeout_sec=5)
    assert (workspace / "output" / "commit.txt").read_text(encoding="utf-8").strip() == subject
