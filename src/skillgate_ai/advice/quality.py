from __future__ import annotations

import re

from skillgate_ai.harness import tokenize

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
    "description: Extract text and merge PDFs. Use when the user mentions a .pdf file, "
    "invoices, or combining documents."
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
            "Add more concrete words to the description — what it does, and the phrases "
            "a user would type.",
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
