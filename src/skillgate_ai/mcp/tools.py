"""MCP tool implementations (no FastAPI or MCP SDK imports)."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from skillgate_ai import __version__
from skillgate_ai.api_payloads import history_row_to_run, scrub_browser_payload
from skillgate_ai.case_import import apply_case_import
from skillgate_ai.case_pack import case_view, dataset_view, skill_has_dataset
from skillgate_ai.catalog import catalog_entries
from skillgate_ai.config import get_llm_config, load_env, missing_key_error
from skillgate_ai.deploy_gate import run_gate_summary
from skillgate_ai.errors import SkillGateError
from skillgate_ai.history import latest_eval, load_history
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.keys import key_presence
from skillgate_ai.mcp.context import McpContext, resolve_pack, tool_error_payload
from skillgate_ai.pack_edit import (
    _UNSET,
    add_pack_case,
    edit_pack_case,
    remove_pack_case,
    set_pack_tool_checks,
    tryout_checks,
)
from skillgate_ai.paths import is_skill_pack
from skillgate_ai.run_lock import BUSY_HINT, project_run_lock
from skillgate_ai.run_registry import BUSY_MESSAGE, RunBusyError, RunRequest
from skillgate_ai.run_status import assert_valid_run_id, find_status_file, record_from_status
from skillgate_ai.scaffold import scaffold_trigger_cases
from skillgate_ai.workspace import new_skill

_MAX_IMPORT_BYTES = 2 * 1024 * 1024


def _compact(pack: Path) -> dict[str, Any] | None:
    return dataset_view(pack, include_files=False)


def _requested_case_ids(case_ids: list[str] | None) -> list[str] | None:
    if case_ids is None:
        return None
    from skillgate_ai.pack_schema import case_id_slug

    seen: set[str] = set()
    out: list[str] = []
    for raw in case_ids:
        slug = case_id_slug(str(raw))
        if slug and slug not in seen:
            seen.add(slug)
            out.append(slug)
    return out if out else None


def _meta_reason(ctx: McpContext, run_id: str) -> str | None:
    meta = ctx.run_meta.get(run_id)
    if meta:
        reason = meta.get("tryout_reason")
        return str(reason) if reason else None
    found = find_status_file(ctx.root, run_id)
    if found is None:
        return None
    payload, _pack = found
    disk = payload.get("meta")
    if isinstance(disk, dict):
        reason = disk.get("tryout_reason")
        return str(reason) if reason else None
    return None


def _resolve_run_record(ctx: McpContext, run_id: str) -> dict[str, Any]:
    assert_valid_run_id(run_id)
    record = ctx.registry.get(run_id)
    if record is not None:
        return record
    try:
        row, pack = _history_row(ctx, run_id, None)
        return history_row_to_run(row, pack)
    except SkillGateError:
        found = find_status_file(ctx.root, run_id)
        if found is None:
            raise SkillGateError(f"Unknown run {run_id}") from None
        payload, _pack = found
        record = record_from_status(payload)
        if record is None:
            raise SkillGateError(f"Unknown run {run_id}") from None
        return record


def _history_row(ctx: McpContext, run_id: str, skill: str | None) -> tuple[dict[str, Any], Path]:
    row: dict[str, Any] | None = None
    skill_path: Path | None = None
    if skill is not None:
        pack = resolve_pack(ctx, skill)
        skill_path = pack
        for item in load_history(pack, limit=0):
            if str(item.get("run_id") or "") == run_id:
                row = item
                break
    else:
        for entry in catalog_entries(ctx.root):
            path = Path(entry["absolute"])
            for item in load_history(path, limit=0):
                if str(item.get("run_id") or "") == run_id:
                    row = item
                    skill_path = path
                    break
            if row is not None:
                break
        if row is None and is_skill_pack(ctx.root):
            skill_path = ctx.root
            for item in load_history(ctx.root, limit=0):
                if str(item.get("run_id") or "") == run_id:
                    row = item
                    break
    if row is None or skill_path is None:
        raise SkillGateError(f"No run named {run_id}.")
    return row, skill_path


def validate_skill(ctx: McpContext, *, skill: str) -> dict[str, Any]:
    pack = resolve_pack(ctx, skill)
    try:
        parsed = ingest_skill(pack, strict=True)
    except SkillGateError as exc:
        return {
            "ok": False,
            "path": str(pack),
            "error": tool_error_payload(exc),
        }
    warning = parsed.warning
    return {
        "ok": True,
        "name": parsed.name,
        "description": parsed.description,
        "warning": warning,
        "path": str(pack),
    }


def dataset_scaffold(
    ctx: McpContext,
    *,
    skill: str | None = None,
    name: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if skill and name:
        raise SkillGateError("Pass skill or name, not both.")
    if not skill and not name:
        raise SkillGateError("Pass one of skill or name.")
    if name:
        path = new_skill(ctx.root, name)
        view = _compact(path)
        return {
            "ok": True,
            "path": str(path),
            "created": True,
            "dataset": view,
        }
    pack = resolve_pack(ctx, skill or "")
    if skill_has_dataset(pack) and not force:
        raise SkillGateError(
            "This skill already has cases.",
            hint="Pass force=true to replace them with the two starter cases.",
        )
    scaffold_trigger_cases(pack)
    return {
        "ok": True,
        "path": str(pack),
        "created": False,
        "dataset": _compact(pack),
    }


def dataset_get(ctx: McpContext, *, skill: str, include_files: bool = False) -> dict[str, Any]:
    pack = resolve_pack(ctx, skill)
    view = dataset_view(pack, include_files=include_files)
    if view is None:
        raise SkillGateError("Not a skill folder.")
    return {"path": str(pack), "include_files": include_files, "dataset": view}


def case_get(ctx: McpContext, *, skill: str, case_id: str) -> dict[str, Any]:
    from skillgate_ai.pack_schema import case_id_slug

    pack = resolve_pack(ctx, skill)
    view = case_view(pack, case_id)
    if view is None:
        raise SkillGateError(f"No check named {case_id_slug(case_id)}.")
    return {"path": str(pack), **view}


def pack_tool_checks_set(
    ctx: McpContext, *, skill: str, tool_checks: dict[str, Any] | None
) -> dict[str, Any]:
    pack = resolve_pack(ctx, skill)
    updated = set_pack_tool_checks(pack, tool_checks)
    sparse = updated.tool_checks.to_sparse_dict() if updated.tool_checks else None
    return {"ok": True, "tool_checks": sparse, "dataset": _compact(pack)}


def case_add(
    ctx: McpContext,
    *,
    skill: str,
    prompt: str,
    case_id: str | None = None,
    expected: str | None = None,
    output_path: str | None = None,
    should_trigger: bool = True,
    inputs: list[str] | None = None,
    output_optional: bool = False,
    force: bool = False,
    tool_checks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pack = resolve_pack(ctx, skill)
    from skillgate_ai.case_pack import load_case_pack

    loaded_before = load_case_pack(pack)
    before = {c.id for c in loaded_before.cases} if loaded_before is not None else set()
    add_pack_case(
        pack,
        prompt=prompt,
        case_id=case_id,
        expected=expected,
        output_path=output_path,
        should_trigger=should_trigger,
        inputs=inputs,
        force=force,
        output_optional=output_optional,
        tool_checks=tool_checks,
    )
    loaded_after = load_case_pack(pack)
    after = {c.id for c in loaded_after.cases} if loaded_after is not None else set()
    new_ids = after - before
    resolved_id = next(iter(new_ids), None) if new_ids else None
    if resolved_id is None and case_id:
        from skillgate_ai.pack_schema import case_id_slug

        resolved_id = case_id_slug(case_id)
    if resolved_id is None:
        raise SkillGateError("Could not determine new case id.")
    return {"ok": True, "case_id": resolved_id, "dataset": _compact(pack)}


def case_edit(
    ctx: McpContext,
    *,
    skill: str,
    case_id: str,
    prompt: str | None = None,
    expected: str | None = None,
    output_path: str | None = None,
    output_optional: bool | None = None,
    tool_checks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if all(v is None for v in (prompt, expected, output_path, output_optional, tool_checks)):
        raise SkillGateError("Nothing to change.")
    from skillgate_ai.pack_schema import case_id_slug

    pack = resolve_pack(ctx, skill)
    slug = case_id_slug(case_id)
    edit_pack_case(
        pack,
        case_id,
        prompt=prompt,
        expected=expected,
        output_path=output_path,
        output_optional=output_optional,
        tool_checks=_UNSET if tool_checks is None else tool_checks,
    )
    return {"ok": True, "case_id": slug, "dataset": _compact(pack)}


def case_remove(ctx: McpContext, *, skill: str, case_id: str) -> dict[str, Any]:
    from skillgate_ai.pack_schema import case_id_slug

    pack = resolve_pack(ctx, skill)
    slug = case_id_slug(case_id)
    remove_pack_case(pack, case_id)
    return {"ok": True, "removed": slug, "dataset": _compact(pack)}


def case_import(
    ctx: McpContext,
    *,
    skill: str,
    content: str,
    format: Literal["csv", "jsonl", "yaml"] | None = None,
    filename: str | None = None,
    on_conflict: Literal["fail", "skip", "replace"] = "fail",
    dry_run: bool = False,
) -> dict[str, Any]:
    encoded = content.encode("utf-8")
    if len(encoded) > _MAX_IMPORT_BYTES:
        raise SkillGateError("Import is too large (max 2 MiB).")
    pack = resolve_pack(ctx, skill)
    plan = apply_case_import(
        pack,
        encoded,
        filename=filename,
        format_hint=format,
        on_conflict=on_conflict,
        dry_run=dry_run,
    )
    applied = 0 if dry_run else len(plan.checks)
    return {
        "ok": True,
        "dry_run": dry_run,
        "format": plan.format,
        "rows": [asdict(r) for r in plan.rows],
        "warnings": plan.warnings,
        "applied": applied,
        "dataset": _compact(pack),
    }


def check_start(
    ctx: McpContext,
    *,
    skill: str,
    harness: Literal["auto", "cursor-agent", "codex", "claude"] = "auto",
    case_ids: list[str] | None = None,
    tryout: bool = False,
    no_judge: bool = False,
    model: str | None = None,
    timeout_sec: int | None = None,
) -> dict[str, Any]:
    pack = resolve_pack(ctx, skill)
    load_env(ctx.root)
    if not get_llm_config(ctx.root).has_any_key:
        raise missing_key_error()
    if ctx.registry.busy():
        raise RunBusyError(BUSY_MESSAGE, hint=BUSY_HINT)
    with project_run_lock(ctx.root):
        pass
    requested = _requested_case_ids(case_ids)
    checks: list[dict[str, Any]] | None = None
    tryout_reason: str | None = "explicit" if tryout else None
    if requested:
        from skillgate_ai.case_pack import load_case_pack

        loaded = load_case_pack(pack)
        if loaded is None:
            raise SkillGateError("This skill has no checks yet.")
        known = {c.id for c in loaded.cases}
        unknown = [cid for cid in requested if cid not in known]
        if unknown:
            raise SkillGateError(f"No check named {unknown[0]}.")
        pinned = {c.id for c in loaded.cases if c.status == "pinned"}
        wanted = set(requested)
        if not tryout and wanted == pinned:
            checks = None
        else:
            checks = [c for cid in requested for c in tryout_checks(pack, cid)]
            if not tryout:
                tryout_reason = "includes_drafts" if wanted - pinned else "subset"
            tryout = True
    overrides = {"model": model, "timeout_sec": timeout_sec}
    config = {k: v for k, v in overrides.items() if v is not None}
    started = ctx.registry.start(
        RunRequest(
            skill_path=pack,
            harness=harness,
            checks=checks,
            config=config,
            tryout=tryout,
            no_judge=no_judge,
            source="mcp",
        )
    )
    run_id = started["id"]
    meta = {"tryout_reason": tryout_reason, "case_ids": requested}
    ctx.run_meta[run_id] = meta
    ctx.registry.set_run_meta(run_id, meta)
    row = {"status": "running", "tryout": tryout}
    gate = run_gate_summary(row, tryout_reason=tryout_reason)
    return {
        "id": run_id,
        "status": started["status"],
        "skill": pack.name,
        "tryout": tryout,
        "tryout_reason": tryout_reason,
        "case_ids": requested,
        "run_gate": gate,
    }


def check_poll(
    ctx: McpContext,
    *,
    run_id: str,
    include_report: bool = False,
) -> dict[str, Any]:
    record = _resolve_run_record(ctx, run_id)
    out = dict(scrub_browser_payload(record))
    reason = _meta_reason(ctx, run_id)
    out["run_gate"] = run_gate_summary(out, tryout_reason=reason)
    if reason is not None:
        out["run_gate"] = {**out["run_gate"], "tryout_reason": reason}
    out["tryout_reason"] = out["run_gate"].get("tryout_reason")
    if not include_report and out.get("status") != "running":
        out["report"] = None
        out["report_omitted"] = True
    return out


def check_cancel(
    ctx: McpContext,
    *,
    run_id: str,
    mode: Literal["kill", "skip"] = "kill",
) -> dict[str, Any]:
    ok = ctx.registry.kill(run_id) if mode == "kill" else ctx.registry.skip(run_id)
    if not ok:
        raise SkillGateError(f"Run {run_id} is not running.")
    return {"ok": True, "id": run_id, "mode": mode, "status": "running"}


def report_latest(ctx: McpContext, *, skill: str) -> dict[str, Any]:
    pack = resolve_pack(ctx, skill)
    row = latest_eval(pack)
    run = history_row_to_run(row, pack) if row is not None else None
    if run is not None:
        run_id = str(run.get("id") or (row or {}).get("run_id") or "")
        reason = _meta_reason(ctx, run_id)
        if reason is not None:
            run = dict(run)
            run["run_gate"] = {**run["run_gate"], "tryout_reason": reason}
            run["tryout_reason"] = reason
    return {"run": run, "path": str(pack)}


def report_get(
    ctx: McpContext,
    *,
    run_id: str,
    skill: str | None = None,
) -> dict[str, Any]:
    row, skill_path = _history_row(ctx, run_id, skill)
    out = history_row_to_run(row, skill_path)
    reason = _meta_reason(ctx, run_id)
    if reason is not None:
        out = dict(out)
        out["run_gate"] = {**out["run_gate"], "tryout_reason": reason}
        out["tryout_reason"] = reason
    return out


def doctor(ctx: McpContext) -> dict[str, Any]:
    load_env(ctx.root)
    cfg = get_llm_config(ctx.root)
    from skillgate_ai.harness import harness_auth_status

    agents = harness_auth_status(cfg)
    raw_keys = key_presence(ctx.root)
    keys = {name: {k: bool(v) for k, v in meta.items()} for name, meta in raw_keys.items()}
    return {
        "root": str(ctx.root),
        "can_check": bool(cfg.has_any_key),
        "agents": agents,
        "keys": keys,
        "version": __version__,
    }
