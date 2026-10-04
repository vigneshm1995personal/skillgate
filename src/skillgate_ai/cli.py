"""CLI: skillgate / skillgate-ai. Human output first; JSON opt-in."""

from __future__ import annotations

import os
from pathlib import Path

import typer
from rich.console import Console

from skillgate_ai import __version__
from skillgate_ai.config import load_env
from skillgate_ai.errors import SkillGateError
from skillgate_ai.gate import run_check
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.paths import is_skill_pack, project_root
from skillgate_ai.report import format_cli, format_github, report_to_dict
from skillgate_ai.suite import discover_suites

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Skill Gate — evaluate agent skills. Pack on disk + `skillgate check` (exit 0/1).",
)
console = Console(stderr=False)


def _boot() -> Path:
    root = project_root()
    load_env(root)
    return root


@app.callback()
def _main() -> None:
    """Skill Gate."""


@app.command()
def version() -> None:
    """Print the CLI version."""
    console.print(__version__)


@app.command()
def ingest(
    skill: Path = typer.Argument(..., help="Path to a skill folder containing SKILL.md"),
) -> None:
    """Validate a skill folder against the agentskills spec."""
    try:
        loaded = ingest_skill(skill)
    except SkillGateError as exc:
        console.print(exc.render())
        raise typer.Exit(exc.exit_code) from exc
    console.print(f"OK  {loaded.name}")
    console.print(loaded.description)


def _run_gate(
    *,
    target: Path,
    skill: Path | None,
    harness: str,
    sandbox: str,
    demo: bool,
    live: bool,
    expect_fail: bool,
    summary: str,
    json_out: bool,
    model: str | None,
    timeout: int | None,
    temperature: float | None,
    reasoning_effort: str | None,
) -> None:
    result = run_check(
        target,
        skill=skill,
        harness=harness,
        sandbox=sandbox,
        demo=demo,
        live=live,
        expect_fail=expect_fail,
        model=model,
        timeout=timeout,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
        source="cli",
    )
    if result.demo_notice:
        console.print(f"[dim]{result.demo_notice}[/dim]\n")
    if result.error:
        console.print(result.error["message"])
        hint = result.error.get("hint")
        if hint:
            console.print(hint)
        raise typer.Exit(result.exit_code)
    report = result.report
    if report is None:
        raise typer.Exit(result.exit_code)
    if json_out or summary == "json":
        import json as _json

        console.print(_json.dumps(report_to_dict(report), indent=2))
    elif summary == "github":
        text = format_github(report)
        console.print(text)
        gh = os.environ.get("GITHUB_STEP_SUMMARY")
        if gh:
            path = Path(gh)
            prev = path.read_text(encoding="utf-8") if path.exists() else ""
            path.write_text(prev + text, encoding="utf-8")
    else:
        console.print(format_cli(report))
    if result.expect_fail_notice:
        console.print(result.expect_fail_notice)
    raise typer.Exit(result.exit_code)


_HARNESS_HELP = "auto | cursor-agent | codex | llm | demo"
_SANDBOX_HELP = "local | docker"


@app.command("check")
def check_pack(
    pack: Path = typer.Argument(..., help="Skill pack directory (SKILL.md + evals/)"),
    harness: str = typer.Option("auto", "--harness", help=_HARNESS_HELP),
    sandbox: str = typer.Option("local", "--sandbox", help=_SANDBOX_HELP),
    demo: bool = typer.Option(False, "--demo", help="Use the demo harness (no API key)"),
    live: bool = typer.Option(False, "--live", help="Require a BYOLLM key; do not fall back"),
    expect_fail: bool = typer.Option(
        False,
        "--expect-fail",
        help="Exit 0 only if the suite is red (sabotaged / intentional-fail demo)",
    ),
    summary: str = typer.Option("cli", "--summary", help="cli | github | json"),
    json_out: bool = typer.Option(False, "--json", help="Machine JSON (not the primary UX)"),
    model: str | None = typer.Option(None, "--model", help="Requested model id"),
    timeout: int | None = typer.Option(None, "--timeout", help="Per-task timeout seconds"),
    temperature: float | None = typer.Option(None, "--temperature", help="BYOLLM temperature (0–2)"),
    reasoning_effort: str | None = typer.Option(
        None, "--reasoning-effort", help="Codex reasoning: low | medium | high | ultra"
    ),
) -> None:
    """Run pack-local evals/cases.yaml. Exit 0 if green, 1 if red. No account required."""
    _run_gate(
        target=pack,
        skill=None,
        harness=harness,
        sandbox=sandbox,
        demo=demo,
        live=live,
        expect_fail=expect_fail,
        summary=summary,
        json_out=json_out,
        model=model,
        timeout=timeout,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
    )


