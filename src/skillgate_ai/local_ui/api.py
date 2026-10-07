"""JSON handlers for the local UI. No auth, no Skill Gate account."""

from __future__ import annotations

import re
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from skillgate_ai import __version__
from skillgate_ai.advice import (
    description_from_paste,
    description_is_usable,
    rewrite_skill_description,
)
from skillgate_ai.case_pack import CasePack, dataset_view, save_case_pack
from skillgate_ai.config import ROOT_ENV_NAMES, get_llm_config, load_env
from skillgate_ai.demo_files import ensure_demo_pdfs
from skillgate_ai.errors import MissingLLMKeyError, SkillGateError
from skillgate_ai.gate import run_check
from skillgate_ai.history import load_history
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.live import create_control, drop_control, get_control
from skillgate_ai.pack import (
    CannotSynthesizeFixture,
    browser_files,
    copy_into_pack,
    write_sample_fixture,
)
from skillgate_ai.paths import is_skill_pack
from skillgate_ai.report import progress_to_dict, report_to_dict
from skillgate_ai.scaffold import clone_pdf_layout, create_pack, scaffold_trigger_cases
from skillgate_ai.skill_md import skill_to_dict, write_skill_md

ALLOWED_ENV = frozenset(ROOT_ENV_NAMES)
_TRAVERSAL = re.compile(r"(^|/)\.\.(/|$)")


@dataclass
class RunRecord:
    run_id: str
    progress: dict[str, Any] | None = None
    payload: dict[str, Any] | None = None
    done: bool = False
    error: str | None = None


@dataclass
class UiState:
    root: Path
    initial_pack: Path | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    active_run_id: str | None = None
    runs: dict[str, RunRecord] = field(default_factory=dict)


def error_body(exc: BaseException, *, status: int = 400) -> tuple[int, dict[str, Any]]:
    if isinstance(exc, SkillGateError):
        code = 409 if isinstance(exc, MissingLLMKeyError) else status
        return code, {"error": exc.message, "hint": exc.hint, "exit_code": exc.exit_code}
    if isinstance(exc, CannotSynthesizeFixture):
        return 400, {"error": str(exc), "hint": "Upload a real photo or scan instead."}
    return status, {"error": str(exc)}


def resolve_user_path(raw: str | None, state: UiState, *, must_exist: bool = False) -> Path:
    text = (raw or "").strip()
    if not text:
        raise SkillGateError("A pack path is required.")
    if _TRAVERSAL.search(text.replace("\\", "/")):
        raise SkillGateError(
            "Path must stay inside the workspace.",
            hint="Do not use .. in pack paths.",
        )
    supplied = Path(text).expanduser()
    asked_absolute = supplied.is_absolute()
    path = supplied if asked_absolute else (state.root / supplied)
    path = path.resolve()
    root = state.root.resolve()
    try:
        path.relative_to(root)
    except ValueError:
        # Relative paths (including symlinks under --root) must stay inside.
        # An explicit absolute path the user owns is allowed only if it exists.
        if not asked_absolute or not path.exists():
            raise SkillGateError(
                "Path must stay inside the workspace.",
                hint="Open an existing folder, or create a pack under --root.",
            ) from None
    if must_exist and not path.exists():
        raise SkillGateError("Path not found.")
    return path


def list_packs(state: UiState) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    skills_root = state.root / "skills"
    candidates: list[Path] = []
    if skills_root.is_dir():
        candidates.extend(sorted(p for p in skills_root.iterdir() if p.is_dir()))
    if is_skill_pack(state.root) or (state.root / "SKILL.md").is_file():
        candidates.insert(0, state.root)
    seen: set[Path] = set()
    for child in candidates:
        if not (child / "SKILL.md").is_file():
            continue
        resolved = child.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        name = child.name
        found.append(
            {
                "name": name,
                "path": str(resolved),
                "display_path": display_pack_label(resolved, state.root),
                "red_demo": name == "pdf-sabotaged",
                "green_demo": name == "pdf",
            }
        )
    return found


def display_pack_label(path: Path, root: Path) -> str:
    """Short relative label for the UI. Never an absolute machine path."""
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        return path.name
    text = str(rel).replace("\\", "/")
    if text in {"", "."}:
        return path.name
    return text


