# PORTAGE: native transfer and placement performance

One component of `main:revenue/kaggriculture/cloud-execution-lab/candidates/v4`, not another agent or release line. Source/test claim is complete when this packet is on main. Production sources, defaults, archive and Kaggle submission are not changed by this packet.

## Implementation and composition

`compose_portage.py` rewrites only `_is_shed_adjacent`, `_spawn_hand` and `_drop_inventories_to_shed` in a NEW mechanics file. It authenticates each original function and the `_shed_access_tiles` dependency, accepts exact partial/postimages, and rejects drift, duplicate/decorated/rebound definitions and existing output files. UTF-8 byte offsets preserve every byte outside the three spans. No import or persistent cache is added to the runtime.

The integer-grid adjacency path avoids constructing four tuples, a list and a set. Other input types retain the original tuple/set evaluation. Spawn selection uses minimum occupancy with the dictionary's original NWSE insertion-order tie break for integer boards; other board types retain the original sort. End-of-day transfer uses `sum(shed.values())` only for exact builtin dictionaries, retaining the original generator for subclasses. It deliberately recomputes capacity for each transfer: no stale running sum, reordered workers/goods, retained overflow or changed seed accounting. Arbitrary runtime monkeypatching of the private geometry helper is not an extension contract.

Pricing (PRISM), joint PLANT admission (UNITFLOW), scheduler-prefix semantics (RIDGE), optimizers and runtime finalizers are outside these spans. The composer can preserve their disjoint edits; this packet does NOT certify an unexecuted combined stack. WEAVE's existing combined/native integration owner remains authoritative. Do not overwrite a peer's full module with the historical generated postimage.

## Exact execution

Baseline mechanics Git blob: `044a4f9c0a4a44dde10ada57563238bcaf82075d`. Composed blob: `64818e396f07ed99a597264c1b074ce1d4d35ab6`; SHA256 `c1077c274441bc0d832ac88c707a9587181da0a153ee59b26a3879dbde738326`.

Python 3.13.5: 12/12 normal and 12/12 `-O`. EACH mode executes 648 integer geometry cells, 486 spawn cells, 640 ordered transfer cases, 180 full official-interpreter differential pairs (360 interpreter calls), 40 actual native `post_units` cases and 24 actual native receipt-profile/optimizer cases. Complete state, insertion order, aliases, generic input failures, fallback behavior, source preservation and CLI refusal are checked. All seven deliberately broken variants fail behavioral assertions in BOTH modes with zero infrastructure errors. The interpreter comparison uses the unmodified pinned engine against another complete engine instance with ONLY the three composed function bodies installed; no replacement transition simulator is used.

Additionally, four existing suites pass unchanged in BOTH baseline and composed full-package copies, in normal and `-O`: operating stock 31, feed stock 24, crop release 22, funded prefix 8; 85/85 per arm/mode. These are selected regressions, not repository-wide CI.

Seven alternating paired local batches gave median time reductions of 43.3% for adjacency, 42.5% for spawning, 53.5% for dense end-of-day transfer, 13.3% for one-product transfer, 10.5% for actual `post_units`, and 19.8% for actual `receipt_profile`. Empty transfer was 11.58 vs 11.50 ms: no meaningful improvement claimed. Native timing fixtures use the actual caller functions with constructed observations and a controlled route, not a natural game. Raw samples, iteration counts and source identities are in `VALIDATION.json`.

NOT RUN / NOT CLAIMED: full-game policy strength, hosted Kaggle speed, deadline hit-rate, Python 3.11, full combined-peer stack, repository-wide CI or production enablement. No benchmark-derived feature/default flip is requested.

## Reproduce offline

Recover existing workflow artifact `10175943272` (ZIP SHA256 `3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8`). `ROOT` below is its `final-pressure-runtime` directory. The exact b567 archive and all 109 runtime-manifest members were authenticated for this execution. Engine dependencies are present under `checks/reference`; the gate refuses missing/mismatched official sources rather than fetching replacements.

```sh
python compose_portage.py "$ROOT/mechanics.py" /tmp/portage-new-mechanics.py
python check_portage.py --runtime-root "$ROOT" --receipt /tmp/portage-normal.json
python -O check_portage.py --runtime-root "$ROOT" --receipt /tmp/portage-optimized.json
python run_portage.py --runtime-root "$ROOT" --mode controls --receipt /tmp/portage-controls.json
python -O run_portage.py --runtime-root "$ROOT" --mode controls --receipt /tmp/portage-controls-O.json
python run_portage.py --runtime-root "$ROOT" --mode benchmark --receipt /tmp/portage-benchmark.json
```

For selected existing regressions, make a separate scratch COPY of ROOT, write `compose(original_bytes)` to that copy's mechanics.py, and in EACH root run the following in both normal Python and `python -O`:

```sh
for test in test_operating_stock.py test_feed_stock.py test_crop_release.py test_funded_prefix.py; do
  python -m unittest discover -s checks -p "$test" || exit 1
done
```

For a reviewed disjoint composition, keep the pinned baseline root and pass the resulting whole mechanics file using `check_portage.py --candidate PATH --runtime-root "$ROOT"`; then execute all other owners' combined gates. The function composer does not itself activate a runtime or change an archive. All source stays in this single canonical performance package.
