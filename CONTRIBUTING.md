# Contributing

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

`pre-commit install` runs Ruff, Ruff format, mypy, and the basic file hooks on each commit.

## Lint (required)

```bash
ruff check
ruff format --check
mypy src
```

CI fails if those commands fail. Fix with `ruff check --fix` and `ruff format` (safe fixes only; do not pass `--unsafe-fixes`).
