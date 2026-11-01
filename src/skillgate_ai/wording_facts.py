"""Compile explicit skill wording rules into deterministic text checks."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from skillgate_ai.judge_spec import JudgeQuestion, JudgeSpec

_SKILL_MARK = "--- SKILL.md ---"
_LABEL = re.compile(
    r"(?im)^[ \t]*(?:[-*][ \t]*)?"
    r"(?P<kind>banned|forbidden|required)"
    r"(?:[ \t]+(?:done[- ]words?|phrases?|wording|words?|customer"
    r"(?:[ \t]+(?:copy|reply|wording))?))?"
    r"[ \t]*:[ \t]*(?P<body>.+)$"
)
_DONE_LINE = re.compile(r"(?im)done[- ]words?\b[^\n:]*:[ \t]*(.+)$")
_BAN_CLAIM = re.compile(
    r"(?i)(?:nowhere|never|do[ \t]+not|must[ \t]+not|don['’]t)"
    r"(?:[^\n.\"“]{0,80})"
    r"(?:say|use|write|claim|tell)"
)
_MUST_QUOTED = re.compile(
    r"(?i)(?:must|always)[ \t]+(?:say|include|write|contain|use)"
    r"[ \t]+[\"“]([^\"”]{2,80})[\"”]"
)
_QUOTED = re.compile(r"[\"“]([^\"”]{2,80})[\"”]")
_LIST_CUT = re.compile(r"\.(?:\s|$)|[ \t]+(?:unless|when|if)[ \t]+", re.IGNORECASE)
_SPLIT = re.compile(r"\s*(?:,|;|\bor\b|\band\b)\s*", re.IGNORECASE)
_NEG = re.compile(
    r"(?i)\b(?:not|never|no|without|hasn['’]t|haven['’]t|didn['’]t|"
    r"did[ \t]+not|has[ \t]+not|have[ \t]+not|wasn['’]t|isn['’]t|not[ \t]+been)\b"
)
_COVER = re.compile(
    r"(?i)\breply\b|wording|banned|forbidden|done[- ]word|pending refund done|"
    r"already been issued|must include|required pending|never say|"
    r"nowhere in the reply|customer (?:reply|copy)"
)
_DONE_WORDS = frozenset(
    {
        "submitted",
        "issued",
        "processed",
        "completed",
        "refunded",
        "started",
        "sent",
        "initiated",
    }
)
_DONE_PHRASES = ("on its way", "on the way")
_HONEST_NEGATION = re.compile(
    r"(?i)(?:not[ \t]+(?:been[ \t]+)?submitted[ \t]+yet|"
    r"not[ \t]+yet[ \t]+submitted|"
    r"\bnot[ \t]+yet\b|"
    r"\bnot[ \t]+done\b|"
    r"has[ \t]+not[ \t]+gone[ \t]+through|"
    r"not[ \t]+been[ \t]+issued)"
)
_STOP = frozenset(
    {
        "the",
        "a",
        "an",
        "to",
        "for",
        "in",
        "of",
        "and",
        "or",
        "customer",
        "reply",
        "copy",
        "words",
        "word",
        "phrase",
        "phrases",
    }
)


@dataclass(frozen=True)
class WordingRule:
    kind: Literal["banned", "required"]
    phrase: str


def compile_wording_rules(
    skill_text: str | None,
    spec: JudgeSpec | None = None,
) -> list[WordingRule]:
    """Explicit banned/required phrases from the skill (and extra asks)."""
    blobs = [_skill_body(skill_text)]
    if spec is not None:
        blobs.extend(question.ask for question in spec.extras)
    found: list[WordingRule] = []
    seen: set[tuple[str, str]] = set()
    for blob in blobs:
        for rule in _rules_from_text(blob):
            key = (rule.kind, rule.phrase.lower())
            if key in seen:
                continue
            seen.add(key)
            found.append(rule)
    return found


def wording_ask(rules: Sequence[WordingRule]) -> str:
    """One Yes/No prompt listing the compiled phrases."""
    return _wording_ask(rules)


def attach_wording_questions(spec: JudgeSpec, skill_text: str | None) -> JudgeSpec:
    """Add one extra when the skill has wording rules and no covering check."""
    rules = compile_wording_rules(skill_text, spec)
    if not rules:
        return spec
    if any(_covers_wording(question.ask) for question in spec.extras):
        return spec
    extra = JudgeQuestion(
        id="wording",
        type="predicate",
        ask=_wording_ask(rules),
        on_fail="block",
    )
    return spec.with_questions([*spec.questions, extra])


def resolve_wording_facts(
    spec: JudgeSpec,
    outputs: Sequence[Mapping[str, Any]] | str | None,
    skill_text: str | None,
    *,
    succeeded: bool = False,
    hedge: bool = False,
) -> dict[str, Any]:
    """Fail extras that the skill's wording rules can decide from the text."""
    rules = compile_wording_rules(skill_text, spec)
    if not rules:
        return {}
    covering = [question for question in spec.extras if _covers_wording(question.ask)]
    if not covering and any(question.id == "wording" for question in spec.extras):
        covering = [question for question in spec.extras if question.id == "wording"]
    if not covering:
        return {}
    from skillgate_ai.span_facts import _reply_text

    reply = _reply_text(outputs)
    if outputs is not None and not reply:
        return {
            question.id: {
                "probability": 0.0,
                "source": "text",
                "reason": "reply.txt missing",
            }
            for question in covering
        }
    texts = _agent_texts(outputs)
    if not texts:
        return {}
    _ = hedge
    violated = _violations(rules, texts, succeeded=succeeded)
    yes = not violated
    if yes:
        reason = "The reply follows the skill's wording."
    else:
        phrases = ", ".join(f'"{rule.phrase}"' for rule in violated)
        reason = (
            f"The reply uses banned wording: {phrases} (the agent's wording)."
            if phrases
            else "The reply uses banned wording (the agent's wording)."
        )
    facts: dict[str, Any] = {
        question.id: {
            "probability": 1.0 if yes else 0.0,
            "source": "text",
            "reason": reason,
        }
        for question in covering
    }
    if yes and _HONEST_NEGATION.search(reply or ""):
        for fact in facts.values():
            fact["honest_negation"] = True
    return facts


