<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="web/public/sg-mark-dark.svg">
    <img alt="skillgate" src="web/public/sg-mark-light.svg" width="96" height="96">
  </picture>
</p>

<h1 align="center">skillgate</h1>

<p align="center">A local gate for agent skills.</p>

<p align="center">
  <a href="https://pypi.org/project/skillgate-ai/"><img alt="PyPI" src="https://img.shields.io/pypi/v/skillgate-ai"></a>
  <a href="https://pypi.org/project/skillgate-ai/"><img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-blue"></a>
  <a href="https://github.com/vigneshm1995personal/skillgate/actions/workflows/gate.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/vigneshm1995personal/skillgate/gate.yml?branch=main&label=CI"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/github/license/vigneshm1995personal/skillgate"></a>
</p>

skillgate checks an agent skill that lives in a folder on your machine. A pack is `SKILL.md` plus `evals/`. `skillgate check` exits 0 when the run passes, 1 when it fails, and 2 when it cannot run. Live checks are scored only by a decision model you select. Requires Python 3.11+. The package name is `skillgate-ai` (`pip install skillgate` is a different project).

<p align="center">
  <img alt="Local UI on the pdf example, before a live check" src="docs/screenshots/readme-hero-light.png" width="880">
</p>

## Quickstart

In an empty directory:

```bash
pip install skillgate-ai
skillgate examples install
skillgate check skills/json-response
skillgate check skills/json-response-sabotaged
```

`skillgate examples install` writes six skills under `skills/`. Files already in that folder stay as they are. `skills/json-response` exits 0 when the live run is green. `skills/json-response-sabotaged` exits 1: the JSON checks fail, and the unrelated check can pass. Both checks exit 2 until an agent is available and a decision model is selected. Use `skillgate login` or `skillgate keys set` for the agent, and `skillgate judge provider set` for the decision model. These commands match release 0.7.9. A check that never starts is not saved. `skillgate import` of a skill already in this project stops and leaves the files alone. A decision-model key is not an agent login.

The same steps in the local UI:

```bash
skillgate ui
```

Open http://127.0.0.1:8765. Click **Skills**. On Skill Repository, click **Examples**, then **Install**. The toast reads `Installed 6 examples (47 files).` Open `json-response`, click **Evaluate this skill**, then **Run**. The button reads `Run 3 cases`. Until you sign in or add a key, the line above it is `Next: sign in or add a key in Settings, then press Run.` Repeat for `json-response-sabotaged` to see the failing checks.

## Set up a decision model

A decision model scores each live check, and one is required. Each option below takes one key and only the fields listed. `skillgate keys set` prompts, or reads the value from stdin. Do not put the key on the command line.

### OpenRouter

An OpenRouter key from <https://openrouter.ai/keys>, saved as the Jev key.

Fields: base URL `https://openrouter.ai/api/v1`, model `typesafe/jev-1.14`, API key.

```bash
printf '%s\n' "$JEV_API_KEY" | skillgate keys set JEV_API_KEY
skillgate judge provider set jev --base-url https://openrouter.ai/api/v1 --model typesafe/jev-1.14
```

`skillgate judge provider set jev` fills that URL and model when you leave the flags off.

UI: `skillgate ui`, open Settings, choose OpenRouter, confirm Advanced shows that URL and model, paste the key, Save, then Test.

### OpenAI

An OpenAI key from <https://platform.openai.com/api-keys>.

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
- `That account id wasn't found.` The account id in the URL does not exist.
- `gpt-4o isn't a decision model.` A chat model on a custom endpoint is refused. Scoring errors do not include HTTP codes.
- `This decision model needs a model.` Pass `--model`, or pick one from the list.
- `Pick a decision model before running a live check.` Run one `skillgate judge provider set` command above.
- `skillgate judge provider show` prints the option id, its model, and its base URL.

## Features

- One pack on disk, checked with `skillgate check`
- Exit 0 (pass), 1 (fail), or 2 (not ready)
- Live checks scored only by a decision model
- Custom scoring questions on top of the built-in questions
- `--expect-fail` for a pack that should fail
- Deploy copies skill files after a passing check
- Local UI with `skillgate ui`
- Compare two versions of the same dataset

## Usage

From the quickstart directory:

```bash
skillgate examples list
skillgate examples install json-response
skillgate check skills/json-response --case flatten-orders
skillgate check skills/json-response-sabotaged --expect-fail
skillgate example pdf
skillgate check skills/pdf
skillgate ingest skills/pdf
skillgate example pdf-sabotaged
skillgate check skills/pdf-sabotaged --expect-fail
skillgate deploy skills/pdf
skillgate judge provider show
skillgate judge add-question skills/pdf --ask "Did the answer follow the requested format?"
skillgate compare versions skills/pdf --dry-run
skillgate ui
```

