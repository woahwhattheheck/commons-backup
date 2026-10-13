# Joint public-history terminal scenarios

`joint_terminal_history.py` is an additive consumer of the existing T12
`FlowHistory`, for POLY's existing terminal-input producer. It does not replace
inference, choose a policy, call a controller, project workers, or solve a game.

## Consumer contract

```python
from joint_terminal_history import build_joint_terminal_scenarios

family = build_joint_terminal_scenarios(
    history, mechanics.PRODUCTS, observation['step'],
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
# Feed packet['document'] to the existing score consumer with its ordinary
# action-feasibility and incomplete-receipt handling. Do not call a new parent.
```

Supply the full product universe. A slot template has `id`, nonempty `origin`,
and `slots` containing product names or `None`. Each named product occurs at
most once; its whole hypothesized lot occupies that slot. Zero leaves an empty
slot rather than moving later simultaneous orders. These templates are finite
hypotheses: past public inventory changes do not identify past or current order
positions, repeated slots, or split lots.

WHEAT and FERTILIZER are always unobserved in this adapter because the upstream
inference cannot distinguish their purchases from sales. Each completion has
`id`, `origin`, and `stock` specifying both products, including explicit zeros.
Additional `unobserved_products` require similarly explicit completion fields.
A zero completion is a declared quiet-stock hypothesis, not measured absence.

The adapter intersects complete prior same-phase, one-turn windows by the SAME
historical lag across every identified product. Minimum support applies to
that intersection. It never combines independent product medians or treats a
missing/censored sample as zero. A whole history witness stays attached to each
scenario; identical scenarios share all their original witnesses. No scenario
probabilities are assigned. Past simultaneous product totals are hypothesized
to recur; they are neither current stock nor a calibrated terminal model.

Insufficient support, unidentified slot order, omitted positive products,
capacity-incompatible completions, or more than the configured scenario budget
returns `ready=False` and no scenarios. Preserve the original complete action;
do not optimize the earlier subset or silently substitute a default stress
family. The default budget is 32, matching the existing terminal producer.

## Executed changed-path evidence

26 focused adapter methods and six input-reader methods pass. Eight constructed both-seat cases feed the
actual POLY, PORT, LARCH, PRISM, POLY full-support and T15 modules. All 624 cash
receipt comparisons match complete native terminal interpreter transitions.
There are 632 producer market calls (including eight one-cell incomplete
packets), 628 independent complete interpreter calls (including four separate
slot-gap discriminator transitions), eight native own-unit boundary captures,
and 16 actual score-selector calls. Every incomplete table preserves the
original action. Workers and inherited purchase slots remain unchanged.

In the fixed-slot discriminator, deleting an empty rival slot changes
own/rival terminal cash from 100830/100797 to 100826/100799 in each seat despite
unchanged quantities. This is one constructed mechanic, not independent games.

The separately retained TRACE/DELVE control input contains 719 already-recorded
own observation/action rows. Only its five prior terminal-phase pairs train the
adapter. Existing observed-fill reconciliation succeeds on all five; T12 gives
30 exact product observations, five floor-censored observations, and ten
intentionally unidentified operating-product observations. Joint exact support
is zero, so the original action is preserved with no terminal optimizer call.
Detailed inputs and outputs stay in the existing private evidence road.

LARCH's separate existing PRISM-derived bank supplies ten distinct runtime
payloads from sixteen original development records. All 50 prior fill pairs
reconcile. One payload has joint support four and supplies four scenarios to
four own plans: 16 native market cells and one actual score-selector invocation.
The included model finds the baseline optimal and preserves it. The other nine
payloads preserve their original action for insufficient joint support. This
bank adds 51 own-unit captures and 50 native town-consumption calls, but no
full game or actor replay. Its source-input validation remains LARCH's work.
The new reader preserves all 719 original TRACE rows exactly; the first TRACE
consumer receipt is retained at its original source checkpoint, rather than
silently relabeled as a later execution.

These checks run zero full games, zero policy-controller calls and zero new
seeds. They do not establish prediction quality, strength, a leaderboard gain,
a runtime deadline, or a selected-default change. The terminal phase may have
a different sale regime from ordinary prior days even at the same hour.

## Reproduce using existing source and input packages

From this directory, using Python 3.10 or newer:

```sh
python -B test_joint_terminal_history.py --flow flow.py --report /tmp/joint-unit.json
python -B test_joint_input_reader.py
python -B check_joint_terminal_consumer.py \
  --poly-package /path/to/extracted/TITAN-POLY-terminal-inputs-20260907 \
  --flow flow.py --output /tmp/joint-consumer.json
python -B check_joint_retained_prefix.py \
  --input /path/to/TITAN-TRACE-DELVE-control-inputs/candidate-inputs.jsonl.gz \
  --poly-package /path/to/extracted/TITAN-POLY-terminal-inputs-20260907 \
  --flow flow.py --observed-fills ../cloud-observed-fills/observed_fills.py \
  --output /tmp/joint-retained-prefix.json
```

For LARCH's second existing input format, use the same prefix command with
`--input /path/to/TITAN-LARCH-public-history-inputs-20260908/runtime/*.json.gz`.
Multiple runtime files are evaluated as separate histories; the offline
`index.json` is not an accepted input and is not read by this command.

No download or new source-export command is invoked. The existing POLY package
provides its original source, consumer dependencies, native engine and helper
for capturing the exact own-unit boundary. The retained-prefix command reuses
`ObservedFillLedger` and native town consumption before calling `infer_flow`;
submitted SELL requests are not substituted for executed quantities. It reads
no current rival queue, opponent private state, terminal scores, or future
outcomes. Native unit-boundary captures are partial interpreter executions,
not complete games or independent on-policy rollouts.

Exact consumed source: T12 flow Git blob
`7b3c1c383e98ce1eb5bf539caddf0ab4351f8633`; observed fills
`cabe10ad3d683351077c9597ad7bb36cb58ce9c6`; terminal producer
`2eae54ea4c62a83048ba8c5d69b9bbd48af2caa7` (POLY PR10099).
The existing POLY package SHA256 is
`af693707f97eea60e068a094af075255c107407c067eb82977a84a2ad74c1cd4`.
The existing TRACE input ZIP SHA256 is
`2c4018d3348cef69941f0fc8f557fbee02bb5c263cb6c94d884dfaf1a462e037`.
The existing LARCH input ZIP SHA256 is
`b64a2363365b4e6711c08c38b3398bc44466994ef3d4d75da2a35be9d8488568`.
Aggregate counts and source hashes are in `JOINT-HISTORY-VALIDATION.json`.

KEEL owns causal inference; ESTUARY owns observed fills; POLY owns terminal
inputs; PORT/LARCH/PRISM/T15 retain their existing consumer/solver interfaces.
TRACE/DELVE/FINCH retain original input provenance. This delivery owns only
this adapter, its changed-path checks and reproduction notes.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
