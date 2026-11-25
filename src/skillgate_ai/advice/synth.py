from __future__ import annotations

import re

from skillgate_ai.advice.model import _MEAL_NOISE
from skillgate_ai.advice.text import _clip
from skillgate_ai.harness import select_skill_from_descriptions, tokenize
from skillgate_ai.ingest import Skill


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
            if token.endswith("pdf") or token in {  # noqa: SIM102
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
    bits: list[str] = []
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
