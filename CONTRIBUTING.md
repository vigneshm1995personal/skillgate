# Contributing

Thanks for helping improve Skill Gate AI (OSS). This repo is the `skillgate-ai` PyPI package and CLI.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Requires **Python 3.11+**. Optional: `pnpm install` in `web/` if you touch the marketing or local UI frontend.

## Checks before you push

```bash
pytest -q
ruff check .          # optional; included in dev deps
skillgate check skills/pdf              # needs a model key for exit 0
skillgate check skills/pdf-sabotaged --expect-fail
```

CI runs `pytest` and web unit tests; live checks in GHA use keys from repo secrets when configured.

## Pull requests

- Keep changes focused; match existing style in touched files.
- Update `docs/` and `README.md` when CLI flags or user-facing behavior changes.
- Do not commit secrets or real API keys. Use `skillgate keys set` locally and `SKILLGATE_*` in CI.

## License

By contributing, you agree your contributions are licensed under the project’s [Apache-2.0](LICENSE) license.
