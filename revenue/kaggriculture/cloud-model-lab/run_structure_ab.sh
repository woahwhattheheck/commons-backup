#!/usr/bin/env bash
# Paired test of the structure-balance block: same seed, same bank, same opponent and
# continuation, renderer state the only difference.
#
# The block states empty structures with their tile ids, animal stock in shed and in
# hands, which structures already have a worker on them carrying a matching animal,
# and what cash affords. The question it exists to answer is whether the model then
# allocates workers to realizable revenue instead of building nine structures for
# three animals -- a change in decisions, not in labels.
#
# KAG_NO_STRUCTURE_BALANCE=1 suppresses the block, giving the OFF arm.
set -eu
M=/home/user/work/model/gemma-4-E4B-it.litertlm
POL=../cloud-market/main.py::agent
TURNS="${TURNS:-24}"
for SEED in "$@"; do
  for ARM in off on; do
    TAG="sb-${ARM}-s${SEED}"
    /home/user/work/venv/bin/python -B -c "
import sys, json; sys.path.insert(0,'.')
import exemplar_bank as EB
print(json.dumps(EB.make_baseline('results/bank-teacher.jsonl','results/bank-$TAG-in.jsonl')))
"
    echo "===== STRUCTURE BALANCE $ARM  seed=$SEED turns=$TURNS ====="
    if [ "$ARM" = "off" ]; then export KAG_NO_STRUCTURE_BALANCE=1; else unset KAG_NO_STRUCTURE_BALANCE; fi
    /home/user/work/venv/bin/python -u -B play.py --model $M --seed "$SEED" --seat 0 \
      --from-step 3 --turns "$TURNS" --warmup $POL --opponent $POL \
      --deriv-cards results/deriv-cards.json --eval-cards results/eval-cards.json \
      --examples bank --bank "results/bank-$TAG-in.jsonl" --render slots \
      --freeze-bank --out "results/play-$TAG.json"
  done
done
unset KAG_NO_STRUCTURE_BALANCE || true
echo "===== CONTINUATIONS ====="
/home/user/work/venv/bin/python -B continuation.py \
  $(for SEED in "$@"; do for A in off on; do echo --run "results/play-sb-${A}-s${SEED}.json"; done; done) \
  --warmup $POL --opponent $POL --out results/continuation-structure-ab.json
