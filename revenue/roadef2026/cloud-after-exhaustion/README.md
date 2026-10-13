Development proposal; qualification not submitted.

This separate opt-in integration runs PRISM's critical-coordinate polishing only after the frozen candidate naturally exhausts its ordinary search, while the original allowance remains. It does not change the held package, supervisor, SEDGE, FLORA, checker, or default enablement. No native build, benchmark, cloud job, or submission was performed for this proposal.

The base is the composed candidate SHA256 `758977095f8f34263bbcd9ed043ac4ab7943f04f65fae530c78ee64787c34f8f`. The proposed source is `e8014d78f40df5546d80f0ff6f1c6bc3a97944a526d7c347eb0dcdbe77728e46` (47,011 bytes). `after_exhaustion.patch` applies exactly to that base. `main.cpp` is the resulting source; its four-argument main function is unchanged.

`FLEET_POLISH_AFTER_EXHAUSTION=1` enables the new handoff. With the variable unset or zero, ordinary search and its checkpoints remain the active path. The only natural-exhaustion marker is the existing `adaptive && stalled >= 64` stopping condition. A signal, expired allowance, or round-limit exit skips polishing. The handoff occurs after ordinary search writes its final incumbent. It reuses the same Solver, routes, load state, RNG, clock origin, allowance, and output path. It creates no second allowance or solver process.

PRISM's `rankOne()` method is reused verbatim from [PR10430](https://github.com/woahwhattheheck/commons/pull/10430), merged at `73a805e290cee36981917ac09e7ce2133f35afd7`, under `revenue/roadef2026/cloud-a-rank1`. Its 7,846-byte METHOD literal has SHA256 `ecf8ed930eae457263130984ce50d3b04a95ef5b4debd64467ff4710cd91f207`. The original SEDGE/FLORA MIT attribution remains at the top of the candidate. The new dispatch glue is separate; PRISM's optional rank-six followthrough is outside this proposal.

To reproduce the source, provide the exact frozen composed main.cpp and PRISM's pinned builder:

```sh
python3 -B build_after_exhaustion.py frozen-main.cpp \
  --prism-builder build_rank1_candidate.py \
  --output proposed-main.cpp \
  --patch proposed.patch \
  --receipt source-receipt.json
```

The builder does no networking, compilation, or execution of PRISM's script. It checks PRISM's Git blob `96d457207f1e3a63e8932a20dce8be63e4f87a1d` (SHA256 `e5a77185d7126c8e87ab5e54557d7a7ff40a918e2a14646923cc95b0f25b08d6`) and extracts its literal METHOD using Python's AST. It first reproduces the measured PRISM source SHA256 `038cffc7121f6447423d231c473af1f49e6f75d4d315bdc5c7fc2b2391f94306`, then applies the separate handoff. Output files must be fresh and distinct from inputs.

Review facts in the generated source:

- Lines 814, 892 and 898 add the natural-stop marker and handoff. Lines 788-812 implement the opt-in and skip reasons. No input filename, case identity, reference scalar, or known answer controls runtime behavior.
- Lines 650-786 contain the unchanged PRISM method. It targets the largest incumbent load coordinate, ranks that coordinate's contributing demands, and tries direct routes, deletions, single waypoints, replacements, insertions, and ordered waypoint pairs over at most seven distinct time windows. It stops after a no-acceptance pass.
- Passes/demands/pair-node defaults are 16/32/24; their explicit upper bounds are 128/256/96. Ordered pairs are at most 552 per demand by default, 9,120 at the maximum, each over at most seven windows. Single-waypoint ranking remains input-sized; no arbitrary absolute graph-size bound is claimed.
- The inherited ejection search (line 421) considers at most four first demands, six first diversions, two burdened edges, four second demands, thirteen second routes and five intervals: at most 12,480 joint route evaluations per call, plus input-sized candidate scoring. Its secondary slice is at most three seconds within the original allowance when SEDGE_MAX_ROUNDS is unset. Setting that variable disables the secondary slice; the overall deadline remains active.
- Every accepted proposal goes through unchanged move()/moveTogether() (line 266), which checks segment count, unique waypoints/endpoints, reachability and every affected transition budget before committing routes and loads together. Internal acceptance uses the inherited conservative integer six-decimal bins and descending multiset comparison (line 239). This is not equivalent to the official Decimal ordering for scientific submicro values. The unchanged official checker and comparator remain authoritative; cost is not a tiebreaker.
- `finished()` (line 94) observes the original clock and signal flag. Pass, demand, path-window, pair and waypoint-scoring loops check it. Individual DAG construction, ECMP flow calculation, multiset comparison, contributor sorting and file writes have no internal interruption point. The original allowance is preserved in source, but a strict wall-time or signal-latency bound still requires an executed measurement.
- The atomic solution writer (line 479) writes a temporary file and renames it. Ordinary search checkpoints before handoff; polishing checkpoints after each pass, with at most one accepted move/joint exchange per pass, and again at exit. A hard kill before the next rename retains the previous complete checkpoint. Stats are diagnostics, not the submitted solution.

