"""CLI: skillgate / skillgate-ai. Human output first; JSON opt-in."""

from __future__ import annotations

import getpass
import json
import os
import sys
from pathlib import Path

import typer
from rich.console import Console

from skillgate_ai import __version__
from skillgate_ai.config import load_env
from skillgate_ai.errors import SkillGateError
from skillgate_ai.gate import run_check
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.keys import bind_key_env, reset_key_env_bindings
from skillgate_ai.paths import is_skill_pack, project_root, resolve_user_path
from skillgate_ai.report import format_cli, format_github, report_to_dict
from skillgate_ai.suite import discover_suites

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False,
    help="Skill Gate — evaluate agent skills. Pack on disk + `skillgate check` (exit 0/1).",
)
console = Console(stderr=False)


def _emit_json(payload: object) -> None:
    """Write JSON to stdout with no terminal wrapping. Safe to pipe to json.tool."""
    sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")
    sys.stdout.flush()


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
        raise typer.Exit(exc.exit_code) from None
    console.print(f"OK  {loaded.name}")
    console.print(loaded.description)


def _present_check(result) -> None:
    if result.error:
        console.print(result.error["message"])
        hint = result.error.get("hint")
        if hint:
            console.print(hint)
    elif result.report is not None:
        console.print(format_cli(result.report))


def _parse_targets(*values: str | None, default: str = "cursor") -> list[str]:
    found: list[str] = []
    for raw in values:
        if not raw:
            continue
        for part in raw.split(","):
            name = part.strip().lower()
            if name and name not in found:
                found.append(name)
    if found:
        return found
    return [part.strip() for part in default.split(",") if part.strip()]


def _bind_key_env(key_env: list[str] | None) -> None:
    reset_key_env_bindings()
    bind_key_env(key_env)


def _stdin_is_tty() -> bool:
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


def _read_omitted_key() -> str:
    if _stdin_is_tty():
        return getpass.getpass("Value (hidden): ")
    return sys.stdin.read()


def _run_gate(
    *,
    target: Path,
    skill: Path | None,
    harness: str,
    sandbox: str,
    expect_fail: bool,
    summary: str,
    json_out: bool,
    model: str | None,
    timeout: int | None,
    temperature: float | None,
    reasoning_effort: str | None,
    key_env: list[str] | None = None,
) -> None:
    _bind_key_env(key_env)
    result = run_check(
        target,
        skill=skill,
        harness=harness,
        sandbox=sandbox,
        expect_fail=expect_fail,
        model=model,
        timeout=timeout,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
        source="cli",
    )
    machine = json_out or summary == "json"
    if not machine and summary != "github":
        _present_check(result)
        if result.error or result.report is None:
            raise typer.Exit(result.exit_code)
        if result.expect_fail_notice:
            console.print(result.expect_fail_notice)
        raise typer.Exit(result.exit_code)
    if result.error:
        if machine:
            _emit_json(
                {
                    "error": result.error["message"],
                    "hint": result.error.get("hint"),
                    "exit_code": result.exit_code,
                }
            )
        else:
            console.print(result.error["message"])
            hint = result.error.get("hint")
            if hint:
                console.print(hint)
        raise typer.Exit(result.exit_code)
    report = result.report
    if report is None:
        raise typer.Exit(result.exit_code)
    if machine:
        _emit_json(report_to_dict(report))
    else:
        text = format_github(report)
        console.print(text)
        gh = os.environ.get("GITHUB_STEP_SUMMARY")
        if gh:
            path = Path(gh)
            prev = path.read_text(encoding="utf-8") if path.exists() else ""
            path.write_text(prev + text, encoding="utf-8")
    if result.expect_fail_notice:
        if machine:
            sys.stderr.write(f"{result.expect_fail_notice}\n")
        else:
            console.print(result.expect_fail_notice)
    raise typer.Exit(result.exit_code)


_HARNESS_HELP = "auto | cursor-agent | codex | llm"
_SANDBOX_HELP = "local | docker"
_KEY_ENV_HELP = "Use this process env name as a Skill Gate key (repeatable). Example: --key-env OPENAI_API_KEY"


