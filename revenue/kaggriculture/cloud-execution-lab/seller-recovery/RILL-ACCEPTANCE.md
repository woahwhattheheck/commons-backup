# Independent acceptance of PR10400 seller recovery

This packet applies the previously landed `seller-recovery/check_seller_recovery.py` consumer to RILL PR10400's exact production runtime. The acceptor changed no production source, runtime archive, configuration, game, seed, workflow or provider state.

## Exact source

Tested runtime commit: `575fb659757dff28e5e3171980aece2577914726`. Runtime blob `a1edf5a6fc2d96ed9731f02883bfebc72e522656`, SHA-256 `f718b435e58336acb223ee6e6a7ef7f6686d8916dd7f02733888eb9e98eaf066`, 18,405 bytes. The PR later advanced to `4f0be47fad98870606c1e3f25c0d00203e54ac1f`; comparison shows only the dedicated workflow file changed, so the tested runtime/dependency closure remains exact.

## Results

- **Completed transform-entry fallback, step 450:** 719 calls per actor, exact fallback, one producer call per input, all routes equal, zero later action or seller-state differences.
- **Completed after-observer fallback, step 450:** the same 719-call acceptance passes with zero later differences.
- **Interrupted replanning negative, step 447:** differences remain at steps 449 and 453. This is expected and required; the candidate does not promote unreturned replanning.

The retained input is DELVE development 9965001 seat 0, 719 own observations. It is not a new game and is not passed expected actions, opponent private state or original outcomes. No engine interpreter runs.

## Reproduce

Materialize the Library package identified in `RILL-LIBRARY-EVIDENCE.json`, then run from its extraction root:

```bash
python -B check_seller_recovery.py \
  --runtime runtime --pins RILL-SOURCE-PINS.json \
  --input input/candidate-inputs.jsonl.gz --receipt input/INPUT-RECEIPT.json \
  --step 450 --through 718 --boundary transform_entry \
  --report /tmp/rill-entry450.json --require-continuity

python -B check_seller_recovery.py \
  --runtime runtime --pins RILL-SOURCE-PINS.json \
  --input input/candidate-inputs.jsonl.gz --receipt input/INPUT-RECEIPT.json \
  --step 450 --through 718 --boundary after_observe \
  --report /tmp/rill-after-observe.json --require-continuity

python -B check_seller_recovery.py \
  --runtime runtime --pins RILL-SOURCE-PINS.json \
  --input input/candidate-inputs.jsonl.gz --receipt input/INPUT-RECEIPT.json \
  --step 447 --through 460 --boundary transform_entry \
  --report /tmp/rill-replan447.json
```

Detailed executed reports are included as deterministic gzip files under `reports/` in the Library packet. `RILL-ACCEPTANCE.json` binds every compressed and decoded digest.

## Integration boundary

The production contract is accepted. PR10400's current head still points CURRENT at the predecessor archive in the checked snapshot; the producer's dedicated single-writer workflow owns the coherent archive/source/pointer update. Do not merge a text-only source head or create a competing runtime fork.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
