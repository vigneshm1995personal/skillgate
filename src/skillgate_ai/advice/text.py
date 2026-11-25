from __future__ import annotations

from skillgate_ai.suite import TaskSpec


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
    if text.startswith("{") or text.startswith("["):  # noqa: SIM103
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
