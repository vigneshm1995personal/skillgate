"""GitHub Action metadata and the keyless check runner."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "action.yml"
README = ROOT / "README.md"
RELEASE = ROOT / ".github" / "workflows" / "release.yml"
WORKFLOW = ROOT / ".github" / "workflows" / "skillgate-action.yml"
SCRIPT = ROOT / "scripts" / "skillgate_action.py"

_PROVIDER_NAMES = (
    "openai",
    "anthropic",
    "claude",
    "cursor",
    "codex",
    "cloudflare",
    "openrouter",
    "promptfoo",
    "gpt-",
    "jev",
    "typesafe",
)


def _load_action_module():
    spec = importlib.util.spec_from_file_location("skillgate_action", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _action() -> dict:
    return yaml.safe_load(ACTION.read_text(encoding="utf-8"))


def test_action_metadata_is_marketplace_ready() -> None:
    meta = _action()
    assert meta["name"] == "Skill Gate"
    description = meta["description"]
    lowered = description.lower()
    assert "exit 0" in lowered
    assert "exit 1" in lowered
    assert "exit 2" in lowered
    for name in _PROVIDER_NAMES:
        assert name not in lowered, name
    branding = meta["branding"]
    assert branding["icon"] == "shield"
    assert branding["color"] == "black"
    assert meta["runs"]["using"] == "composite"
    steps = meta["runs"]["steps"]
    setup = next(step for step in steps if step.get("uses", "").startswith("actions/setup-python@"))
    assert setup["with"]["python-version"] == "3.11"
    check = next(step for step in steps if step.get("id") == "check")
    assert "skillgate_action.py" in check["run"]
    assert meta["outputs"]["exit-code"]["value"] == "${{ steps.check.outputs.exit-code }}"


def test_action_inputs_match_the_check_command() -> None:
    inputs = _action()["inputs"]
    assert inputs["path"]["default"] == "skills"
    assert inputs["version"]["default"] == "latest"
    for name in ("judge", "model", "base-url", "account-id", "harness", "args"):
        assert name in inputs
        assert inputs[name]["required"] is False
    blob = "\n".join(item.get("description", "") for item in inputs.values()).lower()
    for name in _PROVIDER_NAMES:
        assert name not in blob, name
    assert "decision model" in inputs["judge"]["description"].lower()
    assert "another decision model" in inputs["judge"]["description"].lower()


def test_readme_has_a_copy_paste_workflow() -> None:
    text = README.read_text(encoding="utf-8")
    assert "uses: vigneshm1995personal/skillgate@v1" in text
    assert "SKILLGATE_JEV_API_KEY" in text
    assert "path: skills/pdf" in text
    assert "--no-judge" in text
    assert "exit 2" in text.lower() or "exit 2" in text


def test_self_test_workflow_expects_cannot_run_without_a_paid_key() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    job = workflow["jobs"]["action"]
    steps = job["steps"]
    gate = next(step for step in steps if step.get("uses") in {"./", "./."})
    assert gate["with"]["path"] == "skills/pdf"
    assert "--no-judge" in gate["with"]["args"]
    assert gate.get("continue-on-error") is True
    assert "secrets." not in text
    assert "OPENAI" not in text
    joined = "\n".join(step.get("run", "") for step in steps if "run" in step)
    assert 'exit-code' in joined
    assert '"2"' in joined or "'2'" in joined
    assert "No agent is available to run checks." in joined


def test_release_workflow_does_not_publish_pypi_from_action_tags() -> None:
    text = RELEASE.read_text(encoding="utf-8")
    assert '- "v0.*.*"' in text
    assert '- "v*.*.*"' not in text
    assert "v1" in text
    for job in ("pypi", "ghcr"):
        assert f"{job}:" in text
    assert text.count("startsWith") >= 2
    assert "v0." in text


def test_latest_version_installs_that_exact_release(monkeypatch, tmp_path) -> None:
    mod = _load_action_module()
    installed: list[str] = []
    commands: list[list[str]] = []

    monkeypatch.setenv("INPUT_VERSION", "latest")
    monkeypatch.setenv("INPUT_PATH", "skills/pdf")
    monkeypatch.setenv("INPUT_ARGS", "--no-judge")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out.txt"))
    monkeypatch.setattr(mod, "fetch_latest_version", lambda: "0.7.9")

    def install(version: str) -> None:
        installed.append(version)

    def run(cmd: list[str]) -> tuple[int, str]:
        commands.append(cmd)
        return 2, "No agent is available to run checks."

    monkeypatch.setattr(mod, "install_release", install)
    monkeypatch.setattr(mod, "run_command", run)
    assert mod.main() == 2
    assert installed == ["0.7.9"]
    assert commands == [
        ["skillgate", "check", "skills/pdf", "--no-judge", "--summary", "github"]
    ]
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "Cannot run" in summary
    assert "exit 2" in summary
    assert "No agent is available to run checks." in summary
    output = (tmp_path / "out.txt").read_text(encoding="utf-8")
    assert "exit-code=2" in output
    assert "result=cannot-run" in output


def test_explicit_version_is_passed_to_pip_install() -> None:
    mod = _load_action_module()
    assert mod.pip_install_args("0.7.9") == [
        "skillgate-ai==0.7.9",
    ]


def test_invalid_version_does_not_install(monkeypatch, tmp_path) -> None:
    mod = _load_action_module()
    monkeypatch.setenv("INPUT_VERSION", "0.7.9; rm -rf /")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out.txt"))
    monkeypatch.setattr(
        mod,
        "install_release",
        lambda version: (_ for _ in ()).throw(AssertionError("install must not run")),
    )
    assert mod.main() == 2
    assert "Cannot run" in (tmp_path / "summary.md").read_text(encoding="utf-8")


def test_judge_failure_does_not_run_check_or_switch_models(monkeypatch, tmp_path) -> None:
    mod = _load_action_module()
    commands: list[list[str]] = []
    monkeypatch.setenv("INPUT_VERSION", "0.7.9")
    monkeypatch.setenv("INPUT_JUDGE", "chat")
    monkeypatch.setenv("INPUT_PATH", "skills/pdf")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out.txt"))
    monkeypatch.setattr(mod, "install_release", lambda version: None)

    def run(cmd: list[str]) -> tuple[int, str]:
        commands.append(cmd)
        return 0, ""

    monkeypatch.setattr(mod, "run_command", run)
    assert mod.main() == 2
    assert commands == []
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "decision model" in summary.lower()
    assert "exit 2" in summary


def test_rejected_decision_model_does_not_fall_back(monkeypatch, tmp_path) -> None:
    mod = _load_action_module()
    commands: list[list[str]] = []
    monkeypatch.setenv("INPUT_VERSION", "0.7.9")
    monkeypatch.setenv("INPUT_JUDGE", "jev")
    monkeypatch.setenv("INPUT_MODEL", "typesafe/jev-1.14")
    monkeypatch.setenv("INPUT_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("INPUT_ACCOUNT_ID", "account1")
    monkeypatch.setenv("INPUT_HARNESS", "auto")
    monkeypatch.setenv("INPUT_PATH", "skills/pdf")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out.txt"))
    monkeypatch.setattr(mod, "install_release", lambda version: None)

    def run(cmd: list[str]) -> tuple[int, str]:
        commands.append(cmd)
        if "check" in cmd:
            raise AssertionError("check must not run after a rejected decision model")
        return 2, "This decision model needs an API key."

    monkeypatch.setattr(mod, "run_command", run)
    assert mod.main() == 2
    assert commands == [
        [
            "skillgate",
            "judge",
            "provider",
            "set",
            "jev",
            "--model",
            "typesafe/jev-1.14",
            "--base-url",
            "https://openrouter.ai/api/v1",
            "--account-id",
            "account1",
        ]
    ]


def test_accepted_judge_then_check(monkeypatch, tmp_path) -> None:
    mod = _load_action_module()
    commands: list[list[str]] = []
    monkeypatch.setenv("INPUT_VERSION", "0.7.9")
    monkeypatch.setenv("INPUT_JUDGE", "jev")
    monkeypatch.setenv("INPUT_PATH", "skills/pdf")
    monkeypatch.setenv("INPUT_HARNESS", "auto")
    monkeypatch.setenv("INPUT_ARGS", "--expect-fail")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out.txt"))
    monkeypatch.setattr(mod, "install_release", lambda version: None)

    def run(cmd: list[str]) -> tuple[int, str]:
        commands.append(cmd)
        if cmd[1] == "check":
            return 1, "Gate is red."
        return 0, "jev"

    monkeypatch.setattr(mod, "run_command", run)
    assert mod.main() == 1
    assert commands[0][:5] == ["skillgate", "judge", "provider", "set", "jev"]
    assert commands[1] == [
        "skillgate",
        "check",
        "skills/pdf",
        "--harness",
        "auto",
        "--expect-fail",
        "--summary",
        "github",
    ]
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "Failed" in summary
    assert "exit 1" in summary
    output = (tmp_path / "out.txt").read_text(encoding="utf-8")
    assert "exit-code=1" in output
    assert "result=fail" in output


def test_pass_writes_a_green_summary(monkeypatch, tmp_path, capsys) -> None:
    mod = _load_action_module()
    monkeypatch.setenv("INPUT_VERSION", "0.7.9")
    monkeypatch.setenv("INPUT_PATH", "skills/pdf")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out.txt"))
    monkeypatch.setattr(mod, "install_release", lambda version: None)
    monkeypatch.setattr(mod, "run_command", lambda cmd: (0, "Gate is green."))
    assert mod.main() == 0
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "Passed" in summary
    assert "exit 0" in summary
    assert "result=pass" in (tmp_path / "out.txt").read_text(encoding="utf-8")
    assert "Skill Gate passed (exit 0)." in capsys.readouterr().out


def test_secrets_are_masked_and_never_printed(monkeypatch, tmp_path, capsys) -> None:
    mod = _load_action_module()
    secret = "sk-test-secret-value"
    commands: list[list[str]] = []
    monkeypatch.setenv("SKILLGATE_OPENAI_API_KEY", secret)
    monkeypatch.setenv("SKILLGATE_JEV_API_KEY", secret)
    monkeypatch.setenv("INPUT_VERSION", "0.7.9")
    monkeypatch.setenv("INPUT_PATH", "skills/pdf")
    monkeypatch.setenv("INPUT_JUDGE", "jev")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out.txt"))
    monkeypatch.setattr(mod, "install_release", lambda version: None)

    def run(cmd: list[str]) -> tuple[int, str]:
        commands.append(cmd)
        if "check" in cmd:
            return 2, f"No agent is available to run checks. key={secret}"
        return 0, "ok"

    monkeypatch.setattr(mod, "run_command", run)
    assert mod.main() == 2
    visible = [
        line
        for line in capsys.readouterr().out.splitlines()
        if not line.startswith("::add-mask::")
    ]
    assert secret not in "\n".join(visible)
    assert "::add-mask::" not in (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert secret not in (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert secret not in (tmp_path / "out.txt").read_text(encoding="utf-8")
    flat = " ".join(" ".join(cmd) for cmd in commands)
    assert secret not in flat


def test_user_summary_flag_is_not_duplicated(monkeypatch) -> None:
    mod = _load_action_module()
    monkeypatch.setenv("INPUT_PATH", "skills/pdf")
    monkeypatch.setenv("INPUT_ARGS", "--summary json --no-judge")
    assert mod.check_command() == [
        "skillgate",
        "check",
        "skills/pdf",
        "--summary",
        "json",
        "--no-judge",
    ]


def test_default_path_is_skills(monkeypatch) -> None:
    mod = _load_action_module()
    monkeypatch.delenv("INPUT_PATH", raising=False)
    assert mod.check_command()[2] == "skills"


def test_pip_failure_exits_2(monkeypatch, tmp_path) -> None:
    mod = _load_action_module()
    monkeypatch.setenv("INPUT_VERSION", "0.7.9")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out.txt"))

    def install(version: str) -> None:
        raise mod.ActionError("Could not install skillgate-ai==0.7.9.")

    monkeypatch.setattr(mod, "install_release", install)
    monkeypatch.setattr(
        mod,
        "run_command",
        lambda cmd: (_ for _ in ()).throw(AssertionError("check must not run")),
    )
    assert mod.main() == 2
    assert "exit-code=2" in (tmp_path / "out.txt").read_text(encoding="utf-8")


def test_missing_skillgate_binary_is_exit_2() -> None:
    mod = _load_action_module()
    code, detail = mod.run_command(["skillgate-not-installed", "check", "skills"])
    assert code == 2
    assert "Could not run skillgate-not-installed." in detail


def test_install_release_invokes_pip(monkeypatch) -> None:
    mod = _load_action_module()
    seen: list[list[str]] = []

    def fake_run(cmd, check=False):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    mod.install_release("0.7.9")
    assert seen[0][1:3] == ["-m", "pip"]
    assert seen[0][3] == "install"
    assert seen[0][4] == "skillgate-ai==0.7.9"
