# Selected SELL incumbent-bound pruning

ASTRA-SIEVE component for the one canonical `main:candidates/v4`. This is a
performance-only transformation of the **active** `selected_sell_core.py`, not
another controller or an edit to production. `FrozenSelected` imports its
optimizer here; the optimizer in `scheduler.py` is not that active binding.

## Mechanism and preservation

For fixed public market inputs, strict optimization ranks a candidate by
`(round(min(scenario_deltas), 8), round(sum(scenario_deltas), 8), quantity_now)`.
A scenario delta already below the incumbent's rounded primary score bounds the
complete minimum below that incumbent. Remaining scenarios cannot rescue it.
The transformer therefore stops scoring those candidates early.

Both comparisons use **rounded, strict `<`**, never `<=` or an unrounded delta.
Equal-primary candidates still compete on summed gain and immediate quantity.
The first bound is AFTER the existing capacity callback; its invocation sequence
is retained. Alternative `expected_downside`, `minimax_regret` and forced
feasibility branches, candidate enumeration, MarketPath pricing/floor admission,
weights, returned diagnostics, and all feature keys/defaults are untouched.
This proof assumes the native scoring inputs, not arbitrary callbacks that mutate
price mechanics while the optimizer is running.

Input Git blob: `f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3`.
Output Git blob: `5e6be72cda2e71a1aff6c68b13a0a934b2964a36`.
`patch_selected_incumbent.py` rejects ANY other input and refuses source-path or
existing-output overwrite. Changed inputs require explicit composition and a new
reviewed pin, never substitution of the whole old file over peer work.

## Executed evidence

`EVIDENCE.json` binds source, commands, outcomes and original stdout digests.

* 18/18 unittest checks normal and 18/18 under `python -O`; zero errors/failures.
  Each mode compares 1,031 complete optimizer results and capacity callback
  traces. The aggregate scenario calls fall from 163,390 to 154,599. Four bad
  inclusive/unrounded-bound mutants are rejected by tie discriminators.
* 90 official-market A/B pairs per mode, both seats, including floor inventory,
  dated rival batches and town consumption: 720 actual market calls per mode.
  Full observable states and own/rival/relative receipts match the model.
* Four fresh-process full-game A/B pairs: seeds 9922023 and 9922999, both seats,
  against the official starter. All 2,876 corresponding raw-action/full-state
  frames have equal SHA256 traces. All 5,752 native callbacks completed without
  fallback; 6,696 active optimizer invocations across eight runs. The driver
  preserves extra hand rows rather than changing official PLANT semantics.
* Ten alternating-order whole-optimizer timing rounds, including construction
  and return assembly. Mixed 160-input panel: median 0.172180s -> 0.163557s
  (about 5.0% less time). A deliberately pruning-heavy 40-input panel measures
  0.091852s -> 0.043454s; floor/no-gain control 0.189703s -> 0.186334s.
  These are local synthetic microbenchmarks, NOT whole-agent speed or strength.

## Reproduce without network or Kaggle installation

Use the existing GitHub Actions artifact **10175943272**, run **34537404363**,
not a new workflow dispatch. ZIP SHA256:
`3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8`.
Extract its `checked-package/exports/titan-current.tar.gz` into a runtime directory.
Archive SHA256:
`b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`.
The full-runtime driver verifies exact SOURCE.json and all 109 manifest entries
before making a disposable copy; it never mutates the supplied runtime.

```sh
export TITAN_SIEVE_RUNTIME=/absolute/path/to/extracted/runtime
python test_selected_incumbent.py
python -O test_selected_incumbent.py
python measure_selected_incumbent.py --rounds 10
python patch_selected_incumbent.py "$TITAN_SIEVE_RUNTIME/selected_sell_core.py" /tmp/selected-candidate.py
for seed in 9922023 9922999; do
  for seat in 0 1; do
    python check_runtime_equivalence.py "$TITAN_SIEVE_RUNTIME" baseline --seed "$seed" --seat "$seat"
    python check_runtime_equivalence.py "$TITAN_SIEVE_RUNTIME" candidate --seed "$seed" --seat "$seat"
  done
done
```

For each identical seed/seat compare `trace_sha256`, `steps`, `status`, `reward`,
`optimizer_calls`, `extra_hands_preserved`, and `native_diagnostics`. Require
719 completed callbacks and no fallback. Timing fields are not equality gates.
Each full-game command must start a fresh Python process; do not reuse globals
across the two arms. This is an explicit official-interpreter local driver, not
the hosted Kaggle runner. Tests use unittest checks that remain active under -O.

## Integration boundary

Source, validation and ownership for this component belong in this directory on
main. No production file, config, default, archive, workflow or Kaggle submission
is changed by this packet. MEADOW retains receipt-prefix numerical work;
PRESSURE-PERF retains pressure-stage quote reuse. Compose nonoverlapping changes
into the active selected core and rerun this suite plus the existing current
package gate. Do not reset a newer peer-composed core to this pinned predecessor.
Full-game equality here proves preservation on four exercised pairs only; no
leaderboard, economic improvement or universal runtime deadline claim is made.
