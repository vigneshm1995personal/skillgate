"""CLI: skillgate / skillgate-ai. Human output first; JSON opt-in."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import typer
from rich.console import Console

from skillgate_ai import __version__
from skillgate_ai.config import get_llm_config, load_env
from skillgate_ai.demo_files import ensure_demo_pdfs
from skillgate_ai.engine import run_eval
from skillgate_ai.errors import SkillGateError
from skillgate_ai.eval_config import (
    EvalConfigError,
    EvalRunConfig,
    apply_eval_config,
    resolve_eval_config,
    stamp_resolved,
    with_timeout_effective,
)
from skillgate_ai.harness import live_harness_or_error, resolve_harness
from skillgate_ai.history import append_eval
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.observability import (
    capture_run_failure,
    eval_transaction,
    log_eval_finished,
    set_eval_passed,
)
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


def _persist_cli_eval(
    *,
    pack_root: Path | None,
    run_id: str,
    passed: bool,
    report: dict | None = None,
    error: dict | None = None,
    config: EvalRunConfig | dict | None = None,
) -> None:
    if pack_root is None or not pack_root.is_dir():
        return
    cfg = config.to_dict() if isinstance(config, EvalRunConfig) else config
    append_eval(
        pack_root,
        run_id=run_id,
        passed=passed,
        report=report,
        error=error,
        config=cfg,
    )


def _prepare_pack_fixtures(pack: Path) -> None:
    fixtures = pack / "evals" / "fixtures"
    if (pack / "SKILL.md").is_file():
        ensure_demo_pdfs(fixtures)


def _resolve_pack_and_spec(target: Path, root: Path):
    """Return (spec, skill_path, pack_root) for a pack dir or a suite YAML."""
    from skillgate_ai.case_pack import expand_from_pack

    path = target if target.is_absolute() else (root / target)
    if path.is_dir() and (path / "SKILL.md").is_file():
        _prepare_pack_fixtures(path)
        return expand_from_pack(path), path, path
    if path.is_file() and path.suffix in {".yaml", ".yml"}:
        return None, None, None
    if is_skill_pack(path):
        _prepare_pack_fixtures(path)
        return expand_from_pack(path), path, path
    raise SkillGateError(
        f"Not a skill pack or suite: {target}",
        hint="Pass a folder with SKILL.md + evals/cases.yaml, or a suite YAML.",
    )


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
    root = _boot()
    cfg = get_llm_config()
    sandbox_kind = sandbox or cfg.sandbox_pref
    spec = None
    suite_path = target if target.is_absolute() else root / target
    pack_root: Path | None = None
    skill_path = skill
    try:
        spec, skill_from_pack, pack_root = _resolve_pack_and_spec(target, root)
        if skill_from_pack is not None:
            skill_path = skill or skill_from_pack
    except SkillGateError as exc:
        if suite_path.is_file():
            spec = None
            pack_root = None
        else:
            console.print(exc.render())
            raise typer.Exit(exc.exit_code) from exc

    run_id = uuid.uuid4().hex[:12]
    skill_label = skill_path.name if skill_path else suite_path.stem
    run_cfg: EvalRunConfig | None = None
    resolved = None
    try:
        run_cfg = resolve_eval_config(
            harness_pref=harness,
            incoming={
                "model": model,
                "timeout_sec": timeout,
                "temperature": temperature,
                "reasoning_effort": reasoning_effort,
            },
            cfg=cfg,
            source="cli",
        )
        cfg = apply_eval_config(cfg, run_cfg)
        if live:
            resolved = live_harness_or_error(harness, cfg)
        else:
            resolved = resolve_harness(harness, cfg, demo=demo)
            if resolved.name == "demo" and not demo and harness == "auto" and not cfg.has_any_key:
                console.print(
                    "[dim]No BYOLLM key in .env — using demo harness (same scorers). "
                    "Set CURSOR_API_KEY, CODEX_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY "
                    "for a live run. See .env.example.[/dim]\n"
                )
        run_cfg = stamp_resolved(run_cfg, resolved.name, cfg)
        mode = "live" if live else ("demo" if resolved.name == "demo" else "live")
        with eval_transaction(
            run_id=run_id,
            skill=skill_label,
            harness=resolved.name,
            mode=mode,
            suite=suite_path.stem,
            sandbox=sandbox_kind,
        ):
            report = run_eval(
                None if spec is not None else suite_path,
                spec=spec,
                harness=resolved,
                sandbox_kind=sandbox_kind,
                docker_image=cfg.docker_image,
                project_root=root,
                skill_override=skill_path or (suite_path if spec is not None else None),
                run_id=run_id,
                timeout_override=run_cfg.timeout_sec,
                config=run_cfg.to_dict(),
            )
            run_cfg = with_timeout_effective(run_cfg, report.timeout_effective)
            report.config = run_cfg.to_dict()
            set_eval_passed(report.passed)
            log_eval_finished(
                run_id=run_id,
                skill=report.skill,
                harness=report.harness,
                passed=report.passed,
            )
            persist_root = Path(report.skill_path) if report.skill_path else pack_root
            _persist_cli_eval(
                pack_root=persist_root,
                run_id=run_id,
                passed=report.passed,
                report=report_to_dict(report),
                config=run_cfg,
            )
    except SkillGateError as exc:
        capture_run_failure(exc)
        persist_root = skill_path or pack_root
        if run_cfg is not None and not isinstance(exc, EvalConfigError) and persist_root:
            _persist_cli_eval(
                pack_root=persist_root,
                run_id=run_id,
                passed=False,
                error={"message": exc.message, "hint": exc.hint},
                config=run_cfg,
            )
        console.print(exc.render())
        raise typer.Exit(exc.exit_code) from exc

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

    red = not report.passed
    if expect_fail:
        if red:
            console.print("Suite failed as expected (intentional fail).")
            raise typer.Exit(0)
        console.print("Expected this suite to fail, but the gate was green.")
        raise typer.Exit(1)
    raise typer.Exit(0 if report.passed else 1)


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


if __name__ == "__main__":
    app()
