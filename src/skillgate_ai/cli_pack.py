"""CLI commands that match OSS UI writes: import, skill files, cases, history."""

from __future__ import annotations

from pathlib import Path

import typer

from skillgate_ai.errors import SkillGateError


def register_pack_commands(app: typer.Typer, case_app: typer.Typer, judge_app: typer.Typer) -> None:
    from skillgate_ai.cli import _boot, _resolve_pack_arg, console

    skill_app = typer.Typer(
        add_completion=False,
        no_args_is_help=True,
        help="Edit files in a skill pack (SKILL.md, fixtures, cases.yaml).",
    )
    app.add_typer(skill_app, name="skill")

    @app.command("import")
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
                    console.print(f"imported  {row.get('slug') or row.get('name')}")
                return
            if zip_path is not None or markdown is not None:
                from skillgate_ai.api_intake import extract_uploaded_skill

                path = zip_path or markdown
                data = path.expanduser().read_bytes()
                dest = extract_uploaded_skill(root, data, filename=path.name)
                console.print(f"Imported {dest}")
                return
            from skillgate_ai.catalog import import_from_agent_folders

            result = import_from_agent_folders(root, sources=source, only=only)
        except (SkillGateError, OSError) as exc:
            message = str(exc) if not isinstance(exc, SkillGateError) else exc.render()
            console.print(message)
            raise typer.Exit(getattr(exc, "exit_code", 1) or 1) from None
        imported = result.get("imported") or []
        skipped = result.get("skipped") or []
        if not imported and not skipped:
            console.print("No skills found to import.")
            raise typer.Exit(1)
        for row in imported:
            console.print(f"imported  {row.get('slug') or row.get('name')}")
        for row in skipped:
            console.print(f"skipped   {row.get('name')}: {row.get('reason')}")

    @skill_app.command("write")
    def skill_write(
        pack: Path | None = typer.Argument(None, help="Skill pack"),
        rel: str = typer.Option(..., "--path", help="Path inside the skill folder"),
        content: str | None = typer.Option(None, "--content", help="File text"),
        src: Path | None = typer.Option(None, "--file", help="Copy this file in"),
        generate: bool = typer.Option(False, "--generate", help="Write a sample fixture"),
    ) -> None:
        """Write a file in this skill (SKILL.md, fixtures, evals/cases.yaml)."""
        from skillgate_ai.pack import CannotSynthesizeFixture, write_pack_file, write_sample_fixture
        from skillgate_ai.ingest import ingest_skill

        try:
            dest = _resolve_pack_arg(pack)
            if generate:
                written = write_sample_fixture(
                    dest,
                    dest=rel,
                    prompt="",
                    description=ingest_skill(dest, strict=False).description,
                )
                console.print(written.get("path") or rel)
                return
            if src is not None:
                data = src.expanduser().read_bytes()
            elif content is not None:
                data = content
            else:
                raise SkillGateError("Pass --content, --file, or --generate.")
            written = write_pack_file(dest, rel=rel, content=data)
        except (SkillGateError, CannotSynthesizeFixture, OSError) as exc:
            message = str(exc) if not isinstance(exc, SkillGateError) else exc.render()
            console.print(message)
            raise typer.Exit(getattr(exc, "exit_code", 1) or 1) from None
        console.print(written.get("path") or rel)

    @skill_app.command("paste")
    def skill_paste(
        markdown_file: Path | None = typer.Option(None, "--file", help="SKILL.md to paste"),
    ) -> None:
        """Create a skill from a pasted SKILL.md (same as the UI paste)."""
        from skillgate_ai.api_intake import write_pasted_skill

        root = _boot()
        try:
            if markdown_file is not None:
                text = markdown_file.expanduser().read_text(encoding="utf-8")
            else:
                import sys

                text = sys.stdin.read()
            dest = write_pasted_skill(root, text)
        except SkillGateError as exc:
            console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        except OSError as exc:
            console.print("Couldn't read that file.")
            if markdown_file is not None:
                console.print(str(markdown_file))
            if exc.strerror:
                console.print(exc.strerror)
            raise typer.Exit(1) from None
        console.print(f"Created {dest}")

    history_app = typer.Typer(
        add_completion=False,
        invoke_without_command=True,
        help="Show recent check runs for this skill.",
    )
    app.add_typer(history_app, name="history")

    def _print_history_rows(rows: list) -> None:
        from skillgate_ai.judge_copy import customer_scorer_name, scored_by_phrase

        if not rows:
            console.print("No runs yet.")
            return
        for row in reversed(rows):
            report = row.get("report") if isinstance(row.get("report"), dict) else {}
            who = report.get("scored_by") if isinstance(report.get("scored_by"), str) else ""
            if not who or "openai decisions" in who.lower() or "vercel ai gateway" in who.lower():
                stamp = None
                if isinstance(report.get("config"), dict):
                    stamp = report["config"].get("judge")
                who = scored_by_phrase(
                    customer_scorer_name(stamp if isinstance(stamp, dict) else None)
                )
            gate = ("pass" if row.get("passed") else "fail").ljust(4)
            passed = report.get("passed_count")
            total = report.get("task_count")
            if passed is not None and total is not None:
                counts = f" {passed}/{total}".rjust(6)
            elif row.get("error"):
                counts = "   —/—"
            else:
                counts = "      "
            ts = str(row.get("ts") or "")
            date = ts[:10] if ts else ""
            date_bit = f"  {date}" if date else ""
            console.print(f"{row.get('run_id')}  {gate}{counts}{date_bit}  {who}")

    @history_app.callback(invoke_without_command=True)
    def history_cmd(
        ctx: typer.Context,
        pack: Path | None = typer.Option(None, "--pack", help="Skill pack"),
        json_out: bool = typer.Option(False, "--json"),
    ) -> None:
        """Show recent check runs for this skill."""
        if ctx.invoked_subcommand:
            return
        from skillgate_ai.history import load_history

        try:
            dest = _resolve_pack_arg(pack)
            rows = load_history(dest, limit=20)
        except SkillGateError as exc:
            console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        if json_out:
            from skillgate_ai.cli import _emit_json

            _emit_json(rows)
            return
        _print_history_rows(rows)

    @history_app.command("show")
    def history_show(
        run_id: str = typer.Argument(..., help="Run id"),
        pack: Path | None = typer.Option(None, "--pack", help="Skill pack"),
        json_out: bool = typer.Option(False, "--json"),
    ) -> None:
        """Show one saved run."""
        from skillgate_ai.catalog import catalog_entries
        from skillgate_ai.history import load_history

        try:
            row = None
            skill_path = None
            if pack is not None:
                dest = _resolve_pack_arg(pack)
                skill_path = dest
                for item in load_history(dest, limit=0):
                    if str(item.get("run_id") or "") == run_id:
                        row = item
                        break
            else:
                for entry in catalog_entries(_boot()):
                    path = Path(entry["absolute"])
                    for item in load_history(path, limit=0):
                        if str(item.get("run_id") or "") == run_id:
                            row = item
                            skill_path = path
                            break
                    if row is not None:
                        break
                if row is None:
                    dest = _resolve_pack_arg(None)
                    skill_path = dest
                    for item in load_history(dest, limit=0):
                        if str(item.get("run_id") or "") == run_id:
                            row = item
                            break
            if row is None:
                raise SkillGateError(f"No run named {run_id}.")
        except SkillGateError as exc:
            console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        if json_out:
            from skillgate_ai.api_payloads import history_row_to_run
            from skillgate_ai.cli import _emit_json

            _emit_json(history_row_to_run(row, skill_path or Path(".")))
            return
        report = row.get("report") if isinstance(row.get("report"), dict) else {}
        gate = "pass" if row.get("passed") else "fail"
        passed = report.get("passed_count")
        total = report.get("task_count")
        counts = f"  {passed}/{total}" if passed is not None and total is not None else ""
        console.print(f"{row.get('run_id')}  {gate}{counts}")
        err = row.get("error")
        if isinstance(err, dict):
            message = str(err.get("message") or "").strip()
            hint = str(err.get("hint") or "").strip()
            if message:
                console.print(f"  {message}")
            if hint:
                console.print(f"  {hint}")
        tasks = report.get("tasks") if isinstance(report.get("tasks"), list) else []
        for task in tasks:
            if not isinstance(task, dict):
                continue
            tid = str(task.get("id") or task.get("task_id") or "")
            ok = task.get("passed")
            mark = "pass" if ok is True else "fail" if ok is False else "—"
            reason = ""
            if ok is False:
                failures = task.get("failures")
                if isinstance(failures, list) and failures:
                    reason = f"  {failures[0]}"
            console.print(f"  {tid}  {mark}{reason}")

    @case_app.command("list")
    def case_list(pack: Path | None = typer.Argument(None, help="Skill pack")) -> None:
        """List saved checks."""
        from skillgate_ai.case_pack import load_case_pack

        try:
            dest = _resolve_pack_arg(pack)
            loaded = load_case_pack(dest)
        except SkillGateError as exc:
            console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        if loaded is None or not loaded.cases:
            console.print("No checks saved.")
            return
        for case in loaded.cases:
            console.print(f"{case.id}  {case.status}  {case.prompt}")

    @case_app.command("remove")
    def case_remove(
        pack: Path | None = typer.Argument(None, help="Skill pack"),
        case_id: str = typer.Option(..., "--id", help="Check id to remove"),
    ) -> None:
        """Remove a custom check. Original seed checks stay."""
        from skillgate_ai.pack_edit import remove_pack_case

        try:
            dest = _resolve_pack_arg(pack)
            remove_pack_case(dest, case_id)
        except SkillGateError as exc:
            console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        console.print(f"Removed {case_id}.")

    @case_app.command("edit")
    def case_edit(
        pack: Path | None = typer.Argument(None, help="Skill pack"),
        case_id: str = typer.Option(..., "--id", help="Check id"),
        prompt: str | None = typer.Option(None, "--prompt"),
        expected: str | None = typer.Option(None, "--expected"),
        output_path: str | None = typer.Option(None, "--output"),
    ) -> None:
        """Edit a saved check."""
        from skillgate_ai.pack_edit import edit_pack_case

        try:
            dest = _resolve_pack_arg(pack)
            edit_pack_case(
                dest,
                case_id,
                prompt=prompt,
                expected=expected,
                output_path=output_path,
            )
        except SkillGateError as exc:
            console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        console.print(f"Updated {case_id}.")

    @case_app.command("import")
    def case_import_cmd(
        pack: Path | None = typer.Argument(None, help="Skill pack"),
        file: Path = typer.Argument(..., help="CSV, JSONL, or YAML file"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing"),
        on_conflict: str = typer.Option(
            "fail",
            "--on-conflict",
            help="When a check id already exists: fail, skip, or replace",
        ),
    ) -> None:
        """Import checks from a dataset file into evals/cases.yaml."""
        from skillgate_ai.case_import import CaseImportError, apply_case_import

        conflict = on_conflict.strip().lower()
        if conflict not in {"fail", "skip", "replace"}:
            console.print("--on-conflict must be fail, skip, or replace.")
            raise typer.Exit(2)
        try:
            dest = _resolve_pack_arg(pack)
            data = file.expanduser().read_bytes()
            plan = apply_case_import(
                dest,
                data,
                filename=file.name,
                on_conflict=conflict,  # type: ignore[arg-type]
                dry_run=dry_run,
            )
        except CaseImportError as exc:
            console.print(exc.message)
            for row in exc.rows:
                console.print(f"  row {row.row}: {row.error}")
            raise typer.Exit(exc.exit_code) from None
        except SkillGateError as exc:
            console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        for row in plan.rows:
            if row.error:
                console.print(f"row {row.row}  error  {row.error}")
                continue
            action = row.action if dry_run else "imported"
            prompt = row.prompt if len(row.prompt) <= 48 else row.prompt[:45] + "..."
            console.print(f"row {row.row}  {row.id:<24}  {action:<8}  {prompt}")
        for warn in plan.warnings:
            console.print(warn)
        if dry_run:
            console.print(f"Would import {len(plan.checks)} check(s) from {plan.format}.")
        else:
            console.print(f"Imported {len(plan.checks)} check(s) from {plan.format}.")

    @case_app.command("bind")
    def case_bind(
        pack: Path | None = typer.Argument(None, help="Skill pack"),
        inherit: bool = typer.Option(True, "--inherit/--no-inherit"),
        expand: bool = typer.Option(False, "--expand"),
    ) -> None:
        """Attach this skill’s sample files to checks that need them."""
        from skillgate_ai.pack_edit import bind_case_files

        try:
            dest = _resolve_pack_arg(pack)
            bind_case_files(dest, inherit=inherit, expand=expand)
        except SkillGateError as exc:
            console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        console.print("Bound sample files to checks.")

    @judge_app.command("remove-question")
    def judge_remove_question(
        pack: Path | None = typer.Argument(None, help="Skill pack"),
        question_id: str = typer.Option(..., "--id", help="Extra question id"),
    ) -> None:
        """Remove an extra scoring question. Skill Gate’s six stay."""
        from skillgate_ai.pack_edit import remove_judge_question

        try:
            dest = _resolve_pack_arg(pack)
            remove_judge_question(dest, question_id)
        except SkillGateError as exc:
            console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        console.print(f"Removed {question_id}.")

    @judge_app.command("set-question")
    def judge_set_question(
        pack: Path | None = typer.Argument(None, help="Skill pack"),
        question_id: str = typer.Option(..., "--id"),
        on_fail: str = typer.Option(..., "--on-fail", help="Fail the check | Warn only"),
    ) -> None:
        """Change Fail vs warn for a built-in or extra question."""
        from skillgate_ai.pack_edit import set_question_on_fail

        try:
            dest = _resolve_pack_arg(pack)
            set_question_on_fail(dest, question_id, on_fail)
        except SkillGateError as exc:
            console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        console.print(f"Updated {question_id}.")
