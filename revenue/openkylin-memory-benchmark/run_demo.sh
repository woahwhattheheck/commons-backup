#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OUT=${1:-"$HERE/build/demo"}
python3 -B "$HERE/kylin_memory_bench.py" compare \
  --dataset "$HERE/sample/dataset.jsonl" \
  --evidence "$HERE/sample/reference-agent.json" \
  --evidence "$HERE/sample/forgetful-agent.json" \
  --out-dir "$OUT"
echo "reports: $OUT"
