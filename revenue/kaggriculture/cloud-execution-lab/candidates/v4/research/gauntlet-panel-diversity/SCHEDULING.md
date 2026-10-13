# Family-stratified schedule planner

`family_schedule.py` turns a strict `titan.gauntlet.panel.v1` identity manifest into deterministic coordinates for the **existing** gauntlet. It prevents opponent-label multiplicity from becoming compute-budget multiplicity before games are run.

The planner does not execute games, choose promotion thresholds, or decide that two policies are equivalent. `panel_diversity.py` remains the family/source authority layer, old PR #12046 remains the executable/observational identity donor, and COHORT/CHAINLOCK remain result/provenance consumers.

## Contract

For each supplied seed and each cycle, every resolved family receives exactly one selected label in both seats. Labels inside a family rotate deterministically by declared rank then id. Therefore a family with five leaderboard aliases receives the same cell budget as a singleton family instead of 5x the budget.

The schedule seals an order-invariant panel-identity SHA-256 and every cell binds that digest, family, opponent id, cycle, seed and seat. Reordering the manifest or seed arguments does not change the schedule. Changing an identity/rank, seed set, cycle count or rotation does.

`cycles_for_full_label_coverage` equals the largest family multiplicity. Using at least that many cycles guarantees every resolved label appears at least once while family budgets remain equal. Fewer cycles are valid when compute is scarce; the output explicitly reports partial label coverage and `next_rotation_offset` so a later run can continue rotation without always selecting the same alias.

## Fail closed

Authoritative planning requires a complete manifest: exactly `expected_labels` rows and no unresolved identity. The published Riot table currently fails that condition because rank 17 was omitted. A preview can be generated with `--preview-incomplete`, but it is stamped `authoritative: false` and unresolved rows are not silently invented or scheduled.

## Commands

```bash
python -B -m unittest -v test_family_schedule.py
python -O -B -m unittest -v test_family_schedule.py

# authoritative once the live manifest is complete
python -B family_schedule.py opponents.json --seed 17 --seed 23 --cycles 2 --output schedule.json

# descriptive only while rank 17 remains unresolved
python -B family_schedule.py PUBLISHED-TOP30-FAMILIES.json --seed 17 --cycles 1 --preview-incomplete
```

The output is a plan for Riot's one gauntlet, not a second runner. Consumers should preserve `panel_identity_sha256`, `schedule_sha256`, and each `cell_id` beside raw results so CHAINLOCK/COHORT can verify exact schedule custody.
