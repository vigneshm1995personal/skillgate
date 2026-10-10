"""Shared check runner for the CLI and the local UI.

``run_check`` is the only place that resolves a pack, picks a harness, runs
evals, persists history, and computes the process exit code (0 / 1 / 2).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skillgate_ai.config import get_llm_config, load_env
from skillgate_ai.demo_files import ensure_demo_pdfs
from skillgate_ai.engine import EvalProgress, SuiteReport, run_eval
from skillgate_ai.errors import SkillGateError
from skillgate_ai.eval_config import (
    EvalConfigError,
    EvalRunConfig,
    apply_eval_config,
    resolve_eval_config,
    stamp_resolved,
    with_judge,
    with_timeout_effective,
)
from skillgate_ai.harness import DemoHarness, live_harness_or_error, resolve_harness
from skillgate_ai.judge import judge_stamp, resolve_judge
from skillgate_ai.history import append_eval
from skillgate_ai.live import RunControl
from skillgate_ai.observability import (
    capture_run_failure,
    eval_transaction,
    log_eval_finished,
    set_eval_passed,
)
from skillgate_ai.paths import is_skill_pack, project_root
from skillgate_ai.report import report_to_dict

DEMO_NOTICE = "Using the built-in checker. This is not a live model."


@dataclass
class CheckResult:
    report: SuiteReport | None
    exit_code: int
    demo_notice: str | None = None
    error: dict[str, str | None] | None = None
    expect_fail_notice: str | None = None
    run_id: str = ""


def prepare_pack_fixtures(pack: Path) -> None:
    if (pack / "SKILL.md").is_file():
        ensure_demo_pdfs(pack / "evals" / "fixtures")


def persist_eval(
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


def resolve_pack_and_spec(target: Path, root: Path):
    """Return (spec, skill_path, pack_root) for a pack dir or a suite YAML."""
    from skillgate_ai.case_pack import expand_from_pack

    path = target if target.is_absolute() else (root / target)
    if path.is_dir() and (path / "SKILL.md").is_file():
        prepare_pack_fixtures(path)
        return expand_from_pack(path), path, path
    if path.is_file() and path.suffix in {".yaml", ".yml"}:
        return None, None, None
    if is_skill_pack(path):
        prepare_pack_fixtures(path)
        return expand_from_pack(path), path, path
    raise SkillGateError(
        f"Not a skill pack or suite: {target}",
        hint="Pass a folder with SKILL.md + evals/cases.yaml, or a suite YAML.",
    )


def run_check(
    target: Path,
    *,
    skill: Path | None = None,
    harness: str = "auto",
    sandbox: str = "local",
    demo: bool = False,
    live: bool = False,
    expect_fail: bool = False,
    model: str | None = None,
    timeout: int | None = None,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
    on_progress: Callable[[EvalProgress], None] | None = None,
    control: RunControl | None = None,
    run_id: str | None = None,
    source: str = "cli",
    root: Path | None = None,
    checks: list[dict[str, Any]] | None = None,
) -> CheckResult:
    """Run pack-local evals. Exit 0 green, 1 red, 2 live-without-key."""
    project = root if root is not None else project_root()
    load_env(project)
    cfg = get_llm_config()
    sandbox_kind = sandbox or cfg.sandbox_pref
    spec = None
    suite_path = target if target.is_absolute() else project / target
    pack_root: Path | None = None
    skill_path = skill
    try:
        spec, skill_from_pack, pack_root = resolve_pack_and_spec(target, project)
        if skill_from_pack is not None:
            skill_path = skill or skill_from_pack
        if checks and pack_root is not None:
            from skillgate_ai.case_pack import suite_from_checks

            spec = suite_from_checks(pack_root, checks)
    except SkillGateError as exc:
        if suite_path.is_file():
            spec = None
            pack_root = None
        else:
            return CheckResult(
                report=None,
                exit_code=exc.exit_code,
                error={"message": exc.message, "hint": exc.hint},
            )

    rid = run_id or uuid.uuid4().hex[:12]
    skill_label = skill_path.name if skill_path else suite_path.stem
    run_cfg: EvalRunConfig | None = None
    demo_notice: str | None = None
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
            source=source,
        )
        cfg = apply_eval_config(cfg, run_cfg)
        pref = (harness or "auto").strip().lower() or "auto"
        if live:
            resolved = live_harness_or_error(harness, cfg)
        elif demo or pref in {"demo", "fixture", "offline"}:
            resolved = DemoHarness()
            demo_notice = DEMO_NOTICE
        elif pref == "auto" and cfg.has_any_key:
            resolved = live_harness_or_error("auto", cfg)
        elif pref == "auto":
            resolved = DemoHarness()
            demo_notice = DEMO_NOTICE
        else:
            resolved = resolve_harness(harness, cfg, demo=False)
        run_cfg = stamp_resolved(run_cfg, resolved.name, cfg)
        outcome_judge = resolve_judge(cfg, harness_name=resolved.name)
        run_cfg = with_judge(run_cfg, judge_stamp(outcome_judge))
        mode = "live" if live else ("demo" if resolved.name == "demo" else "live")
        with eval_transaction(
            run_id=rid,
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
                project_root=project,
                skill_override=skill_path or (suite_path if spec is not None else None),
                run_id=rid,
                timeout_override=run_cfg.timeout_sec,
                config=run_cfg.to_dict(),
                on_progress=on_progress,
                control=control,
                judge=outcome_judge,
            )
            run_cfg = with_timeout_effective(run_cfg, report.timeout_effective)
            report.config = run_cfg.to_dict()
            set_eval_passed(report.passed)
            log_eval_finished(
                run_id=rid,
                skill=report.skill,
                harness=report.harness,
                passed=report.passed,
            )
            persist_root = Path(report.skill_path) if report.skill_path else pack_root
            persist_eval(
                pack_root=persist_root,
                run_id=rid,
                passed=report.passed,
                report=report_to_dict(report),
                config=run_cfg,
            )
    except SkillGateError as exc:
        capture_run_failure(exc)
        persist_root = skill_path or pack_root
        err = {"message": exc.message, "hint": exc.hint}
        if run_cfg is not None and not isinstance(exc, EvalConfigError) and persist_root:
            persist_eval(
                pack_root=persist_root,
                run_id=rid,
                passed=False,
                error=err,
                config=run_cfg,
            )
        return CheckResult(
            report=None,
            exit_code=exc.exit_code,
            demo_notice=demo_notice,
            error=err,
            run_id=rid,
        )

    notice: str | None = None
    red = not report.passed
    if expect_fail:
        if red:
            notice = "Suite failed as expected (intentional fail)."
            return CheckResult(
                report=report,
                exit_code=0,
                demo_notice=demo_notice,
                expect_fail_notice=notice,
                run_id=rid,
            )
        notice = "Expected this suite to fail, but the gate was green."
        return CheckResult(
            report=report,
            exit_code=1,
            demo_notice=demo_notice,
            expect_fail_notice=notice,
            run_id=rid,
        )
    return CheckResult(
        report=report,
        exit_code=0 if report.passed else 1,
        demo_notice=demo_notice,
        run_id=rid,
    )


def result_payload(result: CheckResult) -> dict[str, Any]:
    """JSON for the local UI / tests. ``exit_code`` matches the CLI."""
    payload: dict[str, Any] = {
        "run_id": result.run_id,
        "exit_code": result.exit_code,
        "demo_notice": result.demo_notice,
        "expect_fail_notice": result.expect_fail_notice,
        "error": result.error,
        "report": report_to_dict(result.report) if result.report is not None else None,
    }
    return payload
