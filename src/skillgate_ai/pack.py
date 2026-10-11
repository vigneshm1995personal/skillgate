"""Skill pack = the skill directory (agentskills spec).

A skill is a folder with SKILL.md plus optional scripts/, references/, assets/,
evals/, and any other files. Progressive disclosure: metadata → SKILL.md body →
resources on demand.

Skill Gate does **not** invent a parallel Artifact blob store. Eval fixtures live
in the skill tree (prefer ``evals/fixtures/`` or ``assets/``). Checks reference
those files with relative paths from the skill root — the same rule as
agentskills file refs.
"""

from __future__ import annotations

import fnmatch
import hashlib
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from skillgate_ai.demo_files import write_pdf

FIXTURE_DIR = "evals/fixtures"
GOLDEN_DIR = "evals/goldens"
ASSET_DIR = "assets"
DEFAULT_FIXTURE_GLOB = f"{FIXTURE_DIR}/*"
CASE_SUFFIXES = {".md"}
_SKIP_DIR_NAMES = {".git", "__pycache__", ".skillgate", "node_modules"}
_SKIP_FILE_NAMES = {".ds_store", "thumbs.db"}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
# Underscore/hyphen count as separators so receipt_image.txt is a photo stand-in.
_UNSYNTHESIZABLE = re.compile(
    r"(?:^|[^a-z0-9])(photo|photos|image|images|png|jpe?g|screenshot|scan|scans)(?:[^a-z0-9]|$)",
    re.IGNORECASE,
)
_PDF_MAGIC = b"%PDF"
_IMAGE_MAGICS = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
)


class CannotSynthesizeFixture(ValueError):
    """Photo/scan samples cannot be faked; the check needs a real upload."""

    def __init__(self, message: str | None = None):
        super().__init__(
            message
            or "This check needs a real photo or scan — upload one instead of a generated sample."
        )


def list_pack_files(skill_path: str | Path) -> list[dict[str, Any]]:
    """Relative paths from the skill root (SKILL.md itself is omitted)."""
    root = Path(skill_path).expanduser().resolve()
    if not root.is_dir():
        return []
    found: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = _rel_to_skill(root, path)
        if rel is None:
            continue
        if rel == "SKILL.md" or rel.lower() in _SKIP_FILE_NAMES:
            continue
        if any(part.lower() in _SKIP_DIR_NAMES for part in Path(rel).parts):
            continue
        found.append({"path": rel, "bytes": path.stat().st_size})
    return found


def fixture_files(skill_path: str | Path) -> list[dict[str, Any]]:
    """Files agentskills would treat as input resources: evals/, assets/."""
    out: list[dict[str, Any]] = []
    for item in list_pack_files(skill_path):
        path = item["path"]
        if path.startswith(("evals/", f"{ASSET_DIR}/")):
            out.append(item)
    return out


def relevant_eval_fixtures(
    skill_path: str | Path,
    glob_pat: str | None = None,
) -> list[dict[str, Any]]:
    """Dataset files under the pack (default evals/fixtures/*).

    Skips standup/prompt ``.md`` cases and unauthentic PDF/image stand-ins.
    """
    root = Path(skill_path).expanduser()
    if not root.is_dir():
        return []
    pattern = (glob_pat or DEFAULT_FIXTURE_GLOB).replace("\\", "/").strip()
    if not pattern:
        pattern = DEFAULT_FIXTURE_GLOB
    found: list[dict[str, Any]] = []
    for item in list_pack_files(root):
        rel = str(item["path"]).replace("\\", "/")
        if rel.startswith(f"{GOLDEN_DIR}/") or rel == GOLDEN_DIR:
            continue
        if not _glob_match(rel, pattern):
            continue
        suffix = Path(rel).suffix.lower()
        if suffix in CASE_SUFFIXES:
            continue
        path = root / rel
        if not path.is_file():
            continue
        data = path.read_bytes()
        if suffix in IMAGE_SUFFIXES or suffix == ".pdf":
            if not is_authentic_fixture_bytes(rel, data):
                continue
        elif len(data) < 1:
            continue
        found.append({"src": rel, "dest": Path(rel).name, "bytes": len(data)})
    return found