The handoff writes stderr lines prefixed `FLEET_POLISH ` followed by JSON. Events are `begin`, `skipped`, and `end`. All include elapsed and remaining seconds; begin records cumulative pre-phase attempts/accepts, and end records phase duration plus attempt/accept deltas. Skip reasons are `signal`, `deadline`, or `round_limit`. The unchanged optional FLEET_RANK1_REPORT JSON contains per-pass records; its final counters are cumulative across ordinary search and polishing. Do not set FLEET_RANK1=1: the experimental replacement dispatch is not part of this integration.

The accompanying SOURCE-RECEIPT.json records completed source-only checks: exact base and PRISM identity, reproduction of the historical transformed hash, unchanged method bytes, repeat generation, exact patch application, and rejection of altered inputs. These do not establish native compilation, runtime bounds, default-output equivalence, or cold performance.

The first cloud trial is four strictly sequential, cold whole-portfolio runs: A04 baseline then proposal; A14 proposal then baseline. Use the same cloud machine, pinned official inputs and frozen context; record actual CPU, RAM and operating system. Keep all three lanes and change only the candidate binary and the new arm's opt-in. Use PORTFOLIO_SECONDS=585, the supervisor's original 565-second search allowance and checker reserve, FLEET_DIRECTED=1, FLEET_JOINT=1, FLEET_WAYPOINT_LIMIT=0, and default 16/32/24 polish limits. Clear CLOUD_INITIAL_SOLUTION, SEDGE_MAX_ROUNDS and inherited experimental tuning. Give each arm fresh output paths. Retain the existing TERM590/KILL600 external envelope; do not restart a finished candidate or recycle saved calibration incumbents.

The frozen supervisor SHA256 is `182371658e82f9037716e90ea8cd115622d089d02512916c7a7bf3b39fca1c63`; authoritative comparator SHA256 is `a402a0166b1e52c95dd181e15b8a124504ac78ddea7e815944c754569b323cb8`. Recheck every selected solution with the pinned official checker at six decimals and separately at twelve decimals. Compare complete descending six-decimal Decimal vectors and coordinate sets, reporting first differing rank and no cost tiebreak. Preserve both candidate-lane and portfolio-selected results: a candidate gain need not change the selected portfolio solution. Record source, binary, input, checker and solution hashes, selected lane, feasibility, wall/check durations, resource measurements, termination status, and raw phase/lane logs even on failure.

Before promotion, meaningful runtime controls should establish disabled-path equivalence on fixed-round controls, no polishing on round-limit/deadline/signal exits, and actual entry after a natural stop. Reuse the accepted segment/transition/full-vector fixtures with the new binary. A signal test must document that the candidate is still inside an active polishing phase when TERM arrives; missing the short phase is not a passing phase-specific test. Also retain a real whole-portfolio TERM control with an independently valid checkpoint, exit within ten seconds, and no surviving descendants. Record original-deadline behavior under a demanding instance. These are proposed cloud acceptance checks, not completed results.

PRISM's accepted run `34202488794` / artifact `10046558128` is warm-start evidence: A04 tied; A14's peak improved from 0.533147 to 0.517621; A16 first improved at rank 539. All three outputs passed six- and twelve-decimal checkers. Those measurements do not establish a cold integration gain, a full-vector reference tie, or competition rank. This proposal includes no workflow trigger and starts no job; the separate dispatch-only trial harness is coordinated by the root agent.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
