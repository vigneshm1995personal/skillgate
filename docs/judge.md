# Bring your own judge

Optional. Live checks still run with Cursor, Codex, or Claude. Scoring uses a decision model you pick in Settings (or `skillgate judge provider set`): OpenAI Decisions, Jev, or Clef. Skill Gate does not ship a model or an account. Ambient `OPENAI_API_KEY` is ignored unless you pass `--key-env`.

## What you get

When you pick a decision model and run a live check (`skillgate check`, or Run in the local UI), Skill Gate asks the same fixed questions on each live task. The check passes only when those answers meet the bar (job done, correct, followed the rules, and so on). Every check still needs a signed-in agent (`skillgate login`) or a key. Without one, `skillgate check` exits 2. Scoring is optional. File-exists, contains, and page-count scorers grade the live run when:

- you leave the scoring provider on Auto (file checks only)
- you set `SKILLGATE_JUDGE=skip`

Scorers such as "does the output contain this text?" and page counts still apply. Scoring does not compare the full output to the expected file. It reads the expected and actual text (and a few images) and judges whether the work is done.

Add extra scoring questions on top of Skill Gate's six (`skillgate judge add-question`, or the Checks editor). Built-in questions cannot be deleted. They can be Warn only. Seed pdf cases cannot be removed.

## Setup

```bash
skillgate keys set OPENAI_API_KEY
skillgate judge provider set openai
```

Or paste the key in `skillgate ui` (Settings) and pick OpenAI Decisions. **CI and Docker:** set `SKILLGATE_OPENAI_API_KEY` (and the other `SKILLGATE_*` key names). That prefix is the documented job path and is always read. Ambient `OPENAI_API_KEY` is ignored unless you pass `--key-env`.

Jev and Clef need their own key. They never reuse an OpenAI key.

```bash
skillgate judge provider set openai
skillgate keys set JEV_API_KEY
skillgate judge provider set jev --base-url https://openrouter.ai/api/v1 --model typesafe/jev-1.14
skillgate keys set CLOUDFLARE_API_TOKEN
skillgate judge provider set clef --account-id YOUR_ACCOUNT_ID --model clef
skillgate judge provider test
```

Jev on OpenRouter uses the saved model and posts to `POST https://openrouter.ai/api/alpha/decisions`. Any other Jev base URL still posts to `{base}/evaluate`. Clef posts to the Cloudflare Workers AI decision endpoint for `clef` or `clef-flash`. A bad endpoint, rejected key, or empty balance fails that check. Skill Gate does not switch to another judge.

Chat and Responses scoring was removed. Setting the judge backend to responses fails the run. AWS and Other scoring were removed. A saved file that still names them fails until you pick auto, openai, jev, or clef.

`--key-env` on `set` stores the env var name in `.skillgate/judge`. The key stays in that environment variable. Skill Gate does not write the value.

| Env | Meaning |
| --- | --- |
| `SKILLGATE_JUDGE=auto` | Default. File checks only. A saved key does not turn scoring on. |
| `SKILLGATE_JUDGE=openai` | Score with OpenAI Decisions. Missing `OPENAI_API_KEY` exits 2. A gateway key is not used. |
| `SKILLGATE_JUDGE=skip` | Never score with the judge. File-exists, contains, and page-count scorers grade the live run. |
| `SKILLGATE_JUDGE_BACKEND=decisions` | OpenAI scoring uses the Decisions API. This is the only OpenAI scoring path. |

Bad key, no credits, 403, 400, or timeout fails the check (exit 1) with a plain error. It never silently passes. The key is never printed or stored in history.

If the scorer is not very sure about a pass, the check still passes. You will see: *The judge wasn't very sure about this one.* That warning does not change exit 0/1.

## GitHub Action (optional secret)

```yaml
- uses: actions/setup-python@v5
  with: { python-version: "3.12" }
- run: pip install skillgate-ai==0.7.3
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
# JSON names who scored. Exit 0 or 1. Never a traceback.
```

OpenAI scoring uses the Decisions API. Chat and Responses scoring was removed.
