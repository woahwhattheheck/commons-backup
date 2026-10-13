# TITAN V3 terminal settlement certificate

`terminal_settlement.py` is a default-off, caller-owned transform for one exact
Kaggriculture boundary: the final executable action, `episodeSteps - 2` (718 in
the official 720-state configuration). It does not select a route, call a parent,
forecast a rival, or use the missing P11 service-calendar artifact.

The transform settles visible stock that the selected policy would otherwise
leave worthless at match end. It can extend a fully funded sale-only queue to
sell remaining shed stock and can change a shed-access actor's exact `PASS` into
`DROP` when an exact caller-supplied unit projection proves that no baseline or
previously admitted shed lot is displaced.

## Runtime API

```python
from terminal_settlement import compose_terminal_settlement
from scheduler import post_units

candidate, report = compose_terminal_settlement(
    observation,
    configuration,
    selected_action,
    project_units=post_units,
)
```

Inputs are copied. The return value is the unchanged selected action whenever a
certificate is unavailable.

## Admission contract

All of the following must hold:

1. The observation is the final executable step.
2. The public market exposes its sellable products.
3. The selected market is within the order cap and contains valid `SELL` orders
   only. Every requested baseline sale unit is present in the exact baseline
   post-unit shed.
4. Actor, action, position, and inventory cardinalities agree exactly.
5. Only an exact `PASS` by an actor already standing on one of the four shed
   access tiles can become `DROP`.
6. The caller's exact unit projector shows the candidate post-unit shed is
   componentwise greater than or equal to both the baseline shed and every
   previously admitted candidate shed. This rejects capacity displacement.
7. Every newly deposited product is sellable and can be scheduled under the
   market order cap.
8. Existing order positions and trailing fields stay fixed. For an already-sold
   product, only its last existing `SELL` quantity can grow. A missing product is
   added only as a tail order.
9. The candidate schedules strictly more successful own sale units. Search is
   bounded to the eight highest visible-price cargo actors by default.

Mixed buy/hire queues, underfunded sale requests, malformed projections,
non-sellable admitted cargo, and order-cap conflicts fail closed.

## Cash proof

The official engine sets terminal reward to the farm's money. Unit-stage cargo,
unsold shed contents, seeds, land, buildings, animals, and future production have
no terminal reward component.

The fully funded sale-only precondition means every baseline own sale succeeds.
For each product, any quantity extension is placed after all baseline own units
for that product; a newly introduced product is appended after the entire
baseline queue. The official market quotes both players before each lockstep
commit, so all baseline own quotes remain unchanged. Every additional successful
sale pays at least `$1`. Therefore:

```text
candidate final cash - baseline final cash
    >= candidate successful sale units - baseline successful sale units
    = report["guaranteed_min_cash_gain"]
    > 0
```

This proof holds for arbitrary legal rival sale queues and does not assume a
future quote, private rival stock, or no-rival timing.

## Evidence

Run from this directory:

```bash
python3 -m unittest -v
python3 -m py_compile terminal_settlement.py test_terminal_settlement.py
```

The focused suite contains 17 methods. One method executes 1,000 deterministic
random adversarial lockstep cases with varying rival queues, stock, market
inventory, and positive declining prices. The suite also covers:

- visible-shed settlement without changing units;
- accessible carried-stock delivery;
- exact last-order extension with duplicate product sells;
- high-value actor priority under one remaining shed slot;
- rejection of baseline-stock displacement by an earlier `DROP`;
- mixed market, underfunded sale, non-sellable cargo, order-cap, malformed state,
  projection failure, nonterminal, and input-mutation boundaries;
- an explicit eight-candidate search cap.

Measured locally on the connector worker: 17/17 methods passed; the unittest body
reported 0.365 seconds and the process wall measurement reported 0.95 seconds.
A synthetic 17-actor fixture executed 5,000 complete transform calls at a mean
1.752 ms per call using the small test projector. That timing is a bounded
microbenchmark, not a current TITAN runtime or hosted Kaggle measurement.

`RESULTS.json` records hashes and exact limitations. `install.patch` is a
reviewable default-off integration patch. Its canonical-file contexts are pinned
to branch base `7cf3468435b0102cfcfdaa8c21dfa4b05026ee81`; this candidate does not apply
the patch or change any canonical runtime, archive, config, submission, or
selected-output path by itself.

## Disposition

`SOURCE_CANDIDATE / TESTED / GAME_UNMEASURED`.

The certificate proves monotonic final cash only when it activates. Activation
frequency and whole-game W/T/L on current TITAN bytes remain unmeasured. No
leaderboard-score claim is made.
