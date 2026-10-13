# Reached-state inputs for the terminal score consumer

`terminal_inputs.py` supplies the missing receipt-producing step for the existing
PORT terminal table and LARCH absolute-score selector. It accepts one selected
complete action and the already-computed **same action's own-unit snapshot**.
It generates a bounded family of market alternatives, runs the unchanged native
market for each complete rival hypothesis, and returns the raw PORT document.
It constructs no controller, replays no worker action, calls no optimizer, and
samples no plan. ADMISSION's worker/deposit search and the original LARCH/PRISM
selection implementation remain separate.

## Runtime use

```python
from terminal_inputs import build_terminal_inputs

# post_units is the SAME selected unit stage's post_unit_observation, for
# example a caller's existing OrderedSelectedSell.prepare result. No second
# prepare/controller call is needed. score_selector is the existing LARCH
# selector, one per actor, with the existing PORT/POLY/PRISM/T15 dependencies.
try:
    packet = build_terminal_inputs(
        mechanics, obs, cfg, selected_action,
        post_unit_observation=post_units,
        scenarios=causal_whole_sale_hypotheses,
        max_plans=8, max_cells=256, deadline=caller_monotonic_deadline,
    )
except ValueError:
    output = selected_action
else:
    output = score_selector.transform_terminal(
        obs, cfg, selected_action, document=packet['document'],
        feasible=current_complete_queue_feasibility,
    ) if packet['complete'] else selected_action
```

`mechanics` supplies the pinned engine's `PRODUCTS`, `market_price` and unmodified
`_process_market`; the tested provider is the complete official module loaded
from the existing source cache. This module imports no Kaggle package, downloads
nothing, and does not bundle a substitute engine. Integrators must retain the
actual mechanics dependency; this delivery is not a new standalone default agent.

Only the final actionable step (`episodeSteps - 2`) is supported. The native
unit/production/day-close operations do not change money after the final market,
so the paired market balances equal terminal cash, including when the final step
is a day close. The snapshots may contain own private inventory, which is a valid
agent input; no rival private state is read. The counterpart farm's visible cash
and current public market are taken from the original observation, not from an
invented rival unit continuation.

The caller is responsible for the snapshot's actual action provenance and its
own cash/stock reservations. Matching step/player and an unchanged market are
necessary checks, not proof that an arbitrary snapshot belongs to the action.
A feasible completed engine action may contain a partial fill or a legal no-op;
receipts use the actually executed result, never assume every requested unit sold.

## Complete own queues and rival scenarios

Baseline is first and remains exact. Up to seven alternatives liquidate available
post-unit product stock in different fixed SELL/empty positions. The finite family
uses current quote-value ordering, reverse/alphabetic ordering, and individual
product-first orders. It is not an exhaustive queue optimizer. All other action
fields, all inherited non-SELL positions, and any engine-inactive tail are retained.
In particular, an earlier sale can fund an unchanged later HIRE: the entire native
queue is executed, so that cost is not mistaken for profit.

A supplied rival scenario is:

```python
{'id': 'prior-public-window-1',
 'shed': {'WHEAT': 17},
 'market': [['SELL', 'WHEAT', 17], []],
 'origin': 'caller description of causal public-history source'}
```

There must be 1..32 whole scenarios, each with distinct identity, nonnegative
product stock under the **joint** shed capacity, and enough stock for the entire
fixed-slot SELL queue. This producer supports rival sale-only scenarios, not
rival buying, hiring, or probabilistic beliefs. Those excluded behaviors can
change the optimum; it is not a universal rival-response guarantee. Every own
plan faces the same complete scenario with the same slot indices. The caller
establishes causal/history applicability of externally supplied scenarios; the
labels themselves are not that proof.

