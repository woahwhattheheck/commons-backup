# Peapod compound / plate provenance gate

This package implements the offline, buyer-neutral acceptance core behind
`peapod-compound-plate-provenance-gate-01`.

It reconciles research metadata for compound transfers across:

- compound master identity;
- source vial, plate, well, plate lot, volume and concentration;
- singleton versus pool membership;
- destination plate / well / lot and destination compound identity;
- assay protocol version and control-well-map hash;
- instrument-run linkage.

The output is evidence, not a scientific decision. Every row is
`READY_FOR_SCREEN` or `HOLD` with exact reason codes. The JSON manifest is
canonical and its records form a SHA-256 append-only chain; the CSV projection
contains the same decision records. Both artifacts have independent SHA-256
sidecars and an offline verifier.

## Exact acceptance fixture

`fixture.py` generates exactly **384** synthetic transfer rows:

- **360** clean rows must be `READY_FOR_SCREEN`;
- **24** planted defects must be `HOLD`;
- exactly four rows exercise each of:
  `DUPLICATE_ASSIGNMENT`, `SOURCE_DESTINATION_MISMATCH`,
  `WRONG_POOL_MEMBERSHIP`, `VOLUME_BALANCE_FAILURE`, `STALE_PROTOCOL`,
  `ORPHANED_RUN_LINK`;
- zero defective rows may be ready;
- repeated builds and reversed input iteration are byte-identical.

Run:

```bash
python -m unittest -v revenue.peapod_compound_plate_provenance_gate.test_gate
python -O -m unittest -v revenue.peapod_compound_plate_provenance_gate.test_gate
python -m revenue.peapod_compound_plate_provenance_gate.cli --out /tmp/peapod-proof
```

The CLI writes `provenance-manifest.json`, `provenance-manifest.csv`, and
`SHA256SUMS`.

## Authority boundary

This package processes synthetic/research metadata only. It does **not** evaluate
potency, toxicity, efficacy, hit quality, campaign value, or compound
suitability. It does not release a screening campaign, operate instruments,
write to a LIMS, contact a buyer, use buyer credentials/data, or perform any
payment/provider/deployment action. A human scientist retains campaign-release
and scientific interpretation authority. A clean gate is provenance evidence
only.
