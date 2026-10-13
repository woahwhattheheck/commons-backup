# Biohub BTrack adapter

Data-free integration scaffold for the Biohub Cell Tracking During Development paid competition lane. It converts explicit `(dataset,detection_id,t,z,y,x)` point detections into a **pinned BTrack v0.7.0** run and then into Commons submission node/edge rows. This directory contains no competition data, model weights, Kaggle credentials, score, rank, award, or payment claim.

## Reproducibility boundary

Upstream is pinned to `quantumjot/btrack` **v0.7.0**, source commit `a3bd947915efe6837936f9db6db88417f0b51b45` (MIT). Real execution requires that exact package/runtime and an audited BTrack configuration. The pure adapter tests inject a fake tracker; they do **not** claim a native BTrack/GLPK run. The offline dependency lane must separately prove the v0.7.0 wheel/native library and `cvxopt.glpk.ilp` work in the target notebook image before optimizer-backed lineage is called ready.

## Safety/identity rules implemented here

* Detections are sorted deterministically before `append()`. BTrack v0.7.0 overwrites incoming localization IDs with `0..N-1`; the adapter freezes that sequential ref -> original integer voxel detection map and also tags each object with `commons_detection_id`.
* Output coordinates always come from the immutable original detection map, never from BTrack's physical `x/y/z` values.
* The adapter converts `tracker.tracks` **immediately** after tracking/optimisation and never invokes list-mode HDF export first. BTrack v0.7.0 `HDF5FileHandler.write_tracks(list[Tracklet])` mutates object IDs before recomputing `Tracklet.refs`; the independent property tag + coordinate/time checks fail closed if ref identity changed.
* Each Commons `dataset` gets a fresh `BayesianTracker`, fresh ref map, fresh volume and output accumulator. Multiple dataset values are never appended into one native engine.
* Multi-dataset CLI runs require an exact dataset -> voxel-bounds CSV manifest. The manifest must contain one and only one row for every dataset in the detections CSV; missing or extra datasets fail closed. The six scalar bound flags remain available only for single-dataset CLI runs, so one shared volume cannot be silently reused across differently shaped datasets.
* Voxel `(z,y,x)` positions are scaled into physical BTrack `(x,y,z)`. Configured volume is reordered/scaled into the same units and `max_search_radius` is explicitly a physical distance. `optimise=True` additionally requires an explicit `optimizer_distance_units="physical"` attestation for the external BTrack configuration.
* Adapter input is preflighted against the pinned native ABI: `t` must fit BTrack's unsigned 32-bit timestamp field, and scaled coordinates/volume endpoints must remain finite before anything reaches the tracker engine.
* Dummy/negative refs never become Commons nodes or edges. A track that would bridge nonconsecutive real observations fails closed; emitted edges are strictly `t -> t+1`.
* Parent/child Tracklet lineage is converted as parent-last-real -> child-first-real. The adapter rejects unknown refs/tracks, duplicate track IDs, >1 parent, >2 children, and non-adjacent lineage.

The default scale is the currently routed Biohub anisotropy pin: `z=1.625`, `y=x=0.40625` physical units per voxel. Volume bounds remain explicit inputs rather than being inferred from detections because BTrack uses the configured imaging volume in border/hypothesis logic.

## CLI shape

Single-dataset runs may use the six scalar voxel bounds:

```text
python adapter.py \
  --detections detections.csv \
  --output submission.csv \
  --config audited_cell_config.json \
  --max-search-radius 8.5 \
  --zlo 0 --zhi <z-max> --ylo 0 --yhi <y-max> --xlo 0 --xhi <x-max>
```

For a detections CSV containing multiple datasets, use `--bounds-csv` instead of the scalar bound flags:

```text
python adapter.py \
  --detections detections.csv \
  --output submission.csv \
  --config audited_cell_config.json \
  --max-search-radius 8.5 \
  --bounds-csv dataset_bounds.csv
```

The bounds manifest header is exact and deterministic:

```csv
dataset,zlo,zhi,ylo,yhi,xlo,xhi
dataset_a,0,63,0,511,0,511
dataset_b,0,95,0,383,0,383
```

Dataset names must use the same no-`.zarr`, no-surrounding-whitespace form as the detections CSV. Bound values must be finite and each high bound must be greater than or equal to its low bound. The manifest dataset set must exactly equal the detections dataset set.

Add `--optimise --optimizer-distance-units physical` only after the configuration's optimizer thresholds have been audited into the same physical coordinate system and the offline GLPK smoke has passed.

## Data-free acceptance

`test_adapter.py` covers deterministic sorting/CSV bytes, anisotropic physical-coordinate equivalence, physical volume/radius propagation, one-engine-per-dataset isolation, exact two-child lineage conversion, dummy/gap rejection, unknown refs, the HDF-style valid-ref permutation guard, optimizer-unit fail-closed behavior, and original voxel-coordinate preservation. `test_bounds_manifest.py` covers exact manifest parsing, multi-dataset fail-closed behavior without a manifest, exact dataset-set matching, and distinct expected physical volumes on separate injected tracker instances. `test_output_alias.py` covers resolved-path and hard-link output aliases so detections/config inputs are preserved. `test_track_membership.py` covers global real-ref membership/coverage and fail-closed Tracklet/lineage invariants, including all-dummy output. `test_contract_parity.py` feeds fake-tracker output through LINEAGE's canonical `submission_contract.py`, asserts the exact submission schema, and proves adapter/canonical repeat-write byte determinism. `test_abi_ranges.py` covers the pinned unsigned-32-bit timestamp limit and finite physical-coordinate/volume preflight. These are data-free fake-engine/contract tests; native BTrack/GLPK execution remains a separate offline-dependency gate.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

