#!/usr/bin/env bash
# Run CLINVEIL on the practice data and pass the output through the organiser's
# UNMODIFIED tools: validate_output.py, check_dev.py and (optionally) check_submission.py.
#
#   backend/scripts/official_checks.sh            # validate + dev self-check
#   backend/scripts/official_checks.sh --submit   # also check_submission.py --run (3 runs)
#
# Env: CLINVEIL_TOOLKIT (default ./organiser-toolkit), CLINVEIL_OUT (default: a mktemp dir),
# RAKSHA_SECRET (default: a fresh random value per invocation; nothing is committed).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TK="${CLINVEIL_TOOLKIT:-$REPO/organiser-toolkit}"
PY="${PYTHON:-python3}"
OUT="${CLINVEIL_OUT:-$(mktemp -d "${TMPDIR:-/tmp}/clinveil-out.XXXXXX")}"

[[ -f "$TK/validate_output.py" ]] || { echo "organiser toolkit not found at $TK" >&2; exit 2; }
# Only ever clear a directory that is empty or is a previous CLINVEIL output.
if [[ -d "$OUT" && -n "$(ls -A "$OUT")" ]]; then
  [[ -f "$OUT/report.json" && -d "$OUT/sanitized" ]] || { echo "refusing to clear non-output dir: $OUT" >&2; exit 2; }
  rm -rf "$OUT"
fi
mkdir -p "$OUT"

RAKSHA_SECRET="${RAKSHA_SECRET:-$("$PY" -c 'import secrets; print(secrets.token_hex(16))')}"
export RAKSHA_SECRET

echo "== run (output: $OUT)"
"$PY" "$REPO/main.py" --input "$TK/dev/input" --output "$OUT"

echo "== validate_output.py"
"$PY" "$TK/validate_output.py" --input "$TK/dev/input" --output "$OUT"

echo "== check_dev.py"
"$PY" "$TK/check_dev.py" --output "$OUT"

if [[ "${1:-}" == "--submit" ]]; then
  echo "== check_submission.py --run"
  "$PY" "$TK/check_submission.py" --repo "$REPO" --run
fi
