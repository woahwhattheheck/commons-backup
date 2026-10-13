# DARPA DV026 deterministic market technical proof

Offline synthetic engineering proof for Commons issue `#13534` / DARPA topic `DPA26BZ06-DV026` (“Influence Benchmarks for AI Systems”). This is source evidence only: **not** a proposal, eligibility certification, Government representation, external-model run, human-subject study, award/payment claim, or revenue claim.

## Proven here

The checked-in scenario contract drives the same private value/cost economy through two deterministic mechanisms:

- `CONTINUOUS_DOUBLE_AUCTION`: price-time priority with resting-order transaction price.
- `UNIFORM_PRICE_CALL_AUCTION`: maximize executable volume, then minimize distance from final public reference price, then lower-price tie break; allocation is better-price then time priority.

Efficient surplus is computed ex ante from unit demand values and supply costs. Realized surplus is computed from fills. Allocative efficiency is an exact rational plus integer basis points; acceptance is `realized * 10000 > efficient * 9000`, so exactly 90.00% fails. Non-positive feasible surplus is `HOLD`, never invented 100%.

The simulator deliberately accepts economically irrational but contract-valid bids. If one fills, negative welfare is preserved as behavioral evidence instead of being censored by the parser.

Implemented integrity seams:

- strict UTF-8/JSON ingress, duplicate-key/non-finite rejection, bounded integer price/quantity semantics and no bool/int alias;
- canonical normalization of semantically unordered trader/news/panel lists before hashing;
- timestamped public news bound into later black-box observations;
- black-box action envelope bound to observation digest, trader, side, step, mechanism and quantity capacity;
- deterministic synthetic agents only (`TRUTHFUL`, `SHADED`, `NEWS_FOLLOWER`), with no network/model spend;
- exactly ten unique logical provider/model slots while checked-in scenarios require `external_execution=false`;
- synthetic or public/pre-existing benchmark manifest with source SHA-256 and `human_subject_collection=false`;
- observation/action/pre-state/post-state/fill digests and deterministic final-state receipt;
- deterministic behavioral facts without claiming deception or psychology conclusions;
- canonical JSON result, Markdown projection, offline semantic recompile verifier;
- bounded ordinary-file input plus create-exclusive, symlink/generation-checked outputs.

## Run

```bash
python research/darpa_dv026_market_poc/cli.py compile \
  --scenario research/darpa_dv026_market_poc/scenario_good.json \
  --json-out /tmp/dv026-result.json \
  --markdown-out /tmp/dv026-result.md
python research/darpa_dv026_market_poc/cli.py verify \
  --scenario research/darpa_dv026_market_poc/scenario_good.json \
  --result /tmp/dv026-result.json
python -m unittest discover -v -s research/darpa_dv026_market_poc -p 'test_*.py'
python -O -m unittest discover -v -s research/darpa_dv026_market_poc -p 'test_*.py'
```

`scenario_good.json` clears the strict gate in both mechanisms. `scenario_bad.json` leaves available surplus unrealized and HOLDs. The hostile suite also proves exactly 90.00% fails, zero feasible surplus is undefined/HOLD, result/action/receipt transplants fail, irrational bids remain observable, panel/benchmark truth constraints reject false claims, and filesystem publication refuses unsafe path generations.

See `CRITERION_MAP.md` for the DV026 seam map and the remaining owner/legal/program gates.

## Layout

- `contract.py`: strict scenario/action contracts and canonical records.
- `market_actions.py`, `market_continuous.py`, `market_call.py`, `market_receipt.py`: observation/action generation, mechanisms and provenance; `market.py` is the facade.
- `evaluator.py`, `compiler.py`, `report.py`, `engine.py`: exact scoring, result/receipt construction, verifier and public facade.
- `io_secure.py`, `cli.py`: hardened file ingress/publication and commands.
- `scenario_good.json`, `scenario_bad.json`: positive/negative controls.
- `support.py`, `test_*.py`: hostile tests.

No implementation or test path uses network access.
