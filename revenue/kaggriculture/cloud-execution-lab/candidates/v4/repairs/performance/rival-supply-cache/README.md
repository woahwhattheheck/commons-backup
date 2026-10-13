# Transform-local public rival-supply cache

Status: **built, executed, and stored in the one canonical V4 workspace; not activated in the production runtime or archive.** Owner: ASTRA-OBSERVE-PERF. Source publication commits: `ce7db73d`, `6667f1e3`, `8ddbbfaa`; receipt commit `816f2acf`.

## What changes

The current `FrozenSelected.transform` repeatedly asks the same public `rival_supply` question while evaluating sale products and attempting same-turn acquisition funding. The candidate reuses a lazy, bounded, per-transform lookup. It does not infer hidden rival stock, change economic scenarios, alter sale quantities, or change acceptance rules.

The cache is constructed after `observe()` and is not stored on the consumer, in its checkpoint, or in process-global observation state. A new transform gets a new cache. Zero values cache normally; exceptions and unused products are not eagerly evaluated. The exact native class and four inherited method identities must match; subclasses or replaced methods keep their original dynamic calls.

This is separate from the active MEADOW receipt arithmetic, EVENTPATH/CALENDAR traversal, SIEVE pruning, PRESSURE-PERF batching, PRISM scalar pricing, and fast-clone components. It adds no controller, feature key, release branch, or second V4.

## Exact input and output

The scripts verify all **109 runtime-map files** from source manifest `e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2`. Input archive SHA256 is `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`, recoverable from existing GitHub artifact **10175943272**, run **34537404363**. The artifact ZIP SHA256 is `3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8`; the archive is inside `checked-package/exports/titan-current.tar.gz`.

`rival_supply_cache.py` accepts only FrozenSelected blob `fc7baf5c179818a55037f6a61d92984d81d1a21c` / SHA256 `5ca1bc39efed756de71207f46926744ea69f9d2f300dd7b9c1a8cc4dbefeb9ef`. It emits a self-contained module, 38,608 bytes, with computed Git blob `2cea26a3affe9814357920b42db58cea93d9ac3a` and SHA256 `12d317e401bc7bc74cf783c450fe72fa61317c4b993f2b30fc9e6688091d3d6d`. That postimage is generated, not installed as a production source file or promised as a stored Git object.

The transformer refuses unknown source and refuses to overwrite any existing output. Do not weaken those guards to consume a changed runtime. Compose the small semantic delta explicitly with newer peer repairs and repeat acceptance on the composed bytes. If the assembled consumer becomes a subclass or replaces a guarded method, this optimization deliberately bypasses; measure engagement rather than assuming a speedup.

## Executed evidence

See `RECEIPT.json` for source identities and results, and `TIMING-SAMPLES.json` for the unfiltered timing samples.

* **24/24 tests in normal Python and 24/24 under `-O`**, Python 3.13.5. Each mode covers 116 native comparison cases, including 24 paired official-interpreter transitions. Actions, complete seller diagnostics, pending/planned state, public history, input objects, and controller routes are compared. End-of-day, terminal, both seats, stock floors, all product types, alternative economic rules, custom market parameters, lifecycle changes, overrides, and source/output guards are covered.
* **Five broken variants rejected in both modes**, each with at least one behavioral assertion failure: no cache, stale cross-transform cache, caching overrides, eager all-product evaluation, and a wrong product key.
* Valid 25-tile funding fixtures reduce public scans **29 to 3** and **41 to 3**. Twenty-one alternating unprofiled observations per arm/case measured **1.040–1.060x** median wall speed on three funding fixtures. Non-funding fixtures range **0.985–1.001x**; small regressions are explicitly retained. This is not a universal or whole-game speedup claim.
* Native default `main.py::agent` with the full pinned official interpreter, seed **9922999**, against **official_starter**, both physical seats: control and candidate each finish 719 callbacks per seat, **2,876 total**, zero fallbacks, identical full own-and-rival action traces, and equal final banks. The common trace SHA256 is `92be34952363255fc3a8f9d9a0f6a02dd046382d7f46bb63ecaf3510b618b65f`. This is one-seed integration smoke, not playing-strength evidence.

The 24 engine pairs are included in the 116 native cases, not an additional 24 independent cases. Early separate 100-tile stress witnesses had 81/85/86-to-3 scan counts; they are not the valid 25-tile timing fixtures above.

## Reproduce offline

Run from this component directory. `RUNTIME` must point to the unpacked exact b567 archive, not the moving repository root. The scripts read that input and write only the explicit result paths; the transformer needs an absent output path.

```sh
RUNTIME=/absolute/path/to/unpacked-b567
OUT=/absolute/path/to/new-results
mkdir -p "$OUT"
python rival_supply_cache.py "$RUNTIME/frozen_selected.py" "$OUT/frozen_selected.py"
python validate_rival_supply_cache.py --runtime-root "$RUNTIME" --output "$OUT/normal.json"
python -O validate_rival_supply_cache.py --runtime-root "$RUNTIME" --output "$OUT/optimized.json"
python exercise_rival_supply_cache.py --runtime-root "$RUNTIME" --mode negative-controls --output "$OUT/mutations-normal.json"
python -O exercise_rival_supply_cache.py --runtime-root "$RUNTIME" --mode negative-controls --output "$OUT/mutations-optimized.json"
python exercise_rival_supply_cache.py --runtime-root "$RUNTIME" --mode benchmark --repetitions 21 --output "$OUT/timing.json"
for seat in 0 1; do
  for arm in control candidate; do
    python exercise_rival_supply_cache.py --runtime-root "$RUNTIME" --mode episode --variant "$arm" --seat "$seat" --seed 9922999 --output "$OUT/episode-$arm-$seat.json"
  done
done
```

Episode mode injects only the exact generated FrozenSelected module for the candidate. It executes the unchanged package entrypoint, default feature config, official interpreter, and opponent. Compare `trace` and `bank` for each matched pair; wall times naturally differ. A nonzero fallback or divergent trace is evidence to inspect, not a pass to hide. No hosted Kaggle service or paid compute is needed for this reproduction.
