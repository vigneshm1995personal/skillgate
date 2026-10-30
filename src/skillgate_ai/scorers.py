"""First-class scorers: skill trigger, task completion, basic rubric."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

from skillgate_ai.suite import FileExpect, RubricCheck, ScorerSpec, TaskSpec


@dataclass
class Score:
    scorer: str
    passed: bool
    detail: str
    expected: str | None = None
    actual: str | None = None
    weight: float = 1.0
    headline: str = ""


@dataclass
class TriggerEvidence:
    selected_skill: str | None
    read_paths: list[str] = field(default_factory=list)
    transcript: str = ""


@dataclass
class RunArtifacts:
    workspace: Path
    trigger: TriggerEvidence
    stdout: str = ""
    stderr: str = ""


def score_task(
    task: TaskSpec,
    artifacts: RunArtifacts,
    *,
    skills: list | None = None,
) -> list[Score]:
    skip_output = task.expect_skill is None
    scores = [
        score_one(spec, task, artifacts, skills=skills)
        for spec in task.scorers
        if not (skip_output and spec.type in {"task_completion", "rubric", "answer_contains"})
    ]
    for score in scores:
        score.headline = headline_for(score)
    return scores


def score_one(
    spec: ScorerSpec,
    task: TaskSpec,
    artifacts: RunArtifacts,
    *,
    skills: list | None = None,
) -> Score:
    if spec.type == "skill_trigger":
        return score_skill_trigger(task, artifacts.trigger, skills=skills)
    if spec.type == "task_completion":
        return score_task_completion(spec.files, artifacts.workspace)
    if spec.type == "rubric":
        return score_rubric(spec.checks, spec.min_score, artifacts.workspace)
    if spec.type == "answer_contains":
        return score_answer_contains(spec.answer, artifacts)
    return Score(scorer=spec.type, passed=False, detail=f"Unknown scorer {spec.type}")


def headline_for(score: Score) -> str:
    if score.passed:
        if score.scorer == "skill_trigger":
            if score.expected == "none":
                return "Correctly did not trigger"
            return "Skill triggered"
        if score.scorer == "task_completion":
            return "Task completed"
        if score.scorer == "rubric":
            return "Rubric passed"
        if score.scorer == "answer_contains":
            return "Answer matched"
        return "Passed"
    if score.scorer == "skill_trigger":
        if (score.actual or "none") == "none":
            return "Skill didn’t trigger"
        return f"Wrong skill triggered ({score.actual})"
    if score.scorer == "task_completion":
        return f"Task failed: {score.detail}"
    if score.scorer == "rubric":
        return f"Rubric missed: {score.detail}"
    if score.scorer == "answer_contains":
        return f"Answer mismatch: {score.detail}"
    return score.detail


def score_skill_trigger(
    task: TaskSpec,
    evidence: TriggerEvidence,
    *,
    skills: list | None = None,
) -> Score:
    """Did the expected skill activate for this request?

    Gate pre-selects ``selected.json``, so selection alone is not enough: the
    skill's name+description must still be a valid progressive-disclosure
    trigger for the prompt (keeps sabotaged-description suites red).

    For ``expect_skill is None`` (no-trigger negatives): any resolved skill —
    including one inferred solely from a real ``SKILL.md`` read in
    ``read_paths`` — is a fail. Prompt/prose path mentions should not appear
    in ``read_paths`` (harness ``_parse_read_paths`` requires tool/shell
    evidence). Engine also omits staging skill packs on null-expect tasks.
    """
    expected = task.expect_skill
    selected = _normalize_skill(evidence.selected_skill)
    read = [_skill_from_path(p) for p in evidence.read_paths]
    inferred = selected
    if inferred is None:
        named = [name for name in read if name]
        if len(set(named)) == 1:
            inferred = named[0]
        elif expected and expected in named:
            inferred = expected

    if expected is None:
        passed = inferred is None
        detail = (
            "Correctly skipped skills"
            if passed
            else f"Triggered `{inferred}` on a task that should use no skill"
        )
        return Score(
            scorer="skill_trigger",
            passed=passed,
            detail=detail,
            expected="none",
            actual=inferred or "none",
        )

    if inferred == expected and skills:
        from skillgate_ai.harness import select_skill_from_descriptions

        picked = select_skill_from_descriptions(task.prompt, list(skills))
        if picked != expected:
            return Score(
                scorer="skill_trigger",
                passed=False,
                detail=(
                    f"Did not trigger `{expected}` (description does not match this request)"
                ),
                expected=expected,
                actual="none",
            )

    passed = inferred == expected

    if passed:
        detail = f"Triggered `{expected}`"
    elif inferred is None:
        detail = f"Did not trigger `{expected}` (this skill wasn't opened during this run)"
    else:
        detail = f"Triggered `{inferred}` instead of `{expected}`"
    return Score(
        scorer="skill_trigger",
        passed=passed,
        detail=detail,
        expected=expected,
        actual=inferred or "none",
    )


def score_task_completion(expects: list[FileExpect], workspace: Path) -> Score:
    if not expects:
        return Score(
            scorer="task_completion",
            passed=False,
            detail="Task completion scorer has no expected files",
        )
    failures: list[str] = []
    for item in expects:
        target = workspace / item.path
        if item.exists and not target.is_file():
            if item.optional:
                continue
            failures.append(f"missing file {item.path}")
            continue
        if not item.exists and target.exists():
            failures.append(f"{item.path} should not exist")
            continue
        if not target.is_file():
            continue
        data = target.read_bytes()
        if item.min_bytes is not None and len(data) < item.min_bytes:
            failures.append(f"{item.path} is {len(data)} bytes (need ≥ {item.min_bytes})")
        looks_text = Path(item.path).suffix.lower() in {
            ".json",
            ".txt",
            ".md",
            ".csv",
        }
        if looks_text:
            from skillgate_ai.case_pack import sniff_output_bytes

            sniffed = sniff_output_bytes(data)
            if sniffed["kind"] == "bytes":
                magic = sniffed.get("magic") or "bytes"
                failures.append(f"{item.path} is binary ({magic}), not text/JSON")
                continue
        if item.contains:
            text = _file_text(target)
            if item.contains not in text:
                failures.append(f"{item.path} does not contain {item.contains!r}")
        if item.min_pages is not None or item.max_pages is not None:
            pages = _pdf_pages(target)
            if pages is None:
                failures.append(f"{item.path} is not a readable PDF")
            else:
                if item.min_pages is not None and pages < item.min_pages:
                    failures.append(f"{item.path} has {pages} pages (need ≥ {item.min_pages})")
                if item.max_pages is not None and pages > item.max_pages:
                    failures.append(f"{item.path} has {pages} pages (need ≤ {item.max_pages})")
    passed = not failures
    detail = "All expected outputs present" if passed else "; ".join(failures)
    return Score(scorer="task_completion", passed=passed, detail=detail)


def score_answer_contains(needles: list[str], artifacts: RunArtifacts) -> Score:
    cleaned = [str(item).strip() for item in needles if str(item).strip()]
    if not cleaned:
        return Score(
            scorer="answer_contains",
            passed=True,
            detail="No expected answer text",
            weight=0,
        )
    haystack = _answer_haystack(artifacts)
    failures = [
        f"answer does not contain {needle!r}"
        for needle in cleaned
        if needle not in haystack
    ]
    passed = not failures
    detail = "Expected text found in final answer" if passed else "; ".join(failures)
    return Score(scorer="answer_contains", passed=passed, detail=detail)


def _answer_haystack(artifacts: RunArtifacts) -> str:
    parts = [
        artifacts.trigger.transcript or "",
        artifacts.stdout or "",
        artifacts.stderr or "",
    ]
    for line in (artifacts.trigger.transcript or "").splitlines():
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("type") == "result":
            result = obj.get("result")
            if isinstance(result, str) and result.strip():
                parts.append(result)
        message = obj.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text_block = block.get("text")
                        if isinstance(text_block, str) and text_block.strip():
                            parts.append(text_block)
    return "\n".join(parts)


def score_rubric(checks: list[RubricCheck], min_score: float, workspace: Path) -> Score:
    if not checks:
        return Score(scorer="rubric", passed=True, detail="No rubric checks", weight=0)
    hits = 0
    notes: list[str] = []
    for check in checks:
        ok, note = _rubric_check(check, workspace)
        if ok:
            hits += 1
        else:
            notes.append(f"{check.id}: {note}")
    ratio = hits / len(checks)
    passed = ratio + 1e-9 >= min_score
    if passed:
        detail = f"{hits}/{len(checks)} checks"
    else:
        detail = f"{hits}/{len(checks)} checks (need {min_score:.0%})"
        if notes:
            detail += " — " + "; ".join(notes)
    return Score(scorer="rubric", passed=passed, detail=detail, actual=f"{ratio:.2f}")


def _rubric_check(check: RubricCheck, workspace: Path) -> tuple[bool, str]:
    if not check.file:
        return False, "rubric check is missing `file`"
    target = workspace / check.file
    if not target.is_file():
        if check.optional:
            return True, "optional file absent"
        return False, f"missing {check.file}"
    min_bytes = None if check.optional else check.min_bytes
    if min_bytes is not None and target.stat().st_size < min_bytes:
        return False, "too small"
    if check.contains and check.contains not in _file_text(target):
        return False, f"missing {check.contains!r}"
    if check.pdf_pages is not None:
        pages = _pdf_pages(target)
        if pages != check.pdf_pages:
            return False, f"{pages} pages, expected {check.pdf_pages}"
    return True, "ok"


def _file_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        pages = _pdf_text(path)
        if pages is not None:
            return pages
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _pdf_pages(path: Path) -> int | None:
    try:
        return len(PdfReader(str(path)).pages)
    except Exception:
        return None


def _pdf_text(path: Path) -> str | None:
    try:
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return None


def _normalize_skill(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().strip("`").strip()
    if cleaned.lower() in {"", "none", "null", "n/a", "no-skill", "no_skill"}:
        return None
    return cleaned


def _skill_from_path(path: str) -> str | None:
    normalized = path.replace("\\", "/")
    match = re.search(r"(?:^|/)(?:\.skillgate/)?skills/([^/]+)/SKILL\.md$", normalized)
    if match:
        return match.group(1)
    parts = Path(normalized).parts
    if parts and parts[-1] == "SKILL.md" and len(parts) >= 2:
        return parts[-2]
    return None