def pdf_demo_path(state: UiState) -> Path | None:
    candidate = state.root / "skills" / "pdf"
    if candidate.is_dir() and (candidate / "SKILL.md").is_file():
        return candidate.resolve()
    return None


def meta_payload(state: UiState) -> dict[str, Any]:
    load_env(state.root)
    cfg = get_llm_config()
    pack = None
    if state.initial_pack:
        pack = display_pack_label(state.initial_pack, state.root)
    pdf = pdf_demo_path(state)
    judge_pref = (cfg.judge_pref or "auto").strip().lower() or "auto"
    if judge_pref == "skip" or not cfg.openai_api_key:
        judge_provider = "skip"
    else:
        judge_provider = "openai"
    return {
        "version": __version__,
        "has_any_key": cfg.has_any_key,
        "has_openai_key": bool(cfg.openai_api_key),
        "judge_provider": judge_provider,
        "demo_default": True,
        "account": False,
        "pack": pack,
        "pdf_path": display_pack_label(pdf, state.root) if pdf else None,
    }


def pack_payload(state: UiState, raw_path: str | None) -> dict[str, Any]:
    path = resolve_user_path(raw_path, state, must_exist=True)
    skill = ingest_skill(path)
    usable, hint = description_is_usable(skill.description)
    dataset = None
    try:
        dataset = dataset_view(path)
    except SkillGateError as exc:
        dataset = {"error": exc.message, "hint": exc.hint}
    return {
        "path": str(path),
        "display_path": display_pack_label(path, state.root),
        "skill": skill_to_dict(skill),
        "description_usable": usable,
        "description_hint": hint,
        "files": browser_files(path),
        "dataset": dataset,
        "history_tail": load_history(path, limit=20),
        "is_seed_sabotaged": path.name == "pdf-sabotaged",
    }


def merge_env_file(path: Path, updates: dict[str, str]) -> None:
    existing = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    written: set[str] = set()
    out: list[str] = []
    for line in existing:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates:
            value = updates[key]
            if value:
                out.append(f"{key}={value}")
            written.add(key)
            continue
        out.append(line)
    for key, value in updates.items():
        if key not in written and value:
            out.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(out)
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def handle(
    state: UiState,
    *,
    method: str,
    path: str,
    query: str,
    body: dict[str, Any] | None,
) -> tuple[int, dict[str, Any] | bytes | None, str]:
    """Return (status, JSON-or-None, content_type). Static files handled in server."""
    qs = parse_qs(query or "")
    payload = body or {}
    try:
        return _dispatch(state, method=method, path=path, qs=qs, payload=payload)
    except (SkillGateError, CannotSynthesizeFixture, ValueError, FileNotFoundError, OSError) as exc:
        status, data = error_body(exc)
        return status, data, "application/json"


def _dispatch(
    state: UiState,
    *,
    method: str,
    path: str,
    qs: dict[str, list[str]],
    payload: dict[str, Any],
) -> tuple[int, dict[str, Any] | None, str]:
    if method == "GET" and path == "/api/meta":
        return 200, meta_payload(state), "application/json"
    if method == "GET" and path == "/api/packs":
        return 200, {"packs": list_packs(state)}, "application/json"
    if method == "POST" and path == "/api/packs":
        return _create_pack(state, payload)
    if method == "GET" and path == "/api/pack":
        raw = (qs.get("path") or [None])[0]
        return 200, pack_payload(state, raw), "application/json"
    if method == "PUT" and path == "/api/pack/skill-md":
        return _put_skill_md(state, payload)
    if method == "PUT" and path == "/api/pack/cases":
        return _put_cases(state, payload)
    if method == "POST" and path == "/api/pack/scaffold":
        pack = resolve_user_path(str(payload.get("path") or ""), state, must_exist=True)
        cases = scaffold_trigger_cases(pack)
        return (
            200,
            {"path": str(pack), "skill": cases.skill, "case_count": len(cases.cases)},
            "application/json",
        )
    if method == "POST" and path == "/api/pack/fixtures":
        return _post_fixtures(state, payload)
    if method == "PUT" and path == "/api/env":
        return _put_env(state, payload)
    if method == "POST" and path == "/api/check":
        return _start_check(state, payload)
    if method == "GET" and path.startswith("/api/runs/"):
        rest = path[len("/api/runs/") :]
        if rest.endswith("/kill"):
            return 405, {"error": "Use POST to kill a run."}, "application/json"
        return _get_run(state, rest)
    if method == "POST" and path.startswith("/api/runs/") and path.endswith("/kill"):
        run_id = path[len("/api/runs/") : -len("/kill")]
        return _kill_run(state, run_id)
    if method == "POST" and path == "/api/pack/apply-advice":
        return _apply_advice(state, payload)
    return 404, {"error": f"Unknown route {method} {path}"}, "application/json"


