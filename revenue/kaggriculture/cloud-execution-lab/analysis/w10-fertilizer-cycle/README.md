# TITAN W10 — realized fertilizer-cycle certificate

This directory contains an **observation-only, fail-closed admission check** for fertilizer decisions. It answers the W10 question that a local quote cannot:

> Did the fertilizer change produce additional units that were harvested, deposited, sold and retained as positive net cash inside the same deterministic horizon, without breaking protected work or protected sale stock?

The checker does not choose a fertilizer action and does not modify the canonical TITAN producer. It turns a paired experiment into a small, machine-verifiable certificate that a producer can consume later.

## Counterfactual contract

Run the control and fertilized candidate from the same:

- engine and evaluator bytes;
- opponent bytes;
- random seed and controlled player;
- exact starting state;
- horizon and worker-tick budget;
- protected-commitment ledger; and
- counterfactual protocol.

Those values are bound into `identity` by SHA-256 or exact scalar value. The candidate policy SHA may differ; everything in `identity` must match. The counterfactual runner is responsible for ensuring fertilizer placement is the intended treatment rather than silently changing unrelated policy.

Each trace starts with an identical pre-decision snapshot and ends exactly at `horizon_tick`. Snapshots carry cumulative counters for production, harvest, deposit, sale, loss and worker activity, plus current cash and inventory. Counters are observed facts, not optimistic quotes.

## Certification gates

`certify_realized_fertilizer(control, candidate)` returns `CERTIFIED` only when all gates pass:

1. strict schemas, capacities and counterfactual identity validate;
2. starting metrics are equivalent after normalization;
3. the candidate uses additional fertilizer;
4. additional produced units become additional harvested units;
5. those units become additional deposited units;
6. those units become additional sold units;
7. final cash is higher after all in-horizon costs;
8. incremental output obeys `produced >= harvested >= deposited >= sold > 0`;
9. first positive deltas occur in causal order: `fertilizer -> production -> harvest -> deposit -> sale`;
10. discarded output does not increase;
11. protected-obligation misses do not increase; and
12. protected-stock shortfall does not increase.

A candidate with a higher local yield quote but no realized sale is rejected. A candidate that sells pre-existing stock without additional deposit is rejected. A sale reached only after the comparison horizon is rejected because both traces must terminate exactly at the bound horizon.

## Fail-closed behavior

The trace contract intentionally rejects unknown or missing keys, floats or booleans in integer fields, malformed SHA-256 identities, decreasing cumulative counters, duplicate/decreasing ticks, capacity overflows, action counters greater than accounted worker ticks, worker use beyond the declared budget, and truncated traces. Validation order is fixed so malformed multi-error inputs produce stable reasons and certificate hashes across processes.

Malformed input produces a deterministic `REJECTED` document instead of an exception escaping into a producer admission path.

## CLI

```bash
python realized_fertilizer.py \
  --control control.json \
  --candidate fertilized.json \
  --output certificate.json \
  --pretty
```

The command exits `0` only for `CERTIFIED`, and `1` otherwise. Without `--output`, canonical JSON is written to stdout. Output includes normalized terminal deltas, derived milestone ticks, both normalized trace hashes and a self-verifiable certificate hash.

## Validation

```bash
python -m py_compile \
  revenue/kaggriculture/cloud-execution-lab/analysis/w10-fertilizer-cycle/realized_fertilizer.py \
  revenue/kaggriculture/cloud-execution-lab/analysis/w10-fertilizer-cycle/test_realized_fertilizer.py

python -m unittest -v \
  revenue/kaggriculture/cloud-execution-lab/analysis/w10-fertilizer-cycle/test_realized_fertilizer.py
```

The 17-test matrix includes a positive whole-cycle witness and independent rejections for local-yield-only gains, nonpositive cash, unattributable sales, discard, protected-stock/obligation regressions, capacity overflow, identity/start mismatch, horizon truncation, boolean/unknown fields, unaccounted actions, deterministic hashing, and CLI exit semantics.

## Producer handoff

The safe next integration step is narrow:

1. instrument the current producer/evaluator path to emit this trace schema;
2. run paired deterministic replays with only the fertilizer treatment changed;
3. store the certificate beside run evidence; and
4. admit a production fertilizer rule only when the certificate says `CERTIFIED` across the required seed/opponent matrix.

That handoff belongs to the current owner of existing producer paths. This W10 artifact deliberately avoids claiming or editing those paths.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
