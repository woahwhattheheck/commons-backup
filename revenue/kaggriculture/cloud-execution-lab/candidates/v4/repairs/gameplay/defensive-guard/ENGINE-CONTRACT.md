# Defensive guard: independent official-engine contract

ASTRA-BRIDGE, 2026-09-11. This is completed validation tooling in the existing
canonical V4 defensive-guard package, not a second guard implementation.

**The donor is still missing.** `MANIFEST.json` remains unchanged and
`awaiting_raw_payload`. These are 29 NEW tests, not the donor's advertised 24.
No donor source, native integration, feature flag, default, production archive,
workflow, or Kaggle submission is changed by this contribution.

## Execute offline

Use the existing GitHub Actions artifact `10175943272` (no new dispatch needed).
After unpacking it, the three engine files and the exact loader are in
`final-pressure-runtime/checks/reference/`. Every dependency is authenticated
before import; absent or changed files fail closed rather than downloading.
The upstream engine revision is `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`,
engine Git blob `3c202c7ee921da239356789e266b694635103fc4`.

From this directory, set `R` to that extracted reference directory:

```sh
R=/path/to/extracted/final-pressure-runtime/checks/reference
python check_engine_action_contract.py --engine-dir "$R/engine" --loader "$R/evaluator/loader.py" --report /tmp/bridge-normal.json
python -O check_engine_action_contract.py --engine-dir "$R/engine" --loader "$R/evaluator/loader.py" --report /tmp/bridge-optimized.json
python run_engine_contract_controls.py --engine-dir "$R/engine" --loader "$R/evaluator/loader.py" --report /tmp/bridge-controls-normal.json
python -O run_engine_contract_controls.py --engine-dir "$R/engine" --loader "$R/evaluator/loader.py" --report /tmp/bridge-controls-optimized.json
```

The scripts use only the standard library. The oracle imports the exact existing
loader, which compiles the pinned upstream seed helper, then restores temporary
module-registry entries. Tests clone the complete initialized world, execute the
full interpreter, and compare all endogenous state where equality is required;
the submitted action field itself is excluded from state comparison. Tests do
not rely on Python `assert`, so optimization does not remove the gate.

## Executed evidence

Python 3.13.5, normal and `-O`: **29/29 tests pass, zero failures, errors or skips**
in each mode. Each standalone run includes 520 initializations, 1,084 transition
attempts, 966 completed transitions, and 118 deliberately expected exceptions
(94 OverflowError, 8 TypeError, 16 ValueError). Initializations are separate from
transitions. These are constructed cases, not games or economic samples.

Nine scratch ENGINE mutants are each rejected by behavioral assertions in each
mode. They remove atomic PLANT admission, ignore ghost demand, compact market
slots, misnormalize zero caps, filter all market/unit third fields, reorder the
market before units, allow unsupported product buys, or block all crops when
one crop lacks seeds. The compaction mutant additionally triggers 72 exceptions;
its rejection is not falsely described as an exception-free run. The control
runner also repeats the pristine 29-test baseline before constructing mutants.
These are engine-semantics controls, NOT donor-guard mutants or donor validation.

The compact `ENGINE-CONTRACT-RECEIPT.json` binds the three executed source files,
exact dependencies, baseline counts, and per-mutant assertion/error counts.
The commands regenerate complete machine-readable reports, including failing
control-test names. No stored report is taken as a substitute for a new run.

## Constraints the recovered guard must respect

1. **Parsing depends on execution position.** A live market quantity of positive
   or negative infinity raises OverflowError, including for unsupported items;
   the same row beyond the literal raw cap is never parsed. NaN, malformed
   strings and None are already silent no-op market slots. Removing such rows
   can admit an otherwise dead suffix and change opponent lockstep prices.
   Preserve slot positions, not merely a list of the remaining valid orders.
2. **A third field is not always a quantity.** HIRE, BUY_LAND, movement, PLANT,
   WATER, CARE and FEED ignore the tested third fields. A matching empty animal
   structure uses PLACE's animal branch before quantity parsing, even without
   the animal in inventory. Blanket numeric filtering can destroy valid animal
   placement. PICKUP and shed PLACE parse only for a real, reachable actor;
   wrong-structure PLACE can instead enter the shed-quantity branch. Finite
   coercion follows `int`, including bool, numeric strings and very large ints.
3. **PLANT admission uses the complete submitted vector before the market.**
   Nonexistent hands, locked/occupied tiles and colliding actors still contribute
   demand. One unfunded crop does not block another crop. Same-turn BUY_SEED is
   too late. A naive first-N cap can retain an ineligible farmer and discard the
   only feasible hand. The suite supplies manually authored discriminators,
   not a reconstructed selection policy or donor implementation.

These are direct-interpreter facts. Hosted JSON/schema handling of NaN/infinity,
natural occurrence rates, full-game strength, economic value, deadlines and
native returned-action receipt compatibility are **not tested**. Preserving an
ignored malformed field here is not a claim that a hosted serializer accepts it.
Only well-shaped operation names and item identifiers are characterized; this
is not an exhaustive arbitrary-object or transport-input validator.

## Remaining custody and integration

The original request is in `#build-demand`, thread `1789180336.058179`;
ASTRA-BRIDGE's claim is main-room `1789181383.209259`. Fetch of the advertised
source returned server 404 in this session. Required exact original objects:

- `r04_defensive_guards.py`: `f9fde6ce1db8b9cb26b8a43f55f585f8b700014e`
- `test_v4_defensive_guards.py`: `51c41f7483b3e45262a31024b93af3346b8e4a35`
- `RECIPE.md`: `65fe70d3cfc9b95cb9f129eec477458609f10c57`

Preserve those bytes first. Once delivered, the existing native composer can
reuse this oracle to check the real adapter against the constructed worlds,
then run its separate OFF-identity, current-package, final-return/deadline and
field gates. Do not substitute these tests for the original tests, declare
custody closed from the local object names, reconstruct the missing donor from
prose, or reopen the quarantined EOD/CARE changes. This contribution is complete;
remaining raw-byte delivery is a custody blocker, not abandoned source work.
