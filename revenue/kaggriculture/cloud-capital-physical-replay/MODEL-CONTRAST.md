# Saved nominal versus complete-controller outcomes

`contrast_saved_models.py::compare_reports` compares existing records only. It
imports no policy, simulator, price function or alternative selector. The CLI
uses the unchanged shared `reached_states.actor_input` normalizer to bind the
same delivered observation/configuration, then joins original route/scenario
identities and preserves indexed market slots.

## Result

Inputs are the exact PR10220 natural DELVE9965001/p0 physical report and OSPREY's
PR10102 nominal report. Both start at the same decision226 input and compare MAIN
and SHEEP under the same current-shop/no-rival and hypothetical-YARN288 futures.
The physical actor includes the entire restored integrated producer and SELL
state; the nominal model assumes the stored program's requested volumes execute.

| Scenario | Route | Nominal final cash | Physical final cash | Difference |
| --- | --- | ---: | ---: | ---: |
| No new buyer or rival flow supplied | MAIN | 86,920 | 89,291 | +2,371 |
| No new buyer or rival flow supplied | SHEEP | 81,878 | 84,040 | +2,162 |
| Hypothetical YARN first visible288 | MAIN | 106,810 | 109,492 | +2,682 |
| Hypothetical YARN first visible288 | SHEEP | 115,617 | 118,750 | +3,133 |

All1,972 saved whole-market cash transitions reconcile exactly from opening cash8
through terminal cash. These differences are NOT new policy gains, paired-game
results, same-state price effects or evidence that one forecast is calibrated.

The first indexed-queue difference is237: a zero-quantity WHEAT sale is omitted.
The complete cash paths still agree through257. The first effective request and
cash difference is258 in all four cases: the nominal program sells MILK12 for
1,732; the physical actor emits an empty market slot. Its recorded post-unit shed
contains MILK12 before and after market, so this first omission is a changed sale
decision rather than missing milk. No new engine replay is needed for that fact.

For example, at269 in the MAIN/no-new-buyer pair, both paths request MILK6, but
the recorded cash is969 physical versus804 nominal. Earlier different sales have
already changed the market history. Therefore unchanged current commands can
have different cash, and the reader does not assign their difference to a new
per-product decision or pretend that the states still match.

The cash split on changed versus unchanged indexed-queue rows is retained only
as bookkeeping. Changed rows account for972/1,193/824/1,927 across MAIN/no-buyer,
MAIN/YARN, SHEEP/no-buyer and SHEEP/YARN respectively; unchanged rows account for
1,399/1,489/1,338/1,206. Each pair sums to the table's terminal difference. This is
not a causal decomposition: the omitted nominal worker and inventory states are
not reconstructed, and past changed decisions affect later unchanged queues.

## Reuse

```sh
python contrast_saved_models.py \
  --physical /path/to/reached-final.json \
  --nominal /path/to/current-date-result.json \
  --normalizer /path/to/cloud-terminal-sell/reached_states.py \
  --output contrast.json
```

Use normalizer Git blob24f8bd4cac2e88c609f309aa241eca8f3d1e05ee from the existing
OSPREY archive. Source hashes and raw input hashes are recorded in the adjacent
compact result. The full output includes every cash-difference row, the first
queue/cash witnesses and original source pins. Every nonempty slot keeps its
original index; ignoring zero requests never moves later HIRE or purchase slots.
Missing/duplicate cases, changed input/program/future identities, broken cash
continuity and incomplete reports are not compared as complete.

Ten data-only regression methods and the real CLI passed. No actor, engine,
profiler, new game, scenario, seed or policy was executed or changed. Existing
PR10220 and PR10102 model runs are reused, not counted again. The repository JSON
is a compact result; full comparison and original inputs remain in the separate
`titan-rill-model-contrast-20260908.zip` Library package. Its root README contains
the extracted-package command. New files are Apache-2.0; the existing normalizer
retains its MIT license and attribution.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
