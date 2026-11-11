# Scripted QA

`scripts/qa.sh` runs the QA groups with no AI chat. It builds a fresh venv with `uv`, uses a throwaway `HOME` under a temp dir (your real `HOME` is never touched), installs this checkout, sets the judge provider, and prints one `PASS`/`FAIL` line per check against its expected green/red.

```bash
export SKILLGATE_ANTHROPIC_API_KEY=...   # agent key for --harness claude
export SKILLGATE_OPENAI_API_KEY=...      # judge key (default provider: openai)
scripts/qa.sh                            # everything
scripts/qa.sh --only examples:pdf,rescore --repeat 3 --parallel 2
scripts/qa.sh --list
```

Flags: `--only a,b` (check names, group names, or bare example names), `--repeat N` (1), `--harness H` (claude), `--fail-fast`, `--parallel N` (4).

| Group | Checks | Needs keys |
| --- | --- | --- |
| `examples` | the 8 bundled skills; `*-sabotaged` must be red (exit 1) | yes (live) |
| `guard` | reply-guard cases (retry warning, double refund, not-yet, duplicate) | no |
| `adv-amt` | copied USD 4.90 vs billing log 49.00 is red | no |
| `rescore` | six saved runs re-scored with `skillgate rescore` | no |

Live exit 2 ("cannot run") is a FAIL, never a pass. Keys are read only from `SKILLGATE_*` env vars; logs are redacted of those values. Judge: `SKILLGATE_QA_JUDGE` (default `openai`) and `SKILLGATE_QA_JUDGE_ARGS` for extra `judge provider set` flags.

Output: `qa-results.json` (`QA_OUT` to move it) plus `qa-results-logs/`. Exit is nonzero on any FAIL; rerun failures with `--only`.
