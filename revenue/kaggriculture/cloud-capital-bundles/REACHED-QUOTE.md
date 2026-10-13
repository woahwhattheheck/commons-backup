# Reached-input conditional quotation

`reached_quote_case.py` connects the published HAZEL market-program quotations to ROUTE-FLOW's dated receipts and DATE's existing ranker. It consumes the shared retained-input normalizer. None of those four components is reimplemented or changed, and this helper is not a live agent.

## Run

Use an existing Commons source checkout and the private input/scenario files:

```sh
python reached_quote_case.py input-row.json scenarios.json --output result.json
OSPREY_QUOTE_INPUT=/path/to/input-row.json OSPREY_QUOTE_EXPECTED=/path/to/expected-result.json \
  python -m unittest -v test_reached_quote_case.py
```

Run from this directory. The default dependency root is the parent `revenue/kaggriculture/` directory; `--kaggriculture-root` selects an existing relocated source tree. All six dependency identities are recorded in `DEPENDENCIES` and the result. Nothing is downloaded or installed. An existing output file is preserved.

Input rows use the existing recorded-input shape: `step`, `seat`, `observation`, `configuration`, with optional evaluator fields. The shared normalizer retains only the delivered observation and public configuration before quotation. Expected actions, final labels, and evaluator configuration seeds do not enter pricing. Keep the original input receipt separately: the helper does not certify whether a caller's row came from a recorded game or a constructed fixture.

`scenarios.json` is a nonempty JSON list of explicitly declared worlds. Each object has `name`, and optional `description`, `shop_additions` and `rival_orders`. The latter two map future decimal step keys to the existing FLOW values. Preserve complete ordered rival market slots, including PASS, and repeated shop instances. The helper does not assign probabilities, derive a future buyer from later recorded observations, or drop an incomplete world to improve a route's ranking.

`load_dependencies(root)` returns the exact original modules. `compare_saved_input(row, specifications, dependencies, max_units=100000, seconds=0.2, retain_trace=True)` produces original marked offers, the complete FLOW report, DATE's joint and individual-world rankings, and reconciled accounting. Incomplete flow returns `complete=false` and no ranking; the CLI writes that diagnostic and exits3. Invalid input/IO exits2. Successful comparison exits0. The cooperative budget covers FLOW's original scope, not imports, quotation, ranking, or a hard preemptive deadline.

## Meaning and limits

The two static programs come from `arlene.routes()`. No Agent is constructed or called; no current or future controller state is restored; no live route is applied. A complete producer route also includes worker operations, source amendments and successful physical fills. The emitted market quotations are not a replacement for those mechanisms.

Every future trade quantity and original fixed-cost quotation remains conditional. `minimum_marked_cash` is an ordered nominal budget, not proof of inventory, delivery or execution. DATE ranks own cash across the supplied scenarios, not game win probability; FLOW's rival effects remain separately available. Keeping current shops forever with no rival flow is an explicit counterfactual, not an asserted prediction. A later-shop scenario is likewise not a feature observed at the selection point.

This specific consumer compares the original MAIN/SHEEP quotations at226. It does not invoke HAZEL's live compatibility check or certify that the original integrated controller can be reset at that step. FINCH/TRACE's actor-history restoration, RILL's physical continuation, and DATE/FLOW's model ownership remain separate.

## Executed validation

18 regression methods passed with the retained natural input and its private expected-result file. They cover exact component calls, zero actor/switch calls, unchanged programs/inputs, scenario provenance, missing/budget-exhausted flow, clock/seat binding, JSON date conversion, duplicate shops/slots, fresh output behavior and CLI status. Without both private fixture environment variables, the 17 constructed/CLI methods run and the natural-input method is explicitly skipped.

The actual source case is TRACE's saved DELVE development control input, not a reconstructed WIDEFIELD or HAZEL-candidate checkpoint. Two explicit scenarios and two programs yielded four matching FLOW/DATE final/minimum/first-negative accounting records and870 variable settlement rows. The native CLI reproduced the direct-module comparison. The private reuse package contains the original input-line identity, original stream receipt, scenarios, source closure, expected values and full outputs. No new full game, interpreter replay, held seed, live action, or policy promotion occurred in this comparison.

The earlier capital-agent export and its16-test report remain byte-identical. This follow-through is an offline comparison consumer; it is not included automatically in that submission-shaped archive and does not alter the selected TITAN entrypoint.

DATE's additive completed-replay extension landed during this integration. This consumer uses its current nominal API at blob `5e418aeca191e71d281f669a9fdd9f4b0730617f`; all18 methods passed again, and the complete saved-case comparison remained identical apart from source provenance. Its new physical-outcome branch is not called here. Earlier direct-comparison output is preserved privately with its original source identity.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
