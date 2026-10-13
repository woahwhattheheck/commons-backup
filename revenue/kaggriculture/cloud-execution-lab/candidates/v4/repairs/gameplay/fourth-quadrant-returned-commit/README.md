# Fourth-quadrant returned-commit and observed-acquisition repair

**Source-ready component for the ONE canonical `main:candidates/v4`. Default OFF.**
This does not modify the production root, runtime finalizer, economic admission,
configuration, current archive, or Kaggle submission. Existing native composition
owns integration. Do not make a second FourthQuadrant controller or V4 tree.

## Concrete defects and repair

The exact native `fourth_quadrant.py` (Git blob
`57ffe172a5a5ebf5b57132319731aa367b9dc7f5`) admitted a tentative plan when the
returned unit actions and total HIRE count matched. Removing BUY_LAND while
retaining HIRE could therefore commit an unevaluated return. HIRE rows past the
engine's raw cap could also veto an otherwise identical executed action. Extra
nonexistent hand PLANT rows were not checked, although the official interpreter
counts them in atomic seed demand and can block a real actor's PLANT.

`compose.py` replaces this receipt check with the full unit vector and **raw
executable market prefix**. Empty slots still consume capacity. The cap follows
the engine's `max(1, int(value))`; malformed configuration/actions fail closed.
Tentative state is consumed before validation so a rejected return cannot be
replayed into a committed plan.

A returned BUY_LAND is still only an intent. If it cannot fill, cheaper seeds and
HIRE may fill, and the old continuation's worker-position checks can pass while
the target remains LOCKED. The repair checks the next public observation before
any optional continuation: the declared quadrant and target tiles must have been
acquired after the scheduled purchase. This also covers delayed first purchases,
controller reconstruction, and dates with no worker-calendar entry. Existing
abort behavior stops optional spending and restores pristine routes. It does not
undo purchases already executed, and successful acquisition does not bypass the
existing worker-position checks.

Output module blob: `3fde47add58ff04cd768f7bf904d8f643e85cba8`.
The composer accepts only the exact native input and creates a NEW output file.
Peer drift, repeat application, existing outputs and symlinks are rejected.
Do not relax the pin or overwrite a peer-composed source. Compose the two reviewed
method changes and helper deliberately if another FourthQuadrant edit has landed.

## Reproduce offline

Set `LANE` to this directory, `PKG` to an extracted original current b567 package,
and `OUT` to a new scratch directory. No dependencies are downloaded.

```sh
mkdir -p "$OUT"
python "$LANE/compose.py" "$PKG/fourth_quadrant.py" "$OUT/fourth_quadrant.py"
python "$LANE/check_landreturn.py" --package "$PKG" --receipt "$OUT/normal.json"
python -O "$LANE/check_landreturn.py" --package "$PKG" --receipt "$OUT/optimized.json"
python "$LANE/run_controls.py" --package "$PKG" --output "$OUT/controls-normal"
python -O "$LANE/run_controls.py" --package "$PKG" --output "$OUT/controls-optimized"
python "$LANE/check_entrypoint.py" --package "$PKG" --receipt "$OUT/opening-normal.json"
python -O "$LANE/check_entrypoint.py" --package "$PKG" --receipt "$OUT/opening-optimized.json"
```

Exact source transport: existing GitHub artifact `10175943272`, ZIP SHA256
`3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8`;
inside it `checked-package/exports/titan-current.tar.gz`, SHA256
`b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`.
The entrypoint runner authenticates pinned SOURCE.json and all 109 runtime
members. The focused runner authenticates its five exact native/engine/loader
inputs before importing; it does not call the old evaluator's `play()`.

## Executed evidence and limits

Python 3.13.5: **20/20 normal and 20/20 optimized**, zero failures/errors/skips.
Each mode executes 362 complete official-interpreter calls, 328 authored-row
controller calls and 112 receipt-matrix cells. Two funded 24-callback controls
preserve actions and full state. Two deliberately unfunded 49-callback witnesses
abort at step265: original cash258, repaired259 in both seats, same shed/seeds/
land and rival farm. This is a constructed $1 mechanism witness, NOT field EV.

The exact predecessor yields 72 failed test/subtest records and four errors per
mode. All seven semantic mutants are rejected by behavioral assertions in both
modes; none is counted merely for a compile/import failure. The runner preserves
full stdout and per-control JSON when rerun.

Separately, actual `main.py::agent` executes 64 opening callbacks per mode across
original/repaired, OFF/ON, and both seats. All complete with identical raw actions
and observations. These are eight-step opening controls with ZERO quadrant
engagement, not evidence that economic admission or late-game activation works.
The focused engaged tests use the real FourthQuadrant, real generated proposals
and full official interpreter, but an explicit authored-row reader and proposal
chooser instead of the full production controller/economic admission.

The prefix receipt is intentionally conservative: even an economically harmless
within-cap rewrite may reject a tentative plan. No adversarial-market-proof,
full-game gain, natural activation rate, Python 3.11 acceptance, or current
composed-stack promotion is established. Existing engine tests do not replace
those gates. Keep `fourth_quadrant=false` until the sole integrated V4 passes them.

Claim and handoff thread: #titan-kaggriculture `1789181235.114039`.
