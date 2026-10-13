#!/usr/bin/env bash
# Launch one arm from its OWN pristine teacher-only baseline.
#
# Sharing one bank path across arms let an earlier arm's banked model rows reach a
# later one, so the arms no longer differed by the variable under test alone. Each
# arm now gets an independent copy built by omitting model provenance, and its
# starting hash and row counts are printed and recorded in the run JSON.
set -eu
SRC="$1"; ARM="$2"; shift 2
BASE="results/bank-arm-$ARM.jsonl"
/home/user/work/venv/bin/python -B -c "
import sys, json; sys.path.insert(0,'.')
import exemplar_bank as EB
print(json.dumps(EB.make_baseline('$SRC', '$BASE')))
"
exec /home/user/work/venv/bin/python -u -B play.py --bank "$BASE" "$@"
