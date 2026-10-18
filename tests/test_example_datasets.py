"""Bundled dataset examples: valid packs, and install that never overwrites."""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

from conftest import plain_text
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from skillgate_ai.api import create_app
from skillgate_ai.case_pack import load_case_pack
from skillgate_ai.cli import app
from skillgate_ai.examples import DATASET_EXAMPLES, install_examples, list_examples
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.pack import relevant_eval_fixtures

ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()

THEMES = (
    "json-response",
    "readme-writer",
    "log-summarizer",
    "sql-writer",
    "receipt-extractor",
)
RED_EXAMPLE = "json-response-sabotaged"
_PERSONAL = re.compile(
    r"@[a-z0-9.-]+\.[a-z]{2,}|\b\d{3}[-.]\d{3}[-.]\d{4}\b|\b\d{13,}\b|\bssn\b",
    re.IGNORECASE,
)


def _isolate_home(monkeypatch, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(tmp_path / "cursor-skills"))
    monkeypatch.setenv("SKILLGATE_CODEX_SKILLS", str(tmp_path / "codex-skills"))
    monkeypatch.setenv("SKILLGATE_CLAUDE_SKILLS", str(tmp_path / "claude-skills"))
    return home


def test_wheel_example_list_matches_the_package() -> None:
    spec = importlib.util.spec_from_file_location(
        "skillgate_build", ROOT / "src" / "skillgate_build.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from skillgate_ai.examples import BUNDLED_EXAMPLES

    assert module.EXAMPLE_NAMES == BUNDLED_EXAMPLES


def test_dataset_examples_cover_the_themes() -> None:
    assert set(THEMES) <= set(DATASET_EXAMPLES)
    assert RED_EXAMPLE in DATASET_EXAMPLES
    assert "pdf" not in DATASET_EXAMPLES


def test_each_dataset_pack_is_valid() -> None:
    saw_negative = False
    for name in DATASET_EXAMPLES:
        pack = ROOT / "skills" / name
        loaded = ingest_skill(pack)
        assert loaded.name == name
        cases = load_case_pack(pack)
        assert cases is not None
        assert cases.skill == name
        pinned = [case for case in cases.cases if case.status == "pinned"]
        assert 3 <= len(pinned) <= 6
        negatives = [case for case in pinned if not case.should_trigger]
        assert negatives, name
        saw_negative = True
        fixtures = {Path(item["src"]).name for item in relevant_eval_fixtures(pack)}
        assert fixtures, name
        assert not fixtures & {"alpha.pdf", "beta.pdf", "hello.pdf", "invoice.pdf", "notes.pdf"}
        for case in pinned:
            if not case.should_trigger:
                continue
            assert case.input.files, case.id
            assert case.golden is not None, case.id
            assert case.contains, case.id
            for item in case.input.files:
                assert (pack / item.src).is_file(), item.src
            assert (pack / case.golden.path).is_file(), case.golden.path
            prompt = case.prompt
            for needle in case.contains:
                assert needle not in prompt, f"{name}/{case.id} leaks {needle!r}"
        blob = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in pack.rglob("*") if path.is_file() and path.suffix != ".pdf")
        assert _PERSONAL.search(blob) is None, name
        for path in pack.rglob("*"):
            if path.is_file():
                assert path.stat().st_size < 4096, path
    assert saw_negative


