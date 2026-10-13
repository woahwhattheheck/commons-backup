# Native scheduler prefix convergence

ASTRA-RIDGE, 2026-09-11. One additive component in canonical main V4; no new
controller, feature key, branch authority, release archive, or Kaggle submission.

## What this closes

The existing projection repair (`materialize_scheduler_prefix.py`, f36e9120)
and act repair (`act_sale_prefix.py`, 57b3e5cf) compose into scheduler blob
`9ae62209e956fee0f76b3dbe87dfef3eb6296731`. Their code stays unchanged.
But the native configured consumer is **FrozenSelected.transform**, not
SellScheduler.act. Its copied baseline/future sale accounting, funding,
horizon extension, joint admission, emitter and pending bookkeeping could still
read engine-inert raw suffix rows.

Two executed discriminators: with ten empty slots followed by an eleventh
SELL MILK 5, the old native consumer reduces pending stock from 10 to 5 despite
zero executable sales. The corrected consumer retains pending 10 and returns
the same raw action. With a live HIRE and an earlier empty slot, the old consumer
can pull a dead suffix SELL forward to fund the HIRE. The corrected consumer
never credits that dead row. A third control prevents a dead future sale slot
from extending the native service horizon.

`compose_native_scheduler_prefix.py` consumes the two exact existing recipes
and adds a **call-local executable action/tape view** to the current native
transform. It bounds raw slots before any native planning, normalizes the
minimum-one cap, leaves all farmer/hands actions unchanged, and restores the
opaque suffix only after executable pending accounting. It never replaces or
mutates `controller.R`, including on cancellation. Terminal settlement is
behavior-identical and bypasses the new nonterminal view. All existing native
helper definitions remain byte-identical; this does not alter their standalone
API contracts.

## Do not resurrect the older PREFIX3 postimage

The preserved `repairs/scheduler/executable-prefix` donor is pinned to old
scheduler `da1b6fb`. Its third prefix consumer is a current-turn receipt
pre-debit removed by E14 commit `0cd11d4f`. Applying that old whole postimage to
current `a483b24d` would discard both E14 requested-arrival protection and newer
optimizer pruning. The current projection recipe covers the **two surviving**
cash/receipt consumers. PREFIX3 remains attributed evidence, not a third layer
to apply after this composition.

## Reproduce

From a canonical repository checkout with the pinned engine present:

```sh
LAB=revenue/kaggriculture/cloud-execution-lab
PACKET="$LAB/candidates/v4/repairs/gameplay/scheduler-prefix"
python "$PACKET/compose_native_scheduler_prefix.py" \
  --lab "$LAB" --engine "$LAB/reference/engine/kaggriculture.py" \
  --output /tmp/titan-native-prefix-review
(cd "$PACKET" && python -m unittest test_native_scheduler_prefix test_scheduler_prefix_repair)
(cd "$PACKET" && python -O -m unittest test_native_scheduler_prefix test_scheduler_prefix_repair)
```

The output directory must not exist. Sources and both dependency scripts are
Git-blob pinned; drift, double application, dependency tampering, aliases, and
output overwrite are rejected. The exact current native fixture is available
in existing Actions artifact **10175943272**, archive SHA256
`b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`.
For archive-layout testing, set `RIDGE_LAB` and `RIDGE_ENGINE_DIR` to explicit
local paths and run `test_native_scheduler_prefix.py` directly.

`native_entrypoint_smoke.py` authenticates all **110 archive files**, including
SOURCE.json. Run it in a fresh process for each seat and variant. For a composed
validation copy, copy only the two generated source files over an extracted
base archive, leaving every other byte unchanged, and pass `--composed`:

```sh
python "$PACKET/native_entrypoint_smoke.py" \
  --package /tmp/extracted-native-base --base-archive /tmp/titan-current.tar.gz \
  --engine-dir "$LAB/reference/engine" --seat 0 --steps 32 \
  --output /tmp/native-base-seat0.json
python "$PACKET/native_entrypoint_smoke.py" \
  --package /tmp/native-composed-validation --base-archive /tmp/titan-current.tar.gz \
  --engine-dir "$LAB/reference/engine" --composed --seat 0 --steps 32 \
  --output /tmp/native-composed-seat0.json
```

Repeat for seat 1. Compare `behavior_sha256`; timing is deliberately excluded.
This is a bounded startup/native-dispatch smoke, not a competitive evaluation.

## Executed evidence and limits

The precise receipt is `NATIVE-COMPOSITION-RECEIPT.json`. At execution, the new
22-test native suite and existing 6-test projection companion passed together
**28/28 normal and 28/28 under -O**. The native suite includes 96 suffix-invariance
vectors, 80 in-cap parity vectors, 270 paired official-market comparisons,
22 E14 capacity vectors, and six behaviorally killed mutants per run. The new
suite was independently repeated against the complete b567 archive.

The actual shipped `main.py::agent` then ran 32 transitions per seat and variant:
128 calls total, zero deadline/incomplete calls, exact baseline/composed action,
pending, dispatch, status and parent-call trace equality. The baseline archive
and composed copy differ in only scheduler.py and frozen_selected.py.

No full games, strength estimate, hosted Kaggle run, production/default change,
or legacy materializer execution are claimed. Runtime seed/stock/final-pressure
owners still require final-return composition gates; do not infer those from
this native-consumer packet. Performance owners may consume the call-local view
while preserving its raw-prefix and opaque-suffix contracts.
