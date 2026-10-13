# V5 frontier replay behavior profiles

`frontier_replay_profile.py` turns an **exact recorded public Kaggriculture episode** into a deterministic returned-action fingerprint for one of the six rated `3000+` submissions pinned by `frontier-opponent-pack.json`.

This is evidence tooling, not an opponent implementation. A profile describes what an exact submission returned in one recorded episode. It is **not** evidence that a market order filled, a unit action succeeded, or the same submission would return the same action in a counterfactual game. It never promotes a replay, approximation, or the local stress-opponent league into executable leaderboard source.

## Required provenance

Every profile requires all three inputs:

1. raw public replay JSON containing `steps`;
2. an episode identity manifest with exact episode id and per-seat `submissionId` values (the checked-in `leader-reference-replay-manifest.json` is the model for this shape);
3. the checked-in `frontier-opponent-pack.json` proving the requested submission is one of the pinned rated targets.

The profiler records SHA-256 for all three inputs. It fails closed if the submission is not in the rated frontier pack, seat identity does not match, the replay/identity episode ids disagree, a replay row lacks the requested seat, or required structures are malformed.

## Replay semantics

The saved Kaggriculture evidence uses the Kaggle convention that replay row `t+1` contains the action selected from decision observation `t`; row `0` is therefore not counted as a decision action. Market profiling mirrors the pinned engine's executable prefix (`max(1, int(maxMarketOrdersPerTurn))`) and `_parse_order` quantity grammar, including `int(qty)` coercion and ignored trailing fields. Rows beyond the market prefix are counted as truncated rather than attributed as engine-visible intent.

Unit counts are returned-action intent. They include the farmer plus every returned hand action and do not claim that an action's game preconditions succeeded.

Profiles include early (days 0–9), mid (10–19), and late (20+) buckets with unit operation counts, market order/quantity counts, sale cadence, and active-step counts for HIRE, BUY_LAND, BUY_ANIMAL, BUY_SEED, PLANT, FEED, COLLECT_FERTILIZER, HARVEST, and SELL.

## VM usage

```sh
python -B frontier_replay_profile.py \
  --replay /path/to/exact-public-replay.json \
  --identity-manifest /path/to/exact-episode-manifest.json \
  --submission-id 56156662 \
  --seat 0 \
  --output /path/to/profile.json
```

Run the focused contract before fleet use:

```sh
python -B -m unittest -v test_frontier_replay_profile.py
python -O -B -m unittest -v test_frontier_replay_profile.py
```

For fleet comparisons, keep exact episode id, seat, submission id, replay SHA-256, and resulting profile artifact path together. Do not aggregate same-team uploads unless their exact submission ids are intentionally grouped as a separate analysis.