@app.command("check")
def check_pack(
    pack: Path = typer.Argument(..., help="Skill pack directory (SKILL.md + evals/)"),
    harness: str = typer.Option("auto", "--harness", help=_HARNESS_HELP),
    sandbox: str = typer.Option("local", "--sandbox", help=_SANDBOX_HELP),
    expect_fail: bool = typer.Option(
        False,
        "--expect-fail",
        help="Exit 0 only if the suite is red (sabotaged / intentional-fail)",
    ),
    summary: str = typer.Option("cli", "--summary", help="cli | github | json"),
    json_out: bool = typer.Option(False, "--json", help="Machine JSON (not the primary UX)"),
    model: str | None = typer.Option(None, "--model", help="Requested model id"),
    timeout: int | None = typer.Option(None, "--timeout", help="Per-task timeout seconds"),
    temperature: float | None = typer.Option(None, "--temperature", help="Temperature (0–2)"),
    reasoning_effort: str | None = typer.Option(
        None, "--reasoning-effort", help="Codex reasoning: low | medium | high | ultra"
    ),
    key_env: list[str] | None = typer.Option(None, "--key-env", help=_KEY_ENV_HELP),
) -> None:
    """Run pack-local evals/cases.yaml. Exit 0 if green, 1 if red, 2 if no key."""
    _run_gate(
        target=pack,
        skill=None,
        harness=harness,
        sandbox=sandbox,
        expect_fail=expect_fail,
        summary=summary,
        json_out=json_out,
        model=model,
        timeout=timeout,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
        key_env=key_env,
    )


@app.command("run")
def run_suite(
    suite: Path = typer.Argument(..., help="Skill pack directory or eval suite YAML"),
    skill: Path | None = typer.Option(None, "--skill", help="Override the skill folder"),
    harness: str = typer.Option("auto", "--harness", help=_HARNESS_HELP),
    sandbox: str = typer.Option("local", "--sandbox", help=_SANDBOX_HELP),
    expect_fail: bool = typer.Option(
        False,
        "--expect-fail",
        help="Exit 0 only if the suite is red (sabotaged / intentional-fail)",
    ),
    summary: str = typer.Option("cli", "--summary", help="cli | github | json"),
    json_out: bool = typer.Option(False, "--json", help="Machine JSON (not the primary UX)"),
    model: str | None = typer.Option(None, "--model", help="Requested model id"),
    timeout: int | None = typer.Option(None, "--timeout", help="Per-task timeout seconds"),
    temperature: float | None = typer.Option(None, "--temperature", help="Temperature (0–2)"),
    reasoning_effort: str | None = typer.Option(
        None, "--reasoning-effort", help="Codex reasoning: low | medium | high | ultra"
    ),
    key_env: list[str] | None = typer.Option(None, "--key-env", help=_KEY_ENV_HELP),
) -> None:
    """Run an eval pack or suite YAML. Prefer `skillgate check` for CI."""
    notice = "Prefer `skillgate check` for CI."
    if json_out or summary == "json":
        sys.stderr.write(notice + "\n")
    else:
        console.print(notice)
    _run_gate(
        target=suite,
        skill=skill,
        harness=harness,
        sandbox=sandbox,
        expect_fail=expect_fail,
        summary=summary,
        json_out=json_out,
        model=model,
        timeout=timeout,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
        key_env=key_env,
    )


@app.command()
def deploy(
    pack: Path = typer.Argument(..., help="Gated skill pack to copy"),
    target: str | None = typer.Option(None, "--target", help="cursor | claude | codex (comma ok)"),
    targets: str | None = typer.Option(
        None, "--targets", help="Same as --target; one name or a comma list"
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Install even if the latest check did not pass. Does not skip a skill that has never been checked.",
    ),
) -> None:
    """Copy a skill pack into a local agent skills directory.

    Refuses unless this pack already has a passing check. Does not run check.
    Copies skill files only (not evals/). --force only overrides a red latest check.
    """
    from skillgate_ai.deploy import get_adapter

    root = _boot()
    path = resolve_user_path(pack, root)
    selected = _parse_targets(target, targets, default="cursor")
    try:
        adapters = [get_adapter(name) for name in selected]
        loaded = ingest_skill(path)
        for adapter in adapters:
            result = adapter.install(skill=loaded, source=path, force=force)
            console.print(result["message"])
    except SkillGateError as exc:
        console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None


