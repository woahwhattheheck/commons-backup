# S8 reopened: one source, explicit economics

This is a source-only repair in the existing canonical `main:candidates/v4` S8
family. It does not change native runtime, configuration, production archive or
Kaggle submissions. `enabled=False` and the existing `r04_s8_egg_care` key remain.
The original `s8_egg_care.py` (blob `30a0e05c0cd7a435a59316d9d070da59eb2bb865`)
and original legacy tests are preserved unchanged. Do not run the legacy R04
materializer against the current native ABI.

## Exact consumption

`compose_reopened_s8.py` (blob `7cc261b907e377961e204c47d594cf3cfc85663c`)
accepts only those exact donor bytes. `compose(bytes) -> bytes` generates a
standalone module with blob `8591f8208b35a7ffc6547385ca72244f423a44a2`, SHA256
`86be29534c8cfedef7d0b13043ec86586632b40eac2b16084dd1a9b6ac06d213`.

```python
apply_egg_care(observation, parent_action, configuration=None,
               *, enabled=False, price_mode="spread_or_discard")
```

Disabled and unmatched calls retain the parent object by identity. Changed calls
copy the action and rewrite only qualifying hour-23 `COLLECT_FERTILIZER` rows.
The original fed/uncared, pending-bonus, maturity, held-cap, last-day, worker
collision and HARVEST-priority guards remain. No orders, hires, movement or stock
are added. Source-only mode selection is not a new production config key.

The four experimental modes are `donor`, `spread`, `discard`, and
`spread_or_discard`. Donor mode preserves the original action decision; telemetry
now classifies structural opportunities before economic rejection. Spread mode
uses EGG > FERTILIZER instead of the former +20 and 1.2 ratio. It still requires
the four-unit fertilizer buffer. This is a quote heuristic, NOT a future-profit
certificate.

Discard mode additionally permits low quotes/no buffer only when
`discarded_fertilizer(observation, action, configuration)` proves the shed remains
full until inventory disposal. All unit rows must be conservatively shed-neutral.
All requested SELL quantities in the **raw executable prefix** are subtracted,
even unfillable sales. BUY does not invent occupancy; unknown/removing unit or
live market rows fail closed. Dead suffixes do not veto or shift live slots.
This proves zero lost first-EOD retained fertilizer, not future egg proceeds.

## Composition boundary

The single native assembler must invoke the helper **after existing HARVEST
rescue and before final returned-action receipts**, with the final market prefix
visible, inside the normal deadline. Do not append it after `main.py::agent`
returns: that bypasses internal action/stock receipts. This source package does
not certify such a native binding. HENHOUSE owns independent native/legal-setup
field evidence; GOOSE owns independent complete-engine lifecycle acceptance on
this same source. Reuse their files in this directory; do not create siblings.

Prefer **discard-only** for the next separate native gate. Do not silently enable
the combined/spread mode or infer field value from a constructed control.

## Executed acceptance

From this directory, with an unpacked artifact10175943272 checked package:

```sh
S8_NATIVE_ROOT=/path/to/unpacked-b567 python test_reopened_s8.py
S8_NATIVE_ROOT=/path/to/unpacked-b567 python -O test_reopened_s8.py
python run_reopened_controls.py --native-root /path/to/unpacked-b567 --output /tmp/s8-full-report.json
python compose_reopened_s8.py --output /tmp/reopened_s8.py
```

The output path for composition must not already exist. No command fetches engine
inputs; missing/changed engine, JSON, upstream utility or loader fails before
import. Exact expected inputs and all source hashes are in
`REOPENED-VALIDATION.json`.

GOSLING executed 30/30 tests in normal and optimized Python3.13.5, zero
failures/errors/skips. Each baseline mode performed 309 full-interpreter
initializations plus 548 action transitions (857 calls, **not games**), including
160 donor-action controls, 80 randomized first-EOD state comparisons, and 16
additional market/multi-worker state comparisons. Twelve deliberately broken
helpers failed behavioral assertions in each mode; none received error-only
credit. Four missing plus four changed reference inputs were refused per mode.
The runner reproduces full logs; the committed receipt is the compact summary.

Both-seat constructed continuations produced these identical cash differences:
full-shed discarded fertilizer + next-day feeding **+50**; mild 115/100 quoted
spread + feeding **+16**; discarded fertilizer without next-day feeding **0**;
spread without next-day feeding **-99**. Real HARVEST/DROP/SELL is executed in
those continuations. Initial goose/stock/quote states are constructed cuts, not
legal-from-initializer native policy trajectories. Future clipping, inventory
admission, feeding, sales, opponent effects and final-stack economics still
require separate acceptance.

The unchanged checked-native seed17 seat0 census completed719 callbacks versus
the official starter (105846/3741 cash) with no workers on GOOSE at any of29
hour-23 checkpoints. This is missing activation opportunity, **not a kill**.
All110 archive file members were byte-checked against b567; this is not a claim
of110 agent modules or validation of a later composed main package.

Source construction and component acceptance are delivered. Native activation,
full-current-V4 competitive gain, hosted CI and Python3.11 are NOT certified by
this receipt. No further source-custody demand or alternate S8 controller is
needed.
