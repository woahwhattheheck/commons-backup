# TITAN V5 route-matrix row receipt

This is the **observation/receipt bridge** between the merged shared route carrier
(`#13475`) and the merged P04 reducer (`#13478`). It is not a second evaluator,
route-force harness, or runtime selector.

`route_matrix_row_receipt.py` is the fail-closed public facade. The older
row/snapshot logic remains in `_route_matrix_row_receipt_core.py`;
`route_matrix_candidate_custody.py` adds archive/root identity, captured-source
execution, worker-private candidate custody, and shared publication authority.

The bridge:

- SHA-verifies the pinned official native evaluator (`e30b3108...`) and engine
  loader (`61093af2...`) before execution.
- Consumes a shared `build_route_matrix.py` manifest and accepts only the
  step-144 matrix (`selection_step=144`, one changed `r04_full_router.py`,
  production-v3 baseline `20f20116...`, router preimage `41ea55c5...`).
- Requires both the route-candidate archive and its materialized root. It
  single-reads every materialized member, rejects symlinks/extras/missing files,
  and checks every SHA against `manifest.files`.
- Decodes the candidate tar through the exact SHA-pinned `build_delivery.members`
  parser used by the canonical route builder (`build_delivery.py` SHA256
  `8f578d09...`). That parser authenticates the archive SHA and rejects
  non-files, duplicate/noncanonical paths, traversal and backslashes. The bridge
  then requires the archive member SHA map to equal `manifest.files` **and** the
  decoded archive bytes to equal the captured executable root byte-for-byte.
  An archive-A/root-B pair therefore cannot authorize a row.
- Loads SHA-pinned helper modules from one authenticated captured byte stream:
  the final path is `lstat`-checked, opened with `O_NOFOLLOW` when available,
  inode-checked with `fstat`, read once, hashed, and the captured bytes are
  `compile`/`exec`'d directly. A helper path cannot be hashed and then reopened
  with different bytes.
- Captures the complete Kaggle file-agent loader closure before execution:
  `cloud-pack/official.py` SHA256 `83e53481...`,
  `cloud-pack/upstream/manifest.json` SHA256 `040ed98c...`, and every upstream
  file named by that exact manifest at its manifest SHA256.
- Embeds the authenticated candidate bytes and loader closure into a generated
  bootstrap. No caller candidate-root or official-loader pathname is embedded
  in that bootstrap.
- Uses a private subclass of the **unchanged pinned evaluator Actor** only for the
  candidate seat. The bootstrap is created as `candidate-adapter.py` inside the
  Actor's fresh private cwd, made read-only while that cwd is non-writable, and
  passed to the evaluator worker as a relative spec. After the worker reports
  ready, the parent re-hashes the adapter and unlinks it immediately.
- Inside the worker, the bootstrap materializes its embedded candidate and
  loader closure into a fresh worker-private directory, verifies every byte,
  executes the captured `official.py` bytes directly with `__file__` pointed at
  the private captured closure, constructs the candidate through
  `official.make_agent()`, re-verifies the private trees, and freezes them
  read-only. Original caller-visible candidate/loader paths are never reopened.
- Imports the pinned evaluator unchanged and calls its original `play()` exactly
  once. During that call it temporarily wraps `Actor.act` only to observe the
  candidate input at step 144, then delegates exactly once to the original
  method with the same observation/configuration/timeout.
- Immediately reduces that observation to P04's public contract: first two
  shops, public market prices/inventory, own cash/worker+animal+crop counts,
  rival visible animal+crop counts, and source-derived incumbent plan. Raw
  `private`, shed, farmer inventory, future town and RNG fields are never
  serialized.
- Requires a complete failure-free 719-decision / 720-episode-step game and
  emits terminal own/rival/margin directly from the pinned evaluator result.
- Requires the candidate Actor report to attest the expected adapter SHA256,
  actor-private publication, and adapter removal after startup before a row can
  be published.
- Runs the produced row through `p04_route_ranker.normalize_row()` and
  SHA256-binds its canonical public snapshot.
- Publishes the JSONL row and sidecar receipt through the ONE merged V5 shared
  `selective-carrot/publication_custody.py` primitive (SHA256 `d1594489...`).
  Final paths are create-exclusive, all are reserved before payload writes,
  success re-authenticates pathname/payload identity, and rollback only removes
  this invocation's still-owned finals while reservation FDs remain live.

The sidecar binds the route candidate archive, full materialized-file manifest,
archive/root byte identity, evaluator/loader/engine authority, captured official
loader closure, generated bootstrap SHA256, candidate Actor custody attestation,
opponent entry fingerprint, seed/seat/RNG seed, step-144 snapshot digest,
full-game trace digest, and exact horizon. It records
`private_observation_persisted=false`.

## Example: R07

```bash
python -B route_matrix_row_receipt.py \
  --evaluator /.../reference/evaluator/evaluate.py \
  --engine-dir /.../reference/engine \
  --loader /.../20260907-offline-agent/evaluate.py \
  --official-file-loader /.../cloud-pack/official.py \
  --candidate-root /.../plan7-payload \
  --candidate-archive /.../plan7.tar.gz \
  --route-manifest /.../plan7-manifest.json \
  --opponent-label apex_v7 \
  --opponent /.../opponents/apex_v7/adapter.py::agent \
  --opponent-entry-sha256 e7b78d4b9e2fc7a68528e45f876a68b50d364103ebd5bf5f2dbbf68770bf54f5 \
  --seed 1209131101 --seat 0 --plan-index 7 \
  --row-out /.../r07-s1209131101-apex-s0.jsonl \
  --receipt-out /.../r07-s1209131101-apex-s0.receipt.json
```

The resulting row is directly consumable by `p04_route_ranker.py` after all
R00-R12 rows for the same `(seed, opponent, seat)` have landed.

This bridge upgrades **candidate** custody through captured-byte execution and a
worker-private loader/candidate closure. It does not independently snapshot the
opponent executable closure; the native executor must continue to use the
authenticated/owned opponent tree required by the existing #13468 authority.

The route discovery matrix is research evidence only. P04 keeps
`policy_ready=false`; any runtime selector still needs a predeclared observable
rule and fresh held-out native games.
