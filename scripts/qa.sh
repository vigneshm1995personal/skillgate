#!/usr/bin/env bash
# Scripted QA: fresh venv + throwaway HOME, then named check groups, one PASS/FAIL line each.
# See docs/QA.md. Keys come only from SKILLGATE_* env vars and are never printed.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UV="${UV:-$HOME/.local/bin/uv}"

# name|group|kind|arg|expect   (kind: live = skillgate check, pytest = node id, py = qa_offline.py)
CHECKS='
examples:json-response|examples|live|json-response|green
examples:json-response-sabotaged|examples|live|json-response-sabotaged|red
examples:log-summarizer|examples|live|log-summarizer|green
examples:pdf|examples|live|pdf|green
examples:pdf-sabotaged|examples|live|pdf-sabotaged|red
examples:readme-writer|examples|live|readme-writer|green
examples:receipt-extractor|examples|live|receipt-extractor|green
examples:sql-writer|examples|live|sql-writer|green
guard:refused-retry-is-warning|guard|pytest|tests/test_qa_0714_refused_retry.py::test_guard_refused_retry_is_a_warning_not_a_fail|green
guard:two-succeeded-stay-red|guard|pytest|tests/test_qa_0714_refused_retry.py::test_two_succeeded_refunds_still_fail|red
guard:notyet-stays-red|guard|pytest|tests/test_qa_0722_r12.py::test_notyet_stored_violated_stays_red_without_remap|red
guard:guarded-duplicate-stays-red|guard|pytest|tests/test_qa_0722_r12.py::test_dupx_guarded_stored_incorrect_stays_red_without_remap|red
adv-amt:wrong-amount|adv-amt|py|adv-amt|red
rescore:refund-twice-one-done|rescore|py|rescore refund-twice-one-done|red
rescore:timeout-success-double|rescore|py|rescore timeout-success-double|red
rescore:guard-refused|rescore|py|rescore guard-refused|green
rescore:both-succeeded|rescore|py|rescore both-succeeded|red
rescore:rg4-negation|rescore|py|rescore rg4-negation|green
rescore:wrong-amount|rescore|py|rescore wrong-amount|red
'

usage() {
  cat <<USAGE
usage: scripts/qa.sh [--only a,b] [--repeat N] [--harness H] [--fail-fast] [--parallel N] [--list]
  --only        check names, group names (examples, guard, adv-amt, rescore) or bare example names
  --repeat      run each check N times (default 1)
  --harness     agent harness for live example checks (default claude)
  --fail-fast   stop starting new checks after the first FAIL
  --parallel    concurrent checks (default 4)
env: SKILLGATE_* keys (e.g. SKILLGATE_ANTHROPIC_API_KEY, SKILLGATE_OPENAI_API_KEY);
     SKILLGATE_QA_JUDGE (judge provider, default openai); SKILLGATE_QA_JUDGE_ARGS (extra flags);
     QA_OUT (results path, default ./qa-results.json)
USAGE
}

# ---- worker mode: run one check (invoked via xargs) ----
if [ "${1:-}" = "--_one" ]; then
  name="$2"; rep="$3"
  line="$(printf '%s\n' "$CHECKS" | grep -F "$name|" | head -1)"
  IFS='|' read -r _ group kind arg expect <<<"$line"
  id="${name//[:\/]/_}.$rep"
  if [ -e "$QA_TMP/stop" ]; then
    printf '{"check":"%s","group":"%s","rep":%s,"expected":"%s","status":"SKIP"}\n' "$name" "$group" "$rep" "$expect" >"$QA_TMP/rows/$id.json"
    printf 'SKIP %s (rep %s)\n' "$name" "$rep"; exit 0
  fi
  work="$QA_TMP/work/$id"; mkdir -p "$work"; log="$QA_LOGS/$id.log"
  start=$(date +%s)
  case "$kind" in
    live)
      cp -R "$REPO/skills/$arg" "$work/$arg"
      (cd "$work" && "$QA_TMP/venv/bin/skillgate" check "$arg" --harness "$QA_HARNESS") >"$log.raw" 2>&1; rc=$?
      # green: exit 0. red: exit 1 (exit 2 = could not run, never a pass)
      if [ "$expect" = green ]; then [ $rc -eq 0 ] && ok=1 || ok=0; else [ $rc -eq 1 ] && ok=1 || ok=0; fi ;;
    pytest)
      (cd "$REPO" && "$QA_TMP/venv/bin/python" -m pytest -q -x "$arg") >"$log.raw" 2>&1; rc=$?
      [ $rc -eq 0 ] && ok=1 || ok=0 ;;
    py)
      # shellcheck disable=SC2086
      (cd "$work" && "$QA_TMP/venv/bin/python" -I "$REPO/scripts/qa_offline.py" $arg) >"$log.raw" 2>&1; rc=$?
      [ $rc -eq 0 ] && ok=1 || ok=0 ;;
  esac
  secs=$(( $(date +%s) - start ))
  "$QA_TMP/venv/bin/python" -I "$REPO/scripts/qa_offline.py" redact <"$log.raw" >"$log"; rm -f "$log.raw"
  if [ $ok -eq 1 ]; then status=PASS; else status=FAIL; [ -n "$QA_FAIL_FAST" ] && touch "$QA_TMP/stop"; fi
  printf '{"check":"%s","group":"%s","rep":%s,"expected":"%s","status":"%s","exit_code":%s,"seconds":%s,"log":"%s"}\n' \
    "$name" "$group" "$rep" "$expect" "$status" "$rc" "$secs" "$log" >"$QA_TMP/rows/$id.json"
  printf '%s %s (rep %s, expect %s, exit %s, %ss)\n' "$status" "$name" "$rep" "$expect" "$rc" "$secs"
  exit 0