def test_script_matches_golden_and_sabotaged_misses_it(tmp_path: Path) -> None:
    for name in DATASET_EXAMPLES:
        pack = ROOT / "skills" / name
        cases = load_case_pack(pack)
        assert cases is not None
        entry = pack / "scripts" / "agent_entry.py"
        assert entry.is_file(), name
        for case in cases.cases:
            if not case.should_trigger or case.golden is None:
                continue
            work = tmp_path / name / case.id
            work.mkdir(parents=True)
            for item in case.input.files:
                target = work / item.dest
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((pack / item.src).read_bytes())
            env = os.environ.copy()
            env["SKILLGATE_TASK"] = case.prompt
            proc = subprocess.run(
                [sys.executable, str(entry)],
                cwd=work,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            assert proc.returncode == 0, proc.stderr
            produced = (work / case.golden.output_path).read_text(encoding="utf-8")
            golden = (pack / case.golden.path).read_text(encoding="utf-8")
            if name == RED_EXAMPLE:
                assert produced != golden
                assert any(needle not in produced for needle in case.contains)
            else:
                assert produced == golden
                for needle in case.contains:
                    assert needle in produced


def test_install_leaves_existing_files_and_avoids_home(tmp_path: Path, monkeypatch) -> None:
    home = _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv("SKILLGATE_OPENAI_API_KEY", "sk-test-secret-value")
    dest = tmp_path / "skills"
    first = install_examples(dest)
    assert {row["name"] for row in first["installed"]} == set(DATASET_EXAMPLES)
    assert first["skipped"] == []
    marker = dest / "json-response" / "SKILL.md"
    original = marker.read_bytes()
    marker.write_text(original.decode("utf-8") + "\ncustom-marker\n", encoding="utf-8")
    kept = marker.read_bytes()
    golden = dest / "json-response" / "evals" / "goldens" / "flatten-orders.json"
    golden.unlink()
    second = install_examples(dest, names=["json-response"])
    assert marker.read_bytes() == kept
    assert "custom-marker" in marker.read_text(encoding="utf-8")
    assert golden.is_file()
    assert any(row["path"].endswith("SKILL.md") for row in second["skipped"])
    assert not any(path.is_file() for path in home.rglob("*"))
    listed = {row["name"] for row in list_examples()}
    assert set(DATASET_EXAMPLES) <= listed


def test_examples_cli_installs_into_dest_without_printing_keys(
    tmp_path: Path, monkeypatch
) -> None:
    home = _isolate_home(monkeypatch, tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setenv("SKILLGATE_ROOT", str(work))
    monkeypatch.setenv("SKILLGATE_OPENAI_API_KEY", "sk-test-secret-value")
    dest = tmp_path / "out-skills"
    listed = runner.invoke(app, ["examples", "list"])
    text = plain_text(listed.stdout + listed.stderr)
    assert listed.exit_code == 0, text
    for name in (*THEMES, RED_EXAMPLE):
        assert name in text
    assert "sk-test-secret-value" not in text
    installed = runner.invoke(app, ["examples", "install", "--dest", str(dest)])
    out = plain_text(installed.stdout + installed.stderr)
    assert installed.exit_code == 0, out
    assert (dest / "receipt-extractor" / "SKILL.md").is_file()
    assert "sk-test-secret-value" not in out
    (dest / "sql-writer" / "SKILL.md").write_text("keep-me\n", encoding="utf-8")
    again = runner.invoke(app, ["examples", "install", "sql-writer", "--dest", str(dest)])
    again_out = plain_text(again.stdout + again.stderr)
    assert again.exit_code == 0, again_out
    assert (dest / "sql-writer" / "SKILL.md").read_text(encoding="utf-8") == "keep-me\n"
    assert "sk-test-secret-value" not in again_out
    unknown = runner.invoke(app, ["examples", "install", "not-a-skill", "--dest", str(dest)])
    assert unknown.exit_code != 0
    assert not any(path.is_file() for path in home.rglob("*"))


def test_examples_api_install_skips_existing_files(tmp_path: Path, monkeypatch) -> None:
    home = _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv("SKILLGATE_MODE", "local")
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    client = TestClient(create_app(root=tmp_path), base_url="http://127.0.0.1:8765")
    catalog = client.get("/api/examples")
    assert catalog.status_code == 200
    names = {row["name"] for row in catalog.json()["examples"]}
    assert set(THEMES) <= names
    first = client.post("/api/examples/install", json={})
    assert first.status_code == 200, first.text
    body = first.json()
    assert {row["name"] for row in body["installed"]} == set(DATASET_EXAMPLES)
    skill = tmp_path / "skills" / "readme-writer" / "SKILL.md"
    skill.write_text("already-here\n", encoding="utf-8")
    second = client.post("/api/examples/install", json={"name": "readme-writer"})
    assert second.status_code == 200, second.text
    assert skill.read_text(encoding="utf-8") == "already-here\n"
    assert second.json()["skipped"]
    assert "sk-" not in second.text
    assert not any(path.is_file() for path in home.rglob("*"))
