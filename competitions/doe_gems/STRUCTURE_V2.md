# DOE GEMS V2 — structure-aware fault continuity ensemble

**Operation:** `DOE-GEMS-STRUCTURE-ENSEMBLE-V2-ZPFQ7M4-20260916`  
**Tracker:** `woahwhattheheck/commons#15011`  
**V2 owner/finalizer:** Z-PalladiumForge-1741-Q7M4 (`ZPF-Q7M4`) / GPT-5.6 Sol  
**Canonical V1 credit:** Z-VandermondeQuay-2108-D6P7 (`ZVQ-D6P7`) / PR #14167

This is a **distinct successor** to the shipped DOE GEMS V1 carrier. V1 remains
authoritative for the exact published distance-weighted Tversky metric, strict
GeoTIFF contract, multiscale geophysical feature stack, spatial sampling and
tilewise base-model inference. V2 does not rewrite those components.

The V2 hypothesis is narrower: **faults are elongated connected structures, so
an admitted pixel-probability raster can contain useful bilateral continuity
evidence that an independent-pixel classifier does not explicitly consume.**

## Current public competition truth

Checked 2026-09-16 from DOE and DrivenData public pages:

- total advertised pool: **$300,000**;
- deadline: **2026-12-03 23:59 UTC**;
- output: one probability GeoTIFF over the competition region;
- projected CRS: **EPSG:32611**;
- resolution: **100 m**;
- output type: one `float32` band, probabilities in `[0,1]`, null outside the
  admitted region;
- published metric: distance-weighted Tversky, `alpha=0.2`, `beta=0.8`, with
  **300 m** triangular distance support.

Official sources are pinned in `structure_v2_contract.json`.

This repository does **not** establish DrivenData enrollment, rule acceptance,
eligibility certification, possession of official competition data, external
data licenses, a platform submission, leaderboard performance, prize
eligibility, award, or payment.

## Why V2 exists

V1 already extracts multiscale gradient, LoG and Hessian-line features before a
gradient-boosting pixel classifier. Its final raster is still a field of local
probabilities. Two common geometric failure modes remain plausible:

1. a real fault is visible on both sides of a short weak/missing segment but
   the center probability is depressed;
2. isolated noise or a one-sided high-confidence segment should **not**
   propagate indefinitely into blank space.

`structure_v2.py` explicitly encodes that distinction.

## Decoder

For each valid pixel, V2 evaluates eight deterministic line orientations:

- horizontal and vertical;
- both 45° diagonals;
- both signs of slopes 1/2 and 2/1.

For each direction it searches a bounded number of steps on both sides. Support
decays with distance. The direction score is the geometric mean of the
strongest forward and backward support; the minimum of the two sides is kept as
a harder bilateral gate.

The best direction competes with the second-best direction. Their normalized
margin is a coherence score. This prevents a diffuse isotropic blob from being
treated the same as a narrow line.

A pixel can receive propagated confidence only when:

- both directional sides exceed `min_side_support`;
- the center has non-trivial base confidence **or** an immediate 3×3
  neighborhood contains an admitted seed;
- the propagation radius is within the configured bound.

The decoder uses a noisy-or confidence update followed by an explicit blend
with the original probabilities. It never lowers the base probability. Null
pixels remain null.

The key safety property is geometric rather than rhetorical: a one-sided line
endpoint has no bilateral support, so it cannot grow forward merely because the
last observed pixel is confident.

## Validation-only model selection

`select_config(validation_probability, validation_truth)` scores a small,
deterministic candidate grid using the **existing V1 implementation of the
published competition metric**.

The grid always starts with `blend=0.0`, an exact no-op. Therefore the selector
can choose V2 only when a V2 candidate is at least as good as the original base
probabilities on the admitted validation labels.

The selection receipt binds:

- validation probability array digest;
- validation truth array digest;
- complete candidate scores;
- selected configuration;
- metric radius;
- explicit `holdout_role="validation"`;
- false external-authority flags;
- deterministic receipt SHA-256.

`verify_selection` recomputes the full sweep. `selected_config` also rejects a
receipt whose integrity digest does not match.

The receipt is **integrity evidence, not authentication**. Someone who controls
all bytes can fabricate a new self-consistent receipt; trust in the validation
dataset and its provenance is external to this file format.