@app.command()
def sync(
    repo: str = typer.Option(..., "--repo", help="Git repo URL with skills/ inside"),
    target: str | None = typer.Option(None, "--target", help="Same as --targets"),
    targets: str | None = typer.Option(
        None, "--targets", help="Comma-separated targets (default cursor,codex,claude)"
    ),
    interval: int = typer.Option(0, "--interval", help="Seconds between syncs (0 = once)"),
    install_launchd: bool = typer.Option(
        False, "--install-launchd", help="Install a macOS LaunchAgent for sync"
    ),
) -> None:
    """Pull a skills repo and copy its skills into local agent dirs."""
    from skillgate_ai.sync import install_launchd_plist, run_sync_loop, sync_once

    selected = _parse_targets(target, targets, default="cursor,codex,claude")
    try:
        if install_launchd:
            path = install_launchd_plist(
                repo_url=repo, targets=selected, interval=interval
            )
            console.print(f"Installed sync LaunchAgent at {path}")
            raise typer.Exit(0)
        if interval and interval > 0:
            run_sync_loop(repo, targets=selected, interval=interval)
        else:
            result = sync_once(repo, targets=selected)
            for name in result.get("skipped") or []:
                console.print(f"skipped {name}: latest check did not pass")
            for name in result.get("synced") or []:
                console.print(f"synced  {name}")
            for target_key, summary in result["targets"].items():
                console.print(
                    f"{target_key}  installed={summary['installed']} "
                    f"removed={summary['removed']} → {summary['target_root']}"
                )
    except SkillGateError as exc:
        console.print(exc.render())
        raise typer.Exit(exc.exit_code) from exc


@app.command()
def connect(
    url: str = typer.Option(..., "--url", help="Hosted Skill Gate URL"),
    code: str = typer.Option(..., "--code", help="One-time pairing code"),
    name: str | None = typer.Option(None, "--name", help="Nickname for this Mac"),
) -> None:
    """Pair this Mac with a hosted Skill Gate (stores a token at 0600)."""
    from skillgate_ai.helper import connect as connect_helper

    try:
        config = connect_helper(url, code, name)
    except SkillGateError as exc:
        console.print(exc.render())
        raise typer.Exit(exc.exit_code) from exc
    console.print(f"Connected {config['name']} ({config['device_id']}).")
    console.print("Run `skillgate helper` to receive deploy jobs.")


@app.command()
def helper(
    once: bool = typer.Option(False, "--once", help="Poll once and exit"),
    install_launchd: bool = typer.Option(
        False, "--install-launchd", help="Install a macOS LaunchAgent for the helper"
    ),
) -> None:
    """Poll a hosted Skill Gate for deploy jobs and install skills (outbound only)."""
    from skillgate_ai.helper import (
        install_launchd_plist,
        load_helper_config,
        run_helper,
    )

    try:
        if install_launchd:
            path = install_launchd_plist()
            console.print(f"Installed helper LaunchAgent at {path}")
            raise typer.Exit(0)
        config = load_helper_config()
        if config is None:
            raise SkillGateError(
                "Not connected. Run `skillgate connect --url <hosted> --code <code>` first."
            )
        run_helper(config, once=once)
    except SkillGateError as exc:
        console.print(exc.render())
        raise typer.Exit(exc.exit_code) from exc


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


keys_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Set keys in this project. Never reads OPENAI_API_KEY from the shell unless --key-env.",
)
app.add_typer(keys_app, name="keys")


