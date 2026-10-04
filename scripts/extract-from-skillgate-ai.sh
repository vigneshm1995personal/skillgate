#!/usr/bin/env bash
# Copy allowlisted paths from a local skillgate-ai checkout into this repo.
# Usage: scripts/extract-from-skillgate-ai.sh /path/to/skillgate-ai 6372ba1
set -euo pipefail

SRC="${1:?path to skillgate-ai checkout}"
SHA="${2:-}"
DEST="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -n "$SHA" ]]; then
  git -C "$SRC" rev-parse --verify "$SHA^{commit}" >/dev/null
fi

DENY=(
  src/skillgate_ai/auth_siwv.py
  src/skillgate_ai/vault.py
  src/skillgate_ai/store.py
  src/skillgate_ai/store_postgres.py
  src/skillgate_ai/web.py
  src/skillgate_ai/eval_slice.py
  src/skillgate_ai/jev_qa.py
  src/skillgate_ai/author.py
  src/skillgate_ai/wizard.py
  src/skillgate_ai/stage_b.py
  src/skillgate_ai/deploy_git.py
  Dockerfile.vercel
)

ALLOW=(
  LICENSE
  src/skillgate_ai/__init__.py
  src/skillgate_ai/advice.py
  src/skillgate_ai/case_pack.py
  src/skillgate_ai/cli.py
  src/skillgate_ai/config.py
  src/skillgate_ai/demo_files.py
  src/skillgate_ai/deploy.py
  src/skillgate_ai/engine.py
  src/skillgate_ai/errors.py
  src/skillgate_ai/eval_config.py
  src/skillgate_ai/fixture_bind.py
  src/skillgate_ai/harness.py
  src/skillgate_ai/ingest.py
  src/skillgate_ai/live.py
  src/skillgate_ai/metrics.py
  src/skillgate_ai/observability.py
  src/skillgate_ai/pack.py
  src/skillgate_ai/paths.py
  src/skillgate_ai/report.py
  src/skillgate_ai/sandbox.py
  src/skillgate_ai/scorers.py
  src/skillgate_ai/spans.py
  src/skillgate_ai/suite.py
  src/skillgate_ai/usage.py
)

for rel in "${DENY[@]}"; do
  if [[ -e "$DEST/$rel" ]]; then
    echo "refuse: deny-list path already in destination: $rel" >&2
    exit 1
  fi
done

mkdir -p "$DEST/src/skillgate_ai"
for rel in "${ALLOW[@]}"; do
  if [[ -f "$SRC/$rel" ]]; then
    cp "$SRC/$rel" "$DEST/$rel"
  fi
done

if [[ -d "$DEST/src/skillgate_ai/remote_harness" ]] || [[ -d "$DEST/src/skillgate_ai/web" ]] || [[ -d "$DEST/web" ]]; then
  echo "refuse: hosted tree appeared in destination" >&2
  exit 1
fi

echo "copied allowlist from $SRC into $DEST (strip hosted imports next)"
