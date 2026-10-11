# 10-minute quickstart (no account)

Skill Gate’s public CLI is a **local gate**. You do not sign up and you do not need a Skill Gate account. Built-in checks need no API key.

Requires **Python 3.11+**.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install skillgate-ai
skillgate version           # 0.4.2
```

(`pip install skillgate` is a different product.) From a clone of this repo you can use `pip install -e .` instead.

Skill scripts run with that same Python — install the skill’s own packages there too (the pdf example needs `pypdf`).

## Red → green on the pdf twins

The sabotaged twin has a meal-planner description, so PDF prompts never trigger it:

```bash
skillgate check skills/pdf-sabotaged
echo $?    # 1
```

Copy the **corrected SKILL.md description** the CLI prints, or copy `skills/pdf/SKILL.md` over the sabotaged frontmatter. Then:

```bash
skillgate check skills/pdf
echo $?    # 0
```

Intentional-fail CI:

```bash
skillgate check skills/pdf-sabotaged --expect-fail
echo $?    # 0
```

No `AI_GATEWAY_API_KEY`, no Docker required for this path. Live scoring with your OpenAI key is optional — see [openai-judge.md](https://github.com/vigneshm1995personal/skillgate/blob/main/docs/openai-judge.md).

## Deploy (after a green check)

`skillgate deploy` copies the pack into Cursor, Claude, or Codex. It refuses unless the latest local check passed. If this pack has never been checked, deploy runs the check first. Pass `--force` to install anyway (the skill may still be broken).

```bash
skillgate deploy skills/pdf
skillgate deploy skills/pdf --target claude
skillgate deploy skills/pdf --force
```

## Optional local UI

```bash
skillgate ui                 # http://127.0.0.1:8765 — no account
```

Same `run_check` engine as the CLI. See [ui.md](https://github.com/vigneshm1995personal/skillgate/blob/main/docs/ui.md). The Docker image still runs `skillgate check /pack`; do not treat the UI as `serve`.

## Docker (optional)

Multi-stage image, non-root UID 1001, `ENTRYPOINT ["skillgate"]`, `CMD ["check", "/pack"]`.

```bash
docker compose run --rm --no-TTY skillgate
PACK=./skills/pdf-sabotaged docker compose run --rm --no-TTY skillgate
```

## Copy-paste Action

Put this in a skill repo whose working directory is the pack (folder with `SKILL.md`). Needs Python 3.11+.

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
      - run: pip install skillgate-ai==0.4.2
      - run: skillgate check .
```

To score live checks in CI, add an optional `OPENAI_API_KEY` secret (see [openai-judge.md](https://github.com/vigneshm1995personal/skillgate/blob/main/docs/openai-judge.md)). Omit it to keep the built-in checker.
