# Score live checks with your OpenAI key

Optional. Deterministic fixture checks still need **no key**. Live checks still run with Cursor, Codex, Claude, or OpenAI. **Scoring** with OpenAI uses **your** `OPENAI_API_KEY` only. Skill Gate does not ship a model or an account.

## What you get

When `OPENAI_API_KEY` is set and you run a live check (`skillgate check --live`, or Run live in the local UI), Skill Gate asks OpenAI the same fixed questions on each live task and applies a Pass/Fail lock. The built-in checker stays in charge when:

- there is no OpenAI key
- you set `SKILLGATE_JUDGE=skip`
- you use the built-in / demo path (`--demo`, or Skip in the wizard)

`AI_GATEWAY_API_KEY` without `OPENAI_API_KEY` does **not** score.

## Setup

```bash
# .env — never commit this file
OPENAI_API_KEY=sk-...
```

Or paste the OpenAI key in `skillgate ui` (wizard **Your API key**, or the skill page **Add your API key**). Other keys run live checks; an OpenAI key also scores them.

Override if you need it:

| Env | Meaning |
| --- | --- |
| `SKILLGATE_JUDGE=auto` | Default. Score when an OpenAI key is present; otherwise the built-in checker. |
| `SKILLGATE_JUDGE=openai` | Require scoring. Missing key → exit 2. |
| `SKILLGATE_JUDGE=skip` | Never score. Built-in checker owns Pass/Fail. |
| `SKILLGATE_JUDGE_BACKEND=decisions` | Default scoring API. |
| `SKILLGATE_JUDGE_BACKEND=responses` | Fallback if Decisions is not enabled for your key. Set this yourself; Skill Gate does not switch on 403. |
| `SKILLGATE_JUDGE_WHY=0` | Skip the short Fail explanation call (saves a follow-up request). |

Bad key, quota, 403, 400, or timeout **fails the check** (exit 1) with a plain error. It never silently Passes. The key is never printed or stored in history.

If the scorer is not very sure about a Pass, the check still Passes. You will see: *The judge wasn't very sure about this one.* That warning does not change exit 0/1.

## GitHub Action (optional secret)

```yaml
- uses: actions/setup-python@v5
  with: { python-version: "3.12" }
- run: pip install skillgate-ai==0.3.0
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
# tasks[].judge.backend is "decisions" on the default path
# tasks[].judge.answers.task_completion.choice is set
# confidence is present on Decisions answers
# exit 0 or 1 — never a traceback
```

If that key gets HTTP 403 on the default scorer, set `SKILLGATE_JUDGE_BACKEND=responses` and retry. That is a fallback you choose, not an automatic switch.
