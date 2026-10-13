# Delivery-timed carrot experiment

This is an experimental extension of the existing selective-carrot family over
frozen V4 with completed-route recovery. It keeps the cap12 crop selection and
buys displaced feed at delivery time. A returned BUY order does not discharge
the replacement debt: the next observed shed increase settles only the filled
quantity. Existing authored wheat purchases and EOD defer the replacement so
the receipt remains distinguishable.

The candidate is not current-main's complete feature composition. No default,
release pointer, or Kaggle submission is changed. The owner submission hold
remains in force.

The default builder emits v2, normalizing the outer observation clock from
day/hour and configured turnsPerDay when step is absent or null. Both the
policy and receipt callback receive that same copied observation.

## Exact artifacts

Public release: `titan-kaggriculture-gauntlet-20260912` in
`woahwhattheheck/commons`.

| Asset | SHA256 |
|---|---|
|`titan-v4-route-recovery-delivery-carrot-v2.tar.gz`|`0d42ee5fabb089745fa0064207654bfdf5df9466ba6499d91b6e685d4880cab1`|
|Earlier v1 `titan-v4-route-recovery-delivery-carrot.tar.gz`|`4db8d176bd34b219eff62c65e584a0786889065a52467b68f79e01f24af8fb30`|
|`v4-runtime-repair-route-recovery.tar.gz`|`a44bf380cd79f967893ea90273be7dc92d6fd4f5e553aac0b02e457e85cf4ca8`|
|Existing `titan-v5-selective-carrot-cap12.tar.gz`|`5bf8e90602e145b353b9ff421fc514f2cf8af77ec549557e5e0acc1bc6bd67aa`|
|Existing exact submitted V4 `titan-v4-56182437-4d960155.tar.gz`|`4d9601552b5e25d02d8a33961c0bed54ed92d032dbcd4a72f6ab8e03515ed21b`|
|Existing exact submitted V3.1 `titan-v3.1-56172377-5db3921f.tar.gz`|`5db3921f85efbc7596e5a1e7e198fc5f4644ceea43d8e8323c74ded7b4ba4361`|

The route-recovery control differs from submitted V4 only in `main.py`. The
delivery candidate adds `delivery_choice.py`, updates the cap12 wrapper import
and constructor, and replaces its `baseline_main.py` with that recovery entry.
All remaining members are byte-identical to the exact inputs. The builder
checks input snapshots and the final archive hash before creating any output.

From this directory, with downloaded archives at the specified paths:

```bash
python -B test_delivery_receipts.py
python -O -B test_delivery_receipts.py
python -B build_delivery.py --cap12 /path/to/titan-v5-selective-carrot-cap12.tar.gz \
  --route-recovery /path/to/v4-runtime-repair-route-recovery.tar.gz \
  --out /new/path/delivery-payload --tar /new/path/delivery.tar.gz
```

The default archive exactly reproduces the tested 78-member v2 artifact.
Add `--version v1` to reproduce the unchanged earlier 4db8d176 archive. The builder uses
the old core inside the authenticated cap12 archive, so subsequent changes to
current-main `selective_carrot.py` do not silently change the frozen candidate.

## Observed strategy diagnostic

Six receipt tests cover partial fills, rejected purchases, fallback actions,
EOD deferral, authored wheat buys, and preceding sales. They pass normally and
under `python -O`.

The following strategy screen directly tested v1 (4db8d176). V2 has a
separate full-game absent-step seat1 callback bridge with all 719 actions
identical to v1; see `PRODUCTION-CALLBACK-BRIDGE.json`.

On exact Arlene, seat0, seed2051966578 the candidate margin is3620 versus V4's1940
(+1680), while V3.1 remains11746. Four fresh Arlene seat0 seeds1209125501–5504
give candidate-minus-V4 margins +2188,0,+1380,0, mean+892. Candidate-minus-V3.1
is +2591,-2008,-16829,-7718, mean-5991. Timing guards were disabled for these
719-decision strategy diagnoses. They establish neither native timing nor
hosted rating nor overall V3.1 superiority. Full reduced results and input
identities are in `DELIVERY-RESULTS.json`.

## Native fleet run using the existing evaluator

The leading production v2 candidate in `PRODUCTION-RECOVERY.md` takes the
next SPARK slot if no delivery process has started. Preserve any running
delivery cell/panel. Later unstarted standalone delivery arms use v2.
The following delivery comparison retains its existing exact controls.
Panel: seeds2051966578,1209125501,1209125502, both seats, responsive Apex_v7 and
Arlene_v14, delivery candidate / exact V4 / exact V3.1:36 total arm-games before
reuse. Reuse only completed controls with identical archive, opponent, engine,
seed, seat, agent RNG and timing limits. The route-recovery archive is an
available extra cancellation-control arm; do not relabel it as submitted V4.

Use the existing Linux checkout and pinned engine. `KG` is its existing
`revenue/kaggriculture` directory; `RUN` is a new output directory. Extract each
authenticated archive to `$RUN/delivery`, `$RUN/v4`, `$RUN/v31`. Reuse existing
opponent adapters from the completed native bridge, or prepare each with the
existing bank command:

```bash
python "$KG/cloud-execution-lab/candidates/v4/research/reference-policy-bank/reference_policies.py" \
  --key apex_v7 --kg-root "$KG" --out "$RUN/opponents/apex_v7"
python "$KG/cloud-execution-lab/candidates/v4/research/reference-policy-bank/reference_policies.py" \
  --key arlene_v14 --kg-root "$KG" --out "$RUN/opponents/arlene_v14"
python - "$KG" "$RUN" <<'PY'
import importlib.util
from pathlib import Path
import sys
kg, run = map(Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location('existing_pack', kg/'cloud-pack/pack.py')
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)
for arm in ('delivery', 'v4', 'v31'):
    pack.write_adapter(run/(arm+'-adapter.py'), (run/arm/'main.py').resolve())
PY
```

Run the unchanged evaluator separately for every missing arm. It automatically
runs both seats. Do not use old selective-carrot `paired.py`: it deliberately
accepts only its original wrapper and would reject this candidate.

```bash
python "$KG/cloud-execution-lab/reference/evaluator/evaluate.py" \
  --engine-dir "$ENGINE" --loader "$KG/20260907-offline-agent/evaluate.py" \
  --candidate "$RUN/delivery-adapter.py::agent" \
  --opponent "apex_v7=$RUN/opponents/apex_v7/adapter.py::agent" \
  --opponent "arlene_v14=$RUN/opponents/arlene_v14/adapter.py::agent" \
  --seeds 2051966578,1209125501,1209125502 --rng-seed 20260912 \
  --action-timeout 1.25 --startup-timeout 10 --game-timeout 900 \
  --output "$RUN/delivery-report.json"
```

For missing exact controls substitute `v4-adapter.py` or `v31-adapter.py` and
distinct output paths, restricting seeds/opponents to avoid completed work.
Post PID/workspace and archive IDs, then numerical results in `#sim-data`:
own/rival cash, paired margins, completed decisions, callback/fallback timing,
first action divergence and available carrot/replacement-wheat engagement.
Retain negative and failed cells. Native results remain pending at publication.
