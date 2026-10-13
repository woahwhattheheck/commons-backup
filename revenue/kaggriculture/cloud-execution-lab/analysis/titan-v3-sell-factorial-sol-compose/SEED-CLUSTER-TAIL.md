# TITAN V3 independent-seed composition tail closure

This companion closes a decision-theory gap in the four-arm SELL interaction gate. The parent gate correctly rejects pooled gains that regress an opponent-by-seat stratum, but those aggregate screens can still hide a sharp loss in one independent environment seed.

## Exact predecessor

Seven seeds can have:

```text
control=100, own_value=101, certified_pressure=101, both=103
```

while an eighth seed has:

```text
control=100, own_value=101, certified_pressure=101, both=95
```

The pooled composed arm remains ahead, its median is positive, seven cells improve for every one that regresses, and every outcome can remain a win. Yet the composed arm loses 6 to each eligible singleton on one independent seed.

A second checkerboard predecessor is invisible even to seed means and opponent means: two opponents × two seeds can alternate `+6/-6` composition regret so every row and column mean is zero while two opponent×seed paired games regress.

## Guard

`seed_cluster_guard.py` consumes the complete JSON packet emitted by `interaction_gate.py` under exact operation identity:

```text
titan-v3-sell-objective-certified-pressure-factorial-gate-20260910-01
```

It validates the declared opponent × seed × seat grid and the upstream non-promotional disposition, then:

1. compares `both` with the per-cell best **eligible** singleton separately for own cash and margin;
2. preserves the best eligible singleton's W/T/L outcome rank in every cell;
3. pairs mirrored seats within each opponent × seed game;
4. collapses all opponents and both seats into each independent seed cluster;
5. requires nonnegative mean own-cash and margin regret in every opponent×seed pair and every seed cluster;
6. downgrades an unsafe `SELECT_BOTH` deterministically to the strongest eligible singleton.

The output binds both the exact input-byte SHA-256 and a canonical semantic SHA-256. It never authorizes promotion or a hosted leaderboard claim.

## Usage

```bash
python -B seed_cluster_guard.py \
  --input /evidence/FACTORIAL-DECISION.json \
  --head "$GITHUB_SHA" \
  --output /evidence/SEED-CLUSTER-DECISION.json \
  --markdown /evidence/SEED-CLUSTER-DECISION.md
```

## Verification

```text
python -B -m py_compile interaction_gate.py test_interaction_gate.py \
  seed_cluster_guard.py test_seed_cluster_guard.py
python -B -m unittest -v test_interaction_gate.py test_seed_cluster_guard.py

Parent: 28 tests
Tail closure: 13 tests
```

The tail suite retains the seven-good/one-bad predecessor, the opponent×seed checkerboard, mirrored-seat pairing, singleton fallback, lost-outcome protection, exact grid validation, duplicate-cell rejection, detached margin rejection, strict JSON parsing, byte/semantic receipt binding, and non-promotion boundaries.

## Custody boundary

This stacked child is based on PR #12048 head `6f92daf79863e1df1837edec50d37dee56308de3`. It modifies no factor, runtime, canonical archive, package pointer, evaluator, game result, provider state, Kaggle state, or submission state. The parent owner retains factor contracts, base-gate integration, evidence production, merge, promotion, and submission custody.
