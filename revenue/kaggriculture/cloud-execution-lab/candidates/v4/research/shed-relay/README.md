# SHEDRELAY — same-callback shed handoff

Status: **mechanism proven; authenticated baseline cold; no runtime admission**.

The official interpreter applies unit actions in actor order (farmer, then hands) against one shared mutable `private.shed`, before market processing. Because legal shed-adjacent `DROP` and shed-path `PLACE` mutate that shed immediately, a later actor in the same callback can `PICKUP` the newly deposited item. Reverse order cannot observe a future deposit.

`DROP` has an important capacity hazard: it deletes each source-inventory entry even when only part of that quantity fits in the shed. A relay optimizer must therefore be capacity-safe; a generic `DROP` rewrite is not admissible.

## Evidence

The source oracle is pinned to reference-engine Git blob `3c202c7ee921da239356789e266b694635103fc4` and SHA256 `bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`. `shed_relay_probe.py` proves forward `DROP→PICKUP`, forward shed-path `PLACE→PICKUP`, reverse-order rejection, item mismatch, adjacency rejection, and the partial-capacity DROP loss case against the official evaluator loader.

The route census is pinned to Actions artifact `10180428228`, inner `checked-package/exports/titan-current.tar.gz` SHA256 `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`, source manifest SHA256 `e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2`. Across seeds 1–4 × both seats versus the official starter, fresh processes observed 5,752 callbacks, 930 actual shed writes, 1,288 actual pickups, and 56 callbacks where an earlier shed write preceded a later pickup. None were same-item links; none were causal relays.

That result is deliberately **not** a claim about the eventual sole current-main composition postimage. It proves a real engine seam and records that the authenticated b567 baseline does not exploit it. Do not add a second scheduler or runtime hook from this evidence. Re-open only if the sole current postimage yields an output-changing, capacity-safe same-item relay witness with OFF identity and fresh economics.

Machine-readable results are in `SHED-RELAY-VALIDATION.json`.
