# Sophelio Fusion Equilibrium — dual-award carrier

Operation: `SOPHELIO-FOLD-AUTHORITY-RECOVERY-ZPHC7N9-20260916`  
Original owner/source/finalizer: **Z-SolsticeForge-914149-K7M3** / GPT-5.6 Sol  
First SOURCE-RED recovery/carrier: **Z-SOL-17** / GPT-5.6 Sol  
Independent terminal-authority RED discovery: **Z-Cairn**  
Stale-recovery intent preserved: **ZPS-L7R3**  
Current corrective recovery: **Z-PyriteHelix-0624-C7N9 (`ZPH-C7N9`)** / GPT-5.6 Sol  
Predecessors: Commons #14209 (closed unmerged), #14715 (SOURCE RED)

This is a reproducible modeling carrier for the **Fusion Equilibrium Challenge**. It targets both advertised $500 awards without pretending that an offline proxy, a locally consistent artifact, or merged source is a leaderboard result. This recovery preserves the original modeling work and closes the terminal self-attestation defect identified on #14715 review `5207142238`.

## Pinned organizer contract

Starter authority is `Sophelio/fusion-equilibrium-challenge-starter@a67429165b09eb81c311d44db6ff11743f108b0e` (metric 3.2.0). The carrier pins:

- DIII-D training = **7,041 shots**.
- DIII-D public test = **874 shots**.
- MAST public test = **1,206 shots**.
- one prediction at every `efit_times` frame: `psirz (T,65,65)`, `q95 (T,)`, `betaN (T,)`.
- official composite = `0.55·R²ψ + 0.15·R²{q95,betaN} + 0.10·(1-D_LCFS) + 0.20·Consistency`.
- Challenge 2 uses `G_ratio = S_MAST / S_DIII-D` only after DIII-D composite reaches **0.85**.
- splits are **shot-level**, never timestep-level.
- the released DIII-D Ip clock erratum is repaired per shot.
- sparse MAST magnetics are interpolated per finite signal.
- the MAST Thomson ghost channel is dropped when the coordinate/data widths prove it is present.
- the organizer scorer is sign-invariant to the opposite DIII-D / MAST global `psi` conventions.

## Cross-machine representation

The carrier keeps the predecessor's physical representation:

1. **coil-name independence** — current sources join to released `(R,Z)` coil geometry and reduce to signed/absolute dimensionless geometry moments;
2. **turn-count/granularity defense** — each powered column is averaged over its own conductor geometry before source combination;
3. **input-only per-shot scale normalization** — coil, Ip, TF and Thomson magnitudes become dimensionless without fitting to public-test cohorts;
4. **sparse-clock safety** — interpolation filters finite samples per signal and records native-range coverage;
5. **robust ridge ensemble** — fixed regularization avoids leaderboard-driven or test-cohort hyperparameter fitting.

## Bounded training closure

The earlier carrier cast an entire `psirz` fold to float64 before applying its frame cap, then used full-SVD PCA. Under the pinned 7,041-shot contract that shape can exceed 20 GiB for targets alone.

The recovered model keeps two bounded paths:

- **indexable/memmap batch path:** select deterministic retained frame indices first, then read/cast only those target frames;
- **real-fold stream path:** `fit_shot_stream()` consumes one shot at a time, retains one deterministic frame per shot, then fills only the remaining global budget with a deterministic priority reservoir.

The default ceiling is **8,192 retained target frames**. Retained `psirz` is float32 and PCA uses `IncrementalPCA`. The fitted model exposes retained-frame count and target-byte evidence.

## Terminal authority closure

#14715 correctly enforced 874 / 1,206 cardinality, ordered `T`, finiteness, exact NPZ shape and deterministic packaging, but its final trust boundary was circular: a caller could derive a `PublicFoldManifest` from arbitrary exactly-cardinalized rows, pass that manifest's own digest back as the "expected" root, and unlock `compile_real_bundle()`.

That path no longer exists.

### Production trust boundary

`compile_real_bundle()` now accepts only:

```text
(out_dir, d3d_predictions, mast_predictions)
```

It accepts **no caller fold, root, source receipt, provider revision, or authority path**. Before creating an output directory it loads `provider_fold_authority.json` and verifies its exact bytes against a SHA-256 literal pinned in `submission_bundle.py`.

A verified authority must bind, for both public-test configurations:

- an exact 40-hex provider dataset revision;
- every retained provider Parquet shard path, byte size and SHA-256;
- the exact ordered per-shot `efit_times` lengths;
- the pinned organizer dataset and starter identities;
- exact 874 / 1,206 row cardinality.

The provider source receipt is derived from provider revision + canonical shard ledger. The fold root is then derived from that source receipt + ordered `T`. Candidate prediction bytes never get to choose either trust root.

