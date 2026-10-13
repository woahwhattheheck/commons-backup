# TITAN V2 target-domain ablation

Operation: `titan-v2-target-domain-ablation-20260909-sol-bulwark-01`

## Exact hypothesis

The frozen V1 and V2 entrypoints are byte-identical. Their executable scheduler
closures are not. One V1→V2 change widened the products owned by the SELL
scheduler:

```python
# V1: only baseline SELL or previously pending scheduler intent
targets = {
    p: min(max(0, int(shed.get(p, 0))), q + self.pending.get(p, 0))
    for p, q in {**{p: 0 for p in self.pending}, **baseline_q}.items()
}

# V2: every non-operating product physically present in shed
targets = {
    p: max(0, int(shed.get(p, 0)))
    for p in PRODUCTS
    if shed.get(p, 0) > 0
}
```

That is a policy expansion, not merely an execution-safety repair. V2 may begin
planning liquidation for a product that inherited Arlene never offered and that
the scheduler had never previously owned.

## One-factor arm

`materialize.py` copies the frozen V2 runtime tree to a temporary directory and
replaces exactly that expression with V1's target domain. It fails closed unless:

- the source `scheduler.py` Git blob is exactly
  `7c068b7078c3d7c09bb3836590ad42b0af934cdf`;
- the V2 expression occurs once and the V1 expression occurs zero times;
- every source-tree member is a regular file;
- the copied file inventory is identical;
- `scheduler.py` is the only changed file;
- the source tree remains byte-identical after materialization; and
- the patched scheduler compiles.

The ablation deliberately preserves V2's later-rival scenarios, full continuation
value, route SELL reconstruction, max-order feasibility, forced-capacity repair,
original order-index preservation, and all reference/mechanics bytes.

## Causal screen

The workflow evaluates frozen V2 control and the one-factor ablation on the same
official interpreter, seeds, seats, opponent source bytes, evaluator, loader,
timeouts, and RNG seed. Opponents are frozen V1 and public Arlene.

Because both packages retain the same 66-byte `candidate.py`, the evaluator's
entry-file hash cannot distinguish them. The comparison therefore requires the
materializer's independently computed full-tree closure identities and rejects
equal or malformed closures.

Primary outcome is own cash, not margin. `UPSIDE_SCREEN` requires:

1. at least one returned action trace changes;
2. positive mean own-cash delta;
3. nonnegative median own-cash delta;
4. at least as many positive as negative paired cells; and
5. nonnegative mean own-cash delta in both the V1 and Arlene strata.

This is a causal screen only. It cannot promote a candidate or authorize a
leaderboard submission.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
