#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
: "${EXPECTED_HEAD:?EXPECTED_HEAD is required}"
: "${EXPECTED_CURRENT_MAIN:?EXPECTED_CURRENT_MAIN is required}"
: "${RUNNER_TEMP:?RUNNER_TEMP is required}"
SEEDS="${SEEDS:-539131249,1834999074,2609097301,2609097302,2609097303,2609097304,2611092201,2611092207}"
export SEEDS

OUT="${1:-$RUNNER_TEMP/titan-v3-route-reference-echo-current-activation}"
case "$OUT" in
  "$RUNNER_TEMP"/*) ;;
  *) echo "output must stay under RUNNER_TEMP" >&2; exit 2 ;;
esac
rm -rf "$OUT"
mkdir -p "$OUT/evaluator"
export PYTHONPYCACHEPREFIX="$OUT/pycache"

LAB=revenue/kaggriculture/cloud-execution-lab
KAG=revenue/kaggriculture
SOURCE_LANE="$LAB/analysis/v3-route-reference-echo-sol-accrual"
CASE="$LAB/analysis/v3-route-reference-echo-current-activation-sol-accrual"
HEAD="$(git rev-parse HEAD)"
test "$HEAD" = "$EXPECTED_HEAD"
git merge-base --is-ancestor "$EXPECTED_CURRENT_MAIN" "$HEAD"
test "$(git merge-base "$EXPECTED_CURRENT_MAIN" "$HEAD")" = "$EXPECTED_CURRENT_MAIN"
git diff --exit-code -- .
test -z "$(git status --porcelain)"

verify_blob() {
  local path="$1" expected="$2" actual
  actual="$(git hash-object "$path")"
  printf '%s  %s\n' "$actual" "$path"
  test "$actual" = "$expected"
}

{
  printf 'head %s\n' "$HEAD"
  printf 'current-main-ancestor %s\n' "$EXPECTED_CURRENT_MAIN"
  verify_blob "$LAB/main.py" 4a8cf7bcda1f0fea231a144692cb84a779a9e73e
  verify_blob "$LAB/scheduler.py" a483b24dd72b580d7d8811636b54d2d44f391575
  verify_blob "$LAB/frozen_selected.py" fc7baf5c179818a55037f6a61d92984d81d1a21c
  verify_blob "$LAB/runtime/integrated-selected/CURRENT-ARCHIVE.json" 5bd67f93b832b6f35ea6482d35cebdd0d600cbe1
  verify_blob "$LAB/runtime/integrated-selected/CURRENT-SOURCE.json" d80b40e345bcdbacfed9f7f4c8173aeb134fd781
  verify_blob "$KAG/cloud-eval/evaluate.py" 077feb2208b6e0c1727835eb4f8089709bf67f3b
  verify_blob "$LAB/reference/engine/kaggriculture.py" 3c202c7ee921da239356789e266b694635103fc4
  verify_blob "$LAB/runtime/variants/v1/reference/next-panel/vendor/arlene.py" bdb9cf58148a3c7961c085f4902759537decabf6
  verify_blob "$LAB/runtime/variants/v1/candidate.py" 8db1262a2d38cc3115d06732383e18e1132ccfba
  verify_blob "$SOURCE_LANE/candidate.py" 665440df03b113b4eefc174fe2445a437ed85e66
  verify_blob "$SOURCE_LANE/route_reference_echo.py" a2ab6c472486e188416fb6c73159c29d8d67327d
  verify_blob "$SOURCE_LANE/route_lifecycle.py" 70b459b4bd2c76de25ad5fca47bb634d1d91bd87
} | tee "$OUT/SOURCE-BLOBS.txt"

LAB="$LAB" python - <<'PY' | tee "$OUT/ARCHIVE-POINTER.json"
import hashlib
import json
import os
from pathlib import Path

lab = Path(os.environ["LAB"])
pointer = json.loads((lab / "runtime/integrated-selected/CURRENT-ARCHIVE.json").read_text())
assert pointer["sha256"] == "5f6a4153e502713b9467776eafe7464af650584149173ce7507a31a1b2af60f1"
assert pointer["source_manifest_sha256"] == "3249398b6aa56d1b3464db8d0cce5aa35e8edee397fc4341bd710d1f74dad469"
assert pointer["bytes"] == 428158
assert pointer["runtime_files"] == 109
payload = (lab / pointer["path"]).read_bytes()
assert len(payload) == pointer["bytes"]
assert hashlib.sha256(payload).hexdigest() == pointer["sha256"]
print(json.dumps(pointer, sort_keys=True, allow_nan=False))
PY

python -B -m py_compile "$SOURCE_LANE"/*.py "$CASE"/*.py
python -B -m unittest discover -s "$SOURCE_LANE" -p 'test_*.py' -v \
  2>&1 | tee "$OUT/SOURCE-CONTRACTS.txt"
python -B -m unittest discover -s "$CASE" -p 'test_*.py' -v \
  2>&1 | tee "$OUT/CURRENT-ACTIVATION-CONTRACTS.txt"
python -B "$SOURCE_LANE/audit.py" \
  --lab "$LAB" \
  --output "$OUT/SOURCE-AUDIT.json" \
  --require-opportunity
python -B "$LAB/build_integrated.py" --check \
  2>&1 | tee "$OUT/CANONICAL-BUILD-CHECK.txt"

git diff --exit-code -- .
test -z "$(git status --porcelain)"

python -B "$CASE/materialize_evaluator.py" \
  --source "$KAG/cloud-eval/evaluate.py" \
  --output "$OUT/evaluator/evaluate.py" \
  --receipt "$OUT/EVALUATOR-MATERIALIZATION.json" \
  | tee "$OUT/EVALUATOR-MATERIALIZATION-STDOUT.json"
python -B -m py_compile "$OUT/evaluator/evaluate.py"

EVALUATOR="$OUT/evaluator/evaluate.py"
COMMON_ARGS=(
  --engine-dir "$LAB/reference/engine"
  --loader "$KAG/20260907-offline-agent/evaluate.py"
  --opponent "arlene=$LAB/runtime/variants/v1/reference/next-panel/vendor/arlene.py::agent"
  --opponent "v1=$LAB/runtime/variants/v1/candidate.py::agent"
  --seeds "$SEEDS"
  --rng-seed 20260910
  --action-timeout 1.0
  --startup-timeout 15
  --game-timeout 180
  --recheck-first
)

python -B "$EVALUATOR" \
  "${COMMON_ARGS[@]}" \
  --candidate "$LAB/main.py::agent" \
  --output "$OUT/control.json" \
  2>&1 | tee "$OUT/control.log"

python -B "$EVALUATOR" \
  "${COMMON_ARGS[@]}" \
  --candidate "$CASE/instrumented_candidate.py::agent" \
  --output "$OUT/candidate.json" \
  2>&1 | tee "$OUT/candidate.log"

python -B "$CASE/analyze_panel.py" \
  --control "$OUT/control.json" \
  --candidate "$OUT/candidate.json" \
  --output "$OUT/PANEL.json" \
  --markdown "$OUT/PANEL.md" \
  | tee "$OUT/PANEL-STDOUT.json"

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  cat "$OUT/PANEL.md" >> "$GITHUB_STEP_SUMMARY"
fi

OUT="$OUT" HEAD="$HEAD" EXPECTED_CURRENT_MAIN="$EXPECTED_CURRENT_MAIN" CASE="$CASE" python - <<'PY'
import hashlib
import json
import os
from pathlib import Path
import subprocess

out = Path(os.environ["OUT"])
panel = json.loads((out / "PANEL.json").read_text())
files = {}
for path in sorted(out.rglob("*")):
    if path.is_file() and path.name != "PROVENANCE.json":
        files[path.relative_to(out).as_posix()] = {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
provenance = {
    "schema_version": 1,
    "operation": "titan-v3-route-reference-echo-current-activation-20260910-01",
    "git_head": os.environ["HEAD"],
    "current_main_ancestor": os.environ["EXPECTED_CURRENT_MAIN"],
    "run_script_git_blob": subprocess.check_output(
        ["git", "hash-object", f"{os.environ['CASE']}/run_current_panel.sh"], text=True
    ).strip(),
    "canonical_archive_sha256": "5f6a4153e502713b9467776eafe7464af650584149173ce7507a31a1b2af60f1",
    "canonical_source_manifest_sha256": "3249398b6aa56d1b3464db8d0cce5aa35e8edee397fc4341bd710d1f74dad469",
    "seeds": [int(value) for value in os.environ["SEEDS"].split(",")],
    "opponents": ["arlene", "v1"],
    "both_seats": True,
    "planned_games_per_arm": 32,
    "planned_games_total": 64,
    "verdict": panel["verdict"],
    "activation": panel["activation"],
    "overall": panel["overall"],
    "promotion_authorized": False,
    "canonical_release_modified": False,
    "provider_or_kaggle_mutation": False,
    "files": files,
}
(out / "PROVENANCE.json").write_text(
    json.dumps(provenance, indent=2, sort_keys=True, allow_nan=False) + "\n",
    encoding="utf-8",
)
PY

required=(
  SOURCE-BLOBS.txt
  ARCHIVE-POINTER.json
  SOURCE-CONTRACTS.txt
  CURRENT-ACTIVATION-CONTRACTS.txt
  SOURCE-AUDIT.json
  CANONICAL-BUILD-CHECK.txt
  EVALUATOR-MATERIALIZATION.json
  evaluator/evaluate.py
  control.json
  candidate.json
  PANEL.json
  PANEL.md
  PROVENANCE.json
)
for path in "${required[@]}"; do
  test -s "$OUT/$path"
done

git diff --exit-code -- .
test -z "$(git status --porcelain)"
printf '%s\n' "$HEAD" > "$OUT/COMPLETE"