With `scenarios=None`, the default is explicitly a **finite, uncalibrated
current-snapshot stress family**: quiet empty shed, each product filling a shed
and sold at the first or last market slot, plus two mixed-capacity lots. At the
normal ten-slot setting this gives 21 columns. These are individually legal
post-unit hypotheses, not estimates of hidden holdings. Earlier public history
may exclude some; other possible scenarios are absent. Scenario probabilities
and calibrated win probability remain null. Do not present this family as a
learned history model or silently remove adverse columns after seeing outcomes.

## Results, limits, and feasibility

The packet includes `document`, original `plans`, detached `scenarios`, call counts,
`complete`, `status`, and exact `fallback_action`. PORT receipts retain own/rival
cash, actual own action, current step, and consistent plan/scenario/current-state
hashes. The state hash includes available own private state and the supplied unit
snapshot; the PORT field name is not a claim that the hash excludes own inventory.

At most 8 real plans and 32 scenarios are admitted; `max_cells` is 0..256. Quantity,
configuration and worker limits bound the supported runtime. Invalid or unsupported
inputs raise `ValueError` rather than return fictitious completed receipts. A
`deadline` is an absolute `time.perf_counter()` timestamp in this process, checked
between native market calls. It is cooperative, not a hard preemptive timeout.

Cell/deadline exhaustion retains every missing cell with null balances and
`done=False`. PORT/LARCH therefore see an incomplete table and keep the supplied
action; a completed-looking subset is never optimized. A native receipt is a
conditional hypothetical execution, not proof of a subsequently observed real fill.
The existing current full-queue feasibility callback remains the caller's duty.

## Executed evidence

The 20 new focused methods pass with no failures, errors or skips. The final run
contains 257 producer market calls and 59 separate full official-interpreter cash
comparisons, including both positions, custom resolved market parameters, floor
sales, inherited buying/hiring, DROP-stage reuse, inactive slots, incomplete-table
fallback, and unchanged results when evaluator-only fields are added.

The existing PORT constructed lead-33 fixture passes through the new producer
and actual corrected LARCH/PRISM/POLY/T15 modules: baseline has a losing included
column, while the generated wheat-first complete action wins both. The lead-30
fixture retains the one-draw 1/2 mixture over its two complementary alternatives.
These are new producer integration checks on an accepted constructed regime,
not new full-game wins or another run of PORT's original test suite.

The reached-state pass consumes the existing private T05/SELL development archive:
32 retained records, 24 unique observation payloads, only 2 original independent
seeds. It uses the **recorded own action as an explicitly supplied selected-action
boundary**; it does not recreate a stateful controller from a single frame.
The runtime producer sees observation/configuration/own action/post-unit state
only. The recorded current rival action and terminal private state are used after
selection solely to reconstruct the final market for evaluation.

All 32 original cash pairs reconcile exactly before those final-market
counterfactuals. The pass executes 4,452 conditional native cells plus 64 separate
evaluation-only market calls. The stress family changes zero selected actions:
24 records have baseline and best worst-included win-point floor 0; 8 have floor 1.
The original 28 wins/4 ties remain unchanged across these repeated trajectory
records. This is neither 32 new games nor 32 independent observations. No held
records or fresh gameplay seeds are consumed.

Maximum measured producer time is 223.3 ms; the separate selector maximum is
87.5 ms. These maxima are from a single retained-input pass, exclude controller
work and the evaluator's unit-boundary capture, and are not a whole-agent bound.
The two maxima need not occur in the same record. The broad stress model's lack
of selection is not evidence that a causally narrowed scenario family cannot
help. Such a family is the next meaningful consumer input, not another solver.

The reached pass used the same successful-input logic before two editorial
string changes; the private archive retains that source and the published
version separately. The final focused suite executes the published bytes.
The first focused attempt's custom-price fixture supplied sparse parameters
where the native observation requires resolved parameters; both that retained
attempt and the corrected native fixture are in the private packet.

## Frozen-family diagnostic

`diagnose_terminal_family.py` reads the already-saved runtime report and executes
every existing candidate against the evaluation-only recorded rival queue. It
never regenerates plans, calls the selector, or changes the model. Observation
and original-action bindings are checked before each case.

