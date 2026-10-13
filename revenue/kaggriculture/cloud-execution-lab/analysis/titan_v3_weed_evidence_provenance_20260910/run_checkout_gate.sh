#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
usage: run_checkout_gate.sh OUT_DIR [CLAIM_ID] [LABEL]

Certifies the exact TITAN checkout, requires EXPLICIT_W0, creates a W0 claim,
and gates that claim. No panel labeled W0/R0P0O0 should run or promote unless
this command exits 0 and its three JSON outputs are archived with the panel.
USAGE
  exit 64
}

[[ $# -ge 1 && $# -le 3 ]] || usage

OUT_DIR=$1
CLAIM_ID=${2:-titan-panel}
LABEL=${3:-R0P0O0}
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
LAB_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd)
REVISION=$(git -C "$LAB_ROOT" rev-parse HEAD 2>/dev/null || git rev-parse HEAD)

mkdir -p -- "$OUT_DIR"
RECEIPT="$OUT_DIR/weed-semantics-receipt.json"
CLAIM="$OUT_DIR/weed-evidence-claim.json"
DECISION="$OUT_DIR/weed-evidence-decision.json"

python "$SCRIPT_DIR/weed_evidence_certifier.py" certify \
  --spatial "$LAB_ROOT/spatial_tempo.py" \
  --runtime "$LAB_ROOT/titan_runtime.py" \
  --entrypoint "$LAB_ROOT/main.py" \
  --config "$LAB_ROOT/TITAN-CONFIG.json" \
  --revision "$REVISION" \
  --timestamp \
  --require EXPLICIT_W0 \
  --output "$RECEIPT"

python "$SCRIPT_DIR/weed_evidence_certifier.py" make-claim \
  --receipt "$RECEIPT" \
  --claim-id "$CLAIM_ID" \
  --declared W0 \
  --label "$LABEL" \
  --output "$CLAIM"

python "$SCRIPT_DIR/weed_evidence_certifier.py" gate \
  --receipt "$RECEIPT" \
  --claim "$CLAIM" \
  --spatial "$LAB_ROOT/spatial_tempo.py" \
  --runtime "$LAB_ROOT/titan_runtime.py" \
  --entrypoint "$LAB_ROOT/main.py" \
  --config "$LAB_ROOT/TITAN-CONFIG.json" \
  --revision "$REVISION" \
  --output "$DECISION"

printf 'weed evidence accepted: %s\n' "$DECISION"
