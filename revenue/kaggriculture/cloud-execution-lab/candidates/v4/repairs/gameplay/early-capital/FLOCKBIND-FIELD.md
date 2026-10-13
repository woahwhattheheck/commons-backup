# FLOCKBIND field gate — widened b567 falsifier

This packet extends the **existing** `repairs/gameplay/early-capital/` FLOCKBIND family. It does not add another controller, feature key, evaluator, runtime, default, archive, or Kaggle path.

## Result

The source-bound FLOCKBIND mechanism naturally engages on authenticated artifact `10175943272` / inner b567 package `b567942e...` against the official starter. Every one of four seeds engages in both seats at step 216, replaces the deferred WHEAT row with one SHEEP while preserving the current full market cardinality, and fulfills the exact WHEAT×4 obligation on the authenticated parent-empty callback at step 227 before the step-228 WHEAT plant. All eight games complete 719 interpreter steps with no reported failure.

The widened economics **falsify activation**:

| Seed | Own delta | Margin delta | Seats |
| ---: | ---: | ---: | :--- |
| 17 | +25,744 | +25,834 | 0, 1 mirror-exact |
| 101 | +4,995 | +5,163 | 0, 1 mirror-exact |
| 6607 | **-6,825** | **-6,553** | 0, 1 mirror-exact |
| 9,922,999 | **-9,407** | **-9,471** | 0, 1 mirror-exact |

Across the eight paired cells the mean own delta is +3,626.75 and mean margin delta is +3,743.25, but that positive average is not promotion evidence: four cells are negative and the seed sign flips are large. The correct disposition is `HOLD_NEGATIVE_CELLS` / default OFF.

`FLOCKBIND-FIELD-B567.json` is the machine-readable receipt. `flockbind_field_gate.py` validates exact source identities, all four seeds × both seats, score/delta arithmetic, 719-step completion, one rebind at step 216, one WHEAT×4 fulfillment at step 227, and starter-seat mirror orientation. Any missing/duplicate cell, source drift, failure, score inconsistency, or unfulfilled obligation is `INVALID`. Even an all-nonnegative panel returns only `ALL_CELLS_NONNEGATIVE` with `activation_authority=false`; stronger-opponent and live-runtime gates remain separate.

## Current-main custody boundary

This is deliberately labeled **historical b567 fixture evidence**, not current-live-main evidence. Its native runtime Git blob is `b952c9c228ecbde592bf3d2df01638677abb0d24`. Live main subsequently advanced through the REBIND runtime transition, so the active one-package current-native refresh must be consumed before making a new live verdict. Do not weaken the helper/source pins or call this b567 receipt current merely because its engine and Arlene identities still match.

The field gate is reusable: a refreshed panel must carry its own exact source identity and should be validated against an explicit expected-source map; this packet intentionally does not silently accept a different runtime as equivalent.

## Falsified shortcuts

Exploratory follow-up on the same authenticated b567 fixture found no safe simple promotion shortcut. Public shop/Strawberry heuristics still admitted large losing cells, and pulling one route-authored FERTILIZER sale forward to pre-fund step 216 changed outcomes non-monotonically, including flipping the strong seed-17 win negative. Those probes are not policy bytes and are not included as an admission rule. They are a warning against overfitting the original seed-17/101 recovered wins.

## Focused validation

From this directory:

```sh
python -B -m unittest -v test_flockbind_field_gate.py
python -O -B -m unittest -v test_flockbind_field_gate.py
python -m py_compile flockbind_field_gate.py test_flockbind_field_gate.py
python -B flockbind_field_gate.py FLOCKBIND-FIELD-B567.json --pretty
```

A new exact-current package should rerun full games first, then feed the resulting complete paired receipt into this fail-closed evidence boundary. No activation is authorized by this packet.
