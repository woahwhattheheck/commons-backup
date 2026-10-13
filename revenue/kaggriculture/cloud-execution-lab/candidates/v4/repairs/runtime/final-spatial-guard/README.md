# #12019 current-ABI final SpatialTempo guard

Operation: `TITAN-V4-12019-FINAL-SPATIAL-GUARD-CURRENT-ABI-20260919-01`

This is the current-source redrive of the historical final-pressure idle-fertilizer ledger rebind. It is a repair carrier inside the existing V4 repair tree, not a sibling V4 root and not independent promotion authority.

## Live defect

The canonical wrapper already lets `SpatialTempo.guard_returned()` validate an idle-FERT `DROP` plus unique `SELL FERTILIZER 1` before the wrapper's late market finalizers. The wrapper then permits final pressure, town procurement, and overflow preservation to alter the returned market bytes. `SpatialTempo.finish()` commits afterward using `_sale_proposal['slot']`. A valid late reorder can therefore leave the proposal bound to a stale slot and lose the ledger receipt even though the engine-facing sale executes.

The current shared guard already owns the safe semantics needed for the redrive: it accepts only the current proposal, requires the paired DROP when a worker is bound, requires exactly one exact `SELL FERTILIZER 1`, rebinds the proposal to that final slot, and fails the paired action closed when the lot is missing or ambiguous.

## Current-ABI repair

After every existing late market transform, and only on a completed producer result, call the same `spatial.guard_returned(obs, returned)` once more immediately before `_early_capital_selected()` returns. Checkpoint those fully guarded bytes as `spatial_final_guard`.

This placement is deliberately after pressure/procurement/overflow and before the outer runtime can call `SpatialTempo.finish()`. Deadline fallback does not start this additional guard.

## Source custody

The carrier is bound to exact Git blobs:

- `main.py`: `727c36ee3727db159f5879d4ac9a842a28ca570c`
- `spatial_tempo.py`: `a2f13cd9871e6da24b2ccf3297c4c96ac324100e`
- serial base used for this recovery: `7c3b010b77f1fe16fdeffb5a4601504a284c616a`
- unchanged materialized candidate: `bb3a044aedefa36dcdc5d933ca396fefbf1d9fdd`, 30,367 bytes

Any source drift fails closed before materialization. Both source identities are checked again before a success receipt is emitted. This is a source-copy tool, not an installer.

## Output nonmutation fix-forward

The original #16088 materializer (`fa953f7b3fcf1901b444ad235052b06f0aa95b97`) compared resolved pathnames before calling `write_bytes`. A distinct hardlink to either pinned input could therefore overwrite that input; the CLI also replaced its optional receipt destination. The predecessor was reproduced using only disposable synthetic fixture bytes. Original #12019/#16088 source, design, and six current-ABI contracts retain their attribution; ZZ-PALISADE-T4Q9 contributes this output-handling correction and its regression tests.

Candidate and receipt must now be distinct, nonexistent paths outside the resolved source tree. Existing files, directories, hardlinks, symlinks (including dangling ones), and receipt/candidate aliases are refused. Both destinations are preflighted before candidate creation; exclusive `xb` creation also refuses a file or link appearing between preflight and open. Existing output bytes are never intentionally replaced, and success is printed only after the requested receipt is written and read back.

The two output files are **not an atomic transaction**. A later I/O error or concurrent source change can leave a newly created candidate without a success receipt; retain it for inspection or retry with fresh paths. The tool does not delete such files or represent the partial attempt as completed. Use a caller-controlled output directory: this narrow nonreplacement contract does not claim safety against hostile concurrent replacement of ancestor directories, concurrent writers after an output is created, or hardlink creation after exclusive open. No broader filesystem confinement claim is made.

## Contracts

`test_current_abi.py` proves:

- the exact current source identities;
- the literal current predecessor loses the ledger slot after a late FERT/CARROT reorder;
- the candidate rebinds to the final returned slot and checkpoints those bytes;
- a duplicate final fertilizer sale fails closed together with the paired DROP;
- no proposal is identity-equivalent; and
- deadline fallback does not start the new final guard.

`test_materialize_outputs.py` adds 30 disposable-fixture contracts for candidate/receipt nonreplacement, canonical-tree exclusion, path aliases, leaf creation after preflight, source reauthentication, failure receipts, CLI behavior, and repeat execution. It uses real source hash checks and output I/O but a synthetic patch; it does **not** substitute for the six production-source contracts above. The existing `source-parses` workflow runs both suites in normal and optimized Python 3.11/3.12 without adding a workflow slot, then materializes the real pinned candidate and checks source nonmutation.

Run from this directory, using a fresh external directory on every invocation:

```bash
python -B -m unittest -v test_current_abi.py test_materialize_outputs.py
python -O -B -m unittest -v test_current_abi.py test_materialize_outputs.py
out=$(mktemp -d)
python -B apply_repair.py --tree ../../../../../../../.. --output "$out/main.final-spatial-guard.py" --receipt "$out/final-spatial-guard.json"
python -m py_compile "$out/main.final-spatial-guard.py"
```

Composition into canonical `main.py` requires the one-tree queue; this carrier itself changes no runtime/config/CURRENT/CANONICAL/COMPOSITION/INTEGRATION/archive/release/Kaggle/ref state.
