# KESTREL paired-game handoff

## Fixed identities

- Baseline release at lane intake:
  `exports/titan-current.tar.gz`
- Baseline content SHA-256:
  `a055fd56ca5821208096f37787f77dbdddc2f65c14c24132d6e219a05e6f02ba`
- Baseline entrypoint:
  `main.py::agent`
- Candidate source-tree entrypoint:
  `candidates/v3-kestrel-capital-execution/candidate_main.py::agent`
- Official engine:
  Kaggriculture `1.32.7`, commit
  `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`
- Candidate changes:
  only the final early-capital transform and its call binding.

Re-read all identities from the branch before execution. A changed baseline
archive, engine, candidate source, opponent artifact, seed set, seat map, or
configuration creates a new panel; do not mix cells.

## Development panel

Use the same frozen six-opponent bank and 16-seed, both-seat grid already named
by the Titan full-policy/panel owners. Expected completeness is:

```text
6 opponents × 16 seeds × 2 seats = 192 cells per arm
```

Run `current` and `kestrel` on identical cells. Never rerun only candidate
losses, only baseline wins, or any subset selected after reading outcomes.

At minimum retain for every cell:

- opponent artifact SHA and entrypoint;
- seed and seat;
- engine/config identity;
- terminal own score, rival score, and margin;
- timeout/error/invalid-action status;
- action count; and
- candidate source SHA set.

Because the mechanism is expected to activate sparsely, also retain the
candidate `early_capital` diagnostic report for every activation when the
runner supports per-step diagnostics. Missing diagnostics do not permit
dropping a completed game.

## Decision rule

Feed the complete paired artifact to the strict paired-game panel gate from
PR #11530 (or its fresh-main successor). The candidate is not promotable unless:

1. all expected cells are present exactly once;
2. there are no errors, invalid outputs, or selective retries;
3. the paired primary metric clears the predeclared improvement threshold;
4. both seats and every predeclared opponent stratum avoid the configured
   regression floor;
5. timeout behavior is non-inferior; and
6. a disjoint holdout, frozen before inspection, confirms the direction.

A semantic HOLD is a valid result. Do not weaken the gate because the source
contracts pass.

## Integration after a win

On fresh main:

1. copy `kestrel_early_capital.py` to canonical `early_capital.py`;
2. bind `TitanAgent._early_capital_selected` to
   `post_unit=self._selected_snapshot(obs, selected)`;
3. port the two focused test modules into the canonical checks;
4. run the complete existing source test surface;
5. run `python build_integrated.py`;
6. run `python build_integrated.py --check`;
7. review archive, source-manifest, receipt, and historical-archive changes as
   one atomic publication; and
8. rerun a readback smoke panel on the exact built archive.

This handoff does not authorize a hosted submission.
