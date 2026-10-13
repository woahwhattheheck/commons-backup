# Explicit WOOL hypotheses: retained-input consumer experiment

This is an offline use of existing components, not a new inference model,
controller, solver, canonical agent, or release. It addresses the previously
observed exact-history intersection failure without pretending that censored
WOOL sales became known.

## Fixed question and inputs

Use JOINT's existing `unobserved_products=['WOOL']` option. Supply explicit WOOL
lots of 0, 25, or 50, crossed with the existing operating-stock hypotheses
(WHEAT/FERTILIZER both zero or both five) and the existing two slot templates.
Other products retain their same-lag exact historical quantities. These are
finite current-stock and recurrence assumptions, not estimates of hidden stock
or calibrated probabilities. Capacity and scenario limits remain unchanged;
an impossible family is not silently clipped or partially optimized.

`WOOL-FREEZE.json` was written before execution and retains the settings,
experiment/JOINT/flow/score source hashes, and saved-history input identity.
The ten runtime payloads are the already-exposed LARCH/PRISM development inputs,
not fresh held data. Fifty prior reconciliations were consumed from their saved
records instead of rerunning the history inference, actors, or full games.

## Actual result

Exact-only readiness was 1/10. Explicit WOOL assumptions make all 10 inputs
usable, each with 12 scenarios; eight inputs have five common historical lags
and two have four. This change in availability is caused by assumptions, not
new knowledge about WOOL.

The existing producer executes 720 conditional native markets. The two existing
objective choices make 20 score calls: default baseline-on-tie changes no action;
`cash_pareto` changes nine complete actions. All selected action/scenario pairs
are checked by 228 full native interpreter transitions, with matching own/rival
terminal cash. There are ten own-unit snapshot captures and no additional
historical inference, production-controller call, full game, or game seed.

The primary conditional win-point floor remains 1 in every included column.
Changed actions have no negative relative-cash delta in the included family and
positive deltas of 2, 3, 4, or 5 in some columns. Seven of the nine changes have
positive deltas only when the rival operating-stock hypothesis is nonzero. Two
also improve columns with WOOL and zero operating stock. This is important:
nine changed actions are not nine demonstrated game improvements, and most do
not establish a new WOOL-specific economic mechanism.

No recorded current rival queue, hidden inventory, terminal outcome, or reward
was used or looked up for this experiment. Actual-rival coverage and realized
performance remain unmeasured here. The result does not warrant changing the
single canonical agent or its default configuration.

## Checks

Nine local boundary methods pass. They preserve censored/missing records,
reject mismatched saved-input hashes and interval identities, retain empty
slots and explicit unknown quantities, and keep unavailable or capacity-invalid
families away from the terminal producer. A scenario budget returns no trimmed
family. These checks are separate from the 720/228 executed native comparisons.

```sh
python -B revenue/kaggriculture/cloud-market-response/test_joint_wool_hypotheses.py
```

The tests use the adjacent existing `flow.py` and `joint_terminal_history.py`.
`TITAN_WOOL_FLOW` and `TITAN_WOOL_JOINT` can point to those exact files in an
extracted source layout. No engine or private input archive is needed for the
nine boundary tests.

## Reproduce the retained-input comparison

Reuse these existing private Library archives; do not rerun an actor, game,
exporter, or inference job to regenerate the inputs:

- `TITAN-JOINT-HISTORY-PR10119.zip`, SHA256 `76a78052e7b60365a9547556b14829df926e02868ba37e1b08c9f5d11afca78c`: saved `evidence/larch-prefixes.json`.
- `TITAN-LARCH-public-history-inputs-20260908.zip`, SHA256 `b64a2363365b4e6711c08c38b3398bc44466994ef3d4d75da2a35be9d8488568`: the ten `runtime/*.json.gz` inputs.
- Existing POLY package `TITAN-POLY-terminal-inputs-20260907.zip`, SHA256 `af693707f97eea60e068a094af075255c107407c067eb82977a84a2ad74c1cd4`: its exact source, dependency, and engine directories. It is also retained inside LARCH's cash-tie evidence package.

Use the LARCH score source Git blob `f8219d69985f4fe5a92e688a42507c5294db5744`,
not the earlier score file bundled in the POLY package. The script explicitly
loads the supplied later score module; all other consumer modules are the
unchanged POLY closure. The source hashes in the freeze are checked by the CLI.

```sh
python -B revenue/kaggriculture/cloud-market-response/check_joint_wool_hypotheses.py \
  --saved-reports "$JOINT_INPUT/evidence/larch-prefixes.json" \
  --runtime-dir "$LARCH_INPUT/runtime" \
  --poly-package "$POLY_PACKAGE" \
  --joint revenue/kaggriculture/cloud-market-response/joint_terminal_history.py \
  --flow revenue/kaggriculture/cloud-market-response/flow.py \
  --score revenue/kaggriculture/cloud-score-endgame/score_endgame.py \
  --freeze revenue/kaggriculture/cloud-market-response/WOOL-FREEZE.json \
  --output /private/wool-hypotheses-results.json
```

Detailed inputs, complete per-scenario receipts, certificates, and selected
queues stay in private storage. `WOOL-HYPOTHESES-SUMMARY.json` contains only the
aggregate outcome and source identities. POLY retains its distinct expanded
current-snapshot stress-family experiment; this delivery does not modify it.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
