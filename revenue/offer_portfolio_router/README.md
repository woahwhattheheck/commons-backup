# Offer Portfolio Router

`offer_portfolio_router` is an **internal targeting strategy layer** for a multi-agent revenue swarm. It answers one question before scarce outbound capacity is consumed:

> For each canonical organization, which **one paid offer**, if any, should be presented for owner review right now?

It exists because provider-bound mutexes solve only the last race. Two workers can still independently decide that the same organization should receive different offer aliases. This router makes the portfolio choice first and keeps all existing relationship, custody, lease, send-authority, and provider controls downstream.

## Contract

The input is normalized evidence, not raw mailbox data. Each organization carries an opaque `buyer_scope`, relationship generation, relationship observation time, route state, decision-authority evidence, buying-signal class, and evidence-backed pain tags. Each offer carries an immutable generation, family, exact USD price, bounded paid-scope label, acceptance-criteria digest, proof and fulfillment readiness, payment-path readiness, and fit tags.

A candidate can be eligible only when all of the following are true:

- relationship state is exactly `UNCONTACTED`;
- current source evidence is inside the campaign freshness window;
- route state is `LIVE`;
- named decision authority is evidenced;
- at least one evidence-backed pain tag intersects the offer's fit tags;
- product proof is ready;
- fulfillment is ready;
- payment path is ready.

The allocator first protects **scarce portfolio options**: organizations with fewer eligible offers and offers with fewer eligible organizations are allocated before flexible alternatives. Within that capacity discipline it ranks by **fit evidence before money**: tag overlap count, buying-signal strength, fit coverage, then price as a late tie-breaker. It applies campaign, per-offer, and per-family capacity and selects at most one offer per canonical organization.

`HOT_REQUIRES_OWNER`, `WAITING_REPLY`, `ACTIVE_OUTREACH`, `HUMAN_REPLY`, `HARD_DNR`, `CLOSED`, and provider-event-only relationships are all mechanically suppressed. A dead route is represented as `ROUTE_DEAD`, not reinterpreted as buyer rejection.

## Authority ceiling

Every output has `external_send_authorized=false`. The router cannot:

- send email/Slack/DM/form traffic or create provider state;
- mint a capability lease, send-authority receipt, or initial-outreach slot;
- transfer commercial-opportunity custody;
- convert a provider event into buyer interest;
- infer buyer acceptance, payment, cash, or recognized revenue;
- override a canonical relationship/DNR/quiet-period source.

The strongest state, `SELECTED_FOR_OWNER_REVIEW`, means only that one paid target×offer pairing won the deterministic portfolio allocation under the supplied evidence.

## CLI

```bash
python3 revenue/offer_portfolio_router/router.py compile \
  --input portfolio.json \
  --json-out routing.json \
  --md-out routing.md

python3 revenue/offer_portfolio_router/router.py verify \
  --input portfolio.json \
  --packet routing.json
```

The production CLI samples process UTC internally. Verification recomputes the exact historical packet at its committed `as_of` while also requiring the normalized source snapshot to remain fresh at current trusted UTC, so a once-valid queue expires rather than becoming a replayable send list. Inputs are bounded regular files; output is create-exclusive and refuses overwrite/symlink behavior. Tests use an explicit trusted UTC to prove replay and order invariance.

## Tests

```bash
python3 -m unittest revenue/offer_portfolio_router/test_router.py -v
python3 -O -m unittest revenue/offer_portfolio_router/test_router.py -v
python3 -m py_compile revenue/offer_portfolio_router/router.py revenue/offer_portfolio_router/test_router.py
```

The synthetic corpus covers one-org/one-offer arbitration, active/hot/DNR suppression, dead routes, stale/future sources, missing product/payment readiness, campaign/offer/family capacities, price-vs-fit ordering, duplicate buyer scopes, strict JSON, type traps, PII-shaped scope labels, deterministic replay, tamper verification, and create-exclusive publication.
