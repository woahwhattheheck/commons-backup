# Top-agent mechanics mining

Research-only candidate-generation tooling for comparing an explicitly supplied top-agent cohort with the rest of a replay corpus. It does **not** alter gameplay, feature defaults, production runtime, archive exports, or Kaggle activation.

## Design

`mine_top_mechanics.py` reads event-level farmer-action and/or market-order CSVs and emits mechanics enriched among the explicitly supplied `--top-teams` cohort. Leaderboard membership is never inferred from event count or match volume.

Support is counted per **unique team**, not per event or match, so one prolific submission cannot dominate the ranking. Features include action/target presence, early/mid/late phase, first-day timing, early/late day presence, per-match count buckets, quantity buckets, same-step co-occurrence, and within-source/player 2- and 3-event sequences. Cross-source events are deliberately not assigned an artificial sequence order; they are represented by same-step co-occurrence instead.

The ranking reports top-team support, field-team support, support delta, and Jeffreys-smoothed team-level log odds. A high-ranked feature is only a candidate mechanic: it still requires an exact replay witness plus a current-Titan overlap check before anyone should create a gameplay lane.

## CSV schema

The reader resolves common aliases and fails closed if required columns are absent.

- match: `match_id`, `episode_id`, `episode`, `game_id`, `match`, `replay_id`
- team: `team`, `team_id`, `team_name`, `submission_id`, `agent`, `agent_id`, `submission`
- player/seat (optional): `player`, `seat`, `player_index`, `agent_index`, `player_id`
- step: `step`, `timestep`, `turn`, `turn_id`, `step_id`
- verb: `action_verb`, `verb`, `action`, `action_type`, `order_type`, `command`
- target (optional): `target`, `item`, `product`, `crop`, `animal`, `building`, `resource`
- quantity (optional): `qty`, `quantity`, `amount`, `units`, `count`

Top teams must be passed as a comma-separated list or newline-delimited file. Use leaderboard identities when available. If a corpus lacks leaderboard rank, a cohort derived from corpus performance must be labeled as such rather than described as the leaderboard top 10.

## Example

```bash
python -B mine_top_mechanics.py \
  --farmer-actions /path/to/farmer_actions.csv \
  --market-orders /path/to/market_orders.csv \
  --top-teams top_teams.txt \
  --min-top-teams 3 \
  --min-top-support 0.30 \
  --output mechanics.json
```

## Verification receipt

Landed miner Git blob: `0aa78703f26ee647bd5af5c0fbfd207ea3dd15f8`; SHA-256 `edd59b90460d801faa40e30fdb5a16f337955fcaad5245583fd028f1370c1045`.

Landed regression Git blob: `4666fcf7bc0f5c027e8663e457c280bbbffa41a2`; SHA-256 `66d236d59cd2511c59227aa77a3e8fd8c2d38c2d0550a07d20b6e2a95476d94f`.

Local verification before landing: **9/9 tests PASS** under both normal Python and `python -O`. The suite covers unique-team weighting, row-order-independent sequences, cross-source sequence non-fabrication, same-step co-occurrence, quantity mechanics, alias resolution, missing-top-team failure, enriched-sequence ranking, and strict JSON output.

## Pending data receipt

At tool landing, the replay corpus itself lived in Muse's workspace rather than Git. A schema/sample request was sent for `vijaikm/kaggriculture-match-replay-corpus` (`farmer_actions.csv`, `market_orders.csv`, `matches_meta.csv`). The first real-data run must record the exact resolved columns, corpus provenance/hash, explicit cohort identities, team/match counts, and output hash. Do not infer a top-agent mechanic from a guessed schema or from unmatched anecdotal replay examples.
