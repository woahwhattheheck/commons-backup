# KINETIC: native unit-dispatch fusion — research-only

**Disposition: no measured whole-native speed gain; do not promote or add a required wiring task.**

This closes ASTRA-KINETIC's broad unit-action execution-cost investigation in the
single canonical `main:candidates/v4` workspace. It is neither another V4 runtime
nor a gameplay policy. Source, runnable checks, actual execution results and a
repeatable negative promotion result are delivered together.

## What was built

`compose_kinetic.py` generates a scratch derivative of the native mechanics
module. It inlines the three tiny actor-position/inventory/position-set helpers
inside `_apply_unit_action`, while keeping identity-guarded fallbacks for rebound
helpers. It preserves the inventory-growth side effect of PASS, missing-actor
short-circuit order, negative indices, position replacement rather than alias
mutation, mapping access order, live movement-table edits, and every remaining
action branch. No mutable world state is cached. The list-construction shortcut
also checks the original list binding.

The composer authenticates exact function/dependency spans, rejects drift and
name collisions, is idempotent, and preserves every source byte outside its
alias block and the single target function. Input files cannot be overwritten
through its CLI. This is an Apache-2.0 derivative of the original pinned Kaggle
helper, not a claim that the generated function remains unmodified upstream.

Input native mechanics Git blob: `044a4f9c0a4a44dde10ada57563238bcaf82075d`.
Generated mechanics Git blob: `2a74c0b94f1898bbc1c10cbf309c22b205126778`.
Generated SHA256: `2f5d3cf3767dd2e2d3db6c7dc396bff97cacb53c1ff71ffd10974b0ef8284def`.

## Executed evidence

Python 3.13.5; normal and `-O` component runs each pass **15/15** tests with no
failures, errors or skips. Each mode covers 1,172 direct differential pairs
(including 208 expected exception pairs) and 188 full official-interpreter
pairs: 184 completed transition pairs plus four expected numeric-conversion
exception pairs. Nine additional initializations occur per suite. Animal PLACE
with an ignored nonfinite third field is a positive control, not classified as
a conversion exception. Both seats and EOD/terminal boundaries are included.

Ten deliberately broken variants are rejected by named behavioral assertions
in each mode, never credited for infrastructure errors. A clean nine-test
control runs before the variants. Full interpreter tests retain the engine's
atomic PLANT admission, including ghost rows; this component does not replace
UNITFLOW's separate joint-stage repair.

Twenty complete native `main.py::agent` games were executed: eight uninstrumented
normal, eight uninstrumented optimized, and four separately instrumented games.
All 14,380 native callbacks completed; all ten baseline/candidate pairs match
complete returned-action and post-interpreter state-stream hashes, final scores
and termination. The 16 uninstrumented games use seeds 17/101 and both seats
against the official starter, with alternating arm order (reversed in the
optimized panel). Four instrumented seed17 games independently show 310,798
unit-kernel calls per game, with identical opcode histograms in both arms.

All 109 runtime members and the exact SOURCE manifest were authenticated.
The game fixture is the checked b567 archive, not the subsequently assembled
whole-V4 tree. The live mechanics source matched this input when inspected.
No claims are made about competitive opponents or hosted Kaggle performance.

## Why this is not promoted

Seven alternating 150,000-call local batches per fixture measured about 5.05%
less elapsed for PASS, 6.58% for movement and 3.94% for the constructed mixed
loop. These small helper-level gains did **not** establish an end-to-end gain:
median paired native elapsed ratios were 1.00249 normal and 1.00996 optimized
(candidate/baseline). Individual signs were mixed. This is a noisy neutral
result, not proof of a statistically significant slowdown either.

Preserve the source and tests as research. Do not multiply the microbenchmark
with WEAVE/PORTAGE/PHENOLOGY timings or force this into their active stack.
Their methods remain separate; no combined-stack execution is claimed here.
In-place function `__code__` mutation, arbitrary concurrent in-process monkeypatch
races, forced-deadline cancellation and Python 3.11 were not validated. Helper
rebinding and ordinary mutable input/alias behavior are explicitly tested.

## Reproduce offline

Use an extracted immutable copy of `exports/titan-current.tar.gz` with SHA256
`b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`.
Set `B` to that extracted directory and run from this research directory.

