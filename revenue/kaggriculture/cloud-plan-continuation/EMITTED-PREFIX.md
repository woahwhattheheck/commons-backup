# Preserve the emitted prefix when selecting a new suffix

The existing `ContinuationPlanSelector` now retains the product, fixed market
slot and quantity emitted at each positive sale date. Before a later decision,
the active plan must describe that same prefix. A changed, deleted, duplicated
or reattributed prior sale retires the key and returns the caller's complete
fallback with `reason: emitted_prefix_changed`. No replacement plan is drawn.

This closes a runtime consumer boundary, not a defect in the existing recourse
compiler: `compile_policy` already requires equal prefixes in its own input
family. The additional check compares a subsequently supplied active plan with
what this adapter actually emitted, rather than only checking that its dates
appeared previously. No new wrapper, optimizer or controller is introduced.

## Reproduced distinction

On the preceding `continuation.py` blob
`ac65cd08c4826532d0d34ce5d9c9a6f4156092c6`, a three-unit plan emits EGG1 at10
and retains EGG2 at13. Replacing its active schedule with `[10:2,13:1]` before
11 is accepted, although the prefix now claims a different quantity. Deleting
the prior sale is also accepted. The corrected adapter returns the unchanged
current fallback and retires that key. These are explicit synthetic consumer
sequences, not naturally reached game failures or measured cash losses.

A genuine `[10:1,12:2]` observed suffix remains usable: the completed prefix is
unchanged, and the normal current-feasibility callback still evaluates the
remaining schedule. A plan ID or index may change; equality is about dated
emissions, not naming. Reordering serialized dates and explicit zero entries do
not alter the positive prefix. The current decision is not counted as a past
date; ordinary identical same-step retries keep one draw. This change does not
introduce a new API for replacing a whole plan during the same decision.

An emitted sale still is not a fill receipt. The existing optional fill ledger
runs first, and short/unknown/missing fills keep their existing failure reasons.
A proven prior fill does not authorize rewriting that emission's quantity. Both
`record_final` and `observe_fills` are unchanged. Final-unit facts and a legal
fallback remain the caller's responsibility. No canonical TITAN release or
frozen experiment is rewritten or promoted by this consumer repair.

## Executed validation

`test_emitted_prefix.py` runs 27 new methods against actual T15 selector/solver,
ESTUARY fill ledger, and recourse compiler/MarketPath modules. Corrected source:
27 pass, zero failures/errors/skips. Exact predecessor: 15 failed assertion
records across 13 methods, zero errors; the remaining methods pass.

The same run includes 2,240 paired ordinary mixed-selector invocations with
identical actions, active state, retired keys, draw counts, decision records and
fill reports versus the predecessor. Sixteen RNG initializations are sampler
controls, not game seeds. Eight constructed compiler tables, four inventories
in both positions, retain their genuine identical-prefix recourse and all16
returned actions. This is component execution, not an official-engine transition,
full adaptive-agent simulation, policy improvement or latency measurement.

Only `__init__`, `_abort` and `transform` have changed runtime ASTs. Existing
fill methods, current-feasibility callback and original tests/evidence remain
unchanged. `EMITTED-PREFIX-RESULTS.json` records exact source identities and run
summaries; the delivery ZIP retains both full reports and logs.

## Reproduce

From repository root, with neighboring T15 and ESTUARY sources present:

```sh
python -B revenue/kaggriculture/cloud-plan-continuation/test_emitted_prefix.py -v \
  --report /tmp/emitted-prefix-results.json
```

For the original-source differential, extract the predecessor into a temporary
file, without replacing current source, and provide it as `--baseline`:

```sh
git show c77b0ff08912510c523fc65ea684eb94723fd2a1:revenue/kaggriculture/cloud-plan-continuation/continuation.py \
  > /tmp/ash-prefix-original.py
python -B revenue/kaggriculture/cloud-plan-continuation/test_emitted_prefix.py -v \
  --baseline /tmp/ash-prefix-original.py --report /tmp/emitted-prefix-results.json
```

To run the negative control, add `--module /tmp/ash-prefix-original.py`.
`--source-root` accepts a relocated `revenue/kaggriculture` tree. The reports
fingerprint the actual inputs, so later dependency changes are not attributed
to this run. Without `--baseline`, only the original-source differential is
explicitly skipped. Source is Apache-2.0, consistent with this existing component.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
