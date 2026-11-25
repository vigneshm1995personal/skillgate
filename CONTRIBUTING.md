# Contributing

## Setup

```bash
uv sync --locked --extra dev
source .venv/bin/activate
pre-commit install
```

Or with pip: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`.

## Dependencies / lockfile

CI and Docker install from the committed `uv.lock` with `uv sync --locked`. After changing dependencies in `pyproject.toml`, run `uv lock` and commit the updated lockfile. The repo pins **uv 0.12.13** (same as `UV_VERSION` in `.github/workflows/gate.yml`).

`pre-commit install` runs Ruff, Ruff format, mypy, and the basic file hooks on each commit.

## Tests

```bash
pytest -q -m "not integration"
pytest -q -m "not integration" --cov   # enforces fail_under in pyproject.toml
pytest -q -m integration tests/integration
```

## Lint (required)

```bash
ruff check
ruff format --check
mypy src
```

CI fails if those commands fail. Fix with `ruff check --fix` and `ruff format` (safe fixes only; do not pass `--unsafe-fixes`).
