# Score live checks with your OpenAI key

Optional. Deterministic fixture checks still need **no key**. Live checks still run with Cursor, Codex, Claude, or OpenAI. **Scoring** uses OpenAI’s scoring API (`POST /v1/decisions`): your `OPENAI_API_KEY` talks to OpenAI directly; `AI_GATEWAY_API_KEY` without an OpenAI key uses that same API on AI Gateway. Skill Gate does not ship a model or an account.

## What you get

When an OpenAI or AI Gateway key is set and you run a live check (`skillgate check --live`, or Run live in the local UI), Skill Gate asks the same fixed questions on each live task. The check Passes only when those answers meet the bar (job done, correct, followed the rules, and so on). An OpenAI key is never rerouted through the gateway. The built-in checker stays in charge when:

- there is no OpenAI key and no AI Gateway key
- you set `SKILLGATE_JUDGE=skip`
- you use the built-in / demo path (`--demo`, or Skip in the wizard)

The built-in checker only runs fixture checks such as “does the output contain this text?” and page counts. It does **not** compare the full output to the expected file. Scoring does read the expected and actual text (and a few images) and judges whether the work is done.

## Setup

```bash
# .env — never commit this file
OPENAI_API_KEY=sk-...
```

Or paste the OpenAI key in `skillgate ui` (Settings, or the skill page **Add your API key**). Other keys run live checks; an OpenAI or AI Gateway key also scores them.

Override if you need it:

| Env | Meaning |
| --- | --- |
| `SKILLGATE_JUDGE=auto` | Default. Score when an OpenAI or AI Gateway key is present; otherwise the built-in checker. |
| `SKILLGATE_JUDGE=openai` | Require scoring. Missing key → exit 2. |
| `SKILLGATE_JUDGE=skip` | Never score with OpenAI. The built-in checker decides the result. |
| `SKILLGATE_JUDGE_BACKEND=decisions` | Default scoring service. |
| `SKILLGATE_JUDGE_BACKEND=responses` | If your key can't use the newer scoring service, set this yourself. Skill Gate does not switch on 403. |
| `SKILLGATE_JUDGE_WHY=0` | Skip the short Fail explanation call (saves a follow-up request). |

Bad key, no credits, 403, 400, or timeout **fails the check** (exit 1) with a plain error. It never silently Passes. The key is never printed or stored in history.

If the scorer is not very sure about a Pass, the check still Passes. You will see: *The judge wasn't very sure about this one.* That warning does not change exit 0/1.

## GitHub Action (optional secret)

```yaml
- uses: actions/setup-python@v5
  with: { python-version: "3.12" }
- run: pip install skillgate-ai==0.4.1
- run: skillgate check .
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}   # optional; omit for the built-in checker
```

Do not add a required OpenAI secret to merge CI.

## Live smoke (not CI)

```bash
export OPENAI_API_KEY=sk-...     # never echo
export SKILLGATE_JUDGE=openai
skillgate check /path/to/one-case-pack --live --json
# JSON names who scored. Exit 0 or 1 — never a traceback.
```

If your key can't use the newer scoring service, set `SKILLGATE_JUDGE_BACKEND=responses` and retry. That is a fallback you choose, not an automatic switch.
