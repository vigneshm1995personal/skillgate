"""Fresh-env round 2 regressions (PR #23 follow-up)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from conftest import plain_text
from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.compare import run_versions_compare
from skillgate_ai.history import append_eval, load_compares
from skillgate_ai.judge_settings import judge_settings_path, load_judge_settings, save_judge_settings
from skillgate_ai.keys import CUSTOMER_SETTINGS_KEYS
from skillgate_ai.paths import config_root_for, project_root

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]


def test_init_workspace_counts_before_any_skill(tmp_path: Path, monkeypatch) -> None:
    nested = tmp_path / "ws" / "nested"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    runner.invoke(app, ["init"])
    assert (nested / "skills").is_dir()
    monkeypatch.delenv("SKILLGATE_ROOT", raising=False)
    assert project_root() == nested.resolve()
    assert config_root_for() == nested.resolve()


def test_new_from_nested_workspace_writes_under_nested(tmp_path: Path, monkeypatch) -> None:
    nested = tmp_path / "ws" / "nested"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    runner.invoke(app, ["init"])
    monkeypatch.delenv("SKILLGATE_ROOT", raising=False)
    result = runner.invoke(app, ["new", "inner"])
    assert result.exit_code == 0, result.stdout
    assert (nested / "skills" / "inner" / "SKILL.md").is_file()
    assert not (tmp_path / "ws" / "skills" / "inner").exists()


def test_check_non_pack_with_case_errors_not_no_checks(tmp_path: Path, monkeypatch) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "skills").mkdir()
    pdf = ROOT / "skills" / "pdf"
    monkeypatch.chdir(ws)
    monkeypatch.setenv("SKILLGATE_ROOT", str(ws))
    result = runner.invoke(app, ["check", "./pdf", "--case", "extract-hello"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "not a skill pack" in out.lower()
    assert "no checks yet" not in out.lower()


def test_keys_set_help_mentions_ai_gateway_key() -> None:
    result = runner.invoke(app, ["keys", "set", "--help"])
    out = plain_text(result.stdout + result.stderr)
    collapsed = " ".join(out.split())
    assert "AI Gateway key" in collapsed
    assert "Other" not in collapsed


def test_api_settings_keys_hides_judge_backend_key_names(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from skillgate_ai.api import create_app

    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    client = TestClient(create_app(root=tmp_path), base_url="http://127.0.0.1:8765")
    blob = json.dumps(client.get("/api/settings/keys").json())
    assert "JEV_API_KEY" not in blob
    assert "AWS_ACCESS_KEY_ID" not in blob
    assert "AI_GATEWAY_API_KEY" in blob


def test_judge_settings_file_omits_decisions_path_after_save(tmp_path: Path) -> None:
    path = judge_settings_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"provider": "compatible", "base_url": "https://x", "decisions_path": "/score"}\n',
        encoding="utf-8",
    )
    settings = load_judge_settings(tmp_path)
    assert settings.decisions_path == "/score"
    save_judge_settings(tmp_path, provider=settings.provider, base_url=settings.base_url)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "decisions_path" not in raw


def test_stored_config_label_has_no_via_gateway(tmp_path: Path) -> None:
    from skillgate_ai.eval_config import EvalRunConfig, coerce_eval_config

    cfg = EvalRunConfig(
        harness="cursor-agent",
        harness_pref="llm",
        model="openai/gpt-4o-mini",
        applied={"model": True, "via_gateway": True},
    )
    stored = cfg.to_dict()
    assert "via gateway" not in (stored.get("label") or "").lower()


def test_compare_versions_dry_run_cli(tmp_path: Path, monkeypatch) -> None:
    pack = tmp_path / "skills" / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["compare", "versions", str(pack), "--run", "a", "--run", "b", "--dry-run"],
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert "dry_run" in out.lower() or "checks" in out.lower()
    assert "started" not in out.lower()


def test_compare_versions_run_populates_case_rows(tmp_path: Path) -> None:
    pack = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    fp = "fp"
    for rid, passed2 in [("run-a", False), ("run-b", True)]:
        append_eval(
            pack,
            run_id=rid,
            passed=True,
            report={
                "pack_fingerprint": fp,
                "tasks": [
                    {"id": "c1", "passed": True},
                    {"id": "c2", "passed": passed2},
                ],
                "usage": {"tokens_total": 10, "cost_usd": 0.001},
            },
        )
    result = run_versions_compare(pack, run_ids=["run-a", "run-b"], root=tmp_path)
    assert len(result.payload["cases"]) == 2
    assert result.payload["arms"][0]["task_count"] == 2


def test_compare_versions_git_outside_repo_no_started(tmp_path: Path, monkeypatch) -> None:
    pack = tmp_path / "skills" / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["compare", "versions", str(pack), "--git", "HEAD~1", "--git", "HEAD"],
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "started" not in out.lower()


def test_failed_compare_appears_in_list(tmp_path: Path, monkeypatch) -> None:
    from skillgate_ai.compare import CompareError, run_models_compare, parse_arm_spec

    pack = tmp_path / "skills" / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))

    def boom(*_a, **_k):
        raise CompareError("Arm failed.")

    with pytest.raises(CompareError):
        run_models_compare(
            pack,
            arms=[
                parse_arm_spec("A:cursor-agent", arm_id="a", index=0),
                parse_arm_spec("B:cursor-agent", arm_id="b", index=1),
            ],
            root=tmp_path,
            run_check_fn=boom,
            compare_id="deadbeef0001",
        )
    rows = load_compares(pack)
    assert any(r.get("compare_id") == "deadbeef0001" and r.get("status") == "error" for r in rows)


def test_compare_cli_cost_precision(tmp_path: Path) -> None:
    from skillgate_ai.compare_format import format_compare_cli

    text = format_compare_cli(
        {
            "mode": "models",
            "skill": "pdf",
            "arms": [{"arm_id": "a", "label": "A", "usage": {"cost_usd": 0.0014}}],
            "cases": [],
        }
    )
    assert "$0.0014" in text


def test_customer_settings_keys_constant() -> None:
    assert "AI_GATEWAY_API_KEY" in CUSTOMER_SETTINGS_KEYS
    assert "JEV_API_KEY" not in CUSTOMER_SETTINGS_KEYS
