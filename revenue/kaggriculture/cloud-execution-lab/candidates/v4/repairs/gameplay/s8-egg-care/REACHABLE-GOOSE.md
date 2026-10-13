# Reachable three-goose S8 acceptance fixture

**Status: built and executed locally; NOT posted to Slack, committed, merged, or promoted.**

This is additive test infrastructure for the existing
`main:revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/gameplay/s8-egg-care/`
package. It does not introduce another TITAN controller, runtime feature, V4 branch,
production archive or Kaggle submission. The sole S8 implementation remains
GOSLING's `compose_reopened_s8.py`; HENHOUSE retains native engagement and field
integration, and GOOSE retains the independent engine lifecycle oracle.

## Why this adds evidence

The native tape's animal work often already uses CARE or has no eligible surviving
hour-23 collection. This support fixture buys and services THREE real geese using
the unmodified official startingMoney=3000. It adds a standard-bankroll,
multiple-producer capacity/harvest test, rather than another care helper or a
single-animal experiment funded with an enlarged starting bankroll.

Every animal, wheat unit, fertilizer unit, egg, sale and dollar comes through the
pinned official interpreter. The fixture does not mutate a mature animal, preset
private inventory, change market parameters, inject cash, leak the episode seed,
or replace interpreter functions. Its only changes to framework state are the
normal step/remaining-time fields and agents' submitted actions.

This is a **designed reachable test-grower**, not native TITAN or a competitive
opponent benchmark. Its objective is activation and causal attribution, not score.

## Executed results

Python 3.13.5; normal and `-O`. Four fixed development seeds (17, 101, 6607,
9922999), both seats versus the pinned official starter, two legal storage regimes,
five arms, two execution modes: **160 completed games**, each with 719 callbacks.
That is 115,040 action-turn interpreter transitions plus 160 initializations for
the saved panel alone. Unit/fault tests and exploratory runs are separate.

| Standard-cash full-shed seed | Seat 0 margin delta | Seat 1 margin delta | Extra eggs per candidate game | Lost retained FERT |
|---|---:|---:|---:|---:|
| 17 | +577 | +577 | 11 | 0 |
| 101 | +606 | +606 | 11 | 0 |
| 6607 | +530 | +530 | 11 | 0 |
| 9922999 | +560 | +560 | 11 | 0 |

Mean margin delta is +568.25 **in these eight paired fixture cells**, not an
estimate of native field strength. Opponent cash delta is zero in each cell.
Every extra egg is separately observed reaching the tile, being harvested, and
being sold. All eight candidate games substitute eleven genuine hour-23
COLLECT_FERTILIZER rows. The shed holds 100 units at every substitution; egg prices
are below fertilizer prices, isolating the shared helper's discard path rather
than crediting the risk-bearing spread heuristic. All geese remain alive and each
arm actually consumes 90 feed wheat. Residual shed stock is sold before callback718.

The ordinary-storage regime supplies 26 physiological opportunities per baseline
game, but the exact candidate changes **zero** actions, states or scores in all
eight paired cells. This is an unexercised economic trigger, NOT a rejection of S8.
The identity control has exact whole action/state/environment/cash trace parity in
both regimes. All 80 per-mode game records and paired comparisons are equal
between normal Python and `-O`.

Test-only discriminators are explicitly NOT S8: free CARE replaces an idle PASS;
a collection ablation replaces COLLECT with PASS. At seed17 in the full-shed
regime, free CARE makes 13 extra eggs and +670 margin; the ablation loses four
admitted fertilizer units and 380 margin. These controls show why future egg
realization and retained-input opportunity cost both matter.

26/26 acceptance tests pass in each mode. Six broken fixture/measurement variants
are assertion-rejected in each mode: disabled positive control, harvest requests
miscounted as units, omitted terminal liquidation, removed input-mutation guard,
suppressed opportunity recording, and own cash mistaken for relative margin.
The mutation runner first requires the unchanged 26-test gate to pass; import,
setup, timeout or test errors receive no rejection credit.

## Reachable trajectory and scope

Day zero executes BUY GOOSE/WHEAT, PICKUP, BUILD_COOP, PLACE at (4,4), (3,4),
(4,3), then real FEED. All three placements happen before the first weed refresh.
The subsequent daily tape feeds, harvests and collects, and sells actual deposited
output. The ordinary regime buys three wheat for the following day.

