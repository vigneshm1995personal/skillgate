# 10-minute quickstart (no account)

Skill Gate’s public CLI is a **local gate**. You do not sign up and you do not need a Skill Gate account. Install the example datasets, then run one green check and one red check.

Requires **Python 3.11+**.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install skillgate-ai
skillgate version           # 0.7.9
```

(`pip install skillgate` is a different product.) From a clone of this repo you can use `pip install -e .` instead.

Skill scripts run with that same Python — install the skill’s own packages there too (the pdf example needs `pypdf`).

## Example datasets

In an empty directory:

```bash
skillgate examples list
skillgate examples install
```

`skillgate examples install` writes these folders under `skills/`:

| Skill | What the dataset checks |
| --- | --- |
| `json-response` | Flatten a JSON API body to `id`, `status`, and `total` |
| `json-response-sabotaged` | The same JSON cases, with instructions that ignore them |
| `readme-writer` | Turn a project brief into a README |
| `log-summarizer` | Count errors and warnings in a log |
| `sql-writer` | Write a SQL query from a table schema |
| `receipt-extractor` | Read merchant, date, and total from a fictional receipt |

Files already in the destination stay as they are. A second install prints `Left N existing file(s) in place.` Install one skill with `skillgate examples install json-response`. Another folder: `skillgate examples install --dest /path/to/skills`.

## Keys

Sign in with the agent CLI (subscription login) or set a key. `skillgate login --status` labels them Editor agent, Code agent, and Terminal agent. Skill Gate does not read `OPENAI_API_KEY` from the shell unless you pass `--key-env`. CI and Docker still use a key (vault, Settings, or the `SKILLGATE_*` prefix):

```bash
skillgate login                  # cursor | claude | codex; omit to sign in missing agents
skillgate login --status         # installed / logged in / API key / none
# Editor agent:
printf '%s\n' "$CURSOR_API_KEY" | skillgate keys set CURSOR_API_KEY
# Code agent:
printf '%s\n' "$ANTHROPIC_API_KEY" | skillgate keys set ANTHROPIC_API_KEY
# Terminal agent:
printf '%s\n' "$CODEX_API_KEY" | skillgate keys set CODEX_API_KEY
# or paste in Settings (`skillgate ui`)
skillgate judge provider set <endpoint>
```

A decision-model key is not an agent login. Pick a decision model before a live check. With none selected, `skillgate check` exits 2 and asks you to pick one. Commands for each option are in [Set up a decision model](judge.md#set-up-a-decision-model). Every check is a live agent run. Without `skillgate login` or a key, `skillgate check` exits 2. Default results say "Scored by the judge" when a decision model scored the run.

## A pass and a fail

```bash
skillgate check skills/json-response
echo $?    # 0 when the live run is green; 2 until an agent and a decision model are ready
skillgate check skills/json-response-sabotaged
echo $?    # 1 when the JSON checks fail. The unrelated check can pass.
skillgate check skills/json-response-sabotaged --expect-fail
echo $?    # 0 only when that live run is red; 2 when no agent is available
```

`json-response` has three pinned cases: flatten two orders, flatten an empty list, and an unrelated pytest prompt that should not trigger the skill. `json-response-sabotaged` keeps those cases and writes a snack list instead of the JSON, so the trigger cases fail.

One case:

```bash
skillgate check skills/json-response --case flatten-orders
```

Confirm the files before a live run:

```bash
skillgate ingest skills/json-response
skillgate case list skills/json-response
```

## The same steps in the UI

```bash
skillgate ui                 # http://127.0.0.1:8765 — no account
```

1. Click **Skills**. The page title is Skill Repository.
2. Click **Examples**, then **Install**. Existing files stay as they are.
3. Open `json-response`. Click **Evaluate this skill**.
4. Click **Run**. With the three cases loaded, the label is `Run 3 cases`. Until you sign in or add a key, the line above the button is `Next: sign in or add a key in Settings, then press Run.` A live check also needs a decision model. With none selected, the check exits 2.
5. Open `json-response-sabotaged` and press **Run** again. The JSON checks fail. The unrelated check can pass.

Same `run_check` engine as the CLI. See [ui.md](https://github.com/vigneshm1995personal/skillgate/blob/main/docs/ui.md). The Docker image still runs `skillgate check /pack`; do not treat the UI as `serve`.

## The pdf example

`skillgate example pdf` still copies the PDF pack. It refuses to write when the destination folder already exists. The dataset command above does not replace it.

```bash
skillgate example pdf
skillgate check skills/pdf
echo $?    # 0 when the live run is green; 2 until an agent and a decision model are ready
```

The sabotaged PDF example has a meal-planner description, so PDF prompts never trigger it:

```bash
skillgate example pdf-sabotaged
skillgate check skills/pdf-sabotaged
echo $?    # 1 when the live run is red; 2 until an agent and a decision model are ready
```

Intentional-fail CI:

```bash
skillgate check skills/pdf-sabotaged --expect-fail
echo $?    # 0 only when that live run is red
```

## Deploy (after a green check)

`skillgate deploy` copies **only the skill files** (not `evals/`) into the signed-in agent's skills folder (Editor agent, Code agent, or Terminal agent). It refuses unless this pack already has a passing check **and an agent is available** (`skillgate login`, vault, Settings, or `SKILLGATE_*`). It does not run check for you. Without an agent, Deploy stays blocked even after a green check; the pointer is `skillgate login` or Settings / `skillgate keys set`.

```bash
skillgate check skills/pdf
skillgate deploy skills/pdf
skillgate deploy skills/pdf --target claude
skillgate deploy skills/pdf --targets cursor,codex
```

## Docker (optional)

Multi-stage image, non-root UID 1001, `ENTRYPOINT ["skillgate"]`, `CMD ["check", "/pack"]`. Keyless `check` exits 2. Clone this repo first (`compose.yaml` lives here):

```bash
git clone https://github.com/vigneshm1995personal/skillgate.git
cd skillgate
docker compose run --rm --no-TTY skillgate example pdf --dest /tmp/pdf
```

## Copy-paste Action

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
          version: 0.7.9
          judge: jev
        env:
          SKILLGATE_JEV_API_KEY: ${{ secrets.SKILLGATE_JEV_API_KEY }}
```

`version: 0.7.9` installs `skillgate-ai==0.7.9`. Leave `version` unset for the latest release. Pass keys as `SKILLGATE_*` variables. Or set `SKILLGATE_OPENAI_API_KEY` instead of `--key-env`. The `SKILLGATE_*` key names are the documented CI/Docker path and are always read.
