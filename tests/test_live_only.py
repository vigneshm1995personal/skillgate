from __future__ import annotations

import shutil
from pathlib import Path

from typer.testing import CliRunner

from conftest import plain_text
from skillgate_ai.cli import app
from skillgate_ai.gate import run_check
from skillgate_ai.harness import resolve_harness
from skillgate_ai.keys import set_vault_key

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN = (
    "built-in checker",
    "not a live model",
    "pdf twin",
    "Corrected SKILL.md description",
)


def test_check_without_key_exits_2(tmp_path: Path, monkeypatch) -> None:
    pack = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = runner.invoke(app, ["check", str(pack)])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 2, out
    assert "Settings" in out
    assert "skillgate keys set" in out
    assert "built-in checker" not in out.lower()
    assert "not a live model" not in out.lower()


def test_run_check_without_key_does_not_start(tmp_path: Path) -> None:
    pack = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    result = run_check(pack, source="test", root=tmp_path)
    assert result.exit_code == 2
    assert result.report is None
    assert result.error is not None
    message = (result.error.get("message") or "") + " " + (result.error.get("hint") or "")
    assert "skillgate keys set" in message
    assert "Settings" in message


def test_check_help_has_no_demo_flag() -> None:
    result = runner.invoke(app, ["check", "--help"], color=False)
    help_text = plain_text(result.stdout + result.stderr).lower()
    assert result.exit_code == 0, help_text
    assert "--demo" not in help_text
    assert "--live" not in help_text
    assert "--key-env" in help_text


def test_demo_flag_is_unknown(tmp_path: Path, monkeypatch) -> None:
    pack = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = runner.invoke(app, ["check", str(pack), "--demo"])
    combined = plain_text(result.stdout + result.stderr).lower()
    assert result.exit_code != 0
    assert "no such option" in combined or "unrecognized" in combined or "unexpected" in combined


def test_harness_demo_is_unknown(tmp_path: Path, monkeypatch) -> None:
    pack = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    set_vault_key(tmp_path, "OPENAI_API_KEY", "sk-test-not-a-real-key")
    result = runner.invoke(app, ["check", str(pack), "--harness", "demo"])
    combined = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, combined
    assert "Unknown harness" in combined
    assert "No model key found" not in combined


def test_resolve_harness_auto_is_not_demo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    set_vault_key(tmp_path, "OPENAI_API_KEY", "sk-test-not-a-real-key")
    from skillgate_ai.config import get_llm_config

    cfg = get_llm_config(tmp_path)
    harness = resolve_harness("auto", cfg)
    assert harness.name != "demo"


def test_customer_copy_denylist() -> None:
    roots = [
        ROOT / "src" / "skillgate_ai",
        ROOT / "web" / "src",
        ROOT / "README.md",
        ROOT / "docs" / "quickstart.md",
        ROOT / "docs" / "ui.md",
        ROOT / "docs" / "pack.md",
        ROOT / "docs" / "openai-judge.md",
        ROOT / ".env.example",
    ]
    hits: list[str] = []
    for root in roots:
        paths = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in paths:
            if not path.is_file():
                continue
            if path.suffix not in {".py", ".ts", ".tsx", ".md", ".example", ""} and path.name != ".env.example":
                continue
            if "plans" in path.parts or ".test." in path.name:
                continue
            text = path.read_text(encoding="utf-8")
            lower = text.lower()
            for needle in FORBIDDEN:
                if needle.lower() in lower:
                    hits.append(f"{path.relative_to(ROOT)}: {needle}")
    assert hits == [], "forbidden customer copy:\n" + "\n".join(hits)


def test_all_run_buttons_disable_without_key() -> None:
    eval_page = (ROOT / "web" / "src" / "components" / "dashboard" / "eval-page.tsx").read_text(
        encoding="utf-8"
    )
    check_list = (ROOT / "web" / "src" / "components" / "dashboard" / "check-list.tsx").read_text(
        encoding="utf-8"
    )
    results = (
        ROOT / "web" / "src" / "components" / "dashboard" / "checks-results-table.tsx"
    ).read_text(encoding="utf-8")
    gate = (ROOT / "web" / "src" / "components" / "dashboard" / "gate-page.tsx").read_text(
        encoding="utf-8"
    )
    assert "id=\"btn-run\"" in eval_page
    assert eval_page.count("!status?.has_key") >= 2
    assert "Run this check" in check_list
    assert "has_key" in check_list
    run_check = check_list.split("Run this check")[0][-400:]
    assert "hasKey" in run_check or "!hasKey" in run_check
    assert "has_key" in results
    table_run = results.split("Run this check")[0][-400:]
    assert "hasKey" in table_run or "!hasKey" in table_run
    fix_run = gate.split('id="btn-fix-run"')[1][:500]
    assert "has_key" in fix_run


def test_eval_banner_has_no_cli_or_env_names() -> None:
    text = (ROOT / "web" / "src" / "components" / "dashboard" / "eval-page.tsx").read_text(
        encoding="utf-8"
    )
    assert "skillgate keys set" not in text
    assert "skillgate ui" not in text
    assert "SKILLGATE_" not in text
    assert "--key-env" not in text
