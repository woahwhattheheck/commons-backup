# Frozen JH terminal choices under a second stress family

This offline consumer compares already-selected actions; it does not select
again, reconstruct a controller, learn a history model, sample an action, or
change the canonical TITAN release. It consumes PR10215's ten source-bound JH
explicit-WOOL records and their existing public/own runtime payloads.

## Fixed comparison

The prior experiment declares WOOL quantities 0/25/50, operating stock 0/0 or
5/5, and two fixed market-order templates. Its default absolute-score choice
changes no action; its optional cash-Pareto choice changes nine. The gains in
that original conditional family remain accepted and are not rerun here.

The second family is the unchanged PR10206 callable
`interior_liquidation_scenarios`. Its 32 columns retain the 21 original
current-snapshot stress hypotheses and add nine middle-slot full-shed sales
plus two mixed interleavings. This is **not** a calibrated distribution or a
claim that every column is compatible with the entire public history. It
respects instantaneous shed capacity and market positions only. The two
families are kept separately named; neither silently replaces the other.

`compare_frozen(engine, report, raw_payload)` first binds the payload SHA-256,
original action, complete prior packet, selected-plan identity and the same
native own-unit snapshot. It retains the selected queue unchanged and compares
its exact final cash margin with the original queue in every new column.
Identical old cells can be reused by complete shed/queue identity; this run
found none. No original objective, feasibility method or sampler is replaced.
The CLI reads only hash-named `runtime/*.json.gz` members, not the archive's
outcome/index records. Public prior history is not trained or replayed.

## Result and interpretation

Ten retained inputs, nine previously changed choices: **all nine have negative
cash-margin columns in the second family**. Their worst changes range from
-279 to -614. Original-family minimum changes remain zero and maxima remain
2 to 5. A fixed MILK100/slot0 hypothesis causes one frozen ordering to lose312
own cash and raise rival cash302, for a -614 relative change.

This does not falsify JH's reported conditional result or establish actual
losses. It shows that the small cash improvements depend on the declared
unknown-stock/order family and are not uniform dominance over the broader
stress assumptions. A policy-strength claim would require justified terminal
uncertainty and separate actual evaluation, not relabeling these columns.

The comparison executes608 native market cells and10 own-unit boundary
captures; zero optimization, inference, full-game or recorded-outcome calls.
All chosen actions remain exactly the prior choices. Thirteen focused methods
pass on the final source, including18 complete native terminal transitions
checking the nine worst baseline/candidate pairs. The valid-consumer
nonmutation test separately repeats64 of this new consumer's cells; it is not
added to the primary608 experiment count. Initial and final configured test
logs are retained separately. Unconfigured discovery skips explicitly and is
not counted as a native pass.

## Reproduce

Use existing sibling `terminal_inputs.py`, `terminal_input_cases.py` and
`interior_liquidation.py`; this delivery adds no copies in the repository.
The private package contains exact execution dependencies and old inputs.
From that package's root:

```sh
export PYTHONPATH="$PWD/source:$PWD/work"
python -B work/check_frozen_terminal_choice.py \
  --reports inputs/WOOL-RESULTS.json --payload-zip inputs/public-history.zip \
  --loader dependencies/engine_loader.py --engine-dir engine \
  --freeze results/CROSS-FREEZE.json --output /tmp/frozen-choice-new.json
python -B work/test_frozen_terminal_choice.py \
  --reports inputs/WOOL-RESULTS.json --payload-zip inputs/public-history.zip \
  --executed /tmp/frozen-choice-new.json \
  --loader dependencies/engine_loader.py --engine-dir engine \
  --output /tmp/frozen-choice-tests-new.json
```

Output names must be new. The comparison verifies the pre-execution source and
input freeze. The generator beside the runner is the unchanged PR10206 source.
`FROZEN-CHOICE-STRESS.json` contains compact identities and counts. Detailed
payloads and per-scenario receipts remain in private Library storage. The
native engine is the existing pinned28b6d8af source; all three hashes are retained.

The source/result consumers are JH, LARCH and the canonical builder. Keep the
single current release and default unchanged. This is a sensitivity result,
not a new admission check, mandatory integration step or release variant.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
