# Selected-history to terminal-consumer integration

This is a tested integration recipe for the existing builder, not a replacement
controller or a changed selected default. PR10129 supplies `SelectedActionHistory`;
JOINT-HISTORY PR10119 supplies `build_joint_terminal_scenarios`; POLY supplies the
terminal receipt producer. The existing score consumer continues to own table
completeness, feasibility and fallback. Their source and credit remain intact.

## Use the existing history and selected-unit snapshot

First record/observe final own actions with the existing bridge as documented in
`SELECTED-ACTION-HISTORY.md`. At the final actionable decision, use only that
same bridge's completed prior history:

```python
family = build_joint_terminal_scenarios(
    bridge.history, mechanics.PRODUCTS, observation['step'],
    slot_templates=explicit_slot_templates,
    unobserved_lots=explicit_operating_stock_hypotheses,
    capacity=configuration['shedCapacity'],
    max_orders=configuration['maxMarketOrdersPerTurn'],
)
if not family['ready']:
    return selected_action
packet = build_terminal_inputs(
    mechanics, observation, configuration, selected_action,
    post_unit_observation=same_selected_unit_snapshot,
    scenarios=family['scenarios'],
)
# Give packet['document'] to the EXISTING score selector with the existing
# feasibility callback; preserve its incomplete-table fallback.
```

Do not substitute the old scheduler's history, requested sales, independent
product medians, a second worker projection, or a second controller. An empty
family is not a reason to choose a different default stress model. No terminal
call is required on the not-ready branch. A ready family can still yield an
incomplete receipt table when its computation budget is exhausted; preserve the
existing score consumer's fallback rather than selecting from a partial table.

Slot positions and unobserved operating stocks are explicit hypotheses, not
facts identified from public market changes. The adapter retains whole same-lag
history witnesses, including their prior timestamps. No calibrated probability
or current rival order is supplied by this recipe.

## New combined-boundary execution

`check_selected_history_terminal.py` ran two test methods containing twelve
both-seat cases on Python 3.13.5. Unlike a manually populated history fixture,
all training records here come from the actual merged bridge after existing
own-fill reconciliation against native market transitions. One seat delegates
the ledger calls; the other consumes existing shared bindings/results while
instrumentation prohibits a second ledger call.

The ready histories produce twelve explicit scenarios and three complete own
plans per seat. All **72 own/rival cash pairs** match independent complete native
terminal interpreter transitions. Original worker actions, fixed HIRE/BUY_SEED
slots and caller metadata are preserved. The consumer receives the same supplied
history object and retains every scenario's origin and causal timestamps.

Ten not-ready cases cover short joint support, floor censoring, unknown slots,
unspecified operating stocks and scenario-budget exhaustion, on both seats.
Each returns the identical original action object with **zero terminal producer
or selector calls**, without needing a unit snapshot. Two additional budget-
limited terminal tables return the unchanged action through the existing score
consumer with no draw. A separate deliberately faulty readiness-bypass recipe
fails all ten not-ready cases; the shipped recipe is unchanged.

Positive-run counts: 34 constructed training market calls, two terminal own-unit
boundary captures, 74 producer market cells, 72 independent terminal interpreter
calls and four score-selector invocations. The test makes zero actor calls,
complete-game runs, input-bank replays or new game-seed requests. This is an
interface/receipt check, not strength evidence or a policy promotion. The
previous 24-method bridge suite and retained 718-transition result are separate
already-published evidence, not reruns by this follow-through.

## Reproduce with existing files

From the repository's `cloud-market-response` directory:

```sh
python -B check_selected_history_terminal.py \
  --poly-package /existing/TITAN-POLY-terminal-inputs-20260907 \
  --output /tmp/selected-history-terminal-results.json
```

Default paths use the adjacent bridge, history and joint adapter and sibling
`cloud-observed-fills/observed_fills.py`. The POLY archive already contains its
original source, consumer dependencies, engine cache and native snapshot helper.
No network fetch or new source-export job is run. Each output records all actual
source/dependency hashes and the three checked official engine hashes.

This execution consumes the original POLY package SHA256
`af693707f97eea60e068a094af075255c107407c067eb82977a84a2ad74c1cd4`.
Its score consumer precedes the separate LARCH cash-tie and ANCHOR context work;
this result does not claim those newer versions were exercised. No current
objective/context file is modified here.

New check SHA256:
`28959995864a446d5a39cbc2efbfd4336ff0fb2fa38e03104a8e9e56fd896558`.
Executed bridge Git blob: `59d85cefb4cb793f8d7a3fc79d8e5675449956fb`.
Executed joint-adapter Git blob: `3d03475fb422fa0aab998b3f537a1b9532ff6e90`.
Exact output tables, logs and the negative-control source/output are retained in
the separate private CEDAR history-terminal-join packet. Original dependency and
input packages are referenced, not republished.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
