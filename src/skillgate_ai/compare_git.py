"""Git ref snapshots for version compare (skill files only; Dataset stays on pack)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable

from skillgate_ai.compare import (
    CompareArmSpec,
    CompareError,
    CompareResult,
    _arm_ids,
    _build_cases,
    _task_map,
    _usage_from_report,
)
from skillgate_ai.history import append_compare


def find_git_root(pack: Path) -> Path:
    pack = pack.resolve()
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=pack,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CompareError(
            "This skill folder is not inside a git repository.",
            hint="Use history runs to compare versions, or move the pack into a git work tree.",
        ) from exc
    root = Path(out.stdout.strip())
    if not root.is_dir():
        raise CompareError("Could not resolve git root for this skill.")
    return root


def _materialize_ref(pack: Path, git_root: Path, ref: str, dest: Path) -> Path:
    rel = pack.resolve().relative_to(git_root.resolve())
    dest.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            ["git", "archive", ref, str(rel)],
            cwd=git_root,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        raise CompareError(
            f"Git ref {ref!r} is not valid for this skill path.",
            hint="Use `git rev-parse` to verify the ref, or compare two history runs instead.",
        ) from exc
    import io
    import tarfile

    with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode="r:*") as tar:
        tar.extractall(dest, filter="data")
    skill_dir = dest / rel
    if not skill_dir.is_dir():
        raise CompareError(f"Ref {ref!r} did not include this skill folder.")
    evals_src = pack / "evals"
    evals_dst = skill_dir / "evals"
    if evals_src.is_dir():
        if evals_dst.exists():
            shutil.rmtree(evals_dst)
        shutil.copytree(evals_src, evals_dst)
    return skill_dir


def run_git_versions_compare(
    pack: Path,
    *,
    refs: list[str],
    compare_id: str,
    root: Path,
    run_check_fn: Callable[..., Any] | None = None,
    harness: str = "auto",
) -> CompareResult:
    if len(refs) != 2:
        raise CompareError("Pick exactly two git refs.")
    git_root = find_git_root(pack)
    arm_rows: list[dict[str, Any]] = []
    pack_fp: str | None = None
    pack_case_ids: list[str] = []

    with tempfile.TemporaryDirectory(prefix="skillgate-compare-") as tmp:
        tmp_path = Path(tmp)
        for idx, ref in enumerate(refs):
            arm_id = _arm_ids(2)[idx]
            label = f"{ref[:12]}"
            work = tmp_path / f"arm-{arm_id}"
            skill_dir = _materialize_ref(pack, git_root, ref, work)
            if not (skill_dir / "SKILL.md").is_file():
                raise CompareError(f"Ref {ref!r} has no SKILL.md for this skill path.")
            spec = CompareArmSpec(
                arm_id=arm_id,
                label=label,
                harness_pref=harness,
            )
            runner = run_check_fn
            from skillgate_ai.compare import run_check as default_run

            fn = runner or default_run
            run_id = uuid.uuid4().hex[:12]
            result = fn(
                skill_dir,
                run_id=run_id,
                source="compare",
                root=root,
                **spec.to_run_kwargs(),
            )
            from skillgate_ai.history import append_eval
            from skillgate_ai.report import report_to_dict

            arm_config = {
                "harness": harness,
                "harness_pref": harness,
                "source": "compare",
                "git_ref": ref,
            }
            if result.report is not None:
                append_eval(
                    pack,
                    run_id=run_id,
                    passed=result.report.passed,
                    report=report_to_dict(result.report),
                    config={**arm_config, "harness": result.report.harness or harness},
                )
            elif result.error:
                append_eval(
                    pack,
                    run_id=run_id,
                    passed=False,
                    error=result.error,
                    config=arm_config,
                )
            if result.error or result.report is None:
                raise CompareError(
                    result.error.get("message") if result.error else f"Ref {ref} failed to run.",
                    hint=result.error.get("hint") if result.error else None,
                )
            report = report_to_dict(result.report)
            fp = str(report.get("pack_fingerprint") or "")
            if pack_fp is None:
                pack_fp = fp
                pack_case_ids = list(report.get("pack_case_ids") or [])
            elif fp != pack_fp:
                raise CompareError("Dataset fingerprint differed between git refs.")
            arm_rows.append(
                {
                    "arm_id": arm_id,
                    "label": label,
                    "subtitle": ref,
                    "source": "git",
                    "git_ref": ref,
                    "run_id": run_id,
                    "passed": report.get("passed"),
                    "passed_count": report.get("passed_count"),
                    "task_count": report.get("task_count"),
                    "usage": _usage_from_report(report),
                    "duration_sec": None,
                    "task_by_id": _task_map(report),
                }
            )

    payload: dict[str, Any] = {
        "kind": "compare",
        "compare_id": compare_id,
        "mode": "versions",
        "skill": pack.name,
        "pack_fingerprint": pack_fp,
        "pack_case_ids": pack_case_ids,
        "status": "done",
        "arms": [{key: val for key, val in arm.items() if key != "task_by_id"} for arm in arm_rows],
        "cases": _build_cases(arm_rows, pack_case_ids),
        "spend": {"cap_usd": None, "spent_usd": None, "stopped_reason": None},
        "error": None,
    }
    append_compare(pack, row=payload)
    return CompareResult(exit_code=0, payload=payload)
