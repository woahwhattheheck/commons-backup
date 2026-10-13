#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
: "${EXPECTED_HEAD:?EXPECTED_HEAD is required}"
: "${EXPECTED_CURRENT_MAIN:?EXPECTED_CURRENT_MAIN is required}"
: "${RUNNER_TEMP:?RUNNER_TEMP is required}"
SEEDS="${SEEDS:-539131249,1834999074,2609097301,2609097302,2609097303,2609097304,2611092201,2611092207}"
export SEEDS

OUT="${1:-$RUNNER_TEMP/titan-v3-own-value-bound-panel}"
case "$OUT" in
  "$RUNNER_TEMP"/*) ;;
  *) echo "output must stay under RUNNER_TEMP" >&2; exit 2 ;;
esac
rm -rf "$OUT"
mkdir -p "$OUT"
export PYTHONPYCACHEPREFIX="$OUT/pycache"

LAB=revenue/kaggriculture/cloud-execution-lab
KAG=revenue/kaggriculture
PARENT="$LAB/analysis/titan-v3-own-value-objective-sol-objective"
CARRIER="$LAB/analysis/titan-v3-own-value-archive-carrier-sol-foundry"
CASE="$LAB/analysis/titan-v3-own-value-bound-panel-sol-closure"
HEAD="$(git rev-parse HEAD)"
test "$HEAD" = "$EXPECTED_HEAD"
test "$(git rev-parse HEAD^2)" = "$EXPECTED_CURRENT_MAIN"

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
  verify_blob "$LAB/runtime/integrated-selected/CURRENT-ARCHIVE.json" 5bd67f93b832b6f35ea6482d35cebdd0d600cbe1
  verify_blob "$LAB/runtime/integrated-selected/CURRENT-SOURCE.json" d80b40e345bcdbacfed9f7f4c8173aeb134fd781
  verify_blob "$PARENT/own_value_objective.py" 17c49e220de6b8c1c1ba15a95e4707a3d9cd1ea0
  verify_blob "$PARENT/compare.py" 9a4642211f2fe16da4452aad0a084a1efa85bb31
  verify_blob "$CARRIER/archive_runtime_guard.py" 2fbc4b45d2f0f06f8ccef2665d8d740d73c9e3db
  verify_blob "$CARRIER/archive_carrier.py" 2f5be09c36368732ddf80a84f3a86b36b2ae405e
  verify_blob "$CARRIER/verify_panel_binding.py" 82f0026fd1924ab3987aaf804eba7cc3f56cd87c
  verify_blob "$KAG/cloud-eval/evaluate.py" 077feb2208b6e0c1727835eb4f8089709bf67f3b
  verify_blob "$LAB/runtime/variants/v1/candidate.py" 8db1262a2d38cc3115d06732383e18e1132ccfba
  verify_blob "$LAB/runtime/variants/v1/reference/next-panel/vendor/arlene.py" bdb9cf58148a3c7961c085f4902759537decabf6
  verify_blob "$CASE/materialize_evaluator.py" 1041c0c2d9099478f21b6ad7082d0527877a5b14
  verify_blob "$CASE/action_admission.py" 6a1ab9eeeb01fe6937bc0e56d540142f700172a6
  verify_blob "$CASE/test_bound_evidence.py" 9d08bd39f55ed01e7f26bdec467c5abfa37018da
} | tee "$OUT/SOURCE-BLOBS.txt"

LAB="$LAB" python - <<'PY' | tee "$OUT/ARCHIVE-POINTER.json"
import hashlib
import json
import os
from pathlib import Path

lab = Path(os.environ["LAB"])
pointer = json.loads(
    (lab / "runtime/integrated-selected/CURRENT-ARCHIVE.json").read_text(
        encoding="utf-8"
    )
)
expected_archive = "5f6a4153e502713b9467776eafe7464af650584149173ce7507a31a1b2af60f1"
expected_manifest = "3249398b6aa56d1b3464db8d0cce5aa35e8edee397fc4341bd710d1f74dad469"
assert pointer["sha256"] == expected_archive
assert pointer["source_manifest_sha256"] == expected_manifest
assert pointer["bytes"] == 428158
assert pointer["runtime_files"] == 109
archive = lab / pointer["path"]
payload = archive.read_bytes()
assert len(payload) == pointer["bytes"]
assert hashlib.sha256(payload).hexdigest() == expected_archive
print(json.dumps(pointer, sort_keys=True, allow_nan=False))
PY

(
  cd "$PARENT"
  python -m py_compile \
    own_value_objective.py candidate.py mechanism_witness.py compare.py \
    test_own_value_objective.py test_compare.py
  python -m unittest -v test_own_value_objective.py test_compare.py
  python mechanism_witness.py
) 2>&1 | tee "$OUT/OBJECTIVE-CONTRACTS.txt"

(
  cd "$CARRIER"
  python -m py_compile \
    archive_runtime_guard.py archive_carrier.py verify_panel_binding.py \
    test_archive_carrier.py
  python -m unittest -v test_archive_carrier.py
) 2>&1 | tee "$OUT/CARRIER-CONTRACTS.txt"

(
  cd "$CASE"
  python -m py_compile \
    materialize_evaluator.py action_admission.py test_bound_evidence.py
  python -m unittest -v test_bound_evidence.py
) 2>&1 | tee "$OUT/BOUND-EVIDENCE-CONTRACTS.txt"

mkdir -p "$OUT/evaluator"
python "$CASE/materialize_evaluator.py" \
  --source "$KAG/cloud-eval/evaluate.py" \
  --output "$OUT/evaluator/evaluate.py" \
  --receipt "$OUT/EVALUATOR-MATERIALIZATION.json" \
  | tee "$OUT/EVALUATOR-MATERIALIZATION-STDOUT.json"
python -m py_compile "$OUT/evaluator/evaluate.py"

python "$CARRIER/archive_carrier.py" materialize \
  --lab-root "$LAB" \
  --pointer "$LAB/runtime/integrated-selected/CURRENT-ARCHIVE.json" \
  --overlay "$PARENT/own_value_objective.py" \
  --output "$OUT/carrier" \
  --git-head "$HEAD" \
  | tee "$OUT/MATERIALIZE-STDOUT.json"

python "$CARRIER/archive_carrier.py" probe \
  --entry "$OUT/carrier/control/control_entry.py" \
  --output "$OUT/CONTROL-PROBE.json" \
  > "$OUT/CONTROL-PROBE-STDOUT.json"
python "$CARRIER/archive_carrier.py" probe \
  --entry "$OUT/carrier/candidate/candidate_entry.py" \
  --output "$OUT/CANDIDATE-PROBE.json" \
  > "$OUT/CANDIDATE-PROBE-STDOUT.json"
python "$CARRIER/archive_carrier.py" verify \
  --root "$OUT/carrier" \
  --output "$OUT/PRE-PANEL-VERIFY.json" \
  > "$OUT/PRE-PANEL-VERIFY-STDOUT.json"

OUT="$OUT" python - <<'PY'
import json
import os
from pathlib import Path

out = Path(os.environ["OUT"])
receipt = json.loads((out / "carrier/CARRIER-RECEIPT.json").read_text())
control = json.loads((out / "CONTROL-PROBE.json").read_text())
candidate = json.loads((out / "CANDIDATE-PROBE.json").read_text())
pre = json.loads((out / "PRE-PANEL-VERIFY.json").read_text())
assert receipt["archive"]["sha256"] == "5f6a4153e502713b9467776eafe7464af650584149173ce7507a31a1b2af60f1"
assert receipt["archive"]["source_manifest_sha256"] == "3249398b6aa56d1b3464db8d0cce5aa35e8edee397fc4341bd710d1f74dad469"
assert receipt["canonical_runtime_equal"] is True
assert receipt["canonical_repository_modified"] is False
assert control["install_receipt"] is None
install = candidate["install_receipt"]
assert install["changed_field"] == "MarketPath.score[0]"
assert install["actual_git_blob"] == install["expected_git_blob"]
assert install["canonical_files_modified"] is False
assert pre["canonical_runtime_equal"] is True
PY

git diff --exit-code -- .
test -z "$(git status --porcelain)"

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

python "$EVALUATOR" \
  "${COMMON_ARGS[@]}" \
  --candidate "$OUT/carrier/control/control_entry.py::agent" \
  --output "$OUT/control.json"

python "$EVALUATOR" \
  "${COMMON_ARGS[@]}" \
  --candidate "$OUT/carrier/candidate/candidate_entry.py::agent" \
  --output "$OUT/candidate.json"

python "$CARRIER/verify_panel_binding.py" \
  --receipt "$OUT/carrier/CARRIER-RECEIPT.json" \
  --control "$OUT/control.json" \
  --candidate "$OUT/candidate.json" \
  --output "$OUT/PANEL-BINDING.json" \
  | tee "$OUT/PANEL-BINDING-STDOUT.json"

python "$PARENT/compare.py" \
  --control "$OUT/control.json" \
  --candidate "$OUT/candidate.json" \
  --head "$HEAD" \
  --output "$OUT/PAIRED-REPORT.json" \
  --markdown "$OUT/PAIRED-REPORT.md" \
  | tee "$OUT/PAIRED-REPORT-STDOUT.json"

python "$CASE/action_admission.py" \
  --control "$OUT/control.json" \
  --candidate "$OUT/candidate.json" \
  --paired "$OUT/PAIRED-REPORT.json" \
  --evaluator-receipt "$OUT/EVALUATOR-MATERIALIZATION.json" \
  --output "$OUT/ACTION-ADMISSION.json" \
  --markdown "$OUT/ACTION-ADMISSION.md" \
  | tee "$OUT/ACTION-ADMISSION-STDOUT.json"

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  cat "$OUT/ACTION-ADMISSION.md" >> "$GITHUB_STEP_SUMMARY"
  printf '\n' >> "$GITHUB_STEP_SUMMARY"
  cat "$OUT/PAIRED-REPORT.md" >> "$GITHUB_STEP_SUMMARY"
fi

python "$CARRIER/archive_carrier.py" verify \
  --root "$OUT/carrier" \
  --output "$OUT/POST-PANEL-VERIFY.json" \
  > "$OUT/POST-PANEL-VERIFY-STDOUT.json"

OUT="$OUT" HEAD="$HEAD" CASE="$CASE" EXPECTED_CURRENT_MAIN="$EXPECTED_CURRENT_MAIN" python - <<'PY'
import hashlib
import json
import os
from pathlib import Path
import subprocess

out = Path(os.environ["OUT"])
files = {}
for path in sorted(out.rglob("*")):
    if path.is_file() and path.name != "PROVENANCE.json":
        files[path.relative_to(out).as_posix()] = {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

def load(name):
    path = out / name
    return json.loads(path.read_text()) if path.is_file() else None

admission = load("ACTION-ADMISSION.json")
paired = load("PAIRED-REPORT.json")
binding = load("PANEL-BINDING.json")
evaluator = load("EVALUATOR-MATERIALIZATION.json")
post = load("POST-PANEL-VERIFY.json")
assert admission is not None and paired is not None and binding is not None
assert evaluator is not None and post is not None
assert post["canonical_runtime_equal"] is True
result = {
    "schema_version": 2,
    "operation": "titan-v3-own-value-bound-gameplay-screen-20260910-01",
    "git_head": os.environ["HEAD"],
    "current_main_parent": os.environ["EXPECTED_CURRENT_MAIN"],
    "historical_prefooter_archive_sha256": "17f536087b3a6baf4ae1222a051285766a3ea8c2ca5af6edc190d4f527e12b86",
    "run_script_git_blob": subprocess.check_output(
        ["git", "hash-object", f"{os.environ['CASE']}/run_bound_panel.sh"],
        text=True,
    ).strip(),
    "archive_sha256": "5f6a4153e502713b9467776eafe7464af650584149173ce7507a31a1b2af60f1",
    "source_manifest_sha256": "3249398b6aa56d1b3464db8d0cce5aa35e8edee397fc4341bd710d1f74dad469",
    "seeds": [int(value) for value in os.environ["SEEDS"].split(",")],
    "opponents": ["arlene", "v1"],
    "both_seats": True,
    "planned_games_per_arm": 32,
    "planned_games_total": 64,
    "candidate_action_capture": evaluator["patched"],
    "panel_binding": binding,
    "paired_verdict": paired["verdict"],
    "admission_verdict": admission["verdict"],
    "gates": admission["gates"],
    "overall": admission["overall"],
    "by_opponent_seat": admission["by_opponent_seat"],
    "canonical_release_modified": False,
    "promotion_authorized": False,
    "hosted_leaderboard_claim": False,
    "files": files,
}
(out / "PROVENANCE.json").write_text(
    json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
    encoding="utf-8",
)
PY

required=(
  SOURCE-BLOBS.txt
  ARCHIVE-POINTER.json
  OBJECTIVE-CONTRACTS.txt
  CARRIER-CONTRACTS.txt
  BOUND-EVIDENCE-CONTRACTS.txt
  EVALUATOR-MATERIALIZATION.json
  evaluator/evaluate.py
  carrier/CARRIER-RECEIPT.json
  CONTROL-PROBE.json
  CANDIDATE-PROBE.json
  PRE-PANEL-VERIFY.json
  control.json
  candidate.json
  PANEL-BINDING.json
  PAIRED-REPORT.json
  PAIRED-REPORT.md
  ACTION-ADMISSION.json
  ACTION-ADMISSION.md
  POST-PANEL-VERIFY.json
  PROVENANCE.json
)
for path in "${required[@]}"; do
  test -s "$OUT/$path"
done

git diff --exit-code -- .
test -z "$(git status --porcelain)"
printf '%s\n' "$HEAD" > "$OUT/COMPLETE"
python - "$OUT/ACTION-ADMISSION.json" <<'PY'
import json
from pathlib import Path
import sys
report = json.loads(Path(sys.argv[1]).read_text())
print(json.dumps({"verdict": report["verdict"], **report["overall"]}, sort_keys=True))
PY
