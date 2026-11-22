"""CLI compare: show, cancel, list commands."""

from __future__ import annotations

from pathlib import Path

import typer

from skillgate_ai.paths import project_root


def register_compare_show(compare_app: typer.Typer) -> None:
    from skillgate_ai.cli import _boot, _emit_json, _resolve_pack_arg, console

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


def register_compare_cancel(compare_app: typer.Typer) -> None:
    from skillgate_ai.cli import _boot, console

    @compare_app.command("cancel")
    def compare_cancel_cmd(
        compare_id: str = typer.Argument(..., help="Compare id to stop"),
    ) -> None:
        """Cancel an in-flight compare (same as the Compare tab Cancel button)."""
        from skillgate_ai.compare_control import request_cancel_compare

        root = _boot()
        outcome = request_cancel_compare(root, compare_id)
        if outcome == "unknown":
            console.print(f"Unknown compare {compare_id}")
            raise typer.Exit(1)
        if outcome == "already_done":
            console.print(f"Compare {compare_id} is already done.")
            raise typer.Exit(0)
        console.print(f"Cancel requested for compare {compare_id}.")
        raise typer.Exit(0)


def register_compare_list(compare_app: typer.Typer) -> None:
    from skillgate_ai.cli import _emit_json, _resolve_pack_arg, console

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
                payload = scrub_compare_payload(base) if row.get("list_source") == "disk" else base
                console.print(
                    f"{payload.get('compare_id')}  {payload.get('mode')}  "
                    f"{payload.get('status')}  {payload.get('skill')}"
                )
