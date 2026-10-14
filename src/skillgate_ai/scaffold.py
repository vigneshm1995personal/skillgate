"""Create a local skill pack and scaffold trigger-only evals. No LLM."""

from __future__ import annotations

import shutil
from pathlib import Path

from skillgate_ai.case_pack import CasePack, PackCase, load_case_pack, save_case_pack
from skillgate_ai.errors import IngestError
from skillgate_ai.ingest import NAME_RE, ingest_skill
from skillgate_ai.skill_md import default_body, default_description, write_skill_md

UNRELATED_PROMPT = (
    "Write a pytest for a FastAPI /health endpoint. Do not touch any PDFs."
)


def create_pack(
    parent: str | Path,
    name: str,
    *,
    description: str | None = None,
) -> Path:
    """mkdir ``parent/name`` and write a stub SKILL.md. Name equals folder basename."""
    slug = (name or "").strip()
    if not NAME_RE.match(slug) or not (1 <= len(slug) <= 64):
        raise IngestError(
            f"name {slug!r} is invalid",
            hint="Use lowercase letters, numbers, and single hyphens; no leading/trailing/double hyphens.",
        )
    dest = Path(parent).expanduser().resolve() / slug
    if dest.exists():
        raise IngestError(
            f"Folder already exists: {dest}",
            hint="Pick a new name or open the existing pack.",
        )
    dest.mkdir(parents=True)
    try:
        (dest / "evals" / "fixtures").mkdir(parents=True, exist_ok=True)
        write_skill_md(
            dest,
            name=slug,
            description=(description or default_description(slug)).strip(),
            body=default_body(slug),
        )
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    return dest


def scaffold_trigger_cases(pack: str | Path) -> CasePack:
    """Two pinned cases: one should-trigger (no golden) and one negative."""
    root = Path(pack).expanduser().resolve()
    skill = ingest_skill(root, strict=False)
    prompt = _prompt_from_description(skill.name, skill.description)
    cases = CasePack(
        schema_version=1,
        skill=skill.name,
        cases=[
            PackCase(
                id="should-trigger-1",
                status="pinned",
                prompt=prompt,
                should_trigger=True,
            ),
            PackCase(
                id="no-trigger-unrelated",
                status="pinned",
                prompt=UNRELATED_PROMPT,
                should_trigger=False,
            ),
        ],
    )
    save_case_pack(root, cases)
    return cases


def clone_pdf_layout(dest: str | Path, *, source: str | Path) -> Path:
    """Copy a pdf demo pack, then rewrite ``name`` / ``skill`` to dest basename."""
    src = Path(source).expanduser().resolve()
    dst = Path(dest).expanduser().resolve()
    if not src.is_dir() or not (src / "SKILL.md").is_file():
        raise IngestError(
            f"PDF demo pack not found: {src}",
            hint="Pass a folder with skills/sample-skill (or skills/pdf), or scaffold trigger-only cases instead.",
        )
    loaded = ingest_skill(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".skillgate", "*.jsonl"),
    )
    write_skill_md(
        dst,
        name=dst.name,
        description=loaded.description,
        body=loaded.body,
        license=loaded.license,
        compatibility=loaded.compatibility,
        allowed_tools=loaded.allowed_tools,
        metadata=dict(loaded.metadata) or None,
    )
    pack = load_case_pack(dst)
    if pack is not None:
        rewritten = CasePack(
            schema_version=1,
            skill=dst.name,
            cases=pack.cases,
            budgets=pack.budgets,
        )
        save_case_pack(dst, rewritten)
    return dst


def _prompt_from_description(name: str, description: str) -> str:
    clipped = " ".join((description or "").split())[:220]
    return f"Please run {name}: {clipped}"