fi

only=""; repeat=1; harness=claude; fail_fast=""; parallel=4
while [ $# -gt 0 ]; do
  case "$1" in
    --only) only="$2"; shift 2 ;;
    --repeat) repeat="$2"; shift 2 ;;
    --harness) harness="$2"; shift 2 ;;
    --fail-fast) fail_fast=1; shift ;;
    --parallel) parallel="$2"; shift 2 ;;
    --list) printf '%s\n' "$CHECKS" | grep . | cut -d'|' -f1; exit 0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown flag: $1" >&2; usage >&2; exit 2 ;;
  esac
done

# ---- select checks ----
selected=""
while IFS='|' read -r name group _; do
  [ -z "$name" ] && continue
  if [ -z "$only" ]; then selected="$selected $name"; continue; fi
  IFS=',' read -ra wanted <<<"$only"
  for w in "${wanted[@]}"; do
    if [ "$w" = "$name" ] || [ "$w" = "$group" ] || [ "$w" = "${name#*:}" ]; then selected="$selected $name"; break; fi
  done
done <<<"$CHECKS"
if [ -z "$selected" ]; then echo "no checks match --only '$only' (see --list)" >&2; exit 2; fi

# ---- throwaway sandbox: venv + HOME under a temp dir, never the real HOME ----
QA_TMP="$(mktemp -d "${TMPDIR:-/tmp}/skillgate-qa.XXXXXX")"
out="${QA_OUT:-$PWD/qa-results.json}"
QA_LOGS="${out%.json}-logs"; rm -rf "$QA_LOGS"
mkdir -p "$QA_TMP/home" "$QA_TMP/rows" "$QA_LOGS" "$QA_TMP/work"
trap 'rm -rf "$QA_TMP"' EXIT

echo "setup: venv + local checkout in $QA_TMP"
"$UV" venv -q --python ">=3.11" "$QA_TMP/venv" || { echo "FAIL setup: uv venv" >&2; exit 2; }
HOME="$QA_TMP/home" "$UV" pip install -q -p "$QA_TMP/venv/bin/python" -e "$REPO[dev]" >"$QA_TMP/install.log" 2>&1 \
  || { echo "FAIL setup: install (see below)" >&2; tail -5 "$QA_TMP/install.log" >&2; exit 2; }

export HOME="$QA_TMP/home" XDG_CONFIG_HOME="$QA_TMP/home/.config" XDG_DATA_HOME="$QA_TMP/home/.local/share"
export PATH="$QA_TMP/venv/bin:$PATH"
export QA_TMP QA_LOGS QA_HARNESS="$harness" QA_FAIL_FAST="$fail_fast"

# judge provider (key is read from the matching SKILLGATE_* env var, never echoed)
# shellcheck disable=SC2086
skillgate judge provider set "${SKILLGATE_QA_JUDGE:-openai}" ${SKILLGATE_QA_JUDGE_ARGS:-} >"$QA_TMP/judge.log" 2>&1 \
  || echo "warn: judge provider set failed; live checks will exit 2 (see judge.log)" >&2

# ---- run ----
export REPO CHECKS
jobs=""
for ((r = 1; r <= repeat; r++)); do for n in $selected; do jobs="$jobs$n $r"$'\n'; done; done
printf '%s' "$jobs" | xargs -P "$parallel" -L 1 bash "$REPO/scripts/qa.sh" --_one

"$QA_TMP/venv/bin/python" -I "$REPO/scripts/qa_offline.py" report "$QA_TMP/rows" "$out"
