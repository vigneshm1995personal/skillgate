"""Sandboxes: local tempdir (default) and optional Docker."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Protocol

from skillgate_ai.errors import SandboxError
from skillgate_ai.ingest import Skill
from skillgate_ai.live import CheckAborted, OutputSink
from skillgate_ai.observability import breadcrumb_harness_spawn, breadcrumb_timeout
from skillgate_ai.pack import copy_skill_pack
from skillgate_ai.suite import DEFAULT_TASK_TIMEOUT_SEC

_PIPE_JOIN_SEC = 5.0


class Sandbox(Protocol):
    workspace: Path
    output_sink: OutputSink | None

    def run(
        self,
        command: list[str],
        *,
        env: dict[str, str] | None = None,
        timeout: int = DEFAULT_TASK_TIMEOUT_SEC,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]: ...

    def close(self) -> None: ...


@dataclass
class PreparedWorkspace:
    workspace: Path
    skill_root: Path


def prepare_workspace(
    workspace: Path,
    skills: list[Skill],
    files: list[tuple[Path, str]],
) -> PreparedWorkspace:
    """Copy skills + task fixtures into an isolated workspace."""
    skill_root = workspace / ".skillgate" / "skills"
    skill_root.mkdir(parents=True, exist_ok=True)
    catalog_lines = ["# Available skills (name + description only)", ""]
    for skill in skills:
        dest = skill_root / skill.name
        copy_skill_pack(skill.path, dest)
        catalog_lines.append(f"## {skill.name}")
        catalog_lines.append(skill.description)
        catalog_lines.append("")
    catalog = workspace / ".skillgate" / "catalog.md"
    catalog.write_text("\n".join(catalog_lines), encoding="utf-8")
    (workspace / "output").mkdir(exist_ok=True)
    for src, dest_rel in files:
        dest = workspace / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    return PreparedWorkspace(workspace=workspace, skill_root=skill_root)


class LocalSandbox:
    def __init__(self, workspace: Path | None = None):
        self._tmp: tempfile.TemporaryDirectory[str] | None
        if workspace is None:
            self._tmp = tempfile.TemporaryDirectory(prefix="skillgate-")
            self.workspace = Path(self._tmp.name)
        else:
            self._tmp = None
            self.workspace = workspace
            self.workspace.mkdir(parents=True, exist_ok=True)
        self.output_sink: OutputSink | None = None

    def run(
        self,
        command: list[str],
        *,
        env: dict[str, str] | None = None,
        timeout: int = DEFAULT_TASK_TIMEOUT_SEC,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = with_running_python(command)
        merged = _sandbox_env(env)
        breadcrumb_harness_spawn(command)
        sink = self.output_sink
        try:
            if sink is None:
                # Close stdin. An inherited pipe makes Codex wait on
                # "Reading additional input from stdin..." until TimeoutExpired.
                return subprocess.run(
                    command,
                    cwd=str(cwd or self.workspace),
                    env=merged,
                    text=True,
                    capture_output=True,
                    timeout=timeout,
                    check=False,
                    stdin=subprocess.DEVNULL,
                )
            return _run_streaming(
                command,
                cwd=str(cwd or self.workspace),
                env=merged,
                timeout=timeout,
                sink=sink,
            )
        except subprocess.TimeoutExpired:
            breadcrumb_timeout(command, timeout)
            raise

    def close(self) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None


class DockerSandbox:
    def __init__(self, image: str, workspace: Path | None = None):
        if shutil.which("docker") is None:
            raise SandboxError(
                "Docker is not installed or not on PATH.",
                hint="Install Docker, or run with `--sandbox local` (the default).",
            )
        self.image = image
        _ensure_docker_image(image)
        self._local = LocalSandbox(workspace)
        self.output_sink: OutputSink | None = None

    @property
    def workspace(self) -> Path:
        return self._local.workspace

    def run(
        self,
        command: list[str],
        *,
        env: dict[str, str] | None = None,
        timeout: int = DEFAULT_TASK_TIMEOUT_SEC,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        work = self.workspace
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "-v",
            f"{work}:/work",
            "-w",
            "/work",
        ]
        for key, value in (env or {}).items():
            docker_cmd.extend(["-e", f"{key}={value}"])
        docker_cmd.append(self.image)
        docker_cmd.extend(command)
        breadcrumb_harness_spawn(docker_cmd)
        sink = self.output_sink
        try:
            if sink is None:
                return subprocess.run(
                    docker_cmd,
                    text=True,
                    capture_output=True,
                    timeout=timeout + 30,
                    check=False,
                    stdin=subprocess.DEVNULL,
                )
            return _run_streaming(
                docker_cmd,
                cwd=None,
                env=None,
                timeout=timeout + 30,
                sink=sink,
            )
        except subprocess.TimeoutExpired:
            breadcrumb_timeout(docker_cmd, timeout + 30)
            raise
        except FileNotFoundError as exc:
            raise SandboxError("Docker executable disappeared while running.") from exc

    def close(self) -> None:
        self._local.close()


def _run_streaming(
    command: list[str],
    *,
    cwd: str | None,
    env: dict[str, str] | None,
    timeout: int,
    sink: OutputSink,
) -> subprocess.CompletedProcess[str]:
    """Popen with reader threads so the live tail fills while the CLI runs."""
    abort = sink.should_abort()
    if abort:
        raise CheckAborted(abort)
    proc = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        text=True,
        bufsize=1,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
    )
    sink.attach_process(proc)
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    readers = [
        threading.Thread(
            target=_pump,
            args=(proc.stdout, "stdout", sink, stdout_chunks),
            daemon=True,
        ),
        threading.Thread(
            target=_pump,
            args=(proc.stderr, "stderr", sink, stderr_chunks),
            daemon=True,
        ),
    ]
    for reader in readers:
        reader.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise
    finally:
        for reader in readers:
            reader.join(timeout=_PIPE_JOIN_SEC)
        sink.detach_process()
    return subprocess.CompletedProcess(
        command,
        proc.returncode,
        stdout="".join(stdout_chunks),
        stderr="".join(stderr_chunks),
    )


def _pump(
    stream: IO[str] | None,
    name: str,
    sink: OutputSink,
    chunks: list[str],
) -> None:
    if stream is None:
        return
    try:
        for line in iter(stream.readline, ""):
            chunks.append(line)
            try:
                sink.on_line(name, line.rstrip("\n"))
            except Exception:  # noqa: BLE001, S110 - a sink bug must not kill the harness
                pass
    finally:
        stream.close()


def _ensure_docker_image(image: str) -> None:
    try:
        inspect = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SandboxError(
            "Couldn't reach Docker.",
            hint="Start Docker, or run with `--sandbox local` (the default).",
        ) from exc
    except OSError as exc:
        raise SandboxError(
            "Couldn't reach Docker.",
            hint="Start Docker, or run with `--sandbox local` (the default).",
        ) from exc
    if inspect.returncode == 0:
        return
    err = f"{inspect.stderr or ''} {inspect.stdout or ''}".lower()
    if "cannot connect" in err or "daemon" in err:
        raise SandboxError(
            "Couldn't reach Docker.",
            hint="Start Docker, or run with `--sandbox local` (the default).",
        )
    raise SandboxError(
        f"Docker image {image} is not installed.",
        hint="Build or pull that image, or run with `--sandbox local` (the default).",
    )


def open_sandbox(kind: str, docker_image: str) -> Sandbox:
    if kind in {"local", "fs", "temp"}:
        return LocalSandbox()
    if kind in {"docker", "container"}:
        return DockerSandbox(docker_image)
    raise SandboxError(
        f"Unknown sandbox {kind!r}",
        hint="Use `local` or `docker`.",
    )


_PYTHON_NAMES = frozenset({"python", "python3", "python.exe", "python3.exe"})


def running_python() -> str:
    """Interpreter Skill Gate is running in — not a bare `python3` on PATH."""
    return sys.executable


def with_running_python(command: list[str]) -> list[str]:
    """Rewrite `python` / `python3` to the running interpreter. Leave other commands."""
    if not command:
        return list(command)
    name = Path(command[0]).name.lower()
    if name in _PYTHON_NAMES:
        return [running_python(), *command[1:]]
    return list(command)


def _sandbox_env(extra: dict[str, str] | None) -> dict[str, str]:
    # Do not leak API keys into the skill sandbox.
    blocked = {
        "CURSOR_API_KEY",
        "CODEX_API_KEY",
        "CODEX_ACCESS_TOKEN",
        "AI_GATEWAY_API_KEY",
        "ANTHROPIC_API_KEY",
        "SKILLGATE_SECRETS_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
    }
    env = {k: v for k, v in os.environ.items() if k not in blocked}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    if extra:
        env.update(extra)
    bindir = str(Path(running_python()).resolve().parent)
    path = env.get("PATH", "")
    parts = [
        item
        for item in path.split(os.pathsep)
        if item and Path(item).resolve() != Path(bindir)
    ]
    env["PATH"] = os.pathsep.join([bindir, *parts] if bindir else parts)
    return env
