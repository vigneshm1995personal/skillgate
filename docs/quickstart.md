# 10-minute quickstart (no account)

Skill Gate’s public CLI is a **local gate**. You do not sign up and you do not need a Skill Gate account. Every check is a live model run with a key you set in Skill Gate.

Requires **Python 3.11+**.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install skillgate-ai
skillgate version           # 0.6.1
```

(`pip install skillgate` is a different product.) From a clone of this repo you can use `pip install -e .` instead.

## Keys, then the sample-skill example

Skill Gate does not read `OPENAI_API_KEY` from the shell unless you pass `--key-env`. Set a key explicitly (vault, Settings, or the `SKILLGATE_*` CI/Docker prefix):

```bash
skillgate keys set OPENAI_API_KEY
# hidden prompt; or pipe stdin: printf '%s\n' "$OPENAI_API_KEY" | skillgate keys set OPENAI_API_KEY
# or paste in Settings (`skillgate ui`)
skillgate example sample-skill
skillgate check sample-skill
echo $?    # 0 when the live run is green
```

The sabotaged example has a meal-planner description, so PDF prompts never trigger it:

```bash
skillgate example pdf-sabotaged
skillgate check pdf-sabotaged
echo $?    # 1
```

Intentional-fail CI:

```bash
skillgate check pdf-sabotaged --expect-fail
echo $?    # 0
```

Live scoring is optional — pick OpenAI, Jev, AWS, or Other in Settings. See [judge.md](https://github.com/vigneshm1995personal/skillgate/blob/main/docs/judge.md). Every check is a live model run; without a key, `skillgate check` exits 2. Default results say “Scored by the judge” unless you picked a provider.

## Deploy (after a green check)

`skillgate deploy` copies **only the skill files** (not `evals/`) into Cursor, Claude, or Codex. It refuses unless this pack already has a passing check **and a model key is set** (vault, Settings, or `SKILLGATE_*`). It does not run check for you. Without a key, Deploy stays blocked even after a green check; the pointer is Settings / `skillgate keys set`.

```bash
skillgate check sample-skill
skillgate deploy sample-skill
skillgate deploy sample-skill --target claude
skillgate deploy sample-skill --targets cursor,codex
```

## Optional local UI

```bash
skillgate ui                 # http://127.0.0.1:8765 — no account
```

Same `run_check` engine as the CLI. Run is disabled until a key is in Settings. See [ui.md](https://github.com/vigneshm1995personal/skillgate/blob/main/docs/ui.md). The Docker image still runs `skillgate check /pack`; do not treat the UI as `serve`.

## Docker (optional)

Multi-stage image, non-root UID 1001, `ENTRYPOINT ["skillgate"]`, `CMD ["check", "/pack"]`. Keyless `check` exits 2.

```bash
docker compose run --rm --no-TTY skillgate example sample-skill --dest /tmp/sample-skill
```

## Copy-paste Action

Put this in a skill repo whose working directory is the pack (folder with `SKILL.md`). Needs Python 3.11+ and a key.

```yaml
name: skillgate
on: [push, pull_request]
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install skillgate-ai==0.6.1
      - run: skillgate check . --key-env OPENAI_API_KEY
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

Or set `SKILLGATE_OPENAI_API_KEY` instead of `--key-env`. The `SKILLGATE_*` key names are the documented CI/Docker path and are always read.
