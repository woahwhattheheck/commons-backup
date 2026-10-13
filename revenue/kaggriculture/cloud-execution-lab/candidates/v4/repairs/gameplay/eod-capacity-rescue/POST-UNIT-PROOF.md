# Post-unit EOD component proof

**Supplemental component evidence, not a competing native caller.** The live
mixed-product return-boundary port documented in `NATIVE-README.md` retains
ownership of native integration. This packet evaluates only the single-product
post-unit component in `native_eod_capacity_rescue.py`; its zero-engagement result
does NOT evaluate or reject that mixed-product native port.

Status: component verified; zero engagement on the declared starter panel;
not wired into production; default OFF. All files remain in this existing V4
repair package. Existing donor, caller-composer and market-externality work are
preserved. No config key, production controller, archive, legacy materializer,
or Kaggle submission was added or changed.

## Phase and actor semantics

The component uses exact current `scheduler.post_units`, not pre-action cargo,
legacy router imports, or a potentially stale selected-action snapshot. If the
post-unit shed total is S <= 100, all carried cargo is one known product with
quantity T, O = S + T - 100 > 0, and the shed contains at least O of that same
product, append SELL O after the original shed-neutral market prefix. EOD
backfills that product, preserving own post-EOD private shed and cargo state.
This private-state result is not a public-market or competitive-EV theorem.

This admits actual HARVEST/COLLECT_FERTILIZER output, subtracts FEED/FERTILIZE
consumption, accounts for partial PLACE and rejects cargo already discarded by
premarket DROP. Omitted actors retain cargo. Extra nonexistent actors cannot
act but their PLANT rows still count in the official atomic-demand check. The
complete raw command list is projected; inventories bind to actual actors.

A real parent quirk at step143 emitted five hand rows for four hands. The
component and full-engine tests now handle that exactly. No production actor
sanitizer was changed. A future approved composition belongs before the
finalizer/history receipts, under the existing native integration owner.

## Executed evidence

The exact b567 canonical archive is 429,604 bytes; its literal entrypoint is
4a8cf7, runtime b952, scheduler a483 and mechanics 044a. Full source identities,
commands' inputs, compact per-game rows and local raw-output hashes are in
`POST-UNIT-RECEIPT.json`.

- 19/19 tests in normal Python and 19/19 optimized. Each mode executes 411
  candidate checks and 256 full official-interpreter differential pairs, across
  nine products, both seats, actor orders, inventory boundaries, market budgets,
  neutral purchase prefixes, rival quotes and the terminal boundary.
- Seven intentionally broken variants rejected in each mode. The mixed-cargo
  witness funds both possible selected products so hash/set order cannot hide a
  missing guard. The original donor was not mutated.
- Literal unmodified `main.py::agent` versus official deterministic starter,
  seeds9120701+9120702, both seats: four complete games, 2,876 callbacks and 116
  usable EOD callbacks PER MODE. **Zero component activations.** All parent calls
  completed; normal/optimized action+diagnostic hashes match in every cell.
  EOD skips are 55 not-single-product, 49 existing stock-changing/unknown market
  prefix and 12 no-overflow. The other 2,760 calls are not usable EOD boundaries.

Mature-WHEAT fixtures recover five or six units depending on WATER/HARVEST
order; fertilizer collection recovers one. These are synthetic witnesses, not
observed field profit. The starter panel is not opponent-diverse economics.
**NO PROMOTION of this component on this panel.** Do not transfer that verdict
to the separate mixed-product native port, or infer zero opportunity everywhere.

## Reproduction

Set `TITAN_RUNTIME_ROOT` to the unpacked canonical b567 archive. From this repair
directory run each command using both `python` and `python -O`:

```sh
python test_native_eod_capacity_rescue.py
python check_native_mutants.py
python census_native_eod.py --seeds 9120701 9120702 --seats 0 1 --output CENSUS.json
```

The gate verifies dependency Git blobs and the existing offline loader verifies
all official engine files. No network or legacy materialization is used. The
census calls the literal entrypoint but never executes the candidate action. It
writes the local plan before execution and complete EOD action/state rows to the
chosen output. Raw-output Git hashes in the receipt are calculated identities,
not a claim that those raw blobs were published; the committed receipt retains
compact observed results and the runner reproduces detailed output. This was
local execution, not an externally preregistered or hosted run.
