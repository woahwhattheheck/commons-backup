# Methods and decision contract

## 1. Local surface frame

For each deterministically selected positive label voxel, a bounded local neighborhood is gathered. The smallest-eigenvalue eigenvector of the local coordinate covariance is used as an approximate surface normal. Its sign is canonicalized by the largest-magnitude component so repeated runs do not flip orientation arbitrarily.

## 2. Bounded CT profile

The CT volume is sampled with nearest-neighbor coordinates at integer signed offsets within a code-owned ceiling of ±6 voxels. The default is ±3. A proposal must have both robust peak prominence and a positive peak-vs-runner-up delta. Border points that cannot support the full bounded profile are skipped rather than padded or extrapolated.

## 3. Cross-point consensus

Prominent local proposals are grouped into fixed-size spatial blocks. A proposal is accepted into the **review mask** only when the block has sufficient consensus around its median displacement. A global `REVIEW` decision additionally requires a minimum accepted fraction. Otherwise the run remains `ABSTAIN`, even if a few local review flags exist.

This is deliberate: the public 30-volume real-derived evidence pinned in `real_derived_calibration.json` is centered near zero and therefore does not justify a global label shift.

## 4. Candidate rasterization is not authority

The normal product is audit evidence: local normal, signed proposal, confidence, acceptance mask, block receipts, and summary. Candidate rasterization is disabled by default. If a user opts in, accepted source voxels are moved to nearest-neighbor destinations. That operation can merge/split components; therefore every candidate receipt states `topology_preserved_claim=false`.

## 5. Data and leakage custody

Every `.npy` input is bound by SHA-256 before load. Optional Zarr inputs are bound by a canonical digest over exact regular-file paths, sizes, and digests. Symlinks and special files are rejected. Train and evaluation boxes are half-open and must be spatially disjoint.

The repository contains no restricted/private scroll data. The checked-in real-derived calibration is aggregate public evidence only. A later worker with data-host access should run this exact source on raw authorized Dataset059 and publish a separate exact-input receipt; that future run must not be backfilled into this carrier's claims.

## 6. Prize-readiness package

The deterministic bundle contains exact evidence, metrics, report, and receipt. Verification rejects duplicate, missing, extra, traversal, non-regular, oversized, size-mismatched, or digest-mismatched members. The receipt binds the validated input manifest, exact input digests, code-visible config, calibration digest, artifact digests, and explicit false claims for raw-data execution/topology/prize authority.