@app.command("run")
def run_suite(
    suite: Path = typer.Argument(..., help="Skill pack directory or eval suite YAML"),
    skill: Path | None = typer.Option(None, "--skill", help="Override the skill folder"),
    harness: str = typer.Option("auto", "--harness", help=_HARNESS_HELP),
    sandbox: str = typer.Option("local", "--sandbox", help=_SANDBOX_HELP),
    demo: bool = typer.Option(False, "--demo", help="Use the demo harness (no API key)"),
    live: bool = typer.Option(False, "--live", help="Require a BYOLLM key; do not fall back"),
    expect_fail: bool = typer.Option(
        False,
        "--expect-fail",
        help="Exit 0 only if the suite is red (sabotaged / intentional-fail demo)",
    ),
    summary: str = typer.Option("cli", "--summary", help="cli | github | json"),
    json_out: bool = typer.Option(False, "--json", help="Machine JSON (not the primary UX)"),
    model: str | None = typer.Option(None, "--model", help="Requested model id"),
    timeout: int | None = typer.Option(None, "--timeout", help="Per-task timeout seconds"),
    temperature: float | None = typer.Option(None, "--temperature", help="BYOLLM temperature (0–2)"),
    reasoning_effort: str | None = typer.Option(
        None, "--reasoning-effort", help="Codex reasoning: low | medium | high | ultra"
    ),
) -> None:
    """Run an eval pack or suite YAML. Prefer `skillgate check` for CI."""
    _run_gate(
        target=suite,
        skill=skill,
        harness=harness,
        sandbox=sandbox,
        demo=demo,
        live=live,
        expect_fail=expect_fail,
        summary=summary,
        json_out=json_out,
        model=model,
        timeout=timeout,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
    )


@app.command()
def deploy(
    pack: Path = typer.Argument(..., help="Gated skill pack to copy"),
    target: str = typer.Option("cursor", "--target", help="cursor | claude | codex"),
) -> None:
    """Copy a skill pack into a local agent skills directory."""
    from skillgate_ai.deploy import get_adapter

    try:
        loaded = ingest_skill(pack)
        result = get_adapter(target).install(skill=loaded, source=Path(pack))
    except SkillGateError as exc:
        console.print(exc.render())
        raise typer.Exit(exc.exit_code) from exc
    console.print(result["message"])


@app.command("list")
def list_assets() -> None:
    """Show skills/ and evals/ (skill-first paths)."""
    root = _boot()
    console.print(f"root  {root}")
    skills_root = root / "skills"
    if skills_root.is_dir():
        console.print("skills/")
        for child in sorted(skills_root.iterdir()):
            if child.is_dir() and (child / "SKILL.md").is_file():
                console.print(f"  {child.name}")
    elif is_skill_pack(root):
        console.print(f"pack  {root.name}")
    evals_root = root / "evals"
    if evals_root.is_dir():
        cases = evals_root / "cases.yaml"
        if cases.is_file():
            console.print("evals/cases.yaml")
        console.print("evals/")
        for suite in discover_suites(evals_root):
            console.print(f"  {suite.name}")


@app.command("ui")
def ui_cmd(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address (default loopback)"),
    port: int = typer.Option(8765, "--port", help="Port (default 8765, not hosted 8477)"),
    root: Path | None = typer.Option(None, "--root", help="Workspace root for browse/create"),
    pack: Path | None = typer.Option(None, "--pack", help="Open this pack instead of the picker"),
    open_browser: bool = typer.Option(False, "--open", help="Open the loopback URL in a browser"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open a browser"),
) -> None:
    """Local setup wizard + check UI. No account. Not hosted serve. Docker check /pack unchanged."""
    from skillgate_ai.local_ui.server import serve_ui

    workspace = (root or project_root()).expanduser().resolve()
    load_env(workspace)
    should_open = open_browser and not no_browser
    if host not in {"127.0.0.1", "localhost", "::1"}:
        console.print(
            "Warning: binding off loopback. This is still a local process with no auth — "
            "not the hosted Skill Gate app."
        )
    console.print(
        "Local Skill Gate UI — no account, demo harness if no key. "
        "CI/Docker still use `skillgate check` (image CMD check /pack)."
    )
    try:
        serve_ui(
            root=workspace,
            host=host,
            port=port,
            pack=pack,
            open_browser=should_open,
        )
    except OSError as exc:
        console.print(f"Could not bind {host}:{port}: {exc}")
        raise typer.Exit(1) from exc


if __name__ == "__main__":
    app()
