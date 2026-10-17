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
from skillgate_ai.api_payloads import scrub_browser_payload
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


def _version_callback(value: bool) -> None:
    if value:
        console.print(__version__)
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print the CLI version.",
    ),
) -> None:
    """Skill Gate."""
    del version


@app.command()
def version() -> None:
    """Print the CLI version."""
    console.print(__version__)


def _print_agent_status(*, json_out: bool) -> None:
    from skillgate_ai.config import get_llm_config
    from skillgate_ai.harness import format_harness_status, harness_auth_status

    rows = harness_auth_status(get_llm_config(_boot()))
    if json_out:
        _emit_json({"harnesses": rows})
        return
    console.print(format_harness_status(rows))


def _login_targets(agent: str | None) -> list[str]:
    from skillgate_ai.config import get_llm_config
    from skillgate_ai.harness import harness_auth_status, normalize_login_agent

    if agent:
        kind = normalize_login_agent(agent)
        if kind is None:
            raise typer.BadParameter("Use cursor, claude, or codex.")
        return [kind]
    rows = harness_auth_status(get_llm_config(_boot()))
    missing = [
        str(row["agent"])
        for row in rows
        if row["installed"] and row["auth"] == "none"
    ]
    if missing:
        if _stdin_is_tty() and len(missing) > 1:
            names = ", ".join(missing)
            picked = typer.prompt(
                f"Sign in ({names}, or all)",
                default="all",
            ).strip().lower()
            if picked in {"all", "*", "missing"}:
                return missing
            kind = normalize_login_agent(picked)
            if kind is None:
                raise typer.BadParameter("Use cursor, claude, codex, or all.")
            return [kind]
        return missing
    return []


@app.command()
def login(
    agent: str | None = typer.Argument(
        None, help="cursor | claude | codex. Omit to sign in missing agents."
    ),
    status: bool = typer.Option(
        False, "--status", help="Show installed / logged in / API key / none."
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine JSON"),
    force: bool = typer.Option(
        False, "--force", help="Run the official login even if already signed in."
    ),
) -> None:
    """Sign in with Cursor, Codex, or Claude Code using that agent's official login."""
    from skillgate_ai.config import get_llm_config
    from skillgate_ai.harness import (
        AUTH_CLI_LOGIN,
        claude_auth_kind,
        cursor_auth_kind,
        format_harness_status,
        harness_auth_status,
        normalize_login_agent,
        run_official_login,
    )

    root = _boot()
    if status:
        _print_agent_status(json_out=json_out)
        raise typer.Exit()
    try:
        targets = _login_targets(agent)
    except typer.BadParameter as exc:
        console.print(str(exc))
        raise typer.Exit(2) from None
    if not targets:
        rows = harness_auth_status(get_llm_config(root))
        installed = [row for row in rows if row["installed"]]
        if json_out:
            _emit_json({"harnesses": rows, "signed_in": []})
        elif not installed:
            console.print(format_harness_status(rows))
        else:
            console.print("All installed agents already have a key or CLI login.")
            console.print(format_harness_status(rows))
        raise typer.Exit(0 if installed else 2)
    cfg = get_llm_config(root)
    signed_in_kind = normalize_login_agent(agent) if agent else None
    already_signed_in = {
        "claude": ("claude", claude_auth_kind, "Claude Code is already signed in"),
        "cursor": ("cursor", cursor_auth_kind, "Cursor is already signed in"),
    }
    if signed_in_kind in already_signed_in and not force:
        name, auth_kind, message = already_signed_in[signed_in_kind]
        if auth_kind(cfg) == AUTH_CLI_LOGIN:
            if json_out:
                _emit_json(
                    {
                        "results": [
                            {
                                "agent": name,
                                "ok": True,
                                "installed": True,
                                "status": "logged in",
                                "message": message,
                            }
                        ],
                        "harnesses": harness_auth_status(cfg),
                    }
                )
            else:
                console.print(message)
            raise typer.Exit(0)
    results = [run_official_login(name, cfg) for name in targets]
    if json_out:
        _emit_json({"results": results, "harnesses": harness_auth_status(cfg)})
        if any(not item.get("installed") for item in results):
            raise typer.Exit(2)
        raise typer.Exit(0 if all(item.get("ok") for item in results) else 1)
    code = 0
    for item in results:
        if not item.get("installed"):
            console.print(f"{item.get('agent')}: not installed.")
            console.print(str(item.get("install") or ""))
            code = max(code, 2)
            continue
        console.print(str(item.get("message") or ""))
        if not item.get("ok"):
            code = max(code, 1)
    console.print(format_harness_status(harness_auth_status(cfg)))
    raise typer.Exit(code)


@app.command()
def doctor(
    json_out: bool = typer.Option(False, "--json", help="Machine JSON"),
) -> None:
    """Show whether Cursor, Codex, and Claude Code are installed and signed in."""
    _print_agent_status(json_out=json_out)


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
    if loaded.warning:
        console.print(f"Warning: {loaded.warning}")


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
    harness: str | None,
    sandbox: str,
    expect_fail: bool,
    summary: str,
    json_out: bool,
    model: str | None,
    timeout: int | None,
    temperature: float | None,
    reasoning_effort: str | None,
    key_env: list[str] | None = None,
    case_id: str | None = None,
    no_judge: bool = False,
) -> None:
    _bind_key_env(key_env)
    checks = None
    tryout = False
    if case_id:
        from skillgate_ai.pack_edit import tryout_checks
        from skillgate_ai.paths import is_skill_pack

        dest = resolve_user_path(target, project_root())
        if not is_skill_pack(dest):
            exc = SkillGateError(
                f"Not a skill pack: {dest}",
                hint="Pass a skill folder with SKILL.md and evals/.",
                exit_code=2,
            )
            if json_out or summary == "json":
                _emit_json(
                    {
                        "error": exc.message,
                        "hint": exc.hint,
                        "exit_code": exc.exit_code,
                    }
                )
            else:
                console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        try:
            checks = tryout_checks(dest, case_id)
            tryout = True
        except SkillGateError as exc:
            if json_out or summary == "json":
                _emit_json(
                    {
                        "error": exc.message,
                        "hint": exc.hint,
                        "exit_code": exc.exit_code,
                    }
                )
            else:
                console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
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
        checks=checks,
        tryout=tryout,
        no_judge=no_judge,
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
        _emit_json(scrub_browser_payload(report_to_dict(report)))
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


