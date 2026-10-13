# Methods note — geometry moments for zero-shot tokamak transfer

## Objective

Improve the transfer hypothesis before spending submission budget. DIII-D and MAST expose the same physical classes of information—actuator currents, plasma current, toroidal field, Thomson profiles and machine geometry—but their coil names, conductor granularity and current units differ. A model that binds identity to DIII-D coil names has no natural MAST input vocabulary.

## Representation

For every powered coil input column `c`, interpolate only its finite native samples onto `efit_times`. Let `(r_c,z_c)` be the average of all released conductor rows driven by that column, mapped to `[-1,1]²` in the machine's native EFIT box. The column current is converted to `asinh(I_c / s)` where `s` is the median 95th-percentile magnitude across powered columns in that shot.

We aggregate signed and magnitude-weighted moments over the six basis functions:

`[1, r, z, r², z², rz]`.

Geometry is averaged inside each powered column first. Repeated MAST conductor rows therefore refine where a source sits; they do not multiply one current source by its element count.

Plasma current and TF are separately normalized by their own input-only per-shot robust scales. Thomson Te/ne profiles use input-only per-shot scale normalization and per-frame distribution summaries. No statistic is fit across the DIII-D or MAST public-test cohort.

## Target and model

The predecessor compressed DIII-D flux maps with full-SVD PCA only after promoting the whole target fold to float64. Independent review showed that this defeats the intended per-shot cap and is not viable at the pinned 7,041-shot scale.

The recovered model selects before promotion:

- batch/indexable inputs compute deterministic bounded indices first and then read only those frames;
- the real-fold API consumes one shot at a time;
- every shot contributes one mandatory deterministic frame;
- remaining capacity is filled by a deterministic priority reservoir over the other per-shot candidates;
- `max_retained_frames` is a hard global ceiling (default 8,192);
- target maps are retained as float32;
- target compression uses `IncrementalPCA` with bounded batches.

At 8,192 retained frames, raw dense target storage is about 132 MiB (`8192 × 65 × 65 × 4`), before ordinary bounded PCA/scaler workspace. The model exposes its observed retained-frame count and target bytes.

The feature side still uses a `RobustScaler` and averages three fixed-alpha multi-output ridge regressors. `q95` and `betaN` use parallel ridge heads.

## Selection discipline

Every candidate comparison remains whole-shot. PCA, scaling and regression are refit inside each training fold. The carrier's `partial_composite = 0.55*R2_psi + 0.15*R2_scalars` omits the organizer-only LCFS/consistency terms and must never be quoted as the challenge score. Real model selection must use the pinned organizer scorer on held-out training shots.

## Challenge-2 logic

A transfer feature change is useful only if DIII-D remains strong enough to clear the current `S_model >= 0.85` gate. `transfer_retention()` encodes that gate for bookkeeping, but only organizer-scored machine composites can make its numeric output competition-relevant.

## Terminal bundle discipline

Synthetic fixture bundles are intentionally separate from real terminal bundles.

A real bundle requires an independently retained public-fold length manifest derived from the streamed test rows. That manifest fixes the exact 874 DIII-D and 1,206 MAST shot counts and ordered `T` sequence. The compiler emits contiguous `shot_XXXX_{psirz,q95,betaN}` keys; the verifier reopens both NPZs and proves exact keys, per-shot shapes, finiteness, file digests, fold roots and the exact two-member upload ZIP.

## Failure modes explicitly tested

- same shot appearing in both train and validation;
- full-fold target conversion before retained-frame selection;
- retained target frames exceeding the global budget;
- full-SVD/full-fold memory shape returning through refactoring;
- DIII-D Ip blanket shifting instead of per-shot repair;
- MAST union-clock NaNs treated as signal dropouts;
- MAST Thomson ghost-channel misalignment;
- EFIT targets affecting feature extraction;
- another public-test shot changing this shot's features;
- partial 873/874 or 1205/1206 fold evidence;
- extra public-test shots;
- altered/reordered per-shot `T` commitments;
- a synthetic 1+1 fixture being presented to the real verifier;
- malformed/extra submission keys or extra direct-upload ZIP members;
- DIII-D or MAST NaN/Inf output;
- nondeterministic NPZ/ZIP bytes;
- post-package file tampering.