def _skill_body(text: str | None) -> str:
    raw = str(text or "")
    if _SKILL_MARK in raw:
        raw = raw.split(_SKILL_MARK, 1)[1]
    return raw


def _rules_from_text(text: str) -> list[WordingRule]:
    rules: list[WordingRule] = []
    for match in _LABEL.finditer(text or ""):
        kind: Literal["banned", "required"] = (
            "required" if match.group("kind").lower() == "required" else "banned"
        )
        rules.extend(_phrases(kind, match.group("body")))
    for match in _DONE_LINE.finditer(text or ""):
        rules.extend(_phrases("banned", match.group(1)))
    for match in _BAN_CLAIM.finditer(text or ""):
        tail = _LIST_CUT.split(text[match.start() :], maxsplit=1)[0]
        rules.extend(_quoted_only("banned", tail))
    for match in _MUST_QUOTED.finditer(text or ""):
        rules.extend(_phrases("required", match.group(1)))
    return rules


def _phrases(kind: Literal["banned", "required"], blob: str) -> list[WordingRule]:
    head = _LIST_CUT.split((blob or "").strip(), maxsplit=1)[0]
    quoted = _quoted_only(kind, head)
    if quoted:
        return quoted
    items: list[WordingRule] = []
    for part in _SPLIT.split(head):
        phrase = _clean_phrase(part)
        if not _usable(phrase):
            continue
        items.append(WordingRule(kind=kind, phrase=phrase))
    return items


def _quoted_only(kind: Literal["banned", "required"], blob: str) -> list[WordingRule]:
    items: list[WordingRule] = []
    for match in _QUOTED.finditer(blob or ""):
        phrase = _clean_phrase(match.group(1))
        if not _usable(phrase):
            continue
        items.append(WordingRule(kind=kind, phrase=phrase))
    return items


def _clean_phrase(raw: str) -> str:
    return raw.strip().strip("\"“”'`").strip(" .;:")


def _usable(phrase: str) -> bool:
    token = phrase.strip()
    if len(token) < 3:
        return False
    if token.lower() in _STOP:
        return False
    return len(token.split()) <= 12


def _covers_wording(ask: str) -> bool:
    return bool(_COVER.search(ask or ""))


def _wording_ask(rules: Sequence[WordingRule]) -> str:
    banned = [rule.phrase for rule in rules if rule.kind == "banned"]
    required = [rule.phrase for rule in rules if rule.kind == "required"]
    bits: list[str] = []
    if banned:
        bits.append("do not use " + ", ".join(banned))
    if required:
        bits.append("must include " + ", ".join(required))
    return "The reply follows the skill's wording: " + "; ".join(bits) + "."


def _agent_texts(outputs: Sequence[Mapping[str, Any]] | str | None) -> list[str]:
    from skillgate_ai.span_facts import _reply_text

    reply = _reply_text(outputs)
    if reply.strip():
        return [reply]
    if isinstance(outputs, str) and outputs.strip():
        return [outputs]
    return []


def _violations(
    rules: Sequence[WordingRule],
    texts: Sequence[str],
    *,
    succeeded: bool,
) -> list[WordingRule]:
    blob = "\n".join(texts)
    hit: list[WordingRule] = []
    for rule in rules:
        if rule.kind == "required":
            if "pending" in rule.phrase.lower() and succeeded:
                continue
            if not _present(blob, rule.phrase):
                hit.append(rule)
            continue
        if _done_like(rule.phrase) and succeeded:
            continue
        if _asserted(blob, rule.phrase):
            hit.append(rule)
    return hit


def _done_like(phrase: str) -> bool:
    folded = _fold_apos(phrase).lower()
    if any(item in folded for item in _DONE_PHRASES):
        return True
    tokens = {part.lower() for part in re.findall(r"[A-Za-z']+", folded)}
    return bool(tokens & _DONE_WORDS)


def _present(text: str, phrase: str) -> bool:
    return bool(_hits(text, phrase))


def _asserted(text: str, phrase: str) -> bool:
    for start, end in _hits(text, phrase):
        if _quoted(text, start, end) or _negated(text, start):
            continue
        return True
    return False


def _fold_apos(text: str) -> str:
    return text.replace("’", "'").replace("‘", "'")


def _hits(text: str, phrase: str) -> list[tuple[int, int]]:
    hay = _fold_apos(text)
    token = _fold_apos(phrase.strip())
    if not token:
        return []
    if re.search(r"\s|'", token):
        pat = re.compile(re.escape(token), re.IGNORECASE)
    else:
        pat = re.compile(
            rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])",
            re.IGNORECASE,
        )
    return [(match.start(), match.end()) for match in pat.finditer(hay)]


def _quoted(text: str, start: int, end: int) -> bool:
    for left, right in _quote_spans(text):
        if left < start and end <= right:
            return True
    return False


def _quote_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    i = 0
    opens = "\"“"
    closes = "\"”"
    while i < len(text):
        if text[i] in opens:
            j = i + 1
            while j < len(text) and text[j] not in closes:
                j += 1
            if j < len(text):
                spans.append((i, j + 1))
                i = j + 1
                continue
        i += 1
    return spans


def _negated(text: str, start: int) -> bool:
    return bool(_NEG.search(text[max(0, start - 48) : start]))
