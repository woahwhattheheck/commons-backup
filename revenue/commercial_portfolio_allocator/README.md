# Commercial Portfolio Allocator

`commercial-portfolio-allocator/v1` is an offline, deterministic allocator for scarce commercial execution capacity across qualified deals, competitions, and procurements. It sits above deal-specific systems and answers a narrow question: **which already-qualified opportunities deserve the next owner-review slots, given finite capacity and current evidence?**

It is not a CRM, outbound agent, bid submitter, payment system, or accounting ledger.

## Hard boundaries

The allocator never converts pipeline into booked revenue. Every output contains `booked_revenue_minor: 0` and `recognized_revenue_minor: 0`. It does not infer buyer acceptance, authorize contact, submit a bid, mutate a provider, or move money.

Conversion probability is also never invented from a stage label. Every opportunity must carry an explicit integer `conversion_ppm` plus a `conversion_basis_ref` and digest. Two opportunities at the same stage may therefore carry different declared conversion inputs. The engine reports those inputs; it does not claim they are statistically calibrated or externally authenticated.

A SHA-256 source digest proves byte identity only. It does not prove that a buyer, provider, bank, competition organizer, or procurement authority produced the source.

## Fail-closed eligibility

An opportunity is suppressed from allocation when any of these apply:

- state is `DNR`, `CLOSED`, or `BLOCKED`;
- deadline passed or lies beyond the portfolio horizon;
- evidence is older than the portfolio freshness ceiling;
- prerequisites or declared dependency keys are unsatisfied;
- owner review is not ready;
- required effort exceeds portfolio capacity;
- declared conversion/weighting yields zero allocatable value.

Future-dated evidence, changed same-`opportunity_id` facts, or two distinct opportunities sharing one `collision_key` HOLD the entire portfolio. `collision_key` is not free-form: it must equal the SHA-256 commitment derived from canonical `buyer_id + opportunity_key`, preventing parallel workers from evading a shared seam merely by spelling the collision label differently. This is deliberate: identity ambiguity must be reconciled before a fleet spends capacity.

Exact duplicate opportunity records are treated as replays and collapse for state evaluation. Same-ID generations are grouped before evaluation; duplicate multiplicities and each distinct generation digest are retained in a deterministic conflict projection. Input array order therefore does not change the receipt, including when conflicts and replays coexist.

## Current-time authority

Package-level `compile_plan(packet)` and `verify_plan(packet, plan)` own the process UTC clock. They do not accept a caller-selected `now`. Deterministic at-time evaluation exists only on underscore-prefixed internal surfaces used for historical receipt verification and tests.

`verify` reports historical receipt integrity separately from current decision semantics. The CLI exits successfully only when the historical receipt is valid **and** its allocation/hold decision still matches a fresh process-time evaluation; a historically authentic but now stale/expired plan does not clear the current gate.

## Objective and global capacity allocation

For each eligible opportunity, the engine computes integer-only metrics:

1. `expected_cash_pipeline_minor = gross_value_minor * conversion_ppm / 1e6`
2. risk adjustment using declared `risk_ppm`
3. deterministic deadline urgency from 1.0x at the portfolio horizon to 2.0x near the current evaluation time
4. declared `strategic_weight_ppm`

It then solves a deterministic 0/1 capacity allocation, not a greedy ranking. That means two smaller opportunities may correctly beat one individually attractive opportunity when their combined objective is higher under the same capacity limit.

The selected total is still pipeline expectation, never cash, booking, acceptance, or revenue recognition.

## CLI

```bash
python -m revenue.commercial_portfolio_allocator.cli compile portfolio.json --format json
python -m revenue.commercial_portfolio_allocator.cli compile portfolio.json --format markdown
python -m revenue.commercial_portfolio_allocator.cli verify portfolio.json plan.json
```

Ingress rejects duplicate JSON keys, non-regular final files, oversized inputs, and final-component symlinks where `O_NOFOLLOW` is available. Unknown object keys are rejected throughout the contract.

## Validation

```bash
python -m py_compile revenue/commercial_portfolio_allocator/*.py
python -m unittest revenue.commercial_portfolio_allocator.test_engine revenue.commercial_portfolio_allocator.test_cli
python -O -m unittest revenue.commercial_portfolio_allocator.test_engine revenue.commercial_portfolio_allocator.test_cli
python -m revenue.commercial_portfolio_allocator.acceptance
```
