"""Shared check runner for the CLI and the local UI.

``run_check`` is the only place that resolves a pack, picks a harness, runs
evals, persists history, and computes the process exit code (0 / 1 / 2).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skillgate_ai.config import LLMConfig, get_llm_config, load_env
from skillgate_ai.demo_files import ensure_demo_pdfs
from skillgate_ai.pack_schema import _example_marker_slug
from skillgate_ai.engine import EvalProgress, SuiteReport, run_eval
from skillgate_ai.errors import MissingLLMKeyError, SkillGateError
from skillgate_ai.eval_config import (
    EvalConfigError,
    EvalRunConfig,
    apply_eval_config,
    resolve_eval_config,
    stamp_resolved,
    with_judge,
    with_model,
    with_timeout_effective,
)
from skillgate_ai.harness import is_live_harness, live_harness_or_error
from skillgate_ai.judge import judge_stamp, resolve_judge
from skillgate_ai.history import append_eval
from skillgate_ai.live import RunControl
from skillgate_ai.observability import (
    capture_run_failure,
    eval_transaction,
    log_eval_finished,
    set_eval_passed,
)
from skillgate_ai.paths import is_skill_pack, project_root, resolve_user_path
from skillgate_ai.report import report_to_dict

@dataclass
class CheckResult:
    report: SuiteReport | None
    exit_code: int
    demo_notice: str | None = None
    error: dict[str, str | None] | None = None
    expect_fail_notice: str | None = None
    run_id: str = ""


def prepare_pack_fixtures(pack: Path) -> None:
    if (pack / "SKILL.md").is_file() and _example_marker_slug(pack) is not None:
        ensure_demo_pdfs(pack / "evals" / "fixtures")


def persist_eval(
    *,
    pack_root: Path | None,
    run_id: str,
    passed: bool | None,
    report: dict | None = None,
    error: dict | None = None,
    config: EvalRunConfig | dict | None = None,
    tryout: bool = False,
    gate_moved: bool | None = None,
) -> None:
    if pack_root is None or not pack_root.is_dir():
        return
    from skillgate_ai.api_payloads import scrub_browser_payload, scrub_config

    cfg = config.to_dict() if isinstance(config, EvalRunConfig) else config
    is_tryout = tryout or bool((report or {}).get("tryout"))
    append_eval(
        pack_root,
        run_id=run_id,
        passed=passed,
        report=scrub_browser_payload(report) if report else None,
        error=error,
        config=scrub_config(cfg) if cfg else None,
        tryout=is_tryout,
        gate_moved=gate_moved,
    )


def resolve_pack_and_spec(target: Path, root: Path):
    """Return (spec, skill_path, pack_root) for a pack dir or a suite YAML."""
    from skillgate_ai.case_pack import expand_from_pack

    path = resolve_user_path(target, root)
    if path.is_dir() and (path / "SKILL.md").is_file():
        return expand_from_pack(path), path, path
    if path.is_file() and path.suffix.lower() in {".yaml", ".yml"}:
        from skillgate_ai.suite import load_suite

        spec, _ = load_suite(path)
        return spec, None, None
    if is_skill_pack(path):
        return expand_from_pack(path), path, path
    raise SkillGateError(
        f"Not a skill pack or suite: {target}",
        hint="Pass a skill folder with SKILL.md, or a suite YAML.",
    )


def run_check(
    target: Path,
    *,
    skill: Path | None = None,
    harness: str | None = None,
    sandbox: str = "local",
    demo: bool = False,
    live: bool = True,
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
    tryout: bool = False,
    no_judge: bool = False,
) -> CheckResult:
    """Run pack-local evals. Exit 0 green, 1 red, 2 live-without-key."""
    project = root if root is not None else project_root()
    suite_path = resolve_user_path(target, project)
    if root is None and not os.environ.get("SKILLGATE_ROOT") and suite_path.is_dir():
        from skillgate_ai.paths import config_root_for

        project = config_root_for(suite_path)
    load_env(project)
    cfg = get_llm_config(project)
    sandbox_kind = sandbox or cfg.sandbox_pref
    spec = None
    pack_root: Path | None = None
    skill_path = skill
    try:
        if suite_path.is_dir() and (suite_path / "SKILL.md").is_file():
            prepare_pack_fixtures(suite_path)
            skill_path = skill or suite_path
            pack_root = suite_path
            if checks:
                from skillgate_ai.case_pack import suite_from_checks

                spec = suite_from_checks(
                    suite_path,
                    checks,
                    tryout=tryout,
                    only_listed=tryout or source == "compare",
                )
            else:
                from skillgate_ai.case_pack import expand_from_pack

                spec = expand_from_pack(suite_path)
        else:
            spec, skill_from_pack, pack_root = resolve_pack_and_spec(target, project)
            if skill_from_pack is not None:
                skill_path = skill or skill_from_pack
    except SkillGateError as exc:
        return CheckResult(
            report=None,
            exit_code=exc.exit_code,
            error={"message": exc.message, "hint": exc.hint},
        )

    from skillgate_ai.run_lock import project_run_lock

    lock = project_run_lock(project)
    try:
        lock.__enter__()
    except SkillGateError as exc:
        return CheckResult(
            report=None,
            exit_code=exc.exit_code,
            error={"message": exc.message, "hint": exc.hint},
        )

    try:
        return _execute_check(
            project=project,
            suite_path=suite_path,
            pack_root=pack_root,
            skill_path=skill_path,
            spec=spec,
            cfg=cfg,
            sandbox_kind=sandbox_kind,
            harness=harness,
            expect_fail=expect_fail,
            model=model,
            timeout=timeout,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            on_progress=on_progress,
            control=control,
            run_id=run_id,
            source=source,
            tryout=tryout,
            no_judge=no_judge,
        )
    finally:
        lock.__exit__(None, None, None)


def _execute_check(
    *,
    project: Path,
    suite_path: Path,
    pack_root: Path | None,
    skill_path: Path | None,
    spec: Any,
    cfg: LLMConfig,
    sandbox_kind: str,
    harness: str,
    expect_fail: bool,
    model: str | None,
    timeout: int | None,
    temperature: float | None,
    reasoning_effort: str | None,
    on_progress: Callable[[EvalProgress], None] | None,
    control: RunControl | None,
    run_id: str | None,
    source: str,
    tryout: bool,
    no_judge: bool = False,
) -> CheckResult:
    rid = run_id or uuid.uuid4().hex[:12]
    skill_label = skill_path.name if skill_path else suite_path.stem
    run_cfg: EvalRunConfig | None = None
    demo_notice: str | None = None
    started = False
    try:
        harness_pref = (harness if harness is not None else cfg.harness_pref) or "auto"
        run_cfg = resolve_eval_config(
            harness_pref=harness_pref,
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
        resolved = live_harness_or_error(harness_pref, cfg)
        run_cfg = stamp_resolved(run_cfg, resolved.name, cfg)
        outcome_judge = resolve_judge(cfg, harness_name=resolved.name)
        run_cfg = with_judge(run_cfg, judge_stamp(outcome_judge))
        mode = "live"
        with eval_transaction(
            run_id=rid,
            skill=skill_label,
            harness=resolved.name,
            mode=mode,
            suite=suite_path.stem,
            sandbox=sandbox_kind,
        ):
            started = True
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
                strict_ingest=source == "cli",
            )
            run_cfg = with_timeout_effective(run_cfg, report.timeout_effective)
            agent_model = next((t.model for t in report.tasks if t.model), None)
            if agent_model:
                run_cfg = with_model(run_cfg, agent_model)
            report.config = run_cfg.to_dict()
            set_eval_passed(report.passed)
            log_eval_finished(
                run_id=rid,
                skill=report.skill,
                harness=report.harness,
                passed=report.passed,
            )
            persist_root = Path(report.skill_path) if report.skill_path else pack_root
            payload = report_to_dict(report)
            if tryout:
                payload["tryout"] = True
            persist_eval(
                pack_root=persist_root,
                run_id=rid,
                passed=report.passed,
                report=payload,
                config=run_cfg,
                tryout=tryout,
            )
    except SkillGateError as exc:
        capture_run_failure(exc)
        persist_root = skill_path or pack_root
        err = {"message": exc.message, "hint": exc.hint}
        if persist_root and run_cfg is not None:
            if isinstance(exc, (EvalConfigError, MissingLLMKeyError)):
                if tryout or started:
                    persist_eval(
                        pack_root=persist_root,
                        run_id=rid,
                        passed=None,
                        error=err,
                        config=run_cfg,
                        tryout=tryout,
                        gate_moved=False,
                    )
            elif started:
                persist_eval(
                    pack_root=persist_root,
                    run_id=rid,
                    passed=False,
                    error=err,
                    config=run_cfg,
                    tryout=tryout,
                    gate_moved=True,
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
    exit_code = 0 if report.passed else 1
    if (
        not no_judge
        and not tryout
        and is_live_harness(report.harness)
        and _quality_scoring_was_skipped(report)
    ):
        exit_code = 2
    return CheckResult(
        report=report,
        exit_code=exit_code,
        demo_notice=demo_notice,
        run_id=rid,
    )


def _quality_scoring_was_skipped(report: SuiteReport) -> bool:
    if not is_live_harness(report.harness):
        return False
    for task in report.tasks:
        judge = task.judge if isinstance(task.judge, dict) else None
        if isinstance(judge, dict):
            status = str(judge.get("status") or "")
            if status == "error":
                return True
            if status == "skip" and str(judge.get("provider") or "") == "skip":
                return True
    cfg = report.config if isinstance(report.config, dict) else {}
    stamp = cfg.get("judge") if isinstance(cfg, dict) else None
    if isinstance(stamp, dict) and str(stamp.get("provider") or "") == "skip":
        return True
    return False


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
