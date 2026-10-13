# Explicit rival hiring in terminal receipts

The existing terminal-input producer can now consume caller-supplied whole
rival queues containing SELL and HIRE, using `allow_rival_hire=True`. The
flag defaults to false. The existing sale-only stress family, own-plan
construction, native market, score solver and selector are unchanged.

This is a bounded scenario-interface extension, not a hiring predictor. It
adds no scenario and assigns no probability. Rival goods remain an explicit
joint-capacity hypothesis; money, current workers and `hires_today` come from
the same current public observation used for every own plan. The native
interpreter, not a precomputed affordability label, determines each hire's
execution after the preceding ordered transactions.

## Why this matters

A constructed final-turn case has one own MILK unit, two hypothesized rival
MILK units, public rival cash59, and13 hires already made that day. The next
native hire costs377. Consider delaying our sale to slot1 versus moving it to
slot0, with the rival selling its two units in slot0.

| Complete own plan | Rival sells only: own / rival cash | Rival then attempts HIRE: own / rival cash |
| --- | ---: | ---: |
| Original delayed sale | 156 / 377 | 156 / 0 |
| Early sale | 160 / 375 | 160 / 375 |

With only the sale column, the early sale improves our relative cash by6 and
ties the absolute terminal score, so the existing opt-in cash-Pareto rule
selects it. With the later HIRE present, reducing rival sale proceeds by2
makes the rival unable to pay377. It keeps375 instead. The original queue
wins that constructed scenario; the early queue loses it.

Keeping BOTH hypotheses gives terminal point rows `[0,1]` and `[0,0]`. The
existing selector retains the original action, with no draw. Its worst
included point value is still0; this is not a guaranteed win across worlds.
The example executes identically in both player positions through the full
pinned interpreter. It is not a reached-game frequency or gameplay result.
The earlier32-record cash-tie counterfactual evidence is unchanged; this
example does not assert that those old records contained a rival hire.

## Callable

```python
packet = build_terminal_inputs(
    mechanics, observation, configuration, selected_action,
    post_unit_observation=the_same_selected_unit_snapshot,
    scenarios=[
        {"id": "sale-only", "shed": {"MILK": 2},
         "market": [["SELL", "MILK", 2]],
         "origin": "explicit conditional hypothesis"},
        {"id": "sale-then-hire", "shed": {"MILK": 2},
         "market": [["SELL", "MILK", 2], ["HIRE"]],
         "origin": "explicit conditional hypothesis"},
    ],
    allow_rival_hire=True,
)
```

The same `packet['document']` feeds the existing absolute-score consumer.
Only complete packets may start a decision. Missing cells preserve every
original row/column and leave nonterminal/null receipts; deadline and cell
limits must not become an optimized subset. HIRE requests are left in their
exact slots, including failed requests and repeats. Their escalating native
costs and new-worker counts are calculated separately for each own plan.

This mode requires explicit scenarios and an explicit boolean flag. The new
public hiring-count bound is an integer from0 through the current number of
rival workers. Existing worker, stock, quantity, scenario-count and slot
bounds remain. Other rival operations, including BUY_PRODUCT, BUY_SEED,
BUY_ANIMAL and BUY_LAND, remain outside this narrow interface. Unsupported
queues raise before native execution rather than being dropped or relabeled
as a sale scenario. The default still rejects HIRE.

Only opt-in receipts add `rival_hands_after` and `rival_hires_today_after`.
Their source records the `caller-supplied-sale-and-hire-hypotheses` family and
`rival_hire_enabled=True`. Original sale-only packet fields and their source
labels remain byte-for-JSON equivalent in the checked cases. No runtime
controller is constructed, no own unit stage is recomputed, and no hidden
rival inventory, authored current action or later outcome is read.

The canonical TITAN release and feature switches are not changed by this
source increment. A later deliberate consumer can provide explicit supported
queues on an independently identified source. Current history/IRIS proposals
must not be converted into a certain whole rival queue merely to use this API.

## Executed tests and source binding

Eighteen new methods pass with0 failures,0 errors and0 skips. The completed
run contains63 producer-native cells,14 original-producer correspondence
cells,32 full terminal-interpreter comparisons, and1 own-unit boundary
capture stopped before market. Eight complete default packets match original
producer2eae54ea exactly. These are overlapping component comparisons, not
independent game samples. No full game, held panel or game seed is used.

The full interpreter comparisons include native cash, final status, own
stock/seeds/workers and rival worker/hire counts. Tests cover both positions,
the cash58..61 affordability threshold, repeated Fibonacci hiring, zero
cost multiplier, final slot position, input detachment, explicit-only mode,
public-count validation, incomplete cells and propagation of the original
BaseException cancellation. An actual DROP snapshot is consumed without a
second unit call. The actual PORT/POLY/LARCH/PRISM/T15 selector consumes the
new matrix; no replacement optimizer or action selector is tested instead.

Two deliberately incorrect local variants are detected: discarding HIRE
slots produces6 failed methods, and resetting the public hire count produces5;
both run all18 methods with0 errors and0 skips. Their reports stay separate
from the successful source. The initial exploratory native probe is retained
as development evidence, not added to the completed test count.

Runtime changes are confined to `_scenarios` and `build_terminal_inputs`.
Every other existing function, including `market_cell`, `sale_plans`,
`stress_scenarios` and current-state preparation, remains AST-identical.
The full source identities and original/final outputs are in the private
reuse packet; compact identities are in RIVAL-HIRE-RESULTS.json. The original
producer is POLY2eae54ea; score consumer is LARCHf8219d69 (cash tie plus ANCHOR
context); cached exact POLY7f7e2e9d, PRISM2c21f897 and T15546b7118 are used.
The engine is upstream28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c.

## Reproduction

Use the existing extracted POLY source/dependencies/engine package plus the
cash-tie score source, or the self-contained new evidence packet. No network
is needed or used; the existing loader requires all three native engine files
before invocation. From the new evidence packet root:

```sh
python -B source/test_rival_hire.py \
  --context context \
  --runtime-file source/terminal_inputs.py \
  --score-file context/dependencies/score_endgame.py \
  --original-file context/source/terminal_inputs.py \
  --output /tmp/rival-hire-new.json
```

Use this explicit CLI to initialize its real dependency context, not generic
unittest discovery. An existing output path is preserved and causes an error.
The resulting report records all14 supplied source identities and the exact
constructed matrices/selector results. Later dependency versions require a
separate source-specific result rather than reusing these recorded counts.

An early GitHub transport copy lost a parenthesis in the otherwise unchanged
stress-family line. That branch-only copy was corrected before PR creation;
the published runtime now exactly matches the already-executed local blob.
No test success is attributed to the malformed transport copy.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
