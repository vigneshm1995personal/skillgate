#!/usr/bin/env bash
# Fresh-env smoke test for README quickstart (PyPI skillgate-ai==0.6.1).
set -euo pipefail
WORKDIR="${VERIFY_WORKDIR:-/tmp/skillgate-readme-verify}"
HOME_DIR="${VERIFY_HOME:-/tmp/skillgate-readme-verify-home}"
rm -rf "$WORKDIR" "$HOME_DIR"
mkdir -p "$WORKDIR" "$HOME_DIR"
export HOME="$HOME_DIR"
cd "$WORKDIR"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q "skillgate-ai==0.6.1"
echo "=== skillgate version ==="
skillgate version
echo "=== skillgate init ==="
skillgate init
echo "=== sample-skill example (pending PyPI) ==="
if skillgate example sample-skill --dest skills/sample-skill 2>&1; then
  echo "sample_skill_example=pass"
else
  echo "sample_skill_example=pending_release"
fi
echo "=== fallback: pdf example on 0.6.1 ==="
skillgate example pdf
set +e
skillgate check skills/pdf; pdf_ec=$?
echo "pdf_check_exit=$pdf_ec"
echo "=== skillgate new verify-skill ==="
skillgate new verify-skill
skillgate check skills/verify-skill; new_ec=$?
echo "new_skill_check_exit=$new_ec"
skillgate deploy skills/verify-skill; deploy_ec=$?
echo "deploy_exit=$deploy_ec"
set -e
skillgate ui --help | head -3
