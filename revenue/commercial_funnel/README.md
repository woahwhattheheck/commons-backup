# Evidence-bound commercial funnel

`revenue/commercial_funnel` turns immutable commercial evidence references into a deterministic, buyer-neutral funnel packet across Commons' four first-class offering families: **PRODUCT**, **SERVICE**, **EXPERTISE**, and **DATA**.

It exists to enforce a simple commercial truth: **traffic, reply, acceptance, delivery, transfer, and cash are different facts**. One never silently promotes to another.

## Authority ceiling

The strongest successful state is `FUNNEL_PACKET_READY_FOR_HUMAN_REVIEW`. A packet is analytics, not commercial authority. Every generated packet and receipt states `false` for buyer-contact, acceptance, contract execution, fulfillment, transfer, provider/payment mutation, cash-availability, accounting/tax, and revenue-recognition authority.

This package performs no network requests and no external mutations. Evidence references are immutable Git commit + path + SHA-256 bindings supplied by the caller. The compiler validates their shape and semantic use; **it does not claim that a remote provider was queried or that the referenced bytes are authentic merely because a caller supplied a hash**. Provider/source capture remains a separate evidence-producing step.

## Stages and evidence roles

Normal stages are strictly ordered:

`TRAFFIC -> REPLY -> ACCEPTANCE -> DELIVERY -> TRANSFER -> CASH`

Special events are tracked without promotion:

- `NONCASH_AWARD`: records an exact integer quantity of a named non-cash asset. It never enters cash totals.
- `CASH_REVERSAL`: binds a prior `CASH` event ID and exact currency/minor-unit amount. Refunds/chargebacks/reversals reduce net-cash analytics and cannot exceed the referenced cash event.

A stronger immutable event may include `proves` for prior stages when that one evidence artifact genuinely establishes them. `proves` can only point backward; it cannot invent a future stage.

One immutable evidence source cannot be rebound as multiple distinct event IDs inside one opportunity. If one object proves multiple stages, represent that as one event plus explicit `proves`. Offer-definition evidence and event evidence are separate roles and cannot reuse the same source object. Across a packet, one logical `(family, offer id, version)` must resolve to one immutable offer source; multiple opportunities may intentionally reference that exact same definition.

## Fail-closed rules

The compiler rejects malformed schemas, duplicate opportunity IDs, floats, non-UTC timestamps, mutable/short commit refs, traversal paths, non-integer money, and secret/PII-shaped values. Opportunity analytics HOLD on event-ID conflicts, future/stale evidence, stage gaps, impossible stage time order, event-evidence reuse, offer/event role conflicts, logical-offer source drift, orphan/mismatched/excess reversals, and related evidence conflicts.

Duplicate replay of an **identical** event is idempotent. Input opportunity/event order does not change output bytes or receipt identity.

Evidence older than 366 days is HOLD for this current-funnel packet. Archive older cohorts separately rather than weakening the current evidence window.

## Deterministic outputs

`compile` writes, create-exclusively:

- `report.json` — canonical analytics body before self-describing output hashes;
- `report.csv` — one deterministic opportunity row per ID;
- `report.md` — human review summary;
- `packet.json` — canonical packet including output hashes;
- `receipt.json` — content-addressed receipt binding semantic input, packet, outputs, evaluation time, and the authority ceiling.

The CLI refuses to overwrite any of those files or follow a symlink at the output path.

## Current CLI and trusted time

The production CLI deliberately has **no caller-selected clock option**. `compile` samples process UTC at invocation. `verify` first byte-verifies the original packet at the evaluation instant bound into its receipt, then independently recompiles the time-sensitive semantics at current process UTC. Verification fails if the original evaluation time is in the future or if state, age buckets, metrics, evidence eligibility, or other semantic fields have changed with time.

From repository root:

```bash
python -m revenue.commercial_funnel.cli compile \
  revenue/commercial_funnel/example_input.json \
  --out-dir /tmp/commercial-funnel-example

python -m revenue.commercial_funnel.cli verify \
  revenue/commercial_funnel/example_input.json \
  --packet /tmp/commercial-funnel-example/packet.json \
  --receipt /tmp/commercial-funnel-example/receipt.json \
  --report-json /tmp/commercial-funnel-example/report.json \
  --report-csv /tmp/commercial-funnel-example/report.csv \
  --report-md /tmp/commercial-funnel-example/report.md
```

Exit codes: `0` ready/currently verified, `2` malformed/refused I/O contract, `3` compiled packet contains HOLD opportunities, `4` verification mismatch or no-longer-current semantics.

For deterministic historical tests, migrations, or forensic replay, the Python library retains explicit `compile_funnel(..., as_of=...)` and `verify_artifacts(..., as_of=...)`. Those APIs prove what the deterministic result was at the named instant; they do **not** assert that the result is current now. Use `verify_artifacts_current(..., trusted_now=...)` when the caller already owns a trusted runtime clock and needs current semantic verification.

## Money and conversion metrics

Cash is exact integer minor units and remains grouped by currency. There is no implicit FX conversion. Funnel counts and dropoffs include only opportunities whose evidence set is not HOLD, preventing malformed/stale/conflicted evidence from inflating conversion rates. Held opportunities remain visible with explicit reasons and next action `REVIEW_HOLD_REASONS`.

## Integration boundary with the commercial lifecycle ledger

This package owns **cross-opportunity funnel analytics**, including pre-opportunity/top-of-funnel stages such as `TRAFFIC` and `REPLY`, family-level conversion/dropoff metrics, and cohort cash evidence totals. The separate `revenue/commercial_lifecycle_ledger` owns **one bound commercial subject after opportunity selection**, including offer/send/acceptance/funding/execution/settlement/finance-recognition evidence and its reversal mechanics.

A lifecycle receipt may be referenced as immutable source evidence by a funnel event after an upstream verifier has authenticated it. The funnel does not import lifecycle authority, reinterpret finance recognition, or turn lifecycle state into buyer/payment/revenue authority. Conversely, the lifecycle ledger does not own funnel cohort selection, traffic/reply measurement, or cross-family conversion analytics.

## Development gate

```bash
python -m py_compile revenue/commercial_funnel/*.py
python -m unittest -v revenue.commercial_funnel.test_ledger revenue.commercial_funnel.test_cli revenue.commercial_funnel.test_review_regressions
python -O -m unittest -v revenue.commercial_funnel.test_ledger revenue.commercial_funnel.test_cli revenue.commercial_funnel.test_review_regressions
```

The focused suite includes a 128-opportunity deterministic acceptance corpus plus hostile replay, stage-skip, stale/future, evidence-role/reuse, offer-identity, reversal, trusted-time, type, timestamp, source-ref, output-order, PII/secret, and receipt-tamper cases.
