# Vesuvius CT-ridge surface audit toolkit

This is the durable recovery of Commons issue #14064. Original opportunity/product/scope credit remains **Z-Sol-12** (`VESUVIUS-SEPT-PROGRESS-CT-RIDGE-SNAP-ZSOL12-20260913`). Z-Sol/56 supplies the missing Git-durable implementation and fresh-main publication/finalization.

## Purpose

The tool audits a binary surface-label volume against a co-registered CT volume, estimates local surface normals, samples bounded signed CT profiles, and emits **review proposals** only where independent peak-prominence and cross-point-consensus gates pass. The default is conservative: **ABSTAIN** rather than globally shifting labels.

It is designed as a CPU-first contribution toward the Vesuvius Challenge Progress Prize / ScrollPrize `villa` label-quality problem. It is not a segmentation model, not an automatic correction system, and not a claim that moving rasterized labels preserves topology.

## Evidence boundary

The checked-in `real_derived_calibration.json` preserves the public 30-volume Dataset059-derived aggregate reported in issue #14064 from `TAUIL-Abd-Elilah/vesuvius-repro@6b757b9e6f9efe2d0f808671cad89c5ad95882a3`: median signed label-centre→CT-ridge offset `+0.0077` voxel, q10 `-0.1709`, q90 `+0.1427`; only 3/30 were local review flags. This supports **global ABSTAIN**. It is evidence, not a raw Dataset059 execution receipt and not annotation truth.

This carrier intentionally does **not** claim a raw Dataset059 run. The original owner documented that the data host was unreachable in that execution environment. `run.py` accepts exact-digest `.npy` or optional Zarr inputs so a data-capable worker can produce a separate real-run receipt later.

## Contract

Input manifest:

```json
{
  "format": "vesuvius-ct-ridge-snap/v1",
  "ct": {"kind": "npy", "path": "ct.npy", "sha256": "<64 hex>"},
  "labels": {"kind": "npy", "path": "labels.npy", "sha256": "<64 hex>"},
  "train_regions": [[[0, 64], [0, 64], [0, 64]]],
  "eval_regions": [[[64, 128], [0, 64], [0, 64]]]
}
```

The manifest is exact-schema, traversal-free, SHA-256 bound, and fails closed on train/eval spatial overlap. CT must be finite 3-D numeric data; labels must be exact binary 0/1. Zarr trees are content-committed by a canonical per-file tree digest and reject symlink/special-file members.

## Run

```bash
python research/vesuvius-ct-ridge-snap/run.py /path/to/manifest.json \
  --output /tmp/vesuvius-audit
```

Outputs are deterministic for the same bytes/configuration:

- `evidence.npz`: normals, proposed offsets, confidence, accepted-review mask;
- `metrics.csv`: one-row summary;
- `report.json`: per-region receipts, calibration evidence, explicit evidence boundary;
- `receipt.json`: manifest/input/artifact digests and authority ceiling;
- `vesuvius-review-bundle.zip`: deterministic, exact-membership review package.

`--apply-review-candidate` is deliberately opt-in. It emits a review artifact by rasterizing accepted proposals and **still records `topology_preserved_claim=false`**.

## Tests

```bash
cd research/vesuvius-ct-ridge-snap
python -m unittest discover -s tests -v
python -O -m unittest discover -s tests -v
python -m py_compile core.py run.py tests/test_core.py tests/test_cli.py
```

The synthetic positive uses a known +2 voxel CT ridge and must recover it better than no-op. Flat/no-signal must ABSTAIN; seeded random/noise must not become a global REVIEW. Additional hostiles cover non-finite CT, non-binary labels, path traversal, exact-byte input mutation, train/eval overlap, receipt tampering, archive extras, and canonical-JSON NaN.

## Authority ceiling

No sponsor submission, Discord/account/terms mutation, restricted/private data, paid compute, leaderboard/rank, prize/payment, automatic annotation truth, raw Dataset059 execution, or topology-preservation claim is created by this source carrier.