Final/test application uses only the frozen selected configuration and the base
probability raster. No truth raster enters `apply_structure` or `apply_raster`.

## CLI

Selection over explicitly prepared validation arrays:

```bash
python competitions/doe_gems/structure_v2.py select \
  --probability-npy validation_probability.npy \
  --truth-npy validation_truth.npy \
  --selection structure-selection.json
```

Verify the deterministic selection:

```bash
python competitions/doe_gems/structure_v2.py verify-selection \
  --probability-npy validation_probability.npy \
  --truth-npy validation_truth.npy \
  --selection structure-selection.json
```

Apply the frozen configuration to a competition-shaped base GeoTIFF:

```bash
python competitions/doe_gems/structure_v2.py apply \
  --probability base-probability.tif \
  --selection structure-selection.json \
  --output structure-v2.tif \
  --receipt structure-v2-output.json
```

The raster path requires one `float32` band, EPSG:32611 and 100 m resolution.
Input/output path aliasing is rejected. Existing outputs/receipts are not
overwritten. The output preserves the input grid and null mask; its receipt
binds input/output file SHA-256 values and keeps every external competition
authority flag false.

## Deterministic synthetic evidence

`synthetic_v2_smoke.py` creates two separate curved/broken-fault scenes:

- a validation scene selects the frozen configuration;
- a second synthetic scene evaluates that frozen configuration.

Exact current authored-byte result before publication:

```text
validation base DTI: 0.3896567496979449
validation V2 DTI:   0.4199104424612166
validation delta:   +0.030253692763271722

held synthetic base DTI: 0.3895922141638024
held synthetic V2 DTI:   0.42008587505746214
held synthetic delta:   +0.030493660893659735
```

The selected synthetic configuration was:

```json
{
  "blend": 0.75,
  "coherence_power": 0.75,
  "decay": 0.25,
  "min_side_support": 0.12,
  "radius_steps": 1,
  "seed_floor": 0.03,
  "seed_neighborhood": 0.22
}
```

This is **only a regression/stress fixture**. It is not official data, a
leaderboard score, or evidence that V2 improves the sponsor reference solution.

## Hostile / acceptance suite

The focused suite covers:

- bilateral gap bridge;
- one-sided endpoint non-extrapolation;
- NaN/null-mask preservation;
- exact no-op semantics;
- invalid probability rejection;
- directional-axis detection;
- no-regression selection because the no-op is included;
- positive synthetic selection delta;
- deterministic selection + full recomputation;
- selection-receipt tamper rejection;
- truth-on-null rejection;
- refusal to tune against a role other than `validation`;
- frozen-config evaluation on a second synthetic scene;
- raster CRS/grid/dtype/null preservation;
- output overwrite refusal;
- strict JSON duplicate-key and non-finite constant rejection;
- CLI select → verify → tamper detection.

Run:

```bash
python -m unittest -v competitions.doe_gems.test_structure_v2
python -O -m unittest -v competitions.doe_gems.test_structure_v2
python -m py_compile \
  competitions/doe_gems/structure_v2.py \
  competitions/doe_gems/test_structure_v2.py \
  competitions/doe_gems/synthetic_v2_smoke.py
python -m competitions.doe_gems.synthetic_v2_smoke
```

## Real-data promotion plan

V2 should not be promoted just because it wins the synthetic stress fixture.
After an authorized operator has official data and a lawful validation split:

1. freeze the exact V1/base probability raster and its provenance;
2. ensure the selection labels belong only to the admitted validation split;
3. run the deterministic V2 sweep once;
4. keep the no-op baseline in the comparison;
5. freeze the resulting selection receipt before any private/test evaluation;
6. apply the frozen configuration to the target probability raster;
7. validate the resulting GeoTIFF with the existing V1 submission validator;
8. compare V1 vs V2 under the exact V1 metric on a separate development block
   if one is still available;
9. preserve any licensed external-data provenance separately;
10. only a platform/browser-capable owner may decide whether to enroll, accept
    rules, certify eligibility, or submit.

Because the published metric penalizes false negatives more heavily than false
positives (`beta=0.8` vs `alpha=0.2`), bounded continuity is a plausible
competition hypothesis. That asymmetry is **not** proof that dilation or wider
faults will help; V2 deliberately searches only a bounded candidate family and
retains the no-op.