_HARNESS_HELP = "auto | cursor | cursor-agent | codex | claude"
_SANDBOX_HELP = "local (default)"
_KEY_ENV_HELP = (
    "Use this process env name as a Skill Gate key (repeatable). "
    "CI: set SKILLGATE_OPENAI_API_KEY, or pass --key-env OPENAI_API_KEY."
)


@app.command("check")
def check_pack(
    pack: Path = typer.Argument(..., help="Skill pack directory (SKILL.md + evals/)"),
    harness: str | None = typer.Option(None, "--harness", help=_HARNESS_HELP),
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
    case_id: str | None = typer.Option(None, "--case", help="Run this check only (try-out)"),
    no_judge: bool = typer.Option(
        False,
        "--no-judge",
        help="Allow a run without a scoring key (exit 0 even when quality is not scored).",
    ),
) -> None:
    """Run pack-local evals/cases.yaml. Exit 0 if green, 1 if red, 2 if no agent."""
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
        case_id=case_id,
        no_judge=no_judge,
    )


@app.command("run")
def run_suite(
    suite: Path = typer.Argument(..., help="Skill pack directory or eval suite YAML"),
    skill: Path | None = typer.Option(None, "--skill", help="Override the skill folder"),
    harness: str | None = typer.Option(None, "--harness", help=_HARNESS_HELP),
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

    Refuses unless this pack already has a passing check and an agent is
    available (API key or `skillgate login`). Does not run check. Copies skill
    files only (not evals/). --force only overrides a red latest check; it does
    not skip a missing agent.
    """
    from skillgate_ai.config import get_llm_config, missing_key_error
    from skillgate_ai.deploy import get_adapter, require_passing_check
    from skillgate_ai.history import append_deploy

    root = _boot()
    path = resolve_user_path(pack, root)
    selected = _parse_targets(target, targets, default="cursor")
    try:
        adapters = [get_adapter(name) for name in selected]
        loaded = ingest_skill(path)
        require_passing_check(path, name=loaded.name, force=force)
        if not get_llm_config(root).has_any_key:
            raise missing_key_error()
        for adapter in adapters:
            result = adapter.install(skill=loaded, source=path, force=force)
            console.print(result["message"])
            append_deploy(
                path,
                target=adapter.id,
                status=result.get("status") or "installed",
                file_count=result.get("file_count"),
                mode="local",
            )
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
    name: str = typer.Argument(
        ..., help="CURSOR_API_KEY | CODEX_API_KEY | OPENAI_API_KEY | AI Gateway key | …"
    ),
    value: str | None = typer.Argument(
        None,
        help="The secret. Omit to paste hidden (TTY) or read stdin.",
    ),
) -> None:
    """Write a key into `.skillgate/keys` (mode 0600).

    Names include CURSOR_API_KEY, CODEX_API_KEY, OPENAI_API_KEY, and AI Gateway key
    (AI_GATEWAY_API_KEY).
    """
    from skillgate_ai.keys import public_key_name, set_vault_key

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
    console.print(f"Saved {public_key_name(name)} in Settings (`.skillgate/keys`).")


@keys_app.command("clear")
def keys_clear(
    name: str = typer.Argument(..., help="Key name to remove"),
) -> None:
    """Remove a key from `.skillgate/keys`."""
    from skillgate_ai.keys import clear_vault_key, internal_key_name, public_key_name, read_vault

    root = _boot()
    try:
        key = internal_key_name(name)
        if key not in read_vault(root):
            console.print(f"No {public_key_name(name)} in Settings.")
            raise typer.Exit(1)
        clear_vault_key(root, name)
    except SkillGateError as exc:
        console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    console.print(f"Cleared {public_key_name(name)}.")


@keys_app.command("list")
def keys_list() -> None:
    """Show which keys are set. Never prints values."""
    from skillgate_ai.keys import key_presence

    root = _boot()
    presence = key_presence(root)
    found = False
    from skillgate_ai.keys import public_key_name

    for name, meta in presence.items():
        if not meta["set"]:
            continue
        found = True
        source = "Settings" if meta["from_vault"] else "SKILLGATE_* / --key-env"
        console.print(f"{public_key_name(name)}  ({source})")
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
    except OSError as exc:
        console.print("Couldn't create that folder.")
        if exc.strerror:
            console.print(exc.strerror)
        raise typer.Exit(1) from None
    console.print(f"Workspace ready at {root}")


@app.command("new")
def new_cmd(
    name: str = typer.Argument(..., help="Skill folder name (lowercase, hyphens)"),
) -> None:
    """Create `skills/NAME` with SKILL.md and starter checks (same as the UI)."""
    from skillgate_ai.workspace import new_skill

    from pathlib import Path as _Path

    from skillgate_ai.paths import config_root_for

    root = config_root_for(_Path.cwd())
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

    root = _boot()
    target = (dest or (root / "skills" / name)).expanduser().resolve()
    try:
        written = copy_example(name, target)
    except SkillGateError as exc:
        console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    console.print(f"Wrote {written}")


judge_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Show extra scoring questions and pick who scores live checks.",
)
judge_provider_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Who scores live checks (auto or a configured judge).",
)
app.add_typer(judge_app, name="judge")
judge_app.add_typer(judge_provider_app, name="provider")


def _resolve_pack_arg(pack: Path | None) -> Path:
    root = _boot()
    if pack is not None:
        dest = resolve_user_path(pack, root)
    elif is_skill_pack(root):
        dest = root
    else:
        pdf = root / "skills" / "pdf"
        if is_skill_pack(pdf):
            dest = pdf
        else:
            raise SkillGateError(
                "Pass a skill pack (folder with SKILL.md and evals/).",
                exit_code=2,
            )
    if not (dest / "SKILL.md").is_file():
        raise SkillGateError(
            f"Not a skill pack: {dest}",
            hint="Pass a skill folder with SKILL.md and evals/.",
            exit_code=2,
        )
    return dest


@judge_app.command("show")
def judge_show(
    pack: Path | None = typer.Argument(None, help="Skill pack (default: this folder or skills/pdf)"),
    case_id: str | None = typer.Option(None, "--case", help="Case id"),
    json_out: bool = typer.Option(False, "--json", help="Resolved spec JSON"),
) -> None:
    """Print built-in questions, then extras."""
    from skillgate_ai.case_pack import load_case_pack, pack_judge_dict
    from skillgate_ai.judge_spec import resolve_judge_spec
    from skillgate_ai.project_config import load_project_judge

    try:
        dest = _resolve_pack_arg(pack)
        loaded = load_case_pack(dest)
        case_block = None
        if case_id:
            from skillgate_ai.pack_schema import case_id_slug

            wanted = case_id_slug(case_id)
            found = False
            if loaded is not None:
                for case in loaded.cases:
                    if case.id == wanted:
                        found = True
                        if case.judge is not None:
                            case_block = case.judge.to_sparse_dict()
                        break
            if not found:
                raise SkillGateError(f"No check named {case_id}.")
        spec = resolve_judge_spec(
            project=load_project_judge(_boot()),
            pack=pack_judge_dict(loaded),
            case=case_block,
        )
    except SkillGateError as exc:
        console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    if json_out:
        _emit_json(
            {
                "questions": [
                    {
                        "id": q.id,
                        "type": q.type,
                        "ask": q.ask,
                        "on_fail": q.on_fail,
                        "builtin": q.builtin,
                    }
                    for q in spec.questions
                ]
            }
        )
        return
    console.print("Skill Gate questions (always asked)")
    for question in spec.builtins:
        severity = "Warn only" if question.on_fail == "warn" else "Fail the check"
        console.print(f"  {question.label}  {severity}")
    extras = spec.extras
    if extras:
        console.print("Your questions")
        for question in extras:
            kind = {"predicate": "Yes/No", "choice": "Pick one", "score": "Score"}[question.type]
            severity = "Warn only" if question.on_fail == "warn" else "Fail the check"
            console.print(f"  {question.label}  {kind}  {severity}")
    else:
        console.print("No extra questions.")


@judge_app.command("reset")
def judge_reset(
    pack: Path | None = typer.Argument(None, help="Skill pack"),
) -> None:
    """Drop extras and Fail vs warn overrides. Built-ins stay."""
    from skillgate_ai.case_pack import reset_pack_judge

    try:
        dest = _resolve_pack_arg(pack)
        reset_pack_judge(dest)
    except SkillGateError as exc:
        console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    console.print("Extra scoring questions removed. Skill Gate’s six stay.")


@judge_app.command("add-question")
def judge_add_question_cmd(
    pack: Path | None = typer.Argument(None, help="Skill pack"),
    ask: str = typer.Option(..., "--ask", help="Question text"),
    kind: str = typer.Option("Yes/No", "--type", help="Yes/No | pick one | score"),
    question_id: str | None = typer.Option(None, "--id", help="Optional question id"),
    warn_only: bool = typer.Option(False, "--warn-only", help="Warn instead of failing the check"),
    choices: list[str] | None = typer.Option(
        None, "--choices", help="Pick-one options (repeatable)"
    ),
) -> None:
    """Add an extra scoring question to this skill."""
    from skillgate_ai.pack_edit import add_judge_question

    try:
        dest = _resolve_pack_arg(pack)
        add_judge_question(
            dest,
            ask=ask,
            kind=kind,
            question_id=question_id,
            on_fail="warn" if warn_only else "block",
            choices=choices,
        )
    except SkillGateError as exc:
        console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    console.print(ask)


case_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Add checks to evals/cases.yaml.",
)
app.add_typer(case_app, name="case")


@case_app.command("add")
def case_add_cmd(
    pack: Path | None = typer.Argument(None, help="Skill pack"),
    prompt: str = typer.Option(..., "--prompt", help="What the agent should do"),
    case_id: str | None = typer.Option(None, "--id", help="Optional check id"),
    expected: str | None = typer.Option(None, "--expected", help="Expected text in the output"),
    output_path: str | None = typer.Option(None, "--output", help="Output file to compare"),
    inputs: list[Path] | None = typer.Option(
        None, "--input", "--fixture", help="Input/fixture file to copy into this skill"
    ),
    no_trigger: bool = typer.Option(False, "--no-trigger", help="This check should not run the skill"),
    force: bool = typer.Option(False, "--force", help="Replace a check that already uses this id"),
) -> None:
    """Add a check to this skill's Dataset."""
    from skillgate_ai.pack_edit import add_pack_case

    try:
        dest = _resolve_pack_arg(pack)
        pack_out, warning = add_pack_case(
            dest,
            prompt=prompt,
            case_id=case_id,
            expected=expected,
            output_path=output_path,
            should_trigger=not no_trigger,
            inputs=[str(path) for path in inputs] if inputs else None,
            force=force,
        )
    except SkillGateError as exc:
        console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    except ValueError as exc:
        console.print(str(exc))
        raise typer.Exit(1) from None
    from skillgate_ai.pack_schema import case_id_slug

    added = case_id_slug(case_id) if str(case_id or "").strip() else (
        pack_out.cases[-1].id if pack_out.cases else prompt
    )
    console.print(f"Added check {added}.")
    if warning:
        console.print(warning)


@judge_provider_app.command("show")
def judge_provider_show() -> None:
    """Who scores live checks."""
    from skillgate_ai.config import get_llm_config
    from skillgate_ai.judge_copy import DEFAULT_NAME

    root = _boot()
    cfg = get_llm_config(root)
    if cfg.judge_chosen or cfg.openai_api_key or cfg.gateway_api_key:
        console.print(f"Scoring with {DEFAULT_NAME}")
        return
    console.print("No scoring provider — file checks only.")


@judge_provider_app.command("set")
def judge_provider_set(
    provider: str = typer.Argument(..., help="auto, openai, jev, aws, or other"),
    base_url: str | None = typer.Option(None, "--base-url"),
    region: str | None = typer.Option(None, "--region"),
    model: str | None = typer.Option(None, "--model"),
    decisions_path: str | None = typer.Option(None, "--decisions-path", hidden=True),
    key_env: list[str] | None = typer.Option(None, "--key-env", help=_KEY_ENV_HELP),
) -> None:
    """Write `.skillgate/judge`. Stores env var names, never key values."""
    from skillgate_ai.judge_settings import save_judge_settings

    root = _boot()
    try:
        settings = save_judge_settings(
            root,
            provider=provider,
            region=region,
            model=model,
            base_url=base_url,
            decisions_path=decisions_path,
            key_env=key_env,
        )
    except SkillGateError as exc:
        console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    if settings.chosen:
        console.print("Scoring provider: the judge")
    else:
        console.print("Scoring provider: Auto")


@judge_provider_app.command("test")
def judge_provider_test(
    key_env: list[str] | None = typer.Option(None, "--key-env", help=_KEY_ENV_HELP),
) -> None:
    """Test the scoring connection. Never prints the key."""
    from skillgate_ai.config import get_llm_config
    from skillgate_ai.judge import ping_judge

    root = _boot()
    _bind_key_env(key_env)
    try:
        result = ping_judge(get_llm_config(root))
    except SkillGateError as exc:
        console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    console.print(str(result.get("message") or ""))
    raise typer.Exit(0 if result.get("ok") else 1)


@app.command("ui")
def ui_cmd(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address (default loopback)"),
    port: int = typer.Option(8765, "--port", help="Port (default 8765)"),
    root: Path | None = typer.Option(None, "--root", help="Workspace root for browse/create"),
    pack: Path | None = typer.Option(None, "--pack", help="Open this pack instead of the picker"),
    open_browser: bool = typer.Option(False, "--open", help="Open the loopback URL in a browser"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open a browser"),
) -> None:
    """Local React UI. No account. Run needs an agent (`skillgate login` or a key)."""
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
        console.print("Stop the other process, or pass --port with a free port.")
        raise typer.Exit(1) from exc


from skillgate_ai.cli_compare import register_compare_commands
from skillgate_ai.cli_pack import register_pack_commands

register_pack_commands(app, case_app, judge_app)
register_compare_commands(app, key_env_help=_KEY_ENV_HELP)


if __name__ == "__main__":
    app()