def _glob_match(rel: str, pattern: str) -> bool:
    if fnmatch.fnmatch(rel, pattern):
        return True
    name = Path(rel).name
    if fnmatch.fnmatch(name, pattern):
        return True
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return rel == prefix or rel.startswith(prefix + "/")
    return False


def skill_pack_hash(skill_path: str | Path | None) -> str:
    """Stable hash of the skill directory so fixtures version with the skill."""
    if not skill_path:
        return ""
    root = Path(skill_path)
    if root.is_file():
        return hashlib.sha256(root.read_bytes()).hexdigest()
    if not root.is_dir():
        return ""
    digest = hashlib.sha256()
    for item in list_pack_files(root):
        rel = item["path"]
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update((root / rel).read_bytes())
        digest.update(b"\0")
    skill_md = root / "SKILL.md"
    if skill_md.is_file():
        digest.update(b"SKILL.md\0")
        digest.update(skill_md.read_bytes())
    return digest.hexdigest()


def safe_relpath(rel: str, *, default_dir: str = FIXTURE_DIR) -> str:
    """Keep a path inside the skill folder. Default to evals/fixtures/<name>."""
    cleaned = (rel or "").replace("\\", "/").strip()
    cleaned = cleaned.lstrip("/")
    parts = [p for p in cleaned.split("/") if p and p not in {".", ""}]
    if any(p == ".." for p in parts):
        raise ValueError("Path must stay inside the skill folder.")
    if not parts:
        raise ValueError("A file path is required.")
    if len(parts) == 1:
        return f"{default_dir}/{_safe_filename(parts[0])}"
    parts[-1] = _safe_filename(parts[-1])
    return "/".join(parts)


