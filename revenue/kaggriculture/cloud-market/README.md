# Lean20 farm manager and frozen-source strategy study

**Use `main.py` for the runnable standalone candidate.** It exports
`agent(observation, configuration=None)` and imports only Python's standard
library. Its exact SHA-256 is
`d9487c031b50ede06a706acc8bcb40e0b5a681d9b5e92c1a1a96492b26c2dd62`.

Built directly on Euler's published device-team work, it limits the herd to
20 animals and eight hands without buying additional land. All other executable
farm-manager logic is preserved. In the predeclared reserved validation, it beat
Euler28 in 15/16 games and frozen compact22 in 15/16, with positive mean margins
of 3,202.125 and 2,713 in-game coins. The two losses remain in the report.
See [ECONOMICS.md](ECONOMICS.md) for complete results, rejected experiments,
source attribution and limits. This is not hosted Kaggle ranking or prize money.

## What is preserved

The accepted package under `../20260907-offline-agent/`, its original incumbent,
prior measured results, source loader and root's working competition submission
remain untouched. This is an additive candidate, not an automatic replacement.
The study consumes exact published source and `ECONOMICS.md` from Commons commit
`c57fc2962d7a0da5109162f0b6a267967c3a616e`; it does not access Bryce's physical disk.
Each frozen source is checked against its Git blob ID and recorded with SHA-256.

The prior long-horizon, marginal-lifetime and same-tile-bonus experiments remain
in the original package. Eight new declared candidates test compact staffing,
capacity, care headroom and travel distance. Every candidate is generated as a
complete standalone; none imports a changing live policy at runtime.

## Reproduce in ephemeral cloud storage

Python 3.11+ on Linux, standard library only. Do not create these build/cache
files on Bryce's machine. Preparation is the only networked phase.

```sh
cd revenue/kaggriculture/cloud-market
python -B study.py prepare --root /tmp/kag-study
python -B test_study.py
KAG_STUDY_ROOT=/tmp/kag-study python -B test_behavior.py
python -B study.py development --root /tmp/kag-study
python -B study.py validation --root /tmp/kag-study
python -B diagnostics.py --root /tmp/kag-study
cmp main.py /tmp/kag-study/selected_main.py
```

Development uses seeds 733, 2801 and 8191, both seats, against frozen Euler28
and original compact22. Selection maximizes the smaller opponent mean margin,
then the overall mean and candidate name. Only those selected bytes advance to
validation on 1237, 4421, 10007, 32771, 65539, 131071, 262147 and 524287, both
seats, additionally against incumbent36 and the official starter. Validation
results never feed back into selection. `selection.json` records the delivered
choice and links its original evidence artifact.

The focused Actions workflow prepares source, then runs 25 evaluator tests,
10 study tests, seven behavior/source tests, 96 development games, 64 validation
games, four opponent-specific replays and eight diagnostic equivalence games.
It verifies that committed `main.py` equals the selected artifact. Execution is
inside a network-disabled Docker container, with a read-only source mount,
1.6 CPU and 6.5 GiB memory limits. Source snapshots, runtime image, all game
records, tests and a licensed `delivery/` package are retained in the artifact.
On main, the workflow also verifies integrated source readback.

## Interrupted runs and comparison integrity

Every game result, including failures, is fsynced to an append-only journal.
Interrupted runs resume with the same full source/runtime/settings contract;
only a torn final journal record is removed. Complete corrupted records,
duplicate game IDs or changed contracts are errors, not silently mixed results.
Do not run two writers on the same journal concurrently.

Both seats form one seed cluster for descriptive bootstrap intervals. Failed
games are never counted as wins. Replays check scores plus action/final-state
hashes, and are excluded from win totals. `diagnostics.py` adds daily herd,
inventory, prices, care backlog and requested movement/trade counts without
changing the interpreter. Requests are not assumed successful trades.

The existing KAG-EVAL driver's strict one-second RPC limit does not emulate
Kaggle's overage-time bank; see `../cloud-eval/README.md` for its limitations.
These are controlled official-interpreter experiments, not a guarantee against
unknown opponents or an external submission receipt. The existing account
workflow retains registration, public Kaggle publication and submission.

## Licensing

Owner-authored code, tests and documentation: **MIT OR CC-BY-4.0**, at the
recipient's choice, preserving the device team's dual grant. See [LICENSE](LICENSE),
[MIT terms](LICENSE-MIT.txt) and [CC-BY 4.0 terms](LICENSE-CC-BY-4.0.txt).
Attribution: Bryce Xavier Muhlnickel / TokenJunkieLabs; Euler's base implementation,
ASTRA-WORK study and continuation. Upstream Kaggle source remains Apache-2.0.
No competition data or other third-party material is relicensed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
