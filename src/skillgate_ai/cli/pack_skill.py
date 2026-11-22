"""Pack CLI: skill import/write/paste."""

from __future__ import annotations

from pathlib import Path

import typer

from skillgate_ai.errors import SkillGateError


def register_skill_app(app: typer.Typer) -> typer.Typer:
    skill_app = typer.Typer(
        add_completion=False,
        no_args_is_help=True,
        help="Edit files in a skill pack (SKILL.md, fixtures, cases.yaml).",
    )
    app.add_typer(skill_app, name="skill")
    return skill_app


def register_import_command(app: typer.Typer) -> None:
    from skillgate_ai import cli as _cli

    def import_cmd(
        target: str | None = typer.Argument(
            None, help="Local skill folder or git URL (https://… or git@…)"
        ),
        source: list[str] | None = typer.Option(
            None, "--source", help="cursor | claude | codex (repeatable)"
        ),
        zip_path: Path | None = typer.Option(None, "--zip", help="Zip of a skill folder"),
        markdown: Path | None = typer.Option(None, "--md", help="A SKILL.md file"),
        only: list[str] | None = typer.Option(
            None, "--only", help="Import only these skill slugs (repeatable)"
        ),
    ) -> None:
        """Copy skills from a folder, git URL, agent folder, zip, or SKILL.md."""
        from pathlib import Path as _Path

        from skillgate_ai.paths import config_root_for

        root = config_root_for(_Path.cwd())
        try:
            if target is not None:
                from skillgate_ai.api_intake import import_path_or_git_result

                result = import_path_or_git_result(root, target)
                for row in result.get("imported") or []:
                    _cli.console.print(f"imported  {row.get('slug') or row.get('name')}")
                return
            if zip_path is not None or markdown is not None:
                from typing import cast

                from skillgate_ai.api_intake import extract_uploaded_skill

                path = cast(Path, zip_path or markdown)  # guarded: one of --zip/--md is set
                data = path.expanduser().read_bytes()
                dest = extract_uploaded_skill(root, data, filename=path.name)
                _cli.console.print(f"Imported {dest}")
                return
            from skillgate_ai.catalog import import_from_agent_folders

            result = import_from_agent_folders(root, sources=source, only=only)
        except (SkillGateError, OSError) as exc:
            message = str(exc) if not isinstance(exc, SkillGateError) else exc.render()
            _cli.console.print(message)
            raise typer.Exit(getattr(exc, "exit_code", 1) or 1) from None
        imported = result.get("imported") or []
        skipped = result.get("skipped") or []
        if not imported and not skipped:
            _cli.console.print("No skills found to import.")
            raise typer.Exit(1)
        for row in imported:
            _cli.console.print(f"imported  {row.get('slug') or row.get('name')}")
        for row in skipped:
            _cli.console.print(f"skipped   {row.get('name')}: {row.get('reason')}")

    app.command("import")(import_cmd)


def register_skill_write(skill_app: typer.Typer) -> None:
    from skillgate_ai import cli as _cli

    def skill_write(
        pack: Path | None = typer.Argument(None, help="Skill pack"),
        rel: str = typer.Option(..., "--path", help="Path inside the skill folder"),
        content: str | None = typer.Option(None, "--content", help="File text"),
        src: Path | None = typer.Option(None, "--file", help="Copy this file in"),
        generate: bool = typer.Option(False, "--generate", help="Write a sample fixture"),
    ) -> None:
        """Write a file in this skill (SKILL.md, fixtures, evals/cases.yaml)."""
        from skillgate_ai.ingest import ingest_skill
        from skillgate_ai.pack import CannotSynthesizeFixture, write_pack_file, write_sample_fixture

        try:
            dest = _cli._resolve_pack_arg(pack)
            if generate:
                written = write_sample_fixture(
                    dest,
                    dest=rel,
                    prompt="",
                    description=ingest_skill(dest, strict=False).description,
                )
                _cli.console.print(written.get("path") or rel)
                return
            data: str | bytes
            if src is not None:
                data = src.expanduser().read_bytes()
            elif content is not None:
                data = content
            else:
                raise SkillGateError("Pass --content, --file, or --generate.")
            written = write_pack_file(dest, rel=rel, content=data)
        except (SkillGateError, CannotSynthesizeFixture, OSError) as exc:
            message = str(exc) if not isinstance(exc, SkillGateError) else exc.render()
            _cli.console.print(message, markup=False)
            raise typer.Exit(getattr(exc, "exit_code", 1) or 1) from None
        _cli.console.print(written.get("path") or rel)

    skill_app.command("write")(skill_write)


def register_skill_paste(skill_app: typer.Typer) -> None:
    from skillgate_ai import cli as _cli

    def skill_paste(
        markdown_file: Path | None = typer.Option(None, "--file", help="SKILL.md to paste"),
    ) -> None:
        """Create a skill from a pasted SKILL.md (same as the UI paste)."""
        from skillgate_ai.api_intake import write_pasted_skill

        root = _cli._boot()
        try:
            if markdown_file is not None:
                text = markdown_file.expanduser().read_text(encoding="utf-8")
            else:
                import sys

                text = sys.stdin.read()
            dest = write_pasted_skill(root, text)
        except SkillGateError as exc:
            _cli.console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        except OSError as exc:
            _cli.console.print("Couldn't read that file.")
            if markdown_file is not None:
                _cli.console.print(str(markdown_file))
            if exc.strerror:
                _cli.console.print(exc.strerror)
            raise typer.Exit(1) from None
        _cli.console.print(f"Created {dest}")

    skill_app.command("paste")(skill_paste)
