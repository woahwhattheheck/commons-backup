#!/usr/bin/env bash
# Repeat the segment/continuation measurement on further seeds.
#
# The 24-turn result rests on one seed, one continuation policy and one opponent, and
# its sign disagreed with the 6-turn result on that same seed. Repeating both segment
# lengths on fresh seeds is the cheapest way to tell whether either sign is real.
set -u
STATUS=results/bank-teacher.status.json
until [ "$(python3 -c "import json;print(json.load(open('$STATUS'))['state'])" 2>/dev/null)" = "done" ]; do
  sleep 10
done
M=/home/user/work/model/gemma-4-E4B-it.litertlm
POL=../cloud-market/main.py::agent
for SEED in "$@"; do
  for TURNS in 6 24; do
    TAG="s${SEED}-t${TURNS}"
    echo "===== SEGMENT seed=$SEED turns=$TURNS ====="
    /home/user/work/venv/bin/python -B -c "
import sys, json; sys.path.insert(0,'.')
import exemplar_bank as EB
print(json.dumps(EB.make_baseline('results/bank-teacher.jsonl','results/bank-$TAG-in.jsonl')))
"
    /home/user/work/venv/bin/python -u -B play.py --model $M --seed "$SEED" --seat 0 \
      --from-step 3 --turns "$TURNS" --warmup $POL --opponent $POL \
      --deriv-cards results/deriv-cards.json --eval-cards results/eval-cards.json \
      --examples bank --bank "results/bank-$TAG-in.jsonl" --render slots \
      --freeze-bank --out "results/play-$TAG.json"
  done
done
echo "===== CONTINUATIONS ====="
/home/user/work/venv/bin/python -B continuation.py \
  $(for SEED in "$@"; do for T in 6 24; do echo --run "results/play-s${SEED}-t${T}.json"; done; done) \
  --warmup $POL --opponent $POL --out results/continuation-multiseed.json
