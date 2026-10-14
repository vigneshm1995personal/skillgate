"""Copy-paste fix loop: fail → why → a description that would actually trigger."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

from skillgate_ai.harness import select_skill_from_descriptions, tokenize
from skillgate_ai.ingest import FRONTMATTER_RE, Skill
from skillgate_ai.scorers import Score
from skillgate_ai.suite import TaskSpec

_MEAL_NOISE = {
    "dinner",
    "dinners",
    "recipe",
    "recipes",
    "grocery",
    "groceries",
    "pantry",
    "meal",
    "meals",
    "shopping",
}


@dataclass
class FixAdvice:
    headline: str
    why: str
    change: str
    paste: str
    target: str  # description | body
    description: str | None = None
    demo_note: str | None = None
    apply_label: str = "Run"
    restore_scripts_from: str | None = None


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
) -> FixAdvice | None:
    failed = [s for s in scores if not s.passed]
    if not failed:
        return None
    trigger = next((s for s in failed if s.scorer == "skill_trigger"), None)
    completion = next((s for s in failed if s.scorer == "task_completion"), None)
    rubric = next((s for s in failed if s.scorer == "rubric"), None)
    prompts = list(sibling_prompts or [task.prompt])

    if trigger and task.expect_skill and (trigger.actual or "none") == "none":
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
                "Tighten `description:` so it lists when to use the skill — and implicitly excludes everything else."
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
            change="Make this skill’s description more specific, using keywords from the failed requests.",
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
    trigger_misses = [
        t
        for t in failed
        if t.expect_skill
        and any(s.scorer == "skill_trigger" and not s.passed for s in t.scores)
        and (t.selected_skill in {None, "none"} or t.selected_skill is None)
    ]
    if trigger_misses:
        prompts = [t.prompt for t in trigger_misses]
        description = synthesize_trigger_description(skill, prompts, reference)
        first = trigger_misses[0]
        return _trigger_fix(skill, first.prompt, description, reference)
    return failed[0].advice


def synthesize_trigger_description(
    skill: Skill,
    failed_prompts: list[str],
    reference: Skill | None = None,
) -> str:
    """Build a description that would fire on the failed prompts — not a remix of the bad one."""
    prompts = [p for p in failed_prompts if p.strip()]
    blob = " ".join(prompts).lower()
    pdf_shaped = "pdf" in blob or bool(re.search(r"\.pdf\b", blob))
    if pdf_shaped and reference and "pdf" in reference.description.lower():
        desc = _retarget_description(reference.description, skill.name)
    else:
        desc = _description_from_prompts(skill.name, prompts)
    desc = _clip(desc, 1024)
    probe = Skill(path=skill.path, name=skill.name, description=desc, body=skill.body)
    for prompt in prompts:
        picked = select_skill_from_descriptions(prompt, [probe])
        if picked != skill.name:
            desc = _force_keywords(desc, prompt)
            probe.description = desc
    return _clip(desc, 1024)


_VAGUE_TOKENS = {
    "answers",
    "anything",
    "asks",
    "assistance",
    "blah",
    "complete",
    "data",
    "does",
    "doing",
    "dummy",
    "everything",
    "extra",
    "foo",
    "general",
    "generic",
    "guidance",
    "handle",
    "handles",
    "help",
    "helper",
    "helping",
    "helps",
    "info",
    "information",
    "ipsum",
    "item",
    "items",
    "lorem",
    "need",
    "needed",
    "needs",
    "people",
    "person",
    "please",
    "random",
    "request",
    "requests",
    "skill",
    "skills",
    "someone",
    "something",
    "stuff",
    "support",
    "task",
    "tasks",
    "their",
    "they",
    "thing",
    "things",
    "useful",
    "various",
    "want",
    "wanted",
    "whatever",
    "work",
    "working",
    "works",
}

_THIN_HINT = (
    "That description is too thin to generate checks. Write what the skill does "
    "and when to use it, with keywords from real requests (file types, verbs, product names)."
)
_VAGUE_HINT = (
    "That description is too vague to generate useful checks. Name the work, the objects "
    "(file types, products), and when to trigger — not filler like “helps with things.”"
)
_WHEN_HINT = (
    "Add a “Use when …” clause so the agent knows when to trigger the skill. Example:\n\n"
    "description: Extract text and merge PDFs. Use when the user mentions a .pdf file, invoices, or combining documents."
)
_PADDED_TOKEN = re.compile(r"^(.)\1{3,}$")
_WHEN_SPLIT = re.compile(
    r"\b(use when|whenever|when the user|if the user|use this skill)\b",
    re.IGNORECASE,
)


def description_is_usable(description: str, *, require_when: bool = True) -> tuple[bool, str]:
    text = " ".join((description or "").split())
    if len(text) < 60:
        return False, _THIN_HINT
    compact = re.sub(r"\s+", "", text)
    if re.search(r"(.)\1{9,}", compact):
        return False, _VAGUE_HINT
    tokens = tokenize(text)
    if len(tokens) < 8:
        return (
            False,
            "Add more concrete words to the description — what it does, and the phrases a user would type.",
        )
    content = _content_tokens(text)
    if len(content) < 4:
        return False, _VAGUE_HINT
    if require_when:
        has_when = bool(_WHEN_SPLIT.search(text))
        if not has_when:
            return False, _WHEN_HINT
        parts = _WHEN_SPLIT.split(text)
        tail = parts[-1] if len(parts) > 1 else ""
        if len(_content_tokens(tail)) < 2:
            return False, _VAGUE_HINT
    return True, ""


def _content_tokens(text: str) -> set[str]:
    return {
        token
        for token in tokenize(text)
        if token not in _VAGUE_TOKENS and len(token) > 2 and not _PADDED_TOKEN.match(token)
    }


def rewrite_skill_description(skill_md: Path, new_description: str) -> None:
    text = skill_md.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("SKILL.md has no YAML frontmatter to patch.")
    parsed = yaml.safe_load(match.group(1)) or {}
    if not isinstance(parsed, dict):
        raise ValueError("SKILL.md frontmatter is not a mapping.")
    parsed["description"] = new_description
    body = text[match.end() :]
    dumped = yaml.safe_dump(parsed, sort_keys=False, allow_unicode=True)
    skill_md.write_text(f"---\n{dumped}---\n{body}", encoding="utf-8")


def description_from_paste(markdown: str) -> str:
    text = (markdown or "").strip()
    if text and not text.endswith("\n"):
        text += "\n"
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("Paste a SKILL.md frontmatter block with a description.")
    parsed = yaml.safe_load(match.group(1)) or {}
    if not isinstance(parsed, dict):
        raise ValueError("Paste a SKILL.md frontmatter block with a description.")
    desc = str(parsed.get("description") or "").strip()
    if not desc:
        raise ValueError("The pasted frontmatter has no description.")
    return desc


def apply_description_fix(
    *,
    source: Path,
    dest_root: Path,
    new_description: str,
    restore_scripts_from: Path | None = None,
) -> Path:
    """Copy the skill to a working folder, write the corrected description, keep the same name."""
    dest = dest_root / source.name
    source = source.resolve()
    dest_root.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.resolve() == source:
        rewrite_skill_description(dest / "SKILL.md", new_description)
    else:
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest)
        rewrite_skill_description(dest / "SKILL.md", new_description)
    if restore_scripts_from and restore_scripts_from.is_dir():
        src_scripts = restore_scripts_from / "scripts"
        if src_scripts.is_dir():
            dest_scripts = dest / "scripts"
            if dest_scripts.exists():
                shutil.rmtree(dest_scripts)
            shutil.copytree(src_scripts, dest_scripts)
    return dest


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


def _retarget_description(source: str, name: str) -> str:
    del name
    return " ".join(source.split())


def _description_from_prompts(name: str, prompts: list[str]) -> str:
    """Build a description from failed prompts — not from eval check text verbatim."""
    verbs = []
    for verb in (
        "extract",
        "merge",
        "combine",
        "create",
        "rotate",
        "split",
        "dump",
        "fill",
        "summarize",
        "write",
    ):
        if any(verb in p.lower() for p in prompts) and verb not in verbs:
            verbs.append(verb)
    nouns = []
    for prompt in prompts:
        for token in sorted(tokenize(prompt)):
            if token in _MEAL_NOISE:
                continue
            if token.endswith("pdf") or token in {
                "pdf",
                "invoice",
                "invoices",
                "document",
                "documents",
                "deck",
                "decks",
            }:
                if token not in nouns:
                    nouns.append(token)
    what = ", ".join(verbs[:4]) or "complete the requested files"
    objects = ", ".join(nouns[:6]) or name.replace("-", " ")
    when = _when_clause(prompts)
    # Never paste full eval prompts into the suggested description.
    when = re.sub(r"\s+", " ", when).strip()
    if len(when) > 120:
        when = when[:120].rsplit(" ", 1)[0] + "…"
    return f"{what.capitalize()} {objects}. Use this skill when the user works with {objects}."


def _when_clause(prompts: list[str]) -> str:
    bits = []
    for prompt in prompts[:3]:
        cleaned = re.sub(r"\s+", " ", prompt).strip().rstrip(".")
        if len(cleaned) > 90:
            cleaned = cleaned[:90].rsplit(" ", 1)[0]
        if cleaned and cleaned.lower() not in {b.lower() for b in bits}:
            bits.append(cleaned[0].lower() + cleaned[1:] if cleaned else cleaned)
    if not bits:
        return "do the work described in their request"
    if len(bits) == 1:
        return bits[0]
    return ", or ".join(bits)


def _force_keywords(desc: str, prompt: str) -> str:
    extra = []
    for token in ("pdf", "extract", "merge", "rotate", "invoice"):
        if token in prompt.lower() and token not in desc.lower():
            extra.append(token)
    if not extra:
        return desc
    suffix = " Use when the user mentions " + ", ".join(extra) + "."
    return _clip(desc.rstrip(".") + "." + suffix, 1024)


def _tighten_description(skill: Skill, negative_prompt: str) -> str:
    del negative_prompt
    base = skill.description.strip()
    clause = " Do not use this skill for unrelated questions (weather, unit tests, general chat)."
    if clause.strip().lower() in base.lower():
        return base
    return _clip(base + clause, 1024)


def _frontmatter(name: str, description: str) -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n"


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rsplit(" ", 1)[0] + "..."


def _is_script_failure(returncode: int | None, stderr: str) -> bool:
    if returncode in (None, 0):
        return False
    text = (stderr or "").lstrip()
    if text.startswith("{") or text.startswith("["):
        return False
    return True


def _command_fail_snippet(stderr: str) -> str:
    lines = [line.strip() for line in (stderr or "").splitlines() if line.strip()]
    for line in reversed(lines):
        lower = line.lower()
        if lower.startswith("usage:"):
            continue
        if "error:" in lower:
            return line.split("error:", 1)[-1].strip()
        if "unrecognized" in lower:
            return line
    return (lines[-1] if lines else "")[:200]


def _task_output_path(task: TaskSpec) -> str | None:
    for spec in task.scorers:
        for item in spec.files:
            path = str(item.path or "").strip()
            if path:
                return path
    return None


def _suggested_steps(task: TaskSpec, missing: str, *, write_to: str | None = None) -> str:
    out = write_to or _task_output_path(task) or "output/result.txt"
    return (
        f"## {task.id}\n\n"
        f"When the user asks: {task.prompt}\n\n"
        f"1. Use this skill’s scripts if they exist (`scripts/`).\n"
        f"2. Write the result to `{out}`.\n"
        f"3. Do not finish until that file exists. ({missing})\n"
    )
