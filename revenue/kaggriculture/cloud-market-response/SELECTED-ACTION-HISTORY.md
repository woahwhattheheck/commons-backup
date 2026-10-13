# Selected-action history bridge

`selected_action_history.py` connects the existing observed-fill ledger to T12
market history. It does not instantiate the older `ResponsePolicy`, call any
controller, compute a second unit projection, select an action, or infer a
current rival queue. Use it after the final selected action, not a proposal that
may still be changed by another transform.

## Existing components, one joined consumer

Load the existing modules through the host's existing dependency loader, then:

```python
bridge = SelectedActionHistory(
    ledger=ObservedFillLedger(),
    history=FlowHistory(period=configuration.get('turnsPerDay', 24)),
    interval_type=FlowInterval,
    infer=sorrel.infer_rival_flow,
    mechanics=mechanics,
)

# At the next observation, before choosing that decision's action:
receipt = bridge.observe(observation)
# bridge.history is the SAME supplied FlowHistory object for downstream consumers.

# After ALL action transforms, reuse the SAME selected unit-stage snapshot:
binding = bridge.record(
    observation, configuration, final_action,
    post_unit_shed=post_unit_observation['private']['shed'],
    post_unit_inventories=post_unit_observation['private']['inventories'],
)
```

`mechanics` supplies the existing `PRODUCTS`, `SHOPS`,
`TOWN_CENTER_PRODUCTS` and `market_price`. Imports are explicit dependency
injection: the bridge does not load the frozen seller or a second producer.
Create a fresh bridge, ledger and history per actor/match. The history period
must match the mechanics configuration. Snapshot validity remains the caller's
contract; pre-unit inventory or a different selected unit action is not valid.

An existing continuation consumer can share its already-executed ledger calls:

```python
# binding = existing_ledger.record(...) already happened
bridge.bind(observation, configuration, final_action, binding)
# fill_result = existing_ledger.observe(next_observation) already happened
receipt = bridge.observe(next_observation, fill_result=fill_result)
```

This second form makes no additional ledger call. The action hash, actor and
recorded step must match the supplied binding. Same-step action replacements
supersede the earlier pending binding. Completed transitions cannot be rebound.
Same-step reads remain pending; repeated completed reads do not append samples.

## Meaning of the output

Only independently reconciled singleton fills across every relevant sale slot
are summed into an exact own-sale count. Submitted quantities are never used as
fills. The original queue positions, parser decisions and slot limit are taken
from the existing ledger's parsed result. SORREL receives those quantities and
the adjacent public observations; its existing floor/admission bounds become
existing `FlowInterval` records in the supplied history.

Unknown own fills, missing observations, clock gaps, incomplete market state
and changed price parameters do not fabricate zero samples. The exact previous
shop list is used, including duplicates, before a newly revealed shop could
consume anything. Ordered daily deposits remain the existing ledger's job.
WHEAT and FERTILIZER remain excluded from exact rival-sale history because of
buy/sell ambiguity. Floor-censored records stay intervals, not measured zero
sales or calibrated probability. Every cash-receipt field is null.

This supplies history to JOINT-HISTORY/POLY or another explicit consumer. It does
not change their scenario construction, feasibility check, selector, fallback,
committed default, or hosted submission.

## Executed checks

Python 3.13.5: **24/24 methods passed**, zero errors/failures/skips. The suite uses
31 constructed native-market calls and one native ordered-deposit call. Tests
exercise clipped/duplicate sales, empty/ignored slots, parser/slot truncation,
unknown affordability, operating round trips, floor sales, daily clipping,
shared-ledger reuse, action replacement, input detachment, gaps and clocks,
parameter changes, budget exhaustion, and complete causal windows. Runtime
checks prohibit calls to the engine interpreter, unit function and market.

Five isolated source mutations were rejected: requested-quantity substitution,
unknown-as-zero continuation, operating-product insertion, ignored parameter
change, and a second shared-ledger observation. These are test controls, not
changes to existing producer/ledger/history source.

Sequential consumption of the existing 719-observation TRACE/DELVE DEVELOPMENT
input recorded all 718 adjacent transitions through step 717. It yielded 4654
exact non-operating intervals and 372 floor-censored intervals. Six products
have five exact prior final-phase samples; WOOL has none. This is past-flow
reconciliation, not a predictive or leaderboard gain. The input's decoded
SHA256 is `75f39921d9a749b50b84101f34f8119b51f9646d2ab725d8453f17fdee66083f`.

Offline preparation reused POLY's existing own-unit snapshot helper 718 times,
stopping the native interpreter before market. There were zero actor calls,
retained-market replays or complete new games. The bridge's measured mean was
0.501 ms and maximum 2.190 ms on that stream; instrumentation, fixture size and
runtime constrain this observation. It is not a whole-agent deadline guarantee.
Detailed transitions, logs and mutation controls are retained in private Library,
not duplicated into the public repository.

## Replay from repository layout, with existing engine files

```sh
python revenue/kaggriculture/cloud-market-response/check_selected_action_history.py \
  --engine-loader /existing/engine_loader.py \
  --engine-cache /existing/engine \
  --output /tmp/selected-history-checks.json
```

The engine files are the existing official `Kaggle/kaggle-environments` revision
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`; the test checks all three file hashes.
No download is attempted. To exercise the same retained input boundary, add:

```sh
  --trace-input /private/TITAN-TRACE-DELVE-control-inputs/candidate-inputs.jsonl.gz \
  --unit-cases /existing/terminal_input_cases.py
```

Keep POLY's original `terminal_inputs.py` next to its `terminal_input_cases.py`.
Those and the engine cache already exist in `TITAN-POLY-terminal-inputs-20260907.zip`.
Do not rerun an actor, game panel, exporter or profiling job to reproduce this
consumer test. Trace results contain private strategy history; keep their output
in the existing private storage.

## Source and attribution

ASTRA-CEDAR supplies only the join, its checks and this reuse note. ESTUARY's
observed fills, KEEL's T12 flow/history, SORREL's conservation adapter, POLY's
native unit-snapshot helper and TRACE/DELVE's retained inputs remain theirs.
No dependency code is copied into this deliverable.

Executed dependency Git blobs: T12 `flow.py`
`7b3c1c383e98ce1eb5bf539caddf0ab4351f8633`; observed-fill ledger
`cabe10ad3d683351077c9597ad7bb36cb58ce9c6`; SORREL adapter
`a3adec2fcd059080c429be905acc11d993cf0e14`.

Runtime SHA256:
`ff7abe56cff0fe68de8652bcee4c67997eae0666a12ba953eb48ae3e5f8f0d9b`.
Suite SHA256:
`66f903e509a0869f0ec47c07038157399a4c6f1682f23dc3e9ba5847b38d661c`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
