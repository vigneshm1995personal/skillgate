# Score live checks with your OpenAI key

Optional. Live checks still run with Cursor, Codex, Claude, or OpenAI. **Scoring** uses OpenAI’s scoring API (`POST /v1/decisions`): an OpenAI key in Settings talks to OpenAI directly; a gateway key without an OpenAI key uses that same API on AI Gateway. Skill Gate does not ship a model or an account. Ambient `OPENAI_API_KEY` is ignored unless you pass `--key-env`.

## What you get

When an OpenAI or AI Gateway key is set and you run a live check (`skillgate check`, or Run in the local UI), Skill Gate asks the same fixed questions on each live task. The check Passes only when those answers meet the bar (job done, correct, followed the rules, and so on). An OpenAI key is never rerouted through the gateway. Fixture checks (file exists, contains, page count) decide pass/fail when:

- there is no OpenAI key and no AI Gateway key in Settings
- you set `SKILLGATE_JUDGE=skip`

Fixture checks such as “does the output contain this text?” and page counts still apply. Scoring does **not** compare the full output to the expected file; it reads the expected and actual text (and a few images) and judges whether the work is done.

## Setup

```bash
skillgate keys set OPENAI_API_KEY
```

Or paste the OpenAI key in `skillgate ui` (Settings). Other keys run live checks; an OpenAI or AI Gateway key also scores them.

Override if you need it:

| Env | Meaning |
| --- | --- |
| `SKILLGATE_JUDGE=auto` | Default. Score when an OpenAI or AI Gateway key is present; otherwise fixture checks. |
| `SKILLGATE_JUDGE=openai` | Require scoring. Missing key → exit 2. |
| `SKILLGATE_JUDGE=skip` | Never score with OpenAI. Fixture checks decide the result. |
| `SKILLGATE_JUDGE_BACKEND=decisions` | Default scoring service. |
| `SKILLGATE_JUDGE_BACKEND=responses` | If your key can't use the newer scoring service, set this yourself. Skill Gate does not switch on 403. |
| `SKILLGATE_JUDGE_WHY=0` | Skip the short Fail explanation call (saves a follow-up request). |

Bad key, no credits, 403, 400, or timeout **fails the check** (exit 1) with a plain error. It never silently Passes. The key is never printed or stored in history.

If the scorer is not very sure about a Pass, the check still Passes. You will see: *The judge wasn't very sure about this one.* That warning does not change exit 0/1.

## GitHub Action (optional secret)

```yaml
- uses: actions/setup-python@v5
  with: { python-version: "3.12" }
- run: pip install skillgate-ai==0.5.0
- run: skillgate check . --key-env OPENAI_API_KEY
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

Do not add a required OpenAI secret to merge CI.

## Live smoke (not CI)

```bash
export OPENAI_API_KEY=sk-...     # never echo
export SKILLGATE_JUDGE=openai
skillgate check /path/to/one-case-pack --json
# JSON names who scored. Exit 0 or 1 — never a traceback.
```

If your key can't use the newer scoring service, set `SKILLGATE_JUDGE_BACKEND=responses` and retry. That is a fallback you choose, not an automatic switch.
