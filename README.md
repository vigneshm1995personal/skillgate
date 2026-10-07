# skillgate

Apache-2.0 local gate for [Agent Skills](https://agentskills.io): **one pack on disk** plus `skillgate check` exiting **0 or 1**. No Skill Gate account. Deterministic fixture checks need no API key.

PyPI distribution: **`skillgate-ai`** (`pip install skillgate` is a different project). CLI command: `skillgate`.

Hosted product (SIWV, vault, Neon, dashboard) stays private at [`vigneshm1995personal/skillgate-ai`](https://github.com/vigneshm1995personal/skillgate-ai) and will never be made public.

## 10 minutes, no account

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
skillgate check skills/pdf-sabotaged    # exit 1 — description never matches PDF tasks
# copy SKILL.md from skills/pdf (or paste the CLI “Corrected SKILL.md description”)
skillgate check skills/pdf              # exit 0
```

Optional local UI (same engine, no account): `skillgate ui` → http://127.0.0.1:8765. See [`docs/ui.md`](docs/ui.md). Docker still runs `skillgate check /pack`.

`--expect-fail` inverts the exit code (CI for the sabotaged twin):

```bash
skillgate check skills/pdf-sabotaged --expect-fail   # exit 0
```

## Docker

Image `ENTRYPOINT` is `skillgate`; default `CMD` is `check /pack` (never `serve`).

```bash
docker compose run --rm --no-TTY skillgate
# bind-mount a pack:
PACK=./skills/pdf-sabotaged docker compose run --rm --no-TTY skillgate
# exit 1
```

After the first public tag:

```bash
docker run --rm -v "$PWD/skills/pdf:/pack:ro" \
  ghcr.io/vigneshm1995personal/skillgate:v0.3.0
```

A `:ro` mount skips writing `evals/history/*.jsonl` (EACCES). Compose mounts the pack read-write so history can append.

## Copy-paste GitHub Action

Working directory is the skill pack. Exit 1 fails the job. No account.

```yaml
- uses: actions/setup-python@v5
  with: { python-version: "3.12" }
- run: pip install skillgate-ai==0.3.0
- run: skillgate check .
```

Until the first PyPI release, CI in this repo uses `pip install -e .`.

## Docs

- [`docs/quickstart.md`](docs/quickstart.md) — red sabotaged → green pdf
- [`docs/pack.md`](docs/pack.md) — `evals/cases.yaml` schema 1, fixtures, goldens, history
- [Extract plan](docs/plans/2026-10-03-skillgate-oss-extract.md) — allowlist / deny-list
- [Local UI + setup wizard plan](docs/plans/2026-10-04-local-ui-setup-wizard.md) — `skillgate ui` (local stdlib UI; not hosted `serve`)
- [Score live checks with your OpenAI key](docs/openai-judge.md) — optional; `OPENAI_API_KEY` scores live checks. Built-in checker if unset.
- [OpenAI judge plan](docs/plans/openai-judge.md) — implementation plan
- [`docs/ui.md`](docs/ui.md) — start the local UI, red path, Docker stays `check /pack`
- [`docs/proof/PUBLISH.md`](docs/proof/PUBLISH.md) — secret scan, tag, PyPI Trusted Publishing, GHCR (owner UI; do not flip public from CI)

BYO keys (Cursor / Codex / OpenAI-compatible / Anthropic) run the **live** check. An **OpenAI** key also scores live checks. Skip keys for the built-in checker (not a live model). See `.env.example` and [`docs/openai-judge.md`](docs/openai-judge.md).

Optional Action secret: `OPENAI_API_KEY` (not required to merge).
