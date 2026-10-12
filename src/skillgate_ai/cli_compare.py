"""CLI commands for compare runs (models + versions)."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import typer

from skillgate_ai.paths import project_root


def register_compare_commands(app: typer.Typer, *, key_env_help: str) -> None:
    from skillgate_ai.cli import _bind_key_env, _boot, _emit_json, _resolve_pack_arg, console

    _KEY_ENV_HELP = key_env_help

    compare_app = typer.Typer(
        add_completion=False,
        no_args_is_help=True,
        help="Side-by-side compare on one Dataset (models or versions).",
    )
    app.add_typer(compare_app, name="compare")

    @compare_app.command("models")
    def compare_models_cmd(
        pack: Path = typer.Argument(..., help="Skill pack directory"),
        arm: list[str] = typer.Option([], "--arm", help="Label:harness[:model] (repeatable)"),
        arm_file: list[Path] = typer.Option([], "--arm-file", help="JSON arm config (repeatable)"),
        max_spend_usd: float = typer.Option(5.0, "--max-spend-usd", help="Stop before next arm"),
        cases: str | None = typer.Option(None, "--cases", help="Comma-separated case ids"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Print plan only"),
        json_out: bool = typer.Option(False, "--json", help="Machine JSON (scrubbed)"),
        key_env: list[str] | None = typer.Option(None, "--key-env", help=_KEY_ENV_HELP),
    ) -> None:
        """Run the same Dataset on multiple harness setups."""
        from skillgate_ai.compare import (
            CompareError,
            arm_id_for_index,
            parse_arm_file,
            parse_arm_spec,
            run_models_compare,
            scrub_compare_payload,
            scrub_customer_compare_payload,
            validate_compare_plan,
        )
        from skillgate_ai.compare_format import format_compare_cli

        _bind_key_env(key_env)
        path = _resolve_pack_arg(pack)
        specs = []
        idx = 0
        try:
            for raw in arm:
                specs.append(parse_arm_spec(raw, arm_id=arm_id_for_index(idx), index=idx))
                idx += 1
            for file_path in arm_file:
                specs.append(parse_arm_file(file_path, arm_id=arm_id_for_index(idx), index=idx))
                idx += 1
        except CompareError as exc:
            console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        if len(specs) < 2 and not dry_run:
            console.print("Add at least two --arm or --arm-file values.")
            raise typer.Exit(2)
        case_ids = [part.strip() for part in (cases or "").split(",") if part.strip()] or None
        try:
            validate_compare_plan(specs, max_spend_usd=max_spend_usd)
        except CompareError as exc:
            console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        compare_id = uuid.uuid4().hex[:12]
        if not dry_run:
            line = f"Compare {compare_id} started.\n"
            if json_out:
                sys.stderr.write(line)
            else:
                console.print(line.rstrip())
        try:
            result = run_models_compare(
                path,
                arms=specs,
                root=project_root(),
                max_spend_usd=max_spend_usd,
                case_ids=case_ids,
                dry_run=dry_run,
                compare_id=compare_id,
            )
        except CompareError as exc:
            console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        payload = scrub_compare_payload(result.payload)
        if json_out:
            _emit_json(scrub_customer_compare_payload(result.payload))
        else:
            console.print(format_compare_cli(payload))
        raise typer.Exit(result.exit_code)

    @compare_app.command("versions")
    def compare_versions_cmd(
        pack: Path = typer.Argument(..., help="Skill pack directory"),
        run: list[str] = typer.Option([], "--run", help="History run id (repeat twice)"),
        git_ref: list[str] = typer.Option([], "--git", help="Git ref (repeat twice)"),
        rerun: bool = typer.Option(False, "--rerun", help="Re-run both arms using stored configs"),
        json_out: bool = typer.Option(False, "--json", help="Machine JSON (scrubbed)"),
        key_env: list[str] | None = typer.Option(None, "--key-env", help=_KEY_ENV_HELP),
    ) -> None:
        """Compare two skill versions on the same Dataset."""
        from skillgate_ai.compare import (
            CompareError,
            run_versions_compare,
            scrub_compare_payload,
            scrub_customer_compare_payload,
        )
        from skillgate_ai.compare_format import format_compare_cli

        _bind_key_env(key_env)
        path = _resolve_pack_arg(pack)
        versions_ready = len(run) >= 2 or len(git_ref) >= 2
        compare_id = uuid.uuid4().hex[:12]
        if versions_ready:
            line = f"Compare {compare_id} started.\n"
            if json_out:
                sys.stderr.write(line)
            else:
                console.print(line.rstrip())
        try:
            result = run_versions_compare(
                path,
                run_ids=run if run else None,
                git_refs=git_ref if git_ref else None,
                root=project_root(),
                rerun=rerun,
                compare_id=compare_id,
            )
        except CompareError as exc:
            console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        payload = scrub_compare_payload(result.payload)
        if json_out:
            _emit_json(scrub_customer_compare_payload(result.payload))
        else:
            console.print(format_compare_cli(payload))
        raise typer.Exit(result.exit_code)

    @compare_app.command("show")
    def compare_show_cmd(
        compare_id: str = typer.Argument(..., help="Compare id"),
        pack: Path | None = typer.Option(None, "--skill", help="Skill pack (optional)"),
        json_out: bool = typer.Option(False, "--json", help="Machine JSON (scrubbed)"),
    ) -> None:
        """Show a compare job."""
        from skillgate_ai.compare import (
            find_compare,
            find_compare_anywhere,
            scrub_compare_payload,
            scrub_customer_compare_payload,
        )
        from skillgate_ai.compare_format import format_compare_cli

        root = _boot()
        path = _resolve_pack_arg(pack) if pack else None
        row = find_compare(path, compare_id) if path else None
        if row is None and path is None:
            found = find_compare_anywhere(root, compare_id)
            if found:
                _, row = found
        if row is None:
            console.print(f"Unknown compare {compare_id}")
            raise typer.Exit(1)
        payload = scrub_compare_payload(row)
        if json_out:
            _emit_json(scrub_customer_compare_payload(row))
        else:
            console.print(format_compare_cli(payload))

    @compare_app.command("cancel")
    def compare_cancel_cmd(
        compare_id: str = typer.Argument(..., help="Compare id to stop"),
    ) -> None:
        """Cancel an in-flight compare (same as the Compare tab Cancel button)."""
        from skillgate_ai.compare_control import request_cancel_compare

        root = _boot()
        if not request_cancel_compare(root, compare_id):
            console.print(f"Unknown compare {compare_id}")
            raise typer.Exit(1)
        console.print(f"Cancel requested for compare {compare_id}.")
        raise typer.Exit(0)

    @compare_app.command("list")
    def compare_list_cmd(
        pack: Path | None = typer.Argument(None, help="Skill pack directory"),
        skill: Path | None = typer.Option(None, "--skill", help="Skill pack (same as positional)"),
        json_out: bool = typer.Option(False, "--json", help="Machine JSON (scrubbed)"),
    ) -> None:
        """List recent compare jobs for a pack."""
        from skillgate_ai.compare import (
            list_compares_merged,
            scrub_compare_payload,
            scrub_customer_compare_payload,
            strip_compare_list_meta,
        )

        target = skill or pack
        if target is None:
            console.print("Pass a skill pack path or --skill.")
            raise typer.Exit(2)
        path = _resolve_pack_arg(target)
        root = project_root()
        raw_rows = list_compares_merged(root, path)
        if not raw_rows:
            if json_out:
                _emit_json({"compares": []})
            else:
                console.print("No compares yet.")
            raise typer.Exit(0)
        if json_out:
            _emit_json(
                {
                    "compares": [
                        scrub_customer_compare_payload(strip_compare_list_meta(row))
                        for row in raw_rows
                    ]
                }
            )
        else:
            for row in raw_rows:
                base = strip_compare_list_meta(row)
                payload = (
                    scrub_compare_payload(base) if row.get("list_source") == "disk" else base
                )
                console.print(
                    f"{payload.get('compare_id')}  {payload.get('mode')}  "
                    f"{payload.get('status')}  {payload.get('skill')}"
                )
