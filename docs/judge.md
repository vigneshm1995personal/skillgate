# Bring your own judge

A decision model scores each live check, and one is required. Live checks still need a signed-in agent (`skillgate login`) or a key. Scoring uses the decision model you pick in Settings, or with `skillgate judge provider set`. Skill Gate does not ship a model or an account. A key in the environment is ignored unless you pass `--key-env`.

## What you get

When a decision model is on and you run a live check (`skillgate check`, or Run in the local UI), Skill Gate asks the same fixed questions on each live task. The check passes only when those answers meet the bar (job done, correct, followed the rules, and so on). Every check still needs a signed-in agent (`skillgate login`) or a key. Without one, `skillgate check` exits 2. A live check also needs a decision model. With none selected, the check exits 2 and asks you to pick one. It does not fall back to another model.

Scorers such as "does the output contain this text?" and page counts still apply beside that decision model. Scoring does not compare the full output to the expected file. It reads the expected and actual text (and a few images) and judges whether the work is done. Built-in checks grade against the test's expected outcome (golden / contains). If that outcome is an escalation or refusal — a refund that cannot be issued, a column the schema does not list — doing it is Fully completed, not unfinished. Pass `--no-judge` only when you mean to skip the decision model. It still needs a signed-in agent. Without one, `skillgate check --no-judge` exits 2. To see a named red from a saved run with no agent, list run ids with `skillgate history --pack skills/json-response`, then `skillgate history show RUN --pack skills/json-response`.

Add extra scoring questions on top of Skill Gate's six (`skillgate judge add-question PACK`, or the Checks editor). Pass a skill pack. With none, the command stops and does not write to `skills/pdf`. Built-in questions cannot be deleted. They can be Warn only. Original checks in the bundled examples, including pdf, cannot be removed.

## Set up a decision model

A decision model scores each live check, and one is required. Each option below takes one key and only the fields listed. `skillgate keys set` prompts, or reads the value from stdin. Do not put the key on the command line.

**CI and Docker:** set the `SKILLGATE_*` name for that key. That prefix is the documented job path and is always read. A key that is only in the process environment is ignored unless you pass `--key-env`. Each decision model uses its own key. A missing key fails that check. Skill Gate does not switch to another decision model.

### OpenRouter

An OpenRouter key from <https://openrouter.ai/keys>. Skill Gate stores it as `JEV_API_KEY` because Jev is the OpenRouter decision model that scores the check.

Fields: base URL `https://openrouter.ai/api/v1`, model `typesafe/jev-1.14`, API key.

```bash
printf '%s\n' "$OPENROUTER_API_KEY" | skillgate keys set JEV_API_KEY
skillgate judge provider set jev --base-url https://openrouter.ai/api/v1 --model typesafe/jev-1.14
```

`skillgate judge provider set jev` fills that URL and model when you leave the flags off.

UI: `skillgate ui`, open Settings, choose OpenRouter, confirm Advanced shows that URL and model, paste the key, Save, then Test.

### OpenAI

An OpenAI key from <https://platform.openai.com/api-keys>. `skillgate judge provider set openai` uses model `gpt-6-luna`.

Field: API key.

```bash
printf '%s\n' "$OPENAI_API_KEY" | skillgate keys set OPENAI_API_KEY
skillgate judge provider set openai
```

UI: `skillgate ui`, open Settings, choose OpenAI, paste the key, Save, then Test.

### Cloudflare

A Cloudflare token from <https://dash.cloudflare.com/profile/api-tokens>. The account id is the id in the account URL. Replace `accountid` with that id. Letters and digits only.

Fields: account id, model (`clef` or `clef-flash`), token.

```bash
printf '%s\n' "$CLOUDFLARE_API_TOKEN" | skillgate keys set CLOUDFLARE_API_TOKEN
skillgate judge provider set clef --account-id accountid --model clef
```

UI: `skillgate ui`, open Settings, choose Cloudflare, enter the account id, pick `clef` or `clef-flash`, paste the token, Save, then Test.

### Custom endpoint

A key for the URL you enter.

Fields: base URL, model, API key. There is no fixed model list. Replace `MODEL` with the model name.

```bash
printf '%s\n' "$CUSTOM_DECISION_API_KEY" | skillgate keys set CUSTOM_DECISION_API_KEY
skillgate judge provider set custom --base-url https://example.com/v1 --model MODEL
```

UI: `skillgate ui`, open Settings, choose Custom endpoint, enter the base URL and model, paste the key, Save, then Test.

```bash
skillgate judge test
```

`skillgate judge provider test` runs the same check.

### Troubleshooting

