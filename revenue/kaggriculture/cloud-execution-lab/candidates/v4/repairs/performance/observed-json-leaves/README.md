# Observed-JSON leaf copying — candidate only

Status: **BUILT / TESTED / NOT PUBLISHED**. This packet is an additive contribution for
`main:revenue/kaggriculture/cloud-execution-lab/candidates/v4`, not a second V4
runtime, release branch, archive, or configuration.

## Change

The native `scheduler.post_units` path copies observed farms and private values
through `observed_clone.detached_json_value`. The parent recursively calls the
public function even for scalar leaves. The candidate copies exact scalar leaves
in the containing list/dict comprehension and recurses only for non-scalar values.
There is no mutable-state cache, new gameplay policy, import dependency, or key.

Only `observed_clone.py` differs in the authenticated scratch runtime. Parent git
blob: `f810d53193d3035655a36c21021e18ba1d415916`. Candidate git blob:
`91650bbfe250b3a074b9238b210da1fba3de4251`. Full SHA256 pins are in INPUTS.json.

This preserves the existing *observed JSON* boundary: exact scalar values,
insertion order, detached plain list/dict containers, deliberately separated JSON
aliases, and deepcopy fallback for foreign leaf values. Dict/list wrapper classes
are normalized exactly as the parent does. This is **not** a generic deepcopy
replacement. Cycles remain unsupported. Dynamic rebinding of recursive hooks and
pathological values at the recursion limit are not certified. Do not use it for
checkpoint or arbitrary object-graph copying.

## Evidence

- 23/23 component tests in normal Python and 23/23 under `-O`, without errors or
  skips. Each mode includes 1,000 generated JSON forests, 50 real post_units
  baseline/candidate pairs and 96 full official-interpreter calls.
- Seven deliberately broken variants per mode are rejected by assertions, not
  import failures or infrastructure errors. Unchanged controls pass first.
- Eight completed native games: two seeds (2027, 6607), both seats, baseline and
  candidate versus official_starter. All four paired action/bank/terminal-state
  hashes and scores match. This is 5,752 native callbacks. The primary evaluator
  does not inspect internal fallback diagnostics; do not infer those from scores.
- Two separately executed instrumented pairs match uninstrumented control traces.
  Each game records 2,832 actual projection-copy calls after callback zero and 719
  completed native diagnostics. Helper time falls 13.1% in the original pair and
  22.2% in the portable rerun. Those are callsite measurements, not whole-agent gains.
- The retained seven-batch benchmark shows dense-farm elapsed time 14.5% lower,
  scalar-list 30.8% lower, tile-grid 13.1% lower, and empty-container 11.9% **higher**.
  All 56 raw samples and interpreter/platform details are retained.

**Whole-agent timing is mixed and does not justify production activation.**
The four primary candidate mean-call changes are retained in VALIDATION.json;
one paired cell is about 6.6% slower. No win-rate or score improvement is claimed.
These executions authenticate checked archive b567, not the latest composed V4.
They do not certify Python 3.11 or Kaggle-hosted behavior; the executed interpreter
is Python 3.13.5. Full CLI attempts and serialization/timeout failures are retained
in ATTEMPTS.md, not silently filtered. Final components-only CLI and standalone
packaged game-pair execution pass; an uninterrupted full CLI run was not completed.

## Offline reproduction

Use GitHub Actions artifact **10175943272**, ZIP SHA256
`3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8`.
The CLI authenticates the ZIP, b567 tar, engine/evaluator/loader source, and all
109 declared runtime members plus the matching SOURCE.json manifest (110 files).
It refuses existing output paths. No network or paid/owner-PC compute is required
by these scripts. Python 3.12+ is required for this runner's safe tar extraction;
only Python 3.13.5 was executed here.

Run from this packet directory, replacing the artifact path and choosing new
scratch directories:

```sh
python run_gate.py --artifact /path/to/titan-native-10175943272.zip \
  --output /tmp/leaf-components --components-only

# One command for the complete intended four-cell native panel.
python run_gate.py --artifact /path/to/titan-native-10175943272.zip \
  --output /tmp/leaf-full --seeds 2027,6607 --seats 0,1

# Reproduce actual callsite engagement and check instrumentation against controls.
python run_telemetry.py --artifact /path/to/titan-native-10175943272.zip \
  --output /tmp/leaf-telemetry --seed 2027 --seat 0 \
  --control-receipt /tmp/leaf-full/games-2027-0.json

python benchmark.py --native-root /tmp/leaf-components/baseline \
  --output /tmp/leaf-benchmark.json --batches 7 --iterations 600
```

`progress.json` is written before long stages; only `gate-result.json` records a
completed gate. A timeout or partial games file is never a passing certificate.
The production entrypoint and evaluator remain unchanged in all game executions.
`receipts/original-drivers` preserves the exact initial local scripts; those have
historical absolute scratch paths and are evidence rather than the portable API.

## Composition for the one existing native assembler

`compose.py --source-root <authenticated-current-runtime> --output-root <new-scratch>`
creates a separate test tree. It authenticates the exact parent helper or exact
already-applied candidate, rejects source drift and symlinks, and preserves every
unrelated runtime byte. Do not replace another peer's source with a whole old
runtime tree. It is compatible with unrelated-method composers by construction;
combined-stack behavior and timing still require execution.

QUARRY's snapshot edge-elision, TAPEPORT/TAPESTRY/CLONE-FIELD's action copies,
WEAVE's optimizer, and PHENOLOGY/PORTAGE's mechanics retain their existing scopes.
No overlapping source claim was posted: this session exposed read-only connectors.
HANDOFF.md is an **unsent** peer intake, not a claim of Slack delivery or merge.