def _create_pack(state: UiState, payload: dict[str, Any]) -> tuple[int, dict[str, Any], str]:
    name = str(payload.get("name") or "").strip()
    folder = str(payload.get("folder") or name).strip()
    if folder != name:
        raise SkillGateError(
            f"Skill name {name!r} must match the folder name {folder!r}",
            hint="Rename the folder or the `name` field so they match.",
        )
    parent_raw = str(payload.get("parent") or "").strip() or str(state.root / "skills")
    parent = resolve_user_path(parent_raw, state)
    parent.mkdir(parents=True, exist_ok=True)
    if payload.get("clone_pdf"):
        source = pdf_demo_path(state)
        if source is None:
            raise SkillGateError("No skills/pdf demo pack under --root to clone.")
        dest = clone_pdf_layout(parent / name, source=source)
    else:
        dest = create_pack(parent, name, description=payload.get("description"))
        if payload.get("scaffold", True):
            scaffold_trigger_cases(dest)
    return 201, pack_payload(state, str(dest)), "application/json"


def _put_skill_md(state: UiState, payload: dict[str, Any]) -> tuple[int, dict[str, Any], str]:
    path = resolve_user_path(str(payload.get("path") or ""), state)
    skill = write_skill_md(
        path,
        name=str(payload.get("name") or path.name),
        description=str(payload.get("description") or ""),
        body=str(payload.get("body") or ""),
        license=payload.get("license") or None,
        compatibility=payload.get("compatibility") or None,
        allowed_tools=payload.get("allowed_tools") or payload.get("allowed-tools") or None,
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
    )
    usable, hint = description_is_usable(skill.description)
    return (
        200,
        {"skill": skill_to_dict(skill), "description_usable": usable, "description_hint": hint},
        "application/json",
    )


def _put_cases(state: UiState, payload: dict[str, Any]) -> tuple[int, dict[str, Any], str]:
    path = resolve_user_path(str(payload.get("path") or ""), state, must_exist=True)
    raw = {key: value for key, value in payload.items() if key != "path"}
    pack = CasePack.model_validate(raw)
    save_case_pack(path, pack)
    return 200, {"dataset": dataset_view(path)}, "application/json"


def _post_fixtures(state: UiState, payload: dict[str, Any]) -> tuple[int, dict[str, Any], str]:
    path = resolve_user_path(str(payload.get("path") or ""), state, must_exist=True)
    if payload.get("ensure_demo_pdfs"):
        ensure_demo_pdfs(path / "evals" / "fixtures")
        return 200, {"ok": True, "files": browser_files(path)}, "application/json"
    if payload.get("synthesize"):
        written = write_sample_fixture(
            path,
            dest=payload.get("dest"),
            prompt=str(payload.get("prompt") or ""),
            description=str(payload.get("description") or ""),
        )
        return 200, written, "application/json"
    src = str(payload.get("src") or "").strip()
    if not src:
        raise SkillGateError("Pass src, synthesize, or ensure_demo_pdfs.")
    source = resolve_user_path(src, state, must_exist=True)
    written = copy_into_pack(path, src=source, dest_name=payload.get("dest"))
    return 200, written, "application/json"


def _put_env(state: UiState, payload: dict[str, Any]) -> tuple[int, dict[str, Any], str]:
    unknown = [key for key in payload if key not in ALLOWED_ENV and key != "path"]
    if unknown:
        raise SkillGateError(
            f"Unknown env names: {', '.join(sorted(unknown))}",
            hint="Only API keys from .env.example are allowed.",
        )
    updates: dict[str, str] = {}
    for key in ALLOWED_ENV:
        if key not in payload:
            continue
        value = str(payload[key]).strip()
        if any(ch in value for ch in "\r\n"):
            raise SkillGateError(
                "API keys cannot contain line breaks.",
                hint="Paste a single-line key.",
            )
        updates[key] = value
    dest = state.root / ".env"
    merge_env_file(dest, updates)
    load_env(state.root)
    return 200, {"ok": True, "has_any_key": get_llm_config().has_any_key}, "application/json"


