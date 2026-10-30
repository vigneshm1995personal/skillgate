# Writing a dataset

A dataset is the pinned cases in `evals/cases.yaml`, the inputs under `evals/fixtures/`, and the expected files under `evals/goldens/`. `skillgate check` runs those cases with an agent. This page is the layout, a copy-paste pack, how to write the cases, and how to run them.

The shipped examples are the same shape. Install them with `skillgate examples install`, then open one folder and read it next to this page.

## File layout

The folder name, the `name` in `SKILL.md`, and `skill` in `evals/cases.yaml` are the same string.

```
json-response/
  SKILL.md
  scripts/agent_entry.py
  evals/
    cases.yaml
    fixtures/
      orders.json
      empty-orders.json
    goldens/
      flatten-orders.json
      edge-empty.json
    history/
```

`evals/history/` is where check runs are appended. You can leave it empty. Paths in the YAML are relative to the skill folder.

## Minimal example

This is the empty-input case from `json-response`, trimmed to one case. The full pack on disk has two more.

`SKILL.md`:

```markdown
---
name: json-response
description: Reshape a JSON API response. Flatten nested fields to id, status, and total, and drop empty values. Use when the user has a JSON response.
---

# JSON response

Flatten each object under `data` to `id`, `status`, and `total`. An empty `data` array becomes `[]`.
```

`evals/fixtures/empty-orders.json`:

```json
{
  "data": []
}
```

`evals/goldens/edge-empty.json`:

```json
[]
```

`evals/cases.yaml`:

```yaml
schema: 1
skill: json-response
cases:
  - id: edge-empty
    status: pinned
    prompt: Flatten the JSON API response in empty-orders.json. Save output/orders.json.
    should_trigger: true
    input:
      files:
        - src: evals/fixtures/empty-orders.json
          dest: empty-orders.json
    golden:
      output_path: output/orders.json
      path: evals/goldens/edge-empty.json
      kind: json
    contains:
      - "[]"
```

`status: pinned` is what runs. `input.files[].dest` is the name the agent sees in the workspace. `golden.output_path` is the file the agent must write. `golden.path` is the expected file in the pack. `kind` is `text`, `json`, or `bytes`. `contains` lists substrings that must appear in that output. `should_trigger: false` means an unrelated prompt; leave `input.files` empty and set `golden: null`.

## What each example tests

| Skill | Main case | Edge | Should not trigger |
| --- | --- | --- | --- |
| `json-response` | Flatten two orders to id, status, and total | Empty `data` becomes `[]` | A pytest prompt |
| `readme-writer` | README from `brief.txt`, including install and usage | Missing license renders `not specified` | A log-summary prompt |
| `log-summarizer` | Two timeouts and one rate-limit warning | A quiet log is `Errors: 0` | A README prompt |
| `sql-writer` | `id` and `total` for open orders | Ask for `customer_email`, which the schema does not have | A JSON prompt |
| `receipt-extractor` | Merchant, date, and total `18.40` from a fictional receipt | A receipt with no total stays `null` | A SQL prompt |

`json-response-sabotaged` copies the JSON cases and the fixtures. Its instructions tell the agent to ignore JSON and write a snack list. A live check of that pack fails the trigger cases. The unrelated case can still pass. That is the red path.

## How to write a case

Start with **3 to 6 pinned cases**. Each example ships three: one main behavior, one edge, and one unrelated prompt. Add cases when a bug shows up, not before.

