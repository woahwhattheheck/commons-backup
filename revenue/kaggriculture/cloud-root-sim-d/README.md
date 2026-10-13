# ROOT-SIM-D current-versus-v1 league shard

This additive receipt records operation `titan-root-sim-d-20260908-1345`.
It does not define another agent, evaluator, release, or submission product.

The run froze canonical archive
`499989ab907331d4c0c990af2ab3703e6731dc83078964aca8563ea5a069e48e`
(313,471 bytes; 83 runtime files) as the current controller and immutable archive
`7b58fa06da778b1519b81d509d28dff3481b3bbcc7a2d656e8bdfe4a22540524`
as the historical v1 control. Both expose `main.py::agent`. The repository source
freeze was `9ab11ca5a5d130e20ba1a87d339a1044c27fa507`; later CURRENT movement did not
change either running controller.

The exact development grid is seeds `1909081701` through `1909081732`, both
candidate seats, against unchanged Apex, Arlene, and Euler: 384 completed
full-game identities at 720 frames / 719 action calls. All controller/opponent,
seed, and seat pairs are matched. The official engine is
`Kaggle/kaggle-environments@28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.
The existing `cloud-eval/evaluate.py`, offline loader, and
`cloud-ultra-league/run_league.py` were used without policy substitution.

Apex's preserved Python entrypoint compiles its unchanged native policy on first
use when `agent.so` is absent. Eight initial step-zero attempts retained genuine
compile-time setup timeouts. Apex was then built once with the command already in
its source, and those cells were completed under explicit `setup-fixed`
identities. Two later midgame timeouts occurred while VM load spiked during two-
game concurrency; both were retained and completed under explicit serial-recovery
identities. One in-flight historical cell was interrupted when the batch was
serialized; its partial remains retained and its identity completed once in the
serial recovery. No failure was converted into a win or silently dropped.

Aggregate results are in `RESULTS.json`. Current and v1 each scored 186 wins and
6 losses across their 192 completed games. Current's seed-level paired margin
gain over v1 was positive against Apex and Arlene; Euler's interval includes zero.
These are dependent development games and do not imply a hosted rank.

The retained trajectories exposed a repeated same-target worker inefficiency,
including a mirrored Apex loss. Its exact private fixture and action were handed
to the existing QUARTZ/ELM/current-runtime integration owners rather than
publishing opponent-facing tactics or creating a new subsystem. Raw trajectories
remain in private coordination storage.

`summarize.py` recomputes W/D/L, cash, timing, and deterministic seed-level paired
bootstrap intervals from an authorized private result root. It emits aggregates
only.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