def write_pack_file(
    skill_path: str | Path,
    *,
    rel: str,
    content: str | bytes,
) -> dict[str, str]:
    """Write bytes into the skill directory. Returns src (skill-relative) + dest."""
    root = Path(skill_path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Skill folder not found.")
    relative = safe_relpath(rel)
    dest_path = (root / relative).resolve()
    dest_path.relative_to(root)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8") if isinstance(content, str) else content
    dest_path.write_bytes(data)
    return {"src": relative, "dest": Path(relative).name, "path": relative}


def implies_photo_scan(*parts: object) -> bool:
    """True when skill/check/path/content is a photo, scan, or image input."""
    blob = " ".join(str(part or "") for part in parts)
    return bool(_UNSYNTHESIZABLE.search(blob))


def as_fixture_bytes(content: str | bytes) -> bytes:
    return content.encode("utf-8") if isinstance(content, str) else bytes(content)


def is_authentic_fixture_bytes(dest: str, content: str | bytes) -> bool:
    """Reject ASCII stand-ins for PDF/image binaries (e.g. 33-byte fake .pdf)."""
    suffix = Path(dest).suffix.lower()
    data = as_fixture_bytes(content)
    if suffix == ".pdf":
        return data.startswith(_PDF_MAGIC) and len(data) >= 100
    if suffix in IMAGE_SUFFIXES:
        if len(data) < 200:
            return False
        if any(data.startswith(magic) for magic in _IMAGE_MAGICS):
            return True
        return data[8:12] == b"WEBP" if data.startswith(b"RIFF") else False
    return True


def cannot_synthesize_sample(*, dest: str = "", prompt: str = "", description: str = "") -> bool:
    """True for photo/scan inputs we must not fake as a placeholder image."""
    if implies_photo_scan(prompt, description, dest):
        return True
    name = dest or implied_fixture_name(f"{prompt} {description}")
    return Path(name).suffix.lower() in IMAGE_SUFFIXES


def generate_sample_bytes(*, dest: str, prompt: str = "") -> bytes:
    """Generic sample from dest extension + prompt words. No skill-name switch."""
    name = Path(dest).name or "sample.txt"
    suffix = Path(name).suffix.lower()
    stem = Path(name).stem.replace("-", " ") or "sample"
    hint = " ".join((prompt or stem).split())[:180] or "alpha / beta / gamma"
    if suffix in IMAGE_SUFFIXES or cannot_synthesize_sample(dest=dest, prompt=prompt):
        raise CannotSynthesizeFixture()
    if suffix == ".pdf":
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / name
            write_pdf(path, f"Sample input: {hint[:80]}")
            return path.read_bytes()
    if suffix == ".json":
        body = f'{{\n  "source": {stem!r},\n  "note": {hint!r},\n  "total": "12.40"\n}}\n'
        return body.encode("utf-8")
    if suffix == ".csv":
        return f"item,amount\n{stem},12.40\nnote,{hint}\n".encode("utf-8")
    text = f"Sample input for this check.\nItem: {stem}\nNote: {hint}\nTotal: 12.40\n"
    return text.encode("utf-8")


def write_sample_fixture(
    skill_path: str | Path,
    *,
    dest: str | None = None,
    prompt: str = "",
    description: str = "",
) -> dict[str, str]:
    """Create a synthetic fixture under evals/fixtures/. Never invent a photo/scan."""
    if cannot_synthesize_sample(dest=dest or "", prompt=prompt, description=description):
        raise CannotSynthesizeFixture()
    name = dest or implied_fixture_name(f"{prompt} {description}")
    if "/" in name:
        relative = safe_relpath(name)
    else:
        relative = safe_relpath(f"{FIXTURE_DIR}/{name}")
    payload = generate_sample_bytes(dest=relative, prompt=prompt or description)
    return write_pack_file(skill_path, rel=relative, content=payload)


def copy_into_pack(
    skill_path: str | Path,
    *,
    src: str | Path,
    dest_name: str | None = None,
) -> dict[str, str]:
    """Copy an existing file into evals/fixtures/ (promote / attach)."""
    source = Path(src)
    if not source.is_file():
        raise FileNotFoundError(str(src))
    name = Path(dest_name or source.name).name
    return write_pack_file(skill_path, rel=f"{FIXTURE_DIR}/{name}", content=source.read_bytes())


def is_pack_relative(src: str) -> bool:
    """True when src is a skill-root relative path (never absolute, never ..)."""
    cleaned = (src or "").replace("\\", "/").strip()
    if not cleaned:
        return False
    if Path(cleaned).is_absolute() or cleaned.startswith("/"):
        return False
    parts = [p for p in cleaned.split("/") if p]
    return bool(parts) and not any(p == ".." for p in parts)


def fixture_src_for(src: str, dest: str = "") -> str:
    """Pack-relative evals/fixtures/<name> for a check file that must be rewritten."""
    name = Path(dest or src).name or "sample.bin"
    return f"{FIXTURE_DIR}/{_safe_filename(name)}"


def promote_file_into_pack(
    skill_path: str | Path,
    *,
    src: str,
    dest: str = "",
    root: Path | None = None,
) -> dict[str, str]:
    """Copy or rewrite so files[].src is always relative to the skill pack root."""
    skill_root = Path(skill_path).expanduser().resolve()
    dest_name = Path(dest or src).name or "sample.bin"
    dest_name = _safe_filename(dest_name)
    rewritten = {"src": fixture_src_for(src, dest_name), "dest": dest_name}
    if not (src or "").strip():
        return rewritten
    resolved = resolve_input_file(src, skill_root=skill_root, root=root)
    if resolved is None or not resolved.is_file():
        return rewritten
    try:
        rel = resolved.resolve().relative_to(skill_root).as_posix()
        return {"src": rel, "dest": dest_name or Path(rel).name}
    except ValueError:
        pass
    try:
        return copy_into_pack(skill_root, src=resolved, dest_name=dest_name)
    except (OSError, ValueError, FileNotFoundError):
        return rewritten


def persist_case_file(
    skill_path: str | Path,
    *,
    text: str,
    check_id: str = "case",
    index: int = 1,
) -> dict[str, str]:
    """Save prompt/facts into evals/fixtures/ so the pack stays the only copy."""
    body = (text or "").strip()
    if not body:
        raise ValueError("Nothing to save into the skill folder.")
    slug = _SAFE_NAME.sub("-", check_id).strip("-").lower() or "case"
    if slug.startswith("regression"):
        name = f"{slug}.md"
    elif re.search(r"\b(standup|yesterday|blockers?)\b", body, re.IGNORECASE):
        name = f"standup-case-{index}.md"
    else:
        name = f"{slug}.md" if slug not in {"should-trigger-1", "case"} else f"case-{index}.md"
    content = body if body.endswith("\n") else body + "\n"
    return write_pack_file(skill_path, rel=f"{FIXTURE_DIR}/{name}", content=content)


def implied_fixture_name(text: str) -> str:
    blob = text or ""
    if re.search(r"\bpdf\b", blob, re.IGNORECASE):
        return "sample.pdf"
    if re.search(r"\bcsv\b", blob, re.IGNORECASE):
        return "sample.csv"
    if re.search(r"\bjson\b", blob, re.IGNORECASE):
        return "sample.json"
    if re.search(
        r"\b(image|images|photo|photos|png|jpe?g|screenshot|scan|scans)\b", blob, re.IGNORECASE
    ):
        return "sample.png"
    return "sample.txt"


def resolve_input_file(
    rel: str,
    *,
    skill_root: Path | None = None,
    root: Path | None = None,
    suite_dir: Path | None = None,
) -> Path | None:
    """Skill-root first (agentskills), then project/suite (bundled pdf templates)."""
    raw = (rel or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if path.is_absolute() and path.is_file():
        return path
    if skill_root is not None:
        candidate = _path_under_skill(skill_root, raw)
        if candidate is not None and candidate.is_file():
            return candidate
    if root is None:
        return None
    suite = suite_dir or root / "evals"
    for base in (root, suite, suite.parent):
        candidate = (base / path).resolve()
        if candidate.is_file():
            return candidate
    fallback = (root / path).resolve()
    return fallback if fallback.is_file() else None


def file_copy_from_rel(rel: str) -> dict[str, str]:
    cleaned = rel.replace("\\", "/").lstrip("/")
    return {"src": cleaned, "dest": Path(cleaned).name}


TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
    ".py",
    ".js",
    ".ts",
    ".toml",
    ".xml",
    ".html",
    ".css",
    ".sh",
    ".svg",
}
PREVIEW_TEXT_LIMIT = 80_000


def browser_files(skill_path: str | Path) -> list[dict[str, Any]]:
    """Pack listing for the repository skill detail (includes SKILL.md)."""
    root = Path(skill_path).expanduser().resolve()
    items: list[dict[str, Any]] = []
    skill_md = root / "SKILL.md"
    if skill_md.is_file():
        items.append({"path": "SKILL.md", "bytes": skill_md.stat().st_size})
    items.extend(list_pack_files(root))
    return items


def copy_skill_pack(
    source: str | Path,
    dest: str | Path,
    *,
    include_goldens: bool = False,
) -> dict[str, Any]:
    """Recursive copy of a skill pack root, preserving the relative tree.

    Copies SKILL.md plus scripts/, assets/, references/, evals/fixtures/, and
    any other pack files. Skips VCS/cache dirs.

    Write into a temp directory next to dest, then swap. Never empty an
    existing install first — a failed copy leaves dest intact.

    ``skill_pack_hash`` (the recorded pass) includes ``evals/goldens/``. Import
    into this project, deploy bundle, and git publish pass ``include_goldens=True``
    so checks can score. Sandbox and editor installs keep goldens out so the
    agent cannot read expected answers.
    """
    src = Path(source).expanduser().resolve()
    dst = Path(dest).expanduser().resolve()
    if not src.is_dir():
        raise FileNotFoundError(str(src))
    if src == dst:
        raise ValueError("Install source and dest are the same folder.")
    parent = dst.parent
    parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:10]
    tmp = parent / f".{dst.name}.skillgate-tmp-{token}"
    old = parent / f".{dst.name}.skillgate-old-{token}"

    def ignore_keep(_directory: str, names: list[str]) -> set[str]:
        return {
            name
            for name in names
            if name.lower() in _SKIP_DIR_NAMES or name.lower() in _SKIP_FILE_NAMES
        }

    ignore = _pack_copy_ignore if not include_goldens else ignore_keep
    try:
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(src, tmp, ignore=ignore)
        if dst.exists():
            dst.rename(old)
            try:
                tmp.rename(dst)
            except OSError:
                if old.exists() and not dst.exists():
                    old.rename(dst)
                raise
            shutil.rmtree(old, ignore_errors=True)
        else:
            tmp.rename(dst)
    except BaseException:
        if tmp.exists() and tmp.resolve() != dst:
            shutil.rmtree(tmp, ignore_errors=True)
        raise
    return {
        "pack_path": str(src),
        "dest_path": str(dst),
        "file_count": len(browser_files(dst)),
    }


