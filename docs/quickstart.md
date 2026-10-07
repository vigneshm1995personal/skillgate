# 10-minute quickstart (no account)

Skill Gate’s public CLI is a **local gate**. You do not sign up, you do not need Neon, SIWV, or a Skill Gate account. Deterministic fixtures use the demo harness.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
skillgate version           # 0.3.0
```

Or, after the first PyPI release: `pip install skillgate-ai` (not `pip install skillgate` — that name is a different product).

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

No `AI_GATEWAY_API_KEY`, no Docker required for this path. Live scoring with your OpenAI key is optional — see [`openai-judge.md`](openai-judge.md).

## Optional local UI

```bash
skillgate ui                 # http://127.0.0.1:8765 — no account
```

Same `run_check` engine as the CLI. See [`docs/ui.md`](ui.md). The Docker image still runs `skillgate check /pack`; do not treat the UI as `serve`.

## Docker (optional)

Follows **docker-project-foundations** + **docker-build-strategies**: multi-stage, slim pin+digest, non-root UID 1001, `.dockerignore`, `ENTRYPOINT ["skillgate"]`, `CMD ["check", "/pack"]`.

```bash
docker compose run --rm --no-TTY skillgate
PACK=./skills/pdf-sabotaged docker compose run --rm --no-TTY skillgate
```

## Copy-paste Action (rung 1)

Put this in a skill repo whose working directory is the pack (folder with `SKILL.md`):

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
      - run: pip install skillgate-ai==0.3.0
      - run: skillgate check .
```

Until PyPI publish, replace the install line with a git/editable install of this repo.

To score live checks in CI, add an optional `OPENAI_API_KEY` secret (see [`openai-judge.md`](openai-judge.md)). Omit it to keep the built-in checker.

## What is not in this package

No hosted dashboard, Sign in with Vercel, vault, Neon store, Vercel Sandbox, or generated-check drafts. Those stay in the private `skillgate-ai` app.
