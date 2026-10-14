# AGENTS.md — skillgate (OSS)

Local Apache-2.0 gate for Agent Skills. One pack on disk + `skillgate check` (exit 0/1). No account. PyPI package: `skillgate-ai`. Hosted product lives in the private `skillgate-ai` repo.

## Stack

- Python ≥ 3.11 (`src/skillgate_ai/`), CLI via Typer (`skillgate` / `skillgate-ai`)
- Optional local UI: `skillgate ui` (stdlib server + static assets under `src/skillgate_ai/local_ui/`)
- Docker image ENTRYPOINT is `skillgate`; default CMD is `check /pack`

## Layout

- `src/skillgate_ai/` — package (CLI, gate, judges, local UI, sync/helper)
- `tests/` — pytest
- `skills/` — seed packs (`sample-skill`, `pdf`, `pdf-sabotaged`)
- `docs/` — quickstart, pack schema, plans
- `scripts/` — maintainer helpers
- `.github/workflows/gate.yml` — CI

## Commands (from repo root)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
skillgate check skills/sample-skill
skillgate check skills/pdf-sabotaged --expect-fail
ruff check .    # optional; ruff is a dev dep
```

Docker: `docker build -t skillgate:test --target runtime .` then `docker run --rm -v "$PWD/skills/sample-skill:/pack" skillgate:test`.

## Agent skills

Always apply the skills in `.cursor/skills`: plan-mode, clean-coder, test-driven-vibe, frontend-design (UI), error-driven-debugger (bugs). Run tests locally and push only when green.