def pack_file_path(skill_path: str | Path, rel: str) -> Path:
    root = Path(skill_path).expanduser().resolve()
    candidate = _path_under_skill(root, rel)
    if candidate is None or not candidate.is_file():
        raise FileNotFoundError(rel)
    return candidate


def pack_preview(skill_path: str | Path, rel: str) -> dict[str, Any]:
    path = pack_file_path(skill_path, rel)
    data = path.read_bytes()
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        kind = "image"
    elif suffix == ".pdf":
        kind = "pdf"
    elif suffix in TEXT_SUFFIXES or b"\0" not in data[:1024]:
        kind = "text"
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            kind = "binary"
    else:
        kind = "binary"
    payload: dict[str, Any] = {
        "path": rel.replace("\\", "/").lstrip("/"),
        "bytes": len(data),
        "kind": kind,
        "content_type": _content_type(suffix, kind),
    }
    if kind == "text":
        payload["text"] = data.decode("utf-8", errors="replace")[:PREVIEW_TEXT_LIMIT]
    return payload


def _content_type(suffix: str, kind: str) -> str:
    mapping = {
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".json": "application/json",
        ".yaml": "text/yaml",
        ".yml": "text/yaml",
        ".csv": "text/csv",
        ".py": "text/x-python",
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }
    if suffix in mapping:
        return mapping[suffix]
    if kind == "text":
        return "text/plain"
    return "application/octet-stream"


def _path_under_skill(skill_root: Path, rel: str) -> Path | None:
    cleaned = rel.replace("\\", "/").strip().lstrip("/")
    parts = [p for p in cleaned.split("/") if p and p not in {".", ""}]
    if not parts or any(p == ".." for p in parts):
        return None
    candidate = (skill_root / "/".join(parts)).resolve()
    try:
        candidate.relative_to(skill_root.resolve())
    except ValueError:
        return None
    return candidate


def _pack_copy_ignore(directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    parent = Path(directory).name.lower()
    for name in names:
        key = name.lower()
        if key in _SKIP_DIR_NAMES or key in _SKIP_FILE_NAMES:
            ignored.add(name)
        if parent == "evals" and key == "goldens":
            ignored.add(name)
    return ignored


def _rel_to_skill(root: Path, path: Path) -> str | None:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def _safe_filename(name: str) -> str:
    cleaned = _SAFE_NAME.sub("-", name).strip(".-") or "sample.txt"
    if cleaned in {".", ".."}:
        return "sample.txt"
    return cleaned[:80]
