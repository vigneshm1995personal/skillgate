# Bring your own judge

Optional. Live checks still run with Cursor, Codex, Claude, or OpenAI. **Scoring** uses the judge you pick in Settings (or `skillgate judge provider set`): OpenAI, Jev, AWS, or Other. Skill Gate does not ship a model or an account. Ambient `OPENAI_API_KEY` is ignored unless you pass `--key-env`.

## What you get

When a scoring key is set and you run a live check (`skillgate check`, or Run in the local UI), Skill Gate asks the same fixed questions on each live task. The check Passes only when those answers meet the bar (job done, correct, followed the rules, and so on). Every check still needs a signed-in agent (`skillgate login`) or a key; without one, `skillgate check` exits 2. Scoring is optional. File-exists / contains / page-count scorers grade the live run when:

- there is no scoring key in Settings (a Cursor or Codex key still runs the check)
- you set `SKILLGATE_JUDGE=skip`

Scorers such as “does the output contain this text?” and page counts still apply. Scoring does **not** compare the full output to the expected file; it reads the expected and actual text (and a few images) and judges whether the work is done.

Add extra scoring questions on top of Skill Gate’s six (`skillgate judge add-question`, or the Checks editor). Built-in questions cannot be deleted; they can be Warn only. Seed pdf cases cannot be removed.

## Setup

```bash
skillgate keys set OPENAI_API_KEY
```

Or paste the key in `skillgate ui` (Settings). **CI and Docker:** set `SKILLGATE_OPENAI_API_KEY` / `SKILLGATE_AI_GATEWAY_API_KEY` (and the other `SKILLGATE_*` key names). That prefix is the documented job path and is always read. Ambient `OPENAI_API_KEY` is ignored unless you pass `--key-env`. Other keys run live checks. An OpenAI key scores them when the scoring provider is Auto or OpenAI. Jev, AWS, and Other need their own key — they never reuse OpenAI.

Pick a scoring provider in Settings or:

```bash
skillgate judge provider set openai|jev|aws|other
skillgate judge provider set other --base-url https://openrouter.ai/api/v1 --model openai/gpt-4o-mini --key-env OPENROUTER_API_KEY
skillgate judge provider test
```

`--key-env` on `set` stores the env var name in `.skillgate/judge`. The key stays in that environment variable. Skill Gate does not write the value.

Override if you need it (CI / scripts — keep these `SKILLGATE_*` names):

| Env | Meaning |
| --- | --- |
| `SKILLGATE_JUDGE=auto` | Default. Score when an OpenAI or Other key is present; otherwise file-exists / contains / page-count grade the live run. |
| `SKILLGATE_JUDGE=openai` | Require scoring. Missing key → exit 2. |
| `SKILLGATE_JUDGE=skip` | Never score with the judge. File-exists / contains / page-count grade the live run. |
| `SKILLGATE_JUDGE_BACKEND=decisions` | Default scoring service. |
| `SKILLGATE_JUDGE_BACKEND=responses` | If your key can't use the newer scoring service, set this yourself. Skill Gate does not switch on 403. |
| `SKILLGATE_JUDGE_WHY=0` | Skip the short Fail explanation call (saves a follow-up request). |

Bad key, no credits, 403, 400, or timeout **fails the check** (exit 1) with a plain error. It never silently Passes. The key is never printed or stored in history.

If the scorer is not very sure about a Pass, the check still Passes. You will see: *The judge wasn't very sure about this one.* That warning does not change exit 0/1.

## GitHub Action (optional secret)

```yaml
- uses: actions/setup-python@v5
  with: { python-version: "3.12" }
- run: pip install skillgate-ai==0.7.2
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
