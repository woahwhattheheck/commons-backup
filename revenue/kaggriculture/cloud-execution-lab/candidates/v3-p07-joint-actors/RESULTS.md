# P07 joint actors — measured candidate

Parent archive: `exports/titan-current.tar.gz` SHA-256
`f8f1750266b3cfaea0ebfe663f287aa9c5a2682f6fc47bc932957e1d48e63f1c`
(f8f1). Official engine `kaggle-environments==1.32.7` commit
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.

Engine file SHA-256:

| file | sha256 |
| --- | --- |
| kaggriculture.py | `bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e` |
| kaggriculture.json | `a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867` |
| utils.py | `537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b` |

## What landed

Bounded pairwise swap of complete PICKUP→service/delivery bundles at the
SpatialTempo install callsite. One continuation owner per accepted swap.
Exact rejoin of each actor's original goal. Fail-closed on hire/checkpoint
windows, cargo-masked identical positions, stock contention, collisions,
and non-improving travel.

| artifact | sha256 |
| --- | --- |
| joint_actors.py | `4ab7678d12694d693ab3f189eb2e7646eec60f0af199044c32b7da1686905521` |
| test_joint_actors.py | `9b55435fe3e8e6194ca08edbd19fd0d3851b97e8a7d0c64168afcfbfcce3970c` |
| TITAN-CONFIG.json (candidate) | `0681c500f3c7cc17f28c6722733d40cb7a460c2d65c19ce8a568a16b7533a44d` |
| spatial_tempo.py (candidate) | `2768f2d7fc2359c64ad4135ee5b165b3b8f890c97d7f772631fb6f63e9485bfa` |
| titan_runtime.py (candidate) | `b0b63e85ad7ebb19764a05ff3b6d9cd65905b60462ce56379c4a97453884018d` |

Wiring vs f8f1 is the three-hunk [install.patch](install.patch):

- `Features.joint_actors: bool = False` (default no-op)
- `self.spatial.joint_actors_enabled = bool(f.joint_actors)` before `install`
- `reconcile(...)` after `transform` inside `SpatialTempo.install.act`
- candidate config sets `"joint_actors": true`

Focused tests: **6/6 PASS** (`python -m unittest checks.test_joint_actors -v`).
The crossing-harvest fixture still saves travel 24→8 with exact end-state
preservation. Those two accepted log lines in `/tmp/v25/joint-stats.jsonl`
are the unit-test fixture (step 10, farmer `[2,4]`, hand `[7,4]`, empty
cargo), not official-engine games.

## Panels

Same process-isolated evaluator as prior v25 gauntlets. Two workers,
action timeout 15 s. Candidate seat both 0 and 1.

| panel | seeds | opponents | games | complete | fail |
| --- | --- | --- | ---: | ---: | ---: |
| smoke f8f1 / P07 | 2 seeds × v1_submitted × 2 seats | 4 / 4 | 4 | 4 | 0 |
| matched f8f1 | 2611041001–2611041016 | 6 | 192 | 192 | 0 |
| matched P07 | 2611041001–2611041016 | 6 | 192 | 192 | 0 |
| holdout f8f1 | 2611042001–2611042016 | 6 | 192 | 192 | 0 |
| holdout P07 | 2611042001–2611042016 | 6 | 192 | 192 | 0 |

Opponents: `arlene`, `apex`, `kaito_v43`, `cok_v10`, `public_bt12`,
`v1_submitted`.

Smoke mean margin was 1075.5 on both f8f1 and P07 (4/4 W).

## Paired own-cash deltas

Each cell is `(opponent, seed, candidate_seat)`. Own cash is
`scores[candidate_seat]`. Delta is P07 − f8f1.

**Matched 192/192: every own-cash delta is 0.0, every opponent-cash delta
is 0.0, zero W/T/L flips.**

**Holdout 192/192: every own-cash delta is 0.0, every opponent-cash delta
is 0.0, zero W/T/L flips.**

| opponent | n | matched d_own | holdout d_own | matched W/T/L | holdout W/T/L | holdout mean margin |
| --- | ---: | ---: | ---: | --- | --- | ---: |
| apex | 32 | 0 | 0 | 32/0/0 | 32/0/0 | 7377.750 |
| arlene | 32 | 0 | 0 | 32/0/0 | 32/0/0 | 1438.875 |
| cok_v10 | 32 | 0 | 0 | 32/0/0 | 32/0/0 | 23963.906 |
| kaito_v43 | 32 | 0 | 0 | 32/0/0 | 30/0/2 | 12485.469 |
| public_bt12 | 32 | 0 | 0 | 32/0/0 | 32/0/0 | 22871.188 |
| v1_submitted | 32 | 0 | 0 | 31/0/1 | 32/0/0 | 1057.125 |

W/T/L above is the candidate versus that opponent, identical for f8f1 and
P07 on each panel. The single matched loss is v1_submitted; the two
holdout losses are kaito_v43. P07 did not create or repair either.

Per-game rows: [matched_f8f1.GAMES.jsonl](matched_f8f1.GAMES.jsonl),
[matched_p07.GAMES.jsonl](matched_p07.GAMES.jsonl),
[holdout_f8f1.GAMES.jsonl](holdout_f8f1.GAMES.jsonl),
[holdout_p07.GAMES.jsonl](holdout_p07.GAMES.jsonl).

## Joint assignment on official games

Hour-23 (and any `changed=true`) records go to `TITAN_JOINT_LOG`
(`/tmp/v25/joint-stats.jsonl`). On the matched and holdout official
panels, **zero `accepted_pairwise_swap` records**. Live reason codes
observed at the logged hour-23 boundary are exclusively
`hire_or_checkpoint_window` (the callsite runs; the window gate refuses
to swap through hire/checkpoint cuts). Activations at other hours would
still log because `changed` forces a write. None did.

So the feature is wired and the producer still emits complete bundles,
but this conservative witness did not accept a live pairwise swap on
these 384 official games. Terminal cash identity is the measurement,
not a claim that swaps are impossible on other seeds.

## Interpretation

- Not a Kaggle submission, hosted rating, or archive promotion.
- Default runtime stays `joint_actors=false`.
- Playing strength is unchanged versus f8f1 on this matched+holdout
  matrix: exact score identity, exact W/T/L identity.
- The unit-test crossing fixture remains the existence proof that a
  legal travel-saving swap can be accepted when the synthetic route
  actually crosses.

No owner-PC work, no paid calls, no private-opponent tactics committed.
