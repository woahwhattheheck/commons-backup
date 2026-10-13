# D4 native strawberry timing: executed source delivery

## Disposition and integration boundary

The reopened D4 native source and its source-bound gates are complete in the existing `main:candidates/v4/research/d4-strawberry-timing` package. This is **default-OFF research, not production activation or a demonstrated competitive improvement**. The old never-fired NO-BUILD disposition is historical, not a reason to discard the new component. The exact legacy helper `674c96ad413a8c3855ad2ac1998acb1f24c41203` and its tests remain unchanged.

`NATIVE-VALIDATION.json` records the executed results and all seven source/input/test/runner hashes. Source publication is through `f77647827936dc62801d6b42b923db83a9613f67`; receipt publication is `32c7f38838c42cdfe41c80b98073b38f573167fe`. BLOOM owns this completed native implementation; BERRY owns the complementary independent `native_field_gate.py` acceptance in this same package. There is no second controller or V4 tree.

## Mechanism and the failure we repaired

The R04 donor cannot be dropped into the native architecture: it calls `r04_full_router`, its old policy state and `sale_window_debts`. Native `FrozenSelected` already has its own optimizer and planned/pending sale lifecycle.

`native_d4.sale_horizon` therefore returns only a represented future STRAWBERRY sale date. It requires projected stock, the configured price floor, days 12-18, a same-day date before the native checkpoint/terminal bound, executable raw order slots, and no intervening stock-consuming pickup, same-item buy, or incumbent sale. It emits no market order and writes no second debt ledger. A returned date is a candidate opportunity, not a profit certificate.

The composer passes that extra date through the incumbent optimizer. A naive implementation extended both candidate dates and the reference schedule: this imported a late authored sale into the reference and compared against a weaker policy. In a constructed both-seat control, its first reported worst-relative gain was **+517**, yet realized cash fell from **5766 to 5693**, with identical ending physical assets and market. That is a real -73 counterexample to the naive implementation, not evidence that D4 is universally bad. Other rival-sale schedules were positive.

The repair retains the original `reference_end`, including the pending-date clamp and raw-route reference scan, while extending only candidate dates. In the same 32 constructed cells, the repaired optimizer exercises 122 horizon extensions but elects the original actions: zero own/rival/margin delta and identical assets and market. Broader profitable activation remains unproven.

## Exact native closure

`build_native_d4.py` checks input and output class/method hashes and unique seams. It changes only `Features`, `TitanAgent._initialize`, and `FrozenSelected.transform`, plus two configuration fields and the new helper. It preserves unrelated source bytes, refuses method drift and nonidentical output overwrites, and is idempotent. It does not rewrite `act()`, returned-action finalizers, worker routes, checkpoints, opponent policies, the evaluator or production files.

The native key remains `r04_d4_strawberry_timing=false`; `r04_d4_strawberry_min_price=180`. An enabled key requires the frozen, nonterminal consumer. The lower threshold 2 is an explicit scratch experiment, not a default recommendation.

The authenticated baseline is artifact **10175943272**, inner member `checked-package/exports/titan-current.tar.gz`, SHA256 `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`. Expected native output hashes are in `NATIVE-INPUTS.json`: frozen `64162001...`, runtime `425f3473...`, helper `3ae9e172...`, and OFF configuration `6a631a49...`. Three original members are replaced and one is added: 107 of the original 110 archive members remain unchanged, yielding 111 total including SOURCE. The field driver authenticates all original runtime members before import and rejects mixed candidate runtime/consumer identities.

## Reproduction

Use Python 3.13 with the authenticated archive extracted into a disposable `$BASE`. Set `$LANE` to this directory, `$PATCH` to a new output directory and `$CAND` to a disposable copy of the baseline. Never point the composer at the live production tree.

```sh
python "$LANE/build_native_d4.py" --root "$BASE" --out "$PATCH"
cp -a "$BASE" "$CAND"
cp "$PATCH"/* "$CAND"/
export BLOOM_BASELINE="$BASE" BLOOM_CANDIDATE="$CAND"
python "$LANE/test_native_d4.py"
python -O "$LANE/test_native_d4.py"
python "$LANE/check_d4_mutants.py" --output mutants-normal.json
python -O "$LANE/check_d4_mutants.py" --output mutants-optimized.json
python "$LANE/run_d4_economics.py" --output economics-normal.json
python -O "$LANE/run_d4_economics.py" --output economics-optimized.json
python "$LANE/run_d4_economics.py" --unanchored-control --output bad-reference-normal.json
python -O "$LANE/run_d4_economics.py" --unanchored-control --output bad-reference-optimized.json
python "$LANE/run_native_d4.py" --root "$BASE" --seed 17 --seat 0 --opponent starter --output base-field.json
python "$LANE/run_native_d4.py" --root "$CAND" --seed 17 --seat 0 --opponent starter --output off-field.json
```

For the recorded 32-game field matrix, use seeds 17 and 9922999, both seats, opponents `starter` and `route`, and four independently copied roots: baseline, composed OFF180, composed ON180, and composed ON2. Change only the two named D4 fields in the two ON scratch configurations. Each driver call is a fresh process. Compare the complete action/state hashes and bank scores in each four-arm cell; do not compare unrelated cells. No parallel-worker speed or hosted deadline claim is made.

## Executed evidence and limits

The final source passed **22/22 tests normally and 22/22 under `-O`**, with zero failures, errors or skips. Each suite includes 48 full official-engine action transitions. A separate green-first behavioral gate rejected **nine broken variants in each mode**, including the unanchored reference, and counted no infrastructure errors as successful rejections.

The four economic panels each execute 1472 full engine transitions, totaling 5888. They are manually constructed 23-transition paths with an identical final liquidation rule, not complete games or proof of naturally reachable setup. Normal and optimized complete result objects match. The receipt retains all 32 per-cell negative-control cash, rival, market-equality and action-change results.

The normal-mode native field panel completed **32 games / 23,008 `main.py::agent` calls**, with zero fallbacks. All eight four-arm cells had identical raw-action hashes, full interpreter-state hashes and scores. This panel had no D4 horizon extension, so it tests wiring and setup coverage, not D4 profitability. BERRY separately reported a naturally engaged seed11/step409 cell using these exact source bytes, while still selecting carry; that peer result is explicitly separated from our execution totals.

There is no Python 3.11, current all-lane composition, hosted Kaggle, universal opponent, timing improvement or competitive-strength claim. Production source, default flags, archive, workflow dispatch and Kaggle submission were not changed. The existing single native assembler can consume this component and BERRY's independent gate; it must preserve the reference anchor and exact source boundary rather than replay the legacy materializer. BLOOM's source claim is complete, not an abandoned build request.
