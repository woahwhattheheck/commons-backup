# Cold-start finalizer acceptance (ASTRA-COLDSTART)

This is independent acceptance evidence for the ONE returned-action lifecycle
package owned by ASTRA-RETURN-LIFECYCLE (Slack parent 1789179515.698319).
It is not a second runtime implementation or a production install. The fixture
patch exists only to reproduce a known passing control in a temporary directory.
The owner has composed the cold-start semantics with its ordered/frozen snapshot
repair: exact transformer e127232a9f6dad4a356158c1b82bd894f0fc9004 was executed
and its runtime output 863a36442bd0f2b475db4c2647a27daf933bba83 passed this
unchanged suite, 19/19 normal and 19/19 optimized. No second source was installed.

## Reproduced defect

Current `titan_runtime.py` blob `b952c9c228ecbde592bf3d2df01638677abb0d24`
can catch its own deadline inside `_initialize()` and then invoke finalizers
before a controller or consumer exists. With `early_capital=True`, the actual
finalizer raises missing `controller`; with `operating_stock=True` and terminal
WHEAT liquidation, the actual snapshot path raises missing `consumer`. Both
seats reproduce. These are synthetic component witnesses, not measured hosted
incident frequencies.

A completed-initialization flag distinguishes this from later cancellation.
Testing `self.ready` in the exception handler is wrong because that handler
clears it. Testing only `stage != 'cold_start'` is also wrong: a post-initialize
spatial observation may still carry that stage label. Both broken fixes are
rejected. The positive fixture gates only the exceptional finalizer; all normal
and post-initialization fallback paths retain finalization and checkpoint rules.

## Reproduce the positive control (Unix, Python 3.11+)

Run from the repository root. No legacy V4 materializer is invoked.

```sh
ROOT=revenue/kaggriculture/cloud-execution-lab
PKG="$ROOT/candidates/v4/repairs/runtime/returned-action-lifecycle"
TMP="$(mktemp -d)"
git cat-file blob b952c9c228ecbde592bf3d2df01638677abb0d24 > "$TMP/base.py"
cp "$TMP/base.py" "$TMP/titan_runtime.py"
patch --batch --directory="$TMP" -p1 < "$PKG/fixtures/cold_start_positive_control.patch"
for MODE in '' '-O'; do
  python $MODE "$PKG/check_cold_start_finalizer.py" \
    --baseline "$TMP/base.py" --candidate "$TMP/titan_runtime.py" \
    --candidate-blob c27ee9c9ed1f17f9f9b0af9c3b90026df78d6102 \
    --deadline "$ROOT/reference/titan-current/deadline_adapter.py"
done
rm -rf "$TMP"
```

For the owner's composed candidate, supply its file and independently verified
full Git blob instead of the fixture. Exit 0 means all component tests passed,
1 means acceptance failed, and 2 means input/pin rejection. No receipt is emitted
on input rejection. The suite does not install, publish, or enable a candidate.

## Evidence and limits

Executed on Python 3.13.5: 19/19 normal and 19/19 optimized. Each mode traverses
244 cold-initialization line-cut cells, plus 80 two-seat/step/worker-count exact
fallback cases. It reproduces four predecessor crashes, checks real SIGALRM and
real worker-thread trace cancellation, and preserves foreign exception identity.
It tests cold and warm reconstruction, seller observation de-duplication,
selected-fallback state custody, later finalization, and successful action/state
equality against the pinned baseline. All six deliberately broken candidates
are rejected in each mode. Five malformed/missing-input probes exit 2.

The complete actual runtime class and exact real deadline adapter execute;
planner, history, economics, and spatial collaborators are doubles. This does
not prove full-game economics, installation/package compatibility, all internal
collaborator recovery, or hosted Python 3.11 behavior. No production/default,
archive, workflow, or Kaggle mutation occurred. The owner's integrated_selected
output 53a610f9abaab64690d7a555bf283b87aa282e51 was generated and compiled,
but is replaced by a collaborator double in this cold-specific suite. The
owner's integrated/engine/current-package gates remain separate obligations.
