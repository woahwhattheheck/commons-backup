# TITAN V4 gauntlet panel diversity contract

`panel_diversity.py` prevents a large opponent label count from masquerading as a large number of independent behaviors.

The live top-30 benchmark reported 31 labels (30 ranked opponents plus a mirror), but many ranked labels were explicitly mapped to the same generated archetype. Counting every label equally therefore weights a behavior in proportion to how many leaderboard names were assigned to it. This tool reports both the ordinary label-weighted result and a one-family-one-vote result. It also reports exact source aliases, family multiplicity, concentration (HHI), and the effective family count induced by label weighting.

Identity is metadata-driven. `source_id` and `family` are explicit claims supplied by the gauntlet manifest. Equal scores never make two policies the same: aggregate-equal rows from distinct sources only emit a warning. A `source_id` that is assigned to conflicting families or kinds fails closed.

## Canonical ownership

This directory is the single ASTRA-SPECTRUM gauntlet panel-identity / multiplicity contract for V4. PR #12750 landed this implementation before the later racing PR #12764. The four `replay-loss-autopsy/GAUNTLET-PANEL-IDENTITY*` / `gauntlet_panel_identity.py` files from #12764 are retired as duplicate implementation rather than maintained as a second reducer. Consumers should import or execute `panel_diversity.py` here.

The retired reducer additionally experimented with requiring literal SHA-256 source digests and a separate source-balanced layer. Those are not promoted as a second API. The current published panel maps each resolved family to a single explicit `source_id`, so a separate source-within-family weighting layer would not change this fixture. If a future authoritative manifest places multiple distinct `source_id` values inside one family, extend this canonical reducer and its tests here before treating one-family-one-vote economics as authoritative; do not revive the retired package.

`PUBLISHED-TOP30-FAMILIES.json` is a transcription of Riot's 23:19–23:21 EDT table. It intentionally leaves rank 17 unresolved because that rank was not named in the published message. The manifest still has 31 slots by representing that gap explicitly. Consequently `--require-complete` exits 3: this fixture is descriptive, not a complete authority manifest. When Riot/REFORGE publishes the missing label and current `opponents.json`, replace the unresolved row with the exact source/family identity rather than guessing it.

## Commands

```bash
python -m unittest -v test_panel_diversity
python -O -m unittest -v test_panel_diversity
python panel_diversity.py PUBLISHED-TOP30-FAMILIES.json --output PUBLISHED-TOP30-DIVERSITY.json
python panel_diversity.py PUBLISHED-TOP30-FAMILIES.json --require-complete
# ^ expected exit 3 until rank 17 is resolved; JSON output remains descriptive.
```

For game results, pass `--results RESULTS.json`. Result rows are strict `{opponent_id,wins,losses,draws,margin_sum}` records. Family-balanced economics become authoritative only when the panel has exactly the declared number of labels, every identity is resolved, and every label has a result row.

This package is gauntlet research/tooling only. It changes no V4 gameplay, default, archive, evaluator, workflow, Kaggle submission, or merge policy.
