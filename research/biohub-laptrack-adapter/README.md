# Biohub LapTrack adapter

This is a **data-free, non-submission** integration scaffold for the Biohub cell-tracking lane. It converts explicit 3D detections into the public LapTrack API, then converts the returned directed `(frame, index)` graph into Commons/Biohub node and edge rows.

It does not download competition data, log into Kaggle, run a hosted notebook, submit predictions, or claim leaderboard quality. The build runtime did not have LapTrack installed, so no real LapTrack solver execution is claimed here. Pure input/coordinate/graph/CSV behavior is exercised with an injected synthetic solver, and missing/version-drifted LapTrack fails closed.

## Upstream pin

The adapter is pinned to public `yfukai/laptrack` version `0.17.1`, commit `13acf99fee57eaae0db84b0205142cd079a1d098`, tree `71d8bc8a500456bc75a9add7fb497a917e756d52`, BSD-3-Clause. The audited API exposes `LapTrack.predict(...) -> nx.DiGraph`, uses `(frame,index)` nodes, supports split inference with `splitting_cutoff`, and defaults both splitting and merging off. Exact audited file blobs are in `UPSTREAM.json`.

## Safety/contract choices

- Input CSV header is exactly `dataset,detection_id,t,z,y,x`.
- `detection_id` must be a stable non-negative integer unique within a dataset. It is used only to make frame-local ordering deterministic.
- Physical distance uses `z*scale_z, y*scale_y, x*scale_x`; output nodes retain original integer voxel `z,y,x`.
- LapTrack is configured with squared-Euclidean distance, serial execution, `gap_closing_cutoff=False`, `merging_cutoff=False`, and split inference disabled unless an explicit positive `--splitting-cutoff` is supplied.
- Returned graph nodes must exactly cover the input detections.
- Every edge must be `t -> t+1`; duplicate edges, merges (>1 parent), and sources with >2 children are rejected.
- Node IDs and CSV row IDs are deterministic. Division topology is represented as one source node with exactly two outgoing edges.

These are conservative adapter guards, not a claim that they reproduce the organizer's scoring implementation.

## Runtime

Install the audited LapTrack version in a prepared/offline-compatible environment, then:

```sh
python adapter.py \
  --detections detections.csv \
  --output submission.csv \
  --scale-z 4.0 --scale-y 1.0 --scale-x 1.0 \
  --cutoff 225 \
  --splitting-cutoff 225 \
  --provenance-json laptrack-run.json
```

`--cutoff` and `--splitting-cutoff` are squared physical-distance cutoffs because the adapter pins LapTrack's `sqeuclidean` metric. Omit `--splitting-cutoff` to leave split inference off.

The adapter intentionally rejects a non-`0.17.1` LapTrack import. An environment carrier can widen that pin only after re-auditing the upstream API and updating `UPSTREAM.json`.

## Build-session validation

Run from this directory:

```sh
python -B -W error::ResourceWarning -m unittest -v test_adapter
python -m py_compile adapter.py test_adapter.py
```

The tests are synthetic and contain no competition bytes. A later authorized evaluation should benchmark this adapter against a frozen local/train split and compare it with the BTrack and baseline lanes before any model/parameter promotion.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

