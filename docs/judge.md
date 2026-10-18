# Bring your own judge

Optional. Live checks still run with Cursor, Codex, or Claude. Scoring uses a decision model you turn on in Settings, or with `skillgate judge provider set`. Skill Gate does not ship a model or an account. A key in the environment is ignored unless you pass `--key-env`.

## What you get

When a decision model is on and you run a live check (`skillgate check`, or Run in the local UI), Skill Gate asks the same fixed questions on each live task. The check passes only when those answers meet the bar (job done, correct, followed the rules, and so on). Every check still needs a signed-in agent (`skillgate login`) or a key. Without one, `skillgate check` exits 2. A live check also needs a decision model. With none selected, the check exits 2 and asks you to pick one. It does not fall back to another model.

Scorers such as "does the output contain this text?" and page counts still apply beside that decision model. Scoring does not compare the full output to the expected file. It reads the expected and actual text (and a few images) and judges whether the work is done. Pass `--no-judge` only when you mean to run without a decision model.

Add extra scoring questions on top of Skill Gate's six (`skillgate judge add-question`, or the Checks editor). Built-in questions cannot be deleted. They can be Warn only. Seed pdf cases cannot be removed.

## Setup

```bash
skillgate keys set
skillgate judge provider set <endpoint>
skillgate judge provider test
```

Paste the key in `skillgate ui` (Settings), choose Decision model, and enter the endpoint id. **CI and Docker:** set the `SKILLGATE_*` name for that key. That prefix is the documented job path and is always read. A key that is only in the process environment is ignored unless you pass `--key-env`.

Each decision model uses its own key. A missing key fails that check. Skill Gate does not switch to another decision model.

```bash
skillgate judge provider set <endpoint> --base-url https://example.com/v1 --model <model>
skillgate judge provider set <endpoint> --account-id <account-id> --model <model>
skillgate judge provider test
```

A bad endpoint, rejected key, or empty balance fails that check. Chat and Responses completion models are not judges. Setting the judge backend to `responses`, `chat`, or `completions` fails the run. Older chat-style scoring setups fail until you pick a registered decision model.

`--key-env` on `set` stores the env var name in `.skillgate/judge`. The key stays in that environment variable. Skill Gate does not write the value.

| Env | Meaning |
| --- | --- |
| unset, `auto`, or `skip` | No decision model. A live check exits 2 and asks you to pick one. A saved key does not turn scoring on. |
| a decision-model endpoint id | Score with that decision model. A missing key exits 2. |

Bad key, no credits, 403, 400, or timeout fails the check (exit 1) with a plain error. It never silently passes. The key is never printed or stored in history.

If the scorer is not very sure about a pass, the check still passes. You will see: *The judge wasn't very sure about this one.* That warning does not change exit 0/1.

## GitHub Action (optional secret)

```yaml
- uses: actions/setup-python@v5
  with: { python-version: "3.12" }
- run: pip install skillgate-ai==0.7.7
- run: skillgate check . --key-env DECISION_MODEL_API_KEY
  env:
    DECISION_MODEL_API_KEY: ${{ secrets.DECISION_MODEL_API_KEY }}
```

Do not add a required scoring secret to merge CI.

## Live smoke (not CI)

```bash
export DECISION_MODEL_API_KEY=sk-...     # never echo
skillgate check /path/to/one-case-pack --key-env DECISION_MODEL_API_KEY --json
# JSON names who scored. Exit 0 or 1. Never a traceback.
```

A decision model scores checks directly. Chat and Responses completion models are not judges.