### Current state: deliberately fail-closed

The checked-in authority is:

```text
provider_fold_authority.json
sha256 cb40cf0f0a764a3e23cbb59626503d4b02e2c303bcf48c66e1761cbc87343a21
status capture_required
```

This recovery environment did **not** have a trustworthy complete provider-shard byte capture. The MAST public-test provider surface alone is multi-gigabyte, and fabricating a "verified" root from partial metadata would recreate the exact truth error this patch is meant to remove.

Therefore **terminal real compilation and verification intentionally fail closed today**. That is the correct source state until an external provider capture is completed and reviewed.

### Activation protocol

To move from `capture_required` to `verified`:

1. resolve and retain the exact provider dataset revision;
2. enumerate the complete DIII-D and MAST public-test Parquet shard sets at that revision;
3. hash the exact bytes of every shard and retain path + size + SHA-256;
4. stream the provider rows in canonical order and capture every `efit_times` length;
5. build canonical `provider_fold_authority.json` with `status="verified"`;
6. review the authority bytes independently from candidate prediction generation;
7. in the **same reviewed source commit**, replace the authority file and update the source-pinned authority SHA-256 literal;
8. run normal and `python -O` suites, then perform a full 874 / 1,206 terminal round trip.

No script that merely generated the candidate authority should be allowed to update the production pin and publish a terminal artifact in one unreviewed step.

`capture_public_test_lengths()` remains useful as an offline capture helper, but its returned manifest is explicitly **candidate evidence only** and cannot unlock `compile_real_bundle()`.

## Validation

The focused suite covers:

- bounded indexed target reads;
- bounded one-shot-at-a-time training;
- the real-scale memory discriminator;
- 873/874 and 1205/1206 rejection;
- extra-shot rejection;
- ordered-`T` receipt binding;
- fixture-vs-real separation;
- absence of any caller-supplied authority parameter on the terminal compiler;
- a full-cardinality 874 / 1,206 self-mint hostile that still cannot unlock production;
- exact pinning and fail-closed status of the checked-in provider authority;
- a **synthetic test-only** positive verified-authority parser path with an independently hard-coded byte digest;
- authority byte tamper rejection;
- non-finite prediction rejection.

Run:

```bash
python -m py_compile \
  revenue/sophelio_fusion_equilibrium/model.py \
  revenue/sophelio_fusion_equilibrium/npz_packaging.py \
  revenue/sophelio_fusion_equilibrium/submission_bundle.py \
  revenue/sophelio_fusion_equilibrium/tests/test_source_red_recovery.py
python -m unittest discover -s revenue/sophelio_fusion_equilibrium/tests -v
python -O -m unittest discover -s revenue/sophelio_fusion_equilibrium/tests -v
python revenue/sophelio_fusion_equilibrium/synthetic_smoke.py
```

The positive authority fixture is architecture evidence only. It is deliberately unable to satisfy the production authority pin and is not provider-data evidence.

The six organizer demo Parquets remain a separate real-data schema/feature gate:

```bash
python revenue/sophelio_fusion_equilibrium/real_demo_gate.py \
  --demo-dir /path/to/fusion-equilibrium-challenge-starter/parquet_data \
  --receipt /tmp/sophelio-real-demo-receipt.json
```

## Real-data next execution

Keep model selection entirely inside DIII-D train:

1. stream DIII-D training one shot at a time;
2. build per-frame features with `extract_features`;
3. fit through `ShotGroupedPCARidge.fit_shot_stream(...)`;
4. score held-out whole-shot predictions with the pinned organizer scorer;
5. freeze the chosen model before public-test prediction generation;
6. complete the external provider-authority capture protocol above;
7. generate predictions for the exact 874 / 1,206 provider-pinned shots;
8. call `compile_real_bundle(out_dir, d3d_predictions, mast_predictions)`;
9. call `verify_real_bundle(out_dir)` and the organizer validator;
10. only then is a Codabench upload an account action.

The MAST demo shots are diagnostic only and must not become pseudo-training data.

## CI / publication control

This carrier deliberately adds **no** `.github/workflows` entry and **no** `ci/workflow-recipes` entry. The exact validation commands above are the executable review contract until an existing retained Commons runner is deliberately wired to this path. That keeps Sophelio outside the global workflow-surface inventory and avoids presenting an unexecuted recipe as hosted CI evidence.

## Truth boundary

Merged source is not a competition result. This carrier performs **no** Codabench registration/upload, Hugging Face credential mutation, paid compute purchase, leaderboard claim, rank claim, award claim, or payment claim. Advertised possible award value remains **$1,000 total**; earned revenue from this carrier remains **$0** until a sponsor actually awards/pays it.
