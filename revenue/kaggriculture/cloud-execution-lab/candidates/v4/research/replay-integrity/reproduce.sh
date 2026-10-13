#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 2 ]]; then
  echo "Usage: $0 EXTRACTED_NATIVE_PACKAGE OUTPUT_DIRECTORY" >&2
  exit 2
fi
NATIVE=$(realpath "$1")
mkdir -p "$2"
OUT=$(realpath "$2")
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}
for mode in normal optimized; do
  flags=()
  if [[ "$mode" == optimized ]]; then flags=(-O); fi
  for seed in 9922023 9922999; do
    for seat in 0 1; do
      "$PYTHON_BIN" "${flags[@]}" "$HERE/run_counterfactual_probe.py" \
        --native "$NATIVE" --output "$OUT/$mode-$seed-$seat" \
        --seeds "$seed" --seats "$seat" | tee "$OUT/$mode-$seed-$seat.log"
    done
  done
done
