# Defensive guard pack — raw payload publication (R04_DEFENSIVE_GUARDS, default OFF)

This PR publishes the **awaited raw payload** for the custody-blocked
"defensive guard pack" (`repairs/gameplay/defensive-guard`, INTEGRATION.json
`custody_blocked`): ancestry-neutral raw objects plus focused tests and the
composition recipe. It changes no feature flag, default, runtime, archive, or
Kaggle state.

Donor lineage: `guard-donor-7a64dc3d.patch` (final, published; CARE guard
explicitly excluded by the donor). The three guard bodies in
`r04_defensive_guards.py` are byte-identical to the donor tree's inline
versions (verified via `inspect.getsource` comparison at carrier build time).

## Custody convergence — blocker resolved

The historical `INTEGRATION.json` row saying `awaiting_raw_payload` is stale.
Merged PR #13159 landed the requested ancestry-neutral raw payload at this
pre-existing ledger-owned path, merge
`86363108927b9e946732daa35e91430a78fd3323`. Current exact identities are:

- source `r04_defensive_guards.py` Git blob
  `b1fc775ecaf608ca40d01945ec82ae8372ee988b`;
- focused test `checks/test_v3_r04_defensive_guards.py` Git blob
  `07785fa53d56444f764af9af4d7cb906bd39ba7d`.

Merged PR #13162 subsequently created the parallel path
`repairs/gameplay/r04-defensive-guards` and registered that spelling in
COMPOSITION. Its source and test are byte-identical to the blobs above, so it
is a race duplicate, not a second semantic donor. That duplicate path is now
explicitly quarantined as superseded/evidence-only; this `defensive-guard`
path remains the sole source-custody authority under the one-tree rule. The
unique duplicate README remains recoverable from PR #13162 / blob
`2e9ec8631b26e5ca51dc5c4ebc1cd4ce16810675`.

Raw-payload custody is therefore **CLOSED**. Runtime composition/promotion is
still **BLOCKED** and is a separate gate. The machine integration ledger and
COMPOSITION path should be normalized to this canonical path when the next
metadata-only registry reconciliation is admitted; until then, do not infer a
second authority from the stale rows.

## Guards

1. `_sanitize_numeric_args` — inf/nan/non-coercible numeric-arg clamp
   (engine `int()` on inf/nan kills the whole interpreter step). Independently
   harvestable per the ledger.
2. `_guard_plant_overdemand` — per-crop PLANT cap at seeds held (the engine's
   atomic PLANT rule drops ALL of a turn's PLANTs for a crop when the total
   exceeds seeds). Independently harvestable per the ledger.
3. `_guard_eod_autodrop` — EOD cheapest-first rescue SELLs for projected shed
   overflow. **QUARANTINED per the ledger**: overlaps current V4
   EOD-capacity-rescue; must remain un-composed pending a dedicated ablation.
   Published here as raw evidence bytes only.

The CARE cap-waste guard is **absent** (donor-excluded; the ledger explicitly
rejects CARE stripping — it measured dM -3976 and desyncs the tape's CARE
choreography). This payload introduces no CARE behavior.

Fixed at carrier build: the extracted module was missing `_SHED_CAPACITY`
(the EOD body reads the underscore-prefixed name); the fail-closed try/except
had masked the `NameError` as identity. Fixed by defining
`_SHED_CAPACITY = 100` in the module (verified: 4 EOD-guard tests failed
before, 30/30 after).

## Gate evidence (carrier, 2026-09-11/12)

- Hardened gate 1 (key OFF vs guards-on base, 16 cells): dM **+0, stdev 2**
  (noise; control -0±2) — neutral is PASS for defensive guards. Traces
  differed in 16/16 cells (guards engage in real games).
- Hardened gate 2 (key-ON fidelity, 4 cells): 0/4 trace diffs vs base —
  the keyed seam reproduces the donor's unconditional-guard behavior exactly.
- Verdict: PASS (neutral, as expected for defensive guards).
  Full record: `~/workspace/build/v4/carrier-guards/VERDICT.txt` (fleet artifact).

## Files

- `r04_defensive_guards.py` — the three guard bodies plus
  `_apply_defensive_guards(observation, action)` (identity when nothing needs
  fixing). Standalone, stdlib only.
- `checks/test_v3_r04_defensive_guards.py` — the donor's 30 tests,
  byte-identical. They import `r04_full_router` and use the `r04._guard_*`
  names, i.e. they exercise the router import seam; receipts below were taken
  against the exact seam (module + canonical import), the same seam the
  recipe below installs in the composed router.

## Test receipts (2026-09-12, Python 3.x)

- `python3 -m unittest checks.test_v3_r04_defensive_guards` → **30/30 OK**
- `python3 -O -m unittest checks.test_v3_r04_defensive_guards` → **30/30 OK**

## Composition wiring recipe (default OFF; for the custodian)

Exact seam, matching the gated carrier (key-park pattern):

1. Canonical router: `from r04_defensive_guards import
   (_apply_defensive_guards, _guard_eod_autodrop, _guard_plant_overdemand,
   _sanitize_numeric_args)` replacing the inline guard defs (keeps the
   `r04._guard_*` names the tests use); `R04_DEFENSIVE_GUARDS = False`
   global; in `v3_agent`, after all lane wrappers,
   `if R04_DEFENSIVE_GUARDS: action = _apply_defensive_guards(observation, action)`;
   `install(..., defensive_guards=None)` sets the global.
2. Current-ABI runtime: `Features.r04_defensive_guards: bool = False`;
   `install` kwarg `defensive_guards=...`;
   `diagnostics['defensive_guards']`.
3. `TITAN-CONFIG.json`: `"r04_defensive_guards": false` (ships OFF).

Composition constraints (from the ledger, binding): compose only the
sanitizer and PLANT-overdemand guards; keep the EOD rescue quarantined until
ablation; do not reintroduce CARE stripping; do not enable any guard merely
because this payload exists.