@keys_app.command("set")
def keys_set(
    name: str = typer.Argument(..., help="CURSOR_API_KEY | CODEX_API_KEY | OPENAI_API_KEY | …"),
    value: str | None = typer.Argument(
        None,
        help="The secret. Omit to paste hidden (TTY) or read stdin.",
    ),
) -> None:
    """Write a key into `.skillgate/keys` (mode 0600)."""
    from skillgate_ai.keys import set_vault_key

    root = _boot()
    secret = value
    if secret is None:
        secret = (_read_omitted_key() or "").strip()
    if not secret:
        console.print("Pass a key value, or paste it when prompted.")
        raise typer.Exit(2)
    try:
        set_vault_key(root, name, secret)
    except SkillGateError as exc:
        console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    console.print(f"Saved {name} in Settings (`.skillgate/keys`).")


@keys_app.command("clear")
def keys_clear(
    name: str = typer.Argument(..., help="Key name to remove"),
) -> None:
    """Remove a key from `.skillgate/keys`."""
    from skillgate_ai.keys import clear_vault_key

    root = _boot()
    try:
        clear_vault_key(root, name)
    except SkillGateError as exc:
        console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    console.print(f"Cleared {name}.")


@keys_app.command("list")
def keys_list() -> None:
    """Show which keys are set. Never prints values."""
    from skillgate_ai.keys import key_presence

    root = _boot()
    presence = key_presence(root)
    found = False
    for name, meta in presence.items():
        if not meta["set"]:
            continue
        found = True
        source = "Settings" if meta["from_vault"] else "SKILLGATE_* / --key-env"
        console.print(f"{name}  ({source})")
    if not found:
        console.print("No keys set. Use `skillgate keys set` or Settings in `skillgate ui`.")


@app.command("init")
def init_cmd(
    dest: Path | None = typer.Argument(None, help="Workspace folder (default: current directory)"),
) -> None:
    """Create a Skill Gate workspace (`skills/` and ignore `.skillgate/`)."""
    from skillgate_ai.workspace import init_workspace

    root = (dest or Path.cwd()).expanduser().resolve()
    try:
        init_workspace(root)
    except SkillGateError as exc:
        console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    console.print(f"Workspace ready at {root}")


@app.command("new")
def new_cmd(
    name: str = typer.Argument(..., help="Skill folder name (lowercase, hyphens)"),
) -> None:
    """Create `skills/NAME` with SKILL.md and starter checks (same as the UI)."""
    from skillgate_ai.workspace import new_skill

    root = _boot()
    try:
        dest = new_skill(root, name)
    except SkillGateError as exc:
        console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    console.print(f"Created {dest}")


@app.command("example")
def example_cmd(
    name: str = typer.Argument(..., help="pdf | pdf-sabotaged"),
    dest: Path | None = typer.Option(None, "--dest", help="Folder to write (default: ./NAME)"),
) -> None:
    """Copy a packaged example skill into this folder."""
    from skillgate_ai.examples import copy_example

    target = (dest or Path.cwd() / name).expanduser().resolve()
    try:
        written = copy_example(name, target)
    except SkillGateError as exc:
        console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    console.print(f"Wrote {written}")


@app.command("ui")
def ui_cmd(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address (default loopback)"),
    port: int = typer.Option(8765, "--port", help="Port (default 8765)"),
    root: Path | None = typer.Option(None, "--root", help="Workspace root for browse/create"),
    pack: Path | None = typer.Option(None, "--pack", help="Open this pack instead of the picker"),
    open_browser: bool = typer.Option(False, "--open", help="Open the loopback URL in a browser"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open a browser"),
) -> None:
    """Local React UI. No account. Run needs a key in Settings."""
    from skillgate_ai.server import serve_ui

    if port < 1 or port > 65535:
        console.print("Port must be between 1 and 65535.")
        raise typer.Exit(2)
    workspace = (root or project_root()).expanduser().resolve()
    load_env(workspace)
    should_open = open_browser and not no_browser
    if host not in {"127.0.0.1", "localhost", "::1"}:
        console.print(
            "Warning: binding off loopback. This is still a local process with no auth — "
            "not the hosted Skill Gate app."
        )
    try:
        serve_ui(
            root=workspace,
            host=host,
            port=port,
            pack=pack,
            open_browser=should_open,
        )
    except SkillGateError as exc:
        console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    except OSError as exc:
        console.print(f"Could not bind {host}:{port}: {exc}")
        raise typer.Exit(1) from exc


if __name__ == "__main__":
    app()