The separate 212-call diagnostic finds a better realized-margin member in 16 of
32 retained records. All four original baseline ties contain an alternative that
wins that recorded final market, with margin improvements of 189 or 320. These
are hindsight best-in-family results, not available runtime decisions, new full
games, or evidence of a promoted policy. The runtime still changes zero actions.

One retained tie is especially discriminating: a pre-generated queue moves
CARROT/EGG/FERT before WOOL. Its relative-cash delta is zero in every default
stress column, but 189 against the recorded complete rival queue. The finite
scenario family misses that correlated interior-slot pattern. Extreme full-shed
columns also flatten the absolute point floor. The meaningful next input is a
causal whole-window rival-flow family from the existing T12 machinery, not an
extra optimizer or an invented probability. No model was retuned on this result.

To reproduce this diagnostic without rebuilding the runtime receipt tables, use
the same dependency and archive arguments as `terminal_input_cases.py`, then add
`--saved-report /private/reached-first.json --output /tmp/new-family-diagnostic.json`
to `diagnose_terminal_family.py`. The full per-plan diagnostic stays in private
project storage with the other reached-state evidence.

## Source and storage

Engine: `Kaggle/kaggle-environments@28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`,
Python SHA256 `bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`.
Existing source artifact `10005621438` supplies the engine and accepted offline
`peer/evaluate.py` loader. No new export was created.

Consumer Git blobs: PORT `6734e0b37c9a6a78fb9cff8cd5bbd94d260054ab`;
corrected LARCH `543ab5b4536a2b9605ee4c7c69aabfb637811760`;
PRISM `2c21f8975a64961aec0b94fc6ea930318fec111b`;
T15 selector `546b71188fd44dc47cac99623d1967bc81413da7`;
T15 solver `3a6446d96e8470374dd5b5ba72a8e5c6d41a8ad3`;
POLY cached core `7f7e2e9d62a655e24219490e9c54ab23019f1520`.
All remain reused dependencies, not copied into this public addition.

`TERMINAL-INPUTS-RESULTS.json` is the compact source-bound public receipt.
Full reached receipt matrices, original observations/actions, evaluation-only
reconstruction data, full test outputs and their source manifest are retained in
the account Library as `TITAN-POLY-terminal-inputs-20260907.zip`. Keep these detailed
inputs in private project storage. The accepted intake zip and raw source archive
remain unchanged; no new selected/default/hosted agent is published.

## Reproduce from an existing cloud workspace

`--consumers` names a directory containing the exact five existing files listed
above: `terminal_utility.py`, `score_endgame.py`, `weighted_selector.py`,
`selector.py`, `solver.py`. It can be the retained private package's dependency
folder; it does not require cloning or a new transport job. `--loader` is the
existing artifact's `peer/evaluate.py`; the cache must already contain all three
pinned engine files. The commands perform no download and require new output
filenames so retained runs are not overwritten.

```sh
python3 -B test_terminal_inputs.py --loader /existing/peer/evaluate.py \
  --engine-dir /existing/engine --consumers /existing/consumers \
  --core-file /existing/cloud-full-support/full_support.py --output /tmp/new-terminal-tests.json
python3 -B terminal_input_cases.py --loader /existing/peer/evaluate.py \
  --engine-dir /existing/engine --consumers /existing/consumers \
  --core-file /existing/cloud-full-support/full_support.py \
  --archive /private/osprey-terminal-sell-raw.json.xz --output /tmp/new-reached-terminal.json
```

The offline case driver captures the native interpreter's unit boundary in an
isolated test invocation. That capture is not part of the runtime producer.
Evaluation-only stock reconstruction requires the retained non-EOD final step
and exact baseline cash reconciliation. The driver consumes only `dev/` members.

New code is Apache-2.0 under this directory's existing license. The original
engine, PORT and other component authorship and notices remain intact.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