- **One behavior per case.** `flatten-orders` only checks the flat list. `edge-empty` only checks `[]`. A prompt that asks for both is two cases.
- **Realistic inputs.** `orders.json` is two short API objects. `harbor-receipt.txt` is a fictional shop receipt. `schema.sql` is one table. The agent should be able to finish the task from that file.
- **Clear expected outcomes.** Put the full expected file in `evals/goldens/` and the lines that must appear in `contains`. `readme-writer` expects the heading `Harbor Notes` and the install line `pip install harbor-notes`. `sql-writer` expects `SELECT id, total` and `status = 'open'`.
- **Escalation or refusal is a valid expected outcome.** Put what the agent should do in the golden and `contains`, not a success the user prompt might imply. Built-in checks grade against that expected outcome. If the right answer is to refuse or escalate — a missing column, a refund that cannot be issued — doing that is Fully completed. `sql-writer` case `edge-unknown-column` expects `customer_email is missing from schema.sql`, not a query that invents the column. A refund case whose golden says tell the customer and write an owner report is done when the agent does that.
- **An edge case.** Empty, missing, or zero. `log-summarizer` uses a log with no errors. `receipt-extractor` uses a receipt whose total line is absent. `sql-writer` asks for a column the schema does not list, and the expected file says that column is missing.
- **One case that should fail when the skill is wrong.** Set `should_trigger: false` on a prompt from a different job. If the skill triggers, that case fails. To see a whole pack fail, check `json-response-sabotaged`. `skillgate check skills/json-response-sabotaged --expect-fail` exits 0 only when that run is red.
- **No answer leakage.** The expected sentence stays out of the prompt. The receipt prompt says to extract the total. It does not contain `18.40`. The README edge prompt says not to invent a license. It does not contain `not specified`. That phrase is only in the golden.
- **Small files.** Each example file is under 4 KB. A case should stay a fixture, not a dump of a production system.
- **No personal data.** Use fictional names and ids. The receipt merchant is Harbor Paper Co. There is no email address, phone number, or card number in the examples.

## Check it locally

From the directory that contains `skills/` (an empty directory after `skillgate examples install`):

```bash
skillgate ingest skills/json-response
skillgate case list skills/json-response
skillgate check skills/json-response
skillgate check skills/json-response --case flatten-orders
skillgate check skills/json-response-sabotaged
skillgate check skills/json-response-sabotaged --expect-fail
```

`skillgate ingest` prints `OK  json-response` when `SKILL.md` loads. `skillgate case list` prints each id, `pinned`, and the prompt. `skillgate check` exits 0 when the live run is green, 1 when it is red, and 2 when no agent is available or no decision model is selected. Sign in with `skillgate login` or `skillgate keys set`, then `skillgate judge provider set <endpoint>`. Without those, the check exits 2. That is not a pass.

Match those commands in the UI:

```bash
skillgate ui
```

1. Click **Skills**. The page title is Skill Repository.
2. Click **Examples**, then **Install**.
3. Open `json-response`. Click **Evaluate this skill**. The cases from `evals/cases.yaml` are the checks.
4. Click **Run**. The label is `Run 3 cases` when three checks are loaded. Until you sign in or add a key, the line above the button is `Next: sign in or add a key in Settings, then press Run.`
5. For the red path, open `json-response-sabotaged` and press **Run**. The JSON checks fail. The unrelated check can pass.

`skillgate case list` and **View Dataset** on the skill page show the same cases. A live result comes from **Run** or `skillgate check`.

A red names the failing check and includes the judge's reason, for example `Got the job done? Not completed (need Fully completed) — …`. How majority re-asking works, where to read `tasks[].judge.votes`, and that `--no-judge` still needs an agent are in [Bring your own judge](judge.md).

## Common mistakes

| What you see | Fix |
| --- | --- |
| Ingest says the name does not match the folder | Use one slug for the folder, `name` in `SKILL.md`, and `skill` in `cases.yaml`. `receipt-extractor` uses `receipt-extractor` in all three. |
| `skillgate case list` shows the case, and `skillgate check` skips it | Set `status: pinned`. Draft cases stay on disk and do not run. |
| The fixture is missing at check time | `src` is relative to the skill folder, for example `evals/fixtures/orders.json`. The file has to be there. |
| A `.md` brief never shows up as an input file | Case inputs use a data suffix. `readme-writer` stores the brief as `brief.txt`. Expected READMEs stay under `evals/goldens/` and can be `.md`. |
| The golden is not found | `golden.path` points at `evals/goldens/<file>`. `output_path` is where the agent writes, usually `output/<file>`. |
| The check passes because the prompt already contained the answer | Move that sentence into the golden and `contains`. Read `receipt-extractor` case `extract-total`: `18.40` is in the fixture and the golden, not in the prompt. |
| Every case is the happy path | Add the edge and the `should_trigger: false` case. Each example has both. |
| The pack is huge, or it contains a real email or phone number | Shrink the fixture and replace the value with a fictional one, the way `harbor-receipt.txt` does. |
| `skillgate examples install` prints `Left N existing file(s) in place.` and your edit is still there | That command never replaces a file that already exists. Delete the file you want replaced, or install into an empty folder with `--dest`. |
