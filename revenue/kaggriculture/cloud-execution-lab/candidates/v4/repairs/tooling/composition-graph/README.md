# TITAN V4 composition graph (ASTRA-LOOM)

This tooling is a **fail-closed control plane for the one canonical V4 workspace**. It does not create another V4, materialize production, enable feature keys, rebuild the archive, or submit to Kaggle.

`INTEGRATION.json` remains the custody/evidence ledger. `COMPOSITION.json` answers a different question: *given authenticated transform packages, in what exact order may they be applied to the same source surfaces without silently consuming stale bytes?*

## Contract

A component is one of:

- `compose`: eligible for the deterministic plan when its exact preimage identities match, but not thereby runtime-promoted.
- `blocked`: known package whose prerequisites/economic/custody gate is not satisfied.
- `evidence_only`: preserved evidence that is not executable composition input.

Every active transform names a logical `surface`, an exact `input_identity`, and an exact `output_identity`. Relations (`requires`, `before`, `after`, `conflicts`) are component IDs. The validator rejects unknown relations, active dependencies on blocked/evidence components, active conflicts, cycles, unordered writes to the same surface, stale predecessor identities, duplicate output identities, missing package/entrypoint paths, canonical-root/branch drift, symlink or resolved-path escapes, and strict-discovery entrypoints not registered in the manifest.

A `compose` row is still source-bound. If a receipt authenticates a frozen foundation rather than latest source HEAD, its exact input identities are the gate: newer bytes must not be reset to the fixture just to satisfy the graph. Rebase the component and rerun its combined gates instead.

The graph deliberately stays conservative. Current-ABI fast-tape-clone is composable because both predecessor and materialized postimage are authenticated. The funding-capacity aggregate records the already-executed TOWNPATH -> UNITFLOW -> FUNDING-PERF -> CAPTRACE sequence, including exact baseline scheduler/frozen preimages, final postimages, archive identity, executable source order, and receipt path; it does not claim latest-HEAD or production promotion. D4 strawberry timing remains blocked by its reachability/economic contract. Current-ABI row-shed SELL ordering is also blocked at composition intake: its component/dependency pins are preserved, but no authenticated materialized runtime postimage exists yet, so source custody is not misreported as a composed edge.

## Run

From `candidates/v4`:

```sh
python check_composition_graph.py --json
python -m unittest repairs/tooling/composition-graph/test_composition_graph.py
python -O -m unittest repairs/tooling/composition-graph/test_composition_graph.py
```

A zero exit means the declared graph is internally composable. It does **not** mean the components are production-promoted or that every landed repair has been registered. Strict discovery only covers the entrypoint patterns explicitly listed in `COMPOSITION.json`; extend those patterns and register/justify newly discovered composers as the native integration surface broadens.

## Adding a component

1. Authenticate the exact input and generated output identities against the stated foundation.
2. Add the package and executable entrypoint paths relative to this V4 root.
3. Declare every touched logical surface.
4. Declare ordering/dependency/conflict edges instead of relying on Slack chronology. For an already-composed aggregate, retain its exact internal `source_order` and receipt rather than inventing intermediate whole-file identities.
5. Use `blocked` rather than inventing an identity, predecessor, or authorization.
6. Run the validator and both normal/optimized focused suites before handing the plan to the existing native composer.

LOOM intentionally does not own claim-liveness (LANTERN), custody semantics (LEDGER), optimizer logic (WEAVE), or final native materialization. It only makes cross-package composition order mechanically reviewable.
