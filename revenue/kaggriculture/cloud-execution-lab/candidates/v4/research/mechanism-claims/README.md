# TITAN V4 mechanism claims registry

This package is searchable coordination memory for the **single** canonical V4 line. It exists because fast parallel research can rediscover a plausible engine mechanism after that mechanism has already been source-proved, falsified, narrowed, or handed to a specific next gate.

`CLAIMS.json` records narrow propositions as `CONFIRMED`, `FALSIFIED`, or `CONDITIONAL`. Every entry binds to exact repository evidence by Git blob and to literal evidence anchors. `check_mechanism_claims.py` fails closed on stale blobs, missing anchors, duplicate ids/propositions, unsorted aliases, path traversal, symlinks, malformed JSON, or unsupported statuses.

The registry is deliberately **not** gameplay authority. A claim can prevent wasting time on the same unchanged premise, but it cannot activate a feature, merge a PR, override a source owner, substitute for current-native economics, or turn a constructed witness into field EV. `FALSIFIED` means “do not repeat this proposition on the same evidence without new evidence”; it does not ban a narrower proposition with a genuinely different mechanism.

Initial entries are intentionally conservative and use durable main evidence only: the pinned official engine plus the already-landed `research/market-pressure` package. Slack-only observations are excluded until they have durable source/economic evidence.

Run from the repository root:

```bash
python -B revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/mechanism-claims/check_mechanism_claims.py \
  revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/mechanism-claims/CLAIMS.json \
  --repo-root .

python -B -m unittest -v \
  revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/mechanism-claims/test_check_mechanism_claims.py
python -O -B -m unittest -v \
  revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/mechanism-claims/test_check_mechanism_claims.py
```

When adding a claim, prefer the smallest proposition that the pinned evidence actually supports. Keep `scope`, `disposition`, and `next_gate` explicit so later agents know whether to stop, narrow, or move forward.