The full-shed regime requests enough wheat to fill unused storage; only actually
affordable official fills count. Standard starting cash does not fill the shed
immediately: the first full-shed physiological opportunity is day6 on seed17.
Before the following harvest DROP, an actual WHEAT sale creates the necessary
space; therefore the extra egg is not silently discarded. All arms use the same
observation-driven grower and configuration; the candidate changes only its final
farmer CARE row, never the grower's market rows.

The runner rejects observation/action/config mutation, incompatible timing,
route drift, absent geese, undeclared actor/market changes, capacity assumptions
that fail, duplicate seeds, candidate digest mismatch, changed native input
members and incomplete episodes. Full state/environment traces are hashed after
every actual interpreter call. This is trusted-source in-process execution, NOT
an adversarial-code sandbox, hosted evaluator or deadline/worker-thread proof.

## Exact source custody

- Native input archive: `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`.
- SOURCE.json: `e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2`.
- All 109 listed native members are authenticated before imports. The tar has
  those members plus SOURCE.json: 110 files, NOT 110 agent modules.
- Official engine ref: `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`;
  engine Git blob `3c202c7ee921da239356789e266b694635103fc4`.
- Existing S8 donor Git blob: `30a0e05c0cd7a435a59316d9d070da59eb2bb865`.
- Existing GOSLING composer Git blob: `7cc261b907e377961e204c47d594cf3cfc85663c`.
- Locally generated candidate Git blob: `8591f8208b35a7ffc6547385ca72244f423a44a2`;
  SHA256 `86be29534c8cfedef7d0b13043ec86586632b40eac2b16084dd1a9b6ac06d213`.

The generated blob was materialized from the two authenticated main sources; it
was NOT successfully fetched as a remotely stored Git blob. Both source blobs and
the generated hash match the owner's advertised values. This fixture exercises
`apply_egg_care(..., enabled=True)` with the source's `spread_or_discard` default;
the recorded firing cells all use the discard condition. The spread mode is NOT
validated as safe by this receipt, and all production defaults remain untouched.

## Reproduction in the existing cloud workspace

Let `P` be this existing S8 package and `RUNTIME` the extracted checked-release
archive. No legacy R04 materializer is invoked. Do not point composition output at
a production file; the owner's composer uses exclusive creation.

```sh
python "$P/compose_reopened_s8.py" --donor "$P/s8_egg_care.py" --output /tmp/reopened_s8.py
python "$P/test_reachable_goose_setup.py" --native-root "$RUNTIME" --candidate /tmp/reopened_s8.py
python -O "$P/test_reachable_goose_setup.py" --native-root "$RUNTIME" --candidate /tmp/reopened_s8.py
python "$P/run_reachable_goose_gate.py" --native-root "$RUNTIME" --fixture standard_cash_fullshed --candidate /tmp/reopened_s8.py --candidate-sha256 86be29534c8cfedef7d0b13043ec86586632b40eac2b16084dd1a9b6ac06d213 --output /tmp/reachable-fullshed.json
python "$P/run_reachable_goose_gate.py" --native-root "$RUNTIME" --fixture ordinary --candidate /tmp/reopened_s8.py --candidate-sha256 86be29534c8cfedef7d0b13043ec86586632b40eac2b16084dd1a9b6ac06d213 --output /tmp/reachable-ordinary.json
python "$P/run_reachable_goose_mutations.py" --native-root "$RUNTIME" --candidate /tmp/reopened_s8.py --output /tmp/reachable-mutations.json
python "$P/run_reachable_goose_mutations.py" --native-root "$RUNTIME" --candidate /tmp/reopened_s8.py --optimized --output /tmp/reachable-mutations-O.json
```

Repeat the two panel commands with `python -O` for complete mode parity.
`REACHABLE-GOOSE-PANEL.json.gz` contains ALL FOUR complete raw report objects;
`REACHABLE-GOOSE-FAULTS.json` retains baseline and failed-mutant logs, not just
claimed counts. SHA identities and the exact execution limitations are in
`REACHABLE-GOOSE-VALIDATION.json`.

## Integration boundary

Eight additive files only, in this SAME S8 package. No donor, composer, native
source, config, canonical ledger, production archive, workflow, or remote ref was
modified. There is no new source claim in Slack: the session's exposed GitHub and
Slack tools were read-only. The companion patch is LOCAL and NOT merged; no claim
of peer delivery or CI execution is made.

Current-native reachability, exact composed runtime lifecycle/receipt coherence,
budget handling and a strong opponent field still belong to their existing
owners. This result supplies a standard-bankroll legal positive fixture; it does
not authorize activation, label a zero-fire native panel as a kill, or replace the
single native composer.
