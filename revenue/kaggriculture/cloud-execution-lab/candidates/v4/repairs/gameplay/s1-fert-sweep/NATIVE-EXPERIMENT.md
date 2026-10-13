# S1 native experiment: built, executed, inert on the checked archive

**Disposition: `INERT_ON_CHECKED_ARCHIVE / OFF`. This is executable research in the existing S1 repair package, not a production adapter or a final-V4 promotion.** No production source, configuration, archive, workflow, or Kaggle submission changes. The original `MANIFEST.json` and donor bytes remain authoritative and untouched.

## What was built

`native_s1_experiment.py` ports the S1 fertilizer-sweep admission family to an offline adapter around the actual native `main.py::agent`. It adds one late-day HIRE only after conservative admission, hides that extra hand from the parent, and remaps the complete returned hand vector. It does not install the retired R04 materializer or create another gameplay controller in production. Literal OFF returns the exact supplied parent callable.

The experiment holds its own per-game/per-seat worker state outside the native agent instance. Native reconstruction therefore does not itself erase the experiment's ownership. A pending HIRE is not a filled HIRE: next-step hand count, inventory count, and `hires_today` must all agree. Duplicate, cross-seat, or nonconsecutive calls during custody are rejected rather than silently reinterpreted as a new actor. This adapter is for a synchronous driver that sends its exact final returned action directly to the interpreter; downstream action rewriting requires an additional actual-return commit hook and is not certified here.

Actor remapping preserves short, omitted, invalid, and surplus raw hand rows. It pads missing parent slots before inserting the sweep hand, retains all ghost PLANT demands, and never inserts a PLANT itself. The hidden observation is detached from the real input. A native parent that dynamically returns any COLLECT_FERTILIZER keeps priority: the sweep hand passes that callback. Collection-request telemetry is explicitly not physical fertilizer or sale credit.

The original timing, territory, quoted-value, Fibonacci hiring, future cash-spend/WHEAT-pickup, and current headroom screens are retained. The port requires complete same-day future coverage and checks all possible native tapes. Its runner separately audits the selected tape alone so this additional conservatism cannot silently explain an inert result. It uses an explicit cash reserve, default 100; a composition requiring the legacy F2 covenant must supply 1000. There is no import of old router globals.

## Exact sources and scope

The existing manifest selects canonical donor `f14e18e67b5c0b95943f3c9b9db649d3327d5eb4` at `c8bb1b30047c2827f51931c55c1ceebdfe42979b`, PR #12630. The closed PR's later visible head is `6b7a9813a00ef9321405d7388b5a4228f31d0c4a`, with source `8003f06e696a940a7e02eecc862c2d26f43fad12`. These are different sources. In particular, f14e accepts a truncated future day; the later 8003 guard requires full-day coverage. This is an independent semantic native experiment, not an assertion of byte-equivalence to either donor, and the historical donor test counts are not reused as execution evidence.

Executed native fixture: artifact `10175943272`, ZIP SHA256 `3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8`; checked archive `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`. The source manifest SHA256 is `e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2`; every one of its 109 runtime members is authenticated before import on each native run. The unmodified full official engine is pinned at `3c202c7ee921da239356789e266b694635103fc4`, JSON `b354d06b742fe48402513792253f1a5c29366b20`, utils `91c8822ee6201ba4a5a8416c7dbe34f95dd61c87`.

This checked release is NOT the newer composed V4 scratch tree. Its own native defaults, including idle fertilizer and crop release, remain unchanged. No current-head, final-composition, Python 3.11, hosted-runtime, competitive-opponent, or gauntlet claim is made.

## Executed results

**Component acceptance: 28/28 normal and 28/28 `-O`, zero errors/skips.** Each control run makes 653 full-interpreter invocations, including initialization. The raw actor matrix includes 200 worlds across both seats, with 400 completed paired transitions preserving the normalized own observation, including global raw PLANT demand. Further cases execute real HIRE admission/failure, collected cargo, end-of-day deposit/reset, animal fertilizer refresh, and saturated-shed discard. The full-day positive controls demonstrate the branch works with a constructed parent; they are NOT natural native engagement or profit evidence.

