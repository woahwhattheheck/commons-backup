#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TMP=${TMPDIR:-/tmp}/evidenceaar-demo-$$
trap 'rm -rf "$TMP"' EXIT INT TERM
mkdir "$TMP"
python3 "$HERE/workbench.py" compile "$HERE/fixtures/synthetic_exercise.json" -o "$TMP/bundle.json"
python3 "$HERE/workbench.py" verify "$HERE/fixtures/synthetic_exercise.json" "$TMP/bundle.json"
python3 "$HERE/workbench.py" render "$HERE/fixtures/synthetic_exercise.json" "$TMP/rendered"
python3 - "$TMP/rendered/receipt.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    receipt=json.load(f)
print("exercise:", receipt["exercise_id"])
print("sources:", receipt["source_count"], "events:", receipt["event_count"])
print("aar_sha256:", receipt["aar_sha256"])
print("external authority:", receipt["authority"])
PY
