# TITAN V4 cross-ledger coherence audit

This package is a **read-only** control-plane audit for the sole canonical TITAN V4 tree. It does not register components, order transforms, rewrite either ledger, execute gameplay, promote defaults, assemble a runtime, or authorize a merge.

## Why it exists

`INTEGRATION.json` and `COMPOSITION.json` have separate fail-closed validators, but those validators intentionally own different questions. That leaves split-brain classes where both documents are individually valid while they disagree about what the one V4 actually contains or why a component is blocked.

`check_cross_ledger.py` binds `CANONICAL.json`, `INTEGRATION.json`, `COMPOSITION.json`, and the package-local `SEMANTIC-BINDINGS.json` audit manifest together without changing their ownership boundaries.

The first version of this checker caught a real three-component custody gap: `funding-capacity-stack`, `scoped-construction`, and `projection-state-clone` were already `compose` in the graph without matching landed custody paths. That gap was reconciled canonically in #12919.

A second real incident exposed the remaining blind spot. D4 stayed `blocked` in both ledgers, so state-only checking could not detect that COMPOSITION had advanced to `REACHABLE_BUT_OUTPUT_INERT` after #12852/#12917 while INTEGRATION still said literal zero reachability. #12931 fixed the stale ledger prose; this package now turns that same-state semantic contradiction into a machine-detectable regression.

## Contract

The audit requires the three canonical documents to agree on branch/workspace and requires production coordinates shared by CANONICAL/INTEGRATION to agree.

It then applies asymmetric custody rules:

- A `compose` component must have an exact `INTEGRATION.json` landed row whose `repair_path` equals the component `package`. Missing landed custody is a hard error. A negative/parked row can never satisfy this rule.
- A `blocked` or `evidence_only` component may be represented by either exact landed custody or an exact negative/parked `repair_path`. With neither, the checker emits a warning rather than inventing custody.
- Duplicate landed paths, duplicate negative paths, duplicate component packages, unsafe paths, malformed/duplicate-key JSON, canonical-coordinate drift, and a negative exact package marked `compose` fail closed.
- A landed row that explicitly supplies `composition_state` (and optionally `composition_intake_pr`) remains a bilateral hard contract: exact package and state must match COMPOSITION.

### Same-state semantic bindings

Some important contradictions cannot be represented by state alone. `SEMANTIC-BINDINGS.json` supplies narrow, auditable assertions for those cases without rewriting either canonical ledger schema.

Each binding names an exact COMPOSITION component/package/state, an exact INTEGRATION negative lane/disposition, and a stable semantic marker that must be present in the component reason/note. The checker fails if the component/package moves, the state changes, the negative lane disappears, the INTEGRATION disposition changes, or the COMPOSITION semantic marker disappears.

The initial binding is deliberately the predecessor-killing D4 case:

- component: `d4-strawberry-timing`
- package: `research/d4-strawberry-timing`
- state: `blocked`
- INTEGRATION disposition: `KILL_reachable_but_output_inert_do_not_stack_or_activate`
- COMPOSITION marker: `REACHABLE_BUT_OUTPUT_INERT`

This does **not** reopen D4 or elevate the audit manifest into gameplay authority. It only makes recurrence of the already-resolved split-brain fail closed.

## Authority boundary

The result carries an explicit no-authority policy: no merge/close, ledger rewrite, composition mutation, runtime promotion, gameplay decision, economic decision, archive mutation, or Kaggle action is authorized by this checker.

The semantic binding file is an audit assertion, not a third composition graph. Canonical truth remains in the sole `main:candidates/v4` COMPOSITION/INTEGRATION pair; when their truth legitimately changes, the corresponding binding must change in the same reviewed convergence operation or the checker will fail visibly.

## Run

From this directory:

```bash
python -B -m unittest -v test_check_cross_ledger.py
python -O -B -m unittest -v test_check_cross_ledger.py
python -m py_compile check_cross_ledger.py test_check_cross_ledger.py
```

From anywhere, audit the repository's canonical V4 root:

```bash
python -B revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/cross-ledger-coherence/check_cross_ledger.py --pretty
```

The CLI loads `SEMANTIC-BINDINGS.json` beside the checker by default. Exit status is `0` only when there are no hard cross-ledger errors. Warnings remain visible in the JSON result.
