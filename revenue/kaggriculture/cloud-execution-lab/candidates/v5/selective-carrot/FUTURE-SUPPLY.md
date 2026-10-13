# Own future supply in sale valuation

This optional production-v3 experiment adds represented future own deliveries
to the current-lot sale price model. It keeps the existing production route,
all economic stage flags, the rival scenarios, funding checks, physical
capacity checks, and strict admission rule. It changes no live default or
Kaggle submission.

The seller already follows the chosen own tape within its bounded same-day
horizon to check shed capacity. This treatment uses that same bounded horizon
to identify newly deposited units consumed by later sell-all orders. It adds
their supply and own receipts to each candidate and reference price path.
Initial shed inventory remains the current lot and is counted once. Future
same-product purchases disable the added projection because their financing
needs a separate queue model. Partial sales do not imply a full new-lot sale;
projected PICKUP removes new stock first for conservative lot accounting.

This is conditional own-tape valuation. Dynamic production changes can depart
from that tape; the projection does not claim to forecast them or rival action.
The optimization objective remains own receipts plus carry value minus rival
receipts. All original scenarios still have to improve before a normal sale
plan is admitted.

## Reproduction

Baseline: exact import-safe production v3
`20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239`,
reproduced by the existing `build_production_recovery.py` from the release
inputs documented in `PRODUCTION-RECOVERY.md`.

Treatment: 93-member archive
`ca8ca6f5d1ffb5ad828db5d924ed27d4d3c2f35b3a54ebd1f4cb311d7cdea9e1`.
Only `frozen_selected.py` and `selected_sell_core.py` are modified, and
`future_own_supply.py` is added. The other 90 baseline members are byte-identical.
`FUTURE-SUPPLY-MANIFEST.json` records every resulting member hash.

```bash
python -B build_future_supply.py --baseline /path/to/production-v3.tar.gz \
  --out /new/path/future-supply --tar /new/path/future-supply.tar.gz
python -B test_future_supply.py --payload /new/path/future-supply \
  --loader "$KG/20260907-offline-agent/evaluate.py" --engine-dir "$ENGINE"
python -O -B test_future_supply.py --payload /new/path/future-supply \
  --loader "$KG/20260907-offline-agent/evaluate.py" --engine-dir "$ENGINE"
```

The portable builder authenticates the baseline, exact projection helper and
final archive before writing outputs. Seven tests pass normally and under
`-O`. They cover initial/new inventory separation, immutable observations,
PICKUP, partial sales, future purchases and day boundaries. Four controlled
market cases compare predicted receipts directly with the pinned official
interpreter for two sale plans in both seats.

## Observed strategy screen

All five cells below directly ran the final treatment in a fresh process
against a responsive opponent on the pinned official engine. Local timing
guards were disabled. Positive margin deltas measure a development result;
they establish neither native timing nor hosted rating.

| Opponent | Seed | Seat | Baseline margin | Treatment margin | Delta |
|---|---:|---:|---:|---:|---:|
| Arlene v14 | 2051966578 | 0 | 13784 | 13810 | +26 |
| Arlene v14 | 1209125501 | 0 | 5103 | 5109 | +6 |
| Arlene v14 | 1209129901 | 1 | 5820 | 5877 | +57 |
| Kaito v43 | 1209130051 | 1 | 31787 | 31791 | +4 |
| Igor multiroute | 1209130052 | 0 | 34255 | 34257 | +2 |

Mean delta is +19. All ten paired games completed 719 decisions. Kaito's own
cash is 2 lower while its rival earns 6 less; margin is the primary metric.
Full own/rival cash and action hashes are in `FUTURE-SUPPLY-RESULTS.json`.

On the known 2051966578 cell, future supply appears in 86 evaluation callbacks
and 29 chosen plans. The first action change is step365: sell8 MILK instead
of6. The chosen model includes three newly delivered MILK units sold at375.
The final own/rival changes are +16/-10. This is a small additive improvement;
keep larger production experiments ahead of it in fleet priority.

## Next native comparison

Use the existing generic evaluator and `pack.write_adapter`, as in
`PRODUCTION-RECOVERY.md`, with this payload's `main.py`. Compare with exact
production v3 using matching seed, seat, engine, opponent and timing settings.
Reuse existing controls where every identity matches. Preserve all active
games and the current route-choice matrix. Native timing remains pending;
no extra evaluator or review queue is needed. Kaggle submission remains held.
