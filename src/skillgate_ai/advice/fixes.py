from __future__ import annotations

from skillgate_ai.advice.behavior import _behavior_fix, behavior_question_ids
from skillgate_ai.advice.model import FixAdvice
from skillgate_ai.advice.synth import _tighten_description, synthesize_trigger_description
from skillgate_ai.advice.text import (
    _command_fail_snippet,
    _frontmatter,
    _is_script_failure,
    _suggested_steps,
)
from skillgate_ai.ingest import Skill
from skillgate_ai.scorers import Score
from skillgate_ai.suite import TaskSpec


def advise_task(
    task: TaskSpec,
    scores: list[Score],
    skill: Skill,
    selected: str | None,
    *,
    reference: Skill | None = None,
    sibling_prompts: list[str] | None = None,
    returncode: int | None = None,
    stderr: str = "",
    judge: dict | None = None,
) -> FixAdvice | None:
    failed = [s for s in scores if not s.passed]
    if not failed:
        return None
    trigger = next((s for s in failed if s.scorer == "skill_trigger"), None)
    completion = next((s for s in failed if s.scorer == "task_completion"), None)
    rubric = next((s for s in failed if s.scorer == "rubric"), None)
    prompts = list(sibling_prompts or [task.prompt])
    trigger_unopened = bool(trigger and task.expect_skill and (trigger.actual or "none") == "none")
    behavior = behavior_question_ids(judge)
    if trigger_unopened and behavior:
        return _behavior_fix(behavior[0], skill_unopened=True)

    if trigger_unopened:
        description = synthesize_trigger_description(skill, prompts, reference)
        return _trigger_fix(skill, task.prompt, description, reference)

    if trigger and task.expect_skill is None and trigger.actual not in {None, "none"}:
        description = _tighten_description(skill, task.prompt)
        return FixAdvice(
            headline="Skill triggered when it shouldn’t",
            why=(
                f"The description for `{skill.name}` matched a request that should use no skill: "
                f"“{task.prompt}”."
            ),
            change=(
                "Tighten `description:` so it lists when to use the skill — and "
                "implicitly excludes everything else."
            ),
            paste=_frontmatter(skill.name, description),
            target="description",
            description=description,
        )

    if trigger and task.expect_skill and trigger.actual not in {None, "none", task.expect_skill}:
        description = synthesize_trigger_description(skill, prompts, reference)
        return FixAdvice(
            headline=f"Wrong skill triggered ({trigger.actual})",
            why=f"Expected `{task.expect_skill}` but the agent picked `{trigger.actual}`.",
            change=(
                "Make this skill’s description more specific, using keywords from "
                "the failed requests."
            ),
            paste=_frontmatter(skill.name, description),
            target="description",
            description=description,
        )

    missing = (completion.detail if completion else "") or (
        rubric.detail if rubric else "missing output"
    )
    if _is_script_failure(returncode, stderr):
        snippet = _command_fail_snippet(stderr)
        why = f"The command exited {returncode}."
        if snippet:
            why = f"{why} {snippet}"
        return FixAdvice(
            headline="The command failed",
            why=why,
            change="The script failed. Fix the command or the script, then run this check again.",
            paste=_suggested_steps(task, why),
            target="body",
        )
    return FixAdvice(
        headline=completion.headline
        if completion
        else (rubric.headline if rubric else "Task failed"),
        why=(
            f"The skill triggered (or was expected to), but the work didn’t land. {missing}. "
            f"Request was: “{task.prompt}”."
        ),
        change=(
            "Add a numbered step in SKILL.md that writes the exact output path, "
            "or bundle a script under scripts/ and tell the agent to run it."
        ),
        paste=_suggested_steps(task, missing),
        target="body",
    )


def advise_suite(
    skill: Skill,
    tasks: list,
    *,
    reference: Skill | None = None,
) -> FixAdvice | None:
    failed = [t for t in tasks if not t.passed]
    if not failed:
        return None
    behavior_first = next(
        (t for t in failed if behavior_question_ids(getattr(t, "judge", None))),
        None,
    )
    if behavior_first is not None:
        if behavior_first.advice and behavior_first.advice.target != "description":
            return behavior_first.advice
        questions = behavior_question_ids(getattr(behavior_first, "judge", None))
        unopened = behavior_first.selected_skill in {None, "none"} and any(
            s.scorer == "skill_trigger" and not s.passed for s in behavior_first.scores
        )
        if questions:
            return _behavior_fix(questions[0], skill_unopened=unopened)
    trigger_misses = [
        t
        for t in failed
        if t.expect_skill
        and any(s.scorer == "skill_trigger" and not s.passed for s in t.scores)
        and (t.selected_skill in {None, "none"} or t.selected_skill is None)
        and not behavior_question_ids(getattr(t, "judge", None))
    ]
    if trigger_misses:
        prompts = [t.prompt for t in trigger_misses]
        description = synthesize_trigger_description(skill, prompts, reference)
        first = trigger_misses[0]
        return _trigger_fix(skill, first.prompt, description, reference)
    return failed[0].advice


def _trigger_fix(
    skill: Skill,
    example_prompt: str,
    description: str,
    reference: Skill | None,
    *,
    headline: str = "Skill didn’t trigger",
    ran: bool = False,
) -> FixAdvice:
    restore = None
    if reference and reference.name != skill.name and (reference.path / "scripts").is_dir():
        restore = reference.name
    note = (
        "Copy this into SKILL.md below, then run `skillgate check` on this same skill — "
        "don’t switch to a working copy of this skill."
        if restore or "sabotag" in skill.name
        else "Copy this into SKILL.md below, then run `skillgate check`."
    )
    if ran:
        why = (
            f"The log shows `{skill.name}` ran, but its description would not have "
            f"selected it for this request: “{example_prompt}”."
        )
    else:
        why = (
            f"The agent only sees name + description before opening SKILL.md. "
            f"This request was: “{example_prompt}” — and `{skill.name}`’s current description "
            f"never matched (it talks about something else)."
        )
    return FixAdvice(
        headline=headline,
        why=why,
        change=(
            "Replace the `description:` in SKILL.md with the block below, then run "
            "`skillgate check` on this same skill."
        ),
        paste=_frontmatter(skill.name, description),
        target="description",
        description=description,
        demo_note=note,
        restore_scripts_from=restore,
    )
