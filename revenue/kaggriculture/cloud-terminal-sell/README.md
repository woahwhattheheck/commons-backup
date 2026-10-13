# T05 × frozen SELL — OSPREY

A complete native agent and independent interaction experiment. It supplies RELAY-CI's frozen final-day routes to the unchanged selected SELL scheduler **before** the scheduler's one action pass. No T05/T08 source or shared selected entrypoint is modified.

## Use

Import `composition.py` from this directory. Construct `policy = composition.TerminalSell()` once per game, then call `action = policy.act(observation, configuration)` once per turn. The `agent` function resets its instance at decision0. `main.py` is the native raw-file entrypoint and accepts the loader's `configuration['__raw_path__']`; it does not require `__file__` in raw execution globals.

`policy.owner.contract()` returns a detached current selected action, remaining worker queues, and phase-aware own-state snapshots. **The contract's selected_action is the terminal reference action before SELL adjusts market orders. The return value of policy.act is the actual complete action.** Unit actions are identical; consumers must not treat reference market orders as already executed sales.

Before698, controller state/action and the route supplied to SELL remain exactly the frozen control. From698 through718, the same parent is called once, the stateful T05 planner selects current unit actions, and an isolated clone projects its remaining queues. Empty queues become capacity-admitted DROP/PLACE eligibility, not unconditional cargo arrivals. Future reference routes are available through `owner.R[owner.cur]`; no second parent is created or invoked.

## Conditional model, not joint optimality

The planner's future reference sales provisionally release shed space. Unchanged SELL then replays the route with enlarged projection capacity and subtracts each candidate sale at its actual phase; a future before-market arrival cannot be rescued by a sale later that turn. Actual deposits are recalculated against the observed shared shed on every real call.

The bridge does not rerun T05's deposit-selection dynamic program for every speculative SELL candidate. Its obligations are conditional and can conservatively reject a withholding plan that a different future admission choice could accommodate. It uses current observed quotes for the reference deposit choice, not future rival orders or unknown quotes. It is neither an exact joint optimizer nor a general producer-reservation API. Never combine another worker-routing overlay by simply replacing its unit actions afterward.

## Execute and reproduce

Use an existing Commons source checkout and the existing pinned official engine cache. This creates isolated cloud native bindings and compiles the original Apex opponent; it downloads nothing.

```sh
python revenue/kaggriculture/cloud-terminal-sell/prepare.py --repo . --runtime /tmp/osprey-runtime --terminal
OSPREY_ENGINE_DIR=/path/to/engine/engine sh -c 'cd revenue/kaggriculture/cloud-terminal-sell && python -m unittest -v test_composition.py test_panel.py'
python revenue/kaggriculture/cloud-terminal-sell/measure.py --repo . --engine-dir /path/to/engine/engine --runtime /tmp/osprey-runtime --arm composed --opponent baseline --seed 9860001 --seat 0 --output /tmp/osprey-runs/composed-9860001-baseline-0.json
python revenue/kaggriculture/cloud-terminal-sell/panel.py /tmp/osprey-runs --compare sell composed --output /tmp/osprey-summary.json
python revenue/kaggriculture/cloud-terminal-sell/build.py /tmp/osprey-export
```

Supply both arms before summarizing. Arms are `baseline`, `sell`, `t05`, `composed`; opponents `baseline` and `apex`; seats0/1. Full experiment sets are dev9860001/9860019 and held9860101/9860119. These seeds are now consumed, not unused holdouts for subsequent policies. Use a new output location; never overwrite retained records. Both the setup and exporter require fresh destinations. The full test run above includes an actual official-engine comparison; omitting OSPREY_ENGINE_DIR explicitly skips that one test.

Existing reusable source transport: artifact10030763484, source7f92f6c0f4e3961be8109b2e3dc6da3e4e356d9f, ZIP SHA256 `68f78694fa56976fa1476ffd1d1fb6b3bfd4935392dfd0023a170c7efcd35e62`. Engine artifact10005621438, ZIP SHA256 `06e526df0a87d1d94e60dd0f2ea380aa099a4f0edd40a604a7c5bd274bd189cc`. Both were reused and all88 source members verified; no new transport workflow was run. This directory supplies the later bridge and exact vendored T05 dependency. The engine pin is Kaggle/kaggle-environments@28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c.

## Results and artifacts

See RESULTS.md and scores.csv for all64 official-engine score records, SOURCE-FREEZE.json for the pre-held runtime freeze, and EXPORT-RECEIPT.json / EXPORT-PARITY.json for the reproducible standalone package. Twenty-six tests pass. The64-game raw archive is retained separately in the originating Chat session; RAW-SHA256SUMS.txt commits its per-file identities, not the observation payloads themselves. No additional independent wins are counted for the two source/export packaging checks.

The existing shared TITAN selection is unchanged. All execution stayed in cloud compute; no Kaggle upload, hosted rating claim, new spend, or owner-PC execution occurred. New bridge code is MIT; unchanged T05, SELL, mechanics, receipt math and Arlene retain Apache-2.0 notices and licenses. Existing opponent/engine licenses remain intact.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
