# skillgate-ai

Apache-2.0 local gate for [Agent Skills](https://agentskills.io): **one pack on disk** plus `skillgate check` exiting **0 or 1**. No Skill Gate account. Built-in checks need no API key.

Requires **Python 3.11+**. Install from PyPI:

```bash
pip install skillgate-ai
```

(`pip install skillgate` is a different project.) CLI command: `skillgate`.

## 10 minutes, no account

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install skillgate-ai
skillgate check skills/pdf-sabotaged    # exit 1 — description never matches PDF tasks
# copy SKILL.md from skills/pdf (or paste the CLI “Corrected SKILL.md description”)
skillgate check skills/pdf              # exit 0
```

From a clone of this repo, `pip install -e .` works the same once the virtualenv is on Python 3.11+.

Optional local UI (same engine, no account): `skillgate ui` → http://127.0.0.1:8765. See [`docs/ui.md`](docs/ui.md). Docker still runs `skillgate check /pack`.

`--expect-fail` inverts the exit code (CI for the sabotaged twin):

```bash
skillgate check skills/pdf-sabotaged --expect-fail   # exit 0
```

`skillgate deploy skills/pdf` copies the pack into Cursor, Claude, or Codex **only if** the latest local check passed. If this pack has never been checked, deploy runs the check first. Pass `--force` to install anyway (the skill may still be broken).

```bash
skillgate deploy skills/pdf
skillgate deploy skills/pdf --force
```

## Docker

Image `ENTRYPOINT` is `skillgate`; default `CMD` is `check /pack` (never `serve`).

```bash
docker compose run --rm --no-TTY skillgate
# bind-mount a pack:
PACK=./skills/pdf-sabotaged docker compose run --rm --no-TTY skillgate
# exit 1
```

Public image tag:

```bash
docker run --rm -v "$PWD/skills/pdf:/pack:ro" \
  ghcr.io/vigneshm1995personal/skillgate:v0.4.2
```

A `:ro` mount skips writing `evals/history/*.jsonl` (not writable). Compose mounts the pack read-write so history can append.

## Copy-paste GitHub Action

Working directory is the skill pack. Exit 1 fails the job. No account. Needs Python 3.11+.

```yaml
- uses: actions/setup-python@v5
  with: { python-version: "3.12" }
- run: pip install skillgate-ai==0.4.2
- run: skillgate check .
```

## Docs

- [`docs/quickstart.md`](docs/quickstart.md) — red sabotaged → green pdf
- [`docs/pack.md`](docs/pack.md) — `evals/cases.yaml` schema 1, fixtures, goldens, history
- [`docs/plans/0.5-decisions.md`](docs/plans/0.5-decisions.md) — 0.5 live-only / explicit keys (this PR)
- [Score live checks with your OpenAI key](docs/openai-judge.md) — optional; OpenAI key scores live checks
- [`docs/ui.md`](docs/ui.md) — local React UI (`skillgate ui`), red path, Docker stays `check /pack`
- [`docs/proof/PUBLISH.md`](docs/proof/PUBLISH.md) — secret scan, tag, PyPI Trusted Publishing, GHCR

Your own keys (Cursor / Codex / OpenAI-compatible / Anthropic) run the **live** check. An **OpenAI** key also scores live checks. Skip keys for the built-in checker (not a live model). See `.env.example` and [docs/openai-judge.md](https://github.com/vigneshm1995personal/skillgate/blob/main/docs/openai-judge.md).

Optional Action secret: `OPENAI_API_KEY` (not required to merge).

## Sync &amp; Mac helper (optional, no account)

Pull a skills repo and copy its skills into your local editor folders:

```bash
skillgate sync --repo https://github.com/you/skills.git --targets cursor,codex,claude
```

It only touches the skill dirs it manages — unrelated folders in your skills
roots are never deleted. Add a hands-off LaunchAgent (macOS only):

```bash
skillgate sync --repo https://github.com/you/skills.git --install-launchd
```

Connect a Mac to a hosted Skill Gate to receive installs:

```bash
skillgate connect --url https://your-host.example --code ABCDEFGH --name "My Mac"
skillgate helper            # polls outbound only; no listening ports
skillgate helper --install-launchd
```
