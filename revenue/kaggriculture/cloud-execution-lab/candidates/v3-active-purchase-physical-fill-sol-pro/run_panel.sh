#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
LAB=$(cd "$HERE/../.." && pwd)
KAG=$(cd "$LAB/.." && pwd)
OUT=${1:?output directory required}
SEEDS=${SEEDS:-539131249,1834999074,2609097301,2609097302,2609097303,2609097304,2611092201,2611092207}
mkdir -p "$OUT"
python "$HERE/audit.py" --json "$OUT/SOURCE-AUDIT.json"
python "$HERE/materialize.py" "$OUT/arms" --json "$OUT/MATERIALIZATION.json"
python "$HERE/trace_evaluator.py" "$KAG/cloud-eval/evaluate.py" "$OUT/evaluate_traced.py" \
  > "$OUT/EVALUATOR-PATCH.json"
python "$OUT/evaluate_traced.py" \
  --engine-dir "$LAB/reference/engine" \
  --loader "$KAG/20260907-offline-agent/evaluate.py" \
  --candidate "$OUT/arms/control/main.py::agent" \
  --opponent "arlene=$LAB/reference/next-panel/vendor/arlene.py::agent" \
  --opponent "v1=$LAB/runtime/variants/v1/candidate.py::agent" \
  --seeds "$SEEDS" --output "$OUT/CONTROL.json"
python "$OUT/evaluate_traced.py" \
  --engine-dir "$LAB/reference/engine" \
  --loader "$KAG/20260907-offline-agent/evaluate.py" \
  --candidate "$OUT/arms/candidate/main.py::agent" \
  --opponent "arlene=$LAB/reference/next-panel/vendor/arlene.py::agent" \
  --opponent "v1=$LAB/runtime/variants/v1/candidate.py::agent" \
  --seeds "$SEEDS" --output "$OUT/CANDIDATE.json"
python "$HERE/compare.py" "$OUT/CONTROL.json" "$OUT/CANDIDATE.json" \
  --materialization "$OUT/MATERIALIZATION.json" \
  --evaluator-receipt "$OUT/EVALUATOR-PATCH.json" \
  --json "$OUT/ACTION-ADMISSION.json"
python - <<'PY' "$OUT"
import hashlib, json, pathlib, sys
root=pathlib.Path(sys.argv[1])
files=['SOURCE-AUDIT.json','MATERIALIZATION.json','EVALUATOR-PATCH.json','CONTROL.json','CANDIDATE.json','ACTION-ADMISSION.json']
receipt={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}
(root/'PROVENANCE.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
(root/'COMPLETE').write_text(receipt['ACTION-ADMISSION.json']+'\n')
PY
