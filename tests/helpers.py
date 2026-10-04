"""Test helpers importable without treating ``tests`` as a package.

CI runs ``pytest -q`` with ``pythonpath = ["src", "tests"]``.
"""

from __future__ import annotations

from pathlib import Path


def trust_cleared_report(skill_path: Path) -> dict:
    """Build a live-green report that matches the skill's trust suite identity."""
    from skillgate_ai.case_pack import trust_suite_for_skill

    trust = trust_suite_for_skill(skill_path)
    if trust is None:
        raise AssertionError(f"no trust suite for {skill_path}")
    by_id = {task.id: task for task in trust.suite.tasks}
    tasks: list[dict] = []
    for case_id in trust.case_ids:
        spec = by_id.get(case_id)
        files = (
            [{"src": item.src, "dest": item.dest} for item in spec.files]
            if spec is not None
            else []
        )
        scores = [{"scorer": "skill_trigger", "passed": True}]
        if spec is not None and any(s.type == "task_completion" for s in spec.scorers):
            scores.append({"scorer": "task_completion", "passed": True})
        tasks.append(
            {
                "id": case_id,
                "passed": True,
                "files": files,
                "scores": scores,
            }
        )
    return {
        "passed": True,
        "pack_fingerprint": trust.fingerprint,
        "pack_case_ids": list(trust.case_ids),
        "tasks": tasks,
        "passed_count": len(tasks),
        "task_count": len(tasks),
    }
