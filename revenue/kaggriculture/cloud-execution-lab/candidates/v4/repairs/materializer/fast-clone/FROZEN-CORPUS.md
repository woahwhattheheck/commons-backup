# Independent frozen clone corpus gate

This closes the missing-corpus item in the existing fast-clone recovery. It does not install either donor into the production runtime and does not create another V4 mechanism.

From the repository root, run:

```sh
V4=revenue/kaggriculture/cloud-execution-lab/candidates/v4
CLONE="$V4/repairs/materializer/fast-clone"
python -I -B "$CLONE/verify_frozen_clone_corpus.py" \
  --hardener "$CLONE/harden_v4_fast_clone_recipe.py" \
  --helper "$V4/repairs/performance/fast-tape-clone/r04_fast_tape_clone.py" \
  --tapes "$V4/donor/overlay/r01_tapes.py"
python -I -O -B "$CLONE/verify_frozen_clone_corpus.py" \
  --hardener "$CLONE/harden_v4_fast_clone_recipe.py" \
  --helper "$V4/repairs/performance/fast-tape-clone/r04_fast_tape_clone.py" \
  --tapes "$V4/donor/overlay/r01_tapes.py"
```

The verifier checks the exact Git blob of all three inputs before loading anything. It extracts the hardener's literal helper without executing the hardener script; no legacy materializer, production entrypoint, workflow or submission is executed. Changed input bytes require a new reviewed receipt, not removal of the pin.

The recorded normal and optimized runs each cover both existing helpers: all 13 x 719 = 9,347 frozen actions, zero fast-shape fallbacks, one detached-output mutation witness per action, 25 future-schema cases, and two intentionally broken clone controls. Comparison includes value, exact type, dictionary order, mutable detachment, internal alias graphs, cycles and custom attributes. Clone-only median speedups over deepcopy were 2.094x / 2.091x for the hardened materializer helper and 2.873x / 2.782x for the preserved performance helper. Both exceeded the historical 1.50x clone gate; timings remain machine-specific microbenchmarks.

## Convergence and remaining gates

Keep one production copy mechanism, not the unkeyed recipe plus the keyed performance port plus another recovered key. This worker retired its separate c562352 / baff20f / 0176263 local port in favor of the already-preserved implementations. The two existing source families retain their distinct provenance and wiring contracts; this shared verifier establishes helper equivalence, not permission to stack them.

The current production ABI differs from the legacy R04 materializer. Exact current-ABI composition, materialized package/checker tests, whole-agent timing and game gates remain open. The historical receipts in MANIFEST.json are retained verbatim; the independent_frozen_corpus section and FROZEN-CORPUS-RECEIPT.json supersede only the missing frozen-corpus blocker.
