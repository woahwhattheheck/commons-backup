Draft source variant; no build, trial, publication, promotion or submission.

This separate scheduler-only draft starts from exact e801 after-natural-exhaustion source. It does not change the active cold trial or the held package. Enable both FLEET_POLISH_AFTER_EXHAUSTION=1 and FLEET_POLISH_RANK_TRAVERSAL=1 to use traversal. With the second setting unset or zero, selection and no-accept stopping follow the e801 scheduler. This is a source claim; native default-mode parity has not been measured.

The scheduler partially sorts incumbent load coordinates descending, resolving equal loads by the flattened coordinate index (time * edge count + edge index). On a completed configured pass with no acceptance it advances one rank. An accepted move resets the cursor to rank 1 and recomputes ordering from the changed incumbent. The existing single pass loop supplies one shared budget: default 16, maximum 128, across all ranks and resets. Only min(load coordinate count, pass limit) ranks are selectable. An unchanged-state sweep terminates after that many selected coordinates, without cycling the final rank or calling rankOne() repeatedly. A zero pass limit performs no selection.

The original natural-exhaustion guard, ordinary search, clock, four-argument main, kernel, feasibility checks, candidate-generation/proposal/ejection body and solution writer remain unchanged. The selected pass still uses the existing contributor, waypoint, pair and time-window bounds. A signal or original deadline prevents another pass; there is no new allowance. Sorting adds input-sized work without an internal interruption point, so strict runtime and TERM latency still require actual cloud measurement. Internal conservative integer-bin acceptance is inherited; official Decimal checker/comparator results remain authoritative, including scientific submicro values. Cost is not a tiebreaker.

Traversal emits FLEET_POLISH JSON events rank_pass and rank_stop in addition to the e801 handoff events. rank_pass records zero-based pass number, one-based selected_rank, flattened coordinate, attempts, accepts and outcome. Outcomes are accepted_move, configured_pass_exhaustion, signal or deadline. rank_stop records total passes, pass/rank limits, last selected rank (zero if none), and reason: configured_sweep_exhaustion, pass_budget, signal or deadline. The optional PRISM report adds selected_rank/outcome per pass and rank_traversal/rank_limit/stop_reason at top level only when traversal is enabled. Checkpoint calls retain their original locations.

No acceptance means exhaustion of the configured pass, not coordinate optimality. Contributor limits and ejection's secondary time slice may leave proposals unexplored. The finite sweep is the root agent's new composition rule; it does not copy TRACE's twice-per-band schedule or PR10451's deepest-band cycling, and it is not PRISM's separate requested rank-six followthrough.

Source attribution, confirmed with solver_improvement:

- PRISM proposal mechanism: [PR10430 builder](https://github.com/woahwhattheheck/commons/blob/73a805e290cee36981917ac09e7ce2133f35afd7/revenue/roadef2026/cloud-a-rank1/build_rank1_candidate.py), Git blob 96d457207f1e3a63e8932a20dce8be63e4f87a1d. The complete rankOne method is no longer byte-identical because its scheduler and diagnostics change; its 3,892-byte selected-coordinate proposal/ejection region remains identical.
- Rank-order and acceptance-reset guidance: [PR10451 builder](https://github.com/woahwhattheheck/commons/blob/4b1dcaa793f9b54f13c287d766e6094f2faf4ac8/revenue/roadef2026/cloud-critical-rank-bands/build_candidate.py), Git blob 2731ac7e1e7cb90a121cd898f4c29c98e54406f8. Its band-cycling implementation is not imported.
- Explicit range exhaustion and diagnostics: [TRACE header](https://github.com/woahwhattheheck/commons/blob/3f1ee2866f21cb73988de5a82863b7f818aeb333/revenue/roadef2026/cloud-critical-bands/critical_bands.hpp), Git blob 5826c0a11480cf471316a002c45e3a4f3f9e259b. Original surrounding SEDGE/FLORA MIT attribution remains in main.cpp.

Generate fresh files without networking or compilation:

```sh
python3 -B build_rank_traversal.py e801-main.cpp \
  --output draft-main.cpp --patch draft.patch --receipt draft-receipt.json
```

The exact base is e8014d78f40df5546d80f0ff6f1c6bc3a97944a526d7c347eb0dcdbe77728e46 (47,011 bytes). The generated draft is d85ee6187607b1e04c9d77073d42e3eba699fe42309ee3f3324f25528a8f945e (50,431 bytes). rank_traversal.patch is 9d18568c3cefada7c2f3af964b863a740d5024da34ad4923f92019e1727f47f6 (7,408 bytes).

Completed source controls are recorded in SOURCE-RECEIPT.json: exact base identity, unchanged kernel/writer and proposal/ejection regions, unchanged ordinary run/guard/main, repeat generation, exact patch application and altered-input rejection. Python source generation completed; C++ compilation, scheduler execution, performance and termination tests have not run. There is no workflow or execution trigger in this draft. A cloud test decision follows the separate e801 cold result.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