Before starting any `run_kinetic_games.py` parent process, obtain the runner Git
blob from an **external exact-head authority** (for example the GitHub contents
or tree entry for the commit being tested) and independently confirm the
checkout file matches it. Do not create the expected value by hashing the same
mutable file and then treating that self-derived value as provenance. For this
reviewed runner, `RUNNER_BLOB=1d9526ad8357dfd5c3f1a8b133592565b0bf3d3a`.
Launch the trusted parent with isolated Python startup (`-I -S`) as shown below;
this prevents ambient `PYTHONPATH`/`sitecustomize` hooks from gaining authority
before the externally authenticated source starts.

```sh
python compose_kinetic.py --input "$B/mechanics.py" --output /tmp/kinetic-mechanics.py
python check_kinetic.py --native-root "$B" --report /tmp/kinetic-check.json
python -O check_kinetic.py --native-root "$B" --report /tmp/kinetic-check-O.json
python run_kinetic_mutants.py --native-root "$B" --report /tmp/kinetic-mutants.json
python -O run_kinetic_mutants.py --native-root "$B" --report /tmp/kinetic-mutants-O.json
RUNNER_BLOB=1d9526ad8357dfd5c3f1a8b133592565b0bf3d3a
python -I -S -B run_kinetic_games.py --expected-runner-git-blob "$RUNNER_BLOB" --native-root "$B" --seeds 17,101 --repetitions 1 --output /tmp/kinetic-games.json
python -I -S -O -B run_kinetic_games.py --expected-runner-git-blob "$RUNNER_BLOB" --native-root "$B" --seeds 17,101 --repetitions 1 --order-offset 1 --output /tmp/kinetic-games-O.json
python -I -S -B run_kinetic_games.py --expected-runner-git-blob "$RUNNER_BLOB" --native-root "$B" --seeds 17 --repetitions 1 --instrument --output /tmp/kinetic-engagement.json
python benchmark_kinetic.py --native-root "$B" --output /tmp/kinetic-benchmark.json
```

The external runner pin closes the trusted-parent/post-launch repository-reopen
boundary. It does not claim that Python can authenticate its own initial source
before that source begins executing; the launcher/executor must perform the
pre-invocation exact-head check and isolated startup above. After the parent
captures and authenticates its control bundle, child processes do **not** execute
a materialized runner pathname. The parent feeds captured runner bytes to a
constant `python -c` bootstrap over stdin; child startup is fixed to `-I -S -B`
plus only a controlled `-O`, inherited `PYTHON*` variables are stripped, and no
caller-supplied interpreter flags are accepted. The bootstrap recomputes the Git
blob against the external pin before compile/exec. Child-only modes require the
injected attested runner identity.

Each child treats its physical baseline/candidate tree as input transport only.
It authenticates the pinned SOURCE manifest and every declared runtime member
once, captures those bytes, and then stops using that tree as execution authority.
Python modules are imported from a captured-byte meta-path loader under a
non-filesystem virtual `__file__` root. Captured runtime file reads—including the
reference engine JSON—are served from the same in-memory byte map, with normal
text-mode locale encoding semantics preserved, and the reference loader, engine,
agent, mechanics and other local modules execute from that capture. Thus a
same-UID process replacing runtime source/data paths after capture cannot change
the bytes executed or read by the game. The filesystem transport can still be
mutated before/during capture, but such mutations must match the pinned manifest
(or the exact candidate mechanics SHA) or the child fails before runtime
authority is established.

The game runner starts a fresh process per game from captured control bytes,
preserves all raw market and unit rows, records full stream hashes and per-call
timing, and rejects incomplete games or mismatched traces. Child receipts state
both the runner and runtime executed from captured bytes; composer/checker fields
describe the parent-authenticated control identities, not child execution of
those helpers. The committed historical receipt normalizes repeated identities
while retaining all 20 game outcomes and aggregate timing, all 42 benchmark
timing samples, both test receipts, and every fault-control result. It does not
contain every per-call sample; those are regenerated in the runner's output.
Historical evidence predating the custody hardening remains historical; new
custody claims require an exact-head gate.

No production source, config, release archive, workflow definition or Kaggle
submission is changed. This completed research lane creates no production wiring
requirement; exact-head evidence gates for custody changes remain separate.
