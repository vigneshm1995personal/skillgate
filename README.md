# skillgate-ai

Apache-2.0 local gate for [Agent Skills](https://agentskills.io): **one pack on disk** plus `skillgate check` exiting **0, 1, or 2**. No Skill Gate account. Every check is a live model run with a key you set in Skill Gate.

Requires **Python 3.11+**. Install from PyPI:

```bash
pip install skillgate-ai
```

(`pip install skillgate` is a different project.) CLI command: `skillgate`.

## 10 minutes, no account

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install skillgate-ai
skillgate keys set OPENAI_API_KEY   # hidden prompt; or pipe stdin. Or paste in Settings (`skillgate ui`)
skillgate example pdf
skillgate check pdf
```

From a clone of this repo, `pip install -e .` works the same once the virtualenv is on Python 3.11+.

Optional local UI (same engine, no account): `skillgate ui` → http://127.0.0.1:8765. See [`docs/ui.md`](docs/ui.md). Docker still runs `skillgate check /pack` (exit 2 until a key is mounted).

`--expect-fail` inverts the exit code (CI for a skill that should fail):

```bash
skillgate example pdf-sabotaged
skillgate check pdf-sabotaged --expect-fail   # exit 0 after a live red run
```

`skillgate deploy pdf` copies **only the skill files** (not `evals/`) into Cursor, Claude, or Codex **only if** this pack already has a passing check. It does not run check for you.

```bash
skillgate check pdf
skillgate deploy pdf
```

Create a workspace and a new skill (same as the UI):

```bash
skillgate init
skillgate new notes-helper
```

## Docker

Image `ENTRYPOINT` is `skillgate`; default `CMD` is `check /pack` (never `serve`). Without a key, that exits 2.

```bash
docker compose run --rm --no-TTY skillgate example pdf --dest /tmp/pdf
```

Public image tag:

```bash
docker run --rm -v "$PWD/pdf:/pack:ro" \
  -e SKILLGATE_OPENAI_API_KEY \
  ghcr.io/vigneshm1995personal/skillgate:v0.6.0
```

A `:ro` mount skips writing `evals/history/*.jsonl` (not writable). Compose mounts the pack read-write so history can append.

## Copy-paste GitHub Action

Working directory is the skill pack. Exit 1 fails the job. No account. Needs Python 3.11+ **and** a key (Skill Gate does not read `OPENAI_API_KEY` unless you pass `--key-env`).

```yaml
- uses: actions/setup-python@v5
  with: { python-version: "3.12" }
- run: pip install skillgate-ai==0.6.0
- run: skillgate check . --key-env OPENAI_API_KEY
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

Or set `SKILLGATE_OPENAI_API_KEY` in the job env instead of `--key-env`.

## Docs

- [`docs/quickstart.md`](docs/quickstart.md) — keys, example pdf, live check
- [`docs/pack.md`](docs/pack.md) — `evals/cases.yaml` schema 1, fixtures, goldens, history
- [`docs/plans/0.5-decisions.md`](docs/plans/0.5-decisions.md) — 0.5 live-only / explicit keys
- [Score live checks](docs/openai-judge.md) — optional; pick OpenAI, Jev, AWS, or Other in Settings
- [`docs/ui.md`](docs/ui.md) — local React UI (`skillgate ui`), red path, Docker stays `check /pack`
- [`docs/proof/PUBLISH.md`](docs/proof/PUBLISH.md) — secret scan, tag, PyPI Trusted Publishing, GHCR

Keys live in `{project}/.skillgate/keys` (gitignored, mode 0600). Ambient `OPENAI_API_KEY` / `AI_GATEWAY_API_KEY` / `AWS_*` are ignored unless you pass `--key-env`. See `.env.example` for non-secret config. Pick who scores in Settings (`skillgate judge provider set`). Default results say **Scored by the judge** unless you picked a provider.

## Layout

```
skills/<name>/SKILL.md
skills/<name>/evals/cases.yaml
src/skillgate_ai/     # this package
```
