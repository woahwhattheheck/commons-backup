# TITAN V4 GAUNTLETBRIDGE — authenticated opponent-source registry

`opponent_registry.py` closes the source-wiring seam between already-landed V4 opponent research and the existing gauntlet authorities. It does **not** run games, construct schedules, score candidates, or authorize promotion.

## What it binds

The registry consumes only current, pinned authorities already under `candidates/v4`:

- `reference-policy-bank/REFERENCE-POLICIES.json` for static public policies;
- `reference-policy-bank/REFORGE-RECOVERY-VALIDATION.json` plus `prepare_public_bank.py` for the recovered COK/lonespear materialization contract;
- `opponent-challengers/OPPONENTS.json` for ORCHARD's soft reactive family;
- `market-pressure/market_pressure.py` for SQUEEZE's WHEAT-pressure stress opponent;
- canonical SPECTRUM `panel_diversity.py` as the final identity-schema validator.

The tool verifies the Git-blob identity of every authority before composing anything. Static policies then verify every declared source SHA-256 (and any declared notices). ORCHARD verifies its module SHA-256. REFORGE is resolved only when the caller supplies the exact published frozen `REFORGE-BANK.json` materialization and all runtime files verify.

## Identity rules

The paired outputs deliberately separate execution metadata from SPECTRUM identity metadata:

- `titan.gauntlet.opponent-registry.v1` contains entry paths, exact digests, provenance, family labels, and blockers.
- `titan.gauntlet.panel.v1` contains only the fields accepted by SPECTRUM.

ORCHARD's five profiles remain **one** synthetic source family. REFORGE's `lonespear-v18-greedy` and `lonespear-v18-scipy` remain **one** lonespear family. Missing Kaito/Igor custody or absent REFORGE runtime bytes become explicit unresolved rows; the tool never substitutes a nearby implementation or silently drops them.

SPECTRUM is invoked on the generated panel before either output is accepted. A source/family alias conflict therefore fails closed at the canonical authority rather than creating a parallel interpretation here.

## Run

From the repository root:

```bash
V4=revenue/kaggriculture/cloud-execution-lab/candidates/v4
python -B "$V4/research/gauntlet-panel-diversity/opponent_registry.py" \
  --v4-root "$V4" \
  --registry-out /tmp/titan-v4-opponent-registry.json \
  --panel-out /tmp/titan-v4-opponent-panel.json
```

To bind the already-validated REFORGE runtime materialization, add both:

```bash
  --reforge-bank-root /path/to/materialized/bank \
  --reforge-manifest-sha256 d1d9839d80187538b0e8c89a4ccc6ad5a66020a535f534558b8616cc825f5303
```

`--require-resolved` returns status 3 if any known source remains unresolved. This is intentionally strict: it is an admission aid, not a reason to pretend missing opponent custody exists.

## Ownership boundary

Riot/existing gauntlet owners retain orchestration. SPECTRUM/`family_schedule.py` retains scheduling and multiplicity policy. SEALCHAIN retains evidence admission. Reference-policy, ORCHARD, and SQUEEZE owners retain their source semantics. GAUNTLETBRIDGE only authenticates those sources and emits a deterministic identity/entry registry.

No production runtime, gameplay, defaults, archive, workflow, or Kaggle submission path is changed by this package.
