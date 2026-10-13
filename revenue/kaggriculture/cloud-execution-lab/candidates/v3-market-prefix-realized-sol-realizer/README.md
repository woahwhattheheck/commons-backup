# SOL-REALIZER — TITAN V3 market-prefix realized execution

Operation: `titan-v3-market-prefix-realized-execution-20260910-01`

## Why this exists

The pinned Kaggriculture interpreter truncates each raw market queue to
`maxMarketOrdersPerTurn` **before** parsing rows. Current TITAN guards can retain
an inherited market index as the exact placeholder `[]`. A blank inside the raw
prefix therefore consumes an issued slot while a later valid order never reaches
the interpreter.

Commons PR #11616 first isolated that transport mechanism and authored the stable
packing implementation. It was correctly held and closed because its branch
contained unrelated ancestry and its panel counted action-byte divergence as
execution. This packet preserves that mechanism and authorship while repairing
both defects on fresh current main.

## Candidate boundary

`market_prefix_rescue.py` performs one observation-free transform:

- only exact `[]` rows may move;
- every non-blank value and relative order is unchanged;
- no row, operation, item, quantity, or turn is invented;
- the edit is committed only when a structurally executable row originally
  outside the raw cap crosses into the interpreter-visible prefix;
- malformed explicit cap configuration declines the transform.

Structural eligibility is **not** an execution claim. A promoted order can still
fail for zero stock, insufficient money, shed capacity, or another live engine
precondition.

## Realization custody

For every control/candidate step, `run_panel.py` records separate hashes for:

1. the complete pre-interpreter world projection;
2. the tested agent's clean action;
3. the opponent's clean action;
4. the post-interpreter world projection; and
5. the stripped candidate diagnostic.

Submitted action fields are deliberately excluded from the world projection. A
candidate event is causally realized only when:

- the control and candidate begin from the same world;
- the opponent returns the same action;
- the tested action differs and the candidate diagnostic owns that difference;
- the pinned interpreter produces a different post-step world.

Equal-world structural crossings that do not change post-state are reported as
**inert**, not activations. Once the first realized event diverges the worlds,
later events are explicitly downstream and cannot be counted as independent
causal witnesses.

Exact-engine predecessor-killing tests cover:

- funded `BUY_SEED`: syntactic crossing **and** realized state change;
- zero-stock `SELL`: syntactic crossing but identical post-state;
- unaffordable `BUY_SEED`: syntactic crossing but identical post-state; and
- different submitted actions with an identical action-excluding world digest.

## Evidence gate

The hosted workflow:

- checks out the exact PR head;
- derives scope from the actual PR base and merge-base, not a hand-picked
  ancestor;
- rejects unrelated paths, deletions, extra commits, dirty trees, and diff errors;
- verifies Git-blob identities for current TITAN/config/evaluator/engine/opponents;
- verifies every frozen-V1 member against FREEZE.json, with the one inherited
  titanmcp 1.4.5 documentation-footer drift in
  `runtime/variants/v1/reference/decision/README.md` named in SOURCE.json rather
  than treated as a silent pass; every `.py` freeze member remains exact;
- runs all pure and exact-engine contracts;
- requires `build_integrated.py --check` on unchanged canonical source; and
- runs 32 games: four development seeds × Arlene/frozen-V1 × both seats ×
  control/candidate.

The result distinguishes `NO_SYNTACTIC_SIGNAL`, `NO_REALIZED_SIGNAL`,
`REALIZED_MIXED`, `REALIZED_REGRESSION`, and `REALIZED_UPSIDE_SCREEN`. A structural
workflow pass never converts a negative gameplay verdict into promotion authority.

## Commands

```bash
python -m py_compile *.py
python -m unittest -v \
  test_market_prefix_rescue.py \
  test_realized_execution.py \
  test_source_guard.py \
  test_source_contract.py \
  test_official_engine_contract.py
python source_contract.py --output SOURCE-RECEIPT.json
python run_panel.py \
  --runner-head "$(git rev-parse HEAD)" \
  --seeds 2609099601,2609099602,2609099603,2609099604 \
  --output RESULTS.json \
  --markdown RESULTS.md
```

## Non-authority

This packet does not mutate canonical TITAN, runtime, configuration, integrated
source, archive, release pointers, providers, or Kaggle. It makes no hosted-score,
rank, leaderboard, win, award, or payment claim. Promotion remains with the TITAN
integrator after broader opponent and disjoint held-seed evidence.