LIVE_NO_KEY = "No API key found. Run live needs your API key."
LIVE_FAIL = "Your API key could not run this check."


def _customer_live_error(error: dict[str, Any] | None) -> dict[str, Any] | None:
    if not error:
        return None
    hint = error.get("hint") or error.get("message") or LIVE_FAIL
    return {"message": LIVE_FAIL, "hint": hint}


def _start_check(state: UiState, payload: dict[str, Any]) -> tuple[int, dict[str, Any], str]:
    pack = resolve_user_path(str(payload.get("path") or ""), state, must_exist=True)
    live = bool(payload.get("live"))
    load_env(state.root)
    if live and not get_llm_config().has_any_key:
        raise MissingLLMKeyError(
            LIVE_NO_KEY,
            hint="Add a key, then click Run live. Or run with the built-in checker — that is not a live model.",
        )
    with state.lock:
        if (
            state.active_run_id
            and state.runs.get(state.active_run_id)
            and not state.runs[state.active_run_id].done
        ):
            return 409, {"error": "A check is already running."}, "application/json"
        run_id = uuid.uuid4().hex[:12]
        record = RunRecord(run_id=run_id)
        state.runs[run_id] = record
        state.active_run_id = run_id
        create_control(run_id)

    def worker() -> None:
        control = get_control(run_id)
        try:

            def on_progress(progress) -> None:
                record.progress = progress_to_dict(progress)

            result = run_check(
                pack,
                harness=str(payload.get("harness") or "auto"),
                live=live,
                demo=bool(payload.get("demo")),
                expect_fail=bool(payload.get("expect_fail")),
                on_progress=on_progress,
                control=control,
                run_id=run_id,
                source="ui",
                root=state.root,
            )
            err = result.error
            if live and err:
                err = _customer_live_error(err)
            payload_out: dict[str, Any] = {
                "run_id": run_id,
                "exit_code": result.exit_code,
                "demo_notice": result.demo_notice,
                "expect_fail_notice": result.expect_fail_notice,
                "error": err,
                "report": report_to_dict(result.report) if result.report is not None else None,
            }
            record.payload = payload_out
        except Exception as exc:  # noqa: BLE001 — surface to the poller
            message = LIVE_FAIL if live else str(exc)
            if isinstance(exc, SkillGateError):
                message = LIVE_FAIL if live else exc.message
            record.error = message
            record.payload = {
                "run_id": run_id,
                "exit_code": 1,
                "error": {"message": message, "hint": getattr(exc, "hint", None)},
            }
        finally:
            record.done = True
            drop_control(run_id)

    threading.Thread(target=worker, name=f"skillgate-check-{run_id}", daemon=True).start()
    return 202, {"run_id": run_id, "exit_code": None}, "application/json"


def _get_run(state: UiState, run_id: str) -> tuple[int, dict[str, Any], str]:
    record = state.runs.get(run_id)
    if record is None:
        return 404, {"error": f"Unknown run {run_id}"}, "application/json"
    if record.done and record.payload is not None:
        return 200, record.payload, "application/json"
    body: dict[str, Any] = {
        "run_id": run_id,
        "exit_code": None,
        "progress": record.progress,
        "error": record.error,
    }
    return 200, body, "application/json"


def _kill_run(state: UiState, run_id: str) -> tuple[int, dict[str, Any], str]:
    control = get_control(run_id)
    if control is None:
        return 404, {"error": f"Unknown run {run_id}"}, "application/json"
    control.request_kill()
    return 200, {"ok": True, "run_id": run_id}, "application/json"


def _apply_advice(state: UiState, payload: dict[str, Any]) -> tuple[int, dict[str, Any], str]:
    path = resolve_user_path(str(payload.get("path") or ""), state, must_exist=True)
    raw = str(payload.get("description") or payload.get("paste") or "").strip()
    if not raw:
        raise SkillGateError("Pass a description or a SKILL.md paste block.")
    if raw.lstrip().startswith("---"):
        description = description_from_paste(raw)
    else:
        description = raw
    rewrite_skill_description(path / "SKILL.md", description)
    skill = ingest_skill(path)
    return 200, {"skill": skill_to_dict(skill), "path": str(path)}, "application/json"