**Fault discrimination: ten deliberately broken variants are assertion-rejected in each mode.** Every mode first reruns the complete unchanged control. Import errors, skipped tests, or other infrastructure failures do not count as killed mutations. Covered defects: truncated future evidence, ignored alternate routes, cardinality-only hire claims, short-vector shift, ghost-row truncation, wrong private inventory index, headroom bypass, stealing a dynamic parent's fertilizer, request-as-fill credit, and SE worker-territory entry.

**Native execution: 16 complete games, 11,504 actual native calls.** This is four distinct seed/seat cells (seeds 17 and 9922999, both seats), OFF/ON, repeated under normal and optimized Python. Each game completes 719 calls with no observed fallback. OFF and ON have identical complete raw-action hashes, full-state trajectory hashes, final money, and statuses in every pair; normal and optimized trajectories also match. The sole rival is the pinned official starter. This is NOT sixteen independent field cells, a competitive field gate, or Riot's hardened panel.

S1 admits **zero** hires in every native ON game. Selected-tape and all-tape audits give the same per-game first-rejection partition:

| Rejection | Callbacks |
|---|---:|
| Outside days 4–23 / hours 14–22 | 539 |
| Current native fertilizer collection | 77 |
| Future authored fertilizer collection | 78 |
| Current market/schema exclusion | 12 |
| Future market/schema exclusion | 4 |
| No eligible animal targets | 7 |
| Worst-spawn reachability | 2 |
| **Total** | **719** |

Thus 155 of the 180 phase-eligible callbacks are already excluded by current/future collection. None of the remaining 25 pass. Requiring every tape, rather than just the selected tape, adds **zero** rejections in this measured panel. There is no measured cash delta to promote: all four unique OFF/ON cell deltas are zero. This is an inert lane on this fixture, not a universal proof that surplus fertilizer collection has no value.

A useful structural boundary: at hour 22 only one post-hire callback remains. The SE spawn `(5,5)` is outside S1's territory, so even an adjacent permitted animal requires a move plus a collection. The worst-spawn guarantee cannot admit at that hour. Do not treat an hour-22 flag as an executable collection opportunity.

## Reproduction

Extract the exact b567 archive into a fresh directory; it contains `SOURCE.json` and all bundled engine/loader dependencies. Do not apply the old R04 materializer. From this package:

```sh
export S1_RUNTIME=/absolute/path/to/extracted-b567
python test_native_s1_experiment.py
python -O test_native_s1_experiment.py
python check_native_s1_mutants.py --out mutations.json

# Separate processes preserve native module/session isolation.
for seed in 17 9922999; do
  for seat in 0 1; do
    python run_native_experiment.py --runtime "$S1_RUNTIME" --seed "$seed" --seat "$seat" --out "off-$seed-$seat.json"
    python run_native_experiment.py --runtime "$S1_RUNTIME" --seed "$seed" --seat "$seat" --enabled --out "on-$seed-$seat.json"
    python -O run_native_experiment.py --runtime "$S1_RUNTIME" --seed "$seed" --seat "$seat" --out "off-$seed-$seat-O.json"
    python -O run_native_experiment.py --runtime "$S1_RUNTIME" --seed "$seed" --seat "$seat" --enabled --out "on-$seed-$seat-O.json"
  done
done
```

The runner never trims surplus rows, changes the 719-call termination rule, loads private rival data, or substitutes a mock native parent. Results retain separate raw-action/state hashes, completion status, both admission censuses, and daily observations. `NATIVE-EXPERIMENT-VALIDATION.json` contains input/code identities, the executed control/mutation summary and the four cells' shared OFF/ON/normal/optimized receipts. Timing samples are descriptive local measurements, not production deadline certification.

## Integration disposition

Keep the production key absent/OFF. Consume these actor-custody tests and the native inactivity census instead of commissioning another S1 donor port. Do not splice this wrapper outside the production deadline and call it released: its extra work is outside native `main.agent`'s own timer, and downstream final-action rewrites are not bound by its pending state. Native behavior with a naturally owned S1 worker, final-return/deadline composition, and Riot's newly required real-opponent gauntlet remain unmeasured. No gauntlet table was fabricated, and no runtime activation is requested.

This source/experiment task is complete; it is not an orphaned builder claim or a new generic build demand. The existing S1 package is the only home. The existing native assembler and Riot's separate fertilizer-liquidation/hire-cadence builders retain their work.