`--expect-fail` exits 0 only when the live run is red. `skillgate deploy` copies the skill files after this pack already has a passing check. It does not run check for you. Deploy stays blocked until an agent is available, even after a green check. `skillgate ui` serves the local UI at http://127.0.0.1:8765. A version compare takes two `--run` ids or two `--git` refs. `skillgate example NAME` writes `skills/NAME`. `skillgate judge add-question` needs a skill pack. `skillgate case remove` keeps the original checks of the bundled examples.

Create a workspace and a skill:

```bash
skillgate init
skillgate new notes-helper
```

## Writing a dataset

A dataset is `evals/cases.yaml` plus small files in `evals/fixtures/` and expected files in `evals/goldens/`. The folder name, the `name` in `SKILL.md`, and `skill` in `cases.yaml` are the same string. Start with 3 to 6 pinned cases: one behavior, one edge, and one unrelated prompt (`should_trigger: false`). Keep the expected sentence out of the prompt. The examples do this: `json-response` flattens an API body, `readme-writer` turns a brief into a README, `log-summarizer` counts errors, `sql-writer` writes a query from a schema, and `receipt-extractor` reads a fictional receipt. `json-response-sabotaged` uses the same JSON cases and fails them.

Check a dataset on disk, then run it:

```bash
skillgate ingest skills/json-response
skillgate case list skills/json-response
skillgate check skills/json-response
```

In the UI, open the skill from Skill Repository and click **Evaluate this skill**, then **Run**.

The full guide, with a copy-paste pack and the mistakes that reject a dataset, is [Writing a dataset](docs/writing-a-dataset.md). The same page is on the docs site: [Writing a dataset](https://www.skill-gate-ai.app/docs/writing-a-dataset).

## Docker

```bash
docker compose run --rm --no-TTY skillgate
```

The image entrypoint is `skillgate`. The default command is `check /pack`. With no pack mounted, that path is missing and the command exits 2.

## GitHub Action

```yaml
name: skillgate
on: [push, pull_request]
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: vigneshm1995personal/skillgate@v1
        with:
          path: skills/pdf
          judge: jev
        env:
          SKILLGATE_JEV_API_KEY: ${{ secrets.SKILLGATE_JEV_API_KEY }}
```

`path` is a skill pack or a suite file. The default is `skills`. `version` is the `skillgate-ai` release to install. The default is the latest release. `judge` is the decision model id. `model`, `base-url`, and `account-id` are optional. `harness` is optional. `args` holds extra flags, such as `--no-judge` or `--expect-fail`.

Pass keys as `SKILLGATE_*` environment variables from the caller secrets. The action does not print those values. It does not switch to another decision model when `judge` is set.

Exit 0 passes, exit 1 fails, and exit 2 means the check cannot run. The job summary records that result.

## Editor MCP

Connect an editor to the Skill Gate MCP server at `https://mcp.skill-gate-ai.app` (`check_skill`, `run_eval`, `gate`). Auth is a Skill Gate token from GitHub sign-in on [skill-gate-ai.app](https://www.skill-gate-ai.app), passed as `Authorization: Bearer` from `SKILLGATE_TOKEN`. Full steps: [Editor MCP](docs/editors.md).

### Cursor

[Add to Cursor](https://cursor.com/install-mcp?name=skillgate&config=eyJ1cmwiOiJodHRwczovL21jcC5za2lsbC1nYXRlLWFpLmFwcCIsImhlYWRlcnMiOnsiQXV0aG9yaXphdGlvbiI6IkJlYXJlciAke2VudjpTS0lMTEdBVEVfVE9LRU59In19)

```
cursor://anysphere.cursor-deeplink/mcp/install?name=skillgate&config=eyJ1cmwiOiJodHRwczovL21jcC5za2lsbC1nYXRlLWFpLmFwcCIsImhlYWRlcnMiOnsiQXV0aG9yaXphdGlvbiI6IkJlYXJlciAke2VudjpTS0lMTEdBVEVfVE9LRU59In19
```

```json
{
  "mcpServers": {
    "skillgate": {
      "url": "https://mcp.skill-gate-ai.app",
      "headers": {
        "Authorization": "Bearer ${env:SKILLGATE_TOKEN}"
      }
    }
  }
}
```

`/gate-skill` runs `check_skill` on the open `SKILL.md`.

### Claude Code

```bash
claude mcp add --transport http skillgate https://mcp.skill-gate-ai.app --header "Authorization: Bearer ${SKILLGATE_TOKEN}"
```

This repo is a plugin marketplace (`claude plugin marketplace add vigneshm1995personal/skillgate`, then `claude plugin install skillgate@skillgate`). `/skillgate` runs the gate tools. An optional pre-commit hook ships with the plugin (off by default).

### Offline

No Skill Gate token: the local CLI is the offline bring-your-own-key path (`pip install skillgate-ai`, then `skillgate keys set` and `skillgate check`).

## Documentation

[Documentation](https://www.skill-gate-ai.app/docs)

## Contributing

Issues and pull requests are welcome.

## License

Apache License 2.0. See [LICENSE](LICENSE).
