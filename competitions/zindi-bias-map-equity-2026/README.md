# Zindi Bias Mapping Equity 2026 — data/leakage fence

Internal build contract for **ZINDI-BIASMAP-A**. This is preparation only: it does not join Zindi, create a team, submit predictions, or accept competition terms.

## Current scored surface

Use the live Zindi sample-submission files as the authoritative tract set. Current scored regions and row counts are:

- `eastern-ok`: 1,192
- `maricopa-az`: 1,593
- `northern-ca`: 591
- `south-central-tx`: 6,003

Source Cooperative also exposes `eastern-wa`, but it is not a current scored region. Do not add it unless the live Zindi sample changes.

The current public challenge package exposes, per scored region, Overture buildings, roads, roads-unfiltered, rail, infrastructure and POIs; ACS housing; and the sample submission. National strata and tract boundaries are also published. Preserve `GEOID` as 11-digit text (Maricopa needs the leading `04`).

## Hard leakage boundary

For the scored RMSE submission, use only data currently supplied for the challenge. On 2026-09-25 the organizers removed target/reference layers including TIGER/Line road targets, Microsoft building footprints, HIFLD facility targets and Census CBP establishment targets. Do **not** reacquire or feed those sources, archived pre-removal packages, old coverage-gap/reference-score files, cached targets, or target values copied from discussions/other contestants into scored modeling.

Additional public data is for the separately judged Best Bias Discovery write-up only, not the scored coverage-gap model.

The package README's historical description of how reference scores were constructed is not permission to reconstruct removed targets. The live inventory and current competition rules control.

## Train-free feature matrix contract

One modeling row = one current scored tract.

Required:
- `region`: one of the four scored slugs above.
- `GEOID`: exactly 11 digits, retained as text.
- No target/label/coverage-gap component columns.

Recommended namespaces:
- `overture__*`: deterministic aggregates from live Overture layers.
- `acs__*`: supplied ACS housing/population denominators.
- `strata__*`: supplied tract context. Preserve source `*_covered` flags/nulls.
- `quality__*`: missingness/provenance flags derived only from allowed inputs.

Record every feature's source path in a provenance manifest. Distances/areas must handle the package's OGC:CRS84 lon/lat axis order correctly; naive EPSG:4326 handling can silently create invalid geometry math. The live package pins Overture release `2026-08-19.0`.

Example manifest:

```json
{
  "features": [
    {
      "name": "overture__buildings_per_housing_unit",
      "sources": [
        "reference/maricopa-az/maricopa-az-overture-buildings.parquet",
        "reference/maricopa-az/maricopa-az-census-acs-housing.parquet"
      ]
    }
  ]
}
```

Validate it:

```bash
python validate_contract.py manifest --manifest feature-manifest.json
```

## Output contract

Validate each regional prediction against the **current official sample file**, not a hand-maintained GEOID list:

```bash
python validate_contract.py submission \
  --region maricopa-az \
  --sample reference/maricopa-az/maricopa-az-sample-submission.csv \
  --candidate predictions/maricopa-az.csv
```

The validator enforces exact current GEOID set and row count, 11-digit GEOIDs, no duplicates/blanks, and finite `coverage_gap_score` values in `[0,1]`. Optional component columns are allowed by the challenge, but every included cell must be populated.

Baseline/performance seats should run this contract before feature construction and again before producing a scored artifact.
