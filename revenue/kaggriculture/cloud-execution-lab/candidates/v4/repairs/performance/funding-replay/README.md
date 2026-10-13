# Funding replay: exact reuse and owner-lifetime composition

This is a source-composition package for the single V4 on `main`, not a new
controller, policy key, production archive, or successor V4 tree.

## Changes

`apply_funding_replay.py` changes four exact native `frozen_selected.py`
function spans and adds one private disposal helper. It reuses `MarketPath`
quote/single/joint caches inside one `fund_same_turn_acquisition` call. Scalar
price-parameter snapshots invalidate a model even when a rival callback edits
an existing parameter dictionary. Custom parameter mappings take the uncached
path. No cache crosses a funding search or observation.

`funded_minimum_now` runs one trace, rather than two identical traces, only when
the rival inventory draw is zero or the actual bounded raw market prefix has no
`BUY_PRODUCT` row that receives that draw. The two-entry certificate remains.
Live product-buy stress still executes both scenarios. `_funding_trace` itself,
quantity enumeration, order indices, sale quantities, callbacks, barriers,
ranking (including the incumbent positive remaining-cash sign), fallback
reports, and `FrozenSelected.transform` are unchanged.

The pool also consumes ASTRA-CACHELIFE's owner-disposal protocol: clear the
three caches and delete the bound `single`/`joint` wrappers. A borrowed model is
never disposed by its receipt. Parameter-version replacement disposes the old
model; a whole-search `finally` disposes the remaining pool; standalone
receipts dispose their own model on return or exception. There is no production
GC configuration change.

## Source custody and reproduction

The executed fixture is the complete existing Actions artifact `10175943272`,
not a reconstructed collection of selected source files. Its ZIP SHA256 is
`3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8`.
Inside it, `checked-package/exports/titan-current.tar.gz` has SHA256
`b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`.
Extract that archive to `$B567`; do not use the artifact's older variant folders.

`INPUTS.json` binds `SOURCE.json` by SHA256, then the gate checks every one of its
109 runtime entries before importing anything from the runtime or invoking the
literal pinned official interpreter. Missing files are rejected, not downloaded.
Python 3.13.5 executed the recorded tests. No third-party packages are needed.

```sh
python check_funding_replay.py --runtime "$B567" --benchmark --output normal.json
python -O check_funding_replay.py --runtime "$B567" --benchmark --output optimized.json
python check_funding_cli.py --runtime "$B567" --output cli-normal.json
python -O check_funding_cli.py --runtime "$B567" --output cli-optimized.json
python apply_funding_replay.py "$B567/frozen_selected.py" /tmp/frozen_selected.composed.py
```

Native input: git blob `fc7baf5c179818a55037f6a61d92984d81d1a21c`, SHA256
`5ca1bc39efed756de71207f46926744ea69f9d2f300dd7b9c1a8cc4dbefeb9ef`.
Composed output: git blob `fe2dcff5f4a204e48577e781812052c266f9026e`, SHA256
`ec8bed351f15603f69a899d7e2e4412603c422eb991930e2da2bd5f91da1d170`.
The CLI refuses in-place source writes. Changed, mixed, missing or duplicated
required function spans fail before any output write. Applying the complete
repair twice is idempotent. Unrelated source text is preserved byte-for-byte.

## Executed evidence

Each of normal and `-O` passed 27 focused tests, 8 inherited tests run inside the
focused suite, and 4 separate real-process CLI tests. Each mode performed 1,296
receipt comparisons, 1,000 complete same-turn funding comparisons (65 engaged),
900 minimum-sale comparisons, 160 malformed-input comparisons, 48 raw-prefix
stress controls, 32 unmocked full `FrozenSelected.transform` comparisons, and
72 both-seat full official-interpreter transition pairs (144 interpreter calls;
54 pairs actually reordered funding). Outputs, diagnostics and input
immutability are compared, not just final cash.

Five deliberately broken variants are rejected behaviorally: unconditional
stress skipping, stale parameter reuse, removing a certificate entry,
clear-only owner disposal, and premature borrowed-model disposal. Actual CLI
processes reject six missing and six changed dependencies in each mode.
Composition controls include 64 unrelated peer edits and repeat applications,
16 changed/mixed/missing/duplicate method cases, and disposal-helper guards.

Eight success-path searches retain 40 predecessor model owners versus zero
candidate owners with cyclic GC paused only within the test. Candidate owners
also release on standalone receipt, quote-error and rival-callback-error paths.
Both exception controls require all eight injected cuts to occur.

Alternating AB/BA microbenchmarks use nine samples of 20 calls per arm and
validate every returned result. Recorded normal / `-O` speedups are about
3.00x / 3.01x for repeated-sale-prefix search, 1.40x / 1.40x for an 80-unit
floor-price search, and 1.75x / 1.76x for a fixed-buy minimum. The live-product-buy
control is about 0.97x / 0.99x: it incurs a small scan overhead and deliberately
retains both stress simulations. Raw timings, ranges, pins and commands are in
`RECEIPT.json`; these are constructed function benchmarks, not whole-agent
speed or natural-game strength measurements.

## Single-V4 integration and limits

Only the existing native composer should consume this repair. Do not run the
legacy r04 materializer. A peer edit inside one of the four owned methods needs
an explicit combined rebase and fresh tests; the method pins refuse a silent
overwrite. Scheduler, pricing-kernel and selected-core optimizations remain
with their existing owners and require combined-stack measurements.

The per-receipt CACHELIFE experiment was withdrawn in favor of this
pool-aware ownership boundary. Coordination and explicit agreement are in
Slack thread `1789180616.027249`, especially reply `1789181134.044749`.
Funding source claim and measured handoff: `1789180475.694699`.

This package does not change acquisition semantics, fix existing raw-prefix or
ranking decisions, certify a deadline-interrupted trace, or establish Kaggle
rating/EV. No production source/default/archive, Actions dispatch, or Kaggle
submission is changed by publishing this package.
