# Methods-ready note

## Objective

Provide a deterministic, data-free readiness layer for the 2026 Biohub Cell Tracking During Development competition so an authorized training/inference worker can fail fast on packaging and lineage errors before consuming a Kaggle submission slot.

## Representation

The public submission is a graph serialized as CSV. A node is a cell detection with integer `(t,z,y,x)` voxel coordinates; an edge links two node IDs in the same dataset. Divisions are represented as one source with two children. The validator keeps node identity dataset-scoped and enforces consecutive `t→t+1` tracking by default.

## Geometry

The public dataset documentation gives anisotropic spatial scale `(z,y,x)=(1.625,0.40625,0.40625)` µm/voxel. The smoke linker therefore computes Euclidean distance after scaling each axis into physical microns. This avoids a four-fold axial distortion from treating z/y/x voxels as isotropic.

## Baseline hook

`synthetic_baseline.py` is intentionally not a competitive model. It uses deterministic one-to-one nearest-neighbour linking with an 8.5 µm gate on synthetic sparse detections. The goal is to exercise graph construction, stable ordering, sentinels and CSV validation using only the Python standard library.

A competitive lane can replace only the detection/linking producer while retaining the same submission checks. The organizer starter repository is the preferred reference for exact metric evaluation and its learned UNet/transformer baseline.

## Reproducibility

- Standard-library-only smoke/validator code.
- No network access at runtime.
- Fixed synthetic coordinates and deterministic sort/tie-break rules.
- Exact organizer starter Git commit pinned in `SOURCE_LOCK.json`.
- Public starter offline/runtime hazards are bounded in `OFFLINE_RUNTIME.md`; no full-stack offline-install PASS is claimed.
- Unit tests cover valid output plus representative contract failures.

## Data governance

This lane intentionally contains no competition data. Any real training/test bytes stay on an authorized local/Kaggle surface under the competition rules. Publicly available external data/pretrained models may be permitted by the competition, but this lane neither selects nor redistributes them.

## Evidence boundary

Passing these tests proves only that the scaffold's public-contract checks and synthetic link path behave as documented. It does not prove leaderboard accuracy, hidden-test compatibility beyond the published schema, prize eligibility, or payout.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

