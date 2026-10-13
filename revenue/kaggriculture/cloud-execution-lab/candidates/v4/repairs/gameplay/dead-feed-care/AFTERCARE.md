# AFTERCARE: independent W2 lifecycle and economic acceptance

This is acceptance for the **one** `dead-feed-care` package, not another CARE policy, V4 tree, or native controller. SECONDHELP owns `dead_feed_care.py` and donor custody. SECONDCARE owns native pre-consumer wiring and census. AFTERCARE owns the independent full-interpreter oracle and the evidence below.

## What was actually established

The exact helper Git blob `51c17ea3245755673ffead8e86d4b04e7766c949` was consumed and authenticated. In the complete pinned official interpreter, both already-fed entry states and ordered same-turn FEED/FEED states can become one useful CARE. The latter opportunity is invisible to a census that only inspects `fed_today` at callback entry.

CARE is credited **after** the current end-of-day production. Its new bank therefore needs a later fed production boundary. The fixed positive continuations reach real HARVEST, DROP, successful SELL commits, and final rewards. They sell one extra unit without spending more WHEAT: +50 GOOSE, +169 COW, +209 SHEEP in-game cash, in both seats. These are controlled mechanism witnesses, not natural-game expected value.

The same executed helper also exposes a significant composition hazard. In the `collateral-drop` cases, a predeclared crop-service continuation harvests the same MELON crop in both arms. Extra animal cargo enters the finite shed first, displacing one later MELON. Terminal margin changes are -124 GOOSE, -4 COW, and +36 SHEEP. There is no future inventory injection and no additional WHEAT consumption. The complete cash and quantity table is in `AFTERCARE-VALIDATION.json`.

Thus **resource-free CARE is not a theorem of nondecreasing reward**. These are not grounds to kill an unmeasured entire lane, but they invalidate unconditional economic-safety language. The existing native assembler should consume this same evidence when deciding delivery/capacity admission; do not activate from a synthetic positive alone.

Other controls isolate yield clipping, a later same-day CARE that subsumes the rewrite, absent future feeding, terminal horizon, shed admission, and shared-market effects on the rival. The helper correctly declines all six day-28 cases. In the rival-sale cases, own cash and own-minus-rival margin differ; the oracle does not silently equate them.

## Executed validation

- 22/22 oracle tests in normal Python and 22/22 under `-O`.
- 10/10 independent bound-source tests in each mode, zero failures/errors/skips.
- Seven deliberately faulty oracle/intervention/instrumentation variants assertion-rejected in each mode, zero test errors or skips. These are **not helper-source mutation counts**.
- 36 instrumented-versus-pristine complete-interpreter transition pairs per oracle suite: three species, two seats, three clock positions, and two actor arrangements. Full serialized state/environment equality and shared public-state identity are checked.
- Each report has 60 synthetic paired continuation cases (120 arms), 60 initializations, and 60,600 full-interpreter transitions. All arms reach real DONE rewards for both seats. There are 48 distinct initial fixture hashes because some cases intentionally share an initial state but have different fixed continuations.
- The manual intervention changes all 60 cases; the exact helper changes 54. Manual and bound-source reports each regenerate byte-identically between normal Python and `-O`.

The reported 60,600 count is **per report**, not the total across repeated tests, fault controls, and report regenerations. These are continuations from constructed states, not 120 natural full-season games. No native runtime was executed by AFTERCARE; SECONDCARE's native evidence remains separate.

## Source and engine custody

`aftercare_engine.py` authenticates the official engine, its JSON configuration, upstream seed utility, and the existing loader **before import**. Missing dependencies are rejected, never downloaded. The source API is loaded only after matching the caller-supplied full Git blob ID. Loading a helper executes trusted project Python; it is not a sandbox.

Reference source came from workflow artifact `10175943272`, under `final-pressure-runtime/checks/reference/`. The artifact's checked native archive is `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`, but this certificate covers only the four authenticated reference files, not the native archive/runtime or arbitrary latest V4. Exact file identities and every compact source outcome are recorded in the validation JSON.

Oracle source: `9ad59d1143cead79ca22c86b88e1b9850af2e44b`.
Oracle tests: `2d80d49bc9e8c91ca13ee6105eb2d0d3243ed01b`.
Bound-source tests: `c532368bd05f2a7c183e22d2d9860c4d2bd27082`.
Fault runner: `90f7f36a02c15f49e399bbc5acc69b19949d0280`.

## Reproduce

From this directory, point `AFTERCARE_REFERENCE` at an existing authenticated reference tree. `dead_feed_care.py` is the shared SECONDHELP source, not a copied helper in AFTERCARE.

```bash
export AFTERCARE_REFERENCE=/absolute/path/to/final-pressure-runtime/checks/reference
export AFTERCARE_LANE="$PWD/dead_feed_care.py"
export AFTERCARE_LANE_BLOB=51c17ea3245755673ffead8e86d4b04e7766c949
python -B check_aftercare_engine.py
python -O -B check_aftercare_engine.py
python -B check_aftercare_source.py
python -O -B check_aftercare_source.py
python -B faults_aftercare.py --output /tmp/aftercare-faults-normal.json
python -O -B faults_aftercare.py --output /tmp/aftercare-faults-optimized.json
python -B aftercare_engine.py --reference "$AFTERCARE_REFERENCE" --output /tmp/aftercare-manual.json
python -B aftercare_engine.py --reference "$AFTERCARE_REFERENCE" \
  --lane "$AFTERCARE_LANE" --lane-blob "$AFTERCARE_LANE_BLOB" \
  --output /tmp/aftercare-source.json
```

The fault runner also accepts `--only` followed by named faults; each group still requires a green baseline and rejects errors/skips as invalid evidence. This was used to keep executions bounded after one combined invocation exceeded the execution time limit. All seven faults were then completed in each mode. A failed direct-container download was resolved by copying the connector-fetched helper and authenticating its exact Git blob before the successful source runs; the failed pre-copy attempts are not counted as acceptance.

Full raw reports can be regenerated from the committed deterministic fixtures and authenticated dependencies. Their exact fingerprints are:

- Manual: 1,473,192 bytes, SHA256 `4f978433ade67c50f4ec20a032ad5b52abe1578da2dbe8dfd8ac55dd71634b76`.
- Exact helper: 1,472,822 bytes, SHA256 `638040e2a3d255cc43a96b429bf56ad0972afd65247108280b5e7e24991ddd37`.

The validation JSON stores these identities and the complete compact 60-case source outcome table, not the full raw reports. The deliberately extreme market-inventory floor-price fixture is a semantic control, not a claimed reachable season. No production/default/archive/Kaggle setting is changed by this acceptance package.
