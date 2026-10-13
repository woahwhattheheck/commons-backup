# Current-native scheduler action-prefix composition

This package now has one current-native successor to the historical scheduler-only
repair: `compose_current_native.py`. It is source-only and fail-closed. It does not
edit production files, add a feature key, change defaults, build an archive, or
submit to Kaggle.

## Why the historical six-consumer transform is not enough

The historical transform is still authoritative for its exact predecessor
`scheduler.py` blob `a483b24dd72b580d7d8811636b54d2d44f391575`, and its exact
postimage remains `742a200e9a72e303ad18c51c104895013a7f3a4b`. Current production,
however, executes the frozen path `main.py::agent -> TitanAgent -> FrozenSelected`.
`FrozenSelected` inherits scheduler forecasting helpers but also owns newer copied
queue accounting and projection helpers. Applying only the scheduler transform can
therefore leave capped raw suffix rows able to consume projected stock, retire
plans, create false service dates, or fund represented acquisitions even though the
official interpreter never parses those rows.

The current composer ports the same executable-prefix invariant after the reviewed
LOOM source stack. It accepts only these source identities:

- scheduler: SPINDLE postimage `b29d1e9887f517506c5b3d858baa9bda5848e73f`;
- frozen seller: LIVEPATH postimage `4a5d3d5f4bed04acf73c7339e41fed56badf34c9`,
  or that same source after current H3/S420, `712f7334288951bdc5b8dd2a1aa1d7f985cd50dc`.

Unknown or partially applied source refuses instead of rebasing itself.

## Owned accounting surface

The scheduler side reproduces the original six-consumer repair byte-for-byte when
run on the historical predecessor. The current frozen side additionally confines
raw-market accounting to the official executable prefix in:

- `materialize_sales`;
- `_funding_trace` and `fund_same_turn_acquisition`;
- `joint_resource_bound` and `joint_queue_ledger`;
- `event_aware_horizon`;
- `apply_represented_market` / `represented_shed_event`;
- `FrozenSelected.transform` baseline quantities, future references, capacity
  checks, and pending-plan retirement.

Raw suffix rows are preserved as authored. They simply cannot spend money, consume
shed stock, supply a receipt, occupy an executable SELL slot, or retire an intent
until they are inside `max(1, maxMarketOrdersPerTurn)`.

## Validation and custody

`test_compose_current_native.py` reconstructs the existing source lineage from the
actual landed composers: TOWNPATH -> UNITFLOW -> FUNDING-PERF -> CAPTRACE, then
SPINDLE + LIVEPATH, and finally the current H3/S420 source transform. It requires
exact intermediate Git blobs before applying this repair. It also proves the
historical scheduler port remains exactly equal to the existing transformer output
and includes negative witnesses where a capped suffix SELL would otherwise erase
stock/intent or create a false future service date.

Top-level `COMPOSITION.json` is intentionally unchanged here. The generic graph
runner remains the sole graph-to-postimage executor, and H3/S420/current field
ownership remains with its existing lane. Register this component only after the
preceding graph edge chosen for H3/S420 is explicit; do not insert this transform
before an owner whose authenticated preimage would then be broken.

No field-economics, default-promotion, release, or Kaggle claim is made by this
source component.
