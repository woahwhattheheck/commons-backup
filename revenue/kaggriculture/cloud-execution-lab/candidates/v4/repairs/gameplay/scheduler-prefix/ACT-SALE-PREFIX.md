# Nonterminal scheduler sale-prefix continuation

This extends the existing scheduler-prefix repair in the single canonical
`main:candidates/v4` workspace. It is not another V4 branch, feature key or
production release. Original donor bytes and the existing projection repair
remain unchanged.

## Defect and scope

The official market executes only the first
`max(1, maxMarketOrdersPerTurn)` raw list slots. Empty slots still count.
The old `SellScheduler.act` nevertheless counted suffix SELLs in current
baseline demand, future reference sales, available market-slot capacity and
pending-stock accounting. It also inspected and rewrote engine-inert suffix
orders. A suffix sale could therefore erase unsold pending stock or make an
unexecutable planned sale appear feasible.

`act_sale_prefix.py` closes those nonterminal consumers with six exact method
replacements. It preserves raw slot positions and opaque suffix values,
clamps the cap consistently for appended sales, and never debits pending stock
for an inert sale. The transformer preserves all other method bytes and refuses
unknown/partially patched `act` source. The CLI refuses in-place edits and
existing output files.

## Compose on the current foundation

Run from this directory. `TREE` is a verified materialized package with scheduler
blob `a483b24dd72b580d7d8811636b54d2d44f391575` and official engine blob
`3c202c7ee921da239356789e266b694635103fc4`. GitHub artifact `10169538667`
contains `checked-package/exports/titan-current.tar.gz`; expected archive SHA256
is `5f6a4153e502713b9467776eafe7464af650584149173ce7507a31a1b2af60f1`.

```sh
OUT=$(mktemp -d)
python materialize_scheduler_prefix.py "$TREE/scheduler.py" "$OUT/projection.py" \
  --engine "$TREE/checks/reference/engine/kaggriculture.py"
python act_sale_prefix.py --source "$OUT/projection.py" --output "$OUT/scheduler.py"
python test_act_sale_prefix.py --package-tree "$TREE" \
  --scheduler-source "$OUT/projection.py" --mutation-check
python -O test_act_sale_prefix.py --package-tree "$TREE" \
  --scheduler-source "$OUT/projection.py" --mutation-check
```

The existing projection materializer must run FIRST: it pins the whole input
scheduler. Its current output is `1da9934ec45f485a16244bcbc78af26d9109b97e`;
applying this continuation yields `9ae62209e956fee0f76b3dbe87dfef3eb6296731`.
No package is installed by these commands. Do not run the legacy whole-V4
materializer over the current production ABI.

## Executed evidence and limits

CPython 3.13.5: 21 tests pass in normal and optimized modes on the verified
artifact source, the exact older donor, and the current projection postimage.
Each source/mode runs 170 in-cap predecessor-parity cases and 648 official
market-phase cases covering both seats, raw slot caps -2/0/1/2/3/10, and ordinary
and floor-price inventory. Each of six individually reverted changes is rejected
by behavioral assertion failures, not merely by source-hash checks. Repeating
these cases across source variants is compatibility evidence, not additional
independent games.

The suite executes the actual `act` method and official `_process_market`.
It explicitly isolates the already-owned reserve/profile consumers and most
optimizer calls; one separate test executes the real optimizer. The external
seed-resolver import is replaced with a fail-on-use sentinel, not a full-game
simulation substitute. Exact hashes and run receipts are in
`ACT-SALE-PREFIX-RECEIPT.json`.

Terminal settlement, represented purchases/HIRE admission, shared builders,
checker gates, defaults and production archives are unchanged. This is source
and mechanism validation, NOT a full-match, economic-strength, release or
Kaggle-promotion claim. The remaining integration gate belongs to the existing
single V4 builder; do not create a sibling carrier.
