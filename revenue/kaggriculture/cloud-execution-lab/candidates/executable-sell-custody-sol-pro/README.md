# TITAN V3 executable SELL custody — SOL-PRO

Operation: `TITAN-V3-EXECUTABLE-SELL-CUSTODY-20260910-01`

## Source-proven defect

The official engine normalizes `maxMarketOrdersPerTurn` to at least one and
executes only `market[:N]`. Exact current `FrozenSelected.transform()` still
allows rows after that prefix to influence baseline sale quantities, future
references, cash and capacity projections, admission, materialization, and
pending-stock retirement.

The predecessor-discriminating witness is:

```python
maxMarketOrdersPerTurn = 1
shed = {"CARROT": 3}
market = [[], ["SELL", "CARROT", 3]]
```

The engine executes the blank row and sells zero CARROT. The predecessor can
nevertheless count the suffix as `offered == 3`, consume all three units while
materializing, and clear `pending["CARROT"]`.

This is the explicit merge blocker recorded on closed PR #11840. That branch is
not reopened here.

## Candidate boundary

`ExecutableSellCustodyFrozenSelected.transform()`:

1. Git-blob pins exact current `frozen_selected.py` and inherited `scheduler.py`;
2. computes the official `max(1, configured)` queue limit;
3. shallow-copies the selected action and selected represented route with only
   executable market prefixes;
4. delegates the *unchanged* exact current transform against those views;
5. restores the original controller in `finally`; and
6. reattaches the original engine-inactive suffix byte-for-byte without moving
   its indexes.

The complete seller transform therefore has one coherent information boundary:
an engine-inactive row cannot create funding, capacity, admission, sale, or
pending-retirement effects. Every active-prefix row, farmer action, hand action,
optimizer, price rule, funding rule, horizon rule, seller ledger, and
non-market field remains controlled by the current implementation.

The candidate deliberately does not invent a new sale from a suffix intention.
A later experiment may test that policy, but it is not mixed into this custody
repair.

## Executable carrier

`carrier.py` and `executable_receipt_profile.py` are byte-identical copies of
the source-reviewed private archive carrier inputs from closed PR #11840:

- carrier Git blob `6cf5fa502e5f79dabbb1a95cf645558cb5c52bce`;
- bootstrap-patch Git blob `8e984812e15a84db14ee7311b047e0c8483132da`.

`candidate.py` verifies both, verifies the new patch blob, imports the carrier,
and replaces its not-yet-invoked install hook before canonical lazy
construction. The dormant bootstrap patch is loaded only because the reviewed
carrier verifies it; it is never installed. The runtime receipt must name
`ExecutableSellCustodyFrozenSelected` and factor
`engine-inactive market suffix quarantine`.

The carrier independently verifies the exact standalone archive, `SOURCE.json`,
all runtime members, private materialization, module origins, and collision
boundary. Mutable lab sources are not execution dependencies.

## Gates

Focused contracts cover:

- the exact `[[], ["SELL", "CARROT", 3]]`, `N=1` counterexample;
- active-prefix SELL retirement;
- future-route suffix quarantine;
- action and route nonmutation;
- suffix byte/index preservation;
- `max(1, N)` normalization;
- active-prefix parity when no suffix exists;
- controller restoration on exceptions;
- idempotence and source-drift rejection;
- malformed queue rejection; and
- current source Git-blob identities.

`route_census.py` inventories suffix SELL rows in every exact represented route
and reports `STATIC_SIGNAL` or `NO_STATIC_SUFFIX_SELL_SIGNAL`; it is not action
or score evidence.

`carrier_smoke.py` constructs the patched consumer in a `python -I` process and
then runs the pinned process-isolated evaluator for four official-engine steps
in both candidate seats. The workflow also runs canonical
`build_integrated.py --check` and a clean-tree proof.

## Evidence boundary

This branch proves source closure, the execution-custody contract, static route
exposure, and first-action executability. It does not claim a score gain,
promotion, release, provider action, Kaggle upload, or leaderboard strength.
A matched full-game panel is required after candidate-action activation is
observed.