- `This API key was rejected.` The key is wrong for this option, or it was revoked. Create a new key from the same page and run `skillgate keys set` for that option again.
- `This key is for a different endpoint.` The URL is not a scoring URL. OpenRouter uses `https://openrouter.ai/api/v1`.
- `This account is out of credits.` Add credits on that account, then run `skillgate judge test`.
- This looks like an OpenRouter key. Switch to OpenRouter with `skillgate judge provider set jev`. Run that command, or press Switch.
- `OpenAI does not use a base URL. It only needs an API key.` Run `skillgate judge provider set openai`.
- `Cloudflare scores only with clef or clef-flash. Choose OpenRouter for typesafe/jev-1.14.` That option does not score `typesafe/jev-1.14`. Use `--model clef` or `--model clef-flash`, or switch to OpenRouter.
- `OpenRouter scores only with typesafe/jev-1.14. Choose Cloudflare for clef or clef-flash.` Use `--model typesafe/jev-1.14`, or switch to Cloudflare and pick `clef` or `clef-flash`.
- This decision model needs an API key. Add it in Settings, or with `skillgate keys set`. Save the key named above.
- `This decision model needs a base URL.` Pass `--base-url`. OpenRouter's is `https://openrouter.ai/api/v1`.
- This decision model needs an account id. Set it with `skillgate judge provider set` and `--account-id`. Cloudflare needs that flag.
- `An account id uses letters and digits only.` A hyphen is not a missing account id.
- `That account id wasn't found.` A Cloudflare 404 means that account id does not exist. It is not "this key is for a different endpoint."
- `gpt-4o isn't a decision model.` A chat model on a custom endpoint is refused.
- Scoring errors do not include HTTP codes. A 404 or 405 from a non-scoring URL says this key is for a different endpoint.
- `skillgate judge provider show` and `set` print the option id, its model, and its base URL. With none selected, `show` prints `Pick a decision model before running a live check.` and exits 2.
- `This decision model needs a model.` Pass `--model`, or pick one from the list.
- `Pick a decision model before running a live check.` Run one `skillgate judge provider set` command above. A check that never starts is not saved as a scored failure.
- `The judge couldn't score this check. Retry — this is often temporary.` The scoring endpoint had a temporary error. Skill Gate retries those. If it still cannot score, the check cannot run (exit 2), not a quality red (exit 1). Run `skillgate judge test` again. The message never includes HTTP codes or a provider name.

A bad endpoint, rejected key, or empty balance fails that check. Chat and Responses completion models are not judges. Setting the judge backend to `responses`, `chat`, or `completions` fails the run. Older chat-style scoring setups fail until you pick a registered decision model.

`--key-env` on `set` stores the env var name in `.skillgate/judge`. The key stays in that environment variable. Skill Gate does not write the value.

| Env | Meaning |
| --- | --- |
| unset, `auto`, or `skip` | No decision model. A live check exits 2 and asks you to pick one. A saved key does not turn scoring on. |
| a decision-model endpoint id | Score with that decision model. A missing key exits 2. |

Bad key, no credits, 403, 400, timeout, or a scoring outage fails closed with a plain error. It never silently passes. When scoring cannot run, `skillgate check` exits 2, not 1 (a quality red). The key is never printed or stored in history.

If the scorer is not very sure about a pass, the check still passes. You will see: *The judge wasn't very sure about this one.* That warning does not change exit 0/1.

When a blocking answer's confidence is below 0.5, Skill Gate re-asks up to 3 times and takes a majority vote instead of failing on one unsure call. High-confidence fails still fail in one call. Custom checks and the pass mark are unchanged. The majority answer is what the check cells use. Individual votes are in `skillgate check --json` and `skillgate history show RUN --json` under `tasks[].judge.votes` (choice and confidence for each ask). The UI shows the majority result, not each ask.

Blocking questions fail the check (`on_fail` is Fail the check). By default that is the five built-in checks: **Got the job done?**, **Got it right?**, **Followed the rules?**, **Used the right evidence/actions?**, and **Delivered a good result?**. **How it ran** is Warn only. Extra questions you add default to Fail the check. A 0.33 on **Followed the rules?** is blocking, so it is re-asked.

A red names the failing check and includes the judge's reason. Example: `Got the job done? Not completed (need Fully completed) — The refund is impossible, so the bot told the customer.` CLI, GitHub summary, and the What happened column all use that line. After a run is saved, `skillgate history show RUN` prints it without calling an agent.

## GitHub Action (optional secret)

```yaml
- uses: vigneshm1995personal/skillgate@v1
  with:
    path: skills/pdf
    judge: jev
  env:
    SKILLGATE_JEV_API_KEY: ${{ secrets.SKILLGATE_JEV_API_KEY }}
```

Leave `version` unset for the latest release. Until 0.7.10 is published, install from source (`pip install -e .`) instead of pinning that version. The action reads `SKILLGATE_*` variables and does not print them. It does not switch to another decision model. Do not add a required scoring secret to merge CI.

A manual install still works:

```yaml
- uses: actions/setup-python@v5
  with: { python-version: "3.12" }
- run: pip install skillgate-ai
- run: skillgate check . --key-env DECISION_MODEL_API_KEY
  env:
    DECISION_MODEL_API_KEY: ${{ secrets.DECISION_MODEL_API_KEY }}
```

Until 0.7.10 is published, replace that install with `pip install -e .` from a clone of this repo.

## Live smoke (not CI)

```bash
export DECISION_MODEL_API_KEY=sk-...     # never echo
skillgate check /path/to/one-case-pack --key-env DECISION_MODEL_API_KEY --json
# JSON names who scored. Exit 0 or 1. Never a traceback.
```

A decision model scores checks directly. Chat and Responses completion models are not judges.
